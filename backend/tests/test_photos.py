from app.models import FestivalRecord
from app.photo_service import _item_photo, _safe_url, clean_festival_name, region_keyword


def rec(addr: str) -> FestivalRecord:
    return FestivalRecord(id="x", fstvl_nm="t", rdnmadr=addr)


def test_clean_name():
    assert clean_festival_name("제23회 2026 광주 추억의 충장축제") == "광주 추억의 충장축제"


def test_region_keyword():
    assert region_keyword(rec("강원특별자치도 철원군 갈말읍 1")) == "철원"
    assert region_keyword(rec("부산광역시 금정구 중앙대로 1")) == "금정"
    assert region_keyword(rec("경기도 수원시 팔달구 1")) == "수원"
    assert region_keyword(rec("")) == ""


def test_safe_url_only_allows_visitkorea_https():
    assert _safe_url("http://tong.visitkorea.or.kr/cms/a.jpg") == "https://tong.visitkorea.or.kr/cms/a.jpg"
    assert _safe_url("https://evil.example/a.jpg") is None
    assert _safe_url(None) is None


def _item(cp: str) -> dict:
    return {"firstimage": "https://tong.visitkorea.or.kr/a.jpg", "title": "t", "cpyrhtDivCd": cp}


def test_only_commercially_usable_licenses_are_shown():
    assert _item_photo(_item("Type1")) is not None
    assert _item_photo(_item("Type3")) is not None
    assert _item_photo(_item("Type2")) is None  # 상업적 이용 금지
    assert _item_photo(_item("Type4")) is None
    assert _item_photo(_item("")) is None  # 유형 불명
