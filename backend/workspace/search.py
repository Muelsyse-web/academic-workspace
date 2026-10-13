"""Scoped FTS5 retrieval with a Chinese/substring fallback."""
import re
from fastapi import APIRouter, Query, Request

router = APIRouter(prefix='/api/v1')


def index_text(text):
    fragments = set()
    for run in re.findall(r'[\u3400-\u9fff]+', text):
        fragments.update(run)
        fragments.update(run[i:i+2] for i in range(len(run)-1))
    return text + '\n' + ' '.join(sorted(fragments))


def search(db,q,course_id='',document_id='',kind='',limit=20,offset=0,tag=''):
    query = q.strip()[:500]
    if not query:
        return {'mode':'keyword','hits':[],'total':0}
    clauses = ['c.version_id=d.active_version']
    args = []
    if course_id:
        clauses.append('EXISTS(SELECT 1 FROM document_courses dc WHERE dc.document_id=d.id AND dc.course_id=?)')
        args.append(course_id)
    if document_id:
        clauses.append('d.id=?'); args.append(document_id)
    if kind:
        clauses.append('d.kind=?'); args.append(kind)
    if tag:
        clauses.append('EXISTS(SELECT 1 FROM json_each(d.tags) WHERE value=?)'); args.append(tag)
    terms = re.findall(r'[^\W_]+',query,flags=re.UNICODE)[:40]
    expression = ' OR '.join('"'+term.replace('"','""')+'"' for term in terms)
    cte = 'WITH matched AS MATERIALIZED (SELECT chunk_id,bm25(chunks_fts) score FROM chunks_fts WHERE chunks_fts MATCH ?) '
    prefix_args = [expression]
    if not terms:
        cte = 'WITH matched AS (SELECT NULL chunk_id,0 score WHERE 0) '
        prefix_args = []
    source = """ FROM chunks c JOIN documents d ON d.id=c.document_id
        JOIN source_units u ON u.id=c.unit_id LEFT JOIN matched m ON m.chunk_id=c.id """
    condition = 'm.chunk_id IS NOT NULL OR instr(lower(c.text),lower(?))>0'
    match_args = [query]
    if len(terms)>1:
        condition += ' OR ('+' AND '.join('instr(lower(c.text),lower(?))>0' for _ in terms)+')'
        match_args.extend(terms)
    where = ' WHERE '+' AND '.join(clauses)+' AND ('+condition+')'
    parameters = prefix_args+args+match_args
    total = db.one(cte+'SELECT count(*) n'+source+where,parameters)['n']
    select = """SELECT c.id chunk_id,c.document_id,c.version_id,c.text,d.title,d.kind,
        u.locator_type,u.locator,u.heading,coalesce(m.score,0) score"""
    order = ' ORDER BY CASE WHEN instr(lower(c.text),lower(?))>0 THEN 0 ELSE 1 END,coalesce(m.score,0),d.id,u.locator,c.ordinal LIMIT ? OFFSET ?'
    rows = db.all(cte+select+source+where+order,parameters+[query,limit,offset])
    for rank,row in enumerate(rows,offset):
        row['relevance_score']=1/(60+rank+1)
    return {'mode':'keyword','hits':rows,'total':total}



@router.get('/search')
def search_route(request: Request,mode: str='keyword',q: str='',course_id: str='',document_id: str='',kind: str='',tag: str='',limit: int=Query(20,ge=1,le=100),offset: int=Query(0,ge=0)):
    if mode in ('semantic','hybrid'):
        from .embeddings import semantic_search,hybrid_search
        return (semantic_search if mode=='semantic' else hybrid_search)(request.app,q,course_id,document_id,kind,limit,offset,tag)
    return search(request.app.state.db,q,course_id,document_id,kind,limit,offset,tag)
