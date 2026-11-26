# 🎉 전국 축제 정보 & 로컬 AI 큐레이션

공공데이터포털 **전국문화축제표준데이터**(1,372건)를 **ChromaDB 벡터 DB**에 적재하고, 웹에서 10개씩 페이지네이션으로 보며
로컬 **Ollama(Qwen 4B)** 로 축제 한 줄 요약을 받는 풀스택 MVP입니다. 전부 무료 도구만 사용합니다.

## 구성

| 영역 | 기술 |
|------|------|
| Backend | Python 3.12+, [uv](https://docs.astral.sh/uv/), FastAPI, httpx, python-dotenv |
| Vector DB | ChromaDB (`backend/chroma_db`), 임베딩: Ollama `qwen3-embedding:4b` |
| Local AI | Ollama `qwen3.5:4b` (한 줄 요약, DB에 캐싱) |
| Frontend | React 19 + TypeScript + Vite + Tailwind CSS v4 + [DaisyUI](https://daisyui.com)(무료 UI 컴포넌트/테마) + [Lucide](https://lucide.dev)(무료 아이콘) |
| 배포 | GitHub Pages(프론트) + 로컬 백엔드/Ollama + Cloudflare Quick Tunnel (대안: Netlify, `netlify.toml`) |

```
.
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 앱, CORS, API 라우트, 입력 차단
│   │   ├── database.py        # ChromaDB 연결 + Ollama 임베딩 함수
│   │   ├── models.py          # FestivalRecord (SHA-256 고유 id로 중복 방지)
│   │   ├── schemas.py         # 응답 모델 (진행중/예정/완료 계산)
│   │   ├── collector.py       # 공공데이터 전체 수집 + upsert
│   │   ├── ai_service.py      # Ollama 한 줄 요약 + 캐싱
│   │   └── logging_config.py  # 콘솔 + 파일 로그 (backend/logs/app.log)
│   └── .env.example
├── frontend/src/
│   ├── App.tsx            # 목록·검색·연관검색어·페이지네이션
│   ├── FestivalCard.tsx   # 카드(썸네일, 관련 사진 갤러리, AI 요약)
│   ├── photos.ts          # 사진 훅(백엔드 TourAPI 경유)
│   ├── theme.ts           # 축제명 → 테마 색 타일/이모지, 이미지 검색 링크
│   └── security.ts        # 입력 검증·속도 제한·이미지 URL 화이트리스트
├── .github/workflows/deploy-pages.yml   # Pages 자동 배포
├── netlify.toml
└── README.md
```

## 준비
1. Python 3.12+, `uv`, Node.js 20+ 설치
2. [Ollama](https://ollama.com) 설치 후 모델 받기
   ```bash
   ollama pull qwen3.5:4b
   ollama pull qwen3-embedding:4b
   ```
3. 공공데이터포털에서 무료 API 키 발급 (전국문화축제표준데이터)

## 실행
```bash
# 1) 백엔드
cd backend
cp .env.example .env                       # PUBLIC_DATA_API_KEY 입력
uv sync
uv run python -m app.collector             # 전체 수집 → 임베딩 → ChromaDB (약 1분, 재실행해도 중복 없음)
uv run uvicorn app.main:app --port 8000

# 2) 프론트엔드
cd frontend
cp .env.example .env                       # VITE_API_BASE_URL=http://localhost:8000
npm install
npm run dev                                # http://localhost:5173
npm run build                              # 배포용 빌드 (dist/)
```

## API
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/festivals?page=1&size=10&status=진행중` | 전체 개수 + 해당 페이지 목록. `status`(진행중/예정/완료, 생략=전체)는 서버 오늘 날짜 기준이며 `counts`로 상태별 건수 제공. 진행중=곧 끝나는 순, 예정=곧 시작하는 순, 완료=최근 종료 순 |
| GET | `/api/festivals/search?q=충장 축제` | **하이브리드 검색**: 철자·부분일치(오타 허용) 점수 + 벡터 유사도 가산 |
| POST | `/api/festivals/{id}/summarize` | Ollama 한 줄 요약 생성 후 메타데이터에 캐싱 (2회째부터 `cached: true`) |
| GET | `/api/festivals/suggest?q=충장추제` | 연관검색어: 하이브리드 랭킹 상위 축제명 (오타 교정 포함) |
| GET | `/api/festivals/{id}/photos` | **한국관광공사 TourAPI** 사진: 축제 사진 → 없으면 같은 시·군 관광지 사진(`kind: region`). 디스크 캐시 |
| GET | `/api/ai/correct?q=산천어추제` | **로컬 AI 오타 교정**: 후보 축제명 중 의도한 것을 골라 "혹시 ○○?" 제안 |
| POST | `/api/ai/ask` | **로컬 AI 큐레이터(RAG)**: 질문 → 관련 축제 검색 → 검색 결과만 근거로 추천 답변 |
| GET | `/api/health` | 상태 확인 |

## 환경변수 (`backend/.env`)
모든 주소·포트·모델명은 코드에 하드코딩하지 않고 환경변수로 분리했습니다.

`PUBLIC_DATA_API_KEY`, `PUBLIC_DATA_API_URL`, `CHROMA_PERSIST_DIR`, `CHROMA_COLLECTION_NAME`,
`OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_EMBED_MODEL`, `CORS_ORIGINS`, `LOG_LEVEL`, `LOG_DIR`

## 로그
- `backend/logs/app.log` (5MB 로테이션, 3개 보관) + 콘솔에 동시 기록 (`logs/`는 git 제외)
- httpx 요청 로그는 WARNING 이상만 기록 → URL의 `serviceKey`가 로그에 남지 않음

## 주요 기능
- 10개 단위 페이지네이션, 진행중/예정/완료 배지
- 의미 기반 검색 + **오타 시 관련 연관검색어 칩** 제안(클릭하면 바로 검색)
- 카드 커버(실제 사진 또는 축제명 기반 테마 타일), 축제 소개문, **사진 갤러리**(한국관광공사)
- **진행중 / 예정 / 완료 탭**(건수 표시)
- **로컬 AI 활용**: ① 한 줄 요약(캐싱) ② 오타 교정 "혹시 ○○을(를) 찾으셨나요?" ③ AI 큐레이터에게 자연어로 질문(예: "아이랑 가기 좋은 겨울 축제")
- DaisyUI 테마(기본 cupcake, 다크 모드 시스템 설정이면 dracula 자동 적용), 로딩 스켈레톤, 반응형 레이아웃

## 보안
- API 키는 `backend/.env`에서만 읽고(`.env`는 git 제외), 코드·로그에 남기지 않습니다.
- 검색 입력에서 `<script>`, SQL 인젝션(`' OR 1=1 --`, `DROP TABLE` 등), 제어문자, 100자 초과를 차단하고
  `규정위반: 허용되지 않는 입력입니다`(HTTP 400)를 반환합니다.
- 프론트(`security.ts`)에서도 같은 규칙으로 먼저 검증하고, 8회/10초 초과 요청은 제한하며, 위반 3회 누적 시 30초간 검색을 차단합니다.
- 이미지는 `https` + 허용 호스트(한국관광공사 tong.visitkorea.or.kr)만 렌더링합니다.
- CORS는 `CORS_ORIGINS`에 지정한 출처만 허용합니다.

## 배포 (전부 무료)
구성: **프론트 = GitHub Pages**, **백엔드 + Ollama = 내 PC**, 둘을 **Cloudflare Quick Tunnel**로 연결합니다.
(Ollama 모델을 돌릴 수 있는 무료 클라우드가 없어 백엔드는 PC에 둡니다.)

1. **프론트 (자동)**: `main`에 `frontend/**` 변경을 푸시하면 `.github/workflows/deploy-pages.yml`이 빌드·배포합니다.
   - 저장소 Settings → Pages → **Source: GitHub Actions** 로 한 번만 설정 (무료 플랜은 저장소가 public이어야 함)
   - 주소: `https://<계정>.github.io/<저장소명>/`
2. **백엔드 + 터널 (PC에서 실행)**
   ```bash
   cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
   cloudflared tunnel --url http://127.0.0.1:8000     # 출력되는 https://xxxx.trycloudflare.com 주소 확인
   ```
   - `cloudflared`: `winget install Cloudflare.cloudflared`
   - 백엔드 `CORS_ORIGINS`에 Pages 주소(`https://<계정>.github.io`)를 포함
3. **주소 연결**: 터널 주소는 실행할 때마다 바뀌므로 `frontend/public/config.json`의 `apiBaseUrl`을 새 주소로 바꿔 푸시하면 재배포됩니다. (재빌드 시 코드 수정 불필요)

서버는 클라이언트(IP)별 요청 제한이 있습니다: AI 요약 10회/분, AI 큐레이터·교정 12회/분, 검색 40회/분, 연관검색어 90회/분, 그 외 120회/분 (`RATE_LIMIT=off`로 끌 수 있음).

> ⚠️ PC와 터널이 꺼져 있으면 배포된 화면에서 목록이 보이지 않습니다. AI 요약은 로컬 Ollama가 필요합니다.
> 사진은 한국관광공사 TourAPI(같은 공공데이터포털 키, '국문 관광정보 서비스' 활용신청 필요)에서 가져옵니다. 축제 사진이 없으면 같은 지역 관광지 사진을 `○○ 지역` 배지와 함께 보여주고, 그것도 없으면 테마 색 타일을 보여줍니다. 일일 호출 한도가 있어 결과는 `backend/cache/photos.json`에 캐싱합니다.

## 참고
- 검색은 `점수 = 철자 점수(0~1) + 벡터 보너스(≤0.4)`입니다. 대표 질의 12개 중 11개가 1순위로 정확히 나왔습니다(`uv run pytest`로 철자 점수 단위 테스트 실행).
- MIT License
