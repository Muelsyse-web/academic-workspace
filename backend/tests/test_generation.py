"""Mock-provider generation checks; never contacts a real model endpoint."""
import importlib.util
import json

import pytest
from fastapi.testclient import TestClient

from workspace.app import create_app
from workspace.providers import ProviderError
from test_core import login
from test_documents import upload, wait_document


class MockProvider:
    def __init__(self, mode='valid'):
        self.mode = mode
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        if self.mode == 'offline':
            raise ProviderError('Local model offline')
        if self.mode == 'malformed':
            return 'not JSON'
        task = json.loads(messages[-1]['content'])
        evidence = task['evidence'][0]
        citation = {'id': evidence['chunk_id'], 'quote': evidence['text'][:40]}
        if self.mode == 'fake':
            citation['id'] = 'invented'
        if self.mode == 'bad_quote':
            citation['quote'] = 'Invented quotation, not evidence'
        if self.mode == 'blank_quote':
            citation['quote'] = ' '
        citations = [] if self.mode == 'missing' else [citation]
        count = task['count'] + (1 if self.mode == 'wrong_count' else 0)
        if task['kind'] == 'flashcards':
            payload = {'drafts': [{'front': 'How does gradient descent update?',
                                  'back': 'Using derivatives.', 'topic': 'Gradient',
                                  'citations': citations} for _ in range(count)]}
            if self.mode == 'fabricated_source':
                payload['drafts'][0]['sources'] = [{'locator': 999, 'path': '/fake/file'}]
            if self.mode == 'blank':
                payload['drafts'][0]['front'] = ' '
        elif task['kind'] == 'quiz':
            kinds = task['question_kinds']
            questions = []
            for index in range(count):
                kind = 'math' if self.mode == 'wrong_kind' else kinds[index % len(kinds)]
                question = {'kind': kind, 'prompt': 'Explain gradient descent.',
                            'topic': 'Gradient', 'citations': citations}
                if kind in ('single', 'multiple'):
                    question.update(options=['Derivative', 'Random', 'Gradient'],
                                    correct_indices=[0] if kind == 'single' else [0, 2])
                else:
                    question['answer'] = 'Use the derivative to update parameters.'
                if self.mode == 'bad_options':
                    question['correct_indices'] = [99]
                questions.append(question)
            payload = {'draft': {'title': 'Gradient practice', 'questions': questions}}
        else:
            payload = {'answer': 'Review derivatives, then practise gradient updates. [1]',
                       'citations': citations, 'insufficient_evidence': self.mode == 'insufficient'}
        return json.dumps(payload)


@pytest.fixture
def context(tmp_path):
    app = create_app(tmp_path)
    if importlib.util.find_spec('workspace.generation'):
        from workspace.generation import router
        if not any(getattr(route, 'path', '') == '/api/v1/learning/generate' for route in app.routes):
            app.router.routes[0:0] = router.routes
    app.state.provider_override = MockProvider()
    with TestClient(app, base_url='http://localhost') as client:
        login(client)
        course = client.post('/api/v1/courses', json={'name': 'ML'}).json()
        doc = upload(client, 'gradient.txt', b'Gradient descent updates parameters using derivatives.', course['id'])
        upload(client, 'other.txt', b'Gradient descent outside the selected course.')
        yield app, client, course, doc


def generate(client, kind='flashcards', **kwargs):
    return client.post('/api/v1/learning/generate', json={'kind': kind, 'count': 1, **kwargs})


def test_flashcard_drafts_have_real_scoped_sources_and_are_not_saved(context):
    app, client, course, doc = context
    response = generate(client, course_id=course['id'], focus='gradient')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['kind'] == 'flashcards'
    source = result['drafts'][0]['sources'][0]
    assert source == {'document_id': doc['id'], 'version_id': doc['active_version'],
                      'locator_type': 'line', 'locator': 1,
                      'quote': 'Gradient descent updates parameters using derivatives.'[:40]}
    assert source['document_id'] == doc['id']
    assert result['drafts'][0]['course_id'] == course['id']
    sent = json.loads(app.state.provider_override.calls[0][-1]['content'])
    assert all(item['document_id'] == doc['id'] for item in sent['evidence'])
    assert 'untrusted' in app.state.provider_override.calls[0][0]['content'].lower()
    assert client.get('/api/v1/flashcards').json() == []
    assert client.get('/api/v1/quizzes').json() == []
    assert client.post('/api/v1/flashcards', json=result['drafts'][0]).status_code == 201


@pytest.mark.parametrize('mode', ['fake', 'bad_quote', 'blank_quote', 'missing', 'malformed', 'wrong_count', 'blank', 'fabricated_source'])
def test_invalid_flashcard_drafts_rejected(context, mode):
    app, client, course, doc = context
    app.state.provider_override = MockProvider(mode)
    assert generate(client, document_ids=[doc['id']]).status_code == 502
    assert client.get('/api/v1/flashcards').json() == []


def test_all_quiz_question_kinds_are_editable_and_saveable(context):
    app, client, course, doc = context
    kinds = ['single', 'multiple', 'short', 'math']
    response = generate(client, 'quiz', course_id=course['id'], count=4, question_kinds=kinds)
    assert response.status_code == 200, response.text
    draft = response.json()['draft']
    assert [q['kind'] for q in draft['questions']] == kinds
    assert all(q['sources'][0]['document_id'] == doc['id'] for q in draft['questions'])
    assert client.get('/api/v1/quizzes').json() == []
    assert client.post('/api/v1/quizzes', json=draft).status_code == 201


@pytest.mark.parametrize('mode', ['wrong_count', 'wrong_kind', 'bad_options', 'missing', 'fake'])
def test_invalid_quiz_drafts_rejected(context, mode):
    app, client, course, doc = context
    app.state.provider_override = MockProvider(mode)
    assert generate(client, 'quiz', course_id=course['id'], question_kinds=['single']).status_code == 502
    assert client.get('/api/v1/quizzes').json() == []


def test_summary_returns_verified_evidence_and_review_advice(context):
    app, client, course, doc = context
    response = generate(client, 'summary', document_ids=[doc['id']], focus='gradient review advice')
    assert response.status_code == 200, response.text
    assert response.json()['kind'] == 'summary'
    assert 'Review' in response.json()['answer']
    assert response.json()['sources'][0]['document_id'] == doc['id']
    assert app.state.db.all('SELECT * FROM notes') == []
    assert app.state.db.all('SELECT * FROM messages') == []


@pytest.mark.parametrize('mode', ['fake', 'bad_quote', 'missing', 'insufficient', 'malformed'])
def test_unverified_summary_rejected(context, mode):
    app, client, course, doc = context
    app.state.provider_override = MockProvider(mode)
    assert generate(client, 'summary', document_ids=[doc['id']]).status_code == 502


@pytest.mark.parametrize('body', [{'count': 0}, {'count': 11}, {'count': True}, {'count': 1.5},
                                {'course_id': 'missing'}, {'document_ids': ['missing']},
                                {'question_kinds': []}, {'question_kinds': ['essay']},
                                {'course_id': ''}, {'document_ids': ['']}])
def test_bad_inputs_do_not_call_provider(context, body):
    app, client, course, doc = context
    assert generate(client, focus='gradient', **body).status_code == 422
    assert app.state.provider_override.calls == []


def test_evidence_absence_and_unscoped_empty_focus_do_not_call_provider(context):
    app, client, course, doc = context
    assert generate(client).status_code == 422
    assert generate(client, course_id=course['id'], focus='zzzznomatch').status_code == 422
    empty_course = client.post('/api/v1/courses', json={'name': 'Empty'}).json()
    assert generate(client, course_id=empty_course['id']).status_code == 422
    assert generate(client, course_id=empty_course['id'], document_ids=[doc['id']]).status_code == 422
    assert app.state.provider_override.calls == []


def test_offline_provider_has_503_and_does_not_save(context):
    app, client, course, doc = context
    app.state.provider_override = MockProvider('offline')
    response = generate(client, document_ids=[doc['id']])
    assert response.status_code == 503
    assert client.get('/api/v1/flashcards').json() == []


def test_blank_focus_uses_only_active_version_and_requested_documents(context):
    app, client, course, doc = context
    client.post('/api/v1/documents/' + doc['id'] + '/reindex')
    current = wait_document(client, doc['id'])
    assert current['active_version'] != doc['active_version']
    response = generate(client, 'summary', document_ids=[doc['id']])
    assert response.status_code == 200, response.text
    evidence = json.loads(app.state.provider_override.calls[0][-1]['content'])['evidence']
    assert all(source['document_id'] == doc['id'] and source['version_id'] == current['active_version'] for source in evidence)
    assert len(evidence) <= 6 and sum(len(s['text']) for s in evidence) <= 12000
