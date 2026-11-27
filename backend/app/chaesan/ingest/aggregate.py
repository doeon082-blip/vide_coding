"""큰 원본 표를 미리 집계한 서비스용 표(s_*)를 만든다.

D1 무료 한도(하루 읽기 행 수) 때문에 21만 행 입출차 원본(t_15138735)은 서비스에 올리지 않고,
날짜·시간대별로 센 표만 올린다. 집계는 SQL로 하고 결과를 원본과 대조해 합계가 다르면 멈춘다.
"""

from __future__ import annotations

import sqlite3
from typing import Final

# 날짜·시(hour)별 입차·출차 대수. weekday는 0=월 … 6=일(when.py와 같은 기준).
# is_holiday는 공휴일 데이터(한국천문연구원 특일 정보, 2단계)를 연결하기 전까지 NULL로 둔다(추측 금지).
# 원본에는 모든 칸이 같은 행이 있지만 차량 번호가 없어 중복인지 알 수 없으므로 지우지 않고 그대로 센다(카드에 주의점).
_PARKING_HOURLY: Final = """
CREATE TABLE s_parking_hourly (
  date TEXT NOT NULL, hour INTEGER NOT NULL, weekday INTEGER NOT NULL, is_holiday INTEGER,
  entries INTEGER NOT NULL, exits INTEGER NOT NULL, PRIMARY KEY (date, hour)
);
WITH ev AS (
  SELECT substr(entry_at, 1, 10) AS date, CAST(substr(entry_at, 12, 2) AS INTEGER) AS hour, 1 AS e, 0 AS x
    FROM t_15138735 WHERE entry_at IS NOT NULL
  UNION ALL
  SELECT substr(exit_at, 1, 10), CAST(substr(exit_at, 12, 2) AS INTEGER), 0, 1
    FROM t_15138735 WHERE exit_at IS NOT NULL
)
INSERT INTO s_parking_hourly
SELECT date, hour, (CAST(strftime('%w', date) AS INTEGER) + 6) % 7, NULL, SUM(e), SUM(x)
  FROM ev GROUP BY date, hour;
"""


class AggregateMismatch(RuntimeError):
    """집계 합계가 원본과 다르다."""


def build_aggregates(con: sqlite3.Connection) -> None:
    con.executescript(_PARKING_HOURLY)
    src = con.execute("SELECT COUNT(entry_at), COUNT(exit_at) FROM t_15138735").fetchone()
    agg = con.execute("SELECT SUM(entries), SUM(exits) FROM s_parking_hourly").fetchone()
    if tuple(src) != tuple(agg):
        raise AggregateMismatch(f"s_parking_hourly 합계 {agg} ≠ 원본 {src}")
