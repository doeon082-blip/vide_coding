"""저장소 위생 테스트: 환경변수 예시 파일의 정합성, 개인 식별 정보·비밀값 흔적 방지."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
APP = BACKEND / "app"

# 코드는 읽지만 예시에 없어도 되는 선택 항목(기본값이 있고 거의 안 바꾼다)
OPTIONAL_ENV = {"PHOTO_CACHE_FILE"}


def _env_names(path: Path) -> set[str]:
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", path.read_text(encoding="utf-8"), flags=re.MULTILINE))


def _env_read_by_code() -> set[str]:
    names: set[str] = set()
    for py in APP.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        names |= set(re.findall(r"(?:getenv|environ\.get|environ)\(?\[?[\"']([A-Z][A-Z0-9_]+)[\"']", text))
    return names


def test_env_example_has_no_unused_entries() -> None:
    """코드가 읽지 않는 항목이 예시에 남아 있으면 사용자를 헷갈리게 한다(예: 쓰지 않는 API_PORT)."""
    unused = _env_names(BACKEND / ".env.example") - _env_read_by_code()
    assert not unused, f"코드가 읽지 않는 예시 항목: {sorted(unused)}"


def test_env_example_lists_every_setting_the_code_reads() -> None:
    missing = _env_read_by_code() - _env_names(BACKEND / ".env.example") - OPTIONAL_ENV
    assert not missing, f"예시에 없는 설정: {sorted(missing)}"


def test_frontend_env_has_only_public_names() -> None:
    """VITE_ 변수는 빌드 결과(브라우저)에 그대로 들어간다. 비밀로 보이는 이름은 금지."""
    names = _env_names(REPO / "frontend" / ".env.example")
    assert names and all(n.startswith("VITE_") for n in names)
    assert not [n for n in names if re.search(r"KEY|SECRET|TOKEN|PASSWORD", n)]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False).stdout.strip()


def test_no_personal_identifiers_in_tracked_files() -> None:
    """git 사용자 이름·이메일·아이디가 문서·예시 파일에 박혀 있지 않다.
    값은 테스트 코드에 쓰지 않고 실행할 때 git config에서 읽는다(테스트 자체가 개인정보를 담지 않도록).
    pyproject의 authors는 패키지 메타데이터라 제외한다."""
    needles = {v.lower() for v in (_git("config", "user.name"), _git("config", "user.email").split("@")[0]) if len(v) >= 4}
    if not needles:
        pytest.skip("git 사용자 설정 없음")
    hits: list[str] = []
    for rel in _git("ls-files").splitlines():
        p = REPO / rel
        if rel.endswith(("uv.lock", "package-lock.json", "pyproject.toml")) or not p.is_file():
            continue
        if p.suffix in {".png", ".jpg", ".ico", ".svg", ".woff", ".woff2"} or p.stat().st_size > 2_000_000:
            continue
        low = p.read_text(encoding="utf-8", errors="ignore").lower()
        hits += [f"{rel}" for n in needles if n in low]
    assert not hits, f"개인 식별 정보로 보이는 문자열이 있는 파일: {sorted(set(hits))}"


def test_backend_gitignore_protects_secrets_even_from_inside_backend() -> None:
    """backend/에 별도의 .git(중첩 저장소)이 있어, 그 안에서 `git add -A`를 해도 .env·데이터가 올라가지 않아야 한다."""
    required = {".env", "data/", "*.sqlite"}
    lines = {ln.strip() for ln in (BACKEND / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert required <= lines and "!.env.example" in lines
    if (BACKEND / ".git").exists():
        for path in (".env", "data/chaesan.sqlite", "data/raw/files/15089962.csv"):
            checked = subprocess.run(["git", "check-ignore", "-q", path], cwd=BACKEND, check=False)
            assert checked.returncode == 0, f"backend 안에서 {path}가 무시되지 않는다"


def test_web_examples_file_is_tracked_but_raw_data_stays_ignored() -> None:
    """`data/` 무시 규칙이 화면의 예시 답(web/data/examples.json)까지 삼키면 저장소를 새로 받았을 때 예시가 비어 버린다.
    (실제로 한 번 빠진 채 올라갔다.) 예시는 올리고, 원본 데이터 폴더는 계속 막는다."""
    root = BACKEND.parent
    example = "backend/app/chaesan/web/data/examples.json"
    assert subprocess.run(["git", "check-ignore", "-q", example], cwd=root, check=False).returncode == 1, "예시 파일이 무시된다"
    for path in ("backend/data/chaesan.sqlite", "backend/data/raw/files/15089962.csv", "backend/data/cards/x.json"):
        assert subprocess.run(["git", "check-ignore", "-q", path], cwd=root, check=False).returncode == 0, path
