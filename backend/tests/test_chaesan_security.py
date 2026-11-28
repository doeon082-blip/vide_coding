"""OWASP 점검(2026-11-28)에서 나온 문제의 회귀 테스트: SQL 실행 시간 제한, IP 구분 값, 화면 파일 공개 범위, 기록기 예외."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.chaesan.core.catalog import Catalog
from app.chaesan.core.correct import Vocab
from app.chaesan.core.engine import Engine
from app.chaesan.local.app import ASK_PATH, PUBLIC_ENTRIES, create_app
from app.chaesan.local.db import SqliteDB
from app.chaesan.local.ratelimit import _bucket_ip, client_ip
from tests.test_chaesan_api import UNKNOWN, WEB, Clock, FakeLLM, NoDB

# --------------------------------------------------------------------------- A06/A10: 무거운 SQL은 시간이 지나면 끊는다


# 4,000행끼리 3번 교차 조인: 640억 행을 세야 해서 제한이 없으면 사실상 끝나지 않는다(검사기를 거치지 않고 DB 계층만 시험)
HEAVY = "SELECT count(*) FROM t x CROSS JOIN t y CROSS JOIN t z"


def _db_with_rows(tmp_path: Path, rows: int) -> Path:
    path = tmp_path / "big.sqlite"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE t (a INTEGER, b TEXT)")
        con.executemany("INSERT INTO t VALUES (?, ?)", [(i % 50, "x") for i in range(rows)])
    return path


def test_heavy_self_join_is_interrupted_instead_of_hogging_the_database(tmp_path: Path) -> None:
    """같은 큰 표를 서로 조인하는 SQL(검사기가 허용하는 모양)은 계산량이 폭발한다. 제한 시간이 지나면 SQLite가 중단해야 한다."""
    db = SqliteDB(_db_with_rows(tmp_path, 4000), timeout_s=0.3)
    started = time.monotonic()
    with pytest.raises(sqlite3.OperationalError, match="interrupted"):
        asyncio.run(db.query(HEAVY))
    assert time.monotonic() - started < 3  # 제한(0.3초)을 크게 넘겨 매달리지 않는다


def test_normal_queries_and_later_queries_still_work_after_an_interrupt(tmp_path: Path) -> None:
    db = SqliteDB(_db_with_rows(tmp_path, 4000), timeout_s=0.3)

    async def scenario() -> Any:
        with pytest.raises(sqlite3.OperationalError):
            await db.query(HEAVY)
        return await db.query("SELECT count(*) AS n FROM t")  # 중단 뒤에도 연결과 시간 제한이 정상이다

    res = asyncio.run(scenario())
    assert res.rows == [{"n": 4000}]


def test_engine_turns_a_database_timeout_into_a_clean_answer_not_a_crash() -> None:
    """DB가 시간 초과로 실패해도 엔진은 서버 오류가 아니라 '조회 실패' 경로(재계획·모른다)로 처리한다."""
    from app.chaesan.core.ports import QueryResult

    class SlowDB:
        async def query(self, sql: str, params: tuple[Any, ...] = ()) -> QueryResult:
            raise sqlite3.OperationalError("interrupted")

    engine = Engine(db=SlowDB(), llm=FakeLLM(UNKNOWN), clock=Clock(), catalog=Catalog({}, {}), vocab=Vocab({}, {}))
    card = asyncio.run(engine.ask("올림픽공원 주차장 시간대별"))
    assert card.status in {"unknown", "error"} and "interrupted" not in card.answer


# --------------------------------------------------------------------------- A06: 요청 제한의 사용자 구분 값


def _request(peer: str, header: str | None = None) -> Request:
    headers = [(b"cf-connecting-ip", header.encode())] if header is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234), "method": "GET", "path": "/"})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("203.0.113.7", "203.0.113.7"),
        (" 203.0.113.7 ", "203.0.113.7"),
        ("2001:db8:1:2:aaaa:bbbb:cccc:dddd", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:1111:2222:3333:4444", "2001:db8:1:2::/64"),  # 같은 /64의 다른 주소 → 같은 사용자
        ("::ffff:203.0.113.7", "203.0.113.7"),
        ("not-an-ip", None),
        ("203.0.113.7; DROP TABLE", None),
        ("1" * 500, None),
        ("", None),
    ],
)
def test_ip_bucket_values(raw: str, expected: str | None) -> None:
    assert _bucket_ip(raw) == expected


def test_rotating_ipv6_addresses_or_garbage_headers_cannot_evade_the_limit_key() -> None:
    keys = {client_ip(_request("127.0.0.1", f"2001:db8:9:9:{i:x}::1")) for i in range(1, 200)}
    assert keys == {"2001:db8:9:9::/64"}  # 같은 /64 안에서 주소를 바꿔도 한 사람으로 센다
    garbage = {client_ip(_request("127.0.0.1", f"garbage-{i}")) for i in range(50)}
    assert garbage == {"127.0.0.1"}  # 모양이 틀린 헤더는 버린다(요청마다 다른 키로 메모리를 키울 수 없다)
    assert client_ip(_request("198.51.100.4", "203.0.113.99")) == "198.51.100.4"  # 외부 연결의 헤더는 여전히 무시


# --------------------------------------------------------------------------- A02: 화면 파일 공개 범위


def test_public_allowlist_covers_exactly_what_the_page_needs() -> None:
    """허용 목록이 실제 화면 파일과 맞아야 한다: 빠지면 화면이 깨지고, 넘치면 불필요한 파일이 나간다."""
    top_level = {p.name for p in WEB.iterdir() if not p.name.startswith(".")}
    needed = {"index.html", "privacy.html", "favicon.svg", "css", "js", "img", "data"}
    assert needed == PUBLIC_ENTRIES
    assert needed <= top_level
    with TestClient(create_app(None, rate_limit=False)) as c:
        for ok in ("/", "/privacy.html", "/favicon.svg", "/css/base.css", "/js/main.js", "/img/mark.svg", "/data/examples.json"):
            assert c.get(ok).status_code == 200, ok


# --------------------------------------------------------------------------- A10: 기록기가 어떤 예외를 내도 응답은 정상


def test_a_failing_usage_sink_never_turns_a_good_answer_into_a_500() -> None:
    class Exploding:
        def record(self, event: dict[str, Any]) -> None:
            raise RuntimeError("boom with internal detail")

    engine = Engine(db=NoDB(), llm=FakeLLM(UNKNOWN), clock=Clock(), catalog=Catalog({}, {}), vocab=Vocab({}, {}))
    with TestClient(create_app(engine, rate_limit=False, usage=Exploding())) as c:
        r = c.post(ASK_PATH, json={"question": "안녕"})
    assert r.status_code == 200 and "boom" not in r.text
