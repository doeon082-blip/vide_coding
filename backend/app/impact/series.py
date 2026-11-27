"""Parquet 표 → 구역별 시간 합계 시계열. evaluate.py가 받는 입력을 만든다."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, time
from pathlib import Path

import duckdb

from app.impact import config
from app.impact.store import _q, table_path


def load_series(
    processed_dir: Path | None = None,
    suppressed_fill: float = 0.0,
    kinds: Sequence[str] = ("native",),
    require_full_coverage: bool = True,
) -> dict[str, dict[datetime, float]]:
    """구역 → {정시: 그 시각 구역 합계}.

    suppressed_fill: `*`(비식별) 칸에 넣을 값. 0과 3으로 두 번 불러 판정이 달라지는지 본다.
    kinds: 합칠 인구 종류(native, temp_foreign). 여러 개면 모두 더한다.
    require_full_coverage: 구역의 모든 칸×종류가 값(또는 `*`)을 가진 시각만 남긴다.
      칸이 하나라도 빠진 시각의 합은 실제보다 작아서 기준값과 증가분을 왜곡하므로 버려서
      "판정 불가"로 드러나게 한다. (원본이 0인 칸을 생략하는지는 확인 전이라 끌 수 있게 열어 둔다.)
    """
    pop, cells = table_path("pop_hourly", processed_dir), table_path("cells", processed_dir)
    if not pop.exists() or not cells.exists():
        raise FileNotFoundError("pop_hourly.parquet / cells.parquet 이 없습니다. 먼저 수집(B)을 실행하세요.")
    kind_sql = ", ".join("'" + k.replace("'", "''") + "'" for k in kinds)
    query = f"""
        SELECT c.zone, p.date, p.hour,
               sum(CASE WHEN p.suppressed THEN ? ELSE p.value END) AS v,
               count(*) FILTER (WHERE p.suppressed OR p.value IS NOT NULL) AS n_ok
        FROM read_parquet('{_q(pop)}') p
        JOIN read_parquet('{_q(cells)}') c USING (cell_id)
        WHERE p.kind IN ({kind_sql})
        GROUP BY c.zone, p.date, p.hour
    """
    con = duckdb.connect()
    try:
        n_cells = dict(con.execute(f"SELECT zone, count(*) FROM read_parquet('{_q(cells)}') GROUP BY zone").fetchall())
        rows = con.execute(query, [suppressed_fill]).fetchall()
    finally:
        con.close()
    out: dict[str, dict[datetime, float]] = {z: {} for z in config.ZONES}
    for zone, d, hour, v, n_ok in rows:
        if v is None:
            continue
        if require_full_coverage and n_ok != n_cells.get(zone, 0) * len(kinds):
            continue
        out.setdefault(zone, {})[datetime.combine(d, time(hour))] = float(v)
    return out
