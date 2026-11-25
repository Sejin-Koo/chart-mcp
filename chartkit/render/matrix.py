"""행×열 행렬 색칠 — 히트맵·상관 행렬·달력 히트맵·민감도 표."""
from __future__ import annotations

import datetime as dt

import numpy as np
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from .. import style as st
from ..core import Result, figure, put_title, to_png, top_for
from ..errors import as_dict, as_list, as_number, need

SEQ = LinearSegmentedColormap.from_list("seq", st.SEQUENTIAL)
DIV = LinearSegmentedColormap.from_list("div", st.DIVERGING)


def _grid(args):
    rows = [str(r) for r in as_list(args.get("rows"), "rows")]
    cols = [str(c) for c in as_list(args.get("columns"), "columns")]
    vals = as_list(args.get("values"), "values")
    ex = {"rows": ["A", "B"], "columns": ["1월", "2월"], "values": [[12, 15], [20, 18]]}
    need(rows and cols and vals, "rows·columns·values(행×열 2차원 배열)가 필요합니다", example=ex)
    need(len(vals) == len(rows), f"values 행 수 {len(vals)}가 rows 수 {len(rows)}와 다릅니다", example=ex)
    m = np.full((len(rows), len(cols)), np.nan)
    for i, r in enumerate(vals):
        r = as_list(r, f"values[{i}]")
        need(len(r) == len(cols), f"values[{i}]의 칸 수 {len(r)}가 columns 수 {len(cols)}와 다릅니다", example=ex)
        for j, v in enumerate(r):
            x = as_number(v, f"values[{i}][{j}]")
            m[i, j] = np.nan if x is None else x
    return rows, cols, m


def _heat(ax, m, rows, cols, cmap, norm, dec, show=True, base=None, fs=None):
    im = ax.imshow(m, cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(len(cols)), cols)
    ax.set_yticks(range(len(rows)), rows)
    ax.tick_params(length=0)
    for s_ in ax.spines.values():
        s_.set_visible(False)
    ax.xaxis.tick_top()
    notes, cell_unit = [], None
    fig = ax.figure
    rdr = fig.canvas.get_renderer()
    _fit_xticks(fig, ax, len(cols), rdr)
    if show and m.size <= 400:
        # 칸 숫자는 실제 글자 폭을 재서 칸 안에 들어가는 크기로 쓴다(열이 많으면 작게, 최소 MIN_CELL_FS).
        # 최소 크기로도 안 들어가면 천 단위 쉼표를 빼 보고, 그래도 넘치면 숫자를 생략하고 notes로 알린다(2026-11-25 — 24개월 열에서 숫자가 겹침)
        bb = ax.get_window_extent(rdr)
        cw, chh = bb.width / max(1, m.shape[1]), bb.height / max(1, m.shape[0])
        cells = [(i, j) for i in range(m.shape[0]) for j in range(m.shape[1]) if not np.isnan(m[i, j])]
        size0 = fs or (7.6 if m.size > 60 else 8.4)
        # 시도 순서: 그대로 → 천 단위 쉼표 빼기 → 큰 수는 천·만 단위로 줄여 소수 한 자리(색 막대 위에 '칸 숫자 단위'를 적음) → 생략
        vmax = float(np.nanmax(np.abs(m))) if cells else 0.0
        tries = [(lambda v: st.fmt(v, dec), None, None), (lambda v: st.fmt(v, dec).replace(",", ""), "칸이 좁아 칸 안 숫자에서 천 단위 쉼표를 뺐습니다.", None)]
        for div, name in ((1e8, "억"), (1e7, "천만"), (1e6, "백만"), (1e5, "십만"), (1e4, "만"), (1e3, "천")):
            if vmax >= div:
                tries.append((lambda v, d=div: st.fmt(v / d, 1).replace(",", ""), f"칸이 좁아 칸 안 숫자를 {name} 단위(소수 첫째 자리)로 줄여 적었습니다. 정확한 값은 표·엑셀 원본에 있습니다.", name))
                break
        pick = None
        for f, note, cu in tries:
            got = _fit_cell_labels(fig, rdr, [f(m[i, j]) for i, j in cells], cw, chh, size0)
            if got is not None:
                pick = (f, got[0], note, cu)
                break
        if pick is None:
            notes.append(f"칸이 좁아 칸 안 숫자를 생략했습니다(열 {m.shape[1]}개). 숫자는 표로 함께 싣거나 열을 나눠 그리세요.")
        else:
            f, size, note, cell_unit = pick
            if note:
                notes.append(note)
            for i, j in cells:
                v = m[i, j]
                rgba = im.cmap(im.norm(v))
                hexc = "#%02X%02X%02X" % tuple(int(255 * c) for c in rgba[:3])
                bold = base is not None and (i, j) == base
                ax.text(j, i, f(v), ha="center", va="center", color=st.ink_on(hexc), fontsize=size,
                        fontweight="bold" if bold else "normal")
    if base is not None:
        from matplotlib.patches import Rectangle
        ax.add_patch(Rectangle((base[1] - 0.5, base[0] - 0.5), 1, 1, fill=False, edgecolor=st.ORANGE, lw=2.2))
    return im, notes, cell_unit


MIN_TICK_FS = 7.0   # 열 이름 최소 글자 크기(pt) — 이보다 작아져야 하면 세로로 세운다
MIN_CELL_FS = 6.0   # 칸 숫자 최소 글자 크기(pt)


def _fit_xticks(fig, ax, nc, rdr):
    """위쪽 열 이름이 서로 겹치지 않게: 글자를 MIN_TICK_FS까지 줄이고, 그래도 겹치면 세로로 세운 뒤 늘어난 높이만큼 그림 칸을 내린다."""
    labs = [t for t in ax.get_xticklabels() if t.get_text()]
    if not labs or nc < 2:
        return
    cell = ax.get_window_extent(rdr).width / nc
    def widest():
        return max(t.get_window_extent(rdr).width for t in labs)
    fs = labs[0].get_fontsize()
    while widest() > cell * 0.92 and fs > MIN_TICK_FS:
        fs = max(MIN_TICK_FS, fs - 0.5)
        for t in labs:
            t.set_fontsize(fs)
    if widest() <= cell * 0.92:
        return
    h0 = max(t.get_window_extent(rdr).height for t in labs)
    for t in labs:
        t.set_rotation(90)
        t.set_ha("center")
        t.set_va("bottom")
    h1 = max(t.get_window_extent(rdr).height for t in labs)
    grow = (h1 - h0) / fig.bbox.height
    if grow > 0:
        pos = ax.get_position()
        ax.set_position([pos.x0, pos.y0, pos.width, max(0.2, pos.height - grow)])


def _fit_cell_labels(fig, rdr, texts, cw, chh, size0):
    """칸(폭 cw·높이 chh, 픽셀)에 가장 긴 숫자가 들어가는 글자 크기. MIN_CELL_FS로도 안 들어가면 None."""
    if not texts:
        return (size0,)
    longest = max(texts, key=len)
    probe = fig.text(0, 0, longest, fontsize=size0)
    size = size0
    try:
        while True:
            probe.set_fontsize(size)
            e = probe.get_window_extent(rdr)
            if e.width <= cw * 0.9 and e.height <= chh * 0.9:
                return (size,)
            if size <= MIN_CELL_FS:
                return None
            size = max(MIN_CELL_FS, round(size - 0.4, 1))
    finally:
        probe.remove()


def draw(ct: str, args: dict, o: dict) -> Result:
    title, sub, unit = args.get("title"), args.get("subtitle"), args.get("unit")
    notes, computed = [], {}
    if ct == "calendar_heatmap":
        return _calendar(args, o)
    if ct == "correlation" and args.get("variables"):
        var = as_dict(args["variables"], "variables")
        names = list(var)
        need(len(names) >= 2, "variables에 변수가 2개 이상 필요합니다", example={"매출": [1, 2, 3], "방문": [2, 3, 5]})
        data = np.array([[as_number(v, k) for v in as_list(var[k], k)] for k in names], float)
        m = np.corrcoef(data)
        rows = cols = names
        notes.append(f"피어슨 상관계수(n={data.shape[1]})")
    else:
        rows, cols, m = _grid(args)
    dec = o.get("decimals")
    if dec is None:
        dec = 2 if ct == "correlation" else (0 if np.nanmax(np.abs(m)) >= 100 or np.all(np.nan_to_num(m) == np.round(np.nan_to_num(m))) else 1)
    if ct == "correlation":
        cmap, norm = DIV, TwoSlopeNorm(vcenter=0, vmin=-1, vmax=1)
    elif o.get("diverging") or o.get("center") is not None:
        c = float(o.get("center") or 0)
        lo, hi = np.nanmin(m), np.nanmax(m)
        span = max(hi - c, c - lo, 1e-9)
        cmap, norm = DIV, TwoSlopeNorm(vcenter=c, vmin=c - span, vmax=c + span)
    else:
        cmap, norm = SEQ, None
    base = None
    if ct == "sensitivity_table" and o.get("base"):
        b = [str(x) for x in as_list(o.get("base"), "options.base")]
        if len(b) == 2 and b[0] in rows and b[1] in cols:
            base = (rows.index(b[0]), cols.index(b[1]))
            computed["base_value"] = float(m[base])
            notes.append(f"주황 테두리: 기준 칸({b[0]}, {b[1]}) = {st.fmt(m[base], dec)}")
        if norm is None:
            cmap = DIV
            mid = float(m[base]) if base else float(np.nanmedian(m))
            span = max(np.nanmax(m) - mid, mid - np.nanmin(m), 1e-9)
            norm = TwoSlopeNorm(vcenter=mid, vmin=mid - span, vmax=mid + span)
    nr, nc = m.shape
    h = max(2.2, 0.9 + 0.36 * nr)
    with figure(h, o) as fig:
        top = top_for(fig, title, sub, o, False) - 0.06 - (0.08 if (ct == "sensitivity_table" and o.get("x_name")) else 0)
        left = 0.06 + min(0.2, 0.012 * max(len(r) for r in rows))
        ax = fig.add_axes([left, 0.04 if not ct == "sensitivity_table" else 0.1, 0.86 - left, top - (0.06 if ct != "sensitivity_table" else 0.12)])
        im, hn, cell_unit = _heat(ax, m, rows, cols, cmap, norm, dec, show=o.get("show_values", True) is not False, base=base)
        notes.extend(hn)
        cax = fig.add_axes([0.9, 0.1, 0.015, top - 0.16])
        cb = fig.colorbar(im, cax=cax)
        cb.outline.set_visible(False)
        cb.ax.tick_params(labelsize=7, length=0)
        from ..core import num_formatter
        cb.ax.yaxis.set_major_formatter(num_formatter(2 if ct == "correlation" else None))
        if unit or cell_unit:
            cb.ax.set_title((unit or "") + (f"\n(칸: {cell_unit} {unit or ''})".replace(" )", ")") if cell_unit else ""), fontsize=7, color=st.MUTED)
        if ct == "sensitivity_table":
            ax.set_xlabel(o.get("x_name") or "", color=st.MUTED, labelpad=8)
            ax.xaxis.set_label_position("top")
            ax.set_ylabel(o.get("y_name") or "", color=st.MUTED)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    table = ([""] + list(cols), [[r] + [None if np.isnan(v) else float(v) for v in m[i]] for i, r in enumerate(rows)])
    return Result(png, notes, computed, table=table)


def _calendar(args, o):
    title, sub, unit = args.get("title"), args.get("subtitle"), args.get("unit")
    days = as_list(args.get("days"), "days")
    need(days, "days=[{date:'YYYY-MM-DD', value}]가 필요합니다", example=[{"date": "2026-01-02", "value": 132}])
    vals = {}
    for i, d in enumerate(days):
        d = as_dict(d, f"days[{i}]")
        k = dt.date.fromisoformat(str(d.get("date"))[:10])
        vals[k] = as_number(d.get("value"), f"days[{i}].value")
    d0, d1 = min(vals), max(vals)
    start = d0 - dt.timedelta(days=d0.weekday())
    nweeks = (d1 - start).days // 7 + 1
    m = np.full((7, nweeks), np.nan)
    for k, v in vals.items():
        w = (k - start).days // 7
        m[k.weekday(), w] = np.nan if v is None else v
    with figure(max(1.7, 1.2 + 0.0), o, default_h=2.0) as fig:
        top = top_for(fig, title, sub, o, False) - 0.12
        ax = fig.add_axes([0.06, 0.05, 0.86, top - 0.05])
        ax.imshow(m, cmap=SEQ, aspect="auto")
        ax.set_yticks(range(7), ["월", "화", "수", "목", "금", "토", "일"])
        ax.tick_params(length=0, labelsize=7)
        for s_ in ax.spines.values():
            s_.set_visible(False)
        ticks, labs, last = [], [], None
        for w in range(nweeks):
            d = start + dt.timedelta(days=7 * w)
            if d.month != last:
                if ticks and w - ticks[-1] < 3:
                    ticks.pop(); labs.pop()
                ticks.append(w)
                labs.append(f"{d.month}월")
                last = d.month
        ax.set_xticks(ticks, labs)
        ax.xaxis.tick_top()
        ax.set_xticks(np.arange(-0.5, nweeks, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, 7, 1), minor=True)
        ax.grid(which="minor", color="white", lw=1.2)
        ax.tick_params(which="minor", length=0)
        cax = fig.add_axes([0.94, 0.12, 0.012, top - 0.2])
        import matplotlib as mpl
        cb = fig.colorbar(mpl.cm.ScalarMappable(cmap=SEQ, norm=mpl.colors.Normalize(np.nanmin(m), np.nanmax(m))), cax=cax)
        cb.outline.set_visible(False)
        cb.ax.tick_params(labelsize=6.5, length=0)
        if unit:
            cb.ax.set_title(unit, fontsize=6.5, color=st.MUTED)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    rows = [[k.isoformat(), v] for k, v in sorted(vals.items())]
    return Result(png, ["달력 히트맵: 세로 = 요일, 가로 = 주, 진할수록 큰 값"], table=(["날짜", "값"], rows))
