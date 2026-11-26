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

### macOS / Linux에서 실행
코드는 `pathlib`·표준 라이브러리만 쓰고 Windows 전용 코드는 없어서 그대로 동작합니다(실제 Mac에서 돌려 보지는 못했습니다). 다른 점은 설치 명령뿐입니다.
```bash
# 도구 설치 (macOS, Homebrew)
brew install uv node ollama
brew install cloudflared        # 배포(터널)할 때만
ollama serve &                  # 또는 Ollama 앱 실행
ollama pull qwen3.5:4b && ollama pull qwen3-embedding:4b

git clone https://github.com/doeon082-blip/vide_coding.git && cd vide_coding
cd backend
cp .env.example .env            # PUBLIC_DATA_API_KEY 입력 (.env는 저장소에 없으므로 기기마다 새로 만듦)
uv sync && uv run python -m app.collector      # 벡터 DB(chroma_db)도 저장소에 없으므로 기기마다 다시 수집(약 1분)
uv run uvicorn app.main:app --port 8000 --no-proxy-headers
# 다른 터미널
cd frontend && cp .env.example .env && npm install && npm run dev
```
- Apple Silicon은 Ollama가 Metal(GPU)을 써서 Windows CPU보다 빠른 편입니다.
- Linux는 `brew` 대신 각 배포판 패키지 매니저/공식 설치 스크립트로 `uv`, `node`, `ollama`, `cloudflared`를 설치하면 됩니다.

## API
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/festivals?page=1&size=10&status=진행중` | 전체 개수 + 해당 페이지 목록. `status`(진행중/예정/완료, 생략=전체)는 서버 오늘 날짜 기준이며 `counts`로 상태별 건수 제공. 진행중=곧 끝나는 순, 예정=곧 시작하는 순, 완료=최근 종료 순 |
| GET | `/api/festivals/search?q=충장 축제` | **하이브리드 검색**: 철자·부분일치(오타 허용) 점수 + 벡터 유사도 가산 |
| POST | `/api/festivals/{id}/summarize` | Ollama 한 줄 요약 생성 후 메타데이터에 캐싱 (2회째부터 `cached: true`) |
| GET | `/api/festivals/suggest?q=충장추제` | 연관검색어: 하이브리드 랭킹 상위 축제명 (오타 교정 포함) |
| GET | `/api/festivals/{id}/photos` | **한국관광공사 TourAPI** 사진: 축제 사진 → 없으면 같은 시·군 관광지 사진(`kind: region`). 디스크 캐시 |
| GET | `/api/ai/correct?q=산천어추제` | **로컬 AI 오타 교정**: 후보 축제명 중 의도한 것을 골라 "혹시 ○○?" 제안 |
| POST | `/api/chat` | **RAG 챗봇**: 의도 파악 → 근거 검색 → AI는 추천 이유만 작성 → 사실 대조 검증. 축제명·일정·장소·상태는 항상 DB 값 |
| POST | `/api/ai/ask` | 단발성 AI 큐레이터(레거시, 화면에서는 챗봇으로 대체) |
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
- **🧚 축제 요정 챗봇(RAG)**: "단풍 보고 싶어", "이번 주말에 갈 만한 축제"처럼 물으면 데이터에서 근거를 찾아 추천(아래 상세)
- **진행중 / 예정 / 완료 탭**(건수 표시)
- **로컬 AI 활용**: ① 한 줄 요약(캐싱) ② 오타 교정 "혹시 ○○을(를) 찾으셨나요?" ③ 축제 요정 챗봇(근거 기반 추천)
- DaisyUI 테마(기본 cupcake, 다크 모드 시스템 설정이면 dracula 자동 적용), 로딩 스켈레톤, 반응형 레이아웃

## 🧚 축제 요정 챗봇 (RAG, `backend/app/chatbot.py`)
핵심 원칙: **사실은 DB가, 말투는 AI가.** AI가 틀리거나 지어내도 사용자에게 나가지 않게 설계했습니다.

```
질문 → ① 의도 파악(규칙) → ② 근거 검색 → (후보 0건이면 AI 호출 없이 "없어요")
     → ③ AI가 '추천 이유' 한 문장만 작성 → ④ 사실 대조 검증 → ⑤ 서버가 답변 조립
```
| 단계 | 내용 |
|------|------|
| ① 의도 파악 | 주제(단풍·벚꽃·야경·먹거리…), 시기(이번 주말/12월/가을…), 지역, "지난 것 포함" 여부를 **규칙 기반**으로 추출(LLM 오해석 없음). 후속 질문("제주는?", "더 보여줘")은 이전 사용자 질문을 이어받음 |
| ② 근거 검색 | 단어가 축제명·소개문에 **실제로 있는** 축제만 후보. 어떤 단어가 어디서 맞았는지(근거)를 화면에 표시. 한 글자 키워드(`꽃`→`불꽃`)·확장어만 맞은 약한 후보·취소된 행사는 제외 |
| ③ 생성 | LLM은 후보별 추천 이유만 작성(JSON 스키마 고정). 인사말은 고정 템플릿 |
| ④ 검증 | 이유 문장의 **숫자가 원문에 없거나**, **다른 축제명**·원문에 없는 가격/주차/예약 같은 정보가 있거나, 근거 없는 단어가 많으면 **AI 문장을 버리고** 근거 기반 템플릿으로 대체 |
| ⑤ 조립 | 축제명·날짜·장소·상태는 AI가 쓰지 않고 DB 값을 그대로 사용 |

정직하게 답하는 경우:
- **지금 갈 수 있는 게 없을 때**: 예) 오늘(2026-11-26) 기준 단풍 축제는 7건 모두 "완료" → "지금 열리거나 예정된 단풍 축제는 데이터에 없어요"라고 말하고, 끝난 축제는 **"지난 개최(참고용)"** 배지로만 보여줌. 내년 일정은 단정하지 않음
- **데이터에 없는 정보**(입장료·주차·예약·교통·날씨·운영시간·연락처·숙박)를 물으면 AI가 아니라 서버가 "데이터에 없어요, 공식 홈페이지를 확인하세요"라고 안내
- **없는 주제**는 지어내지 않고 "찾지 못했어요"

검증: `uv run pytest`(챗봇 테스트에 *가짜 LLM이 거짓말하는 상황* 포함), 실전 평가 `uv run python -m tests.live_eval_chatbot`
(실제 데이터+실제 Qwen, 질문 20개 → **추천 49건 중 사실 위반 0건**, AI 문장 24건 채택/25건 템플릿 대체).
한계: 4B 모델이라 AI 문장이 가끔 어색하고(문법), 검증이 엄격해 템플릿 문장이 자주 쓰입니다. 데이터에 없는 정보는 알 수 없고, 검색 품질은 데이터 소개문의 충실도에 좌우됩니다.

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
| 프롬프트 인젝션 | 4겹 방어(아래 상세): 정제 → 탐지/차단 → 데이터 격리 → 출력 검증. AI에게 도구·파일·네트워크 권한 없음 | `prompt_injection_defense.py`, `ai_service.py` |
| 챗봇 입력 | 질문 200자 제한, 대화 기록은 **사용자 발화만** 사용(assistant 발화 위조 무시)하고 기록 속 인젝션도 차단, 분당 20회 제한 | `main.py`, `chatbot.py` |
| 응답 헤더 | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `CSP: default-src 'none'`, `Cache-Control: no-store` | `main.py` |
| 프론트 CSP | 빌드 결과에 CSP 메타 적용(스크립트/스타일은 같은 출처만, 이미지는 한국관광공사 도메인만) | `vite.config.ts` |
| 오류 정보 노출 | AI 오류는 일반 메시지만 반환(내부 주소·모델명·예외 상세는 서버 로그에만) | `ai_service.py` |
| 외부 API 한도 보호 | TourAPI 하루 호출 예산(기본 800) 소진 시 사진 호출 중단, 결과 디스크 캐시 | `photo_service.py` |
| 입력 위장 | 검색어도 NFKC 정규화·제로폭 문자 제거 후 검사(전각 `＜ｓｃｒｉｐｔ＞` 우회 차단) | `main.py`, `security.ts` |

한계(알고 쓰세요): 입력 검증은 패턴 기반이라 완전하지 않고, 요청 제한은 메모리 기반(재시작 시 초기화·단일 프로세스)입니다. 계정/인증은 없습니다(공개 조회 서비스). Quick Tunnel로 공개하면 누구나 호출할 수 있으니 쓰지 않을 때는 터널을 끄세요.

### 프롬프트 인젝션 방어 (`backend/app/prompt_injection_defense.py`)
로컬 LLM에 들어가는 텍스트에는 ① 사용자 질문(직접 인젝션)과 ② 공공데이터의 축제명·소개문(간접 인젝션: 데이터에 숨은 지시문)이 있습니다.

| 단계 | 하는 일 |
|------|---------|
| A. 정제 | NFKC 정규화(전각·위장 해제), 제로폭/제어문자 제거, 길이 제한, 채팅 템플릿 토큰·역할 접두어(`system:`)·가짜 구분자 제거 |
| B. 탐지 | 한/영 패턴(지시 무시, 프롬프트 유출, 역할 변경, 탈옥, 템플릿 위조, 출력 강요) + 띄어쓰기·전각·제로폭 위장 탐지. **사용자 질문은 탐지 시 LLM 호출 전에 400 차단**, **데이터는 의심 문장만 삭제하고 진행** |
| C. 격리 | 데이터를 1회용 난수 구분자(`<<<DATA nonce>>>`)로 감싸고, 규칙은 `system` 메시지에 분리, 시스템 프롬프트에 카나리 토큰 삽입 |
| D. 출력 검증 | 카나리·규칙 문구 유출, 템플릿 토큰 → 결과 폐기. 링크·HTML·코드블록 제거. 오타 교정은 **후보 목록에 있는 값만** 인정. 검증 통과한 요약만 DB에 캐싱 |

검증:
- `uv run pytest` — 공격 25종 탐지·차단, 정상 문장 13종 오탐 없음, 정제·격리·출력 검증·`ai_service` 통합 테스트(가짜 LLM) 포함
- 실제 축제 데이터 1,347건(5,388개 필드)에 탐지기를 돌려 **오탐 0건**
- `uv run python -m tests.live_eval_prompt_injection` — 오염된 데이터를 실제 Qwen에 넣어 방어 전/후 비교: **침해 4/6 → 0/6**

한계: 패턴 탐지는 새로운 표현으로 우회될 수 있고, 4B 소형 모델은 지시 구분이 약합니다. 그래서 탐지에만 의존하지 않고 격리·출력 검증·후보 일치 검증·권한 최소화를 함께 둡니다(심층 방어).

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

## 상업적 운영 전 체크리스트
이 저장소의 코드는 MIT라 상업 이용에 제한이 없습니다. 아래는 **데이터·API·인프라** 쪽입니다(법률 자문 아님).

| 항목 | 상태 | 해야 할 일 |
|------|------|------------|
| 축제 표준데이터 | 이용허락범위 "제한 없음" | 출처 표기 유지(푸터) |
| TourAPI 사진 | 공공누리 1·3유형은 상업 이용 가능, **2·4유형은 불가** | 코드가 1·3유형 외 사진은 자동 제외(`ALLOWED_PHOTO_LICENSES`). 3유형은 변형 금지 → 자르지 않고 원본 비율, 사진마다 출처·유형 표기 |
| API 키 한도 | 개발계정 약 1,000건/일 | **상업 서비스는 운영계정(활용사례 등록) 신청** 필요. 키는 공유·재배포 금지(현재 백엔드에만 있고 프론트에 노출되지 않음) |
| 호스팅 | Cloudflare Quick Tunnel은 **테스트·개발 전용**(공식 문서), 주소가 매번 바뀜 | 상업 운영은 고정 도메인 + 정식(Named) 터널 또는 클라우드 서버 |
| AI 모델 | Qwen3.5·Qwen3-Embedding은 Apache 2.0(상업 이용 가능) | 클라우드에서 돌리려면 GPU/메모리 비용 발생(현재의 "무조건 무료"와 충돌) |
| 개인정보 | 검색어 원문은 로그에 남기지 않음(길이·해시만), 로그인·쿠키 없음 | 로그 보관 정책·개인정보처리방침·이용약관 페이지 작성 |
| 서비스 안정성 | 내 PC 의존, 요청 제한은 메모리 기반 | 모니터링, 영구 저장소 기반 레이트리밋, 백업 |

→ **개인 학습·포트폴리오·비영리 데모는 현재 구성으로 문제 없습니다.** 돈을 받거나 광고를 붙이는 상업 서비스라면 운영계정 전환, 정식 호스팅, 약관·개인정보처리방침, 공공데이터포털 이용약관 원문 확인(재판매 조항은 이번 조사에서 원문을 확인하지 못했습니다)이 먼저입니다.

## 참고
- 검색은 `점수 = 철자 점수(0~1) + 벡터 보너스(≤0.4)`입니다. 대표 질의 12개 중 11개가 1순위로 정확히 나왔습니다(`uv run pytest`로 철자 점수 단위 테스트 실행).
- MIT License
