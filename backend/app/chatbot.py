"""축제 RAG 챗봇 — '거짓말하지 않는' 설계.

원칙: **사실은 DB가, 말투는 AI가.**
  1. 의도 파악(규칙 기반): 주제(단풍·벚꽃·야간…)·시간(이번 주말/가을/12월)·지역·"과거 포함 여부"를 뽑는다. LLM 불필요 → 틀릴 일이 적다.
  2. 근거 검색: 키워드가 축제명/소개문에 '실제로 있는' 축제만 후보. 어떤 단어가 어디서 맞았는지(근거)를 함께 기록한다.
  3. 후보 0건이면 LLM 없이 "없어요"라고 답한다. 끝난 축제는 '추천'이 아니라 '지난 개최 참고'로만 보여준다.
  4. LLM은 후보별 '추천 이유' 한 문장만 쓴다. 축제명·날짜·장소·상태는 AI가 쓰지 않고 DB 값을 그대로 붙인다.
  5. 사실 대조 검증: 이유 문장의 숫자·다른 축제명·원문에 없는 위험 정보(가격·주차·예약…)·근거 없는 단어 비율을 검사하고,
     하나라도 걸리면 AI 문장을 버리고 근거 기반 템플릿 문장으로 대체한다.
  6. 데이터에 없는 정보(입장료·주차·교통·날씨…)를 물으면 "데이터에 없어요"를 결정적으로 안내한다.
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from app.models import FestivalRecord
from app.prompt_injection_defense import sanitize_output_text, sanitize_untrusted
from app.schemas import compute_status
from app.search import canonical_name, normalize

logger = logging.getLogger(__name__)

MAX_PICKS = 3

# --------------------------------------------------------------------------- 주제 사전


@dataclass(frozen=True)
class Topic:
    name: str
    triggers: tuple[str, ...]  # 사용자 말에서 이 단어가 보이면 이 주제
    terms: tuple[str, ...]  # 축제 데이터에서 찾을 단어(근거)


TOPICS: tuple[Topic, ...] = (
    Topic("단풍", ("단풍", "낙엽", "은행나무"), ("단풍", "낙엽", "은행", "억새", "국화")),
    Topic("벚꽃", ("벚꽃", "꽃길"), ("벚꽃", "꽃길")),
    Topic("꽃", ("꽃놀이", "꽃구경", "꽃축제", "장미", "튤립", "수국", "유채", "해바라기", "연꽃", "코스모스", "철쭉", "매화", "국화"),
          ("꽃축제", "장미", "튤립", "수국", "유채", "해바라기", "연꽃", "코스모스", "철쭉", "매화", "국화")),
    Topic("겨울", ("눈꽃", "눈썰매", "첫눈", "겨울", "얼음", "스키", "썰매", "송어", "산천어"),
          ("눈꽃", "눈썰매", "겨울", "얼음", "스키", "썰매", "송어", "산천어", "빙어", "빙판")),
    Topic("바다", ("바다", "해변", "해수욕", "갯벌", "머드", "일출", "해맞이", "해돋이", "항구", "포구"),
          ("바다", "해변", "해수욕", "갯벌", "머드", "일출", "해맞이", "해돋이", "항구", "포구", "수산", "해양")),
    Topic("먹거리", ("먹거리", "음식", "맛집", "먹방", "미식", "푸드", "요리", "맥주", "막걸리", "커피", "한우", "김치", "배고"),
          ("먹거리", "음식", "푸드", "요리", "맥주", "막걸리", "커피", "한우", "김치", "특산물", "미식")),
    Topic("불꽃·야경", ("불꽃", "야경", "야간", "조명", "빛축제", "등불", "유등", "드론", "라이트", "루미"),
          ("불꽃", "야간", "야경", "조명", "빛축제", "등불", "유등", "드론", "라이트", "점등")),
    Topic("음악·공연", ("음악", "콘서트", "공연", "재즈", "버스킹", "국악", "연주"),
          ("음악", "콘서트", "공연", "재즈", "버스킹", "국악", "연주", "뮤직")),
    Topic("전통", ("전통", "민속", "한복", "역사", "문화유산", "대보름", "달집", "탈춤", "농악", "사극"),
          ("전통", "민속", "한복", "역사", "문화유산", "대보름", "달집", "탈춤", "농악")),
    Topic("아이·가족", ("아이", "애기", "어린이", "가족", "아기", "유아", "키즈", "초등", "아들", "딸"),
          ("어린이", "가족", "키즈", "아이", "체험", "놀이")),
    Topic("데이트", ("데이트", "연인", "커플", "로맨틱", "감성"),
          ("야간", "야경", "조명", "불꽃", "음악", "공연", "전시", "정원", "감성", "빛")),
    Topic("체험", ("체험", "만들기", "직접"), ("체험", "만들기", "참여")),
    Topic("자연", ("자연", "숲", "산책", "호수", "생태", "나비", "곤충", "습지", "억새"),
          ("자연", "숲", "산책", "호수", "생태", "나비", "곤충", "습지", "억새", "공원")),
    Topic("전시·예술", ("전시", "미술", "예술", "사진전", "영화"), ("전시", "미술", "예술", "사진", "영화")),
    Topic("스포츠", ("마라톤", "달리기", "자전거", "걷기", "스포츠", "트레킹", "대회"), ("마라톤", "달리기", "자전거", "걷기", "스포츠", "트레킹", "대회")),
)

# 이 주제들은 연관어(억새·국화 등)만으로는 후보가 될 수 없다: 사용자가 말한 '그것'이 실제로 있어야 한다
CORE_TERMS: dict[str, tuple[str, ...]] = {"단풍": ("단풍", "낙엽", "은행"), "벚꽃": ("벚꽃", "꽃길")}

# 데이터(공공 축제 표준데이터)에 없는 정보 → 물으면 결정적으로 안내
UNSUPPORTED = {
    "입장료·가격": ("가격", "입장료", "요금", "얼마", "무료", "유료", "할인", "티켓", "비용"),
    "주차": ("주차",),
    "예약": ("예약", "신청방법"),
    "교통·길찾기": ("교통", "버스", "지하철", "셔틀", "가는법", "가는 법", "길찾기"),
    "날씨": ("날씨", "기온", "비 오", "우천"),
    "운영시간": ("운영시간", "몇 시", "몇시", "영업시간", "개장"),
    "연락처": ("전화", "연락처", "문의"),
    "숙박": ("숙소", "숙박", "호텔"),
}

_STOP = {
    "축제", "행사", "추천", "알려", "알려줘", "알려주세요", "있어", "있나", "있는", "어디", "가고", "싶어", "싶은", "보고", "보러",
    "좋은", "좋아", "뭐", "해줘", "하는", "가볼", "만한", "같이", "근처", "쪽", "곳", "거", "것", "좀", "정말", "진짜", "요즘",
    "지금", "이번", "다음", "오늘", "내일", "주말", "다른", "더", "또", "아무거나", "랜덤", "심심", "갈만한", "갈", "볼", "해", "해요",
    "찾아", "찾아줘", "보여줘", "보여", "있을까", "있을까요", "어때", "어떤", "무슨", "가면", "가기", "가자", "추천해줘", "추천해", "없어",
    "작년", "지난", "끝난", "올해", "내년", "혼자", "친구", "우리", "나", "내가", "저", "제가", "에서", "으로",
}
_PARTICLES = "을를이가은는도에의로과와만"
_VERBISH = (
    "하는", "하고", "하면", "하세요", "싶어", "싶은", "있는", "있어", "있나", "열리는", "열리고", "열려", "열린", "보고", "보러", "가고",
    "가면", "갈만", "만한", "해줘", "피어", "피는", "핀", "있는데", "해요", "알려", "추천", "찾아", "어때", "할까", "있을까", "많은", "좋은", "예쁜", "재밌", "즐기", "즐길",
)

_SEASONS = {"봄": (3, 5), "여름": (6, 8), "가을": (9, 11), "겨울": (12, 2)}
_PAST_WORDS = ("작년", "지난", "끝난", "예전", "과거", "이미 끝", "재작년")
_MORE_WORDS = ("더 보여", "다른 거", "다른거", "또 추천", "다른 것", "더 추천", "더 알려", "다른 축제")
_RANDOM_WORDS = ("아무거나", "랜덤", "심심", "뭐 하지", "뭐하지", "뭐 할까", "뭐할까", "골라줘", "알아서")

_PROVINCES = (
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    "충청", "전라", "경상",
)


# --------------------------------------------------------------------------- 의도 파악


@dataclass
class Window:
    start: date
    end: date
    label: str


@dataclass
class Intent:
    topics: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)  # 근거로 찾을 단어(주제 단어 + 사용자가 쓴 고유 단어)
    core_terms: list[str] = field(default_factory=list)  # 이 중 하나는 반드시 있어야 하는 단어
    primary: list[str] = field(default_factory=list)  # 사용자가 직접 쓴 단어(가중치 높음)
    region: str | None = None
    window: Window | None = None
    include_past: bool = False
    random: bool = False
    wants_more: bool = False
    unsupported: list[str] = field(default_factory=list)

    @property
    def has_subject(self) -> bool:
        return bool(self.terms or self.region or self.window)


def _season_window(name: str, today: date) -> Window:
    s_m, e_m = _SEASONS[name]
    for year in (today.year - 1, today.year, today.year + 1):
        start = date(year, s_m, 1)
        end_year = year + 1 if e_m < s_m else year
        end_month = e_m
        nxt = date(end_year + (end_month == 12), (end_month % 12) + 1, 1)
        end = nxt - timedelta(days=1)
        if end >= today:
            return Window(max(start, today), end, f"{name}철({start.month}월~{end.month}월)")
    raise AssertionError("unreachable")


def _month_window(month: int, today: date) -> Window:
    year = today.year if month >= today.month else today.year + 1
    start = date(year, month, 1)
    end = (date(year + (month == 12), (month % 12) + 1, 1)) - timedelta(days=1)
    return Window(max(start, today), end, f"{month}월")


def parse_window(msg: str, today: date) -> Window | None:
    if "내일" in msg:
        d = today + timedelta(days=1)
        return Window(d, d, "내일")
    if "오늘" in msg:
        return Window(today, today, "오늘")
    if "이번 주말" in msg or "주말" in msg:
        sat = today + timedelta(days=(5 - today.weekday()) % 7) if today.weekday() < 5 else today - timedelta(days=today.weekday() - 5)
        sat = max(sat, today)
        sun = sat + timedelta(days=1) if sat.weekday() == 5 else sat
        return Window(sat, sun, f"이번 주말({sat:%m/%d}~{sun:%m/%d})")
    if "이번 주" in msg:
        end = today + timedelta(days=6 - today.weekday())
        return Window(today, end, "이번 주")
    if "다음 달" in msg or "다음달" in msg:
        first = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        end = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        return Window(first, end, "다음 달")
    if "이번 달" in msg or "이번달" in msg:
        end = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        return Window(today, end, "이번 달")
    m = re.search(r"(1[0-2]|[1-9])\s*월", msg)
    if m:
        return _month_window(int(m.group(1)), today)
    for name in _SEASONS:
        if name in msg:
            return _season_window(name, today)
    if re.search(r"지금|요즘|현재|진행\s*중|열리고", msg):
        return Window(today, today, "지금")
    return None


def known_regions(records: list[FestivalRecord]) -> list[str]:
    """데이터에 등장하는 시·군·구·도 이름(접미사 제거본, 2글자 이상) + 광역 약칭."""
    names: set[str] = set(_PROVINCES)
    for r in records:
        for tok in r.rdnmadr.split():
            if tok.endswith(("특별시", "광역시", "특별자치시", "특별자치도")):
                continue
            if len(tok) >= 3 and tok[-1] in "시군구":
                names.add(tok[:-1])
    return sorted((n for n in names if len(n) >= 2), key=len, reverse=True)


def parse_intent(message: str, today: date, regions: list[str], doc_freq: Callable[[str], float] | None = None) -> Intent:
    msg = message.strip()
    it = Intent()
    it.include_past = any(w in msg for w in _PAST_WORDS)
    it.wants_more = any(w in msg for w in _MORE_WORDS)
    it.random = any(w in msg for w in _RANDOM_WORDS)
    it.window = parse_window(msg, today)
    for topic in TOPICS:
        trig = [t for t in topic.triggers if t in msg]
        if trig:
            it.topics.append(topic.name)
            it.primary += [t for t in trig if t not in it.primary]
            for term in topic.terms:
                if term not in it.terms and len(term) >= 2:
                    it.terms.append(term)
            it.core_terms += [t for t in CORE_TERMS.get(topic.name, ()) if t not in it.core_terms]
    # 엄격한 주제(단풍·벚꽃)가 있으면, 사용자가 직접 쓴 구체적 단어(예: 억새)도 '그것이 실제로 있는' 근거로 인정한다
    if it.core_terms:
        it.core_terms += [p for p in it.primary if len(p) >= 2 and p not in it.core_terms]
    for label, words in UNSUPPORTED.items():
        if any(w in msg for w in words):
            it.unsupported.append(label)
    for r in regions:
        if r in msg:
            it.region = r
            break
    # 사용자가 쓴 고유 단어(예: '산천어', '머드') 중 주제/지역/불용어가 아닌 것도 근거 검색어로 쓴다
    known = {*it.primary, *(r for r in [it.region] if r)}
    for tok in re.findall(r"[가-힣]{2,}", msg):
        base = tok[:-1] if len(tok) >= 3 and tok[-1] in _PARTICLES else tok
        if any(v in tok for v in _VERBISH) or base in _STOP or tok in _STOP or base in known or any(base in w or w in base for w in known):
            continue
        if any(w in tok for w in ("월", "주말", "내일", "오늘", "이번", "다음")) or tok in _SEASONS:
            continue
        if base in _SEASONS or base == (it.region or ""):
            continue
        if any(base.startswith(u) for words in UNSUPPORTED.values() for u in words):
            continue
        if doc_freq is not None and doc_freq(base) > 0.05:
            continue  # '하고', '체험' 같은 흔한 말은 변별력이 없다
        if base not in it.terms and len(base) >= 2:
            it.terms.append(base)
            it.primary.append(base)
    return it


def merge_intent(prev: Intent | None, cur: Intent) -> Intent:
    """후속 질문('부산은?', '더 보여줘')은 직전 사용자 질문의 주제·시간·지역을 이어받는다."""
    if prev is None:
        return cur
    if not cur.terms and not cur.window and not cur.region:
        merged = Intent(**{**prev.__dict__})
        merged.wants_more = cur.wants_more or merged.wants_more
        merged.unsupported = cur.unsupported
        merged.random = cur.random
        return merged
    if not cur.terms and (cur.region or cur.window):
        cur.terms, cur.topics, cur.primary, cur.core_terms = list(prev.terms), list(prev.topics), list(prev.primary), list(prev.core_terms)
    if not cur.window and prev.window:
        cur.window = prev.window
    if not cur.region and prev.region and cur.terms == prev.terms:
        cur.region = prev.region
    cur.include_past = cur.include_past or prev.include_past
    return cur


# --------------------------------------------------------------------------- 근거 검색


@dataclass
class Candidate:
    record: FestivalRecord
    status: str | None
    score: float
    evidence: list[str]
    kind: str  # 'active' | 'past'


_CANCELLED = ("행사 취소", "행사취소", "취소됨", "취소되었", "취소되어", "미개최", "개최 취소", "운영 중단", "폐지", "개최하지 않")


def is_cancelled(r: FestivalRecord) -> bool:
    text = r.fstvl_nm + " " + r.fstvl_co
    return any(w in text for w in _CANCELLED)


def _source_text(r: FestivalRecord) -> str:
    return " ".join(x for x in (r.fstvl_nm, r.opar, r.rdnmadr, r.fstvl_co) if x)


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        return None


def _dates(r: FestivalRecord) -> tuple[date, date] | None:
    start, end = _parse_date(r.fstvl_start_date), _parse_date(r.fstvl_end_date)
    start = start or end
    end = end or start
    return (start, end) if start and end else None


def _overlaps(r: FestivalRecord, w: Window) -> bool:
    d = _dates(r)
    return bool(d and d[0] <= w.end and d[1] >= w.start)


def _neg_date(s: str) -> int:
    """날짜가 최근일수록 작은 값(오름차순 정렬 시 최근 먼저)."""
    d = _parse_date(s)
    return -d.toordinal() if d else 0


def evidence_for(r: FestivalRecord, terms: list[str], primary: list[str] | tuple[str, ...] = ()) -> tuple[float, list[str]]:
    """(관련도 점수, 근거 문장들). 축제명에 있으면 3점, 소개문/장소에 있으면 1점.
    사용자가 직접 쓴 단어(primary)는 그대로, 주제 사전이 덧붙인 확장어는 절반만 반영한다."""
    score, ev = 0.0, []
    name, rest = r.fstvl_nm, " ".join((r.opar, r.fstvl_co))
    for t in terms:
        w = 1.0 if t in primary else 0.5
        if t in name:
            score += 3 * w
            ev.append((w, f"축제명에 ‘{t}’"))
        elif t in rest:
            score += 1 * w
            ev.append((w, f"소개문에 ‘{t}’" if t in r.fstvl_co else f"장소에 ‘{t}’"))
    ev.sort(key=lambda x: -x[0])  # 사용자가 직접 쓴 단어에 맞은 근거를 먼저
    return score, [e for _, e in ev][:3]


def retrieve(
    records: list[FestivalRecord],
    intent: Intent,
    today: date,
    *,
    exclude_ids: frozenset[str] = frozenset(),
    vec_scores: dict[str, float] | None = None,
    rng: random.Random | None = None,
    limit: int = MAX_PICKS,
) -> tuple[list[Candidate], list[Candidate]]:
    """(추천 후보, 지난 개최 참고) 를 돌려준다. 근거 단어가 실제로 맞은 축제만 포함한다."""
    vec_scores = vec_scores or {}
    active: list[Candidate] = []
    past: list[Candidate] = []
    for r in records:
        if r.id in exclude_ids:
            continue
        status = compute_status(r.fstvl_start_date, r.fstvl_end_date, today)
        if status is None:
            continue
        if intent.region and intent.region not in (r.rdnmadr + " " + r.opar):
            continue
        if intent.terms:
            score, ev = evidence_for(r, intent.terms, intent.primary)
            # 사용자가 직접 쓴 단어가 맞으면 가중
            score += sum(2 for t in intent.primary if t in r.fstvl_nm)
            if score <= 0:
                continue
            if intent.core_terms and not any(t in (r.fstvl_nm + r.fstvl_co + r.opar) for t in intent.core_terms):
                continue
        else:
            score, ev = 0.0, []
        score += 2.0 * vec_scores.get(r.id, 0.0)
        if status == "완료":
            past.append(Candidate(r, status, score, ev, "past"))
            continue
        if is_cancelled(r):  # 취소된 행사는 '추천'하지 않는다
            continue
        if intent.window and not _overlaps(r, intent.window):
            continue
        active.append(Candidate(r, status, score, ev, "active"))

    order = {"진행중": 0, "예정": 1}

    def start_key(c: Candidate) -> str:
        return c.record.fstvl_start_date or "9999"

    if intent.random and not intent.terms:
        pool = sorted(active, key=lambda c: (order.get(c.status or "", 2), start_key(c)))[:40]
        (rng or random.Random()).shuffle(pool)
        active = pool
    else:
        def duration_bucket(c: Candidate) -> int:
            d = _dates(c.record)
            days = (d[1] - d[0]).days if d else 999
            return 0 if days <= 7 else 1 if days <= 40 else 2  # 상시·장기 행사는 '이번 주말' 같은 요청에 덜 어울린다

        active.sort(key=lambda c: (-c.score, duration_bucket(c), order.get(c.status or "", 2), start_key(c), c.record.id))
        if intent.terms and active:
            top = active[0].score
            active = [c for c in active if c.score >= 0.4 * top]
    def dedupe(items: list[Candidate]) -> list[Candidate]:
        """같은 축제의 회차·연도 변형(예: 제29회/2026 보령머드축제)은 앞선(상위) 하나만 남긴다."""
        seen: set[str] = set()
        out: list[Candidate] = []
        for c in items:
            key = normalize(canonical_name(c.record.fstvl_nm))
            if key not in seen:
                seen.add(key)
                out.append(c)
        return out

    # 지난 개최: 관련도 높은 순, 같으면 최근 개최 먼저
    past.sort(key=lambda c: (-c.score, _neg_date(c.record.fstvl_start_date), c.record.id))
    if intent.terms and past:
        ptop = past[0].score
        past = [c for c in past if c.score >= 0.4 * ptop]
    uniq, past_u = dedupe(active), dedupe(past)
    return uniq[:limit], past_u[:limit]


# --------------------------------------------------------------------------- 사실 대조 검증

_RISKY = ("무료", "유료", "입장료", "주차", "예약", "셔틀", "할인", "반려", "와이파이", "휠체어", "수유", "전화", "현장 판매", "사전 신청")
_GENERIC = {
    "축제", "행사", "추천", "즐길", "수", "있어요", "있는", "있답니다", "만나", "볼", "만날", "함께", "가족", "여러분", "방문", "분위기",
    "다양한", "열리는", "열려요", "열립니다", "진행", "프로그램", "체험", "이벤트", "공연", "먹거리", "경험", "느껴", "느낄", "좋아요",
    "좋은", "곳", "곳에서", "에서", "있습니다", "즐겨", "보세요", "해보세요", "어때요", "특별한", "멋진", "재미", "재밌는", "즐거운", "한번",
    "이곳", "이", "그", "더", "또", "많은", "풍성한", "준비", "마련", "기대", "추억", "시간", "하루", "나들이", "산책", "지금", "곧",
    "매력", "봄", "여름", "가을", "겨울", "낭만", "감성", "힐링", "활기", "즐거움", "볼거리", "먹을거리", "즐길거리", "다채로운", "풍경",
    "느낄", "느끼", "느껴", "만끽", "열려요", "열리며", "열리고", "펼쳐", "펼쳐져요", "있어요", "있고", "있으며", "예요", "이에요", "입니다",
}
_NUM = re.compile(r"\d+")
_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")


def _source_numbers(r: FestivalRecord) -> set[int]:
    own_dates = f"{r.fstvl_start_date} {r.fstvl_end_date}"  # 이 축제 자신의 일정은 언급해도 사실이다
    return {int(n) for n in _NUM.findall(_source_text(r) + " " + own_dates)}


def _supported(token: str, source: str) -> bool:
    if token in _GENERIC or token in source:
        return True
    for cut in (1, 2):
        if len(token) - cut >= 2 and (token[:-cut] in source or token[:-cut] in _GENERIC):
            return True
    return False


def verify_reason(text: str, cand: Candidate, other_names: list[str]) -> tuple[bool, str]:
    """AI가 쓴 추천 이유가 원문에 근거하는지 검사. (통과 여부, 실패 사유)"""
    r = cand.record
    source = _source_text(r)
    if len(text) > 100:
        return False, "too_long"
    nums = {int(n) for n in _NUM.findall(text)}
    if nums - _source_numbers(r):
        return False, "number_not_in_source"
    for w in _RISKY:
        if w in text and w not in source:
            return False, f"risky:{w}"
    for n in other_names:
        if n in text and n not in r.fstvl_nm:
            return False, "other_festival_name"
    toks = [t for t in _TOKEN.findall(text) if not any(ch.isdigit() for ch in t)]  # 숫자는 위에서 따로 검증
    if toks:
        unsupported = [t for t in toks if not _supported(t, source)]
        # 근거 없는 내용어가 2개 이상이거나 30% 초과면 지어낸 문장으로 본다
        if len(unsupported) >= 2 or len(unsupported) / len(toks) > 0.3:
            return False, "unsupported_words"
    return True, ""


def _josa(word: str, yes: str, no: str) -> str:
    """받침 유무에 따라 조사 선택 (이/가, 은/는 …)"""
    ch = word[-1]
    if "가" <= ch <= "힣":
        return yes if (ord(ch) - 0xAC00) % 28 else no
    return no


def template_reason(c: Candidate) -> str:
    """근거 기반 결정적 문장 (AI 문장이 검증에 실패했을 때)."""
    if c.evidence:
        m = re.match(r"(.+?)에 ‘(.+?)’", c.evidence[0])
        if m:
            where, kw = m.groups()
            return f"{where}에 ‘{kw}’{_josa(kw, '이', '가')} 있는 축제예요."
        return f"{c.evidence[0]} 축제예요."
    return "조건에 맞는 일정의 축제예요."


def verify_intro(text: str, picks: list[Candidate], other_names: list[str], window: Window | None) -> bool:
    if len(text) > 160:
        return False
    allowed: set[int] = set()
    if window:
        for d in (window.start, window.end):
            allowed |= {d.year, d.month, d.day}
    for c in picks:
        allowed |= _source_numbers(c.record)
    if {int(n) for n in _NUM.findall(text)} - allowed:
        return False
    if any(n in text and not any(n in c.record.fstvl_nm for c in picks) for n in other_names):
        return False
    return not any(w in text for w in _RISKY)


# --------------------------------------------------------------------------- 응답 조립


@dataclass
class Pick:
    candidate: Candidate
    reason: str
    ai_written: bool


@dataclass
class ChatReply:
    answer: str
    picks: list[Pick]
    notes: list[str]
    suggestions: list[str]
    grounded: bool = True
    debug: dict = field(default_factory=dict)


LLM = Callable[[str, str, str, dict], dict]

_SCHEMA = {
    "type": "object",
    "properties": {"reasons": {"type": "array", "items": {"type": "string"}}},
    "required": ["reasons"],
}

_EMOJI = {"단풍": "🍁", "벚꽃": "🌸", "꽃": "🌷", "겨울": "❄️", "바다": "🌊", "먹거리": "🍜", "불꽃·야경": "🎆", "음악·공연": "🎵",
          "전통": "🏮", "아이·가족": "🧒", "데이트": "💕", "체험": "🛠️", "자연": "🌿", "전시·예술": "🖼️", "스포츠": "🏃"}


def _intro(intent: Intent, n: int) -> str:
    emoji = next((_EMOJI[t] for t in intent.topics if t in _EMOJI), "🎉")
    # 사용자가 쓴 말을 우선 사용한다 ('해맞이'를 '바다'로 바꿔 부르지 않는다). 시기 표현과 겹치는 단어는 뺀다.
    words = [w for w in intent.primary[:2] if not (intent.window and w in intent.window.label)] or intent.topics[:1]
    bits = [x for x in (intent.region, intent.window.label if intent.window else None, "·".join(words)) if x]
    what = " ".join(bits) or "조건"
    return f"{what}에 맞는 축제를 {n}곳 찾았어요 {emoji}"


def _candidate_block(cands: list[Candidate]) -> str:
    lines = []
    for i, c in enumerate(cands, 1):
        r = c.record
        name, _ = sanitize_untrusted(r.fstvl_nm, 100)
        co, _ = sanitize_untrusted(r.fstvl_co, 300)
        place, _ = sanitize_untrusted(r.opar or r.rdnmadr, 80)
        lines.append(f"{i}. 축제명: {name} | 기간: {r.fstvl_start_date}~{r.fstvl_end_date} | 장소: {place} | 소개: {co} | 근거: {', '.join(c.evidence) or '없음'}")
    return "\n".join(lines)


def _default_llm(task: str, data: str, instruction: str, schema: dict) -> dict:
    from app.ai_service import guarded_json

    return guarded_json(task, data, instruction, schema, num_predict=450, temperature=0.4)


def _suggestions(intent: Intent, has_results: bool) -> list[str]:
    base = ["이번 주말 갈 만한 축제", "아이랑 체험하기 좋은 축제", "야경이 예쁜 축제", "🎲 아무거나 추천"]
    if intent.topics and has_results:
        base = ["더 보여줘", *base]
    return base[:4]


def respond(
    message: str,
    *,
    previous_user_messages: list[str],
    records: list[FestivalRecord],
    today: date,
    exclude_ids: frozenset[str] = frozenset(),
    vec_scores: dict[str, float] | None = None,
    llm: LLM | None = None,
    rng: random.Random | None = None,
) -> ChatReply:
    regions = known_regions(records)
    texts = [_source_text(r) for r in records]

    def doc_freq(word: str) -> float:
        return sum(word in t for t in texts) / max(1, len(texts))

    prev: Intent | None = None
    for m in previous_user_messages:  # 오래된 것부터 차례로 이어받는다
        prev = merge_intent(prev, parse_intent(m, today, regions, doc_freq))
    intent = merge_intent(prev, parse_intent(message, today, regions, doc_freq))

    notes: list[str] = []
    if intent.unsupported:
        notes.append(
            f"축제 공공데이터에는 {', '.join(intent.unsupported)} 정보가 없어서 알려드릴 수 없어요. 공식 홈페이지나 주최 측에 확인해 주세요."
        )

    if not intent.has_subject and not intent.random:
        return ChatReply(
            "어떤 축제를 찾고 계세요? 계절(가을·겨울), 주제(단풍·벚꽃·야경·먹거리), 지역, 시기(이번 주말)를 알려 주세요 🙂",
            [], notes, _suggestions(intent, False), grounded=True, debug={"intent": intent.__dict__},
        )

    cands, past = retrieve(records, intent, today, exclude_ids=exclude_ids, vec_scores=vec_scores, rng=rng)
    subject = "·".join(intent.primary[:2] or intent.topics[:2]) or (intent.region or "")
    where = f" {intent.region}" if intent.region and intent.region not in subject else ""
    when = f" {intent.window.label}" if intent.window and intent.window.label != "지금" else ""

    if not cands:
        if past:
            notes.append(
                f"지금 열리고 있거나 예정된{where}{when} {subject} 축제는 데이터에 없어요. "
                "아래는 이미 끝난 지난 축제예요. 매년 비슷한 시기에 열리는 경우가 많지만, 내년 일정은 아직 정해지지 않았을 수 있으니 공식 정보를 확인하세요."
            )
            picks = [Pick(c, template_reason(c), False) for c in past]
            return ChatReply("조건에 딱 맞는 현재 진행·예정 축제는 찾지 못했어요 😥 대신 지난 개최 기록을 보여드릴게요.", picks, notes, _suggestions(intent, True), True, {"intent": intent.__dict__})
        notes.append(f"{where}{when} {subject}".strip() + " 조건에 맞는 축제를 데이터에서 찾지 못했어요.")
        return ChatReply("앗, 조건에 맞는 축제를 찾지 못했어요. 지어내서 말씀드리진 않을게요! 조건을 조금 바꿔 볼까요?", [], notes, _suggestions(intent, False), True, {"intent": intent.__dict__})

    # ---- 후보가 있을 때만 LLM에게 '이유 문장'을 맡긴다
    all_names = [canonical_name(r.fstvl_nm) for r in records if len(canonical_name(r.fstvl_nm)) >= 4]
    reasons: list[str] = []
    debug: dict = {"intent": intent.__dict__, "rejections": []}
    try:
        data = (llm or _default_llm)(
            "후보 축제 각각의 추천 이유를 한 문장씩 쓴다.",
            f"사용자 요청 해석: 주제={subject or '없음'}, 시기={intent.window.label if intent.window else '미지정'}, 지역={intent.region or '미지정'}\n후보:\n{_candidate_block(cands)}",
            f"JSON으로만 답해. reasons: 후보 번호 순서대로 {len(cands)}개, 각 문장은 해당 후보의 '소개'나 '근거'에 있는 내용만 써서 40자 이내의 완결된 문장(~요/~예요 체)으로. "
            "후보에 없는 정보(가격, 주차, 예약, 날씨, 다른 축제)는 쓰지 마.",
            _SCHEMA,
        )
        raw_reasons = data.get("reasons") if isinstance(data.get("reasons"), list) else []
        reasons = [sanitize_output_text(x, 100) or "" for x in raw_reasons]
    except Exception as exc:  # AI 장애는 챗봇 장애가 아니다: 템플릿으로 계속
        logger.warning("chatbot llm failed: %s", type(exc).__name__)
        debug["llm_error"] = type(exc).__name__

    picks: list[Pick] = []
    for i, c in enumerate(cands):
        text = reasons[i] if i < len(reasons) else ""
        ok, why = verify_reason(text, c, all_names) if text else (False, "empty")
        if not ok:
            debug["rejections"].append({"festival": c.record.fstvl_nm, "reason": text, "why": why})
        picks.append(Pick(c, text if ok else template_reason(c), ok))

    intro = _intro(intent, len(picks))
    if any(c.status == "예정" or c.status == "진행중" for c in cands):
        notes.append("일정은 변경될 수 있어요. 방문 전에 공식 안내를 꼭 확인하세요.")
    return ChatReply(intro, picks, notes, _suggestions(intent, True), True, debug)
