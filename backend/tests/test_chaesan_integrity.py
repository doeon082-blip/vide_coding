"""채산 무결성 테스트: 파일 구조, core 의존성 규칙, 비밀값·데이터 커밋 방지."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
CORE = BACKEND / "app" / "chaesan" / "core"

# 지시서 4절 구조 중 지금 단계까지 있어야 하는 파일. 다른 파일(catalog, planner, search, demand)은 C~E단계에서 더한다.
EXPECTED_CORE = {"__init__.py", "config.py", "ports.py", "guard.py", "when.py", "sql_guard.py", "answer.py", "typo.py"}
EXPECTED_INGEST = {"__init__.py", "specs.py", "convert.py", "load.py", "aggregate.py"}


def _core_files() -> list[Path]:
    return sorted(CORE.glob("*.py"))


def test_structure() -> None:
    assert (BACKEND / "app" / "chaesan" / "__init__.py").is_file()
    assert {p.name for p in _core_files()} >= EXPECTED_CORE
    assert {p.name for p in (BACKEND / "app" / "chaesan" / "ingest").glob("*.py")} >= EXPECTED_INGEST


@pytest.mark.parametrize("path", _core_files(), ids=lambda p: p.name)
def test_core_uses_stdlib_only(path: Path) -> None:
    """core/는 Pyodide(서비스)에서 그대로 돌아야 하므로 표준 라이브러리와 core 자신만 import한다."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad: list[str] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        for name in names:
            top = name.split(".")[0]
            if name.startswith("app.chaesan.core") or top == "__future__" or top in sys.stdlib_module_names:
                continue
            bad.append(name)
    assert not bad, f"{path.name}: core에서 쓸 수 없는 import {bad}"


@pytest.mark.parametrize("path", _core_files(), ids=lambda p: p.name)
def test_core_public_functions_are_typed(path: Path) -> None:
    """공개 함수는 인자·반환 타입 힌트와 docstring을 갖는다(작업 규칙 8)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not node.name.startswith("_"):
            args = [a for a in node.args.args + node.args.kwonlyargs if a.arg not in {"self", "cls"}]
            assert node.returns is not None, f"{path.name}:{node.name} 반환 타입 없음"
            assert all(a.annotation is not None for a in args), f"{path.name}:{node.name} 인자 타입 없음"


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def test_data_and_env_not_tracked() -> None:
    assert "backend/data/" in (REPO / ".gitignore").read_text(encoding="utf-8")
    tracked = _tracked()
    assert not [f for f in tracked if f.startswith("backend/data/")]
    assert not [f for f in tracked if re.search(r"(^|/)\.env(\.[^/]*)?$", f) and not f.endswith(".env.example")]


# 실제 키처럼 보이는 값. 이름(PUBLIC_DATA_API_KEY=)만 있고 값이 비어 있는 .env.example은 통과한다.
_SECRET_PATTERNS = [
    re.compile(r"(?i)(?:service_?key|api_?key|secret|token|password)\s*[=:]\s*['\"]?[A-Za-z0-9%+/=_\-]{24,}"),
    re.compile(r"\b(?:sk|ghp|gho|github_pat|xox[abp])_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


_PLACEHOLDER = re.compile(r"(?i)your|here|example|xxx|changeme|dummy")


def test_no_secrets_in_tracked_files() -> None:
    hits: list[str] = []
    for rel in _tracked():
        p = REPO / rel
        if not p.is_file() or p.stat().st_size > 2_000_000 or p.suffix in {".png", ".jpg", ".lock", ".ico"}:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for rx in _SECRET_PATTERNS:
            for m in rx.finditer(text):
                if _PLACEHOLDER.search(m.group(0).split("=", 1)[-1]):
                    continue  # .env.example의 "your_..._here" 같은 자리표시값
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{rel}:{line}")  # 값은 출력하지 않는다
    assert not hits, f"비밀값으로 보이는 문자열: {hits}"
