from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ratelimit import RateLimitMiddleware

app = FastAPI()
app.add_middleware(RateLimitMiddleware)


@app.post("/api/festivals/{fid}/summarize")
def summarize(fid: str) -> dict[str, str]:
    return {"id": fid}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def test_summarize_is_limited_per_client_and_health_is_exempt():
    c = TestClient(app)
    codes = [c.post("/api/festivals/x/summarize", headers={"cf-connecting-ip": "1.1.1.1"}).status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]
    # 다른 클라이언트는 영향 없음
    assert c.post("/api/festivals/x/summarize", headers={"cf-connecting-ip": "2.2.2.2"}).status_code == 200
    assert all(c.get("/api/health").status_code == 200 for _ in range(200))
