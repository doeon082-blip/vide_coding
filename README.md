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
uv run uvicorn app.main:app --port 8000 --no-proxy-headers   # 요청 제한이 위조 헤더에 속지 않도록

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
방어는 **프론트(빠른 차단) → 서버(최종 방어)** 두 겹이고, 외부로 공개되는 건 이 백엔드뿐입니다.

| 영역 | 방어 | 위치 |
|------|------|------|
| API 키 | `backend/.env`에서만 읽고 git 제외. httpx 로그 레벨을 올려 URL의 `serviceKey`가 로그에 남지 않음. 사진 서비스 오류 로그에도 URL을 남기지 않음 | `collector.py`, `logging_config.py`, `photo_service.py` |
| 입력 검증 | `<script>`·SQL 인젝션(`' OR 1=1 --`, `DROP TABLE`)·템플릿 구문(`{{`, `${`)·제어문자·100자 초과 차단 → `규정위반: 허용되지 않는 입력입니다`(HTTP 400). 유니코드 NFC 정규화·공백 정리 후 검사 | 프론트 `security.ts` + 서버 `main.py` |
| 요청 제한 | 클라이언트별 슬라이딩 윈도우: AI 요약 10회/분, AI 큐레이터·교정 12회/분, 검색 40회/분, 연관검색어 90회/분, 사진 240회/분, 그 외 120회/분 → 429. 프론트도 10초 8회 초과 제한 + 위반 3회 누적 시 30초 차단 | `ratelimit.py`, `security.ts` |
| IP 위조 방지 | 요청 제한의 클라이언트 IP는 **직접 연결 상대**를 쓰고, 같은 PC의 터널(cloudflared)에서 온 경우에만 Cloudflare가 넣는 `CF-Connecting-IP`를 신뢰. `X-Forwarded-For`는 무시. 그래서 uvicorn을 `--no-proxy-headers`로 실행 | `ratelimit.py` |
| 요청 크기 | 본문 8KB 초과는 파싱 전에 413, 질문은 200자 제한 | `ratelimit.py`, `schemas.py` |
| 공격면 축소 | `/docs`, `/openapi.json`은 기본 비공개(`ENABLE_DOCS=on`일 때만 공개), CORS는 `CORS_ORIGINS` 허용 출처만 | `main.py` |
| XSS | React가 모든 텍스트를 이스케이프하며 `dangerouslySetInnerHTML`을 쓰지 않음. 외부 이미지는 `https` + `tong.visitkorea.or.kr`만 렌더링(백엔드·프론트 이중 검사), 외부 링크는 `rel="noopener noreferrer"` | `photo_service.py`, `security.ts` |
| 프롬프트 주입 | 사용자 질문과 축제 데이터(외부 공개 데이터)를 LLM 프롬프트에서 '데이터이며 지시문이 아님'으로 구분하고, 후보에 있는 값만 교정 결과로 인정. AI 출력은 텍스트로만 표시하며 AI에게 도구·파일·네트워크 권한이 없음 | `ai_service.py` |

한계(알고 쓰세요): 입력 검증은 패턴 기반이라 완전하지 않고, 요청 제한은 메모리 기반(재시작 시 초기화·단일 프로세스)입니다. 계정/인증은 없습니다(공개 조회 서비스). Quick Tunnel로 공개하면 누구나 호출할 수 있으니 쓰지 않을 때는 터널을 끄세요.

## 배포 (전부 무료)
구성: **프론트 = GitHub Pages**, **백엔드 + Ollama = 내 PC**, 둘을 **Cloudflare Quick Tunnel**로 연결합니다.
(Ollama 모델을 돌릴 수 있는 무료 클라우드가 없어 백엔드는 PC에 둡니다.)

1. **프론트 (자동)**: `main`에 `frontend/**` 변경을 푸시하면 `.github/workflows/deploy-pages.yml`이 빌드·배포합니다.
   - 저장소 Settings → Pages → **Source: GitHub Actions** 로 한 번만 설정 (무료 플랜은 저장소가 public이어야 함)
   - 주소: `https://<계정>.github.io/<저장소명>/`
2. **백엔드 + 터널 (PC에서 실행)**
   ```bash
   cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
   cloudflared tunnel --url http://127.0.0.1:8000     # 출력되는 https://xxxx.trycloudflare.com 주소 확인
   ```
   - `cloudflared`: `winget install Cloudflare.cloudflared`
   - 백엔드 `CORS_ORIGINS`에 Pages 주소(`https://<계정>.github.io`)를 포함
3. **주소 연결**: 터널 주소는 실행할 때마다 바뀌므로 `frontend/public/config.json`의 `apiBaseUrl`을 새 주소로 바꿔 푸시하면 재배포됩니다. (재빌드 시 코드 수정 불필요)

서버는 클라이언트(IP)별 요청 제한이 있습니다: AI 요약 10회/분, AI 큐레이터·교정 12회/분, 검색 40회/분, 연관검색어 90회/분, 그 외 120회/분 (`RATE_LIMIT=off`로 끌 수 있음).

> ⚠️ PC와 터널이 꺼져 있으면 배포된 화면에서 목록이 보이지 않습니다. AI 요약은 로컬 Ollama가 필요합니다.
> 사진은 한국관광공사 TourAPI(같은 공공데이터포털 키, '국문 관광정보 서비스' 활용신청 필요)에서 가져옵니다. 축제 사진이 없으면 같은 지역 관광지 사진을 `○○ 지역` 배지와 함께 보여주고, 그것도 없으면 테마 색 타일을 보여줍니다. 일일 호출 한도가 있어 결과는 `backend/cache/photos.json`에 캐싱합니다.

## 라이선스 · 출처

이 저장소의 **코드**는 MIT입니다([LICENSE](LICENSE)). 아래 데이터·모델·라이브러리는 각자의 조건을 따릅니다.

### 데이터 / API
| 대상 | 조건 | 이 프로젝트에서의 처리 |
|------|------|------------------------|
| [전국문화축제표준데이터(15013104)](https://www.data.go.kr/data/15013104/standard.do) | 공공데이터포털 메타데이터상 이용허락범위 **제한 없음** | 출처 표기(푸터). 제공기관·파일별로 다를 수 있어 상세 페이지 확인 권장 |
| 한국관광공사 국문 관광정보 서비스(TourAPI) 사진 | 공공데이터포털 안내: 저작권 문제가 없는 자료만 제공하며 **공공누리 1유형·3유형** 이미지. 피사체 명예훼손·인격권 침해 용도, 기업 CI/BI 사용 금지 | API가 주는 `cpyrhtDivCd`를 화면에 표기하고 출처 `한국관광공사`를 표시 |

공공누리 유형 ([공식 안내](https://www.mcst.go.kr/kor/s_open/kogl/koglType.jsp)):
- **제1유형(출처표시)**: 상업적·비상업적 이용 가능, 변형 가능
- **제3유형(출처표시+변경금지)**: 상업적·비상업적 이용 가능, **변형(2차적 저작물) 금지**
- 모든 유형: 출처를 알아보기 쉽게 표시, 온라인이면 링크 제공

그래서 제3유형 사진은 **자르지 않고 원본 비율**로 표시하고(라이트박스는 항상 원본 비율), 사진 확대 화면에 유형과 출처를 표기합니다. 제2·4유형(상업적 이용 금지)이 내려오면 표기만 하며, **상업적으로 쓸 경우 유형을 먼저 확인**해야 합니다.

### AI 모델 (로컬 Ollama, 내 PC에서만 실행)
| 모델 | 라이선스 |
|------|----------|
| `qwen3.5:4b` (요약·교정·큐레이터) | Apache 2.0 (`ollama show --license`로 확인) |
| `qwen3-embedding:4b` (임베딩) | Apache 2.0 (Qwen 공식 모델 카드/GGUF 저장소 기준, Ollama 쪽 라이선스 출력은 비어 있음) |

### 주요 라이브러리
FastAPI(MIT) · Pydantic(MIT) · Starlette/Uvicorn/httpx/python-dotenv(BSD-3) · ChromaDB(Apache-2.0) ·
React/Vite/Tailwind CSS/DaisyUI(MIT) · Lucide(ISC) · TypeScript(Apache-2.0) · cloudflared(Apache-2.0, 배포 시)

> 법률 자문이 아닙니다. 상업 서비스로 운영하거나 사진을 재배포할 계획이면 각 원문 약관을 직접 확인하세요.

## 참고
- 검색은 `점수 = 철자 점수(0~1) + 벡터 보너스(≤0.4)`입니다. 대표 질의 12개 중 11개가 1순위로 정확히 나왔습니다(`uv run pytest`로 철자 점수 단위 테스트 실행).
- MIT License
