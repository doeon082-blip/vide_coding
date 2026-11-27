"""공원 경계(GeoJSON)를 읽고, 격자 칸 중심이 어느 구역(park/ring1/ring2)인지 판정한다.

격자 파일(SHP)의 열 이름·ID 형식은 아직 확인 전이라 여기서는 다루지 않는다.
입력은 이미 구한 칸 중심 좌표(미터)만 받는다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import Point, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.impact import config


@lru_cache(maxsize=1)
def _to_planar() -> Transformer:
    # always_xy=True: 입력/출력을 항상 (경도, 위도)/(x, y) 순서로 고정한다.
    # 기본값은 EPSG:4326을 (위도, 경도)로 취급해서 순서가 뒤집히기 쉽다.
    return Transformer.from_crs(config.GEO_CRS, config.PLANAR_CRS, always_xy=True)


@lru_cache(maxsize=1)
def _to_geo() -> Transformer:
    return Transformer.from_crs(config.PLANAR_CRS, config.GEO_CRS, always_xy=True)


def lonlat_to_xy(lon: float, lat: float) -> tuple[float, float]:
    """경도·위도 → EPSG:5179 미터 좌표. 범위를 벗어나면 순서 실수로 보고 거부한다."""
    _check_korea(lon, lat)
    x, y = _to_planar().transform(lon, lat)
    return float(x), float(y)


def xy_to_lonlat(x: float, y: float) -> tuple[float, float]:
    """EPSG:5179 미터 좌표 → (경도, 위도). cells 표의 lat/lon 열을 만들 때 쓴다."""
    lon, lat = _to_geo().transform(x, y)
    return float(lon), float(lat)


def _check_korea(lon: float, lat: float) -> None:
    lo, hi = config.KOREA_LON_RANGE
    la, lb = config.KOREA_LAT_RANGE
    if not (lo <= lon <= hi and la <= lat <= lb):
        raise ValueError(
            f"좌표가 한국 범위를 벗어났습니다 (lon={lon}, lat={lat}). "
            "GeoJSON은 [경도, 위도] 순서입니다. 순서가 뒤집혔는지 확인하세요."
        )


def _geometries(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Feature / FeatureCollection / 순수 geometry 어느 형태든 geometry 목록으로 푼다."""
    kind = doc.get("type")
    if kind == "FeatureCollection":
        return [f["geometry"] for f in doc.get("features", []) if f.get("geometry")]
    if kind == "Feature":
        return [doc["geometry"]] if doc.get("geometry") else []
    return [doc] if kind else []


def load_park_polygon(path: Path) -> BaseGeometry:
    """park.geojson을 읽어 EPSG:5179 폴리곤(여러 개면 합침)으로 돌려준다.

    파일 안의 문자열(name 등 속성)은 데이터일 뿐이라 geometry만 쓴다.
    """
    doc = json.loads(path.read_text(encoding="utf-8"))
    polys: list[BaseGeometry] = []
    for geom in _geometries(doc):
        shp = shape(geom)
        if shp.geom_type not in ("Polygon", "MultiPolygon"):
            continue  # 선·점은 공원 경계가 아니므로 무시
        # 모든 꼭짓점이 한국 범위 안인지 먼저 검사(순서 뒤집힘 방지)
        for lon, lat in _iter_coords(shp):
            _check_korea(lon, lat)
        polys.extend(_project(p) for p in (shp.geoms if hasattr(shp, "geoms") else [shp]))
    if not polys:
        raise ValueError(f"{path.name}에서 Polygon을 찾지 못했습니다.")
    park = unary_union(polys)
    if not park.is_valid:
        park = park.buffer(0)  # 자기 교차 같은 경미한 오류를 보정
    return park


def _project(poly: Polygon) -> Polygon:
    """Polygon 하나의 바깥선·구멍 좌표를 (경도, 위도) → EPSG:5179 미터로 옮긴다.

    shapely.ops.transform은 deprecated이고 numpy 배열 방식은 numpy를 직접 의존하게 되어,
    꼭짓점이 많지 않으니 좌표를 하나씩 변환한다.
    """
    t = _to_planar().transform
    return Polygon(
        [t(lon, lat) for lon, lat in poly.exterior.coords],
        [[t(lon, lat) for lon, lat in ring.coords] for ring in poly.interiors],
    )


def _iter_coords(shp: BaseGeometry):
    parts = shp.geoms if hasattr(shp, "geoms") else [shp]
    for p in parts:
        yield from p.exterior.coords


def assign_zone(x: float, y: float, park: BaseGeometry) -> str | None:
    """칸 중심(x, y; 미터)이 속한 구역. 어디에도 안 속하면 None.

    park: 중심이 경계 안(경계선 위 포함) / ring1: 경계에서 0~500m / ring2: 500m~1.5km.
    경계값(정확히 500m, 1500m)은 안쪽 구역에 넣는다.
    """
    pt = Point(x, y)
    if park.covers(pt):
        return "park"
    d = park.distance(pt)
    if d <= config.RING1_MAX_M:
        return "ring1"
    if d <= config.RING2_MAX_M:
        return "ring2"
    return None
