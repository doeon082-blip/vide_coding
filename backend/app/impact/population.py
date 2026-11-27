"""생활인구 zip → 필요한 칸만 걸러 pop_hourly 형식 CSV로 변환(zip 스트리밍).

원본의 열 이름·인코딩·구분자는 파일을 열어 확인한 뒤 ColumnMap과 인자로 넘긴다
(여기서 추측하지 않는다). zip은 풀지 않고 안에서 바로 읽어 디스크 쓰기와 정리 부담이 없다.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from app.impact.parse import parse_count, parse_date, parse_hour


@dataclass(frozen=True)
class ColumnMap:
    """원본 열 이름 → 의미. 파일 헤더를 확인한 뒤 채운다."""

    date_col: str
    hour_col: str
    cell_col: str
    value_cols: tuple[str, ...]  # 합계 열 하나, 또는 더해야 하는 여러 열(예: 성별·연령별)


@dataclass
class IngestStats:
    rows_read: int = 0
    rows_kept: int = 0  # 구역에 속한 칸의 행
    rows_bad: int = 0  # 날짜·시·사람 수를 해석하지 못한 행(예상과 다른 표기를 드러내려고 센다)
    suppressed: int = 0  # `*` 행 수(kept 중)


def list_zip_members(zip_path: Path) -> list[tuple[str, int]]:
    """zip 안 파일 이름과 압축 해제 크기(바이트). 풀지 않고 목록만 읽는다."""
    with zipfile.ZipFile(zip_path) as zf:
        return [(i.filename, i.file_size) for i in zf.infolist() if not i.is_dir()]


def iter_zip_csv(zip_path: Path, member: str, encoding: str, delimiter: str = ",") -> Iterator[dict[str, str]]:
    """zip 안의 CSV를 한 행씩 dict로 읽는다(메모리에 전부 올리지 않는다).

    encoding은 호출 쪽이 확인한 값을 넘긴다(BOM이 있으면 'utf-8-sig'). 헤더 공백은 제거한다.
    """
    with zipfile.ZipFile(zip_path) as zf, zf.open(member) as raw:
        text = io.TextIOWrapper(raw, encoding=encoding, newline="")
        reader = csv.DictReader(text, delimiter=delimiter)
        if reader.fieldnames is None:
            return
        reader.fieldnames = [h.strip() for h in reader.fieldnames]
        for row in reader:
            yield {k: (v or "") for k, v in row.items() if k is not None}


def ingest_population(
    rows: Iterator[Mapping[str, str]],
    colmap: ColumnMap,
    cell_zone: Mapping[str, str],
    kind: str,
    out_csv: Path,
) -> IngestStats:
    """행들에서 구역에 속한 칸만 골라 pop_hourly 형식 CSV로 쓴다.

    - value_cols가 여럿이면 더한다. 하나라도 `*`면 그 행은 값 없이 suppressed=true(임의로 채우지 않음).
    - 날짜·시·사람 수를 해석하지 못한 행은 건너뛰고 rows_bad로 센다.
    - 필요한 열이 헤더에 없으면 첫 행에서 ValueError로 바로 알린다.
    """
    stats = IngestStats()
    needed = {colmap.date_col, colmap.hour_col, colmap.cell_col, *colmap.value_cols}
    checked = False
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "hour", "cell_id", "kind", "value", "suppressed"])
        for row in rows:
            if not checked:
                missing = needed - set(row)
                if missing:
                    raise ValueError(f"원본에 없는 열: {sorted(missing)} (있는 열: {sorted(row)})")
                checked = True
            stats.rows_read += 1
            cell = row[colmap.cell_col].strip()
            if cell not in cell_zone:
                continue
            d, h = parse_date(row[colmap.date_col]), parse_hour(row[colmap.hour_col])
            if d is None or h is None:
                stats.rows_bad += 1
                continue
            try:
                parts = [parse_count(row[c]) for c in colmap.value_cols]
            except ValueError:
                stats.rows_bad += 1
                continue
            suppressed = any(s for _, s in parts)
            missing_value = any(v is None and not s for v, s in parts)
            if missing_value and not suppressed:
                stats.rows_bad += 1  # 빈 값은 0이 아니라 결측이므로 저장하지 않는다
                continue
            value = None if suppressed else sum(v for v, _ in parts if v is not None)
            w.writerow([d.isoformat(), h, cell, kind, "" if value is None else value, "true" if suppressed else "false"])
            stats.rows_kept += 1
            stats.suppressed += suppressed
    return stats
