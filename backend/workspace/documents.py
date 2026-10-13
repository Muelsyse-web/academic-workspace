"""Original-preserving imports and document metadata/source access."""
import hashlib
import json
import re
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from .db import now, new_id

router = APIRouter(prefix='/api/v1')
MAX_UPLOAD = 100*1024*1024
KINDS = {'pdf','pptx','docx','txt','md'}


def get_document(db, identifier):
    doc = db.one('SELECT * FROM documents WHERE id=?',(identifier,))
    if not doc:
        raise HTTPException(404,'Document not found')
    doc['tags'] = json.loads(doc['tags'])
    doc['favorite'] = bool(doc['favorite'])
    doc['course_ids'] = [r['course_id'] for r in db.all('SELECT course_id FROM document_courses WHERE document_id=?',(identifier,))]
    doc['related_ids'] = [r['target_id'] for r in db.all('SELECT target_id FROM document_links WHERE source_id=?',(identifier,))]
    job = db.one('SELECT id,error FROM jobs WHERE document_id=? ORDER BY created_at DESC LIMIT 1',(identifier,))
    doc['job_id'] = job['id'] if job else None
    doc['error'] = job['error'] if job else None
    return doc


def queue_job(con, identifier):
    existing = con.execute("SELECT id FROM jobs WHERE document_id=? AND status IN ('queued','processing')",(identifier,)).fetchone()
    if existing:
        return existing['id']
    job_id = new_id()
    con.execute('INSERT INTO jobs(id,document_id,status,created_at,updated_at) VALUES (?,?,?,?,?)',(job_id,identifier,'queued',now(),now()))
    con.execute("UPDATE documents SET status='queued' WHERE id=?",(identifier,))
    return job_id


@router.post('/documents',status_code=202)
def import_documents(request: Request, files: Annotated[list[UploadFile],File()],course_id: Annotated[str,Form()]=''):
    db = request.app.state.db
    if course_id and not db.one('SELECT id FROM courses WHERE id=?',(course_id,)):
        raise HTTPException(404,'Course not found')
    if len(files)>100:
        raise HTTPException(422,'Import at most 100 files per batch')
    # Prevalidate batch types before writing any originals.
    for file in files:
        relative = (file.filename or '').replace('\\','/')
        if relative.startswith('/') or '..' in relative.split('/') or re.match(r'^[A-Za-z]:',relative) or len(relative)>2048:
            raise HTTPException(422,'Folder paths must be relative and cannot contain traversal')
        if Path(file.filename or '').suffix.lower().lstrip('.') not in KINDS:
            raise HTTPException(422,'Supported formats: PDF, PPTX, DOCX, TXT, Markdown')
    originals = db.root/'originals'
    incoming = db.root/'incoming'
    originals.mkdir(exist_ok=True)
    incoming.mkdir(exist_ok=True)
    result = []
    for file in files:
        name = (file.filename or 'Untitled').replace('\\','/').split('/')[-1]
        relative = (file.filename or name).replace('\\','/')
        kind = Path(name).suffix.lower().lstrip('.')
        temporary = incoming/new_id()
        sha = hashlib.sha256()
        size = 0
        try:
            with temporary.open('wb') as stream:
                while block := file.file.read(1024*1024):
                    size += len(block)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413,'File exceeds 100 MiB limit')
                    sha.update(block)
                    stream.write(block)
            checksum = sha.hexdigest()
            with db.connect() as con:
                doc = con.execute('SELECT id,status,kind FROM documents WHERE blob_hash=?',(checksum,)).fetchone()
                if doc:
                    identifier = doc['id']
                    job_id = None
                    if doc['status'] in ('failed','needs_attention') and doc['kind'] != kind:
                        con.execute('UPDATE documents SET kind=?,filename=?,title=?,relative_path=? WHERE id=?',(kind,name,Path(name).stem,relative,identifier))
                        job_id = queue_job(con,identifier)
                else:
                    identifier = new_id()
                    target = originals/checksum
                    if not target.exists():
                        temporary.replace(target)
                    con.execute('INSERT OR IGNORE INTO blobs VALUES (?,?,?,?)',(checksum,size,kind,now()))
                    con.execute('INSERT INTO documents(id,blob_hash,title,filename,kind,created_at,relative_path) VALUES (?,?,?,?,?,?,?)',(identifier,checksum,Path(name).stem,name,kind,now(),relative))
                    job_id = queue_job(con,identifier)
                if course_id:
                    con.execute('INSERT OR IGNORE INTO document_courses VALUES (?,?)',(identifier,course_id))
            if job_id:
                request.app.state.index_worker.submit(job_id)
            result.append(get_document(db,identifier))
        finally:
            temporary.unlink(missing_ok=True)
            file.file.close()
    return result


@router.get('/documents')
def documents(request: Request,course_id: str='',kind: str='',q: str='',tag: str='',topic: str=''):
    db = request.app.state.db
    clauses, args = ['1=1'], []
    if course_id:
        clauses.append('EXISTS(SELECT 1 FROM document_courses dc WHERE dc.document_id=d.id AND dc.course_id=?)')
        args.append(course_id)
    if kind:
        clauses.append('d.kind=?')
        args.append(kind)
    if q:
        clauses.append('instr(lower(d.title),lower(?))>0')
        args.append(q)
    if topic:
        clauses.append('d.topic=?');args.append(topic)
    if tag:
        clauses.append('EXISTS(SELECT 1 FROM json_each(d.tags) WHERE value=?)')
        args.append(tag)
    rows = db.all('SELECT d.id FROM documents d WHERE '+' AND '.join(clauses)+' ORDER BY d.created_at DESC',args)
    return [get_document(db,r['id']) for r in rows]


@router.get('/documents/{identifier}')
def document(identifier: str,request: Request):
    return get_document(request.app.state.db,identifier)


class DocumentPatch(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    title: str | None = Field(default=None,min_length=1,max_length=300)
    favorite: bool | None = None
    topic: str | None = Field(default=None,max_length=200)
    tags: list[str] | None = Field(default=None,max_length=40)
    course_ids: list[str] | None = None
    related_ids: list[str] | None = None


@router.patch('/documents/{identifier}')
def patch_document(identifier: str,body: DocumentPatch,request: Request):
    db = request.app.state.db
    get_document(db,identifier)
    values = body.model_dump(exclude_none=True)
    with db.connect() as con:
        if body.course_ids is not None:
            for course in body.course_ids:
                if not con.execute('SELECT 1 FROM courses WHERE id=?',(course,)).fetchone():
                    raise HTTPException(404,'Course not found')
            con.execute('DELETE FROM document_courses WHERE document_id=?',(identifier,))
            con.executemany('INSERT INTO document_courses VALUES (?,?)',[(identifier,c) for c in set(body.course_ids)])
        if body.related_ids is not None:
            for related in body.related_ids:
                if related == identifier or not con.execute('SELECT 1 FROM documents WHERE id=?',(related,)).fetchone():
                    raise HTTPException(422,'Invalid related document')
            con.execute('DELETE FROM document_links WHERE source_id=?',(identifier,))
            con.executemany('INSERT INTO document_links VALUES (?,?)',[(identifier,r) for r in set(body.related_ids)])
        for key in ('title','favorite','topic','tags'):
            if key in values:
                value = json.dumps(list(dict.fromkeys(values[key])),ensure_ascii=False) if key == 'tags' else values[key]
                con.execute(f'UPDATE documents SET {key}=? WHERE id=?',(value,identifier))
    return get_document(db,identifier)


@router.post('/documents/{identifier}/reindex',status_code=202)
def reindex(identifier: str,request: Request):
    db = request.app.state.db
    get_document(db,identifier)
    with db.connect() as con:
        job_id = queue_job(con,identifier)
    request.app.state.index_worker.submit(job_id)
    return {'job_id':job_id}


@router.get('/documents/{identifier}/units')
def units(identifier: str,request: Request,version_id: str=''):
    db = request.app.state.db
    doc = get_document(db,identifier)
    version = version_id or doc['active_version']
    if version and not db.one('SELECT id FROM document_versions WHERE id=? AND document_id=?',(version,identifier)):
        raise HTTPException(404,'Document version not found')
    return db.all('SELECT * FROM source_units WHERE version_id=? ORDER BY locator,rowid',(version,))


@router.get('/documents/{identifier}/original')
def original(identifier: str,request: Request,download: bool=False):
    db = request.app.state.db
    doc = get_document(db,identifier)
    path = db.root/'originals'/doc['blob_hash']
    if not path.is_file():
        raise HTTPException(404,'Original missing; restore from backup')
    return FileResponse(path,filename=doc['filename'],media_type='application/pdf' if doc['kind']=='pdf' else 'application/octet-stream',content_disposition_type='attachment' if download or doc['kind']!='pdf' else 'inline')


@router.get('/jobs')
def jobs(request: Request):
    return request.app.state.db.all('SELECT j.*,d.title FROM jobs j JOIN documents d ON d.id=j.document_id ORDER BY j.created_at DESC LIMIT 100')
