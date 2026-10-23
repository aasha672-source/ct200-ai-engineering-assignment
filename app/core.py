from __future__ import annotations
import hashlib, json, re, uuid
from datetime import datetime, timezone
from pathlib import Path
from difflib import SequenceMatcher
import pymupdf
from sqlalchemy import create_engine, String, Integer, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session

def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid.uuid4())
def norm(s): return re.sub(r"\s+", " ", s).strip()
def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def heading_key(s): return re.sub(r"^\d+(?:\.\d+)*\s+", "", norm(s)).lower()

class Base(DeclarativeBase): pass
class Document(Base):
    __tablename__='documents'
    id: Mapped[str]=mapped_column(String,primary_key=True); name: Mapped[str]=mapped_column(String)
    versions: Mapped[list['Version']]=relationship(back_populates='document')
class Version(Base):
    __tablename__='versions'
    id: Mapped[str]=mapped_column(String,primary_key=True); document_id: Mapped[str]=mapped_column(ForeignKey('documents.id'))
    label: Mapped[str]=mapped_column(String); sha256: Mapped[str]=mapped_column(String); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    document: Mapped[Document]=relationship(back_populates='versions'); nodes: Mapped[list['Node']]=relationship(back_populates='version')
class Node(Base):
    __tablename__='nodes'
    id: Mapped[str]=mapped_column(String,primary_key=True); version_id: Mapped[str]=mapped_column(ForeignKey('versions.id'))
    logical_id: Mapped[str|None]=mapped_column(String,nullable=True); parent_id: Mapped[str|None]=mapped_column(String,nullable=True)
    position: Mapped[int]=mapped_column(Integer); heading: Mapped[str]=mapped_column(String); heading_number: Mapped[str|None]=mapped_column(String,nullable=True)
    level: Mapped[int]=mapped_column(Integer); body: Mapped[str]=mapped_column(Text); pages: Mapped[str]=mapped_column(String); content_hash: Mapped[str]=mapped_column(String)
    warnings: Mapped[str]=mapped_column(Text,default='[]'); version: Mapped[Version]=relationship(back_populates='nodes')
class VersionLogicalMap(Base):
    __tablename__='version_logical_mappings'; id: Mapped[str]=mapped_column(String,primary_key=True); version_id: Mapped[str]=mapped_column(ForeignKey('versions.id')); node_id: Mapped[str]=mapped_column(ForeignKey('nodes.id')); logical_id: Mapped[str]=mapped_column(String); confidence: Mapped[str]=mapped_column(String,default='heading_match')
class Selection(Base):
    __tablename__='selections'
    id: Mapped[str]=mapped_column(String,primary_key=True); name: Mapped[str]=mapped_column(String); version_id: Mapped[str]=mapped_column(String); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class SelectionItem(Base):
    __tablename__='selection_items'; id: Mapped[str]=mapped_column(String,primary_key=True); selection_id: Mapped[str]=mapped_column(ForeignKey('selections.id')); node_id: Mapped[str]=mapped_column(String); snapshot: Mapped[str]=mapped_column(Text); content_hash: Mapped[str]=mapped_column(String)

HEAD=re.compile(r'^(\d+(?:\.\d+)*)\s+(.+?)\s*$')
def parse_pdf(path: str):
    doc=pymupdf.open(path); chunks=[]
    for p,page in enumerate(doc,1):
        text=page.get_text('text').replace('\ufb01','fi').replace('\ufb02','fl')
        chunks += [(p, line.strip()) for line in text.splitlines() if line.strip()]
    nodes=[]; current=None; stack=[]; pos=0
    for page,line in chunks:
        m=HEAD.match(line)
        if m:
            num,title=m.groups(); lvl=len(num.split('.')); pos+=1
            while stack and stack[-1]['level']>=lvl: stack.pop()
            parent=stack[-1]['temp'] if stack else None
            warning=[]
            if stack and lvl>stack[-1]['level']+1: warning.append('skipped hierarchy level')
            n={'temp':uid(),'heading':line,'number':num,'level':lvl,'parent_temp':parent,'position':pos,'body':[],'pages':{page},'warnings':warning}
            nodes.append(n); stack.append(n); current=n
        elif current:
            current['body'].append(line); current['pages'].add(page)
    # title/unheaded first-page content remains intentionally outside tree rather than guessed
    return nodes

def persist_parsed(db:Session, document_id:str, label:str, pdf_path:str):
    raw=Path(pdf_path).read_bytes(); v=Version(id=uid(),document_id=document_id,label=label,sha256=hashlib.sha256(raw).hexdigest()); db.add(v); db.flush()
    parsed=parse_pdf(pdf_path); prior=db.query(Version).filter(Version.document_id==document_id,Version.id!=v.id).order_by(Version.created_at.desc()).first()
    old=db.query(Node).filter_by(version_id=prior.id).all() if prior else []
    used=set(); mapping={}
    for n in parsed:
        candidates=[o for o in old if o.id not in used and heading_key(o.heading)==heading_key(n['heading'])]
        if len(candidates)==1: mapping[n['temp']]=candidates[0].logical_id; used.add(candidates[0].id)
        elif len(candidates)>1: n['warnings'].append('ambiguous prior heading match')
        else: mapping[n['temp']]=uid()
    temp_to_id={n['temp']:uid() for n in parsed}
    for n in parsed:
        body=norm(' '.join(n['body'])); nid=temp_to_id[n['temp']]; logical=mapping.get(n['temp']) or uid(); db.add(Node(id=nid,version_id=v.id,logical_id=logical,parent_id=temp_to_id.get(n['parent_temp']),position=n['position'],heading=n['heading'],heading_number=n['number'],level=n['level'],body=body,pages=json.dumps(sorted(n['pages'])),content_hash=digest(body),warnings=json.dumps(n['warnings']))); db.add(VersionLogicalMap(id=uid(),version_id=v.id,node_id=nid,logical_id=logical,confidence='ambiguous' if n['warnings'] else 'heading_match'))
    db.commit(); return v

def changes(db, node, from_version, to_version):
    src=db.get(Node,node); target=db.query(Node).filter_by(version_id=to_version,logical_id=src.logical_id).all()
    if len(target)!=1: return {'status':'ambiguous_mapping' if target else 'removed','summary':'No unique logical-node match'}
    t=target[0]; return {'status':'unchanged' if src.content_hash==t.content_hash else 'modified','summary':diff_summary(src.body,t.body),'to_node_id':t.id}
def diff_summary(a,b):
    a_words=set(re.findall(r'\S+',a)); b_words=set(re.findall(r'\S+',b)); return 'added: '+', '.join(sorted(b_words-a_words)[:12])+'; removed: '+', '.join(sorted(a_words-b_words)[:12])
def impact(a,b): return 'potentially_high' if re.search(r'\d|mmHg|%|second|not |cannot|must',a+' '+b,re.I) else 'low'
