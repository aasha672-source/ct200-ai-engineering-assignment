from app.core import parse_pdf, Base, Document, persist_parsed, Node
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path
def test_actual_parser_irregularities():
 n=parse_pdf('data/ct200_manual.pdf'); nums=[x['number'] for x in n]
 assert '2.1.1.1' in nums and nums.index('3.4') < nums.index('3.3')
def test_nested_parenting():
 n=parse_pdf('data/ct200_manual.pdf'); x=next(x for x in n if x['number']=='2.1.1.1'); assert x['level']==4
def test_duplicate_headings_preserved():
 n=parse_pdf('data/ct200_manual.pdf'); assert sum('Error Codes' in x['heading'] for x in n)==2
def test_page_continuation():
 n=parse_pdf('data/ct200_manual_v2.pdf'); x=next(x for x in n if x['number']=='4.3'); assert len(x['pages'])==2
def test_table_body_is_preserved():
 n=parse_pdf('data/ct200_manual.pdf'); x=next(x for x in n if x['number']=='2.1'); assert 'Pressure range' in ' '.join(x['body'])
def test_version_matching_changes():
 e=create_engine('sqlite://'); Base.metadata.create_all(e); s=sessionmaker(bind=e)(); d=Document(id='d',name='x');s.add(d);s.commit(); a=persist_parsed(s,'d','v1','data/ct200_manual.pdf'); b=persist_parsed(s,'d','v2','data/ct200_manual_v2.pdf'); assert s.query(Node).filter_by(version_id=b.id).count()>0
