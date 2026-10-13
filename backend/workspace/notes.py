"""Source-verified Markdown notes, durable wiki links, and portable exports."""
from io import BytesIO
import hashlib
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .db import new_id, now

router = APIRouter(prefix='/api/v1')


class SourceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    locator_type: str = Field(min_length=1)
    locator: int = Field(gt=0, strict=True)
    quote: str = Field(min_length=1)

    @field_validator('quote')
    @classmethod
    def nonblank_quote(cls, value):
        if not value.strip():
            raise ValueError('A source quote must contain text')
        return value


class NoteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default='', max_length=1_000_000)
    course_id: str | None = None
    topic: str = Field(default='', max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=100)
    sources: list[SourceInput] = Field(default_factory=list, max_length=500)

    @field_validator('title')
    @classmethod
    def nonblank_title(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('A note title must contain text')
        return value


class NotePatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str | None = None
    body: str | None = None
    course_id: str | None = None
    topic: str | None = None
    tags: list[str] | None = None
    sources: list[SourceInput] | None = None


class LinkChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    raw_title: str = Field(min_length=1)
    target_id: str = Field(min_length=1)


def _export_basename(identifier):
    # Restored TEXT primary keys are untrusted paths and header values.
    return identifier if re.fullmatch(r'[0-9a-f]{32}', identifier) else hashlib.sha256(identifier.encode('utf-8')).hexdigest()


def _row(row):
    result = dict(row)
    result['tags'] = json.loads(result['tags'])
    return result


def _require_note(con, identifier):
    row = con.execute('SELECT * FROM notes WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Note not found')
    return _row(row)


def _sources(con, identifier):
    return [dict(row) for row in con.execute('''
        SELECT s.document_id,s.version_id,s.locator_type,s.locator,s.quote,d.title document_title
        FROM note_sources s JOIN documents d ON d.id=s.document_id
        WHERE s.note_id=? ORDER BY s.ordinal''', (identifier,))]


def _detail(con, identifier):
    row = _require_note(con, identifier)
    row['sources'] = _sources(con, identifier)
    row['outgoing_links'] = [dict(link) for link in con.execute('''
        SELECT n.id,n.title,l.raw_title FROM note_links l JOIN notes n ON n.id=l.target_id
        WHERE l.source_id=? ORDER BY l.raw_title''', (identifier,))]
    row['backlinks'] = [dict(link) for link in con.execute('''
        SELECT n.id,n.title,l.raw_title FROM note_links l JOIN notes n ON n.id=l.source_id
        WHERE l.target_id=? ORDER BY n.title,n.id,l.raw_title''', (identifier,))]
    row['unresolved_links'] = [
        {'raw_title': link['raw_title'],
         'reason': 'deleted' if link['deleted_target_id'] else ('ambiguous' if link['matches'] > 1 else 'missing')}
        for link in con.execute('''
            SELECT raw_title,deleted_target_id,(SELECT count(*) FROM notes WHERE title=l.raw_title) matches
            FROM note_links l WHERE source_id=? AND target_id IS NULL ORDER BY raw_title''', (identifier,))
    ]
    return row


def _validate_references(con, data):
    if data.course_id is not None and not con.execute('SELECT 1 FROM courses WHERE id=?', (data.course_id,)).fetchone():
        raise HTTPException(422, 'Course not found')
    for source in data.sources:
        units = con.execute('''
            SELECT u.text FROM source_units u JOIN document_versions v ON v.id=u.version_id
            WHERE v.document_id=? AND v.id=? AND u.locator_type=? AND u.locator=?''',
            (source.document_id, source.version_id, source.locator_type, source.locator))
        if not any(source.quote in row['text'] for row in units):
            raise HTTPException(422, 'Quote must match text at the specified document version and location')


def _save_sources(con, identifier, sources):
    con.execute('DELETE FROM note_sources WHERE note_id=?', (identifier,))
    con.executemany('''INSERT INTO note_sources
        (note_id,ordinal,document_id,version_id,locator_type,locator,quote) VALUES (?,?,?,?,?,?,?)''',
        [(identifier, index, s.document_id, s.version_id, s.locator_type, s.locator, s.quote)
         for index, s in enumerate(sources)])


def _sync_links(con, identifier, body):
    # Keep existing raw-title -> ID bindings, even when the target has been renamed.
    titles = {match.strip() for match in re.findall(r'\[\[([^\[\]\n]+)\]\]', body) if match.strip()}
    existing = {row['raw_title'] for row in con.execute('SELECT raw_title FROM note_links WHERE source_id=?', (identifier,))}
    con.executemany('DELETE FROM note_links WHERE source_id=? AND raw_title=?',
                    [(identifier, title) for title in existing - titles])
    con.executemany('INSERT INTO note_links(source_id,raw_title) VALUES (?,?)',
                    [(identifier, title) for title in titles - existing])


def _resolve_links(con):
    # A deleted target is a broken saved binding, never a new title lookup.
    con.execute('''UPDATE note_links SET target_id=(SELECT id FROM notes WHERE title=note_links.raw_title)
        WHERE target_id IS NULL AND deleted_target_id IS NULL
        AND (SELECT count(*) FROM notes WHERE title=note_links.raw_title)=1''')


def _markdown(note):
    parts = ['# '+note['title'], '', note['body']]
    if note['sources']:
        parts.extend(['', '## Sources', ''])
        for index, source in enumerate(note['sources'], 1):
            parts.append(f"{index}. {source['document_title']} — {source['locator_type']} {source['locator']} "
                         f"(document `{source['document_id']}`, version `{source['version_id']}`)")
            parts.extend('   > '+line for line in source['quote'].splitlines())
            parts.append('')
    return '\n'.join(parts).rstrip()+'\n'


@router.get('/notes')
def list_notes(request: Request, q: str = '', course_id: str | None = None, topic: str | None = None):
    where, args = [], []
    if q:
        # instr avoids wildcard/query operators; Chinese and ASCII terms stay literal.
        where.append('(instr(lower(title),lower(?))>0 OR instr(lower(body),lower(?))>0)')
        args.extend([q, q])
    if course_id is not None:
        where.append('course_id=?')
        args.append(course_id)
    if topic is not None:
        where.append('topic=?')
        args.append(topic)
    sql = 'SELECT * FROM notes'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY updated_at DESC,id'
    return [_row(row) for row in request.app.state.db.all(sql, args)]


@router.post('/notes', status_code=201)
def create_note(data: NoteInput, request: Request):
    db = request.app.state.db
    identifier, timestamp = new_id(), now()
    with db.connect() as con:
        _validate_references(con, data)
        con.execute('''INSERT INTO notes(id,title,body,course_id,topic,tags,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?)''', (identifier,data.title,data.body,data.course_id,data.topic,
                                         json.dumps(data.tags,ensure_ascii=False),timestamp,timestamp))
        _save_sources(con, identifier, data.sources)
        _sync_links(con, identifier, data.body)
        _resolve_links(con)
        db.activity(con, 'note', '创建笔记：'+data.title)
        return _detail(con, identifier)


# Bulk export must precede the dynamic ID route.
@router.get('/notes/export')
def export_notes(request: Request):
    with request.app.state.db.connect() as con:
        notes = [_detail(con, row['id']) for row in con.execute('SELECT id FROM notes ORDER BY created_at,id')]
    archive = BytesIO()
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as output:
        for note in notes:
            output.writestr(_export_basename(note['id'])+'.md', _markdown(note))
        output.writestr('manifest.json', json.dumps({'version':1,'notes':notes}, ensure_ascii=False, indent=2))
    return Response(archive.getvalue(), media_type='application/zip',
                    headers={'Content-Disposition':'attachment; filename="notes.zip"'})


@router.get('/notes/{identifier}')
def get_note(identifier: str, request: Request):
    with request.app.state.db.connect() as con:
        return _detail(con, identifier)


@router.patch('/notes/{identifier}')
def patch_note(identifier: str, patch: NotePatch, request: Request):
    with request.app.state.db.connect() as con:
        existing = _require_note(con, identifier)
        fields = {key: existing[key] for key in ('title','body','course_id','topic','tags')}
        fields['sources'] = [{key: source[key] for key in SourceInput.model_fields} for source in _sources(con, identifier)]
        fields.update(patch.model_dump(exclude_unset=True))
        try:
            data = NoteInput.model_validate(fields)
        except ValidationError as exc:
            raise HTTPException(422, str(exc)) from exc
        _validate_references(con, data)
        con.execute('UPDATE notes SET title=?,body=?,course_id=?,topic=?,tags=?,updated_at=? WHERE id=?',
                    (data.title,data.body,data.course_id,data.topic,json.dumps(data.tags,ensure_ascii=False),now(),identifier))
        _save_sources(con, identifier, data.sources)
        _sync_links(con, identifier, data.body)
        _resolve_links(con)
        return _detail(con, identifier)


@router.delete('/notes/{identifier}', status_code=204)
def delete_note(identifier: str, request: Request):
    with request.app.state.db.connect() as con:
        _require_note(con, identifier)
        con.execute('DELETE FROM notes WHERE id=?', (identifier,))
        _resolve_links(con)
    return Response(status_code=204)


@router.put('/notes/{identifier}/links')
def choose_link(identifier: str, choice: LinkChoice, request: Request):
    with request.app.state.db.connect() as con:
        _require_note(con, identifier)
        _require_note(con, choice.target_id)
        if not con.execute('SELECT 1 FROM note_links WHERE source_id=? AND raw_title=?',
                           (identifier, choice.raw_title)).fetchone():
            raise HTTPException(404, 'Link not found in note')
        con.execute('UPDATE note_links SET target_id=?,deleted_target_id=NULL WHERE source_id=? AND raw_title=?',
                    (choice.target_id, identifier, choice.raw_title))
        con.execute('UPDATE notes SET updated_at=? WHERE id=?', (now(), identifier))
        return _detail(con, identifier)


@router.get('/notes/{identifier}/export')
def export_note(identifier: str, request: Request):
    with request.app.state.db.connect() as con:
        note = _detail(con, identifier)
    return Response(_markdown(note), media_type='text/markdown; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="{_export_basename(note["id"])}.md"'})
