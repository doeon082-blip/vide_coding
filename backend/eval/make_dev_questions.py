"""개발용 질문 20개를 데이터에서 무작위로 뽑아 만든다(정답은 DB를 직접 계산한 값).

실행: `uv run python -m eval.make_dev_questions` → eval/dev_questions.jsonl

원칙
- 질문의 변수(연도, 센터, FAQ 항목, 연혁 항목 …)는 고정 시드의 난수로 데이터에서 뽑는다. 사람이 '잘 풀릴 질문'을 고르지 않도록.
- 정답(expected)은 내가 짐작한 값이 아니라 DB를 직접 SQL로 계산한 값이다. 채산 코드(엔진·플래너)는 쓰지 않는다.
- E단계를 만들면서 직접 돌려 보고 고친 질문(테니스 최다 월, 입차 최다 시각, 장미 기사, 한산한 시간)은 오염되어 제외한다.
- 20개 중 5개는 오타·줄임말 변형이고, 3개는 데이터에 근거가 없어 '모른다'가 정답이다.
- 이 파일은 개발용이다. 시험용 60문항(test_questions.jsonl)과는 다르며 여기서 점수를 보고 코드를 질문에 맞춰 고치지 않는다(규칙 11·12).

필드: id, question, type, expected_tables(카드 번호), expected_answer(사람이 읽는 정답), expect_status(허용 상태), allowed_fixes(기대하지 않아도 틀린 보정이 아닌 약칭 풀이),
  expect_contains(각 항목은 대안 목록: 답·근거 어디에든 하나는 있어야 함), expect_docs(문서 제목에 있어야 하는 낱말),
  typos([입력한 말, 고쳐야 할 말] 목록)
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.chaesan.ingest.cards import HISTORY_HTML, parse_history
from app.chaesan.ingest.load import BACKEND_DIR, DB_PATH
from app.chaesan.local.db import ro_uri

OUT = BACKEND_DIR / "eval" / "dev_questions.jsonl"
SEED = 20261128


def num(n: int | float) -> list[str]:
    """숫자의 표기 대안: 215528 / 215,528."""
    n = int(n) if float(n).is_integer() else n
    return [f"{n:,}", str(n)] if isinstance(n, int) else [str(n)]


def date_alts(d: str) -> list[str]:
    y, m, day = (int(x) for x in d.split("-"))
    return [d, f"{y}년 {m}월 {day}일", f"{m}월 {day}일", f"{m}월{day}일"]


def build(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    q = lambda sql, *a: con.execute(sql, a).fetchall()  # noqa: E731
    items: list[dict[str, Any]] = []

    def add(type_: str, question: str, tables: list[str], answer: str, **kw: Any) -> None:
        items.append(
            {
                "id": f"dev{len(items) + 1:02d}", "question": question, "type": type_, "expected_tables": tables,
                "expected_answer": answer, "expect_status": kw.pop("status", ["answered"]),
                "expect_contains": kw.pop("contains", []), "expect_docs": kw.pop("docs", []), "typos": kw.pop("typos", []),
                "allowed_fixes": kw.pop("allowed_fixes", []),
            }
        )  # fmt: skip

    # 1 테니스장 연도별 구분별 합계
    year, member = rng.choice(range(2021, 2026)), rng.choice(["월회원", "일일입장"])
    total = q("SELECT SUM(users) FROM t_15133891 WHERE member_type=? AND substr(start_date,1,4)=?", member, str(year))[0][0]
    add("data", f"테니스장 {year}년 {member} 이용자는 모두 몇 명이야?", ["15133891"], f"{total:,}명", contains=[num(total)])

    # 2 주차 월별 최다 월
    lot, year = rng.choice(["올림픽공원", "미사경정공원"]), rng.choice([2023, 2024, 2025])
    month, cars = q("SELECT month, cars FROM t_15131671 WHERE lot=? AND year=? ORDER BY cars DESC LIMIT 1", lot, year)[0]
    add("data", f"{lot}은 {year}년에 주차 대수가 가장 많았던 달이 언제야?", ["15131671"], f"{month}월({cars:,}대)",
        contains=[[f"{month}월", f"{year}-{month:02d}"]])  # fmt: skip  # 묻는 것은 '달'뿐이다(값까지 요구하면 맞는 답을 틀렸다고 채점한다)

    # 3 주차 월별 단일 값
    lot, year, month = rng.choice(["올림픽공원", "미사경정공원"]), rng.choice([2023, 2024, 2025]), rng.randint(1, 12)
    cars = q("SELECT cars FROM t_15131671 WHERE lot=? AND year=? AND month=?", lot, year, month)[0][0]
    add("data", f"{lot}에 {year}년 {month}월에 주차한 차는 몇 대야?", ["15131671"], f"{cars:,}대", contains=[num(cars)])

    # 4 혼잡도 만차 횟수
    n = q("SELECT COUNT(*) FROM t_15164156 WHERE congestion='만차'")[0][0]
    add("data", "주차장 혼잡도 기록 중에 만차인 경우는 몇 번이야?", ["15164156"], f"{n}번", contains=[num(n)])

    # 5 입출차 2024-07 입차 최다 날짜
    d, v = q("SELECT date, SUM(entries) FROM s_parking_hourly GROUP BY date ORDER BY 2 DESC, 1 LIMIT 1")[0]
    add("data", "입출차 자료에서 입차가 가장 많았던 날은 며칠이야?", ["15138735"], f"{d}({v:,}대)", contains=[date_alts(d)])  # 묻는 것은 '날'뿐

    # 6 정원현황 기준일 부서 수
    n = q("SELECT COUNT(*) FROM t_15144222 WHERE base_date='2026-01-01'")[0][0]
    add("data", "2026년 1월 1일 기준 정원현황에는 부서가 몇 개 있어?", ["15144222"], f"{n}개", contains=[num(n)])

    # 7 분당 종목 수 (오타: 센터→센타)
    n = q("SELECT COUNT(DISTINCT sport) FROM t_15118652")[0][0]
    add("typo", "분당스포츠센타에는 종목이 모두 몇 가지야?", ["15118652"], f"{n}가지", contains=[num(n)],
        typos=[["분당스포츠센타", "분당스포츠센터"]])  # fmt: skip

    # 8 언론보도 첫 기사 날짜 (낱말은 난수로)
    term = rng.choice(["스케이트장", "미사경정공원", "자전거", "음악분수", "수영장"])
    first = q("SELECT MIN(doc_date) FROM docs WHERE source_id='15137825' AND squash LIKE ?", f"%{term}%")[0][0]
    add("news", f"언론보도에서 {term} 기사는 언제부터 나왔어?", ["15137825"], first, contains=[date_alts(first)])

    # 9 보도자료 최신 배포일 (오타: 료→로)
    last = q("SELECT MAX(release_date) FROM t_15137824")[0][0]
    add("typo", "가장 최근 보도자로는 언제 배포했어?", ["15137824"], last, contains=[date_alts(last)],
        typos=[["보도자로", "보도자료"]])  # fmt: skip

    # 10 FAQ(숫자가 있는 항목을 난수로)
    # 한 자리 숫자는 아무 문장에나 들어 있어 채점이 우연히 맞는다 → 두 자리 이상 숫자가 있는 항목만 뽑는다
    faqs = [r for r in q("SELECT title, content FROM t_15089962 ORDER BY _row") if re.search(r"\d{2,}", r[1])]
    faq = rng.choice(faqs)
    first_num = re.search(r"\d{2,}", faq[1]).group()  # type: ignore[union-attr]
    add("facility", faq[0].strip() + "?", ["15089962"], f"FAQ 내용에 '{first_num}'이(가) 있음: {faq[1][:60]}…",
        docs=[faq[0].strip()[:6]])  # fmt: skip  # 숫자 일치는 채점하지 않는다: 두 자리 숫자가 답의 핵심인지 알 수 없다(예: 법령 번호)

    # 11 잔디시설 개방(장소는 난수, 오타는 장소마다 정해 둔 자모 한 개 차이)
    typo_of = {"지구촌공원": "지구촌공윈", "전시마당": "전시마탕", "가족놀이동산": "가족놀이동삼", "피크닉장": "피크닉짱"}
    place = rng.choice(sorted(typo_of))
    detail = q("SELECT open_detail FROM t_15143220 WHERE place=? LIMIT 1", place)[0][0]
    if "연중" in detail:
        alt = [["연중", "상시"]]
    else:
        alt = [["6월 1일", "06-01", "6월1일", "6/1"]]
    add("typo", f"{typo_of[place]}은 언제 개방해?", ["15143220"], detail, contains=alt, typos=[[typo_of[place], place]])

    # 12 연혁(월이 있는 항목을 난수로)
    entries = [e for e in parse_history(HISTORY_HTML.read_text(encoding="utf-8")) if e.month]
    e = rng.choice(entries)
    same = [x for x in entries if (x.year, x.month) == (e.year, e.month)]
    words = {w for x in same for w in re.findall(r"[가-힣]{3,}", x.text)}
    add("history", f"기관 연혁에서 {e.year}년 {e.month}월에는 무슨 일이 있었어?", ["history"], " / ".join(x.text for x in same),
        contains=[sorted(words)])  # fmt: skip

    # 13 핫뉴스 최신
    last = q("SELECT MAX(reg_date) FROM t_15090715")[0][0]
    add("news", "올림픽공원 핫뉴스 중에 가장 최근 것은 언제 올라왔어?", ["15090715"], last, contains=[date_alts(last)])

    # 14 개방목록 건수
    n = q("SELECT COUNT(*) FROM t_15147873")[0][0]
    add("org", "한체산이 공공데이터포털에 개방한 파일 목록은 모두 몇 건이야?", ["15147873"], f"{n}건 (포털 58종보다 적음)", contains=[num(n)],
        allowed_fixes=[["한체산", "한국체육산업개발"]])  # 질문 속 공식 약칭을 풀어 읽는 것은 설계된 동작이라 '잘못 고침'이 아니다

    # 15 사전정보공표(항목을 난수로)
    title = rng.choice(q("SELECT title FROM t_15090257 ORDER BY _row"))[0].strip()
    core = re.split(r"[(（]", title)[0].strip()
    key = max(re.findall(r"[가-힣]{3,}", core) or [core[:4]], key=len)  # 항목에서 가장 긴 한글 낱말(흔한 앞부분 대신)
    add("org", f"사전정보공표에서 {core} 자료는 어디서 볼 수 있어?", ["15090257"], title, docs=[key])

    # 16~18 근거 없음(모른다/연결 예정이 정답)
    add("unknown", "스포츠센터 월별 매출액은 얼마야?", [], "데이터 없음", status=["unknown", "planned"])
    add("unknown", "테니스장 코트는 모두 몇 개야?", [], "데이터 없음", status=["unknown", "planned"])
    add("planned", "올림픽공원 유실물 정보를 알려줘", [], "유실물 오픈API(아직 연결 안 됨)", status=["planned", "unknown"])

    # 19 줄임말(올팍) + 주차
    lot_year, lot_month = rng.choice([2023, 2024, 2025]), rng.randint(1, 12)
    cars = q("SELECT cars FROM t_15131671 WHERE lot='올림픽공원' AND year=? AND month=?", lot_year, lot_month)[0][0]
    add("typo", f"올팍에 {lot_year}년 {lot_month}월에 주차한 차는 몇 대야?", ["15131671"], f"{cars:,}대", contains=[num(cars)],
        typos=[["올팍", "올림픽공원"]])  # fmt: skip

    # 20 테니스장 오타(짱)
    year, member = rng.choice(range(2021, 2026)), rng.choice(["월회원", "일일입장"])
    total = q("SELECT SUM(users) FROM t_15133891 WHERE member_type=? AND substr(start_date,1,4)=?", member, str(year))[0][0]
    add("typo", f"테니스짱 {year}년 {member} 이용자는 모두 몇 명이야?", ["15133891"], f"{total:,}명", contains=[num(total)],
        typos=[["테니스짱", "테니스장"]])  # fmt: skip
    return items


def main() -> None:
    con = sqlite3.connect(ro_uri(DB_PATH), uri=True)
    items = build(con)
    con.close()
    assert len(items) == 20
    assert sum(1 for i in items if i["typos"]) == 5
    OUT.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    for i in items:
        print(i["id"], i["type"], i["question"], "→", str(i["expected_answer"])[:60])


if __name__ == "__main__":
    main()
