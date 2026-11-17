# AML Shield preparation and model-training pipeline.
# WARNING: Running this script rebuilds the SQLite database from the source CSV.
# The sampled evaluation pool is case-enriched; reported scores are not deployment estimates.

import os,sqlite3,json,random
from pathlib import Path
import pandas as pd,numpy as np
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier,HistGradientBoostingClassifier
from sklearn.metrics import precision_score,recall_score,f1_score,average_precision_score,confusion_matrix,accuracy_score
import joblib
ROOT=Path(__file__).parent; DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
SOURCE=Path(os.getenv('AML_TRANSACTIONS',str(DATA/'HI-Small_Trans.csv')))
DB=DATA/'aml.db'
CATS=['Receiving Currency','Payment Currency','Payment Format']
NUM=['Amount Received','Amount Paid','same_bank','self_transfer','currency_change','hour']
FEATURES=NUM+CATS

# Create numeric and categorical transaction features without including the target label.
def feature_frame(df):
    x=df[['Amount Received','Amount Paid','Receiving Currency','Payment Currency','Payment Format']].copy()
    x['same_bank']=(df['From Bank'].astype(str)==df['To Bank'].astype(str)).astype(int)
    x['self_transfer']=(df['Account'].astype(str)==df['Account.1'].astype(str)).astype(int)
    x['currency_change']=(df['Receiving Currency']!=df['Payment Currency']).astype(int)
    x['hour']=pd.to_datetime(df['Timestamp'],errors='coerce').dt.hour.fillna(0).astype(int)
    return x[FEATURES]

# Read the IBM CSV in chunks, build an indexed subset, train models, and save evaluation metadata.
def main():
    if not SOURCE.exists(): raise SystemExit('Missing transaction CSV: '+str(SOURCE))
    if DB.exists(): DB.unlink()
    conn=sqlite3.connect(DB); conn.execute('PRAGMA journal_mode=WAL');conn.execute('PRAGMA synchronous=OFF')
    conn.executescript('''CREATE TABLE transactions(id INTEGER PRIMARY KEY, timestamp TEXT,from_bank TEXT,sender TEXT,to_bank TEXT,receiver TEXT,received REAL,recv_currency TEXT,paid REAL,pay_currency TEXT,format TEXT,label INTEGER,score REAL DEFAULT NULL,pattern TEXT DEFAULT NULL);CREATE INDEX ix_sender ON transactions(sender);CREATE INDEX ix_receiver ON transactions(receiver);CREATE INDEX ix_label ON transactions(label);CREATE INDEX ix_date ON transactions(timestamp);CREATE TABLE cases(id INTEGER PRIMARY KEY AUTOINCREMENT,transaction_id INTEGER UNIQUE,status TEXT DEFAULT 'Open',priority TEXT DEFAULT 'High',assignee TEXT DEFAULT 'Unassigned',notes TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE audit(id INTEGER PRIMARY KEY AUTOINCREMENT,case_id INTEGER,action TEXT,details TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);''')
    rng=np.random.default_rng(42); samples=[];total=positive=0;idseq=0
    for chunk in pd.read_csv(SOURCE,chunksize=100000,dtype={'From Bank':str,'To Bank':str,'Account':str,'Account.1':str},low_memory=False):
        chunk['Is Laundering']=pd.to_numeric(chunk['Is Laundering'],errors='coerce').fillna(0).astype(int)
        total+=len(chunk);positive+=int(chunk['Is Laundering'].sum())
        # retain every labeled positive and a deterministic sample of negatives for interactive investigation
        keep=(chunk['Is Laundering'].eq(1) | (rng.random(len(chunk))<0.018))
        sub=chunk.loc[keep].copy()
        vals=[]
        for row in sub.itertuples(index=False,name=None):
            # schema order matches input csv
            idseq+=1
            ts,fb,sa,tb,ra,recv,rc,paid,pc,fmt,label=row
            vals.append((idseq,str(ts),str(fb),str(sa),str(tb),str(ra),float(recv),str(rc),float(paid),str(pc),str(fmt),int(label)))
        conn.executemany('INSERT INTO transactions(id,timestamp,from_bank,sender,to_bank,receiver,received,recv_currency,paid,pay_currency,format,label) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',vals)
        # representative train pool from raw original data, capped for memory
        pos=chunk[chunk['Is Laundering'].eq(1)]; neg=chunk[chunk['Is Laundering'].eq(0)].sample(n=min(2500,int((chunk['Is Laundering']==0).sum())),random_state=42)
        samples.extend([pos,neg]);conn.commit()
        print('Processed',total,'rows; labeled laundering',positive,flush=True)
    sample=pd.concat(samples,ignore_index=True)
    # avoid excessive positives/negatives; evaluate on a stratified untouched subset of the sampled evaluation pool
    if len(sample)>180000:sample=sample.sample(n=180000,random_state=42)
    y=sample['Is Laundering'].astype(int);X=feature_frame(sample)
    Xtr,Xte,ytr,yte=train_test_split(X,y,test_size=.25,random_state=42,stratify=y)
    try:enc=OneHotEncoder(handle_unknown='ignore',sparse_output=False)
    except TypeError:enc=OneHotEncoder(handle_unknown='ignore',sparse=False)
    pre=ColumnTransformer([('num',StandardScaler(),NUM),('cat',enc,CATS)])
    models={'Logistic Regression':LogisticRegression(max_iter=400,class_weight='balanced',random_state=42),'Random Forest':RandomForestClassifier(n_estimators=65,max_depth=13,min_samples_leaf=3,class_weight='balanced_subsample',n_jobs=-1,random_state=42)}
    metrics={};best=None;bestscore=-1
    for name,clf in models.items():
        pipe=Pipeline([('pre',pre),('model',clf)]);pipe.fit(Xtr,ytr);proba=pipe.predict_proba(Xte)[:,1];pred=(proba>=.5).astype(int)
        m={'precision':round(precision_score(yte,pred,zero_division=0),4),'recall':round(recall_score(yte,pred,zero_division=0),4),'f1':round(f1_score(yte,pred,zero_division=0),4),'auprc':round(average_precision_score(yte,proba),4),'accuracy':round(accuracy_score(yte,pred),4),'confusion_matrix':confusion_matrix(yte,pred,labels=[0,1]).tolist()}
        metrics[name]=m;joblib.dump(pipe,DATA/(name.lower().replace(' ','_')+'.joblib'))
        if m['auprc']>bestscore:bestscore=m['auprc'];best=name
    # train/test sampled selection is case enriched: state this explicitly
    joblib.dump(joblib.load(DATA/(best.lower().replace(' ','_')+'.joblib')),DATA/'best_model.joblib')
    for k,v in {'total':total,'positives':positive,'indexed':idseq,'model':best,'metrics':metrics,'train_pool':len(sample),'evaluation_note':'Case-enriched training/evaluation sample, not the full original transaction distribution; AUPRC cannot be interpreted as deployment performance.'}.items():conn.execute('INSERT INTO metadata VALUES (?,?)',(k,json.dumps(v)))
    conn.commit();conn.close();print('DONE',total,positive,idseq,best,metrics,flush=True)
if __name__=='__main__':main()
