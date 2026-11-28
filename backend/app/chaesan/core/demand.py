"""개방 수요 기록: 답하지 못한 질문을 기관의 '추가 개방 검토 자료'로 바꾸는 기초 자료.

**질문 원문은 저장하지 않는다.** 기록에는 코드화된 값만 넣는다: 월, 사유 코드, 갈래, 후보 데이터 번호, 그리고
우리 사전·데이터 이름에 있는 낱말(whitelist)뿐이다. 이름·전화번호 같은 개인정보는 사전에 없으므로 기록에 들어갈 수 없다.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Collection, Iterable, Mapping
from datetime import datetime
from typing import Any, Final, Literal

type Reason = Literal["no_data", "no_evidence", "planned_api"]  # 데이터 없음 / 찾았지만 근거 없음 / 연결 예정 API
MAX_TERMS: Final = 6
_HANGUL_RUN: Final = re.compile(r"[가-힣]{2,}")


def topic_terms(question: str, whitelist: Collection[str], limit: int = MAX_TERMS) -> tuple[str, ...]:
    """질문 속 한글 낱말 중 whitelist(사전·데이터 이름)에 있는 것만. 조사가 붙은 낱말은 끝 글자를 한두 개 떼어 본다."""
    out: list[str] = []
    for run in _HANGUL_RUN.findall(question):
        for cand in (run, run[:-1], run[:-2]):
            if len(cand) >= 2 and cand in whitelist:
                if cand not in out:
                    out.append(cand)
                break
        if len(out) >= limit:
            break
    return tuple(out)


def make_record(
    *, now: datetime, reason: Reason, intent: str, group: str | None, card_ids: Iterable[str], terms: Iterable[str]
) -> dict[str, Any]:
    """저장할 기록. 값은 모두 코드화된 짧은 문자열이다(자유 문장 없음)."""
    return {
        "month": now.strftime("%Y-%m"),
        "reason": reason,
        "intent": intent,
        "group": group,
        "cards": sorted(set(card_ids))[:3],
        "terms": list(terms)[:MAX_TERMS],
    }


def summarize(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """월별 개방 수요 요약(기관 담당자용 리포트의 기초): 사유별·갈래별·낱말별 건수."""
    rows = list(records)
    return {
        "total": len(rows),
        "by_month": dict(Counter(r["month"] for r in rows)),
        "by_reason": dict(Counter(r["reason"] for r in rows)),
        "by_group": dict(Counter(r["group"] for r in rows if r.get("group"))),
        "top_terms": Counter(t for r in rows for t in r.get("terms", ())).most_common(10),
    }
