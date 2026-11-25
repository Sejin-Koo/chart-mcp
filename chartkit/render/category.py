"""범주형 차트(항목·기간별 값) — matplotlib.

꺾은선·영역 계열(누적·100%·계단·전망 밴드·흐름), 혼합(막대·꺾은선·영역, 보조축), 롤리팝·덤벨·방사형 막대·픽토그램,
범프, 원 계열(쪼개진 원·반원 도넛·나이팅게일 로즈), 폭포, 깔때기, 레이더.
"""
from __future__ import annotations

import math

import numpy as np

from .. import style as st
from ..core import Result, axis_unit, figure, legend_top, num_formatter, put_title, style_axes, to_png, top_for
from ..errors import as_list, need
from .common import (bands, categories, color_warn, colors_for, decimals_of, label_mode, series, table_from_series,
                     target_lines)

LINE_TYPES = {"line", "line_marker", "line_stacked", "line_percent", "step_line", "area", "area_stacked", "area_percent", "line_band",
              "bar", "bar_stacked", "bar_percent", "hbar", "hbar_stacked", "combo"}


def _pct(ser):
    n = len(ser[0]["values"])
    tot = [sum((s["values"][i] or 0) for s in ser) for i in range(n)]
    out = []
    for s in ser:
        d = dict(s)
        d["values"] = [round((v or 0) / tot[i] * 100, 2) if tot[i] else None for i, v in enumerate(s["values"])]
        out.append(d)
    return out


def _ref_lines(ax, o, horizontal=False):
    for b in bands(o):
        (ax.axvspan if horizontal else ax.axhspan)(b["from"], b["to"], color=b["color"], alpha=0.9, zorder=0, lw=0)
        if b["label"]:
            if horizontal:
                ax.text(b["to"], 1.0, b["label"], transform=ax.get_xaxis_transform(), ha="right", va="top", fontsize=7.5, color=st.TEAL)
            else:
                ax.text(1.0, b["to"], b["label"], transform=ax.get_yaxis_transform(), ha="right", va="bottom", fontsize=7.5, color=st.TEAL)
    for t in target_lines(o):
        (ax.axvline if horizontal else ax.axhline)(t["value"], color=t["color"], ls="--", lw=1.1, zorder=3)
        lab = t["label"] or st.fmt(t["value"])
        if horizontal:
            ax.text(t["value"], 1.0, lab, transform=ax.get_xaxis_transform(), ha="left", va="bottom", fontsize=7.5, color=t["color"])
        else:
            ax.text(0.0, t["value"], " " + lab, transform=ax.get_yaxis_transform(), ha="left", va="bottom", fontsize=7.5, color=t["color"])


def _spread(labels, gap):
    """같은 x의 라벨 y를 겹치지 않게 벌린다. labels=[(k,y)] → {k:y}."""
    out = {}
    pts = sorted(labels, key=lambda z: z[1])
    for j, (k, y) in enumerate(pts):
        if j and y - out[pts[j - 1][0]] < gap:
            y = out[pts[j - 1][0]] + gap
        out[k] = y
    return out


def draw_line_family(ct: str, args: dict, o: dict) -> Result:
    cats = categories(args)
    ser = series(args, len(cats))
    unit = args.get("unit")
    title, sub = args.get("title"), args.get("subtitle")
    notes = color_warn(len(ser))
    n = len(cats)
    x = np.arange(n)

    if ct in ("line_percent", "area_percent", "bar_percent"):
        ser = _pct(ser)
        unit = "%"
    band_lo = band_hi = None
    if ct == "line_band":
        lo = next((s for s in ser if s.get("role") == "lower"), None)
        hi = next((s for s in ser if s.get("role") == "upper"), None)
        need(lo is not None and hi is not None, "line_band는 role='lower'와 role='upper' 계열이 각각 하나씩 필요합니다",
             example=[{"name": "실적", "values": [120, 138, None]}, {"name": "전망", "role": "forecast", "values": [None, 138, 160]},
                      {"name": "하한", "role": "lower", "values": [None, 138, 150]}, {"name": "상한", "role": "upper", "values": [None, 138, 172]}])
        band_lo, band_hi = lo, hi
        ser = [s for s in ser if s.get("role") not in ("lower", "upper")]

    cols = colors_for(ser)
    stacked = ct in ("line_stacked", "area_stacked", "area_percent", "line_percent", "bar_stacked", "bar_percent", "hbar_stacked")
    horizontal = ct.startswith("hbar")
    kinds = []
    for i, s in enumerate(ser):
        k = s.get("kind") or s.get("type")
        if ct == "combo":
            k = k or ("bar" if i == 0 else "line")
        elif ct.startswith(("bar", "hbar")):
            k = "bar"
        elif ct.startswith("area"):
            k = "area"
        else:
            k = "line"
        kinds.append(k)
    right = [str(s.get("axis", "")).lower() in ("right", "1", "secondary") for s in ser]
    has_right = any(right)
    legend = len(ser) > 1 or band_lo is not None
    h = 3.4 if not horizontal else max(2.2, 0.9 + 0.32 * n)
    with figure(h, o) as fig:
        top = top_for(fig, title, sub, o, legend)
        bot = 0.2 if (horizontal and unit) else 0.13
        ax = fig.add_axes([0.16 if horizontal else 0.09, bot, (0.86 if has_right else 0.89) - (0.07 if horizontal else 0), top - bot - 0.02])
        ax2 = ax.twinx() if has_right else None
        style_axes(ax, grid="x" if horizontal else "y")
        if ax2 is not None:
            for s_ in ("top", "left"):
                ax2.spines[s_].set_visible(False)
            ax2.spines["right"].set_color(st.AXIS)
            ax2.tick_params(length=0)
        _ref_lines(ax, o, horizontal)
        cum = np.zeros(n)
        nbar = sum(1 for k, r in zip(kinds, right) if k == "bar" and not stacked)
        bar_i = 0
        bw = 0.7 if stacked or nbar <= 1 else 0.8 / nbar
        lab_mode = label_mode(o, n, len(ser))
        dec_all = decimals_of([v for s in ser for v in s["values"]])
        line_labels = {}  # x -> [(key, y, text, color, axis)]
        leg = []
        vmax = 0.0
        for i, s in enumerate(ser):
            a = ax2 if right[i] else ax
            vals = np.array([np.nan if v is None else v for v in s["values"]], float)
            c = cols[i]
            k = kinds[i]
            dec = decimals_of(s["values"])
            suffix = s.get("suffix", "")
            if k == "bar":
                if stacked:
                    base = cum.copy()
                    vv = np.nan_to_num(vals)
                    if horizontal:
                        a.barh(x, vv, left=base, height=bw, color=c, zorder=2)
                    else:
                        a.bar(x, vv, bottom=base, width=bw, color=c, zorder=2)
                    for j in range(n):
                        if vv[j] and o.get("show_values", True) is not False:
                            pos = base[j] + vv[j] / 2
                            a.text(*((pos, j) if horizontal else (j, pos)), st.fmt(vv[j], dec) + ("%" if ct.endswith("percent") else ""),
                                   ha="center", va="center", color=st.ink_on(c), fontsize=7.3, fontweight="bold", zorder=4)
                    cum = cum + vv
                else:
                    off = (bar_i - (nbar - 1) / 2) * bw if nbar > 1 else 0
                    bar_i += 1
                    if horizontal:
                        a.barh(x + off, np.nan_to_num(vals), height=bw, color=c, zorder=2)
                    else:
                        a.bar(x + off, np.nan_to_num(vals), width=bw, color=c, zorder=2)
                    if o.get("show_values", True) is not False:
                        for j, v in enumerate(vals):
                            if not np.isnan(v):
                                if horizontal:
                                    a.text(v, j + off, " " + st.fmt(v, dec) + suffix, ha="left", va="center", color=c, fontsize=st.LABEL_SIZE, fontweight="bold")
                                else:
                                    a.text(j + off, v, st.fmt(v, dec) + suffix, ha="center", va="bottom", color=c, fontsize=st.LABEL_SIZE, fontweight="bold")
                    vmax = max(vmax, np.nanmax(vals) if np.any(~np.isnan(vals)) else 0)
                leg.append((s["name"], c, "patch"))
            else:
                yv = vals + cum if stacked else vals
                base = cum.copy()
                ls = "--" if s.get("role") == "forecast" else "-"
                drawstyle = "steps-post" if ct == "step_line" else "default"
                if k == "area":
                    if stacked:
                        a.fill_between(x, base, np.nan_to_num(yv, nan=0), color=c, alpha=0.85, lw=0, zorder=2, step="post" if ct == "step_line" else None)
                    else:
                        a.fill_between(x, 0, yv, color=c, alpha=0.22, lw=0, zorder=2)
                        a.plot(x, yv, color=c, lw=1.8, zorder=3)
                    leg.append((s["name"], c, "patch"))
                else:
                    if ct == "step_line":
                        a.plot([n - 1, n - 0.5], [yv[-1], yv[-1]], color=c, lw=2, zorder=3)
                    a.plot(x, yv, color=c, lw=2, ls=ls, drawstyle=drawstyle, zorder=3,
                           marker="o" if (ct in ("line_marker",) or n <= 12) and ct != "step_line" else None, markersize=4)
                    leg.append((s["name"], c, "dashed" if ls == "--" else "line"))
                if stacked:
                    cum = np.nan_to_num(yv, nan=0)
                # 라벨
                if lab_mode != "none":
                    idx = [j for j in range(n) if not np.isnan(vals[j])]
                    if (lab_mode == "last" or (ct == "combo" and right[i] and k == "area")) and idx:
                        idx = [idx[-1]]
                    for j in idx:
                        if stacked and k == "area":
                            a.text(j, base[j] + vals[j] / 2, st.fmt(vals[j], dec) + ("%" if ct.endswith("percent") else ""),
                                   ha="center", va="center", color=st.ink_on(c), fontsize=7.3, fontweight="bold", zorder=5)
                        else:
                            line_labels.setdefault(j, []).append((i, yv[j], st.fmt(vals[j], dec) + suffix, c, a))
                if not stacked:
                    vmax = max(vmax, np.nanmax(yv) if np.any(~np.isnan(yv)) else 0)
        if band_lo is not None:
            lo = np.array([np.nan if v is None else v for v in band_lo["values"]], float)
            hi = np.array([np.nan if v is None else v for v in band_hi["values"]], float)
            ax.fill_between(x, lo, hi, color=st.NAVY, alpha=0.13, lw=0, zorder=1)
            leg.append((f"{band_lo['name']}~{band_hi['name']}", "#C9D4E8", "patch"))
            vmax = max(vmax, np.nanmax(hi))
        if stacked:
            vmax = max(vmax, float(np.nanmax(cum)) if len(cum) else 0)
        # 꺾은선 라벨 배치(같은 x에서 겹치면 벌림)
        if line_labels:
            yr = (ax.get_ylim()[1] - ax.get_ylim()[0]) or 1
            for j, items in line_labels.items():
                for a in {id(it[4]): it[4] for it in items}.values():
                    its, seen = [], set()
                    for it in items:
                        if it[4] is a and (it[2], round(float(it[1]), 6)) not in seen:
                            seen.add((it[2], round(float(it[1]), 6)))
                            its.append(it)
                    lr = a.get_ylim()
                    gap = (lr[1] - lr[0]) * 0.07
                    pos = _spread([(it[0], it[1]) for it in its], gap)
                    last_only = lab_mode == "last"
                    for it in its:
                        if ct == "step_line":
                            a.annotate(it[2], (j, it[1]), xytext=(3, 3), textcoords="offset points", ha="left", va="bottom",
                                       color=it[3], fontsize=st.LABEL_SIZE, fontweight="bold", zorder=6)
                        elif last_only:
                            a.text(j + 0.12, pos[it[0]], it[2], ha="left", va="center", color=it[3], fontsize=st.LABEL_SIZE, fontweight="bold", zorder=6)
                        else:
                            a.annotate(it[2], (j, it[1]), xytext=(0, 5 + (pos[it[0]] - it[1]) / yr * 100), textcoords="offset points",
                                       ha="center", va="bottom", color=it[3], fontsize=st.LABEL_SIZE, fontweight="bold", zorder=6)
        # 축
        if horizontal:
            ax.set_yticks(x, cats)
            ax.invert_yaxis()
            ax.xaxis.set_major_formatter(num_formatter())
            ax.set_xlim(left=min(0, ax.get_xlim()[0]), right=max(ax.get_xlim()[1], vmax * 1.15))
            axis_unit(ax, unit, "x")
        else:
            ax.set_xticks(x, cats)
            ax.set_xlim(-0.6, n - 0.4 + (0.6 if lab_mode == "last" else 0))
            ax.yaxis.set_major_formatter(num_formatter())
            lo_ = o.get("y_min")
            hi_ = o.get("y_max")
            allv = [v for s_ in ser + ([band_lo, band_hi] if band_lo else []) for v in s_["values"] if v is not None]
            if ct.endswith("percent"):
                ax.set_ylim(0, 112)
                ax.set_yticks([0, 20, 40, 60, 80, 100])
            elif ax2 is None or not any(k == "bar" for k in kinds):
                cur = ax.get_ylim()
                zero_based = stacked or any(k in ("bar", "area") for k in kinds) or (allv and min(allv) < 0.5 * max(allv)) or (allv and min(allv) <= 0)
                lo_auto = min(0, cur[0]) if zero_based else min(allv) - (max(allv) - min(allv)) * 0.25
                hi_auto = max(cur[1], vmax * 1.15) if zero_based else max(allv) + (max(allv) - min(allv)) * 0.3
                # 1.4.0: 지정한 y_min·y_max 밖에 값이 있으면 숫자 라벨이 그림 밖 먼 곳에 찍혀 그림이 수만 픽셀로 커지다 메모리 오류가 났다
                if allv and lo_ is not None and min(allv) < float(lo_):
                    notes.append(f"y_min({st.fmt(lo_)})보다 작은 값이 있어 축 아래 끝을 값에 맞췄습니다")
                    lo_ = None
                if allv and hi_ is not None and max(allv) > float(hi_):
                    notes.append(f"y_max({st.fmt(hi_)})보다 큰 값이 있어 축 위 끝을 값에 맞췄습니다")
                    hi_ = None
                ax.set_ylim(lo_ if lo_ is not None else lo_auto, hi_ if hi_ is not None else hi_auto)
            axis_unit(ax, unit)
            if ax2 is not None:
                rvals = [v for s_, r in zip(ser, right) if r for v in s_["values"] if v is not None]
                rk = [k for k, r in zip(kinds, right) if r]
                if rvals and any(k == "bar" for k, r in zip(kinds, right) if not r):
                    lvals = [v for s_, r in zip(ser, right) if not r for v in s_["values"] if v is not None]
                    ax.set_ylim(min(0, min(lvals)), max(lvals) * 1.75)
                    if "area" in rk:
                        ax2.set_ylim(0, max(rvals) * 1.12)
                    else:
                        span = (max(rvals) - min(rvals)) or abs(max(rvals)) or 1
                        ax2.set_ylim(min(rvals) - span * 1.1, max(rvals) + span * 0.25)
                    ax.set_zorder(ax2.get_zorder() + 1)
                    ax.patch.set_visible(False)
                else:
                    ax2.set_ylim(0, ax2.get_ylim()[1] * 1.12)
                ax2.yaxis.set_major_formatter(num_formatter())
                r_unit = next((s.get("unit") or s.get("suffix") for s, r in zip(ser, right) if r), None)
                if r_unit:
                    ax2.set_ylabel(f"({r_unit})", color=st.MUTED, fontsize=st.FONT_SIZE - 1)
            if len(cats) > 8 and max(len(c) for c in cats) > 4:
                for t in ax.get_xticklabels():
                    t.set_rotation(30)
                    t.set_ha("right")
        if legend:
            legend_top(fig, leg, title, sub, o)
        put_title(fig, title, sub, o)
        if ax2 is not None and not horizontal:
            _lift_secondary(fig, ax, ax2, ser, right, kinds)
        png = to_png(fig)
        w, hh = fig.get_size_inches()
    head, rows = table_from_series(cats, ser + ([band_lo, band_hi] if band_lo else []))
    return Result(png, notes, table=(head, rows), w=int(w * st.DPI), h=int(hh * st.DPI))


def _lift_secondary(fig, ax, ax2, ser, right, kinds):
    """혼합(막대 + 보조축 선): 선의 가장 낮은 점이 막대·막대 숫자 띠보다 위에 오도록 보조축 범위를 잡는다(1.4.0).
    이전에는 보조축을 값 범위로만 잡아 선의 값 폭이 넓으면(2%~27%) 낮은 점이 막대 숫자를 가로질렀다(계정 chart-spec.js 2026-11-25.2와 같은 원칙).
    값이 모두 0 이상이면 보조축의 음수 눈금은 쓰지 않는다."""
    from matplotlib.ticker import FuncFormatter

    from .. import declutter
    rvals = [v for s_, r in zip(ser, right) if r for v in s_["values"] if v is not None]
    if not rvals or not any(k == "bar" for k, r in zip(kinds, right) if not r) or any(k == "area" for k, r in zip(kinds, right) if r):
        return
    declutter.run(fig)  # 막대 숫자를 먼저 세우거나 줄여 실제 높이를 잰다
    rr = fig.canvas.get_renderer()
    tops = [t.get_window_extent(rr).y1 for t in ax.texts if t.get_visible() and t.get_text().strip()]
    tops += [p.get_window_extent(rr).y1 for p in ax.patches]
    if not tops:
        return
    f = min(0.8, (max(tops) - ax.bbox.y0) / ax.bbox.height + 0.06)
    mn, mx = min(rvals), max(rvals)
    span = (mx - mn) or abs(mx) or 1
    hi = mx + span * 0.18
    lo = (mn - f * hi) / (1 - f)
    ax2.set_ylim(lo, hi)
    if mn >= 0:
        ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _p=None: "" if v < -1e-9 else st.fmt(v)))


def draw_stream(args: dict, o: dict) -> Result:
    cats = categories(args)
    ser = series(args, len(cats))
    title, sub = args.get("title"), args.get("subtitle")
    cols = colors_for(ser, wide=True)
    x = np.arange(len(cats))
    ys = np.array([[v or 0 for v in s["values"]] for s in ser], float)
    with figure(3.4, o) as fig:
        top = top_for(fig, title, sub, o, True)
        ax = fig.add_axes([0.05, 0.13, 0.92, top - 0.15])
        style_axes(ax, grid="none")
        # 부드럽게 보간
        xs = np.linspace(0, len(cats) - 1, 200)
        ysm = np.array([np.interp(xs, x, y) for y in ys])
        ax.stackplot(xs, ysm, baseline="wiggle", colors=cols, alpha=0.9, lw=0)
        ax.set_yticks([])
        labels = [c[5:7].lstrip("0") + "월" if len(c) == 10 and c[4] == "-" else c for c in cats]
        ax.set_xticks(x, labels)
        ax.spines["bottom"].set_visible(False)
        legend_top(fig, [(s["name"], c, "patch") for s, c in zip(ser, cols)], title, sub, o)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["스트림그래프: 세로 폭이 값의 크기, 세로 위치에는 의미가 없습니다"], table=table_from_series(cats, ser))


def draw_lollipop(args: dict, o: dict) -> Result:
    cats = categories(args)
    ser = series(args, len(cats))
    title, sub = args.get("title"), args.get("subtitle")
    vals = [v or 0 for v in ser[0]["values"]]
    pairs = list(zip(cats, vals))
    if o.get("sort", "desc") == "desc":
        pairs.sort(key=lambda p: -p[1])
    c = st.color(ser[0].get("color"), st.NAVY)
    hl = o.get("highlight")
    dec = decimals_of(vals)
    n = len(pairs)
    with figure(max(2.2, 0.8 + 0.3 * n), o) as fig:
        top = top_for(fig, title, sub, o, False)
        ax = fig.add_axes([0.2, 0.17 if args.get('unit') else 0.08, 0.74, top - (0.19 if args.get('unit') else 0.1)])
        style_axes(ax, grid="x")
        y = np.arange(n)
        for i, (name, v) in enumerate(pairs):
            cc = st.ORANGE if hl and name == hl else c
            ax.hlines(i, 0, v, color=cc, lw=1.6)
            ax.scatter([v], [i], color=cc, s=46, zorder=3)
            ax.text(v, i, "  " + st.fmt(v, dec), va="center", ha="left", color=cc, fontsize=st.LABEL_SIZE, fontweight="bold")
        ax.set_yticks(y, [p[0] for p in pairs])
        ax.invert_yaxis()
        ax.set_xlim(0, max(v for _, v in pairs) * 1.15 or 1)
        ax.xaxis.set_major_formatter(num_formatter())
        axis_unit(ax, args.get("unit"), "x")
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, table=(["항목", ser[0]["name"]], [list(p) for p in pairs]))


def draw_dumbbell(args: dict, o: dict) -> Result:
    cats = categories(args)
    ser = series(args, len(cats), min_count=2)
    title, sub = args.get("title"), args.get("subtitle")
    a, b = ser[0], ser[1]
    ca, cb = st.color(a.get("color"), st.GRAY), st.color(b.get("color"), st.NAVY)
    dec = decimals_of(a["values"] + b["values"])
    n = len(cats)
    with figure(max(2.2, 0.9 + 0.32 * n), o) as fig:
        top = top_for(fig, title, sub, o, True)
        ax = fig.add_axes([0.2, 0.17 if args.get('unit') else 0.1, 0.74, top - (0.19 if args.get('unit') else 0.12)])
        style_axes(ax, grid="x")
        for i, (va, vb) in enumerate(zip(a["values"], b["values"])):
            if va is None or vb is None:
                continue
            up = vb >= va
            ax.hlines(i, va, vb, color=st.UP if up else st.DOWN, lw=2.2, alpha=0.55)
            ax.scatter([va], [i], color=ca, s=42, zorder=3)
            ax.scatter([vb], [i], color=cb, s=42, zorder=3)
            ax.text(max(va, vb), i, "  " + st.fmt(vb, dec) + f" ({'+' if up else ''}{st.fmt(vb - va, dec)})", va="center", ha="left",
                    fontsize=st.LABEL_SIZE, fontweight="bold", color=cb)
        ax.set_yticks(range(n), cats)
        ax.invert_yaxis()
        hi = max(max(v for v in a["values"] if v is not None), max(v for v in b["values"] if v is not None))
        lo = min(min(v for v in a["values"] if v is not None), min(v for v in b["values"] if v is not None))
        ax.set_xlim(min(0, lo) if lo >= 0 and lo < hi * 0.3 else lo * 0.9, hi * 1.2)
        ax.xaxis.set_major_formatter(num_formatter())
        axis_unit(ax, args.get("unit"), "x")
        legend_top(fig, [(a["name"], ca, "marker"), (b["name"], cb, "marker")], title, sub, o)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, table=table_from_series(cats, [a, b]))


def draw_polar_bar(args: dict, o: dict) -> Result:
    cats = categories(args)
    ser = series(args, len(cats))
    title, sub = args.get("title"), args.get("subtitle")
    vals = [v or 0 for v in ser[0]["values"]]
    vmax = float(o.get("max") or (100 if (args.get("unit") == "%") else max(vals) * 1.1))
    cols = st.palette(len(cats), wide=True)
    with figure(3.6, o) as fig:
        top = top_for(fig, title, sub, o, False)
        ax = fig.add_axes([0.05, 0.04, 0.9, top - 0.06])
        ax.set_aspect("equal")
        ax.axis("off")
        n = len(cats)
        width = 0.75 / n
        for i, (c, v) in enumerate(zip(cats, vals)):
            r = 1 - i * (width + 0.04)
            ax.add_patch(_arc(r, width, -180, 90, st.LIGHT))
            ax.add_patch(_arc(r, width, 90 - 270 * min(v / vmax, 1), 90, cols[i]))
            ax.text(-0.04, r - width / 2, f"{c} {st.fmt(v)}{args.get('unit') or ''}", ha="right", va="center", fontsize=st.LABEL_SIZE, fontweight="bold", color=cols[i])
        ax.set_xlim(-1.15, 1.15)
        ax.set_ylim(-1.1, 1.1)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["방사형 막대: 3/4 바퀴가 최대값(기본 100%)입니다"], table=table_from_series(cats, ser))


def _arc(r, width, a0, a1, color):
    from matplotlib.patches import Wedge
    return Wedge((0, 0), r, a0, a1, width=width, facecolor=color, edgecolor="none")


def draw_pictorial_bar(args: dict, o: dict) -> Result:
    cats = categories(args)
    ser = series(args, len(cats))
    title, sub = args.get("title"), args.get("subtitle")
    vals = [v or 0 for v in ser[0]["values"]]
    per = float(o.get("per") or _nice_unit(max(vals) / 12))
    c = st.color(ser[0].get("color"), st.NAVY)
    n = len(cats)
    with figure(max(2.0, 0.8 + 0.4 * n), o) as fig:
        top = top_for(fig, title, sub, o, False)
        ax = fig.add_axes([0.14, 0.12, 0.82, top - 0.14])
        ax.axis("off")
        maxk = max(math.ceil(v / per) for v in vals) or 1
        for i, (name, v) in enumerate(zip(cats, vals)):
            full, frac = int(v // per), (v % per) / per
            y = n - 1 - i
            for k in range(full):
                ax.add_patch(_person(k, y, c, 1))
            if frac > 0.05:
                ax.add_patch(_person(full, y, c, frac))
            ax.text(-0.4, y, name, ha="right", va="center", fontsize=st.FONT_SIZE)
            ax.text(math.ceil(v / per) + 0.2, y, st.fmt(v) + (args.get("unit") or ""), ha="left", va="center", fontsize=st.LABEL_SIZE, fontweight="bold", color=c)
        ax.set_xlim(-0.5, maxk + 2.5)
        ax.set_ylim(-0.7, n - 0.3)
        ax.text(1, -0.02, f"■ 하나 = {st.fmt(per)}{args.get('unit') or ''}", transform=ax.transAxes, ha="right", va="top", fontsize=7.5, color=st.MUTED)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, table=table_from_series(cats, ser))


def _nice_unit(x):
    if x <= 0:
        return 1
    e = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 5, 10):
        if x <= m * e:
            return m * e
    return 10 * e


def _person(k, y, c, frac):
    from matplotlib.patches import FancyBboxPatch
    return FancyBboxPatch((k + 0.1, y - 0.3), 0.8 * frac, 0.6, boxstyle="round,pad=0,rounding_size=0.12", facecolor=c, edgecolor="none")


def draw_bump(args: dict, o: dict) -> Result:
    cats = categories(args)
    ser = series(args, len(cats))
    title, sub = args.get("title"), args.get("subtitle")
    hl = o.get("highlight")
    cols = colors_for(ser, wide=True)
    x = np.arange(len(cats))
    with figure(3.2, o) as fig:
        top = top_for(fig, title, sub, o, False)
        ax = fig.add_axes([0.06, 0.12, 0.8, top - 0.14])
        style_axes(ax, grid="none")
        for s, c in zip(ser, cols):
            v = np.array([np.nan if x_ is None else x_ for x_ in s["values"]], float)
            dim = hl and s["name"] != hl
            cc = st.GRAY if dim else c
            ax.plot(x, v, color=cc, lw=1.5 if dim else 3, marker="o", markersize=12 if not dim else 9, zorder=2 if dim else 3)
            for j, r in enumerate(v):
                if not np.isnan(r):
                    ax.text(j, r, f"{int(r)}", ha="center", va="center", color="white", fontsize=7, fontweight="bold", zorder=4)
            last = [j for j in range(len(v)) if not np.isnan(v[j])][-1]
            ax.text(last + 0.18, v[last], s["name"], va="center", ha="left", color=cc, fontsize=st.FONT_SIZE, fontweight="bold")
        ax.invert_yaxis()
        ax.set_yticks(range(1, int(np.nanmax([[v for v in s["values"] if v is not None] for s in ser])) + 1) if False else [])
        ax.set_xticks(x, cats)
        ax.set_xlim(-0.4, len(cats) - 0.4)
        ax.spines["bottom"].set_visible(False)
        ax.set_ylabel("순위", color=st.MUTED)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["범프 차트: 위쪽이 1위입니다"], table=table_from_series(cats, ser))


def draw_pie_family(ct: str, args: dict, o: dict) -> Result:
    cats = categories(args)
    ser = series(args, len(cats))
    title, sub = args.get("title"), args.get("subtitle")
    vals = [max(v or 0, 0) for v in ser[0]["values"]]
    total = sum(vals)
    need(total > 0, "원형 차트의 값 합계가 0입니다")
    notes = color_warn(len(cats))
    if len(cats) > 7:
        notes.append(f"원형 계열에 항목이 {len(cats)}개입니다. 7개를 넘으면 읽기 어려우므로 작은 항목을 '기타'로 묶는 것을 권합니다")
    cols = [st.color(c, d) for c, d in zip(as_list(o.get("point_colors"), "options.point_colors") or [None] * len(cats), st.palette(len(cats), wide=True))]
    unit = args.get("unit") or ""
    dec = decimals_of(vals)
    hl = o.get("highlight")
    with figure(3.3 if ct != "half_donut" else 2.6, o) as fig:
        top = top_for(fig, title, sub, o, True)
        ax = fig.add_axes([0.08, 0.04, 0.84, top - 0.06])
        ax.set_aspect("equal")
        ax.axis("off")
        if ct == "rose":
            n = len(vals)
            vmax = max(vals)
            ang = 360 / n
            for i, v in enumerate(vals):
                r = math.sqrt(v / vmax)
                a0 = 90 - (i + 1) * ang
                ax.add_patch(_arc(r, r, a0 + 0.6, a0 + ang - 0.6, cols[i]))
                mid = math.radians(a0 + ang / 2)
                rr = max(r, 0.35) + 0.12
                ax.text(rr * math.cos(mid), rr * math.sin(mid), f"{st.fmt(v, dec)}{unit}", ha="center", va="center", fontsize=st.LABEL_SIZE,
                        fontweight="bold", color=cols[i])
            ax.set_xlim(-1.25, 1.25)
            ax.set_ylim(-1.2, 1.2)
            notes.append("나이팅게일 로즈: 조각의 면적이 값에 비례하도록 반지름을 값의 제곱근으로 그렸습니다")
        else:
            start, span = (180, 180) if ct == "half_donut" else (90, 360)
            width = 0.42 if ct == "half_donut" else None
            a = start
            for i, v in enumerate(vals):
                sweep = span * v / total
                a1 = a - sweep
                off = 0.08 if (ct == "pie_exploded" and ((hl and cats[i] == hl) or (not hl and i == int(np.argmax(vals))))) else 0
                mid = math.radians((a + a1) / 2)
                dx, dy = off * math.cos(mid), off * math.sin(mid)
                from matplotlib.patches import Wedge
                ax.add_patch(Wedge((dx, dy), 1, a1, a, width=width, facecolor=cols[i], edgecolor="white", lw=1.2))
                pct = v / total * 100
                if width:
                    rr = 1 - width / 2
                else:
                    rr = 0.62
                txt = f"{st.fmt(pct, 0)}%" if (unit == "%" or ct == "half_donut") else f"{st.fmt(v, dec)}\n({st.fmt(pct, 0)}%)"
                if pct >= 6:
                    ax.text(dx + rr * math.cos(mid), dy + rr * math.sin(mid), txt, ha="center", va="center", color=st.ink_on(cols[i]),
                            fontsize=st.LABEL_SIZE, fontweight="bold", linespacing=1.2)
                else:
                    ax.text(dx + 1.15 * math.cos(mid), dy + 1.15 * math.sin(mid), txt.replace("\n", " "), ha="center", va="center",
                            color=cols[i], fontsize=st.LABEL_SIZE - 0.5, fontweight="bold")
                a = a1
            if ct == "half_donut":
                ax.text(0, 0.12, st.fmt(total, dec) + unit if unit != "%" else "", ha="center", va="center", fontsize=11, fontweight="bold", color=st.INK)
                ax.set_xlim(-1.2, 1.2)
                ax.set_ylim(-0.1, 1.15)
            else:
                ax.set_xlim(-1.3, 1.3)
                ax.set_ylim(-1.2, 1.2)
        legend_top(fig, [(c, col, "patch") for c, col in zip(cats, cols)], title, sub, o)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    head = ["항목", ser[0]["name"], "비율(%)"]
    rows = [[c, v, round(v / total * 100, 1)] for c, v in zip(cats, vals)]
    return Result(png, notes, table=(head, rows))


def draw_waterfall(args: dict, o: dict) -> Result:
    cats = categories(args)
    ser = series(args, len(cats))
    title, sub = args.get("title"), args.get("subtitle")
    deltas = ser[0]["values"]
    totals = set(str(t) for t in as_list(o.get("totals"), "options.totals")) or {cats[0], cats[-1]}
    run = 0.0
    bars = []  # (bottom, height, kind, label_value)
    for c, d in zip(cats, deltas):
        if c in totals:
            v = d if d is not None else run
            run = v
            bars.append((0, v, "total", v))
        else:
            d = d or 0
            bars.append((min(run, run + d), abs(d), "up" if d >= 0 else "down", d))
            run += d
    col = {"total": st.NAVY, "up": st.TEAL, "down": st.ORANGE}
    dec = decimals_of([b[3] for b in bars])
    n = len(cats)
    with figure(3.3, o) as fig:
        top = top_for(fig, title, sub, o, True)
        ax = fig.add_axes([0.09, 0.15, 0.88, top - 0.17])
        style_axes(ax, grid="y")
        tops = []
        for i, (b, hgt, k, lv) in enumerate(bars):
            ax.bar(i, hgt, bottom=b, color=col[k], width=0.6, zorder=2)
            t = st.fmt(lv, dec) if k == "total" else ("+" if lv >= 0 else "") + st.fmt(lv, dec)
            ax.text(i, b + hgt, t, ha="center", va="bottom", fontsize=st.LABEL_SIZE, fontweight="bold", color=col[k])
            tops.append(b + hgt)
            if i < n - 1:
                lvl = b + hgt if k != "down" else b
                if k == "total":
                    lvl = b + hgt
                ax.plot([i + 0.3, i + 0.7], [lvl, lvl], color=st.MUTED, lw=0.8, ls=":")
        ax.set_xticks(range(n), cats)
        ax.set_ylim(min(0, min(b for b, *_ in bars)), max(tops) * 1.15)
        ax.yaxis.set_major_formatter(num_formatter())
        axis_unit(ax, args.get("unit"))
        legend_top(fig, [("합계", st.NAVY, "patch"), ("증가", st.TEAL, "patch"), ("감소", st.ORANGE, "patch")], title, sub, o)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    rows = [[c, b[3], b[2] == "total" and "합계" or ("증가" if b[2] == "up" else "감소")] for c, b in zip(cats, bars)]
    return Result(png, table=(["항목", ser[0]["name"], "구분"], rows))


def draw_funnel(args: dict, o: dict) -> Result:
    cats = categories(args)
    ser = series(args, len(cats))
    title, sub = args.get("title"), args.get("subtitle")
    vals = [v or 0 for v in ser[0]["values"]]
    vmax = max(vals) or 1
    n = len(cats)
    cols = st.seq(n)[::-1]
    with figure(max(2.4, 0.6 + 0.45 * n), o) as fig:
        top = top_for(fig, title, sub, o, False)
        ax = fig.add_axes([0.03, 0.04, 0.94, top - 0.06])
        ax.axis("off")
        for i, (c, v) in enumerate(zip(cats, vals)):
            w0 = v / vmax
            w1 = (vals[i + 1] / vmax) if i + 1 < n else w0 * 0.85
            y = n - 1 - i
            from matplotlib.patches import Polygon
            ax.add_patch(Polygon([(-w0 / 2, y + 0.45), (w0 / 2, y + 0.45), (w1 / 2, y - 0.45), (-w1 / 2, y - 0.45)], closed=True,
                                 facecolor=cols[i], edgecolor="white"))
            ax.text(0, y, f"{c}  {st.fmt(v)}{args.get('unit') or ''}", ha="center", va="center", color=st.ink_on(cols[i]), fontsize=st.LABEL_SIZE, fontweight="bold")
            if i > 0 and vals[i - 1]:
                ax.text(0.56, y + 0.5, f"전환 {v / vals[i - 1] * 100:.0f}%", ha="left", va="center", fontsize=7.5, color=st.MUTED)
        ax.set_xlim(-0.6, 0.85)
        ax.set_ylim(-0.6, n - 0.4)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    rows = [[c, v, (round(v / vals[i - 1] * 100, 1) if i and vals[i - 1] else None)] for i, (c, v) in enumerate(zip(cats, vals))]
    return Result(png, table=(["단계", ser[0]["name"], "전 단계 대비(%)"], rows))


def draw_radar(ct: str, args: dict, o: dict) -> Result:
    cats = categories(args)
    ser = series(args, len(cats))
    title, sub = args.get("title"), args.get("subtitle")
    cols = colors_for(ser)
    n = len(cats)
    vmax = float(o.get("max") or max(v or 0 for s in ser for v in s["values"]) * 1.1)
    ang = [math.pi / 2 - 2 * math.pi * i / n for i in range(n)]
    with figure(3.6, o) as fig:
        top = top_for(fig, title, sub, o, len(ser) > 1)
        ax = fig.add_axes([0.1, 0.03, 0.8, top - 0.05])
        ax.set_aspect("equal")
        ax.axis("off")
        for lv in (0.25, 0.5, 0.75, 1.0):
            pts = [(lv * math.cos(a), lv * math.sin(a)) for a in ang]
            ax.plot([p[0] for p in pts + pts[:1]], [p[1] for p in pts + pts[:1]], color=st.GRID, lw=0.8)
            ax.text(0.02, lv, st.fmt(vmax * lv), fontsize=6.5, color=st.MUTED, va="bottom", zorder=6,
                    bbox=dict(boxstyle="square,pad=0.05", facecolor="white", edgecolor="none", alpha=0.75))  # 1.4.0: 계열 선이 눈금 숫자를 가로질렀다
        for a, c in zip(ang, cats):
            ax.plot([0, math.cos(a)], [0, math.sin(a)], color=st.GRID, lw=0.8)
            ax.text(1.14 * math.cos(a), 1.12 * math.sin(a), c, ha="center", va="center", fontsize=st.FONT_SIZE, color=st.INK2)
        for s, c in zip(ser, cols):
            pts = [((v or 0) / vmax * math.cos(a), (v or 0) / vmax * math.sin(a)) for v, a in zip(s["values"], ang)]
            xs, ys = [p[0] for p in pts + pts[:1]], [p[1] for p in pts + pts[:1]]
            ax.plot(xs, ys, color=c, lw=2, marker="o", markersize=3.5)
            if ct == "radar_filled":
                ax.fill(xs, ys, color=c, alpha=0.22)
        ax.set_xlim(-1.35, 1.35)
        ax.set_ylim(-1.25, 1.25)
        if len(ser) > 1:
            legend_top(fig, [(s["name"], c, "line") for s, c in zip(ser, cols)], title, sub, o)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, table=table_from_series(cats, ser, "항목"))


def draw(ct: str, args: dict, o: dict) -> Result:
    if ct in LINE_TYPES:
        return draw_line_family(ct, args, o)
    if ct == "stream":
        return draw_stream(args, o)
    if ct == "lollipop":
        return draw_lollipop(args, o)
    if ct == "dumbbell":
        return draw_dumbbell(args, o)
    if ct == "polar_bar":
        return draw_polar_bar(args, o)
    if ct == "pictorial_bar":
        return draw_pictorial_bar(args, o)
    if ct == "bump":
        return draw_bump(args, o)
    if ct in ("pie_exploded", "half_donut", "rose", "pie", "donut"):
        return draw_pie_family(ct, args, o)
    if ct == "waterfall":
        return draw_waterfall(args, o)
    if ct == "funnel":
        return draw_funnel(args, o)
    if ct in ("radar", "radar_filled"):
        return draw_radar(ct, args, o)
    raise ValueError(ct)
