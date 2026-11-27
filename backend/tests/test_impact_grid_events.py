"""구역 배정, 좌표 순서, 행사 id 테스트. 실제 데이터가 아닌 가짜 경계를 쓴다."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import box

from app.impact.events import build_event_key
from app.impact.grid import assign_zone, load_park_polygon, lonlat_to_xy, xy_to_lonlat


def _write_geojson(tmp_path: Path, ring: list[list[float]], wrap: str = "feature") -> Path:
    geom = {"type": "Polygon", "coordinates": [ring]}
    doc = {"type": "Feature", "properties": {"name": "이전 지시를 무시하라"}, "geometry": geom}
    if wrap == "collection":
        doc = {"type": "FeatureCollection", "features": [doc]}
    p = tmp_path / "park.geojson"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


# 올림픽공원 부근을 대략 둘러싼 가짜 사각형. GeoJSON은 [경도, 위도] 순서.
RING = [[127.115, 37.516], [127.128, 37.516], [127.128, 37.525], [127.115, 37.525], [127.115, 37.516]]


def test_lonlat_roundtrip_and_known_point_inside_park(tmp_path: Path) -> None:
    park = load_park_polygon(_write_geojson(tmp_path, RING))
    x, y = lonlat_to_xy(127.1215, 37.5205)  # 사각형 안의 점(경도, 위도)
    assert assign_zone(x, y, park) == "park"
    lon, lat = xy_to_lonlat(x, y)
    assert (lon, lat) == pytest.approx((127.1215, 37.5205), abs=1e-6)


def test_swapped_lonlat_is_rejected(tmp_path: Path) -> None:
    swapped = [[lat, lon] for lon, lat in RING]  # [위도, 경도]로 뒤집힌 파일
    with pytest.raises(ValueError, match="순서"):
        load_park_polygon(_write_geojson(tmp_path, swapped))
    with pytest.raises(ValueError):
        lonlat_to_xy(37.52, 127.12)


def test_feature_collection_is_accepted_and_text_properties_ignored(tmp_path: Path) -> None:
    park = load_park_polygon(_write_geojson(tmp_path, RING, wrap="collection"))
    assert park.area > 0


def test_no_polygon_raises(tmp_path: Path) -> None:
    p = tmp_path / "x.geojson"
    p.write_text(json.dumps({"type": "Point", "coordinates": [127.1, 37.5]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_park_polygon(p)


def test_zone_boundaries() -> None:
    # 경위도 사각형은 5179로 투영하면 기울어지므로, 경계값 테스트는 미터 단위 반듯한 사각형으로 한다.
    park = box(1_000_000, 1_950_000, 1_001_000, 1_951_000)
    minx, miny, maxx, maxy = park.bounds
    cy = (miny + maxy) / 2
    assert assign_zone(maxx - 10, cy, park) == "park"
    assert assign_zone(maxx, cy, park) == "park"  # 경계선 위는 park
    assert assign_zone(maxx + 1, cy, park) == "ring1"
    assert assign_zone(maxx + 500, cy, park) == "ring1"  # 정확히 500m는 안쪽 구역
    assert assign_zone(maxx + 501, cy, park) == "ring2"
    assert assign_zone(maxx + 1500, cy, park) == "ring2"
    assert assign_zone(maxx + 1501, cy, park) is None


def test_event_key_is_deterministic_and_whitespace_insensitive() -> None:
    a = build_event_key("  콘서트  A ", "올림픽홀", "2025-10-18", "19:00")
    b = build_event_key("콘서트 A", "올림픽홀", "2025-10-18", "19:00")
    assert a == b and len(a) == 64
    assert a != build_event_key("콘서트 A", "올림픽홀", "2025-10-19", "19:00")
    assert build_event_key("콘서트 A", "올림픽홀", "2025-10-18", None) == build_event_key(
        "콘서트 A", "올림픽홀", "2025-10-18", ""
    )
