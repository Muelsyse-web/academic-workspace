"""Manual flashcards, SM-2 v1, and source-verified quizzes with durable history."""
from datetime import datetime, timedelta
import json
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator, model_validator

from .db import new_id, now
from .notes import SourceInput

router = APIRouter(prefix='/api/v1')
Index = Annotated[int, Field(strict=True, ge=0)]
Rating = Literal['again', 'hard', 'good', 'easy']


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class FlashcardInput(InputModel):
    front: str = Field(min_length=1, max_length=100_000)
    back: str = Field(min_length=1, max_length=100_000)
    course_id: str | None = None
    topic: str = Field(default='', max_length=200)
    sources: list[SourceInput] = Field(default_factory=list, max_length=500)

    @field_validator('front', 'back')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Flashcard text must not be blank')
        return value


class FlashcardPatch(InputModel):
    front: str | None = None
    back: str | None = None
    course_id: str | None = None
    topic: str | None = None
    sources: list[SourceInput] | None = None


class ReviewInput(InputModel):
    rating: Rating
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class QuestionInput(InputModel):
    kind: Literal['single', 'multiple', 'short', 'math']
    prompt: str = Field(min_length=1, max_length=100_000)
    options: list[str] = Field(default_factory=list, max_length=100)
    correct_indices: list[Index] = Field(default_factory=list, max_length=100)
    answer: str = Field(default='', max_length=100_000)
    explanation: str = Field(default='', max_length=100_000)
    topic: str = Field(default='', max_length=200)
    sources: list[SourceInput] = Field(default_factory=list, max_length=500)

    @model_validator(mode='after')
    def validate_question(self):
        if not self.prompt.strip():
            raise ValueError('Question prompt must not be blank')
        if self.kind in ('single', 'multiple'):
            if len(self.options) < 2 or any(not value.strip() for value in self.options):
                raise ValueError('Choice questions require at least two nonblank options')
            if not self.correct_indices or len(set(self.correct_indices)) != len(self.correct_indices):
                raise ValueError('Correct indices must be nonempty and unique')
            if any(index >= len(self.options) for index in self.correct_indices):
                raise ValueError('Correct index is outside the options')
            if self.kind == 'single' and len(self.correct_indices) != 1:
                raise ValueError('Single-choice questions require exactly one correct index')
        elif self.options or self.correct_indices:
            raise ValueError('Short and math questions cannot have choice options or indices')
        elif not self.answer.strip():
            raise ValueError('Short and math questions require a reference answer for self-grading')
        return self


class QuizInput(InputModel):
    title: str = Field(min_length=1, max_length=500)
    course_id: str | None = None
    questions: list[QuestionInput] = Field(min_length=1, max_length=200)

    @field_validator('title')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Quiz title must not be blank')
        return value.strip()


class QuizPatch(InputModel):
    title: str | None = None
    course_id: str | None = None
    questions: list[QuestionInput] | None = None


class AnswerInput(InputModel):
    question_id: str = Field(min_length=1)
    selected: list[Index] = Field(default_factory=list, max_length=100)
    text: str = Field(default='', max_length=100_000)
    self_correct: StrictBool | None = None


class AttemptInput(InputModel):
    answers: list[AnswerInput] = Field(max_length=200)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _validate_course(con, course_id):
    if course_id is not None and not con.execute('SELECT 1 FROM courses WHERE id=?', (course_id,)).fetchone():
        raise HTTPException(422, 'Course not found')


def _validate_sources(con, sources):
    for source in sources:
        units = con.execute('''SELECT u.text FROM source_units u
            JOIN document_versions v ON v.id=u.version_id
            WHERE v.document_id=? AND v.id=? AND u.locator_type=? AND u.locator=?''',
            (source.document_id, source.version_id, source.locator_type, source.locator))
        if not any(source.quote in row['text'] for row in units):
            raise HTTPException(422, 'Quote must match text at the specified document version and location')


def _card(row):
    result = dict(row)
    result['sources'] = json.loads(result['sources'])
    return result


def _require_card(con, identifier):
    row = con.execute('SELECT * FROM flashcards WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Flashcard not found')
    return _card(row)


def _quiz(con, identifier):
    row = con.execute('SELECT * FROM quizzes WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Quiz not found')
    result = dict(row)
    result['questions'] = [dict(json.loads(q['content']), id=q['id']) for q in con.execute(
        'SELECT * FROM quiz_questions WHERE quiz_id=? ORDER BY ordinal', (identifier,))]
    return result


def _scope(course_id=None, topic=None, *, prefix=''):
    where, args = [], []
    for key, value in [('course_id', course_id), ('topic', topic)]:
        if value is not None:
            where.append(prefix+key+'=?')
            args.append(value)
    return where, args


def _where(clauses):
    return ' WHERE '+' AND '.join(clauses) if clauses else ''


def schedule_review(card, rating, timestamp):
    """SM-2 v1: next interval uses the previous ease, then ease is updated."""
    grade = {'again': 0, 'hard': 3, 'good': 4, 'easy': 5}[rating]
    repetitions = card['repetitions'] + 1 if grade >= 3 else 0
    if grade < 3 or repetitions == 1:
        interval = 1
    elif repetitions == 2:
        interval = 6
    else:
        interval = max(1, round(card['interval_days'] * card['ease']))
    ease = round(max(1.3, card['ease'] + 0.1 - (5-grade)*(0.08+(5-grade)*0.02)), 8)
    due = datetime.fromisoformat(timestamp) + timedelta(days=interval)
    return dict(due_at=due.isoformat(), ease=ease, repetitions=repetitions, interval_days=interval)


@router.get('/flashcards')
def list_flashcards(request: Request, course_id: str | None = None, topic: str | None = None, due: bool | None = None):
    where, args = _scope(course_id, topic)
    if due is not None:
        where.append('due_at'+('<=?' if due else '>?'))
        args.append(now())
    rows = request.app.state.db.all('SELECT * FROM flashcards'+_where(where)+' ORDER BY due_at,id', args)
    return [_card(row) for row in rows]


@router.post('/flashcards', status_code=201)
def create_flashcard(data: FlashcardInput, request: Request):
    identifier, timestamp = new_id(), now()
    with request.app.state.db.connect() as con:
        _validate_course(con, data.course_id)
        _validate_sources(con, data.sources)
        con.execute('''INSERT INTO flashcards
            (id,front,back,course_id,topic,sources,due_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)''',
            (identifier, data.front, data.back, data.course_id, data.topic,
             _json([s.model_dump() for s in data.sources]), timestamp, timestamp, timestamp))
        return _require_card(con, identifier)


@router.get('/flashcards/{identifier}')
def get_flashcard(identifier: str, request: Request):
    with request.app.state.db.connect() as con:
        return _require_card(con, identifier)


@router.patch('/flashcards/{identifier}')
def patch_flashcard(identifier: str, patch: FlashcardPatch, request: Request):
    with request.app.state.db.connect() as con:
        row = _require_card(con, identifier)
        fields = {key: row[key] for key in FlashcardInput.model_fields}
        fields.update(patch.model_dump(exclude_unset=True))
        try:
            data = FlashcardInput.model_validate(fields)
        except ValidationError as exc:
            raise HTTPException(422, str(exc)) from exc
        _validate_course(con, data.course_id)
        _validate_sources(con, data.sources)
        con.execute('UPDATE flashcards SET front=?,back=?,course_id=?,topic=?,sources=?,updated_at=? WHERE id=?',
                    (data.front, data.back, data.course_id, data.topic,
                     _json([s.model_dump() for s in data.sources]), now(), identifier))
        return _require_card(con, identifier)


@router.delete('/flashcards/{identifier}', status_code=204)
def delete_flashcard(identifier: str, request: Request):
    with request.app.state.db.connect() as con:
        _require_card(con, identifier)
        con.execute('DELETE FROM flashcards WHERE id=?', (identifier,))
    return Response(status_code=204)


@router.post('/flashcards/{identifier}/review')
def review_flashcard(identifier: str, data: ReviewInput, request: Request):
    with request.app.state.db.connect() as con:
        # Serialize across processes before reading the current schedule or replay token.
        con.execute('BEGIN IMMEDIATE')
        card = _require_card(con, identifier)
        if data.idempotency_key:
            previous = con.execute('SELECT * FROM reviews WHERE flashcard_id=? AND idempotency_key=?',
                                   (identifier, data.idempotency_key)).fetchone()
            if previous:
                if previous['rating'] != data.rating:
                    raise HTTPException(409, 'Idempotency key was already used for a different rating')
                return dict(previous)
        timestamp = now()
        schedule = schedule_review(card, data.rating, timestamp)
        result = dict(id=new_id(), flashcard_id=identifier, course_id=card['course_id'], topic=card['topic'],
                      rating=data.rating, reviewed_at=timestamp, **schedule,
                      algorithm='sm2-v1', idempotency_key=data.idempotency_key)
        con.execute('''UPDATE flashcards SET due_at=?,ease=?,repetitions=?,interval_days=?,updated_at=? WHERE id=?''',
                    (schedule['due_at'], schedule['ease'], schedule['repetitions'], schedule['interval_days'], timestamp, identifier))
        con.execute('INSERT INTO reviews ('+','.join(result)+') VALUES ('+','.join('?' for _ in result)+')', tuple(result.values()))
        request.app.state.db.activity(con,'review','复习卡片：'+card['front'][:80])
        return result


@router.get('/reviews')
def list_reviews(request: Request, course_id: str | None = None, topic: str | None = None, flashcard_id: str | None = None):
    where, args = _scope(course_id, topic)
    if flashcard_id is not None:
        where.append('flashcard_id=?')
        args.append(flashcard_id)
    return request.app.state.db.all('SELECT * FROM reviews'+_where(where)+' ORDER BY reviewed_at DESC,id', args)


@router.post('/quizzes', status_code=201)
def create_quiz(data: QuizInput, request: Request):
    identifier = new_id()
    with request.app.state.db.connect() as con:
        _validate_course(con, data.course_id)
        for question in data.questions:
            _validate_sources(con, question.sources)
        con.execute('INSERT INTO quizzes VALUES (?,?,?,?)', (identifier, data.title, data.course_id, now()))
        con.executemany('INSERT INTO quiz_questions VALUES (?,?,?,?)',
                        [(new_id(), identifier, i, _json(q.model_dump())) for i, q in enumerate(data.questions)])
        return _quiz(con, identifier)


@router.get('/quizzes')
def list_quizzes(request: Request, course_id: str | None = None):
    where, args = _scope(course_id)
    with request.app.state.db.connect() as con:
        return [_quiz(con, row['id']) for row in con.execute('SELECT id FROM quizzes'+_where(where)+' ORDER BY created_at DESC,id', args)]


@router.get('/quizzes/{identifier}')
def get_quiz(identifier: str, request: Request):
    with request.app.state.db.connect() as con:
        return _quiz(con, identifier)


@router.patch('/quizzes/{identifier}')
def patch_quiz(identifier: str, patch: QuizPatch, request: Request):
    with request.app.state.db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        existing = _quiz(con, identifier)
        fields = {'title': existing['title'], 'course_id': existing['course_id'],
                  'questions': [{key: q[key] for key in QuestionInput.model_fields}
                                for q in existing['questions']]}
        fields.update(patch.model_dump(exclude_unset=True))
        try:
            data = QuizInput.model_validate(fields)
        except ValidationError as exc:
            raise HTTPException(422, str(exc)) from exc
        _validate_course(con, data.course_id)
        for question in data.questions:
            _validate_sources(con, question.sources)
        con.execute('UPDATE quizzes SET title=?,course_id=? WHERE id=?',
                    (data.title, data.course_id, identifier))
        if 'questions' in patch.model_fields_set:
            # Saved attempts own immutable snapshots, so question replacement is safe.
            con.execute('DELETE FROM quiz_questions WHERE quiz_id=?', (identifier,))
            con.executemany('INSERT INTO quiz_questions VALUES (?,?,?,?)',
                            [(new_id(), identifier, i, _json(q.model_dump()))
                             for i, q in enumerate(data.questions)])
        return _quiz(con, identifier)


@router.delete('/quizzes/{identifier}', status_code=204)
def delete_quiz(identifier: str, request: Request):
    with request.app.state.db.connect() as con:
        _quiz(con, identifier)
        con.execute('DELETE FROM quizzes WHERE id=?', (identifier,))
    return Response(status_code=204)


def _answer(row):
    result = dict(row)
    for key in ('question', 'selected'):
        result[key] = json.loads(result[key])
    result['correct'] = bool(result['correct'])
    if result['self_correct'] is not None:
        result['self_correct'] = bool(result['self_correct'])
    result.pop('ordinal', None)
    return result


def _attempt(con, identifier):
    result = dict(con.execute('SELECT * FROM attempts WHERE id=?', (identifier,)).fetchone())
    result.pop('request_json')
    result['answers'] = [_answer(row) for row in con.execute('SELECT * FROM attempt_answers WHERE attempt_id=? ORDER BY ordinal', (identifier,))]
    return result


def _grade(question, answer):
    if question['kind'] in ('single', 'multiple'):
        if answer.self_correct is not None:
            raise HTTPException(422, 'Choice questions are graded from their selected options')
        if len(set(answer.selected)) != len(answer.selected) or any(i >= len(question['options']) for i in answer.selected):
            raise HTTPException(422, 'Selected indices must be unique and within the options')
        if question['kind'] == 'single' and len(answer.selected) != 1:
            raise HTTPException(422, 'Single-choice answers require exactly one selected option')
        return set(answer.selected) == set(question['correct_indices'])
    if answer.selected or answer.self_correct is None:
        raise HTTPException(422, 'Short and math answers require explicit self_correct and no selected options')
    return answer.self_correct


@router.post('/quizzes/{identifier}/attempts', status_code=201)
def submit_attempt(identifier: str, data: AttemptInput, request: Request):
    with request.app.state.db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        quiz = _quiz(con, identifier)
        request_json = _json([a.model_dump() for a in data.answers])
        if data.idempotency_key:
            previous = con.execute('SELECT * FROM attempts WHERE quiz_id=? AND idempotency_key=?', (identifier, data.idempotency_key)).fetchone()
            if previous:
                if previous['request_json'] != request_json:
                    raise HTTPException(409, 'Idempotency key was already used for different answers')
                return _attempt(con, previous['id'])
        answers = {a.question_id: a for a in data.answers}
        if len(answers) != len(data.answers) or set(answers) != {q['id'] for q in quiz['questions']}:
            raise HTTPException(422, 'Submit exactly one answer for every question in this quiz')
        graded = [(q, answers[q['id']], _grade(q, answers[q['id']])) for q in quiz['questions']]
        attempt_id = new_id()
        con.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?)',
                    (attempt_id, identifier, quiz['title'], quiz['course_id'], sum(int(x[2]) for x in graded),
                     len(graded), now(), data.idempotency_key, request_json))
        con.executemany('INSERT INTO attempt_answers VALUES (?,?,?,?,?,?,?,?,?)',
                        [(attempt_id, q['id'], i, q['topic'], _json(a.selected), a.text, a.self_correct, correct, _json(q))
                         for i, (q, a, correct) in enumerate(graded)])
        request.app.state.db.activity(con,'quiz','完成练习：'+quiz['title'])
        return _attempt(con, attempt_id)


@router.get('/attempts')
def list_attempts(request: Request, course_id: str | None = None, quiz_id: str | None = None):
    where, args = _scope(course_id)
    if quiz_id is not None:
        where.append('quiz_id=?')
        args.append(quiz_id)
    with request.app.state.db.connect() as con:
        return [_attempt(con, row['id']) for row in con.execute('SELECT id FROM attempts'+_where(where)+' ORDER BY created_at DESC,id', args)]


@router.get('/learning/weak-topics')
def weak_topics(request: Request, course_id: str | None = None):
    where, args = _scope(course_id, prefix='a.')
    return request.app.state.db.all('''SELECT a.course_id, r.topic,
        sum(1-r.correct) incorrect_count, count(*) total_count
        FROM attempt_answers r JOIN attempts a ON a.id=r.attempt_id'''+_where(where)+'''
        GROUP BY a.course_id,r.topic HAVING sum(1-r.correct)>0
        ORDER BY incorrect_count DESC,a.course_id,r.topic''', args)


@router.get('/learning/wrong-questions')
def wrong_questions(request: Request, course_id: str | None = None, topic: str | None = None):
    where, args = _scope(course_id, prefix='a.')
    where.append('r.correct=0')
    if topic is not None:
        where.append('r.topic=?')
        args.append(topic)
    rows = request.app.state.db.all('''SELECT r.*,a.quiz_id,a.quiz_title,a.course_id,a.created_at
        FROM attempt_answers r JOIN attempts a ON a.id=r.attempt_id'''+_where(where)+
        ' ORDER BY a.created_at DESC,a.id,r.ordinal', args)
    return [_answer(row) for row in rows]
