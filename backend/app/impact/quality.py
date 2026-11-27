"""C단계: 수집한 표의 품질 보고서(data/report/quality.md)를 만든다.

있는 표만 보고하고, 없는 표는 "없음"으로 적는다(없는 데이터를 추측해서 채우지 않는다).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb

from app.impact import config
from app.impact.store import _q, table_path

LIMITATIONS = """\
- 올림픽공원 안의 **공연장(올림픽홀, 체조경기장 등)을 구분할 수 없다.** `park` 합계는 공원 전체다.
- `park` 밖 구역(`ring1`, `ring2`)에는 **인접 거주자의 야간 체류**가 섞여 있어 밤 시간대 증가분은 해석에 주의한다.
- 행사 때문에 늘었는지 **같은 날 다른 이유**(날씨, 수능일 등 시험·행사, 공원 일반 이용)로 늘었는지 구분하지 못한다. 기준값은 같은 요일의 행사 없는 날 중앙값일 뿐이다.
- 생활인구는 추정치이고 `*`(비식별)는 값을 모른다. 0과 3으로 채운 두 계산의 차이만 확인한다.
- 이 분석은 **상관(전후 비교)** 이며 인과를 증명하지 않는다. 방문객 수나 입장객 수를 직접 측정한 것도 아니다.
- 한체산 행사 목록이 올림픽공원 전체 행사를 포함하는지는 대관정보·문화행사와 비교해 보기 전에는 알 수 없다.
"""


def _fmt(rows: list[tuple], headers: list[str]) -> str:
    if not rows:
        return "(없음)\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join("" if c is None else str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def _missing_dates(dates: list[date]) -> list[date]:
    if not dates:
        return []
    have, d, end, out = set(dates), min(dates), max(dates), []
    while d <= end:
        if d not in have:
            out.append(d)
        d += timedelta(days=1)
    return out


def build_quality_report(processed_dir: Path | None = None) -> str:
    """품질 보고서 마크다운 문자열을 만든다."""
    proc = processed_dir or config.PROCESSED_DIR
    cells_p, pop_p, ev_p = (table_path(t, proc) for t in ("cells", "pop_hourly", "events"))
    con = duckdb.connect()
    parts: list[str] = ["# 데이터 품질 보고서\n"]
    try:
        # --- 구역·칸 ---
        parts.append("## 구역별 칸 수\n")
        if cells_p.exists():
            rows = con.execute(f"SELECT zone, count(*) FROM read_parquet('{_q(cells_p)}') GROUP BY 1 ORDER BY 1").fetchall()
            parts.append(_fmt(rows, ["구역", "칸 수"]))
        else:
            parts.append("cells 표 없음\n")

        # --- 생활인구 ---
        parts.append("\n## 생활인구 (pop_hourly)\n")
        if pop_p.exists() and cells_p.exists():
            base = f"read_parquet('{_q(pop_p)}') p JOIN read_parquet('{_q(cells_p)}') c USING (cell_id)"
            rows = con.execute(
                f"SELECT strftime(p.date, '%Y-%m') m, c.zone, p.kind, count(*) n, "
                f"round(100.0 * avg(CASE WHEN p.suppressed THEN 1 ELSE 0 END), 2) pct_star, "
                f"count(*) FILTER (WHERE NOT p.suppressed AND p.value IS NULL) n_null "
                f"FROM {base} GROUP BY 1,2,3 ORDER BY 1,2,3"
            ).fetchall()
            parts.append("### 월·구역·종류별 행 수와 `*` 비율\n")
            parts.append(_fmt(rows, ["월", "구역", "종류", "행 수", "`*` 비율(%)", "값 없음(비`*`)"]))
            for (kind,) in con.execute(f"SELECT DISTINCT kind FROM read_parquet('{_q(pop_p)}') ORDER BY 1").fetchall():
                dates = [r[0] for r in con.execute(
                    f"SELECT DISTINCT date FROM read_parquet('{_q(pop_p)}') WHERE kind = ? ORDER BY 1", [kind]).fetchall()]
                miss = _missing_dates(dates)
                parts.append(f"\n### 빠진 날짜 ({kind}): {dates[0]} ~ {dates[-1]} 중 {len(miss)}일\n")
                parts.append((", ".join(map(str, miss[:40])) + (" …" if len(miss) > 40 else "")) + "\n" if miss else "없음\n")
                short = con.execute(
                    f"SELECT date, count(DISTINCT hour) h FROM read_parquet('{_q(pop_p)}') WHERE kind = ? "
                    f"GROUP BY 1 HAVING count(DISTINCT hour) < 24 ORDER BY 1", [kind]).fetchall()
                parts.append(f"\n### 24시간이 다 없는 날짜 ({kind}): {len(short)}일\n")
                parts.append(_fmt([(str(d), h) for d, h in short[:40]], ["날짜", "있는 시각 수"]))
            parts.append("\n### 구역의 칸이 일부만 있는 (날짜, 시각) 수\n")
            rows = con.execute(
                f"WITH z AS (SELECT zone, count(*) n FROM read_parquet('{_q(cells_p)}') GROUP BY 1), "
                f"h AS (SELECT c.zone, p.kind, p.date, p.hour, count(*) n FROM {base} GROUP BY 1,2,3,4) "
                f"SELECT h.zone, h.kind, count(*) FILTER (WHERE h.n < z.n) partial, count(*) total "
                f"FROM h JOIN z USING (zone) GROUP BY 1,2 ORDER BY 1,2"
            ).fetchall()
            parts.append(_fmt(rows, ["구역", "종류", "칸 일부 누락 시각", "전체 시각"]))
            parts.append("누락 시각은 시계열에서 제외되어 해당 행사가 \"판정 불가\"가 될 수 있다.\n")
        else:
            parts.append("pop_hourly 또는 cells 표 없음\n")

        # --- 행사 ---
        parts.append("\n## 행사 (events)\n")
        if ev_p.exists():
            e = f"read_parquet('{_q(ev_p)}')"
            parts.append(_fmt(con.execute(f"SELECT source, count(*) FROM {e} GROUP BY 1 ORDER BY 1").fetchall(), ["출처", "행사 수"]))
            n_nostart = con.execute(f"SELECT count(*) FROM {e} WHERE start_time IS NULL OR start_time = ''").fetchone()[0]
            parts.append(f"\n- 시작 시각이 없는 행사: **{n_nostart}건** (효과 판정에서 제외)\n")
            dup = con.execute(
                f"SELECT name, venue, date, count(*) n FROM {e} GROUP BY 1,2,3 HAVING count(*) > 1 ORDER BY n DESC LIMIT 20"
            ).fetchall()
            parts.append(f"- 같은 이름·장소·날짜가 둘 이상(출처 간 중복 의심): **{len(dup)}건**\n")
            if dup:
                parts.append(_fmt(dup, ["이름", "장소", "날짜", "건수"]))
            multi = con.execute(
                f"SELECT date, count(*) n FROM {e} GROUP BY 1 HAVING count(*) > 1 ORDER BY 1"
            ).fetchall()
            parts.append(f"\n- 같은 날 행사가 여러 건인 날: **{len(multi)}일**\n")
            parts.append(_fmt([(str(d), n) for d, n in multi[:40]], ["날짜", "행사 수"]))
        else:
            parts.append("events 표 없음\n")

        # --- 입차·날씨 ---
        parts.append("\n## 입차·날씨\n")
        for t in ("parking_hourly", "weather_hourly"):
            p = table_path(t, proc)
            if not p.exists():
                parts.append(f"- {t}: 표 없음 (원본 열 확인 전)\n")
                continue
            cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{_q(p)}')").fetchall()]
            n = con.execute(f"SELECT count(*) FROM read_parquet('{_q(p)}')").fetchone()[0]
            nulls = con.execute(
                "SELECT " + ", ".join(f'count(*) FILTER (WHERE "{c}" IS NULL)' for c in cols) + f" FROM read_parquet('{_q(p)}')"
            ).fetchone()
            parts.append(f"- {t}: {n}행, 열별 결측 " + ", ".join(f"{c}={k}" for c, k in zip(cols, nulls)) + "\n")
    finally:
        con.close()
    parts.append("\n## 이 데이터로 할 수 없는 것\n")
    parts.append(LIMITATIONS)
    return "\n".join(parts)


def write_quality_report(processed_dir: Path | None = None, report_dir: Path | None = None) -> Path:
    """보고서를 data/report/quality.md 로 저장하고 경로를 돌려준다."""
    out_dir = report_dir or config.REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "quality.md"
    path.write_text(build_quality_report(processed_dir), encoding="utf-8")
    return path
