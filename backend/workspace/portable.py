"""Version 1 portable JSON + originals archives, imported as a non-destructive merge.

Limits: 128 MiB data JSON; 4 GiB total expanded data; 20,000 ZIP entries;
8 MiB manifest; 16 MiB central directory. All staging stays in Database.root.
Only the explicitly listed core columns transfer. Credentials, settings (even
public provider configuration), jobs, logs and embeddings are excluded. FTS is
rebuilt. Same-hash documents keep destination metadata and active versions;
imported histories and course memberships are appended with fresh identities.
Newly imported queued/processing documents become failed and are reported for
manual reindexing; active versions and historical sources remain unchanged.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import struct
import tempfile
from typing import Annotated
import zipfile

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .backup import (BLOCK, HASH, MAX_ARCHIVE_BYTES, MAX_ENTRIES,
                     MAX_EXPANDED_BYTES, MAX_MANIFEST_BYTES, _hash, _no_duplicates, _preflight_zip)
from .db import Database, new_id, now
from .learning import AnswerInput, QuestionInput, _grade
from .notes import SourceInput
from .search import index_text

router = APIRouter(prefix='/api/v1/portable')
MAX_DATA_BYTES = 128 * 1024**2
FORMAT = 'academic-workspace-portable'
TABLES = {name: tuple(columns.split()) for name, columns in {
    'courses':'id name code semester color created_at',
    'blobs':'hash size kind created_at',
    'documents':'id blob_hash title filename kind status active_version favorite topic tags created_at relative_path',
    'document_versions':'id document_id created_at parser_version',
    'source_units':'id version_id locator_type locator heading text',
    'chunks':'id unit_id version_id document_id text ordinal',
    'document_courses':'document_id course_id',
    'document_links':'source_id target_id',
    'notes':'id title body course_id topic tags created_at updated_at',
    'note_sources':'note_id ordinal document_id version_id locator_type locator quote',
    'note_links':'source_id raw_title target_id deleted_target_id',
    'conversations':'id title course_id document_ids created_at updated_at',
    'messages':'id conversation_id role content status sources created_at',
    'flashcards':'id front back course_id topic sources due_at ease repetitions interval_days created_at updated_at',
    'reviews':'id flashcard_id course_id topic rating reviewed_at due_at ease repetitions interval_days algorithm idempotency_key',
    'quizzes':'id title course_id created_at',
    'quiz_questions':'id quiz_id ordinal content',
    'attempts':'id quiz_id quiz_title course_id score total created_at idempotency_key request_json',
    'attempt_answers':'attempt_id question_id ordinal topic selected text self_correct correct question',
    'activities':'id kind description created_at',
}.items()}
# SQL identifiers are exclusively these application constants, never JSON keys.
INSERTS = {t: f'INSERT INTO {t} ({",".join(cols)}) VALUES ({",".join("?" for _ in cols)})' for t, cols in TABLES.items()}
REFERENCES = {
    'document_versions':{'document_id':'documents'},
    'documents':{'active_version':'document_versions'},
    'source_units':{'version_id':'document_versions'},
    'chunks':{'unit_id':'source_units','version_id':'document_versions','document_id':'documents'},
    'document_courses':{'document_id':'documents','course_id':'courses'},
    'document_links':{'source_id':'documents','target_id':'documents'},
    'notes':{'course_id':'courses'},
    'note_sources':{'note_id':'notes','document_id':'documents','version_id':'document_versions'},
    'note_links':{'source_id':'notes','target_id':'notes','deleted_target_id':'notes'},
    'conversations':{'course_id':'courses'},
    'messages':{'conversation_id':'conversations'},
    'flashcards':{'course_id':'courses'},
    'reviews':{'flashcard_id':'flashcards','course_id':'courses'},
    'quizzes':{'course_id':'courses'},
    'quiz_questions':{'quiz_id':'quizzes'},
    'attempts':{'quiz_id':'quizzes','course_id':'courses'},
    'attempt_answers':{'attempt_id':'attempts','question_id':'quiz_questions'},
}
JSON_FIELDS = {'documents':{'tags':list},'notes':{'tags':list},
               'conversations':{'document_ids':list},'messages':{'sources':list},
               'flashcards':{'sources':list},'quiz_questions':{'content':dict},
               'attempts':{'request_json':list},'attempt_answers':{'selected':list,'question':dict}}


def _stage(db):
    parent = db.root/'portable-tmp'
    if parent.is_symlink():
        raise HTTPException(409, 'Portable staging directory must be local')
    parent.mkdir(exist_ok=True)
    return Path(tempfile.mkdtemp(prefix='transfer-',dir=parent))


def _json(raw):
    def invalid(value): raise ValueError('Non-finite JSON number')
    return json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=invalid)


def _identifier(value):
    if not isinstance(value,str) or not value or len(value)>256 or '\x00' in value:
        raise ValueError('Invalid identity')
    return value


def _originals(db, rows, stage=None):
    root=db.root/'originals'
    if root.is_symlink(): raise ValueError('Originals directory must be local')
    for row in rows:
        h=row['hash']
        if not isinstance(h,str) or not HASH.fullmatch(h) or type(row['size']) is not int or row['size']<0:
            raise ValueError('Invalid original metadata')
        local=root/h
        staged=stage/'originals'/h if stage else None
        expected={'sha256':h,'size':row['size']}
        if local.is_symlink(): raise ValueError('Original cannot be a symlink')
        if local.exists() and (not local.is_file() or _hash(local)!=expected):
            raise ValueError('Existing original checksum mismatch')
        if staged and staged.is_file():
            if _hash(staged)!=expected: raise ValueError('Original checksum mismatch')
        elif not local.is_file():
            raise ValueError('Missing original; omitted originals must already exist locally')


@router.get('/export')
def export_portable(request: Request, include_originals: bool = True):
    db=request.app.state.db
    stage=_stage(db)
    try:
        with db.maintenance, db.connect() as con:
            con.execute('BEGIN')
            tables={t:[dict(r) for r in con.execute(f'SELECT {",".join(cols)} FROM {t}')] for t,cols in TABLES.items()}
            data={'format':FORMAT,'format_version':1,'schema_version':con.execute('PRAGMA user_version').fetchone()[0],'tables':tables}
            raw=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
            if len(raw)>MAX_DATA_BYTES: raise HTTPException(413,'Portable JSON exceeds 128 MiB')
            (stage/'data.json').write_bytes(raw)
            _originals(db,tables['blobs'])
            files={'data.json':_hash(stage/'data.json')}
            if include_originals:
                files.update({'originals/'+r['hash']:{'sha256':r['hash'],'size':r['size']} for r in tables['blobs']})
            manifest={'format':FORMAT,'format_version':1,'schema_version':data['schema_version'],'created_at':now(),
                      'include_originals':include_originals,'files':files,'settings_policy':'excluded; destination settings retained'}
            manifest_bytes=json.dumps(manifest,ensure_ascii=False).encode()
            if len(files)+1>MAX_ENTRIES or len(manifest_bytes)>MAX_MANIFEST_BYTES or sum(x['size'] for x in files.values())+len(manifest_bytes)>MAX_EXPANDED_BYTES:
                raise HTTPException(413,'Portable archive exceeds size or entry limits')
            archive=stage/'portable.zip'
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                z.writestr('manifest.json',manifest_bytes)
                z.write(stage/'data.json','data.json')
                if include_originals:
                    for row in tables['blobs']: z.write(db.root/'originals'/row['hash'],'originals/'+row['hash'])
        return FileResponse(archive,media_type='application/zip',filename='academic-workspace-portable.zip',background=BackgroundTask(shutil.rmtree,stage,True))
    except ValueError as exc:
        shutil.rmtree(stage,ignore_errors=True)
        raise HTTPException(409,str(exc)) from exc
    except Exception:
        shutil.rmtree(stage,ignore_errors=True)
        raise


def _extract(archive,stage):
    _preflight_zip(archive)
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist(); names=[i.filename for i in infos]
        if len(names)!=len(set(names)) or len(names)>MAX_ENTRIES: raise ValueError('Duplicate paths or too many entries')
        if sum(i.file_size for i in infos)>MAX_EXPANDED_BYTES: raise ValueError('Expanded archive exceeds 4 GiB')
        for i in infos:
            if i.filename not in ('manifest.json','data.json') and not re.fullmatch(r'originals/[0-9a-f]{64}',i.filename): raise ValueError('Unexpected archive path')
            if i.is_dir() or stat.S_IFMT(i.external_attr>>16) not in (0,stat.S_IFREG) or i.flag_bits&1: raise ValueError('Archive links or special entries are forbidden')
            if i.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED): raise ValueError('Unsupported compression')
        if not {'manifest.json','data.json'}<=set(names): raise ValueError('Missing manifest or data')
        if z.getinfo('manifest.json').file_size>MAX_MANIFEST_BYTES or z.getinfo('data.json').file_size>MAX_DATA_BYTES: raise ValueError('JSON exceeds size limit')
        manifest=_json(z.read('manifest.json'))
        if not isinstance(manifest,dict) or manifest.get('format')!=FORMAT or type(manifest.get('format_version')) is not int or manifest['format_version']!=1 or type(manifest.get('include_originals')) is not bool:
            raise ValueError('Unsupported portable manifest')
        files=manifest.get('files')
        if not isinstance(files,dict) or set(files)!=set(names)-{'manifest.json'}: raise ValueError('Manifest file list mismatch')
        (stage/'originals').mkdir()
        total=0
        for name,expected in files.items():
            if not isinstance(expected,dict) or set(expected)!={'sha256','size'} or not isinstance(expected['sha256'],str) or not HASH.fullmatch(expected['sha256']) or type(expected['size']) is not int or expected['size']<0 or expected['size']!=z.getinfo(name).file_size:
                raise ValueError('Invalid file metadata')
            digest=hashlib.sha256(); size=0
            with z.open(name) as source,(stage/name).open('xb') as target:
                while block:=source.read(BLOCK):
                    size+=len(block); total+=len(block)
                    if size>expected['size'] or total>MAX_EXPANDED_BYTES: raise ValueError('Expanded data exceeds budget')
                    target.write(block); digest.update(block)
            if size!=expected['size'] or digest.hexdigest()!=expected['sha256']: raise ValueError('Checksum mismatch')
        return manifest,_json((stage/'data.json').read_bytes())


def _source(con,source):
    if not isinstance(source,dict): raise ValueError('Source must be an object')
    ref=SourceInput.model_validate({k:source[k] for k in SourceInput.model_fields if k in source})
    units=con.execute('''SELECT u.text FROM source_units u JOIN document_versions v ON v.id=u.version_id
        WHERE v.document_id=? AND v.id=? AND u.locator_type=? AND u.locator=?''',
        (ref.document_id,ref.version_id,ref.locator_type,ref.locator)).fetchall()
    if not any(ref.quote in u['text'] for u in units): raise ValueError('Source quote does not exist at its immutable location')
    if 'unit_id' in source:
        unit=con.execute('SELECT * FROM source_units WHERE id=?',(_identifier(source['unit_id']),)).fetchone()
        if not unit or any(unit[k]!=source[k] for k in ('version_id','locator_type','locator')) or ref.quote not in unit['text']:
            raise ValueError('Source unit does not match provenance')
    if 'chunk_id' in source:
        row=con.execute('''SELECT c.*,u.locator_type,u.locator FROM chunks c JOIN source_units u ON u.id=c.unit_id WHERE c.id=?''',(_identifier(source['chunk_id']),)).fetchone()
        if not row or any(row[k]!=source[k] for k in ('document_id','version_id','locator_type','locator')) or ref.quote not in row['text']:
            raise ValueError('Source chunk does not match provenance')
        if 'unit_id' in source and row['unit_id']!=source['unit_id']: raise ValueError('Source chunk unit mismatch')
        if 'text' in source and source['text']!=row['text']: raise ValueError('Source text differs from immutable chunk')


def _question(con,value,identifier=None):
    if identifier is not None and value.get('id')!=identifier: raise ValueError('Question snapshot identity mismatch')
    question=QuestionInput.model_validate({k:v for k,v in value.items() if k!='id'})
    for source in value.get('sources',[]): _source(con,source)
    return question.model_dump()


def _validate(db,stage,manifest,data):
    if not isinstance(data,dict) or set(data)!={'format','format_version','schema_version','tables'} or data['format']!=FORMAT or type(data['format_version']) is not int or data['format_version']!=1:
        raise ValueError('Unsupported portable data')
    if type(data['schema_version']) is not int or data['schema_version']!=max(db.migrations) or manifest.get('schema_version')!=data['schema_version']:
        raise ValueError('Portable schema version is not supported')
    tables=data['tables']
    if not isinstance(tables,dict) or set(tables)!=set(TABLES): raise ValueError('Unexpected or missing core tables')
    staged=Database(stage/'validation',migrations=db.migrations); staged.initialize()
    with staged.connect() as con:
        con.execute('BEGIN IMMEDIATE'); con.execute('PRAGMA defer_foreign_keys=ON')
        for table,columns in TABLES.items():
            if not isinstance(tables[table],list): raise ValueError('Table rows must be arrays')
            schema={r['name']:r for r in con.execute(f'PRAGMA table_info({table})')}
            for row in tables[table]:
                if not isinstance(row,dict) or set(row)!=set(columns): raise ValueError('Unexpected or missing columns')
                for col in columns:
                    value=row[col]; kind=schema[col]['type']
                    if value is None:
                        if schema[col]['notnull'] or schema[col]['pk']: raise ValueError('Null required value')
                    elif kind=='TEXT' and not isinstance(value,str): raise ValueError('Text value required')
                    elif kind=='INTEGER' and type(value) is not int: raise ValueError('Integer value required')
                    elif kind=='REAL' and (type(value) not in (int,float) or not math.isfinite(value)): raise ValueError('Finite number required')
                    if value is not None and (col=='id' or col in REFERENCES.get(table,{})): _identifier(value)
                for col,shape in JSON_FIELDS.get(table,{}).items():
                    parsed=_json(row[col])
                    if not isinstance(parsed,shape): raise ValueError('Invalid JSON field shape')
                    if col in ('tags','document_ids') and any(not isinstance(x,str) for x in parsed): raise ValueError('Expected strings')
                con.execute(INSERTS[table],tuple(row[c] for c in columns))
        if con.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('Foreign key check failed')
        if con.execute('''SELECT 1 FROM documents d LEFT JOIN document_versions v ON d.active_version=v.id
                          WHERE d.active_version IS NOT NULL AND (v.id IS NULL OR v.document_id<>d.id)''').fetchone(): raise ValueError('Invalid active version provenance')
        if con.execute('''SELECT 1 FROM chunks c JOIN source_units u ON u.id=c.unit_id JOIN document_versions v ON v.id=c.version_id
                          WHERE u.version_id<>c.version_id OR v.document_id<>c.document_id OR instr(u.text,c.text)=0''').fetchone(): raise ValueError('Invalid chunk provenance')
        for row in tables['note_sources']: _source(con,row)
        for row in tables['note_links']:
            if row['target_id'] is not None and row['deleted_target_id'] is not None:
                raise ValueError('Wiki link cannot be bound and tombstoned simultaneously')
        for table in ('messages','flashcards'):
            for row in tables[table]:
                for source in _json(row['sources']): _source(con,source)
        for row in tables['quiz_questions']: _question(con,_json(row['content']))
        for row in tables['attempt_answers']:
            question=_question(con,_json(row['question']),row['question_id'])
            selected=_json(row['selected'])
            if row['self_correct'] not in (None,0,1): raise ValueError('Invalid self-correction value')
            answer=AnswerInput.model_validate(dict(question_id=row['question_id'],selected=selected,
                text=row['text'],self_correct=None if row['self_correct'] is None else bool(row['self_correct'])))
            try:
                graded=_grade(question,answer)
            except HTTPException as exc:
                raise ValueError('Invalid historical answer: '+str(exc.detail)) from exc
            if bool(row['correct'])!=graded or row['topic']!=question['topic']:
                raise ValueError('Historical grading or topic differs from its immutable snapshot')
        for row in tables['attempts']:
            request=[AnswerInput.model_validate(v) for v in _json(row['request_json'])]
            answers=con.execute('SELECT * FROM attempt_answers WHERE attempt_id=?',(row['id'],)).fetchall()
            if len(request)!=len(answers) or {a.question_id for a in request}!={a['question_id'] for a in answers} or row['total']!=len(answers) or row['score']!=sum(a['correct'] for a in answers): raise ValueError('Attempt history inconsistent')
            by_id={a.question_id:a for a in request}
            for answer in answers:
                submitted=by_id[answer['question_id']]
                if submitted.selected!=_json(answer['selected']) or submitted.text!=answer['text'] or submitted.self_correct!=answer['self_correct']:
                    raise ValueError('Attempt request differs from saved answer')
        for row in tables['conversations']:
            for identifier in _json(row['document_ids']):
                if not con.execute('SELECT 1 FROM documents WHERE id=?',(_identifier(identifier),)).fetchone(): raise ValueError('Conversation document missing')
    blob_files={'originals/'+r['hash'] for r in tables['blobs']}
    actual=set(manifest['files'])-{'data.json'}
    if (manifest['include_originals'] and actual!=blob_files) or (not manifest['include_originals'] and actual): raise ValueError('Originals list does not match data')
    _originals(db,tables['blobs'],stage)
    return tables


def _preview(con,tables):
    conflicts={'courses':[],'titles':[],'original_hashes':[]}
    for row in tables['courses']:
        found=[r[0] for r in con.execute('SELECT id FROM courses WHERE name=?',(row['name'],))]
        if found: conflicts['courses'].append({'incoming_id':row['id'],'name':row['name'],'existing_ids':found})
    for table in ('documents','notes','quizzes'):
        for row in tables[table]:
            found=[r[0] for r in con.execute(f'SELECT id FROM {table} WHERE title=?',(row['title'],))]
            if found: conflicts['titles'].append({'table':table,'incoming_id':row['id'],'title':row['title'],'existing_ids':found})
    for row in tables['blobs']:
        if con.execute('SELECT 1 FROM blobs WHERE hash=?',(row['hash'],)).fetchone(): conflicts['original_hashes'].append(row['hash'])
    return {'status':'preview','counts':{t:len(rows) for t,rows in tables.items()},'conflicts':conflicts,
            'policy':'Names and titles create separate rows. Same-original documents retain existing metadata and active versions. Settings are excluded.'}


def _merge(db,stage,tables):
    created=[]
    with db.maintenance:
        try:
            with db.connect() as con:
                con.execute('BEGIN IMMEDIATE'); con.execute('PRAGMA defer_foreign_keys=ON')
                _originals(db,tables['blobs'],stage)
                result=_preview(con,tables)
                maps={t:{} for t,c in TABLES.items() if 'id' in c}
                def mapped(table,value):
                    if value is None: return None
                    _identifier(value)
                    return maps[table].setdefault(value,new_id())
                for t,rows in tables.items():
                    if t in maps:
                        for row in rows: mapped(t,row['id'])
                existing_docs=set()
                for row in tables['documents']:
                    prior=con.execute('SELECT id FROM documents WHERE blob_hash=?',(row['blob_hash'],)).fetchone()
                    if prior:
                        maps['documents'][row['id']]=prior['id']; existing_docs.add(row['id'])
                def source(s):
                    r=dict(s)
                    for field,t in [('document_id','documents'),('version_id','document_versions'),('chunk_id','chunks'),('unit_id','source_units')]:
                        if field in r: r[field]=mapped(t,r[field])
                    return r
                def question(q):
                    r=dict(q)
                    if 'id' in r: r['id']=mapped('quiz_questions',r['id'])
                    r['sources']=[source(s) for s in r.get('sources',[])]
                    return r
                counts={t:0 for t in TABLES}
                retry_required=[]
                for t,rows in tables.items():
                    for original in rows:
                        row=dict(original)
                        if t=='documents' and row['id'] in existing_docs: continue
                        if t=='blobs' and con.execute('SELECT 1 FROM blobs WHERE hash=?',(row['hash'],)).fetchone(): continue
                        if t in maps: row['id']=mapped(t,row['id'])
                        if t=='documents' and row['status'] in ('queued','processing'):
                            row['status']='failed'
                            retry_required.append(row['id'])
                        for col,target in REFERENCES.get(t,{}).items(): row[col]=mapped(target,row[col])
                        if t=='document_links' and con.execute('SELECT 1 FROM document_links WHERE source_id=? AND target_id=?',(row['source_id'],row['target_id'])).fetchone():
                            continue
                        for col in JSON_FIELDS.get(t,{}):
                            value=_json(row[col])
                            if col=='sources': value=[source(s) for s in value]
                            elif col=='document_ids': value=[mapped('documents',v) for v in value]
                            elif (t,col) in [('quiz_questions','content'),('attempt_answers','question')]: value=question(value)
                            elif col=='request_json': value=[dict(a,question_id=mapped('quiz_questions',a['question_id'])) for a in value]
                            row[col]=json.dumps(value,ensure_ascii=False,sort_keys=True)
                        con.execute(INSERTS[t],tuple(row[c] for c in TABLES[t])); counts[t]+=1
                if con.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('Merged foreign key check failed')
                con.execute('DELETE FROM chunks_fts')
                con.executemany('INSERT INTO chunks_fts(chunk_id,text) VALUES (?,?)',
                                ((row['id'],index_text(row['text'])) for row in con.execute('SELECT id,text FROM chunks')))
                con.execute('DELETE FROM notes_fts'); con.execute('INSERT INTO notes_fts(note_id,title,body) SELECT id,title,body FROM notes')
                originals=db.root/'originals'; originals.mkdir(exist_ok=True)
                for row in tables['blobs']:
                    path=originals/row['hash']
                    if not path.exists():
                        # Atomic no-clobber install on the same filesystem. Track only
                        # links this import actually created, so rollback cannot remove
                        # a preexisting original or an unrelated concurrent upload.
                        try: os.link(stage/'originals'/row['hash'],path)
                        except FileExistsError:
                            if path.is_symlink() or _hash(path)!={'sha256':row['hash'],'size':row['size']}: raise ValueError('Original changed during import')
                        else: created.append(path)
                result.update(status='imported',imported_counts=counts,mappings=maps,
                              retry_required_document_ids=retry_required)
            return result
        except Exception:
            for path in created: path.unlink(missing_ok=True)
            raise


@router.post('/import')
def import_portable(request: Request, archive: Annotated[UploadFile,File()], confirm: Annotated[str,Form()]=''):
    if confirm not in ('','IMPORT'): raise HTTPException(422,'Type IMPORT to confirm merging this archive')
    db=request.app.state.db; stage=_stage(db)
    try:
        uploaded=stage/'upload.zip'; size=0
        with uploaded.open('xb') as target:
            while block:=archive.file.read(BLOCK):
                size+=len(block)
                if size>MAX_ARCHIVE_BYTES: raise HTTPException(413,'Archive exceeds upload limit')
                target.write(block)
        manifest,data=_extract(uploaded,stage)
        with db.maintenance:
            tables=_validate(db,stage,manifest,data)
            if confirm=='IMPORT': return _merge(db,stage,tables)
            with db.connect() as con: return _preview(con,tables)
    except (ValueError,TypeError,KeyError,sqlite3.Error,zipfile.BadZipFile,EOFError,RuntimeError,struct.error,UnicodeError,RecursionError) as exc:
        raise HTTPException(422,'Invalid portable archive: '+str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500,'Portable import failed; existing library was retained') from exc
    finally:
        archive.file.close(); shutil.rmtree(stage,ignore_errors=True)
