"""Intake — turn a repo URL or local path into a ready-to-analyse project dir,
then detect the stack (grey-box) so the Architect has real signal to plan from.

Cross-platform: uses `pathlib` and `git` (via subprocess) rather than shell
built-ins, so it works on Windows/macOS/Linux. No `ls -la`.
"""
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

# Files that identify a stack/framework. Order matters (first match wins per lang).
_STACK_MARKERS = [
    ("python", "requirements.txt", None),
    ("python", "pyproject.toml", None),
    ("python", "Pipfile", None),
    ("node", "package.json", None),
    ("go", "go.mod", None),
    ("ruby", "Gemfile", None),
    ("java", "pom.xml", None),
    ("rust", "Cargo.toml", None),
    ("php", "composer.json", None),
]

# Framework hints found by scanning source content.
_FRAMEWORK_HINTS = {
    "flask": r"from\s+flask|import\s+flask",
    "fastapi": r"from\s+fastapi|import\s+fastapi",
    "django": r"django",
    "express": r"require\(['\"]express['\"]\)|from\s+['\"]express['\"]",
    "next": r"\"next\"\s*:",
    "gin": r"gin-gonic/gin",
}


def _run_git_clone(repo_url: str, dest: str) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, dest],
        check=True, capture_output=True, text=True, timeout=180,
    )


def resolve_intake(repo_url: Optional[str], project_path: Optional[str]) -> str:
    """Resolve the engagement's source into a local directory path.

    A local `project_path` is preferred (fast, offline-first). A `repo_url` is
    shallow-cloned into a temp dir. Raises ValueError with a human message on
    bad input so the API can surface a 400.
    """
    if project_path:
        p = Path(project_path).expanduser()
        if not p.is_dir():
            raise ValueError(f"project_path not found: {project_path}")
        return str(p.resolve())

    if repo_url:
        if not re.match(r"^(https?://|git@)", repo_url):
            raise ValueError(f"repo_url must be an http(s) or git@ URL: {repo_url}")
        dest = tempfile.mkdtemp(prefix="prody_intake_")
        try:
            _run_git_clone(repo_url, dest)
        except subprocess.CalledProcessError as e:
            raise ValueError(f"git clone failed: {e.stderr.strip() or e}") from e
        except FileNotFoundError as e:
            raise ValueError("git is not installed or not on PATH") from e
        return dest

    raise ValueError("provide either repo_url or project_path")


def extract_zip_upload(zip_path: str) -> str:
    """Extract an uploaded project zip into a temp dir and return the project root."""
    src = Path(zip_path)
    if not src.is_file():
        raise ValueError(f"upload not found: {zip_path}")

    dest = Path(tempfile.mkdtemp(prefix="prody_upload_"))
    dest_root = dest.resolve()

    try:
        with zipfile.ZipFile(src, "r") as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                target = (dest / member.filename).resolve()
                if not str(target).startswith(str(dest_root)):
                    raise ValueError("zip contains unsafe paths")
            zf.extractall(dest)
    except zipfile.BadZipFile as e:
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError("file is not a valid zip archive") from e

    children = [p for p in dest.iterdir() if p.name != "__MACOSX"]
    if len(children) == 1 and children[0].is_dir():
        return str(children[0].resolve())
    return str(dest.resolve())


def detect_stack(project_path: str) -> dict:
    """Grey-box stack detection from marker files + source content sniffing.

    Returns a business-first summary the Architect and dashboard both use.
    """
    root = Path(project_path)
    languages, entrypoints = [], []

    for lang, marker, _ in _STACK_MARKERS:
        if (root / marker).is_file() and lang not in languages:
            languages.append(lang)

    # Common entrypoints (used by the Architect + runner to boot the app).
    for cand in ("app.py", "main.py", "wsgi.py", "manage.py", "server.js",
                 "index.js", "app.js", "main.go", "Dockerfile"):
        if (root / cand).is_file():
            entrypoints.append(cand)

    # Sniff a bounded set of source files for framework hints.
    frameworks = set()
    scanned = 0
    for path in root.rglob("*"):
        if scanned >= 60:
            break
        if not path.is_file() or path.suffix.lower() not in (".py", ".js", ".ts", ".go", ".json"):
            continue
        if any(part in {"node_modules", ".git", ".venv", "venv", "dist", "build"}
               for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:20000]
        except Exception:
            continue
        scanned += 1
        for name, pattern in _FRAMEWORK_HINTS.items():
            if re.search(pattern, text, re.IGNORECASE):
                frameworks.add(name)

    has_dockerfile = (root / "Dockerfile").is_file()
    return {
        "project_path": str(root.resolve()),
        "languages": languages or ["unknown"],
        "frameworks": sorted(frameworks),
        "entrypoints": entrypoints,
        "has_dockerfile": has_dockerfile,
        "deploy_target": "cloud_run",  # our default production surface
    }
