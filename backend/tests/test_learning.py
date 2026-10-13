"""Learning APIs against real SQLite; clock freezes only scheduling timestamps."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from workspace.db import Database, now


def make_client(root):
    from workspace.learning import router
    db = Database(root)
    db.initialize()
    with db.connect() as con:
        con.executescript((Path(__file__).parents[1]/'workspace'/'learning_schema.sql').read_text())
    app = FastAPI()
    app.state.db = db
    app.include_router(router)
    return TestClient(app), db


@pytest.fixture
def learning(tmp_path, monkeypatch):
    client, db = make_client(tmp_path)
    monkeypatch.setattr('workspace.learning.now', lambda: '2026-10-13T12:00:00+00:00')
    with db.connect() as con:
        con.execute("INSERT INTO courses VALUES ('course','AI','AI','2026','#000000',?)", (now(),))
        con.execute("INSERT INTO courses VALUES ('other','Math','M','2026','#000000',?)", (now(),))
        con.execute("INSERT INTO blobs VALUES ('hash',12,'pdf',?)", (now(),))
        con.execute("INSERT INTO documents(id,blob_hash,title,filename,kind,created_at) VALUES ('doc','hash','Source','source.pdf','pdf',?)", (now(),))
        con.execute("INSERT INTO document_versions VALUES ('v1','doc',?,'test')", (now(),))
        con.execute("INSERT INTO source_units VALUES ('u1','v1','page',2,'','A real source quote.')")
    return client, db


def ref(**values):
    return dict(document_id='doc', version_id='v1', locator_type='page', locator=2, quote='real source quote', **values)


def card(client, **values):
    r = client.post('/api/v1/flashcards', json={'front':'Question','back':'Answer', **values})
    assert r.status_code == 201, r.text
    return r.json()


def question(kind='single', **values):
    choice = kind in ('single','multiple')
    return {'kind':kind,'prompt':'What?','options':['A','B','C'] if choice else [],
            'correct_indices':[0] if kind == 'single' else ([0,2] if choice else []),
            'answer':'Reference answer','explanation':'Because','topic':'probability', **values}


def quiz(client, **values):
    r = client.post('/api/v1/quizzes', json={'title':'Quiz','questions':[question()], **values})
    assert r.status_code == 201, r.text
    return r.json()


def test_card_crud_due_filters_and_restart(learning):
    c, db = learning
    a = card(c, course_id='course',topic='probability',sources=[ref()])
    card(c, topic='other')
    assert a['ease'] == 2.5 and a['repetitions'] == 0 and a['interval_days'] == 0
    assert a['due_at'] == '2026-10-13T12:00:00+00:00'
    assert len(c.get('/api/v1/flashcards?due=true').json()) == 2
    assert c.get('/api/v1/flashcards?due=false').json() == []
    assert [x['id'] for x in c.get('/api/v1/flashcards?course_id=course&topic=probability').json()] == [a['id']]
    edited = c.patch('/api/v1/flashcards/'+a['id'],json={'front':'Edited','course_id':None}).json()
    assert edited['front'] == 'Edited' and edited['course_id'] is None and edited['sources'][0]['version_id'] == 'v1'
    fresh, _ = make_client(db.root)
    assert fresh.get('/api/v1/flashcards/'+a['id']).json() == edited
    assert c.delete('/api/v1/flashcards/'+a['id']).status_code == 204
    assert c.get('/api/v1/flashcards/'+a['id']).status_code == 404


@pytest.mark.parametrize('payload',[{'front':''},{'back':' '},{'course_id':'missing'},{'sources':[dict(ref(),quote='fake')]},{'sources':[dict(ref(),version_id='missing')]},{'sources':[dict(ref(),locator_type='paragraph')]},{'sources':[dict(ref(),locator=1)]},{'sources':[dict(ref(),document_id='missing')]}])
def test_invalid_card_does_not_write(learning,payload):
    c, _ = learning
    assert c.post('/api/v1/flashcards',json={'front':'Q','back':'A',**payload}).status_code == 422
    assert c.get('/api/v1/flashcards').json() == []
    a = card(c)
    assert c.patch('/api/v1/flashcards/'+a['id'],json=payload).status_code == 422
    assert c.get('/api/v1/flashcards/'+a['id']).json() == a


def test_sm2_review_sequence_and_idempotency(learning,monkeypatch):
    c, _ = learning
    a = card(c,course_id='course')
    path = '/api/v1/flashcards/'+a['id']+'/review'
    r = c.post(path,json={'rating':'good','idempotency_key':'first'}).json()
    assert (r['repetitions'],r['interval_days'],r['ease']) == (1,1,2.5)
    assert r['due_at'] == '2026-10-14T12:00:00+00:00'
    assert c.post(path,json={'rating':'good','idempotency_key':'first'}).json() == r
    assert c.post(path,json={'rating':'easy','idempotency_key':'first'}).status_code == 409
    assert len(c.get('/api/v1/reviews').json()) == 1
    r = c.post(path,json={'rating':'hard'}).json()
    assert (r['repetitions'],r['interval_days']) == (2,6)
    assert r['ease'] == pytest.approx(2.36)
    r = c.post(path,json={'rating':'easy'}).json()
    assert (r['repetitions'],r['interval_days']) == (3,14)
    assert r['ease'] == pytest.approx(2.46)
    r = c.post(path,json={'rating':'again'}).json()
    assert (r['repetitions'],r['interval_days']) == (0,1)
    assert r['ease'] == pytest.approx(1.66)
    for _ in range(3):
        r = c.post(path,json={'rating':'again'}).json()
    assert r['ease'] == 1.3
    assert c.get('/api/v1/flashcards?due=true').json() == []
    monkeypatch.setattr('workspace.learning.now',lambda:'2026-10-14T12:00:00+00:00')
    assert len(c.get('/api/v1/flashcards?due=true').json()) == 1
    assert len(c.get('/api/v1/reviews?course_id=other').json()) == 0
    assert len(c.get('/api/v1/reviews?flashcard_id='+a['id']).json()) == 7
    assert c.post(path,json={'rating':'invalid'}).status_code == 422


@pytest.mark.parametrize('q',[question(options=['A']),question(correct_indices=[0,1]),question(correct_indices=[3]),question(correct_indices=[-1]),question(correct_indices=[True]),question('multiple',correct_indices=[]),question('multiple',correct_indices=[0,0]),question('short',options=['A']),question('math',correct_indices=[0]),question(prompt=' '),question(sources=[dict(ref(),quote='fake')])])
def test_invalid_quiz_questions(learning,q):
    c, _ = learning
    assert c.post('/api/v1/quizzes',json={'title':'Q','questions':[q]}).status_code == 422
    assert c.get('/api/v1/quizzes').json() == []


def test_scoring_all_kinds_history_and_course_scope(learning):
    c, db = learning
    q = quiz(c,course_id='course',questions=[question(k,sources=[ref()]) for k in ('single','multiple','short','math')])
    ids = [x['id'] for x in q['questions']]
    answers = [{'question_id':ids[0],'selected':[0]}, {'question_id':ids[1],'selected':[2,0]},
               {'question_id':ids[2],'text':'Different wording','self_correct':True},
               {'question_id':ids[3],'text':'Reference answer','self_correct':False}]
    response = c.post('/api/v1/quizzes/'+q['id']+'/attempts',json={'answers':answers,'idempotency_key':'attempt1'})
    assert response.status_code == 201, response.text
    attempt = response.json()
    assert (attempt['score'],attempt['total']) == (3,4)
    assert [a['correct'] for a in attempt['answers']] == [True,True,True,False]
    assert c.post('/api/v1/quizzes/'+q['id']+'/attempts',json={'answers':answers,'idempotency_key':'attempt1'}).json() == attempt
    assert len(c.get('/api/v1/attempts').json()) == 1
    weak = c.get('/api/v1/learning/weak-topics?course_id=course').json()
    assert weak == [{'course_id':'course','topic':'probability','incorrect_count':1,'total_count':4}]
    wrong = c.get('/api/v1/learning/wrong-questions?course_id=course').json()
    assert len(wrong) == 1 and wrong[0]['question']['kind'] == 'math'
    assert wrong[0]['question']['sources'][0]['quote'] == 'real source quote'
    assert wrong[0]['question']['answer'] == 'Reference answer'
    assert c.get('/api/v1/learning/weak-topics?course_id=other').json() == []
    assert c.get('/api/v1/learning/wrong-questions?course_id=other').json() == []
    assert c.get('/api/v1/attempts?course_id=other').json() == []
    assert c.get('/api/v1/quizzes?course_id=other').json() == []
    fresh, _ = make_client(db.root)
    assert fresh.get('/api/v1/quizzes/'+q['id']).json() == q
    assert fresh.get('/api/v1/attempts?quiz_id='+q['id']).json() == [attempt]
    assert c.delete('/api/v1/quizzes/'+q['id']).status_code == 204
    assert c.get('/api/v1/quizzes/'+q['id']).status_code == 404
    # Historical answers remain useful after deleting their original quiz.
    assert c.get('/api/v1/attempts').json() == [attempt]


@pytest.mark.parametrize('kind,selected,self_correct,expected', [('single',[1],None,False),('multiple',[0],None,False),('multiple',[0,1,2],None,False),('short',[],True,True),('math',[],False,False)])
def test_exact_and_explicit_grading(learning,kind,selected,self_correct,expected):
    c, _ = learning
    q = quiz(c,questions=[question(kind)])
    r = c.post('/api/v1/quizzes/'+q['id']+'/attempts',json={'answers':[{'question_id':q['questions'][0]['id'],'selected':selected,'text':'Reference answer','self_correct':self_correct}]})
    assert r.status_code == 201, r.text
    assert r.json()['answers'][0]['correct'] is expected


@pytest.mark.parametrize('bad', ['missing','unknown','duplicate','index','boolean','single-many','self-grade-choice','ungraded-short','selected-short'])
def test_bad_attempt_atomicity(learning,bad):
    c, _ = learning
    q = quiz(c,questions=[question(),question('short')])
    answers = [{'question_id':q['questions'][0]['id'],'selected':[0]}, {'question_id':q['questions'][1]['id'],'text':'answer','self_correct':True}]
    if bad == 'missing': answers.pop()
    elif bad == 'unknown': answers[0]['question_id'] = 'unknown'
    elif bad == 'duplicate': answers[1] = answers[0]
    elif bad == 'index': answers[0]['selected'] = [9]
    elif bad == 'boolean': answers[0]['selected'] = [True]
    elif bad == 'single-many': answers[0]['selected'] = [0,1]
    elif bad == 'self-grade-choice': answers[0]['self_correct'] = True
    elif bad == 'ungraded-short': answers[1].pop('self_correct')
    else: answers[1]['selected'] = [0]
    r = c.post('/api/v1/quizzes/'+q['id']+'/attempts',json={'answers':answers})
    assert r.status_code == 422, r.text
    assert c.get('/api/v1/attempts').json() == []
    assert c.get('/api/v1/learning/weak-topics').json() == []


@pytest.mark.parametrize('method,path,payload', [('get','flashcards/missing',None),('patch','flashcards/missing',{'front':'New'}),('delete','flashcards/missing',None),('post','flashcards/missing/review',{'rating':'good'}),('get','quizzes/missing',None),('delete','quizzes/missing',None),('post','quizzes/missing/attempts',{'answers':[]})])
def test_missing_resources(learning,method,path,payload):
    c, _ = learning
    assert c.request(method,'/api/v1/'+path,**({'json':payload} if payload is not None else {})).status_code == 404


@pytest.mark.parametrize('payload',[{'front':None},{'back':None},{'topic':None},{'sources':None},{'surprise':True}])
def test_invalid_patch_preserves_schedule_and_content(learning,payload):
    c, _ = learning
    a = card(c)
    c.post('/api/v1/flashcards/'+a['id']+'/review',json={'rating':'easy'})
    before = c.get('/api/v1/flashcards/'+a['id']).json()
    assert c.patch('/api/v1/flashcards/'+a['id'],json=payload).status_code == 422
    assert c.get('/api/v1/flashcards/'+a['id']).json() == before


def test_review_history_survives_card_edit_deletion_and_restart(learning):
    c, db = learning
    a = card(c,course_id='course',topic='Original')
    review = c.post('/api/v1/flashcards/'+a['id']+'/review',json={'rating':'again'}).json()
    c.patch('/api/v1/flashcards/'+a['id'],json={'course_id':'other','topic':'Edited'})
    assert c.get('/api/v1/reviews?course_id=course&topic=Original').json() == [review]
    c.delete('/api/v1/flashcards/'+a['id'])
    fresh, _ = make_client(db.root)
    assert fresh.get('/api/v1/reviews?flashcard_id='+a['id']).json() == [review]


def test_immutable_source_versions_for_cards_and_quizzes(learning):
    c, db = learning
    with db.connect() as con:
        con.execute("INSERT INTO document_versions VALUES ('v2','doc',?,'test')", (now(),))
        con.execute("INSERT INTO source_units VALUES ('u2','v2','page',2,'','New version text')")
        con.execute("UPDATE documents SET active_version='v2' WHERE id='doc'")
    a = card(c,sources=[ref()])
    q = quiz(c,questions=[question(sources=[ref()])])
    assert a['sources'][0]['version_id'] == 'v1'
    assert q['questions'][0]['sources'][0]['version_id'] == 'v1'
    bad = dict(ref(),version_id='v2')
    assert c.patch('/api/v1/flashcards/'+a['id'],json={'sources':[bad]}).status_code == 422
    assert c.post('/api/v1/quizzes',json={'title':'Bad','questions':[question(sources=[bad])]}).status_code == 422


def test_attempt_key_conflict_and_empty_multiple_answer(learning):
    c, _ = learning
    q = quiz(c,questions=[question('multiple')])
    payload = {'answers':[{'question_id':q['questions'][0]['id'],'selected':[]}], 'idempotency_key':'same'}
    first = c.post('/api/v1/quizzes/'+q['id']+'/attempts',json=payload)
    assert first.status_code == 201 and first.json()['score'] == 0
    payload['answers'][0]['selected'] = [0,2]
    assert c.post('/api/v1/quizzes/'+q['id']+'/attempts',json=payload).status_code == 409
    assert len(c.get('/api/v1/attempts').json()) == 1


@pytest.mark.parametrize('payload',[{'title':' '},{'questions':[]},{'course_id':'missing'},{'questions':[question('short',answer=' ')]},{'questions':[question(options=['A',' '])] }])
def test_quiz_form_validation(learning,payload):
    c, _ = learning
    assert c.post('/api/v1/quizzes',json={'title':'Quiz','questions':[question()],**payload}).status_code == 422
    assert c.get('/api/v1/quizzes').json() == []


def test_weak_topics_count_multiple_attempts_separately_by_course(learning):
    c, _ = learning
    for course_id in ('course','other'):
        q = quiz(c,course_id=course_id)
        for selected in ([1],[0]):
            r = c.post('/api/v1/quizzes/'+q['id']+'/attempts',json={'answers':[{'question_id':q['questions'][0]['id'],'selected':selected}]})
            assert r.status_code == 201
    rows = c.get('/api/v1/learning/weak-topics').json()
    assert len(rows) == 2
    assert {r['course_id'] for r in rows} == {'course','other'}
    assert all((r['incorrect_count'],r['total_count']) == (1,2) for r in rows)
    assert len(c.get('/api/v1/learning/wrong-questions?course_id=course&topic=probability').json()) == 1
    assert c.get('/api/v1/learning/wrong-questions?topic=missing').json() == []


def test_quiz_edit_preserves_question_ids_until_replaced_and_attempt_snapshots(learning):
    c, db = learning
    original = quiz(c,course_id='course',questions=[question(sources=[ref()])])
    path = '/api/v1/quizzes/'+original['id']
    old_question = original['questions'][0]
    attempt = c.post(path+'/attempts',json={'answers':[{'question_id':old_question['id'],'selected':[1]}]}).json()
    metadata = c.patch(path,json={'title':'Renamed','course_id':'other'})
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()['questions'] == original['questions']
    assert metadata.json()['title'] == 'Renamed' and metadata.json()['course_id'] == 'other'
    replacement = question(options=['New A','New B'],correct_indices=[1],answer='New answer',explanation='Changed explanation')
    updated = c.patch(path,json={'questions':[replacement],'course_id':None})
    assert updated.status_code == 200, updated.text
    updated = updated.json()
    assert updated['questions'][0]['id'] != old_question['id']
    assert updated['questions'][0]['options'] == ['New A','New B']
    assert updated['questions'][0]['correct_indices'] == [1]
    assert updated['course_id'] is None
    assert c.get('/api/v1/attempts').json() == [attempt]
    assert attempt['answers'][0]['question'] == old_question
    assert attempt['course_id'] == 'course' and attempt['quiz_title'] == 'Quiz'
    assert c.get('/api/v1/learning/wrong-questions?course_id=course').json()[0]['question'] == old_question
    stale = c.post(path+'/attempts',json={'answers':[{'question_id':old_question['id'],'selected':[1]}]})
    assert stale.status_code == 422
    fresh_attempt = c.post(path+'/attempts',json={'answers':[{'question_id':updated['questions'][0]['id'],'selected':[1]}]})
    assert fresh_attempt.status_code == 201 and fresh_attempt.json()['score'] == 1
    fresh, _ = make_client(db.root)
    assert fresh.get(path).json() == updated


@pytest.mark.parametrize('payload',[{'title':None},{'title':' '},{'questions':None},{'questions':[]},{'course_id':'missing'},
                                    {'questions':[question(correct_indices=[9])]},
                                    {'questions':[question(sources=[dict(ref(),quote='fake')])]}])
def test_invalid_quiz_edit_rolls_back_every_field(learning,payload):
    c, _ = learning
    original = quiz(c,course_id='course')
    path = '/api/v1/quizzes/'+original['id']
    response = c.patch(path,json={'title':'Changed','course_id':'other',**payload})
    assert response.status_code == 422, response.text
    assert c.get(path).json() == original


def test_patch_missing_quiz_is_404(learning):
    c, _ = learning
    assert c.patch('/api/v1/quizzes/missing',json={'title':'Changed'}).status_code == 404
