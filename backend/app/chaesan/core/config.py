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

# 로컬 개발 모델(ollama list로 설치 확인함). 서비스(Workers AI) 모델 이름은 G단계에서 확인 후 넣는다.
LOCAL_MODEL: Final = "gemma4:26b"

# 데이터 등급별 검색 가중치(검색 점수 = 유사도 × 가중치). 기준은 CLAUDE.md 설계 결정.
TIER_WEIGHTS: Final[dict[str, float]] = {"A": 1.0, "B": 0.5, "C": 0.1}

# LLM이 SQL을 쓸 수 있는 표. B단계(적재)에서 집계 표와 작은 표만 채운다. 비어 있으면 SQL 질문은 모두 거부된다.
ALLOWED_TABLES: Final[frozenset[str]] = frozenset()
