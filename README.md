# 채산 · 한체산 데이터 길라잡이

이 저장소에는 두 가지가 있습니다.

| 이름 | 무엇 | 위치 |
|------|------|------|
| **채산** | 한국체육산업개발(한체산)의 개방 공공데이터와 공개 기록을 근거로, 시민의 질문에 **출처와 함께** 답하는 AI 안내 서비스(**비공식**) | 서버 `backend/app/chaesan/`, 화면 `frontend/` |

> "채산"은 참가자가 붙인 가칭이며 기관의 공식 서비스가 아닙니다. 공모전: 2026 KSPO&Co 공공데이터 활용 경진대회.

## 채산이 하는 일

시민이 "테니스장은 몇 월에 붐벼?", "올림픽공원은 언제부터 이 회사가 관리했어?"처럼 말로 물으면, 한체산 개방 데이터와 공개 기록에서 근거를 찾아 답합니다. 데이터가 오래됐더라도 "언제 자료인지"를 답에 함께 보여 주는 **데이터 길라잡이**입니다.

- **숫자·날짜·판정은 코드가 계산**하고, LLM은 질문 해석·자료 선택·설명만 맡습니다.
- 모든 답에 **데이터 이름·번호·실제 기간·주의점**을 붙입니다. 근거가 없으면 추측하지 않고 "모른다"고 답합니다.
- 답하지 못한 질문은 **주제 요약만** 기록해 기관의 추가 개방 검토 자료로 씁니다(질문 원문은 저장하지 않음).

질문은 다섯 갈래입니다.

| 갈래 | 질문 예 | 근거 | 답하는 방식 |
|------|---------|------|-------------|
| 역사 | 올림픽공원 장미축제는 언제부터 기사가 났어? | 보도자료, 언론보도현황, 기관 연혁 | 문서 검색 후 인용 |
| 시설·이용 | 잔디마당은 언제 개방해? | 자주 묻는 질문, 잔디시설정보 | 문서 검색 후 인용 |
| 소식 | 요즘 공원에 무슨 행사가 있어? | 올팍소식, 핫뉴스, 보도자료 | 날짜순 검색 |
| 기관 정보 | 이 기관은 어떤 사업을 공개하고 있어? | 사전정보공표, 사업실명제, 정보목록 | 목록 검색 후 링크 안내 |
| 데이터 | 테니스장은 몇 월에 이용자가 가장 많았어? | 파일데이터 30종 | 코드가 계산 |

## 진행 상황

| 단계 | 내용 | 상태 |
|------|------|------|
| A | 조사(저장소·재사용 모듈·모델 확인) | 완료 |
| B | 파일 30종 SQLite 적재, 입출차 시간대 집계 표 | 완료 |
| C | 데이터 카드(실제 기간·주의점·등급)와 주제 묶음 | 완료(검토 대기) |
| D | 문서 색인(FTS5)과 오타·줄임말 보정 | 완료(검토 대기) |
| E | 답변 엔진(계획 → 검사·실행 → 설명 → 숫자 대조) | 완료(검토 대기) |
| F | 개발용 질문 20개로 검사 | 측정 완료(자료 선택 95%, 3회) |
| G | 화면과 배포(Cloudflare Workers/D1) | 화면 재구성 완료(H1~H2), 예시 답·배포 대기 |

**아직 되지 않는 것(숨기지 않습니다):** 서비스 배포(Cloudflare)는 아직 없고(로컬 서버 `http://localhost:8100/`에서 화면이 열립니다), 개발용 질문 20개 검사(F단계) 결과는 자체 제작 문항이라 시험용 60문항보다 쉬울 수 있습니다. `POST /api/chaesan/ask`는 로컬에서만 동작합니다. 오픈API 28종은 연결 전이고, 기상청·서울 도시데이터·특일 정보도 2단계 계획입니다. 한글로 쓴 수("삼십 명")는 숫자 대조가 읽지 못해, 프롬프트로 아라비아 숫자만 쓰게 하고 답변 단계에서 따로 거릅니다.

## 구조

```
frontend/               # 화면: 빌드 없는 HTML·CSS·JS 모듈(로컬·서비스 공통). 설명은 frontend/README.md
├── index.html  css/  js/  img/  data/examples.json  tests/   # tests는 npm test(node --test)
backend/app/chaesan/
├── core/        # 로컬·서비스 공통. 표준 라이브러리만 사용(Cloudflare Python Workers에서 그대로 돌아야 함)
│   ├── config.py   ports.py     # 설정값, db·llm·clock 어댑터 인터페이스
│   ├── catalog.py               # 데이터 카드 읽기·검증
│   ├── search.py                # 문서 키워드 검색(FTS5 + LIKE + 등급 가중치)
│   ├── correct.py               # 오타·줄임말 보정(약칭 → 자모 거리 → 확신도)
│   ├── planner.py engine.py     # 후보 데이터 선정·계획 검증, 답변 엔진(질문당 LLM 최대 3번)
│   └── demand.py                # 개방 수요 기록(질문 원문 저장 안 함)
│   ├── guard.py                 # 프롬프트 인젝션 방어, LLM 출력 검사
│   ├── when.py                  # "지난달·7월·주말" 같은 기간 해석(과거 기준)
│   └── sql_guard.py  answer.py  typo.py   # SQL 검사, 답 속 숫자 대조·배지, 자모 풀기·편집 거리
├── local/       # 로컬 전용: sqlite 어댑터, Ollama, 시계, 수요 기록 파일, FastAPI(app.py)
└── ingest/      # 로컬 전용: 원본 CSV → SQLite
    ├── specs.py convert.py load.py aggregate.py   # 적재
    ├── card_meta.py cards.py                      # 데이터 카드(58개: 적재 31 + 미연결 API 27)
    └── docs.py aliases.py                         # 문서 색인(3,635건), 오타 보정용 어휘 사전
backend/data/    # 원본·DB는 git에 올리지 않음(gitignore)
```

## 실행

원본 데이터(`backend/data/raw/files/<번호>.csv` 30종)는 **저장소에 없습니다.** [공공데이터포털](https://www.data.go.kr)의 한국체육산업개발 파일데이터를 직접 내려받아 넣어야 합니다(번호 목록은 `backend/app/chaesan/ingest/specs.py`).

```bash
cd backend
uv sync
uv run python -m app.chaesan.ingest.load     # data/chaesan.sqlite 생성(약 2초). 파일 형식이 명세와 다르면 멈춘다
uv run python -m app.chaesan.ingest.docs     # 문서 색인(docs, docs_fts)
uv run python -m app.chaesan.ingest.aliases  # 오타 보정용 사전 app/chaesan/aliases.json
uv run python -m app.chaesan.ingest.cards    # data/cards/*.json 생성(DB에서 기간·행 수를 직접 계산)
uv run pytest                                # 전체 테스트(린트·타입 검사 포함)
uv run uvicorn app.chaesan.local.app:app --port 8100 --no-proxy-headers   # 채산 API(Ollama와 gemma4:26b 필요)
uv run ruff check && uv run mypy             # 코드 양식·타입 검사(채산 코드만)
```

## 사용 기록과 개인정보

- 서버는 요청마다 **원문이 없는** 기록만 남깁니다: 시각, 처리 결과, 질문 갈래, 걸린 시간, LLM 호출·토큰 수, 사용한 데이터 번호, 질문 글자 수.
- **질문·답변 글, IP 원문은 저장하지 않습니다.** 반복 질문·사용자 수는 하루마다 바뀌는 가명 값으로만 셉니다.
- 서비스에서는 답을 만드는 동안 질문이 Cloudflare Workers AI(해외 서버 포함)로 전송됩니다. 자세한 내용은 화면의 [개인정보 안내](frontend/privacy.html)에 적었습니다.
- 로그는 `backend/data/logs/usage.jsonl`에 30일 보관(git 제외). 요약: `cd backend && uv run python -m app.chaesan.local.usage_report --days 7`

## 안전 원칙

- 질문·데이터 속 문장은 **지시가 아니라 데이터**로만 다룹니다(`core/guard.py`: 정제 → 탐지 → 격리 → 출력 검사).
- LLM이 쓴 SQL은 믿지 않습니다: SELECT만, 허용한 표만, 행 수 상한을 코드가 강제합니다(`sql_guard`, 작성 중).
- API 키·토큰은 코드와 git에 두지 않습니다(`.env`는 gitignore). 테스트가 커밋된 파일의 비밀값·개인 식별 정보를 검사합니다.
- 원본 데이터와 DB 파일은 커밋하지 않습니다.

## 데이터 출처와 이용 조건

- 한국체육산업개발 개방 파일데이터: 공공데이터포털(출처 표기). 이용허락범위는 데이터마다 다를 수 있어 각 상세 페이지를 확인하세요.
- `15160326` 비정형데이터_생태갤러리: **공공누리 4유형(변경금지)**. 사진은 가공·재배포하지 않고 파일 목록만 사용합니다.
- 연혁은 기관 누리집(2026-11-28 확인)의 공개 페이지를 사람이 저장한 것을 읽습니다. 자동 수집 코드는 만들지 않았습니다.

## 작업 문서

- [`CLAUDE.md`](CLAUDE.md): 이 브랜치(`feat/chaesan`)의 작업 규칙·설계 결정·일정(AI 코딩 도구용 지침).
