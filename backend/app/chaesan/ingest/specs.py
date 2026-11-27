"""파일 30종의 적재 명세: 원래 한글 열 이름 → 영문 snake_case 이름과 값 종류.

모든 열 이름은 2026-11-28에 실제 파일 헤더를 열어 확인한 것이다(추측 금지, 작업 규칙 4).
적재할 때 파일 헤더가 이 표와 한 글자라도 다르면 멈춘다. 포털이 파일을 바꿨는데 모르고 적재하는 일을 막기 위해서다.
열의 '뜻'과 주의점은 C단계 데이터 카드에 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

# 값 종류. *_range는 한 칸을 두 열(<en>_start, <en>_end)로 나누고, date_in_text는 원문(<en>)과 날짜(<en>_date)를 함께 둔다.
type Kind = Literal[
    "text", "int", "date", "datetime", "yyyymmdd", "month_ko", "hour_of_time",
    "date_range", "time_range", "date_in_text",
]  # fmt: skip


@dataclass(frozen=True, slots=True)
class Col:
    ko: str  # 파일 헤더 그대로
    en: str
    kind: Kind = "text"


@dataclass(frozen=True, slots=True)
class FileSpec:
    id: str  # 공공데이터포털 번호
    title: str
    cols: tuple[Col, ...]
    # 포털·기획서에 적힌 행 수(대조용). 모르면 None으로 두고 "미확인"으로 보고한다.
    expected_rows: int | None = None
    # 1만 행 이상 원본은 로컬에만 두고 서비스에는 집계 표만 올린다(CLAUDE.md 설계 결정).
    local_only: bool = False

    @property
    def table(self) -> str:
        return f"t_{self.id}"


def _c(*items: tuple[str, str] | tuple[str, str, Kind]) -> tuple[Col, ...]:
    return tuple(Col(*i) for i in items)


_COURSE_A = _c(  # 15101610 올림픽수영장, 15114776 일산: 헤더가 같다
    ("일련번호", "row_id"), ("강좌번호", "course_no", "int"), ("강좌서브번호", "course_sub_no", "int"),
    ("시작월", "start_month", "date"), ("강좌코드명", "course_type"), ("강좌명", "course_name"),
    ("시작종료시간", "time", "time_range"), ("정원", "capacity", "int"), ("요일", "days"),
    ("강습반", "class_group"), ("강좌금액", "fee", "int"), ("시작종료일자", "period", "date_range"),
    ("링크주소", "url"),
)  # fmt: skip

SPECS: Final[tuple[FileSpec, ...]] = (
    FileSpec("15089962", "자주 묻는 질문정보", _c(
        ("순번", "seq", "int"), ("일련번호", "post_id", "int"), ("카테고리", "category"), ("제목", "title"),
        ("내용", "content"), ("등록일", "reg_date", "date"),
    ), expected_rows=49),
    FileSpec("15090255", "정보목록데이터", _c(
        ("순서", "seq", "int"), ("제목", "title"), ("등록일", "reg_date", "date"), ("조회수", "views", "int"),
        ("파일경로", "file_url"),
    )),
    FileSpec("15090257", "사전정보공표 정보", _c(
        ("순번", "seq", "int"), ("사전정보공표분류 일련번호", "class_id", "int"),
        ("사전정보공표데이터 일련번호", "item_id", "int"), ("대분류", "major"), ("소분류", "minor"),
        ("제목", "title"), ("홈페이지링크", "url"), ("등록일", "reg_date", "date"),
    ), expected_rows=722),
    FileSpec("15090260", "사업실명제", _c(
        ("일련번호", "seq", "int"), ("사업실명제 일련번호", "item_id", "int"), ("등록번호", "reg_no", "int"),
        ("담당부서", "dept"), ("제목", "title"), ("파일경로", "file_path"), ("등록일", "reg_date", "date"),
    ), expected_rows=131),
    FileSpec("15090715", "올림픽공원 핫뉴스 정보", _c(
        ("순번", "seq", "int"), ("핫뉴스번호", "news_id", "int"), ("제목", "title"),
        ("시작일", "start_date", "date"), ("종료일", "end_date", "date"), ("홈페이지 주소", "url"),
        ("파일위치", "file_url"), ("등록일", "reg_date", "date"),
    )),
    FileSpec("15090719", "스케이트장 이벤트 정보", _c(
        ("순번", "seq", "int"), ("스케이트장이벤트일련번호", "event_id", "int"), ("제목", "title"),
        ("이벤트시작일자", "start_date", "date"), ("이벤트종료일자", "end_date", "date"),
        ("마감구분", "status"), ("파일경로", "file_url"), ("등록일자", "reg_date", "date"),
    )),
    FileSpec("15098997", "스포츠센터 이벤트 정보", _c(
        ("일련번호", "seq", "int"), ("이벤트 일련번호", "event_id", "int"), ("스포츠센터", "center"),
        ("제목", "title"), ("홈페이지링크", "url"), ("시작일", "start_date", "date"), ("종료일", "end_date", "date"),
        ("첨부링크", "attach_url"), ("등록일", "reg_date", "date"),
    )),
    FileSpec("15099006", "공연 포스터 정보", _c(
        ("일련번호", "seq", "int"), ("공연포스터 일련번호", "poster_id", "int"), ("제목", "title"),
        ("공연일", "perf", "date_in_text"), ("공연장소", "venue"), ("공연가수", "artist"),
        ("연결홈페이지주소", "url"), ("등록일", "reg_date", "date"), ("데이터 기준일", "base_date", "date"),
    )),
    FileSpec("15101610", "올림픽수영장 강좌정보", _COURSE_A),
    FileSpec("15110953", "올림픽스포츠센터 강좌정보", _c(
        ("일련번호", "seq", "int"), ("강좌일련번호", "course_no", "int"), ("강좌서브일련번호", "course_sub_no", "int"),
        ("수강월", "start_month", "date"), ("종목", "sport"), ("강좌명", "course_name"),
        ("수강시간", "time", "time_range"), ("정원", "capacity", "int"), ("수강요일", "days"),
        ("수강대상", "target"), ("수강금액", "fee", "int"), ("수강시작일", "period_start", "date"),
        ("수강종료일", "period_end", "date"),
    )),
    FileSpec("15114776", "일산스포츠센터 강좌정보", _COURSE_A),
    FileSpec("15118652", "분당스포츠센터 강좌정보", _c(
        ("일련번호", "seq", "int"), ("강좌번호", "course_no", "int"), ("시작월일", "start_month", "date"),
        ("종목", "sport"), ("강좌명", "course_name"), ("시작종료시간", "time", "time_range"),
        ("정원", "capacity", "int"), ("요일", "days"), ("강습반", "class_group"), ("금액", "fee", "int"),
        ("시작일", "period_start", "date"), ("종료일", "period_end", "date"),
    )),
    FileSpec("15119388", "온라인 강습 동영상", _c(
        ("순번", "seq", "int"), ("제목", "title"), ("등록일", "reg_date", "date"), ("조회수", "views", "int"),
        ("링크주소", "url"),
    )),
    FileSpec("15127487", "올림픽공원 공연장 실감형 콘텐츠", _c(
        ("순번", "seq", "int"), ("구분", "category"), ("장소", "place"), ("확장자", "file_ext"),
        ("파일명", "file_name"), ("홈페이지주소", "url"),
    )),
    FileSpec("15131671", "월별주차현황", _c(
        ("연도", "year", "int"), ("월", "month", "month_ko"), ("주차장소", "lot"), ("주차대수", "cars", "int"),
    ), expected_rows=72),
    FileSpec("15133891", "테니스장 이용 정보", _c(
        ("순번", "seq", "int"), ("구분", "member_type"), ("시작일", "start_date", "date"),
        ("종료일", "end_date", "date"), ("이용자수", "users", "int"),
    ), expected_rows=120),
    FileSpec("15137824", "보도자료배포현황", _c(
        ("배포일자", "release_date", "date"), ("배포내용", "title"), ("배포매체", "media"), ("사용여부", "in_use"),
    ), expected_rows=499),
    FileSpec("15137825", "언론보도현황", _c(
        ("보도일자", "report_date", "date"), ("보도내용", "title"), ("보도매체", "media"), ("사용여부", "in_use"),
    ), expected_rows=1958),
    FileSpec("15138735", "올림픽공원 입출차 정보", _c(
        ("입차일", "entry_date", "date"), ("입차일시", "entry_at", "datetime"), ("출차일시", "exit_at", "datetime"),
    ), expected_rows=215528, local_only=True),
    FileSpec("15143220", "잔디시설정보", _c(
        ("순서", "seq", "int"), ("장소", "place"), ("개방시간", "open_label"), ("개방내용", "open_detail"),
        ("링크", "url"),
    ), expected_rows=8),
    FileSpec("15144222", "정원현황", _c(
        ("기준일자", "base_date", "date"), ("부서명", "dept"), ("임원수", "executives", "int"),
        *((f"일반직{i}급", f"general_grade{i}", "int") for i in range(1, 9)),
        *((f"기술직{i}급", f"tech_grade{i}", "int") for i in range(1, 9)),
        ("업무직", "work_staff", "int"), ("계약직", "contract_staff", "int"), ("지원직", "support_staff", "int"),
    )),
    FileSpec("15144839", "스포츠센터 종목정보", _c(
        ("종목코드", "item_code"), ("종목명", "item_name"), ("시작 종료일", "valid", "date_range"),
        ("등록일", "reg_date", "date"),
    )),
    FileSpec("15147873", "공공데이터 개방목록", _c(
        ("파일데이터명", "dataset_name"), ("분류체계", "classification"), ("제공기관", "provider"),
        ("관리부서명", "dept"), ("키워드", "keywords"), ("제공형태", "provision"), ("설명", "description"),
        ("비용부과유무", "fee_type"), ("이용허락범위", "license"), ("등록일", "reg_date", "date"),
        ("수정일", "mod_date", "date"), ("링크주소", "url"),
    )),
    FileSpec("15147992", "스포츠센터 강좌 정보", _c(
        ("스포츠센터", "center"), ("강좌명", "course_name"), ("강좌설명", "description"), ("링크주소", "url"),
        ("등록일", "reg_date", "date"), ("수정일", "mod_date", "date"),
    )),
    FileSpec("15149169", "영문 공연정보", _c(
        ("일련번호", "item_id"), ("공연제목", "title"), ("조회수", "views", "int"), ("상세주소", "detail_url"),
        ("공연이미지", "image_url"), ("공연일자", "perf_date", "date"),
    )),
    # 포털 원본은 사진 zip(공공누리 4유형)뿐이라, 사용자가 만든 목록 CSV(zip 안 파일 이름을 나눈 것)를 적재한다.
    FileSpec("15160326", "비정형데이터_생태갤러리(목록)", _c(
        ("zip_path", "zip_path"), ("파일명_날짜", "photo_date", "yyyymmdd"), ("파일명_제목", "title"),
        ("bytes", "bytes", "int"),
    )),
    FileSpec("15161406", "공모참여 목록", _c(
        ("일련번호", "seq", "int"), ("제목", "title"), ("기관명", "org"), ("시작일", "start_date", "date"),
        ("종료일", "end_date", "date"), ("조회수", "views", "int"), ("공유수", "shares", "int"),
        ("썸네일", "thumbnail_url"), ("등록일", "reg_date", "date"), ("추천", "likes", "int"),
        ("비추천", "dislikes", "int"), ("상태", "status"),
    )),
    FileSpec("15164156", "주차장 혼잡도 정보", _c(
        ("일련번호", "seq", "int"), ("주차장아이디", "lot_id"), ("주차구역", "zone"), ("혼잡도", "congestion"),
        ("등록일", "reg_date", "date"), ("등록시간", "reg_hour", "hour_of_time"),
    ), expected_rows=699),
    FileSpec("15168248", "근무복 주문현황정보", _c(
        ("근무복코드", "item_code"), ("근무복명", "item_name"), ("사이즈", "size"), ("성별코드", "gender_code"),
        ("사용날짜", "use_date", "date"), ("주문수량", "qty", "int"),
    )),
    FileSpec("15168288", "근무복 주문현황", _c(
        ("주문일", "order_date", "date"), ("주문상태", "status"), ("계절구분", "season"), ("피복종류", "item_type"),
        ("사이즈", "size"), ("수량", "qty", "int"),
    )),
)  # fmt: skip

SPEC_BY_ID: Final[dict[str, FileSpec]] = {s.id: s for s in SPECS}
