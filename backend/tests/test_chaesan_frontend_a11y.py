"""화면 색 대비 검사(WCAG AA 본문 4.5:1): base.css의 색 변수를 읽어 밝은·어두운 모드 모두에서 글자와 바탕의 대비를 계산한다.

색을 바꿨을 때 읽기 어려운 조합이 생기면 여기서 바로 알 수 있다(사람 눈이나 도구에 기대지 않는다).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[2] / "frontend" / "css" / "base.css").read_text(encoding="utf-8")
LANES = ("history", "facility", "news", "org", "data")


def _blocks() -> tuple[dict[str, str], dict[str, str]]:
    root = re.search(r":root \{(.*?)\n\}", CSS, re.DOTALL)
    dark = re.search(r"prefers-color-scheme: dark\) \{\s*:root \{(.*?)\n  \}", CSS, re.DOTALL)
    assert root and dark
    parse = lambda body: dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", body))  # noqa: E731
    light = parse(root.group(1))
    return light, {**light, **parse(dark.group(1))}  # 어두운 모드는 밝은 모드 값 위에 덮어쓴다


def _rgb(hex6: str) -> tuple[float, float, float]:
    return tuple(int(hex6[i : i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def _lum(rgb: tuple[float, float, float]) -> float:
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _mix(a: tuple[float, float, float], b: tuple[float, float, float], share: float) -> tuple[float, float, float]:
    """color-mix(in srgb, a share%, b)와 같다(CSS가 배지·칩 바탕을 만드는 방식)."""
    return tuple(x * share + y * (1 - share) for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


@pytest.mark.parametrize("mode", [0, 1], ids=["light", "dark"])
def test_text_pairs_meet_aa(mode: int) -> None:
    v = _blocks()[mode]
    c = lambda name: _rgb(v[name])  # noqa: E731
    pairs = {
        "본문/바탕": (c("ink"), c("bg")),
        "본문/카드": (c("ink"), c("surface")),
        "보조 글자/바탕": (c("sub"), c("bg")),
        "보조 글자/카드": (c("sub"), c("surface")),
        "보조 글자/연한 칩": (c("sub"), c("surface-2")),
        "링크·강조/카드": (c("brand"), c("surface")),
        "단추 글자/단추": (c("brand-ink"), c("brand")),
        "주의 글자/주의 바탕": (c("warn"), c("warn-bg")),
        "오류 글자/오류 바탕": (c("err"), c("err-bg")),
        "본문/강조 연한 바탕": (c("ink"), c("brand-soft")),
    }
    for lane in LANES:  # 갈래 글자는 갈래 색을 13~15% 섞은 칩·아이콘 바탕 위에 놓인다
        pairs[f"갈래 {lane}/칩"] = (c(f"lane-{lane}"), _mix(c(f"lane-{lane}"), c("surface"), 0.15))
        pairs[f"갈래 {lane}/카드"] = (c(f"lane-{lane}"), c("surface"))
    failed = {name: round(_ratio(*pair), 2) for name, pair in pairs.items() if _ratio(*pair) < 4.5}
    assert not failed, f"대비 4.5:1 미만: {failed}"
