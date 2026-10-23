"""Run: python demo.py. Uses the real PDFs and deterministic mock QA generator."""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core import Base, Document, Node, persist_parsed, changes

dbfile=Path('demo.db')
if dbfile.exists(): dbfile.unlink()
engine=create_engine('sqlite:///demo.db'); Base.metadata.create_all(engine); s=sessionmaker(bind=engine)()
d=Document(id='ct200',name='CardioTrack CT-200'); s.add(d); s.commit()
v1=persist_parsed(s,d.id,'v1','data/ct200_manual.pdf')
old=s.query(Node).filter_by(version_id=v1.id,heading_number='3.2').one()
print('v1 sections:',s.query(Node).filter_by(version_id=v1.id).count(),'selected:',old.heading)
v2=persist_parsed(s,d.id,'v2','data/ct200_manual_v2.pdf')
print('v2 sections:',s.query(Node).filter_by(version_id=v2.id).count())
print('selected source status:',changes(s,old.id,v1.id,v2.id))
print('New v2 section:',s.query(Node).filter_by(version_id=v2.id,heading_number='5.3').one().heading)
