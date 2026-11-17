# AML Shield backend: serves the dashboard APIs, scores replayed transactions, and manages investigations.
# Dataset labels are synthetic ground truth; generated alerts are only review signals.

import json,sqlite3,os,math,threading,time
import pandas as pd
import joblib
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
ROOT=Path(__file__).parent;DB=ROOT/'data/aml.db'

# Open the SQLite database with dictionary-style result rows.
def db():
 c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row;return c
 
# Run a query that returns multiple rows as JSON-ready dictionaries.
def rows(sql,args=()):
 with db() as c:return [dict(r) for r in c.execute(sql,args).fetchall()]
 
# Retrieve a single database record, or None if missing.
def one(sql,args=()):
 with db() as c:
  r=c.execute(sql,args).fetchone();return dict(r) if r else None
  
# Assemble transaction details, risk indicators, linked records, and case information.
def detail(id):
 t=one('SELECT * FROM transactions WHERE id=?',(id,))
 if not t:return None
 reasons=[]
 if t['label']:reasons.append('Synthetic dataset labels this transaction as laundering')
 if t['sender']==t['receiver']:reasons.append('Same source and destination account')
 if t['from_bank']!=t['to_bank']:reasons.append('Interbank transfer')
 if t['recv_currency']!=t['pay_currency']:reasons.append('Currency conversion')
 if t['paid']>=100000:reasons.append('Large nominal payment (currency-specific; not FX normalized)')
 t['reasons']=reasons;t['case']=one('SELECT * FROM cases WHERE transaction_id=?',(id,))
 t['related']=rows('SELECT id,timestamp,sender,receiver,paid,pay_currency,label FROM transactions WHERE (sender=? OR receiver=? OR sender=? OR receiver=?) AND id!=? ORDER BY timestamp DESC LIMIT 40',(t['sender'],t['sender'],t['receiver'],t['receiver'],id))
 t['network']=rows('SELECT sender,receiver,paid,pay_currency,label FROM transactions WHERE (sender=? OR receiver=? OR sender=? OR receiver=?) LIMIT 75',(t['sender'],t['sender'],t['receiver'],t['receiver']))
 return t

# Replay real IBM HI-Small records from the indexed subset; labels are hidden from scoring.
STREAM_LOCK=threading.RLock()
MODEL=None
FEATURE_COLUMNS=['Amount Received','Amount Paid','same_bank','self_transfer','currency_change','hour','Receiving Currency','Payment Currency','Payment Format']

# Create persistent replay state and event tables when needed.
def init_stream():
 with db() as c:
  c.executescript("""CREATE TABLE IF NOT EXISTS stream_state(id INTEGER PRIMARY KEY CHECK(id=1),cursor INTEGER NOT NULL DEFAULT 0,running INTEGER NOT NULL DEFAULT 0,processed INTEGER NOT NULL DEFAULT 0,alerts INTEGER NOT NULL DEFAULT 0);INSERT OR IGNORE INTO stream_state(id) VALUES (1);CREATE TABLE IF NOT EXISTS stream_events(id INTEGER PRIMARY KEY AUTOINCREMENT,transaction_id INTEGER NOT NULL,processed_at TEXT DEFAULT CURRENT_TIMESTAMP,model_score REAL NOT NULL,rule_score INTEGER NOT NULL,risk_score INTEGER NOT NULL,severity TEXT NOT NULL,reasons TEXT NOT NULL,alert INTEGER NOT NULL,synthetic_label INTEGER NOT NULL);CREATE INDEX IF NOT EXISTS ix_stream_tx ON stream_events(transaction_id);""")
  c.commit()

# Load the saved ML pipeline and combine predicted probability with illustrative risk rules.
def score_batch(transactions):
 global MODEL
 if MODEL is None:MODEL=joblib.load(ROOT/'data/best_model.joblib')
 features=[]
 for t in transactions:
  features.append({'Amount Received':t['received'],'Amount Paid':t['paid'],'same_bank':int(t['from_bank']==t['to_bank']),'self_transfer':int(t['sender']==t['receiver']),'currency_change':int(t['recv_currency']!=t['pay_currency']),'hour':int(t['timestamp'][11:13]) if len(t['timestamp'])>=13 else 0,'Receiving Currency':t['recv_currency'],'Payment Currency':t['pay_currency'],'Payment Format':t['format']})
 probs=MODEL.predict_proba(pd.DataFrame(features)[FEATURE_COLUMNS])[:,1]
 output=[]
 for t,prob in zip(transactions,probs):
  reasons=[];points=0
  if t['sender']==t['receiver']:reasons.append('Self-account transfer');points+=18
  if t['from_bank']!=t['to_bank']:reasons.append('Interbank transfer');points+=8
  if t['recv_currency']!=t['pay_currency']:reasons.append('Currency conversion');points+=12
  
  # Nominal currency amounts are not comparable across currencies.
  if t['paid']>=100000 and t['pay_currency']=='US Dollar':reasons.append('Large USD-denominated transfer');points+=16
  
  # Historical account graph in indexed subset, not a full-transaction history.
  score=int(round(min(100,100*(.75*float(prob)+.25*(points/54)))))
  severity='Critical' if score>=80 else 'High' if score>=60 else 'Medium' if score>=40 else 'Low'
  output.append((t['id'],float(prob),points,score,severity,json.dumps(reasons or ['ML feature-based assessment']),int(score>=60),t['label']))
 return output

# Advance the historical replay cursor and store scored events and alerts.
def stream_step(batch=5):
 batch=max(1,min(30,int(batch)))
 with STREAM_LOCK:
  with db() as c:
   st=c.execute('SELECT * FROM stream_state WHERE id=1').fetchone()
   if not st['running']:return stream_status()
   
   # Ordering is fixed by historical timestamp and id; cursor is the ordinal offset.
   ts=[dict(r) for r in c.execute('SELECT * FROM transactions ORDER BY timestamp,id LIMIT ? OFFSET ?',(batch,st['cursor']))]
   if not ts:
    c.execute('UPDATE stream_state SET running=0 WHERE id=1');c.commit();return stream_status()
   events=score_batch(ts)
   c.executemany('INSERT INTO stream_events(transaction_id,model_score,rule_score,risk_score,severity,reasons,alert,synthetic_label) VALUES (?,?,?,?,?,?,?,?)',events)
   c.execute('UPDATE stream_state SET cursor=cursor+?,processed=processed+?,alerts=alerts+? WHERE id=1',(len(ts),len(ts),sum(e[6] for e in events)))
   c.commit()
  return stream_status()

# Return replay progress and recent events to the frontend.
def stream_status():
 st=one('SELECT * FROM stream_state WHERE id=1')
 events=rows('SELECT e.*,t.timestamp,t.sender,t.receiver,t.paid,t.pay_currency,t.format FROM stream_events e JOIN transactions t ON t.id=e.transaction_id ORDER BY e.id DESC LIMIT 60')
 return {'state':st,'events':events,'mode':'Historical IBM HI-Small indexed-subset replay; not a live bank feed','model':'Saved Random Forest or Logistic Regression model; scores not calibrated','label_policy':'Synthetic labels shown for retrospective evaluation only, never used as scoring inputs'}


# Query observed account-to-account transfers and compute network indicators.
def network_analysis(account, limit=120):
 """Local, indexed-subset account graph. These are indicators, not AML findings."""
 account = str(account).strip()
 if not account or len(account) > 100:
  raise ValueError('Enter a valid account identifier')
 limit = max(10, min(int(limit), 200))
 with db() as c:
  
  # Focus on direct neighbors; retrieve actual transactions, not invented edges.
  direct = [dict(r) for r in c.execute(
   'SELECT id,timestamp,sender,receiver,paid,pay_currency,label FROM transactions '
   'WHERE sender=? OR receiver=? ORDER BY timestamp DESC,id DESC LIMIT ?',
   (account,account,limit)).fetchall()]
  peers = list(dict.fromkeys([x['receiver'] if x['sender']==account else x['sender'] for x in direct]))[:30]
  edges = direct[:]
  if peers:
   marks = ','.join('?' for _ in peers)
   extra = c.execute(
    f'SELECT id,timestamp,sender,receiver,paid,pay_currency,label FROM transactions '
    f'WHERE sender IN ({marks}) AND receiver IN ({marks}) '
    'ORDER BY timestamp DESC,id DESC LIMIT 150',peers+peers).fetchall()
   seen={x['id'] for x in edges}
   edges += [dict(x) for x in extra if x['id'] not in seen]
 sent = [x for x in direct if x['sender']==account]
 received = [x for x in direct if x['receiver']==account]
 sources = {x['sender'] for x in received if x['sender']!=account}
 targets = {x['receiver'] for x in sent if x['receiver']!=account}
 indicators=[]
 if len(sources)>=3:indicators.append({'type':'Fan-in','detail':f'{len(sources)} distinct incoming counterparties in retrieved history'})
 if len(targets)>=3:indicators.append({'type':'Fan-out','detail':f'{len(targets)} distinct outgoing counterparties in retrieved history'})
 pairs={(x['sender'],x['receiver']) for x in edges}
 reciprocal=sorted(x for x in sources & targets if x!=account)
 if reciprocal:indicators.append({'type':'Reciprocal transfers','detail':f'Both directions observed with {len(reciprocal)} counterparties; sequence not established'})
 cycles=[]
 for a,b in pairs:
  if a!=account or b==account:continue
  for c,d in pairs:
   if c==b and d not in (account,b) and (d,account) in pairs:
    path=[account,b,d,account]
    if path not in cycles:cycles.append(path)
    if len(cycles)>=5:break
  if len(cycles)>=5:break
 if cycles:indicators.append({'type':'Three-account cycle','detail':f'{len(cycles)} possible directed cycles in indexed records; timestamps/amounts not validated'})
 return {'account':account,'edges':edges,'direct_count':len(direct),
         'incoming':len(received),'outgoing':len(sent),'sources':len(sources),
         'targets':len(targets),'indicators':indicators,'cycles':cycles,
         'scope':'Indexed HI-Small investigation subset only; limited recent records and sampled normals. Patterns are exploratory, not proof of laundering.'}

init_stream()
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT/'static'),**kw)
 
 # Serialize API responses to JSON with an HTTP status code.
 def sendjson(self,obj,status=200):
  raw=json.dumps(obj,default=str).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 
 # Serve read-only API endpoints; otherwise serve static frontend files.
 def do_GET(self):
  u=urlparse(self.path);p=u.path;q={k:v[0] for k,v in parse_qs(u.query).items()}
  try:
   if p=='/api/overview':
    meta={r['key']:json.loads(r['value']) for r in rows('SELECT * FROM metadata')};meta['cases']=one('SELECT COUNT(*) n FROM cases')['n'];meta['open_cases']=one("SELECT COUNT(*) n FROM cases WHERE status NOT IN ('Closed','Dismissed')")['n'];meta['alerts']=rows('SELECT id,timestamp,sender,receiver,paid,pay_currency,format,label FROM transactions WHERE label=1 ORDER BY timestamp DESC LIMIT 8');meta['daily']=rows('SELECT substr(timestamp,1,10) day,COUNT(*) total,SUM(label) flagged FROM transactions GROUP BY substr(timestamp,1,10) ORDER BY day');meta['formats']=rows('SELECT format,COUNT(*) n,SUM(label) flagged FROM transactions GROUP BY format ORDER BY flagged DESC LIMIT 8');return self.sendjson(meta)
   if p=='/api/transactions':
    where=[];params=[]
    if q.get('label') in ('0','1'):where.append('label=?');params.append(int(q['label']))
    if q.get('search'):where.append('(sender LIKE ? OR receiver LIKE ? OR from_bank LIKE ? OR to_bank LIKE ?)');params.extend(['%'+q['search']+'%']*4)
    if q.get('format'):where.append('format=?');params.append(q['format'])
    sql=' WHERE '+' AND '.join(where) if where else '';page=max(1,min(100000,int(q.get('page','1'))));limit=30
    data=rows('SELECT id,timestamp,from_bank,sender,to_bank,receiver,paid,pay_currency,format,label FROM transactions'+sql+' ORDER BY id DESC LIMIT ? OFFSET ?',params+[limit,(page-1)*limit]);return self.sendjson({'items':data,'page':page,'limit':limit,'total':one('SELECT COUNT(*) n FROM transactions'+sql,params)['n']})
   if p.startswith('/api/transaction/'):
    t=detail(int(p.rsplit('/',1)[1]));return self.sendjson(t,200 if t else 404)
   if p=='/api/cases':return self.sendjson(rows('SELECT c.*,t.sender,t.receiver,t.paid,t.pay_currency,t.label,t.timestamp FROM cases c JOIN transactions t ON t.id=c.transaction_id ORDER BY c.updated_at DESC LIMIT 300'))
   if p.startswith('/api/case/'):
    id=int(p.rsplit('/',1)[1]);c=one('SELECT * FROM cases WHERE id=?',(id,));return self.sendjson({'case':c,'audit':rows('SELECT * FROM audit WHERE case_id=? ORDER BY id DESC',(id,))} if c else {},200 if c else 404)
   if p=='/api/stream':return self.sendjson(stream_status())
   if p=='/api/network':return self.sendjson(network_analysis(q.get('account',''),q.get('limit',120)))
   if p=='/api/health':return self.sendjson({'ok':DB.exists()})
   if p=='/':self.path='/index.html'
   return super().do_GET()
  except Exception as e:return self.sendjson({'error':str(e)},500)
 
 # Process replay controls and investigation updates sent from the browser.
 def do_POST(self):
  p = urlparse(self.path).path
  try:
   n = int(self.headers.get('Content-Length', '0'))
   if n > 100000:
    return self.sendjson({'error': 'Request too large'}, 413)
   data = json.loads(self.rfile.read(n) or b'{}')

   if p == '/api/stream/control':
    action = data.get('action')
    with STREAM_LOCK:
     with db() as c:
      if action == 'start':
       c.execute('UPDATE stream_state SET running=1 WHERE id=1')
      elif action == 'pause':
       c.execute('UPDATE stream_state SET running=0 WHERE id=1')
      elif action == 'reset':
       c.execute('UPDATE stream_state SET cursor=0,running=0,processed=0,alerts=0 WHERE id=1')
       c.execute('DELETE FROM stream_events')
      elif action == 'step':
       pass
      else:
       return self.sendjson({'error': 'Invalid action'}, 400)
      c.commit()
    if action == 'step':
     return self.sendjson(stream_step(data.get('batch', 5)))
    return self.sendjson(stream_status())

   if p == '/api/cases':
    try:
     tx = int(data['transaction_id'])
    except (KeyError, ValueError, TypeError):
     return self.sendjson({'error': 'Valid transaction_id required'}, 400)
    with db() as c:
     transaction = c.execute('SELECT id FROM transactions WHERE id=?', (tx,)).fetchone()
     if transaction is None:
      return self.sendjson({'error': f'Transaction {tx} not found'}, 404)
     cursor = c.execute('INSERT OR IGNORE INTO cases(transaction_id) VALUES (?)', (tx,))
     created = cursor.rowcount == 1
     case = c.execute('SELECT id FROM cases WHERE transaction_id=?', (tx,)).fetchone()
     if case is None:
      raise ValueError('Unable to create investigation case')
     if created:
      c.execute('INSERT INTO audit(case_id,action,details) VALUES (?,?,?)',
                (case['id'], 'Created', 'Case opened for review'))
     c.commit()
    print('INVESTIGATION CASE:', case['id'], flush=True)
    return self.sendjson({'id': case['id']})

   if p.startswith('/api/case/'):
    cid = int(p.rsplit('/', 1)[1])
    status = data.get('status', 'Open')
    priority = data.get('priority', 'High')
    notes = str(data.get('notes', ''))[:5000]
    assignee = str(data.get('assignee', 'Unassigned'))[:100]
    if status not in ['Open', 'Investigating', 'Escalated', 'Closed', 'Dismissed']:
     return self.sendjson({'error': 'Invalid status'}, 400)
    if priority not in ['Low', 'Medium', 'High', 'Critical']:
     return self.sendjson({'error': 'Invalid priority'}, 400)
    with db() as c:
     existing = c.execute('SELECT id FROM cases WHERE id=?', (cid,)).fetchone()
     if existing is None:
      return self.sendjson({'error': 'Case not found'}, 404)
     c.execute('UPDATE cases SET status=?,priority=?,assignee=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
               (status, priority, assignee, notes, cid))
     c.execute('INSERT INTO audit(case_id,action,details) VALUES (?,?,?)',
               (cid, 'Updated', f'{status}; {priority}; assigned {assignee}; notes: {notes[:180]}'))
     c.commit()
    return self.sendjson({'ok': True})

   return self.sendjson({'error': 'Not found'}, 404)
  except Exception as e:
   print('POST ERROR:', repr(e), flush=True)
   return self.sendjson({'error': str(e)}, 400)
if __name__=='__main__':
 if not DB.exists():raise SystemExit('Run python prepare.py first')
 port=int(os.getenv('PORT','8000'));print(f'AML Shield 3.0 http://localhost:{port}',flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
