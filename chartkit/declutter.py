"""글자 겹침 정리(1.4.0) — 그림을 저장하기 직전, 모든 차트에 공통으로 한 번 돈다.

실제 글자 폭을 재서(맑은 고딕) 겹칠 때만 고친다. 겹치지 않는 그림은 손대지 않는다.

1. 축 눈금 이름(가로·세로): 7.2pt까지 줄임 → (범주 가로축) 30도 기울임 → 건너뛰기(k개마다, 마지막 이름은 되도록 남김).
   숫자 축은 눈금 수를 줄인다.
2. 점·선에 붙은 이름(annotate, 오프셋 좌표): 8방향 자리 중 다른 글자·눈금·선·점과 덜 겹치는 자리로 옮긴다.
3. 숫자 라벨: 6.3pt까지 줄임 → 막대 위 숫자는 세로로 세움(위 여백 늘림) → 그래도 겹치면 중요도(처음·끝·최대·최소) 낮은 것부터 생략.
처리한 내용은 notes로 돌려준다(api.draw가 결과 notes에 붙인다). options.declutter=false면 끈다.
"""
from __future__ import annotations

import contextvars
import math
import re

import numpy as np
from matplotlib import colors as mcolors
from matplotlib.collections import PathCollection
from matplotlib.text import Annotation, Text
from matplotlib.ticker import FixedLocator, MaxNLocator

NOTES: contextvars.ContextVar[list | None] = contextvars.ContextVar("declutter_notes", default=None)
ENABLED: contextvars.ContextVar[bool] = contextvars.ContextVar("declutter_enabled", default=True)

TICK_MIN = 7.2
LABEL_MIN = 6.3
GAP = 1.5  # px(100dpi) — 이보다 가까우면 겹침으로 본다

NUM = re.compile(r"^[\s+\-−±▲▼△▽(]*[\d.,]+\s*(%p|%|배|x|억원|억|만원|만|천|원|조|건|개|명|대|pt|p|일|개월|년|위|곳|점|회|t|kg|g|mg|ng/mL|℃|°C)?\)?\s*$")


def _note(msg: str) -> None:
    lst = NOTES.get()
    if lst is not None and msg not in lst:
        lst.append(msg)


# ── 기하 ───────────────────────────────────────────────
def rect(t: Text, r):
    """회전 사각형 (cx, cy, hw, hh, 각도, 축정렬 상자). 축정렬 상자 중심 = 회전 사각형 중심."""
    bb = t.get_window_extent(r)
    if bb.width <= 0 or bb.height <= 0:
        return None
    ang = math.radians(t.get_rotation() % 180)
    if abs(math.sin(ang)) < 1e-3 or abs(math.cos(ang)) < 1e-3:
        return (bb.x0 + bb.width / 2, bb.y0 + bb.height / 2, bb.width / 2, bb.height / 2, 0.0, bb)
    rot = t.get_rotation()
    t.set_rotation(0)
    b0 = t.get_window_extent(r)
    t.set_rotation(rot)
    return (bb.x0 + bb.width / 2, bb.y0 + bb.height / 2, b0.width / 2, b0.height / 2, ang, bb)


def _corners(R):
    cx, cy, hw, hh, a, _ = R
    c, s = math.cos(a), math.sin(a)
    return [(cx + dx * c - dy * s, cy + dx * s + dy * c) for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]


def overlap(A, B, tol: float = GAP) -> float:
    """두 회전 사각형의 겹친 길이(분리축 정리 최소값). 겹치지 않으면 0."""
    a, b = A[5], B[5]
    if a.x1 + tol <= b.x0 or b.x1 + tol <= a.x0 or a.y1 + tol <= b.y0 or b.y1 + tol <= a.y0:
        return 0.0
    if A[4] == 0 and B[4] == 0:
        return max(0.0, min(min(a.x1, b.x1) - max(a.x0, b.x0), min(a.y1, b.y1) - max(a.y0, b.y0)) + tol)
    ca, cb = _corners(A), _corners(B)
    m = float("inf")
    for R in (A, B):
        an = R[4]
        for v in ((math.cos(an), math.sin(an)), (-math.sin(an), math.cos(an))):
            pa = [x * v[0] + y * v[1] for x, y in ca]
            pb = [x * v[0] + y * v[1] for x, y in cb]
            ov = min(max(pa), max(pb)) - max(min(pa), min(pb)) + tol
            if ov <= 0:
                return 0.0
            m = min(m, ov)
    return m


def _area(A, B) -> float:
    a, b = A[5], B[5]
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return w * h if (w > 0 and h > 0) else 0.0


def _visible_text(t: Text) -> bool:
    if not t.get_visible() or not t.get_text().strip():
        return False
    if t.get_alpha() == 0:
        return False
    try:
        return mcolors.to_rgba(t.get_color())[3] > 0
    except ValueError:
        return True


def _drawn_ticks(ax, axis):
    if not ax.axison or not ax.get_visible() or not axis.get_visible():
        return []
    try:
        ticks = axis._update_ticks()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for tk in ticks:
        for lab in (tk.label1, tk.label2):
            if _visible_text(lab):
                out.append(lab)
    return out


def _skip_axes(ax) -> bool:
    return ax.name in ("3d",) or not ax.get_visible()


# ── 1. 축 눈금 이름 ─────────────────────────────────────
def _tick_collisions(labs, r) -> int:
    Rs = [x for x in (rect(t, r) for t in labs) if x]
    n = 0
    for i in range(len(Rs)):
        for j in range(i + 1, min(len(Rs), i + 4)):  # 이웃 몇 개만
            if overlap(Rs[i], Rs[j]) > 0:
                n += 1
    return n


def _sorted_labels(labs, which):
    key = (lambda t: t.get_window_extent().x0) if which == "x" else (lambda t: t.get_window_extent().y0)
    try:
        return sorted(labs, key=key)
    except Exception:  # noqa: BLE001
        return labs


def fix_ticks(fig, ax, which: str) -> None:
    axis = ax.xaxis if which == "x" else ax.yaxis
    r = fig.canvas.get_renderer()
    labs = _sorted_labels(_drawn_ticks(ax, axis), which)
    if len(labs) < 2 or not _tick_collisions(labs, r):
        return
    fixed = isinstance(axis.get_major_locator(), FixedLocator)
    name = "가로축" if which == "x" else "세로축"
    # (1) 글자 줄이기
    size = labs[0].get_fontsize()
    if size > TICK_MIN + 0.05:
        ax.tick_params(axis=which, labelsize=TICK_MIN)
        fig.canvas.draw()
        labs = _sorted_labels(_drawn_ticks(ax, axis), which)
        if not _tick_collisions(labs, r):
            return
    # (2) 범주 가로축: 30도 기울임(두 줄 이름은 기울이지 않음)
    if which == "x" and fixed and all("\n" not in t.get_text() for t in labs) and all(abs(t.get_rotation()) < 1 for t in labs):
        ax.tick_params(axis="x", labelrotation=30)
        for t in ax.get_xticklabels():
            t.set_ha("right")
            t.set_rotation_mode("anchor")
        fig.canvas.draw()
        labs = _sorted_labels(_drawn_ticks(ax, axis), which)
        if not _tick_collisions(labs, r):
            _note(f"{name} 이름이 서로 겹쳐 30도 기울였습니다")
            return
    # (3) 건너뛰기
    if fixed:
        locs = list(axis.get_major_locator().locs)
        texts = [t.get_text() for t in axis.get_majorticklabels()]
        if len(texts) != len(locs) or len(locs) < 3:
            return
        Rs = [rect(t, r) for t in axis.get_majorticklabels()]
        if any(R is None for R in Rs):
            return
        order = sorted(range(len(locs)), key=lambda i: (Rs[i][0] if which == "x" else Rs[i][1]))
        for k in range(2, len(locs)):
            keep = order[::k]
            ok = all(overlap(Rs[a], Rs[b]) == 0 for a, b in zip(keep, keep[1:]))
            if ok:
                last = order[-1]
                if keep[-1] != last:
                    if overlap(Rs[keep[-1]], Rs[last]) == 0:
                        keep.append(last)
                    elif len(keep) > 2 and overlap(Rs[keep[-2]], Rs[last]) == 0:
                        keep[-1] = last
                keep = sorted(keep)
                rot = labs[0].get_rotation()
                ha = labs[0].get_ha()
                axis.set_ticks([locs[i] for i in keep], [texts[i] for i in keep])
                for t in axis.get_majorticklabels():
                    t.set_rotation(rot)
                    t.set_ha(ha)
                    t.set_rotation_mode("anchor" if rot else "default")
                fig.canvas.draw()
                _note(f"{name} 이름 {len(locs)}개가 겹쳐 {k}개마다 하나씩 표시했습니다(전체 값은 엑셀 원본 표)")
                return
    else:
        loc = axis.get_major_locator()
        nb = max(2, len(labs) - 1)
        for _ in range(8):
            nb = max(2, int(nb * 0.7))
            try:
                if isinstance(loc, MaxNLocator):
                    loc.set_params(nbins=nb)
                elif hasattr(loc, "maxticks"):  # 날짜 축
                    loc.maxticks = nb
                else:
                    axis.set_major_locator(MaxNLocator(nbins=nb))
                    loc = axis.get_major_locator()
            except Exception:  # noqa: BLE001
                return
            fig.canvas.draw()
            labs = _sorted_labels(_drawn_ticks(ax, axis), which)
            if not _tick_collisions(labs, r):
                return
            if nb == 2:
                return


# ── 공통: 장애물 ───────────────────────────────────────
def _obstacles(fig, r, exclude: set):
    """움직이지 않는 글자(눈금·범례·그림 글자·축 고정 글자)."""
    obs = []
    for ax in fig.axes:
        if _skip_axes(ax):
            continue
        for axis in (ax.xaxis, ax.yaxis):
            for t in _drawn_ticks(ax, axis):
                R = rect(t, r)
                if R:
                    obs.append(R)
        for t in (ax.xaxis.label, ax.yaxis.label, ax.title):
            if _visible_text(t) and id(t) not in exclude:
                R = rect(t, r)
                if R:
                    obs.append(R)
    for t in fig.findobj(Text):
        if id(t) in exclude or not _visible_text(t):
            continue
        if t.axes is not None and t.figure is fig and t in getattr(t.axes, "texts", []):
            continue  # 축 안 글자는 따로 다룬다
        if t.axes is not None and not t.axes.get_visible():
            continue
        R = rect(t, r)
        if R:
            obs.append(R)
    return obs


def _axes_texts(fig):
    out = []
    for ax in fig.axes:
        if _skip_axes(ax):
            continue
        for t in ax.texts:
            if _visible_text(t):
                out.append(t)
    return out


def _is_num(t: Text) -> bool:
    return bool(NUM.match(t.get_text().replace("\n", " ")))


def _is_light(t: Text) -> bool:
    try:
        return sum(mcolors.to_rgb(t.get_color())) > 2.7
    except ValueError:
        return False


def _fixed_transform(t: Text) -> bool:
    """축 비율 좌표·축 혼합 좌표 글자(사분면 이름·기준선 이름 등)는 움직이지 않는다."""
    ax = t.axes
    if ax is None:
        return True
    tr = t.get_transform()
    return tr in (ax.transAxes, ax.get_yaxis_transform(), ax.get_xaxis_transform()) or tr == fig_transform(t)


def fig_transform(t):
    return t.figure.transFigure if t.figure is not None else None


# ── 2. 옮길 수 있는 이름(annotate) ───────────────────────
_DIRS = [(1, 1, "left", "bottom"), (1, 0, "left", "center"), (0, 1, "center", "bottom"), (-1, 1, "right", "bottom"),
         (-1, 0, "right", "center"), (1, -1, "left", "top"), (0, -1, "center", "top"), (-1, -1, "right", "top")]


def _line_samples(fig):
    pts = []
    for ax in fig.axes:
        if _skip_axes(ax):
            continue
        for ln in ax.get_lines():
            if not ln.get_visible() or ln.get_linestyle() in ("None", "none", "") or ln.get_linewidth() < 0.6:
                continue
            xy = ln.get_xydata()
            if xy is None or len(xy) < 2:
                continue
            try:
                P = ln.get_transform().transform(np.asarray(xy, float))
            except Exception:  # noqa: BLE001
                continue
            P = P[np.isfinite(P).all(axis=1)]
            for a_, b_ in zip(P[:-1], P[1:]):
                n = int(min(400, max(2, np.hypot(*(b_ - a_)) / 3)))
                pts.append(np.linspace(a_, b_, n))
    return np.vstack(pts) if pts else np.zeros((0, 2))


def _point_boxes(fig):
    """산점·거품 표식 위치(표시 좌표)와 반지름(px)."""
    out = []
    for ax in fig.axes:
        if _skip_axes(ax):
            continue
        for c in ax.collections:
            if not isinstance(c, PathCollection) or not c.get_visible():
                continue
            try:
                off = c.get_offset_transform().transform(c.get_offsets())
            except Exception:  # noqa: BLE001
                continue
            sz = c.get_sizes()
            for i, (x, y) in enumerate(off):
                s = sz[i % len(sz)] if len(sz) else 36
                rad = math.sqrt(max(s, 1)) / 2 * fig.dpi / 72
                out.append((x, y, rad))
    return out


def _cost(R, obs, placed, lines, points, own, axbb):
    c = 0.0
    for O in obs:
        c += _area(R, O) * 3
    for O in placed:
        c += _area(R, O) * 4
    b = R[5]
    if len(lines):
        m = (lines[:, 0] > b.x0) & (lines[:, 0] < b.x1) & (lines[:, 1] > b.y0) & (lines[:, 1] < b.y1)
        c += float(m.sum()) * 6
    for (x, y, rad) in points:
        if own is not None and abs(x - own[0]) < 0.5 and abs(y - own[1]) < 0.5:
            rr = rad * 0.6  # 자기 점은 가운데만 피함
        else:
            rr = min(rad, 25)
        w = min(b.x1, x + rr) - max(b.x0, x - rr)
        h = min(b.y1, y + rr) - max(b.y0, y - rr)
        if w > 0 and h > 0:
            c += w * h * 0.8
    if axbb is not None:
        out = max(0, axbb.x0 - b.x0) + max(0, b.x1 - axbb.x1) + max(0, axbb.y0 - b.y0) + max(0, b.y1 - axbb.y1)
        c += out * b.height * 1.5
    return c


def place_annotations(fig) -> None:
    r = fig.canvas.get_renderer()
    movable = [t for t in _axes_texts(fig) if isinstance(t, Annotation) and t.get_visible()
               and str(getattr(t, "anncoords", "")).startswith("offset") and t.xycoords == "data"]
    if not movable:
        return
    if len(movable) > 300:  # 너무 많으면 옮기지 않고 겹치는 것만 생략
        r_ = fig.canvas.get_renderer()
        kept, hid = [], 0
        for t in movable:
            R = rect(t, r_)
            if R is None:
                continue
            if any(overlap(R, K) > 0 for K in kept):
                t.set_visible(False)
                hid += 1
            else:
                kept.append(R)
        if hid:
            _note(f"이름 {hid}개는 다른 이름과 겹쳐 생략했습니다(전체 값은 엑셀 원본 표)")
        return
    Rs = {id(t): rect(t, r) for t in movable}
    # 겹침이 하나도 없으면 손대지 않는다
    others = [t for t in _axes_texts(fig) if id(t) not in Rs]
    obs = _obstacles(fig, r, {id(t) for t in movable}) + [x for x in (rect(t, r) for t in others) if x]
    lines = _line_samples(fig)
    points = _point_boxes(fig)
    lst = [Rs[id(t)] for t in movable if Rs[id(t)]]
    bad = any(overlap(a, b) > 0 for i, a in enumerate(lst) for b in lst[i + 1:]) or any(overlap(a, o) > 0 for a in lst for o in obs)
    if not bad and len(lines):  # 선이 이름 한가운데를 지나는지
        for R in lst:
            b = R[5]
            mx, my = b.width * 0.2, b.height * 0.25
            if ((lines[:, 0] > b.x0 + mx) & (lines[:, 0] < b.x1 - mx) & (lines[:, 1] > b.y0 + my) & (lines[:, 1] < b.y1 - my)).any():
                bad = True
                break
    if not bad:
        return
    placed = []
    moved = hidden = 0
    for t in movable:
        R0 = Rs[id(t)]
        if R0 is None:
            continue
        ax = t.axes
        own = ax.transData.transform(t.xy) if t.xy is not None else None
        dx, dy = t.xyann
        d = max(abs(dx), abs(dy), 4.0)
        orig = (dx, dy, t.get_ha(), t.get_va())
        best = (_cost(R0, obs, placed, lines, points, own, ax.bbox), orig)
        if best[0] > 0:
            for sx, sy, ha, va in _DIRS:
                for mul in (1.0, 1.8):
                    cand = (sx * d * mul * (0.8 if sy else 1), sy * d * mul * (0.8 if sx else 1), ha, va)
                    t.xyann = cand[:2]
                    t.set_ha(ha)
                    t.set_va(va)
                    R = rect(t, r)
                    if R is None:
                        continue
                    c = _cost(R, obs, placed, lines, points, own, ax.bbox)
                    if c < best[0] - 1:
                        best = (c, cand)
                    if best[0] == 0:
                        break
                if best[0] == 0:
                    break
        dx, dy, ha, va = best[1]
        t.xyann = (dx, dy)
        t.set_ha(ha)
        t.set_va(va)
        if best[1] != orig:
            moved += 1
        R = rect(t, r)
        # 다른 글자와 여전히 크게 겹치면 생략
        if R is not None and any(overlap(R, P) > 3 for P in placed + obs):
            t.set_visible(False)
            hidden += 1
            continue
        if R is not None:
            placed.append(R)
    if moved:
        _note(f"이름 {moved}개를 겹치지 않는 자리로 옮겼습니다")
    if hidden:
        _note(f"이름 {hidden}개는 다른 글자와 겹쳐 생략했습니다(전체 값은 엑셀 원본 표)")


# ── 3. 숫자 라벨 ───────────────────────────────────────
def _labels(fig):
    return [t for t in _axes_texts(fig) if _is_num(t) and not _fixed_transform(t)]


def _collisions(labs, Rs, obs):
    bad = set()
    for i in range(len(labs)):
        Ri = Rs[i]
        if Ri is None:
            continue
        for j in range(i + 1, len(labs)):
            if Rs[j] is not None and overlap(Ri, Rs[j]) > 0:
                bad.add(i)
                bad.add(j)
        for O in obs:
            if overlap(Ri, O) > 0:
                bad.add(i)
    return bad


def _above_bar(t: Text) -> bool:
    return abs(t.get_rotation()) < 1 and t.get_va() in ("bottom", "baseline") and t.get_ha() == "center" and not _is_light(t)


def _value_of(t: Text) -> float:
    s = re.sub(r"[^\d.\-−]", "", t.get_text().replace("−", "-"))
    try:
        return float(s)
    except ValueError:
        return 0.0


def fix_value_labels(fig) -> None:
    r = fig.canvas.get_renderer()
    labs = _labels(fig)
    if len(labs) < 2:
        return
    ex = {id(t) for t in _axes_texts(fig)}
    obs = _obstacles(fig, r, ex) + [x for x in (rect(t, r) for t in _axes_texts(fig) if not _is_num(t) or _fixed_transform(t)) if x]
    Rs = [rect(t, r) for t in labs]
    bad = _collisions(labs, Rs, obs)
    if not bad:
        return
    # (1) 줄이기 — 같은 그림의 숫자는 같은 크기로
    for _ in range(4):
        sizes = [t.get_fontsize() for t in labs]
        if min(sizes) <= LABEL_MIN + 0.05:
            break
        for t in labs:
            t.set_fontsize(max(LABEL_MIN, t.get_fontsize() * 0.88))
        Rs = [rect(t, r) for t in labs]
        bad = _collisions(labs, Rs, obs)
        if not bad:
            _note("숫자 라벨이 겹쳐 글자를 줄였습니다")
            return
    # (2) 막대 위 숫자 세우기
    up = [i for i in range(len(labs)) if _above_bar(labs[i])]
    if len(up) >= max(2, len(bad) // 2):
        for i in up:
            labs[i].set_rotation(90)
            labs[i].set_rotation_mode("default")
            t0 = labs[i]
            # 막대 끝에서 살짝 띄움
            if not isinstance(t0, Annotation):
                t0.set_va("bottom")
        fig.canvas.draw()
        # 위 여백: 세운 숫자가 축 위로 나가면 축 범위를 늘린다
        for ax in {labs[i].axes for i in up}:
            for _ in range(3):
                tops = [labs[i].get_window_extent(r).y1 for i in up if labs[i].axes is ax]
                over = (max(tops) if tops else 0) - ax.bbox.y1
                if over <= 1:
                    break
                y0, y1 = ax.get_ylim()
                ax.set_ylim(y0, y1 + (y1 - y0) * (over + 4) / max(ax.bbox.height - over, 10))
                fig.canvas.draw()
        Rs = [rect(t, r) for t in labs]
        obs = _obstacles(fig, r, ex) + [x for x in (rect(t, r) for t in _axes_texts(fig) if not _is_num(t) or _fixed_transform(t)) if x]
        bad = _collisions(labs, Rs, obs)
        if not bad:
            _note("막대 숫자가 칸보다 넓어 세로로 세웠습니다")
            return
    # (3) 중요도 낮은 숫자부터 생략
    def pos(i):
        return Rs[i][0] if Rs[i] else 0

    n = len(labs)
    idx = sorted(range(n), key=pos)
    vals = [_value_of(t) for t in labs]
    pri = []
    for i in (idx[-1], idx[0], max(range(n), key=lambda k: vals[k]), min(range(n), key=lambda k: vals[k])):
        if i not in pri:
            pri.append(i)
    # 나머지는 고르게(이분 순서)
    rest = [i for i in idx if i not in pri]
    order, step = [], len(rest)
    seen = set()
    while step >= 1 and len(order) < len(rest):
        for k in range(0, len(rest), step):
            if rest[k] not in seen:
                seen.add(rest[k])
                order.append(rest[k])
        step //= 2
    pri += order
    kept = []
    hidden = 0
    for i in pri:
        Ri = Rs[i]
        if Ri is None:
            continue
        if any(overlap(Ri, K) > 0 for K in kept) or any(overlap(Ri, O) > 2 for O in obs):
            labs[i].set_visible(False)
            hidden += 1
        else:
            kept.append(Ri)
    if hidden:
        _note(f"숫자 라벨 {hidden}개는 서로 겹쳐 생략했습니다(처음·끝·최대·최소는 남김, 전체 값은 엑셀 원본 표)")


def fix_corner(fig, ax) -> None:
    """가로축 첫 눈금 이름과 세로축 첫 눈금 이름이 모서리에서 겹치면 가로축 이름을 아래로 띄운다."""
    r = fig.canvas.get_renderer()
    xs = [rect(t, r) for t in _drawn_ticks(ax, ax.xaxis)]
    ys = [rect(t, r) for t in _drawn_ticks(ax, ax.yaxis)]
    worst = 0.0
    for X in xs:
        for Y in ys:
            if X and Y and overlap(X, Y) > 0:
                worst = max(worst, X[5].y1 - Y[5].y0 + 2)  # 가로 이름 위가 세로 이름 밑보다 올라간 만큼
    if worst > 0:
        pts = worst * 72 / fig.dpi
        ax.tick_params(axis="x", pad=ax.xaxis.get_major_ticks()[0].get_pad() + pts if ax.xaxis.get_major_ticks() else 3.5 + pts)
        fig.canvas.draw()


def keep_inside(fig) -> None:
    """데이터 좌표 숫자 라벨이 축 위·아래 밖으로 나가면(세운 숫자·음수 막대 아래 숫자) 값 축 범위를 그만큼 늘린다."""
    r = fig.canvas.get_renderer()
    for ax in fig.axes:
        if _skip_axes(ax) or ax.name == "polar" or ax.yaxis_inverted():
            continue
        labs = [t for t in ax.texts if _visible_text(t) and _is_num(t) and t.get_transform() == ax.transData]
        if not labs:
            continue
        for _ in range(3):
            bbs = [t.get_window_extent(r) for t in labs]
            up = max(b.y1 for b in bbs) - ax.bbox.y1
            dn = ax.bbox.y0 - min(b.y0 for b in bbs)
            if up <= 1 and dn <= 1:
                break
            y0, y1 = ax.get_ylim()
            k = (y1 - y0) / max(ax.bbox.height - max(up, 0) - max(dn, 0), 10)
            ax.set_ylim(y0 - (dn + 3) * k if dn > 1 else y0, y1 + (up + 3) * k if up > 1 else y1)
            fig.canvas.draw()


def run(fig) -> None:
    if not ENABLED.get():
        return
    try:
        fig.canvas.draw()
        for ax in list(fig.axes):
            if _skip_axes(ax) or ax.name == "polar":
                continue
            fix_ticks(fig, ax, "x")
            fix_ticks(fig, ax, "y")
            fix_corner(fig, ax)
        fig.canvas.draw()
        place_annotations(fig)
        fig.canvas.draw()
        fix_value_labels(fig)
        fig.canvas.draw()
        keep_inside(fig)
    except Exception as e:  # noqa: BLE001 — 정리 실패로 그림을 못 그리면 안 된다
        _note(f"글자 겹침 정리를 건너뛰었습니다({type(e).__name__})")


# ── 차트별로 부르는 도우미 ──────────────────────────────
def stack_vertical(fig, ax, texts, *, leader_x=None, gap_px: float = 1.0, min_size: float = LABEL_MIN) -> int:
    """같은 세로줄(열)에 붙는 이름표를 위아래로 벌린다(생키 노드 이름 등). 글자 좌표는 데이터 좌표, va='center'.
    축 높이에 다 들어가지 않으면 글자를 줄이고, 그래도 넘치면 작은 순(목록 뒤쪽)부터 생략한다. 생략 수를 돌려준다.
    leader_x: 원래 자리에서 많이 옮긴 이름표에 이끌선을 그릴 x(데이터 좌표, None이면 안 그림)."""
    texts = [t for t in texts if t.get_visible()]
    if len(texts) < 2:
        return 0
    r = fig.canvas.get_renderer()
    fig.canvas.draw()
    inv = ax.transData.inverted()
    anchors = [t.get_transform().transform(t.get_position())[1] for t in texts]
    lo, hi = ax.bbox.y0, ax.bbox.y1

    def heights():
        return [t.get_window_extent(r).height + gap_px for t in texts]

    hs = heights()
    while sum(hs) > (hi - lo) and min(t.get_fontsize() for t in texts) > min_size + 0.05:
        for t in texts:
            t.set_fontsize(max(min_size, t.get_fontsize() * 0.9))
        hs = heights()
    hidden = 0
    order = list(range(len(texts)))
    while sum(hs[i] for i in order) > (hi - lo) and len(order) > 1:
        drop = order[-1]  # 호출자가 중요도 순으로 넘긴다(뒤가 덜 중요)
        texts[drop].set_visible(False)
        order.remove(drop)
        hidden += 1
    idx = sorted(order, key=lambda i: -anchors[i])  # 위(큰 y)부터
    ys = {}
    cur = hi
    for i in idx:  # 위에서 아래로 밀기
        y = min(anchors[i], cur - hs[i] / 2)
        ys[i] = y
        cur = y - hs[i] / 2
    cur = lo
    for i in reversed(idx):  # 아래에서 위로 밀기
        y = max(ys[i], cur + hs[i] / 2)
        ys[i] = y
        cur = y + hs[i] / 2
    moved = 0
    for i in idx:
        t = texts[i]
        tr = t.get_transform()
        x_disp = tr.transform(t.get_position())[0]
        ny = tr.inverted().transform((x_disp, ys[i]))[1]
        if abs(ys[i] - anchors[i]) > 1:
            moved += 1
            t.set_position((t.get_position()[0], ny))
            if leader_x is not None and abs(ys[i] - anchors[i]) > hs[i] * 0.45:
                xd = ax.transData.transform((leader_x, 0))[0]
                a_ = inv.transform((xd, anchors[i]))
                b_ = inv.transform((x_disp, ys[i]))
                ax.plot([a_[0], b_[0]], [a_[1], b_[1]], color="#A6A6A6", lw=0.6, zorder=1)
    if hidden:
        _note(f"이름표 {hidden}개는 자리가 모자라 생략했습니다(전체 값은 엑셀 원본 표)")
    elif moved:
        _note("겹치는 이름표를 위아래로 벌렸습니다")
    return hidden


def fit_row(fig, texts, *, min_size: float = LABEL_MIN, join_lines: bool = True, rotate: bool = True) -> None:
    """한 줄로 늘어선 이름(마리메코 열 이름 등)이 겹치면: 줄이기 → 두 줄을 한 줄로 합쳐 세로로 세우기 → 생략."""
    texts = [t for t in texts if t.get_visible()]
    if len(texts) < 2:
        return
    r = fig.canvas.get_renderer()
    fig.canvas.draw()

    def coll():
        Rs = [rect(t, r) for t in texts]
        Rs_ = sorted([R for R in Rs if R], key=lambda R: R[0])
        return sum(1 for a, b in zip(Rs_, Rs_[1:]) if overlap(a, b) > 0)

    if not coll():
        return
    while coll() and min(t.get_fontsize() for t in texts) > min_size + 0.05:
        for t in texts:
            t.set_fontsize(max(min_size, t.get_fontsize() * 0.9))
    if not coll():
        _note("열 이름이 겹쳐 글자를 줄였습니다")
        return
    if rotate:
        for t in texts:
            if join_lines:
                t.set_text(" ".join(t.get_text().split("\n")))
            t.set_rotation(90)
            t.set_va("top")
            t.set_ha("center")
        if not coll():
            _note("열 이름이 겹쳐 세로로 세웠습니다")
            return
    # 생략: 넓은(중요한) 것부터 남긴다 — 호출자가 중요도 순으로 넘긴다
    kept, hidden = [], 0
    for t in texts:
        R = rect(t, r)
        if R is None:
            continue
        if any(overlap(R, K) > 0 for K in kept):
            t.set_visible(False)
            hidden += 1
        else:
            kept.append(R)
    if hidden:
        _note(f"열 이름 {hidden}개는 자리가 모자라 생략했습니다(전체 값은 엑셀 원본 표)")


def fit_in(fig, t: Text, w_px: float, h_px: float, *, fallbacks=(), min_size: float = LABEL_MIN) -> bool:
    """글자를 w×h(px, 회전 전 기준) 칸 안에 맞춘다: 줄이기 → fallbacks 글로 바꾸기(예: 이름만·비율만) → 숨김. 맞으면 True."""
    r = fig.canvas.get_renderer()
    rot = t.get_rotation()
    t.set_rotation(0)

    def fits():
        b = t.get_window_extent(r)
        return b.width <= w_px and b.height <= h_px

    ok = False
    size0 = t.get_fontsize()
    for txt in (t.get_text(),) + tuple(fallbacks):
        t.set_text(txt)
        size = size0
        t.set_fontsize(size)
        while not fits() and size > min_size + 0.05:
            size = max(min_size, size * 0.9)
            t.set_fontsize(size)
        if fits():
            ok = True
            break
    t.set_rotation(rot)
    if not ok:
        t.set_visible(False)
    return ok


def fit_width(fig, ax, items, *, what: str = "숫자", min_size: float = LABEL_MIN) -> None:
    """옆에 붙인 숫자(상자수염 중앙값 등)가 다음 그룹 자리(max_x, 데이터 좌표)를 넘으면: 줄이기 → 모두 생략.
    items=[(글자, 넘으면 안 되는 오른쪽 x)]. 한 그룹만 빼면 읽기 헷갈리므로 넘치면 전부 뺀다."""
    items = [(t, mx) for t, mx in items if t.get_visible()]
    if not items:
        return
    r = fig.canvas.get_renderer()
    fig.canvas.draw()

    def over():
        return any(t.get_window_extent(r).x1 > ax.transData.transform((mx, 0))[0] - 1 for t, mx in items)

    if not over():
        return
    while over() and min(t.get_fontsize() for t, _ in items) > min_size + 0.05:
        for t, _ in items:
            t.set_fontsize(max(min_size, t.get_fontsize() * 0.9))
    if not over():
        _note(f"{what} 라벨이 옆 그룹과 겹쳐 글자를 줄였습니다")
        return
    for t, _ in items:
        t.set_visible(False)
    _note(f"그룹이 많아 {what} 라벨을 넣을 자리가 없어 생략했습니다(값은 엑셀 원본 표)")


def safe_bbox(fig):
    """저장 영역: 보통은 'tight'. 그림 밖 먼 곳에 글자·도형이 있어 잘라낸 영역이 그림의 3배(폭)·4배(높이)를 넘으면
    그림 크기 그대로 저장한다(1.4.0 — 진척 100을 1로 안 바꾼 입력에서 그림 폭이 7만 픽셀이 되었다)."""
    try:
        tb = fig.get_tightbbox(fig.canvas.get_renderer())
        w, h = fig.get_size_inches()
        if tb.width > w * 3 or tb.height > h * 4:
            _note("그림 범위를 크게 벗어난 값이나 글자가 있어 그림 크기를 고정했습니다 — 입력 값의 단위(비율 0~1·%)를 확인하세요")
            return None
    except Exception:  # noqa: BLE001
        pass
    return "tight"
