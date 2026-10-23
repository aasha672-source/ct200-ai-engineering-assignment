from __future__ import annotations
import json, os, shutil
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .core import *
URL=os.getenv('DATABASE_URL','sqlite:///./ct200.db'); engine=create_engine(URL,connect_args={'check_same_thread':False}); SessionLocal=sessionmaker(bind=engine); Base.metadata.create_all(engine)
app=FastAPI(title='CT-200 Requirements Traceability API')
def db():
 s=SessionLocal()
 try: yield s
 finally: s.close()
def node_out(n): return {'id':n.id,'version_id':n.version_id,'logical_id':n.logical_id,'parent_id':n.parent_id,'heading':n.heading,'heading_number':n.heading_number,'level':n.level,'body':n.body,'pages':json.loads(n.pages),'content_hash':n.content_hash,'warnings':json.loads(n.warnings)}
@app.post('/documents/ingest')
async def ingest(document_name:str=Form(...), version_label:str=Form(...), document_id:str|None=Form(None), file:UploadFile=File(...), s:Session=Depends(db)):
 d=s.get(Document,document_id) if document_id else Document(id=uid(),name=document_name)
 if not d: raise HTTPException(404,'document not found')
 if not document_id: s.add(d); s.commit()
 p=Path('uploads'); p.mkdir(exist_ok=True); target=p/f'{uid()}.pdf'
 with target.open('wb') as out: shutil.copyfileobj(file.file,out)
 v=persist_parsed(s,d.id,version_label,str(target)); return {'document_id':d.id,'version_id':v.id}
@app.get('/documents/{document_id}/versions')
def versions(document_id:str,s:Session=Depends(db)): return [{'id':v.id,'label':v.label,'created_at':v.created_at} for v in s.query(Version).filter_by(document_id=document_id).all()]
@app.get('/documents/{document_id}/sections')
def sections(document_id:str,version:str,s:Session=Depends(db)): return [node_out(n) for n in s.query(Node).filter_by(version_id=version,parent_id=None).order_by(Node.position)]
@app.get('/nodes/search')
def search(q:str,version:str,s:Session=Depends(db)): return [node_out(n) for n in s.query(Node).filter(Node.version_id==version,(Node.heading.contains(q)|Node.body.contains(q))).all()]
@app.get('/nodes/{node_id}')
def get_node(node_id:str,version:str,s:Session=Depends(db)):
 n=s.query(Node).filter_by(id=node_id,version_id=version).first()
 if not n: raise HTTPException(404,'node not found')
 x=node_out(n); x['children']=[node_out(c) for c in s.query(Node).filter_by(parent_id=n.id).order_by(Node.position)]; return x
@app.get('/nodes/{node_id}/changes')
def node_changes(node_id:str,from_version:str,to_version:str,s:Session=Depends(db)): return changes(s,node_id,from_version,to_version)
class SelectionIn(BaseModel): name:str; version_id:str; node_ids:list[str]=Field(min_length=1)
@app.post('/selections')
def select(x:SelectionIn,s:Session=Depends(db)):
 sel=Selection(id=uid(),name=x.name,version_id=x.version_id); s.add(sel)
 for nid in x.node_ids:
  n=s.query(Node).filter_by(id=nid,version_id=x.version_id).first()
  if not n: raise HTTPException(422,f'node {nid} not in version')
  s.add(SelectionItem(id=uid(),selection_id=sel.id,node_id=n.id,snapshot=n.body,content_hash=n.content_hash))
 s.commit(); return {'selection_id':sel.id}
@app.get('/selections/{selection_id}')
def selection(selection_id:str,s:Session=Depends(db)):
 sel=s.get(Selection,selection_id)
 if not sel: raise HTTPException(404,'selection not found')
 return {'id':sel.id,'name':sel.name,'version_id':sel.version_id,'items':[{'node_id':i.node_id,'snapshot':i.snapshot,'content_hash':i.content_hash} for i in s.query(SelectionItem).filter_by(selection_id=sel.id)]}

class GenerateIn(BaseModel): selection_id:str; regenerate:bool=False
def store_path(): return Path('generated_outputs.json')
def load_generations(): return json.loads(store_path().read_text()) if store_path().exists() else []
def save_generations(rows): store_path().write_text(json.dumps(rows,indent=2))
def mock_cases(items):
 out=[]
 for i in range(3):
  item=items[i%len(items)]; out.append({'title':f'Traceable requirement verification {i+1}','objective':'Verify behavior stated in the selected CT-200 source.','source_node_id':item.node_id,'requirement_references':[item.content_hash],'preconditions':['CT-200 test unit is available'],'steps':['Set up the condition described in the source snapshot.',f'Exercise requirement scenario {i+1}.','Record observed behavior.'],'expected_results':['Observed behavior matches the source snapshot; flag ambiguity if it cannot be evaluated.'],'priority':'high','category':'functional','safety_relevance':'Review if the selected requirement is safety-related.'})
 return out
@app.post('/generations')
def generate(x:GenerateIn,s:Session=Depends(db)):
 sel=s.get(Selection,x.selection_id)
 if not sel: raise HTTPException(404,'selection not found')
 items=s.query(SelectionItem).filter_by(selection_id=sel.id).all(); key=digest('|'.join(i.content_hash for i in items)+'mock-qa-v1')
 rows=load_generations(); existing=next((r for r in rows if r['idempotency_key']==key),None)
 if existing and not x.regenerate: return existing
 row={'generation_id':uid(),'selection_id':sel.id,'idempotency_key':key,'model':'mock-qa-v1','created_at':now().isoformat(),'validation_status':'valid','cases':mock_cases(items),'sources':[{'node_id':i.node_id,'version_id':sel.version_id,'content_hash':i.content_hash,'snapshot':i.snapshot} for i in items]}; rows.append(row); save_generations(rows); return row
def stale(row,s):
 result=[]
 for src in row['sources']:
  old=s.get(Node,src['node_id']); latest=s.query(Version).filter_by(document_id=old.version.document_id).order_by(Version.created_at.desc()).first(); matches=s.query(Node).filter_by(version_id=latest.id,logical_id=old.logical_id).all()
  if not matches: status='source_removed'; current=None
  elif len(matches)!=1: status='ambiguous_mapping'; current=None
  else:
   current=matches[0]; status='current' if current.content_hash==src['content_hash'] else 'stale'
  result.append({'source_node_id':src['node_id'],'source_version_id':src['version_id'],'current_version_id':latest.id,'status':status,'original_hash':src['content_hash'],'current_hash':current.content_hash if current else None,'impact':impact(src['snapshot'],current.body) if current else 'unknown','diff_summary':diff_summary(src['snapshot'],current.body) if current else 'logical mapping unavailable'})
 return result
@app.get('/generations/{generation_id}')
def generation(generation_id:str,s:Session=Depends(db)):
 row=next((r for r in load_generations() if r['generation_id']==generation_id),None)
 if not row: raise HTTPException(404,'generation not found')
 return row|{'staleness':stale(row,s)}
@app.get('/selections/{selection_id}/generations')
def selection_generations(selection_id:str,s:Session=Depends(db)): return [r|{'staleness':stale(r,s)} for r in load_generations() if r['selection_id']==selection_id]
@app.get('/nodes/{node_id}/generations')
def node_generations(node_id:str,s:Session=Depends(db)): return [r|{'staleness':stale(r,s)} for r in load_generations() if any(x['node_id']==node_id for x in r['sources'])]
