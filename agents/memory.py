import hashlib
from pathlib import Path







#---------------路径----------------------
def get_memory_dir() -> Path:
    d = Path.home() / ".bear-code" / "projects" / _project_hash() / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _project_hash() -> str:
    return hashlib.sha256(str(Path.cwd()).encode()).hexdigest()[:16]