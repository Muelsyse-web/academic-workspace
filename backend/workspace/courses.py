"""Course organization and library overview."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .db import new_id, now

router = APIRouter(prefix='/api/v1')


class CourseInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1,max_length=200)
    code: str = Field(default='',max_length=80)
    semester: str = Field(default='',max_length=100)
    color: str = '#3e6656'

    @field_validator('color')
    @classmethod
    def valid_color(cls,value):
        import re
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',value):
            raise ValueError('Expected a six-digit hex color')
        return value


class CoursePatch(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    name: str | None = Field(default=None,min_length=1,max_length=200)
    code: str | None = Field(default=None,max_length=80)
    semester: str | None = Field(default=None,max_length=100)
    color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')


@router.get('/courses')
def courses(request: Request):
    return request.app.state.db.all('''SELECT c.*,
        (SELECT count(*) FROM document_courses dc WHERE dc.course_id=c.id) document_count
        FROM courses c ORDER BY c.semester DESC,c.name''')


@router.post('/courses',status_code=201)
def create_course(body: CourseInput,request: Request):
    row = {'id':new_id(), **body.model_dump(),'created_at':now()}
    db = request.app.state.db
    with db.connect() as con:
        con.execute('INSERT INTO courses VALUES (:id,:name,:code,:semester,:color,:created_at)', row)
        db.activity(con,'course','创建课程：'+body.name)
    return row


@router.patch('/courses/{identifier}')
def patch_course(identifier: str,body: CoursePatch,request: Request):
    db = request.app.state.db
    row = db.one('SELECT * FROM courses WHERE id=?',(identifier,))
    if not row:
        raise HTTPException(404,'Course not found')
    merged = {**row,**body.model_dump(exclude_none=True)}
    valid = CourseInput(**{k:merged[k] for k in ('name','code','semester','color')})
    with db.connect() as con:
        con.execute('UPDATE courses SET name=?,code=?,semester=?,color=? WHERE id=?',(*valid.model_dump().values(),identifier))
    return db.one('SELECT * FROM courses WHERE id=?',(identifier,))


@router.delete('/courses/{identifier}',status_code=204)
def delete_course(identifier: str,request: Request):
    with request.app.state.db.connect() as con:
        con.execute('DELETE FROM courses WHERE id=?',(identifier,))


@router.get('/dashboard')
def dashboard(request: Request):
    db = request.app.state.db
    result = {table:db.one('SELECT count(*) n FROM '+table)['n'] for table in ('courses','documents')}
    tables = {row['name'] for row in db.all("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in ('notes','flashcards'):
        result[table] = db.one('SELECT count(*) n FROM '+table)['n'] if table in tables else 0
    result['activities'] = db.all('SELECT * FROM activities ORDER BY created_at DESC LIMIT 15')
    result['recent_documents'] = db.all('SELECT id,title,kind,status,created_at FROM documents ORDER BY created_at DESC LIMIT 6')
    result['due_cards'] = db.one('SELECT count(*) n FROM flashcards WHERE due_at<=?',(now(),))['n'] if 'flashcards' in tables else 0
    return result
