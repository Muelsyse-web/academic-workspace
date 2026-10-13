"""Keep third-party multipart/temp allocations within this project."""
from pathlib import Path
import tempfile

TEMP_ROOT = Path(__file__).resolve().parents[2] / '.cache' / 'tmp'
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEMP_ROOT)
