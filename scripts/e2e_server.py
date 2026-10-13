"""Run each browser suite against a fresh, project-contained library."""
from pathlib import Path
import os
import sys
import tempfile

project=Path(__file__).resolve().parents[1]
runs=project/'.cache'/'e2e-runs'
runs.mkdir(parents=True,exist_ok=True)
(project/'.cache'/'tmp').mkdir(parents=True,exist_ok=True)
os.environ['WORKSPACE_DATA_DIR']=tempfile.mkdtemp(prefix='run-',dir=runs)
os.environ['TMPDIR']=str(project/'.cache'/'tmp')
os.chdir(project)
os.execv(sys.executable,[sys.executable,'-m','uvicorn','workspace.app:create_app','--factory','--app-dir','backend','--host','127.0.0.1','--port','8766','--no-access-log'])
