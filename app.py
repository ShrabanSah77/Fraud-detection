import os, json, sqlite3, io
import pandas as pd
import numpy as np
from flask import Flask,render_template,request,jsonify
from werkzeug.utils import secure_filename
from ml import prepare,FEATURES,train
import joblib
BASE=os.path.dirname(__file__)
app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=12*1024*1024
DATA=os.path.join(BASE,'data','transactions.csv')
DB=os.path.join(BASE,'data','cases.sqlite')
MODEL_DIR=os.path.join(BASE,'models')
_cache={}

def db():
    c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
    c.execute('CREATE TABLE IF NOT EXISTS cases (transaction_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT "Open", notes TEXT NOT NULL DEFAULT "", updated_at TEXT DEFAULT CURRENT_TIMESTAMP)');c.commit();return c

def data():
    df=pd.read_csv(DATA)
    df['Amount (USD)']=pd.to_numeric(df['Amount (USD)'],errors='coerce').fillna(0)
    return df

def model():
    path=os.path.join(MODEL_DIR,'metrics.json')
    if not os.path.exists(path):return None,None
    with open(path) as f:meta=json.load(f)
    name=meta['selected'];p=os.path.join(MODEL_DIR,name.lower().replace(' ','_')+'.joblib')
    if name not in _cache:_cache[name]=joblib.load(p)
    return _cache[name],meta

def assess(df):
    df=df.copy().reset_index(drop=True)
    m,meta=model()
    df['ml_score']=(m.predict_proba(prepare(df)[FEATURES])[:,1]*100).round(1) if m else np.nan
    df['risk_score']=0.;df['reasons']=''
    counts=df['Person Involved'].astype(str).value_counts()
    for i,r in df.iterrows():
        a=float(r['Amount (USD)']); reasons=[];points=0
        if a>=1000000:points+=28;reasons.append('Large transaction ≥ $1M')
        elif a>=100000:points+=15;reasons.append('High transaction value')
        typ=str(r['Transaction Type']).lower()
        if any(x in typ for x in ['offshore','crypto']):points+=24;reasons.append('Offshore/crypto channel')
        if str(r['Country']).lower()!=str(r['Destination Country']).lower():points+=12;reasons.append('Cross-border transfer')
        if counts.get(str(r['Person Involved']),0)>=3:points+=12;reasons.append('Repeated customer activity in current batch')
        if bool(r['Reported by Authority']):points+=18;reasons.append('Previously reported by authority')
        if pd.notna(df.at[i,'ml_score']):points+=float(df.at[i,'ml_score'])*.30
        df.at[i,'risk_score']=round(min(points,100),1)
        df.at[i,'reasons']='; '.join(reasons) or 'No configured rule triggered'
    df['risk_level']=np.where(df['risk_score']>=70,'Critical',np.where(df['risk_score']>=45,'High',np.where(df['risk_score']>=25,'Medium','Low')))
    return df

@app.get('/')
def home():return render_template('index.html')

@app.get('/api/overview')
def overview():
    df=assess(data());c=db();statuses={r['transaction_id']:r['status'] for r in c.execute('SELECT transaction_id,status FROM cases')};c.close()
    df['case_status']=df['Transaction ID'].map(statuses).fillna('Unreviewed')
    top=df.sort_values('risk_score',ascending=False).head(14)
    return jsonify({'total':len(df),'volume':round(float(df['Amount (USD)'].sum()),2),'flagged':int((df.risk_score>=45).sum()),'critical':int((df.risk_score>=70).sum()),'reported':int(df['Reported by Authority'].astype(str).str.lower().eq('true').sum()),'illegal_label':int(df['Source of Money'].astype(str).str.lower().eq('illegal').sum()),'risk_counts':{k:int(v) for k,v in df.risk_level.value_counts().items()},'types':{k:int(v) for k,v in df['Transaction Type'].value_counts().head(8).items()},'countries':{k:int(v) for k,v in df['Country'].value_counts().head(8).items()},'top':records(top),'model_ready':model()[0] is not None})

def records(df):
    fields=['Transaction ID','Country','Destination Country','Amount (USD)','Transaction Type','Date of Transaction','Person Involved','Industry','Reported by Authority','ml_score','risk_score','risk_level','reasons','case_status']
    return json.loads(df[[x for x in fields if x in df.columns]].where(pd.notna(df),None).to_json(orient='records'))

@app.get('/api/transactions')
def transactions():
    df=assess(data());q=request.args.get('q','').strip().lower();risk=request.args.get('risk','All');page=max(1,int(request.args.get('page',1)))
    if q:df=df[df[['Transaction ID','Person Involved','Country','Destination Country','Transaction Type']].astype(str).apply(lambda col:col.str.lower().str.contains(q,regex=False)).any(axis=1)]
    if risk!='All':df=df[df.risk_level==risk]
    df=df.sort_values('risk_score',ascending=False);total=len(df);df=df.iloc[(page-1)*50:page*50]
    c=db();statuses={r['transaction_id']:r['status'] for r in c.execute('SELECT transaction_id,status FROM cases')};c.close();df=df.copy();df['case_status']=df['Transaction ID'].map(statuses).fillna('Unreviewed')
    return jsonify({'total':total,'page':page,'rows':records(df)})

@app.get('/api/metrics')
def metrics():
    _,meta=model()
    return jsonify(meta if meta else {'error':'Model not trained. Run python ml.py first.'}),200 if meta else 404

@app.post('/api/predict')
def predict():
    payload=request.get_json(silent=True) or {}
    required=['Country','Amount (USD)','Transaction Type','Date of Transaction','Person Involved','Industry','Destination Country']
    if any(not str(payload.get(k,'')).strip() for k in required):return jsonify({'error':'Missing required transaction fields'}),400
    try:
        amount=float(payload['Amount (USD)'])
        if not np.isfinite(amount) or amount<0:raise ValueError()
    except (ValueError,TypeError):return jsonify({'error':'Amount must be a nonnegative number'}),400
    payload.update({'Amount (USD)':amount,'Transaction ID':'MANUAL-DEMO','Reported by Authority':bool(payload.get('Reported by Authority',False))})
    try:row=assess(pd.DataFrame([payload]));return jsonify(records(row)[0])
    except Exception as e:return jsonify({'error':str(e)}),400

@app.post('/api/upload')
def upload():
    f=request.files.get('file')
    if not f or not f.filename.lower().endswith('.csv'):return jsonify({'error':'Please upload a CSV file'}),400
    try:
        df=pd.read_csv(f)
        required=['Country','Amount (USD)','Transaction Type','Date of Transaction','Person Involved','Industry','Destination Country','Reported by Authority']
        missing=[x for x in required if x not in df.columns]
        if missing:return jsonify({'error':'Missing columns: '+', '.join(missing)}),400
        if len(df)>10000:return jsonify({'error':'Maximum 10,000 rows per upload'}),400
        if 'Transaction ID' not in df:df['Transaction ID']=['UPLOAD-'+str(i+1) for i in range(len(df))]
        df['Reported by Authority']=df['Reported by Authority'].astype(str).str.lower().isin(['true','1','yes'])
        scored=assess(df)
        return jsonify({'total':len(scored),'flagged':int((scored.risk_score>=45).sum()),'rows':records(scored.sort_values('risk_score',ascending=False).head(200)),'note':'Upload is analyzed in memory; original reference dataset is unchanged.'})
    except Exception as e:return jsonify({'error':str(e)}),400

@app.get('/api/cases')
def cases():
    c=db();rows=[dict(x) for x in c.execute('SELECT * FROM cases ORDER BY updated_at DESC')];c.close();return jsonify(rows)

@app.post('/api/cases/<transaction_id>')
def save_case(transaction_id):
    p=request.get_json(silent=True) or {};status=p.get('status','Open')
    if status not in ['Open','Investigating','Escalated','Closed - Cleared','Closed - Suspicious']:return jsonify({'error':'Invalid status'}),400
    notes=str(p.get('notes',''))[:2000]
    c=db();c.execute('INSERT INTO cases(transaction_id,status,notes,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(transaction_id) DO UPDATE SET status=excluded.status,notes=excluded.notes,updated_at=CURRENT_TIMESTAMP',(transaction_id,status,notes));c.commit();c.close()
    return jsonify({'ok':True})

if __name__=='__main__':
    db().close();app.run(host='127.0.0.1',port=5000,debug=False)
