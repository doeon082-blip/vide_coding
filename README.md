# 전국 축제 정보 & 로컬 AI 큐레이션

공공데이터포털 '전국문화축제표준데이터'를 SQLite에 적재하고, 웹에서 10개씩 페이지네이션으로 보며
로컬 Ollama(Qwen 4B)로 축제 한 줄 요약을 받는 풀스택 MVP. 모두 무료 도구(FastAPI, SQLite, Ollama, React)만 사용합니다.

## 준비
- Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+, [Ollama](https://ollama.com) (`ollama pull qwen3.5:4b`)
- 공공데이터포털 무료 API 키

## 실행
```bash
# 1) 백엔드
cd backend
cp .env.example .env          # PUBLIC_DATA_API_KEY 등 입력
uv sync
uv run python -m app.collector            # 전체 축제 수집 → backend/festivals.db (재실행해도 중복 없음)
uv run uvicorn app.main:app --port 8000

# 2) 프론트엔드
cd frontend
cp .env.example .env          # VITE_API_BASE_URL
npm install
npm run dev                   # http://localhost:5173
npm run build                 # 배포용 빌드 (dist/)
```

## API
- `GET /api/festivals?page=1&size=10` — 전체 개수 + 해당 페이지 목록 (`status`: 진행중/예정/완료)
- `POST /api/festivals/{id}/summarize` — Ollama 한 줄 요약 생성 후 DB 캐싱

모든 포트·URL·모델명은 `.env`로 분리되어 있어 배포 시 환경변수만 교체하면 됩니다.
