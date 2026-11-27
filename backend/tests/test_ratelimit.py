from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ratelimit import RateLimitMiddleware

app = FastAPI()
app.add_middleware(RateLimitMiddleware)


@app.post("/api/festivals/{fid}/summarize")
def summarize(fid: str) -> dict[str, str]:
    return {"id": fid}


@app.post("/api/echo")
def echo(body: dict) -> dict:
    return body


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def post(c: TestClient, **headers: str) -> int:
    return c.post("/api/festivals/x/summarize", headers=headers).status_code


def test_summarize_is_limited_and_health_is_exempt():
    c = TestClient(app, client=("203.0.113.5", 1111))
    codes = [post(c) for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]
    assert all(c.get("/api/health").status_code == 200 for _ in range(200))


def test_spoofed_headers_from_remote_peer_are_ignored():
    # 외부에서 직접 붙은 요청이 헤더를 바꿔 보내도 같은 버킷으로 집계된다
    c = TestClient(app, client=("198.51.100.7", 2222))
    codes = [post(c, **{"x-forwarded-for": f"10.0.0.{i}", "cf-connecting-ip": f"10.1.0.{i}"}) for i in range(12)]
    assert codes[10:] == [429, 429]


def test_tunnel_peer_uses_cf_connecting_ip():
    # 같은 PC의 터널(cloudflared)을 거친 요청은 실제 방문자 IP로 구분된다
    c = TestClient(app, client=("127.0.0.1", 3333))
    assert [post(c, **{"cf-connecting-ip": "1.1.1.1"}) for _ in range(11)][-1] == 429
    assert post(c, **{"cf-connecting-ip": "2.2.2.2"}) == 200


def test_oversized_body_is_rejected_before_parsing():
    c = TestClient(app, client=("192.0.2.9", 4444))
    assert c.post("/api/echo", json={"q": "가" * 20_000}).status_code == 413
    assert c.post("/api/echo", json={"q": "ok"}).status_code == 200


def test_non_numeric_content_length_is_400_not_500():
    # 길이 헤더가 숫자가 아니면 int() 예외로 500이 나던 문제 (2026-11-28 수정)
    c = TestClient(app, client=("192.0.2.9", 3333))
    r = c.post("/api/echo", content=b"{}", headers={"content-length": "abc", "content-type": "application/json"})
    assert r.status_code == 400
