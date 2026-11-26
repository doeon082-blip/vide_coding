"""한국관광공사 TourAPI(KorService2)로 축제/지역 사진을 조회한다. 결과는 디스크에 캐싱한다.

1) 축제명으로 '행사/공연/축제'(contentTypeId=15) 검색 → 제목이 비슷한 항목의 사진 (kind="festival")
2) 없으면 축제가 열리는 시·군·구 이름으로 관광지 검색 → 해당 지역 사진 (kind="region")
3) 그래도 없으면 kind="none"
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote

import httpx
from pydantic import BaseModel

from app.database import BACKEND_DIR
from app.models import FestivalRecord
from app.search import normalize

logger = logging.getLogger(__name__)

TOUR_API_URL = (os.getenv("TOUR_API_URL") or "https://apis.data.go.kr/B551011/KorService2").rstrip("/")
IMAGE_HOSTS = {"tong.visitkorea.or.kr"}
CACHE_FILE = Path(os.getenv("PHOTO_CACHE_FILE") or BACKEND_DIR / "cache" / "photos.json")
CACHE_TTL = 7 * 24 * 3600
CACHE_VERSION = 2  # v2: Photo.license 추가
MAX_PHOTOS = 6
REGION_TYPES = {"12", "14", "15", "28"}  # 관광지, 문화시설, 행사, 레포츠 (숙박/음식점/쇼핑 제외)
_PROVINCE_SUFFIX = ("특별시", "광역시", "특별자치시", "특별자치도", "도")

Kind = Literal["festival", "region", "none"]


class Photo(BaseModel):
    url: str
    thumb: str
    caption: str = ""
    # 공공누리 유형 (cpyrhtDivCd): Type1=출처표시, Type3=출처표시+변경금지. 모르면 빈 문자열
    license: str = ""


class PhotoResult(BaseModel):
    kind: Kind
    photos: list[Photo]
    region: str = ""
    matched_title: str = ""


_lock = threading.Lock()
_cache: dict[str, dict[str, Any]] | None = None


def _load_cache() -> dict[str, dict[str, Any]]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _save_cache() -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("Photo cache write failed: %s", exc)


def _safe_url(url: str | None) -> str | None:
    """http → https 로 올리고 허용 호스트만 통과."""
    if not url:
        return None
    url = re.sub(r"^http://", "https://", url.strip())
    m = re.match(r"^https://([^/]+)/", url)
    return url if m and m.group(1) in IMAGE_HOSTS else None


def _service_key() -> str:
    raw = (os.getenv("PUBLIC_DATA_API_KEY") or "").strip()
    return unquote(raw) if "%" in raw else raw


def _call(client: httpx.Client, endpoint: str, **params: Any) -> list[dict[str, Any]]:
    resp = client.get(
        f"{TOUR_API_URL}/{endpoint}",
        params={"serviceKey": _service_key(), "MobileOS": "ETC", "MobileApp": "festival", "_type": "json", **params},
    )
    resp.raise_for_status()
    header = resp.json()["response"]
    if header["header"]["resultCode"] != "0000":
        raise RuntimeError(f"TourAPI error: {header['header']['resultMsg']}")
    items = header["body"].get("items")
    if not items:
        return []
    got = items["item"]
    return got if isinstance(got, list) else [got]


def clean_festival_name(name: str) -> str:
    """'제23회 2026 광주 추억의 충장축제' → '광주 추억의 충장축제'"""
    name = re.sub(r"제?\s*\d+\s*회", " ", name)
    name = re.sub(r"\b20\d{2}\s*년?", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def region_keyword(record: FestivalRecord) -> str:
    """도로명주소에서 시/군/구 이름을 뽑아 검색 키워드로 쓴다. '강원특별자치도 철원군 …' → '철원'"""
    tokens = record.rdnmadr.split()
    cand = [t for t in tokens if re.search(r"[시군구]$", t) and not t.endswith(_PROVINCE_SUFFIX)]
    cities = [t for t in cand if t.endswith(("시", "군"))]
    pick = (cities or cand or [""])[0]
    kw = re.sub(r"[시군구]$", "", pick)
    if len(kw) < 2 and pick:  # '동구','중구' 처럼 너무 짧으면 접미사 유지
        kw = pick
    return kw


def _similar(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _item_photo(item: dict[str, Any]) -> Photo | None:
    url = _safe_url(item.get("firstimage"))
    if not url:
        return None
    return Photo(
        url=url,
        thumb=_safe_url(item.get("firstimage2")) or url,
        caption=item.get("title", ""),
        license=item.get("cpyrhtDivCd") or "",
    )


def _detail_photos(client: httpx.Client, content_id: str, title: str) -> list[Photo]:
    out: list[Photo] = []
    for im in _call(client, "detailImage2", contentId=content_id, imageYN="Y", numOfRows=MAX_PHOTOS, pageNo=1):
        url = _safe_url(im.get("originimgurl"))
        if url:
            out.append(
                Photo(
                    url=url,
                    thumb=_safe_url(im.get("smallimageurl")) or url,
                    caption=title,
                    license=im.get("cpyrhtDivCd") or "",
                )
            )
    return out


def _lookup(record: FestivalRecord) -> PhotoResult:
    name = clean_festival_name(record.fstvl_nm)
    tokens = sorted({t for t in name.split() if len(t) >= 2}, key=len, reverse=True)
    queries = [name] + [t for t in tokens[:2] if t != name]
    with httpx.Client(timeout=20.0) as client:
        # 1) 축제 직접 검색
        for q in queries:
            for item in _call(client, "searchKeyword2", keyword=q, contentTypeId=15, numOfRows=10, pageNo=1):
                if _similar(name, item.get("title", "")) < 0.6:
                    continue
                photos = _detail_photos(client, item["contentid"], item["title"])
                for ph in photos:
                    ph.license = ph.license or item.get("cpyrhtDivCd") or ""
                first = _item_photo(item)
                if first and all(p.url != first.url for p in photos):
                    photos.insert(0, first)
                if photos:
                    return PhotoResult(kind="festival", photos=photos[:MAX_PHOTOS], matched_title=item["title"])
        # 2) 지역 관광지 사진
        region = region_keyword(record)
        if region:
            photos = []
            for item in _call(client, "searchKeyword2", keyword=region, numOfRows=30, pageNo=1):
                if item.get("contenttypeid") in REGION_TYPES and (p := _item_photo(item)):
                    photos.append(p)
                if len(photos) >= MAX_PHOTOS:
                    break
            if photos:
                return PhotoResult(kind="region", photos=photos, region=region)
    return PhotoResult(kind="none", photos=[])


def get_photos(record: FestivalRecord) -> PhotoResult:
    with _lock:
        hit = _load_cache().get(record.id)
    if hit and hit.get("v") == CACHE_VERSION and time.time() - hit["at"] < CACHE_TTL:
        return PhotoResult(**hit["data"])
    try:
        result = _lookup(record)
    except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as exc:
        # 실패는 캐싱하지 않는다 (키/쿼터 문제일 수 있음). URL(serviceKey 포함)은 로그에 남기지 않는다.
        logger.warning("TourAPI lookup failed id=%s: %s", record.id[:8], type(exc).__name__)
        return PhotoResult(kind="none", photos=[])
    with _lock:
        _load_cache()[record.id] = {"v": CACHE_VERSION, "at": time.time(), "data": result.model_dump()}
        _save_cache()
    logger.info("Photos id=%s kind=%s n=%d", record.id[:8], result.kind, len(result.photos))
    return result
