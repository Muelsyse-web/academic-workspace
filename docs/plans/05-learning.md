# Quiz and Flashcards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Support model-independent manual practice, four quiz formats, durable review history, weak-topic practice and source-grounded generated drafts.
**Architecture:** Dedicated learning service/router and migration, with pure SM-2 scheduling and deterministic choice scoring. AI draft generation will use the shared local provider and validated evidence service.
**Tech Stack:** FastAPI/Pydantic/sqlite3, pytest, React Markdown.

### Backend task
Files: `backend/workspace/learning.py`, `backend/workspace/learning_schema.sql`, `backend/tests/test_learning.py`.
- [x] Test-first flashcard CRUD (front,back,course_id,topic,source references), due list, review Again/Hard/Good/Easy and durable history.
- [x] SM-2 version1: grades 0/3/4/5; Again resets repetitions and interval to1 day; passing first interval1, second6, later round(previous*ease), hard multiplier can reduce interval but minimum1; ease update standard SM-2 formula with floor1.3. Store review timestamps in UTC, next due, ease, interval and repetitions; dates display Shanghai.
- [x] Test-first quiz CRUD with single/multiple/short/math questions. Exact set matching for multiple; single one answer; short/math reference answer and explicit self-assessment. Reject absent options, out-of-range answers and duplicate/invalid responses. Persist attempts and answer outcomes in a transaction.
- [x] Return history, wrong-question list and weak topics based on actual attempts. Review screens function without model configured.
- [x] Validate course and actual source quote references. Seed no user data. Isolated router tests via FastAPI shared Database, module schema executed in test fixture; main integrates migration4.
- [x] GET/POST `/flashcards`, GET/PATCH/DELETE `/flashcards/{id}`, POST `/flashcards/{id}/review` body `{rating:'again'|'hard'|'good'|'easy'}`, GET `/reviews`; filters course_id/topic/due (boolean).
- [x] GET/POST `/quizzes`, GET `/quizzes/{id}`, DELETE `/quizzes/{id}`, POST `/quizzes/{id}/attempts` body `{answers:[{question_id,selected:int[],text:str,self_correct:bool|null}]}`; GET `/attempts`, GET `/learning/weak-topics`, GET `/learning/wrong-questions`. Question fields kind,prompt,options[],correct_indices[],answer,explanation,topic,sources[]. Quiz fields title,course_id,questions[].
- [x] Run tests with `--basetemp=.cache/learning-tests`; report exact APIs/results to main; independent review before milestone acceptance.

### Integration/generation/UI task (main)
- [x] Use shared AI evidence to generate validated draft flashcards/questions, return to editable forms; never persist model drafts without user save.
- [x] Implement Learning page tabs/cards/quiz editor/attempt/review/history. Display exact-choice automatic score separately from short/math self-assessment.
- [x] End-to-end create manual cards and all quiz formats, complete reviews/attempts, reload, verify due dates/history and targeted weak-topic selection.

实施核对：核心实现及最终验证已完成，实际结果与限制以根目录 ACCEPTANCE.md 为准。真实 LM Studio 推理仍未验证；条件性真实模型检查由环境状态记录完成，不能视为真实推理通过。
