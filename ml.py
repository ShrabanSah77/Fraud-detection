import os, json
import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score,precision_score,recall_score,f1_score,average_precision_score,confusion_matrix,precision_recall_curve
from xgboost import XGBClassifier

BASE=os.path.dirname(__file__)
CATS=['Country','Transaction Type','Industry','Destination Country']
NUM=['Amount (USD)','hour','day_of_week']
FEATURES=CATS+NUM

def prepare(df):
    df=df.copy()
    dates=pd.to_datetime(df['Date of Transaction'],errors='coerce')
    df['hour']=dates.dt.hour.fillna(0)
    df['day_of_week']=dates.dt.dayofweek.fillna(0)
    df['Amount (USD)']=pd.to_numeric(df['Amount (USD)'],errors='coerce').fillna(0)
    for c in CATS: df[c]=df[c].fillna('Unknown').astype(str)
    return df

def train():
    df=prepare(pd.read_csv(os.path.join(BASE,'data','transactions.csv')))
    y=df['Source of Money'].astype(str).str.lower().eq('illegal').astype(int)
    X=df[FEATURES]
    xtr,xte,ytr,yte=train_test_split(X,y,test_size=.25,random_state=42,stratify=y)
    os.makedirs(os.path.join(BASE,'models'),exist_ok=True)
    results={};best=None;bestscore=-1
    models={
        'Logistic Regression':LogisticRegression(max_iter=700,class_weight='balanced',random_state=42),
        'Random Forest':RandomForestClassifier(n_estimators=120,max_depth=15,min_samples_leaf=2,class_weight='balanced',random_state=42,n_jobs=-1),
        'XGBoost':XGBClassifier(n_estimators=140,max_depth=5,learning_rate=.07,subsample=.85,colsample_bytree=.9,eval_metric='logloss',random_state=42,n_jobs=2)
    }
    for name,est in models.items():
        prep=ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore'),CATS),('num',StandardScaler(),NUM)])
        pipe=Pipeline([('prep',prep),('model',est)])
        pipe.fit(xtr,ytr)
        p=pipe.predict_proba(xte)[:,1]; pred=(p>=.5).astype(int)
        precision,recall,thresholds=precision_recall_curve(yte,p)
        results[name]={'accuracy':round(accuracy_score(yte,pred),4),'precision':round(precision_score(yte,pred,zero_division=0),4),'recall':round(recall_score(yte,pred,zero_division=0),4),'f1':round(f1_score(yte,pred,zero_division=0),4),'auprc':round(average_precision_score(yte,p),4),'confusion_matrix':confusion_matrix(yte,pred,labels=[0,1]).tolist(),'pr_curve':{'precision':precision[::max(1,len(precision)//70)].round(3).tolist(),'recall':recall[::max(1,len(recall)//70)].round(3).tolist()}}
        joblib.dump(pipe,os.path.join(BASE,'models',name.lower().replace(' ','_')+'.joblib'))
        if results[name]['auprc']>bestscore:bestscore=results[name]['auprc'];best=name
        print(name,results[name]['f1'],results[name]['auprc'],flush=True)
    info={'models':results,'selected':best,'training_rows':len(xtr),'test_rows':len(xte),'positive_rate':round(float(y.mean()),4),'target':'Source of Money: Illegal (proxy label, not confirmed AML conviction)','notes':'Stratified holdout, fixed seed; no target or Reported by Authority feature leakage. Dataset has a high positive rate and is not representative of typical banking prevalence. No SMOTE used; class weights are applied to baseline models.'}
    with open(os.path.join(BASE,'models','metrics.json'),'w') as f:json.dump(info,f,indent=2)
    return info

if __name__=='__main__':train()
