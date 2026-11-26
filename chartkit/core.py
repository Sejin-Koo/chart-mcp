"""matplotlib 공통: 글꼴(맑은 고딕)·그림 크기·축 꾸미기·범례·숫자 라벨·PNG 변환.

- 그림 안에는 제목을 넣지 않는 것이 기본이다. 보고서·화면이 그림 밖에 "[그림 N] 제목"을 단다.
  options.show_title=true면 그림 왼쪽 위에 제목·부제를 넣는다.
- matplotlib은 스레드 안전하지 않으므로 그리기는 전역 잠금 안에서 한다.
"""
from __future__ import annotations

import io
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")  # 서버(읽기 전용 파일시스템)에서 글꼴 캐시를 /tmp에
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from . import style as st  # noqa: E402

LOCK = threading.Lock()
_font_state: dict = {"ready": False, "family": None, "regular": None, "bold": None, "warning": None}

_FONT_NAMES = {"regular": ("malgun.ttf",), "bold": ("malgunbd.ttf",)}
_SEARCH_DIRS = [os.environ.get("FONT_DIR", ""), "/tmp/chartkit-fonts", str(Path.home() / ".local/share/fonts"),
                "/usr/share/fonts", "/usr/local/share/fonts", str(Path(__file__).parent / "fonts")]


def _find(names) -> str | None:
    for d in _SEARCH_DIRS:
        if not d or not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower() in names:
                    return os.path.join(root, f)
    return None


def _download_fonts() -> None:
    """서버(Vercel)에는 글꼴 파일을 넣지 않는다. 환경변수 FONT_URL_REGULAR·FONT_URL_BOLD(비공개 주소)에서 받아 /tmp에 둔다.
    주소 하나에 '|'로 여러 조각 주소를 이으면 순서대로 받아 붙인다(4MB 조각 다운로드 대응)."""
    out = Path("/tmp/chartkit-fonts")
    for key, fname in (("FONT_URL_REGULAR", "malgun.ttf"), ("FONT_URL_BOLD", "malgunbd.ttf")):
        urls = [u for u in os.environ.get(key, "").split("|") if u.strip()]
        dest = out / fname
        if not urls or dest.exists():
            continue
        out.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        with open(tmp, "wb") as fh:
            for u in urls:
                with urllib.request.urlopen(u.strip(), timeout=30) as r:  # noqa: S310 — 환경변수로 받은 고정 주소
                    fh.write(r.read())
        tmp.rename(dest)


def setup_fonts() -> dict:
    if _font_state["ready"]:
        return _font_state
    reg, bold = _find(_FONT_NAMES["regular"]), _find(_FONT_NAMES["bold"])
    if not reg:
        try:
            _download_fonts()
        except Exception as e:  # noqa: BLE001 — 글꼴을 못 받아도 그림은 그린다(대체 글꼴 + 경고)
            _font_state["warning"] = f"맑은 고딕을 받지 못했습니다({type(e).__name__}) — 대체 글꼴로 그렸습니다"
        reg, bold = _find(_FONT_NAMES["regular"]), _find(_FONT_NAMES["bold"])
    family = None
    for p in (reg, bold):
        if p:
            font_manager.fontManager.addfont(p)
    if reg:
        family = font_manager.FontProperties(fname=reg).get_name()
    else:
        for cand in ("Noto Sans CJK KR", "Noto Sans KR", "NanumGothic", "DejaVu Sans"):
            if any(f.name == cand for f in font_manager.fontManager.ttflist):
                family = cand
                break
        family = family or "DejaVu Sans"
        _font_state["warning"] = _font_state["warning"] or f"맑은 고딕이 없어 {family}로 그렸습니다"
    # 맑은 고딕에 없는 글자(빼기 기호 U+2212, ≈ 등)는 matplotlib에 딸린 DejaVu Sans로 글자 단위 대체(1.2.6).
    # 맑은 고딕 원본에도 U+2212가 없어 화산도 축 제목 "−log10"이 네모로 나왔다.
    matplotlib.rcParams.update({
        "font.family": [family, "DejaVu Sans"], "font.size": st.FONT_SIZE, "axes.unicode_minus": False, "svg.fonttype": "none",
        "axes.edgecolor": st.AXIS, "axes.labelcolor": st.INK2, "axes.labelsize": st.FONT_SIZE,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False, "axes.axisbelow": True,
        "grid.color": st.GRID_LINE, "grid.linewidth": 0.8, "grid.linestyle": "-", "xtick.color": st.INK2, "ytick.color": st.INK2,
        "xtick.labelsize": st.FONT_SIZE - 0.5, "ytick.labelsize": st.FONT_SIZE - 0.5, "xtick.major.size": 0, "ytick.major.size": 0,
        "legend.frameon": False, "legend.fontsize": st.FONT_SIZE - 0.5, "figure.facecolor": "white", "savefig.facecolor": "white",
        "axes.prop_cycle": matplotlib.cycler(color=st.PALETTE),
    })
    _font_state.update(ready=True, family=family, regular=reg, bold=bold)
    return _font_state


def font_path(bold: bool = False) -> str | None:
    setup_fonts()
    return _font_state["bold" if bold else "regular"] or _font_state["regular"]


@contextmanager
def figure(height_in: float | None = None, options: dict | None = None, *, default_h: float = 3.6, **kw):
    """잠금을 잡고 그림을 만든다. 크기: 폭 16cm, 높이는 options.height_in > height_in > default_h."""
    o = options or {}
    with LOCK:
        setup_fonts()
        w = float(o.get("width_in") or st.WIDTH_IN)
        h = float(o.get("height_in") or height_in or default_h)
        fig = plt.figure(figsize=(w, h), dpi=100, **kw)
        try:
            yield fig
        finally:
            plt.close(fig)


def top_for(fig, title, sub, o, legend: bool) -> float:
    """플롯 위쪽 경계(0~1). 제목·범례 자리를 인치 단위로 비운다."""
    h = fig.get_size_inches()[1]
    space = 0.08
    if o.get("show_title") and (title or sub):
        space += 0.28 + (0.2 if (title and sub) else 0)
    if legend:
        space += 0.26
    return max(0.55, 1 - space / h)


def put_title(fig, title, sub, o) -> None:
    if not o.get("show_title"):
        return
    h = fig.get_size_inches()[1]
    y = 1 - 0.06 / h
    if title:
        fig.text(0.01, y, title, fontsize=11, fontweight="bold", color=st.INK, va="top", ha="left")
        y -= 0.24 / h
    if sub:
        fig.text(0.01, y, sub, fontsize=8, color=st.MUTED, va="top", ha="left")


def legend_top(fig, items: list[tuple[str, str, str]], title, sub, o, *, ncol: int | None = None) -> None:
    """그림 위쪽 한 줄 범례. items=[(label, color, kind)] kind: patch|line|marker|dashed."""
    if not items:
        return
    hs = []
    for label, c, kind in items:
        if kind == "line":
            hs.append(Line2D([0], [0], color=c, lw=2, label=label))
        elif kind == "dashed":
            hs.append(Line2D([0], [0], color=c, lw=1.4, ls="--", label=label))
        elif kind == "marker":
            hs.append(Line2D([0], [0], color=c, marker="o", lw=0, markersize=6, label=label))
        else:
            hs.append(Patch(facecolor=c, edgecolor=c, label=label))
    h = fig.get_size_inches()[1]
    y = 1 - 0.04 / h
    if o.get("show_title") and (title or sub):
        y -= (0.3 + (0.2 if (title and sub) else 0)) / h
    # 1.4.0: 범례가 그림 폭을 넘으면 한 줄 칸 수를 줄이고, 두 줄 이상이면 그만큼 그림 칸(축)을 아래로 내린다
    #        (이전: 6칸 고정 — 항목이 많거나 이름이 길면 범례가 그림 밖으로 나가거나 축 위를 덮었다)
    nc = ncol or min(len(hs), 6)
    leg = None
    W = fig.bbox.width * 0.98
    while True:
        if leg is not None:
            leg.remove()
        leg = fig.legend(handles=hs, loc="upper center", ncol=nc, frameon=False, bbox_to_anchor=(0.5, y),
                         handlelength=1.2, handletextpad=0.4, columnspacing=1.2)
        if nc <= 1:
            break
        fig.canvas.draw()
        if leg.get_window_extent().width <= W:
            break
        nc -= 1
    fig.canvas.draw()
    lb = fig.transFigure.inverted().transform((0, leg.get_window_extent().y0))[1] - 0.04 / h
    axes = [a for a in fig.axes if a.get_visible()]
    if axes:
        top_ = max(a.get_position().y1 for a in axes)
        bot_ = min(a.get_position().y0 for a in axes)
        if lb < top_ and top_ > bot_ and lb > bot_ + 0.25:
            k = (lb - bot_) / (top_ - bot_)
            for a in axes:
                p_ = a.get_position()
                a.set_position([p_.x0, bot_ + (p_.y0 - bot_) * k, p_.width, p_.height * k])


def style_axes(ax, *, grid: str = "y", left_spine: bool = False) -> None:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_visible(left_spine)
    ax.spines["bottom"].set_color(st.AXIS)
    if grid in ("y", "both"):
        ax.yaxis.grid(True, **st.GRID_KW)
    if grid in ("x", "both"):
        ax.xaxis.grid(True, **st.GRID_KW)
    ax.tick_params(length=0)


def num_formatter(decimals: int | None = None):
    return FuncFormatter(lambda v, _p=None: st.fmt(v, decimals))


def axis_unit(ax, unit: str | None, which: str = "y") -> None:
    if unit:
        (ax.set_ylabel if which == "y" else ax.set_xlabel)(f"({unit})", color=st.MUTED, fontsize=st.FONT_SIZE - 1)


# 맑은 고딕(서버가 받는 글꼴)과 대체 글꼴 DejaVu Sans에 모두 없는 단위 기호는 그리면 네모(□)로 나온다(1.6.3 —
# 산점도 축 제목 "㎡당 평균 거래가격"의 ㎡가 깨짐, 2026-11-27 답변 시험). 그런 글자만 같은 뜻의 글자로 바꿔 그린다.
# 글꼴에 있는 글자는 바꾸지 않는다. 표·엑셀 원본의 글은 그대로 둔다.
_UNIT_SUB = {"㎡": "m²", "㎢": "km²", "㎥": "m³", "㎠": "cm²", "㎤": "cm³", "㎟": "mm²", "㎦": "km³",
             "㎞": "km", "㎝": "cm", "㎜": "mm", "㎏": "kg", "㎎": "mg", "㎍": "μg", "㎖": "mL", "㎗": "dL", "ℓ": "L",
             "㏊": "ha", "㎾": "kW", "㎿": "MW", "㎽": "mW", "㎸": "kV", "㎷": "mV", "㏈": "dB", "㎐": "Hz", "㎑": "kHz",
             "㎒": "MHz", "㎓": "GHz", "℃": "°C", "℉": "°F", "№": "No.", "㏄": "cc", "㎈": "cal", "㎉": "kcal"}
_glyphs: dict = {}


def _font_chars() -> set | None:
    """지금 그리는 글꼴(맑은 고딕 보통·굵게 + DejaVu Sans)이 가진 글자 집합. 못 읽으면 None(바꾸지 않음)."""
    key = (_font_state.get("regular"), _font_state.get("bold"))
    if key in _glyphs:
        return _glyphs[key]
    chars: set | None = set()
    try:
        from fontTools.ttLib import TTFont
        paths = [p for p in key if p]
        paths.append(font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans"), fallback_to_default=False))
        if not key[0]:  # 맑은 고딕이 없을 때는 실제로 고른 대체 글꼴
            paths.append(font_manager.findfont(font_manager.FontProperties(family=_font_state.get("family") or "DejaVu Sans")))
        for p in paths:
            chars |= set(TTFont(p, lazy=True, fontNumber=0).getBestCmap() or {})
    except Exception:  # noqa: BLE001 — 글꼴 점검 실패는 그림을 막지 않는다
        chars = None
    _glyphs[key] = chars
    return chars


def fix_missing_glyphs(fig) -> list[str]:
    """그림 안 글자 중 글꼴에 없는 단위 기호를 바꾼다. 바꾼 기호 목록을 돌려준다."""
    have = _font_chars()
    if not have:
        return []
    done = []
    from matplotlib.text import Text
    for t in fig.findobj(Text):
        s = t.get_text()
        if not s or s.isascii():
            continue
        out, hit = [], False
        for ch in s:
            if ord(ch) in have or ch not in _UNIT_SUB or not all(ord(c) in have for c in _UNIT_SUB[ch]):
                out.append(ch)
            else:
                out.append(_UNIT_SUB[ch])
                hit = True
                if ch not in done:
                    done.append(ch)
        if hit:
            t.set_text("".join(out))
    if done:
        from . import declutter
        declutter._note(f"글꼴에 없는 기호 {'·'.join(done)}를 {'·'.join(_UNIT_SUB[c] for c in done)}로 바꿔 그렸습니다(표·엑셀 원본은 그대로)")
    return done


def to_png(fig, dpi: int | None = None) -> bytes:
    from . import declutter
    fix_missing_glyphs(fig)  # 네모로 나오는 단위 기호 바꾸기(1.6.3) — 글자 폭이 바뀌므로 겹침 정리 전에
    declutter.run(fig)  # 글자 겹침 정리(1.4.0)
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=dpi or st.DPI, bbox_inches=declutter.safe_bbox(fig), pad_inches=0.06)
    return b.getvalue()


def label_fits(fig, text_obj, max_w_px: float) -> bool:
    r = fig.canvas.get_renderer()
    return text_obj.get_window_extent(r).width <= max_w_px


class Result:
    """그리기 결과. png 바이트, 주의사항, 계산값, 엑셀에 넣을 표(sheets: [(시트이름, 머리행, 행들)])."""

    def __init__(self, png: bytes, notes=None, computed=None, table=None, w: int = 0, h: int = 0):
        self.png = png
        self.notes = list(notes or [])
        self.computed = dict(computed or {})
        self.table = table
        self.w, self.h = w, h
