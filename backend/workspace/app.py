"""Application factory: isolated data directory, same-origin UI, lifecycle."""
from contextlib import asynccontextmanager
import os
import tempfile
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .db import Database
from .limits import RequestLimits
from .jobs import IndexWorker
from .embeddings import EmbeddingWorker,router as embeddings_router
from .documents import router as documents_router
from .search import router as search_router
from .security import LocalSecurity, router as security_router
from .courses import router as courses_router
from .notes import router as notes_router
from .learning import router as learning_router
from .backup import router as backup_router
from .ai import router as ai_router
from .configuration import router as configuration_router

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def create_app(data_dir: Path | None = None) -> FastAPI:
    temporary = PROJECT_ROOT/'.cache'/'tmp'
    temporary.mkdir(parents=True,exist_ok=True)
    tempfile.tempdir = str(temporary)
    root = Path(data_dir or os.environ.get('WORKSPACE_DATA_DIR', PROJECT_ROOT/'var'/'data'))
    db = Database(root)
    db.initialize()

    @asynccontextmanager
    async def lifespan(app):
        app.state.index_worker = IndexWorker(db)
        app.state.index_worker.recover()
        app.state.embedding_worker = EmbeddingWorker(app)
        try:
            yield
        finally:
            app.state.index_worker.close()
            app.state.embedding_worker.close()

    app = FastAPI(title='Local Academic Workspace',version='0.1.0',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url='/api/v1/openapi.json')
    app.state.db = db
    app.state.sessions = {}
    app.state.conversation_locks = {}
    app.state.conversation_cancels = {}
    app.add_middleware(RequestLimits)
    app.add_middleware(LocalSecurity)
    app.include_router(security_router)
    app.include_router(courses_router)
    app.include_router(documents_router)
    app.include_router(search_router)
    app.include_router(notes_router)
    app.include_router(learning_router)
    app.include_router(backup_router)
    app.include_router(ai_router)
    app.include_router(configuration_router)
    app.include_router(embeddings_router)

    @app.get('/api/v1/health')
    def health():
        return {'status':'ok','schema_version':db.one('PRAGMA user_version')['user_version']}

    dist = PROJECT_ROOT/'frontend'/'dist'
    if dist.is_dir():
        app.mount('/', StaticFiles(directory=dist,html=True),name='ui')
    return app
