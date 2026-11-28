"""채산 설정값: 제한값·가중치·허용 표 목록.

비밀값(API 키 등)은 여기에 두지 않는다. 비밀값은 실행 환경(로컬 .env, Workers secret)에서만 읽는다.
"""

from __future__ import annotations

from datetime import timedelta, timezone
from typing import Final

# 한국 표준시. "오늘·지난달" 해석은 항상 KST 기준이다(서버가 UTC여도 답이 같아야 하므로).
KST: Final = timezone(timedelta(hours=9), "KST")

# 질문 입력 길이 상한(글자). 긴 입력은 인젝션 시도이거나 요금만 쓰는 경우가 많다.
MAX_QUESTION_LEN: Final = 200

# 질문 한 번에 LLM을 부르는 최대 횟수: 계획 1 + 재계획 1 + 설명 1.
MAX_LLM_CALLS: Final = 3

# LLM이 쓴 SQL에 강제하는 행 수 상한. 답변 근거 표와 D1 읽기 한도를 함께 지킨다.
SQL_ROW_LIMIT: Final = 50

# 문서 색인(docs)에 들어 있는 출처 = 데이터 카드 번호('history'는 연혁). ingest.docs.SOURCES와 같아야 한다(테스트가 확인).
DOC_SOURCES: Final[frozenset[str]] = frozenset(
    {"15089962", "15137825", "15137824", "15090715", "15143220", "15090257", "15090260", "history"}
)

# 서비스에도 올라가는 집계 표의 열 설명(카드에는 원본 표의 열만 있어서 LLM이 SQL을 쓸 수 있게 따로 적는다)
AGGREGATE_SCHEMAS: Final[dict[str, str]] = {
    "s_parking_hourly": (
        "date TEXT(YYYY-MM-DD), hour INTEGER(0~23), weekday INTEGER(0=월 … 6=일), "
        "is_holiday INTEGER(항상 NULL, 공휴일 자료 미연결), entries INTEGER(그 시간 입차 대수), exits INTEGER(그 시간 출차 대수)"
    )
}

MAX_CANDIDATES: Final = 5  # 계획 LLM에게 보여 주는 후보 데이터 수
EVIDENCE_ROWS_FOR_LLM: Final = 20  # 설명 LLM에게 넘기는 근거 행 수 상한(토큰·비용 보호)
DOC_HITS: Final = 8  # 문서 검색 결과 상한
MAX_ANSWER_CHARS: Final = 300
STALE_DAYS: Final = 365  # 마지막 자료가 이보다 오래되면 '1년 넘게 갱신 안 됨' 배지
PLAN_MAX_TOKENS: Final = 500
ANSWER_MAX_TOKENS: Final = 300
NOTICE: Final = "채산은 한국체육산업개발의 공식 서비스가 아닌 비공식 안내입니다."

# LLM이 쓴 SQL의 길이와 표 참조 개수 상한. 긴 SQL과 여러 표의 교차 조인은 서버를 느리게 만드는 흔한 방법이다.
MAX_SQL_LEN: Final = 2000
MAX_SQL_TABLE_REFS: Final = 4

# 로컬 개발 모델(ollama list로 설치 확인함). 서비스(Workers AI) 모델 이름은 G단계에서 확인 후 넣는다.
LOCAL_MODEL: Final = "gemma4:26b"

# 데이터 등급별 검색 가중치(검색 점수 = 유사도 × 가중치). 기준은 CLAUDE.md 설계 결정.
TIER_WEIGHTS: Final[dict[str, float]] = {"A": 1.0, "B": 0.5, "C": 0.1}
