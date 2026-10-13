"""Optional local semantic index. A failed rebuild keeps the prior generation."""
from concurrent.futures import ThreadPoolExecutor
import heapq
import json
import math
from fastapi import APIRouter, HTTPException, Request
from .db import new_id,now
from .configuration import provider_config,get_provider,provider_snapshot
from .providers import ProviderError
from .search import search

router=APIRouter(prefix='/api/v1/embeddings')


class EmbeddingWorker:
    def __init__(self,app):
        self.app=app
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='embeddings')
        with app.state.db.connect() as con:
            con.execute("UPDATE embedding_runs SET status='failed',error='Indexing interrupted; retry to rebuild.' WHERE status IN ('queued','processing')")
            con.execute('DELETE FROM embedding_staging')

    def close(self):
        self.pool.shutdown(wait=True)

    def submit(self,identifier,config,provider):
        self.pool.submit(self.run,identifier,config,provider)

    def run(self,identifier,config,provider):
        db=self.app.state.db
        try:
            with db.connect() as con:
                con.execute("UPDATE embedding_runs SET status='processing' WHERE id=?",(identifier,))
            snapshot=[row['id'] for row in db.all('SELECT c.id FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.version_id=d.active_version ORDER BY c.id')]
            total=len(snapshot)
            dimension=None
            offset=0
            while True:
                identifiers=snapshot[offset:offset+16]
                if not identifiers:break
                rows=db.all('SELECT id,text FROM chunks WHERE id IN ('+','.join('?' for _ in identifiers)+') ORDER BY id',identifiers)
                if len(rows)!=len(identifiers):raise ProviderError('Source documents changed during indexing; rebuild again.')
                if not rows:break
                vectors=provider.embed([row['text'] for row in rows])
                if len(vectors)!=len(rows):raise ProviderError('Embedding count changed during indexing')
                with db.connect() as con:
                    for row,vector in zip(rows,vectors):
                        if dimension is None:dimension=len(vector)
                        if not dimension or len(vector)!=dimension or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in vector):
                            raise ProviderError('Embedding dimensions changed during indexing')
                        con.execute('INSERT INTO embedding_staging VALUES (?,?,?,?)',(identifier,row['id'],dimension,json.dumps(vector)))
                    offset+=len(rows)
                    con.execute('UPDATE embedding_runs SET progress=? WHERE id=?',(min(99,round(100*offset/max(total,1))),identifier))
            with db.connect() as con:
                current={row['id'] for row in con.execute('SELECT c.id FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.version_id=d.active_version')}
                if current!=set(snapshot):raise ProviderError('Source documents changed during indexing; rebuild again.')
                con.execute('DELETE FROM embeddings WHERE provider=? AND model=?',(config['base_url'],config['embedding_model']))
                con.execute('INSERT INTO embeddings SELECT chunk_id,?,?,dimension,vector,? FROM embedding_staging WHERE run_id=?',(config['base_url'],config['embedding_model'],now(),identifier))
                con.execute('DELETE FROM embedding_staging WHERE run_id=?',(identifier,))
                con.execute("UPDATE embedding_runs SET status='done',progress=100 WHERE id=?",(identifier,))
        except Exception as exc:
            error=str(exc)[:300] if isinstance(exc,ProviderError) else 'Embedding indexing failed; previous index is preserved.'
            with db.connect() as con:
                con.execute('DELETE FROM embedding_staging WHERE run_id=?',(identifier,))
                con.execute("UPDATE embedding_runs SET status='failed',error=? WHERE id=?",(error,identifier))


@router.get('/status')
def status(request: Request):
    return request.app.state.db.one('SELECT * FROM embedding_runs ORDER BY created_at DESC LIMIT 1') or {'status':'idle','progress':0}


@router.post('/reindex',status_code=202)
def reindex(request: Request):
    db=request.app.state.db
    config,provider=provider_snapshot(request.app)
    if not config['embedding_model']:
        raise HTTPException(422,'Select a local embedding model first.')
    identifier=new_id()
    with db.connect() as con:
        if con.execute("SELECT id FROM embedding_runs WHERE status IN ('queued','processing')").fetchone():
            raise HTTPException(409,'Embedding indexing already running')
        con.execute('INSERT INTO embedding_runs(id,status,provider,model,created_at) VALUES (?,?,?,?,?)',(identifier,'queued',config['base_url'],config['embedding_model'],now()))
    request.app.state.embedding_worker.submit(identifier,config,provider)
    return {'id':identifier,'status':'queued'}


def semantic_search(app,q,course_id='',document_id='',kind='',limit=20,offset=0,tag=''):
    db=app.state.db
    def fallback(reason):
        return {**search(db,q,course_id,document_id,kind,limit,offset,tag),'warning':reason}
    config,provider=provider_snapshot(app)
    if not config['embedding_model']:
        return fallback('未配置 Embedding 模型，使用关键词检索。')
    where=['e.provider=?','e.model=?','c.version_id=d.active_version']
    args=[config['base_url'],config['embedding_model']]
    if course_id:
        where.append('EXISTS(SELECT 1 FROM document_courses dc WHERE dc.document_id=d.id AND dc.course_id=?)');args.append(course_id)
    if document_id:where.append('d.id=?');args.append(document_id)
    if kind:where.append('d.kind=?');args.append(kind)
    if tag:where.append('EXISTS(SELECT 1 FROM json_each(d.tags) WHERE value=?)');args.append(tag)
    source=' FROM embeddings e JOIN chunks c ON c.id=e.chunk_id JOIN documents d ON d.id=c.document_id JOIN source_units u ON u.id=c.unit_id WHERE '+' AND '.join(where)
    if not db.one('SELECT count(*) n'+source,args)['n']:
        return fallback('当前范围没有可用语义索引，请先构建索引。')
    try:
        vector=provider.embed([q])[0]
        norm=math.sqrt(sum(x*x for x in vector))
        if not norm:raise ProviderError('Query embedding is empty')
        ranked=[]
        total=0
        select='SELECT e.dimension,e.vector,c.id chunk_id,c.document_id,c.version_id,c.text,d.title,d.kind,u.locator_type,u.locator,u.heading'
        with db.connect() as con:
            cursor=con.execute(select+source,args)
            while batch:=cursor.fetchmany(64):
                for row in batch:
                    hit=dict(row)
                    stored=json.loads(hit.pop('vector'))
                    if hit.pop('dimension')!=len(vector):raise ProviderError('Embedding model dimensions changed; rebuild the index.')
                    other_norm=math.sqrt(sum(x*x for x in stored))
                    score=sum(a*b for a,b in zip(vector,stored))/(norm*other_norm) if other_norm else 0
                    if score<=0:continue
                    hit['score']=score
                    hit['relevance_score']=score
                    total+=1
                    heapq.heappush(ranked,(score,hit['chunk_id'],hit))
                    if len(ranked)>limit+offset:heapq.heappop(ranked)
        hits=[entry[2] for entry in sorted(ranked,reverse=True)][offset:offset+limit]
        return {'mode':'semantic','hits':hits,'total':total}
    except (ProviderError,ValueError,TypeError,IndexError) as exc:
        return fallback(str(exc) if isinstance(exc,ProviderError) else '语义索引不可用，请重新索引。')


def hybrid_search(app,q,course_id='',document_id='',kind='',limit=20,offset=0,tag=''):
    # Retrieve the same bounded candidate window for stable pagination.
    keyword=search(app.state.db,q,course_id,document_id,kind,100,0,tag)
    semantic=semantic_search(app,q,course_id,document_id,kind,100,0,tag)
    if semantic['mode']=='keyword':
        return {**search(app.state.db,q,course_id,document_id,kind,limit,offset,tag),'warning':semantic.get('warning')}
    scores={};hits={}
    for group in (keyword['hits'],semantic['hits']):
        for index,hit in enumerate(group):
            identifier=hit['chunk_id'];hits[identifier]=hit
            scores[identifier]=scores.get(identifier,0)+1/(60+index+1)
    ordered=sorted(hits,key=lambda key:(-scores[key],key))
    return {'mode':'hybrid','hits':[{**hits[key],'relevance_score':scores[key]} for key in ordered[offset:offset+limit]],'total':len(ordered),'candidate_limit':200}
