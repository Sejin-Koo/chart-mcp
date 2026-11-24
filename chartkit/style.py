"""디자인 기본값 — 계정 보고서 그림 규칙(ref-report-visualization 3·4절, sys-file-builder chart-png.py)과 같게 둔다.

- 기본 3색(의미 배정): 남색 main · 청록 detail · 주황 compare. 계열이 넷 이상이거나 원·도넛이면 보라·황토·자주를 이어 쓴다(6색 검증 통과).
- 색을 돌려 쓰지 않는다 — 6색을 넘는 범주는 '기타'로 묶도록 안내한다.
- 크기: 보고서 본문 폭 16cm, 220dpi, 기본 글자 9pt. 범례는 그림 위쪽 한 줄(색의 의미), 격자는 연회색.
- 국내 금융 관례: 상승 빨강, 하락 파랑.
"""
from __future__ import annotations

NAVY = "#2E5395"
TEAL = "#2A9478"
ORANGE = "#D2601A"
PURPLE = "#7B4FA8"
OCHRE = "#B5892E"
MAGENTA = "#C2477A"
PALETTE = [NAVY, TEAL, ORANGE, PURPLE, OCHRE, MAGENTA]
ROLE = {"main": NAVY, "detail": TEAL, "compare": ORANGE, "navy": NAVY, "teal": TEAL, "orange": ORANGE, "gray": "#7F7F7F"}

INK = "#262626"
INK2 = "#404040"
MUTED = "#7F7F7F"
GRID = "#E5E5E5"
# 주 눈금선: 연한 회색(Excel '배경 1, 15% 더 어둡게' = D9D9D9) 실선 — 사용자 지정 2026-11-24(엑셀·PPT·Word·채팅 그림 통일)
GRID_LINE = "#D9D9D9"
GRID_KW = {"color": GRID_LINE, "linestyle": "-", "linewidth": 0.8}
AXIS = "#BFBFBF"
GRAY = "#BFBFBF"
LIGHT = "#F2F2F2"
UP = "#C0392B"     # 상승 빨강
DOWN = "#2E5395"   # 하락 파랑(남색과 같게)
GOOD = "#2A9478"
WARN = "#D2601A"
BAD = "#C0392B"

# 순차형(크기) — 남색 한 색의 명도 단계. 발산형(±) — 파랑↔주황 + 회색 중간
SEQUENTIAL = ["#EEF2F9", "#D5DEEF", "#B7C7E3", "#95ACD5", "#7391C6", "#5677B5", "#3F62A5", "#2E5395", "#244379", "#1A335D"]
DIVERGING = ["#2E5395", "#F2F2F2", "#D2601A"]   # 음(-) · 0 · 양(+)

WIDTH_IN = 16 / 2.54      # 보고서 본문 폭 16cm
DPI = 220
FONT_SIZE = 9
LABEL_SIZE = 8.2
MAX_COLORS = len(PALETTE)


def color(c, default: str = NAVY) -> str:
    """'main'·'2E5395'·'#2E5395' 모두 받는다."""
    if not c:
        return default
    s = str(c).strip()
    if s.lower() in ROLE:
        return ROLE[s.lower()]
    s = s.lstrip("#")
    if len(s) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in s):
        return "#" + s.upper()
    return default


def palette(n: int, *, wide: bool = False) -> list[str]:
    """n개 색. 셋 이하는 기본 3색, 그보다 많거나 wide면 6색. 6색을 넘으면 회색 단계로 채운다(호출자가 경고)."""
    base = PALETTE if (wide or n > 3) else PALETTE[:3]
    if n <= len(base):
        return base[:n]
    extra = ["#8C8C8C", "#A6A6A6", "#595959", "#BFBFBF"]
    return (base + extra * 4)[:n]


def seq(n: int) -> list[str]:
    pool = SEQUENTIAL[2:]
    if n <= 1:
        return [pool[len(pool) // 2]]
    return [pool[round(i * (len(pool) - 1) / (n - 1))] for i in range(n)]


def ink_on(hexc: str) -> str:
    """막대 색 위 숫자 색 — 밝은 색이면 진한 회색, 어두운 색이면 흰색(chart-spec.js inkOn과 같은 식)."""
    h = str(hexc or "").lstrip("#")
    if len(h) != 6:
        return "#FFFFFF"
    c = []
    for i in (0, 2, 4):
        v = int(h[i:i + 2], 16) / 255
        c.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return INK if 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] > 0.36 else "#FFFFFF"


def fmt(v, decimals: int | None = None) -> str:
    if v is None:
        return ""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if decimals is None:
        decimals = 0 if abs(v) >= 100 or v.is_integer() else (1 if abs(v) >= 1 else 2)
    return f"{v:,.{decimals}f}"
