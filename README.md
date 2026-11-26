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
| 배포 | Netlify(프론트, `netlify.toml`) + 로컬/자체 호스팅 백엔드 |

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
│   ├── photos.ts          # Wikimedia Commons 사진 조회(무료) + picsum 대체
│   └── security.ts        # 입력 검증·속도 제한·이미지 URL 화이트리스트
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
| GET | `/api/festivals?page=1&size=10` | 전체 개수 + 해당 페이지 목록. `status`는 서버 오늘 날짜 기준 진행중/예정/완료 |
| GET | `/api/festivals/search?q=충장 축제` | **하이브리드 검색**: 철자·부분일치(오타 허용) 점수 + 벡터 유사도 가산 |
| POST | `/api/festivals/{id}/summarize` | Ollama 한 줄 요약 생성 후 메타데이터에 캐싱 (2회째부터 `cached: true`) |
| GET | `/api/festivals/suggest?q=충장추제` | 연관검색어: 하이브리드 랭킹 상위 축제명 (오타 교정 포함) |
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
- 카드 썸네일과 **📷 관련 사진 갤러리**(Wikimedia Commons, 없으면 임의 이미지)
- AI 한 줄 요약(캐싱)
- DaisyUI 테마(기본 cupcake, 다크 모드 시스템 설정이면 dracula 자동 적용), 로딩 스켈레톤, 반응형 레이아웃

## 보안
- API 키는 `backend/.env`에서만 읽고(`.env`는 git 제외), 코드·로그에 남기지 않습니다.
- 검색 입력에서 `<script>`, SQL 인젝션(`' OR 1=1 --`, `DROP TABLE` 등), 제어문자, 100자 초과를 차단하고
  `규정위반: 허용되지 않는 입력입니다`(HTTP 400)를 반환합니다.
- 프론트(`security.ts`)에서도 같은 규칙으로 먼저 검증하고, 8회/10초 초과 요청은 제한하며, 위반 3회 누적 시 30초간 검색을 차단합니다.
- 이미지는 `https` + 허용 호스트(Wikimedia, picsum)만 렌더링합니다.
- CORS는 `CORS_ORIGINS`에 지정한 출처만 허용합니다.

## 배포 (Netlify, 무료)
1. 저장소를 Netlify에 연결하면 `netlify.toml`이 빌드(`frontend`, `npm run build`, `dist`)를 설정합니다.
2. Netlify 사이트 환경변수 `VITE_API_BASE_URL`에 백엔드 공개 주소를 지정합니다.
3. 백엔드의 `CORS_ORIGINS`에 Netlify 주소를 추가합니다.

> ⚠️ AI 요약은 로컬 Ollama가 필요합니다. 백엔드(+Ollama)를 외부에 공개하지 않으면 배포된 프론트에서도 목록은 보이지 않습니다.
> 사진은 Wikimedia Commons에서 파일명에 축제명 단어가 들어간 것만 사용하며, 없으면 [picsum.photos](https://picsum.photos) 임의 이미지로 대체됩니다.

## 참고
- 검색은 `점수 = 철자 점수(0~1) + 벡터 보너스(≤0.4)`입니다. 대표 질의 12개 중 11개가 1순위로 정확히 나왔습니다(`uv run pytest`로 철자 점수 단위 테스트 실행).
- MIT License
