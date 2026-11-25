"""두 숫자의 관계·날짜 시계열 — 산점도·거품·추세선·사분면·연결 산점도·시계열(사건 표시)·관리도."""
from __future__ import annotations

import datetime as dt

import matplotlib.dates as mdates
import numpy as np

from .. import style as st
from ..core import Result, figure, legend_top, num_formatter, put_title, style_axes, to_png, top_for
from ..errors import as_dict, as_list, as_number, need

EX = [{"name": "제품", "points": [{"x": 12, "y": 8.5, "label": "A"}, {"x": 20, "y": 11.2, "label": "B"}]}]


def _date(v, where):
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(v / 1000 if v > 1e11 else v)
    s = str(v).strip()
    for f in ("%Y-%m-%d", "%Y-%m", "%Y.%m.%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(s[:len(dt.datetime.now().strftime(f))] if "T" not in f else s[:19], f)
        except ValueError:
            continue
    need(False, f"{where}의 날짜 {v!r}를 읽을 수 없습니다", hint="'YYYY-MM-DD' 형식으로 넣으세요")


def _points(args, date_x=False):
    items = as_list(args.get("series"), "series")
    need(items, "series=[{name, points:[{x,y}]}]가 필요합니다", example=EX)
    out = []
    for i, s in enumerate(items):
        s = as_dict(s, f"series[{i}]")
        pts = []
        for j, p in enumerate(as_list(s.get("points", s.get("data")), f"series[{i}].points")):
            if isinstance(p, (list, tuple)):
                p = {"x": p[0], "y": p[1], **({"size": p[2]} if len(p) > 2 else {})}
            p = as_dict(p, f"series[{i}].points[{j}]")
            x = _date(p.get("x"), f"series[{i}].points[{j}].x") if date_x else as_number(p.get("x"), f"series[{i}].points[{j}].x")
            pts.append({"x": x, "y": as_number(p.get("y"), f"series[{i}].points[{j}].y"),
                        "size": as_number(p.get("size"), "size") if p.get("size") is not None else None, "label": p.get("label")})
        need(pts, f"series[{i}].points가 비어 있습니다", example=EX)
        out.append({"name": str(s.get("name") or f"계열{i + 1}"), "points": pts, "color": s.get("color")})
    return out


def _labels(ax, pts, color, o, small=False):
    if o.get("show_labels") is False:
        return
    shown = [p for p in pts if p.get("label")]
    if len(shown) > 60 and not o.get("show_labels"):  # 1.4.0: 25 → 60(겹치는 이름은 declutter가 옮기거나 생략)
        return
    for p in shown:
        ax.annotate(str(p["label"]), (p["x"], p["y"]), xytext=(4, 4), textcoords="offset points", fontsize=7.2 if small else 7.6, color=st.INK2)


def draw(ct: str, args: dict, o: dict) -> Result:
    date_x = ct in ("time_series", "control_chart")
    ser = _points(args, date_x)
    ref_texts = []
    title, sub = args.get("title"), args.get("subtitle")
    cols = [st.color(s.get("color"), c) for s, c in zip(ser, st.palette(len(ser)))]
    notes, computed = [], {}
    legend = len(ser) > 1 or ct in ("scatter_trend", "control_chart") or bool(o.get("diagonal"))
    with figure(3.6, o) as fig:
        top = top_for(fig, title, sub, o, legend)
        ax = fig.add_axes([0.1, 0.14, 0.86, top - 0.16])
        style_axes(ax, grid="both", left_spine=True)
        ax.spines["left"].set_color(st.AXIS)
        leg = []
        allx = [p["x"] for s in ser for p in s["points"] if p["y"] is not None]
        ally = [p["y"] for s in ser for p in s["points"] if p["y"] is not None]
        smax = max([p["size"] or 0 for s in ser for p in s["points"]] + [0])
        for s, c in zip(ser, cols):
            pts = [p for p in s["points"] if p["y"] is not None]
            xs, ys = [p["x"] for p in pts], [p["y"] for p in pts]
            if ct in ("bubble", "quadrant") and smax > 0:
                sz = [60 + 900 * ((p["size"] or 0) / smax) for p in pts]
                ax.scatter(xs, ys, s=sz, color=c, alpha=0.55, edgecolor="white", lw=0.8, zorder=3)
            elif ct == "connected_scatter":
                if o.get("smooth") and len(xs) >= 3:
                    t = np.arange(len(xs))
                    tt = np.linspace(0, len(xs) - 1, 120)
                    from scipy.interpolate import make_interp_spline
                    k = min(3, len(xs) - 1)
                    ax.plot(make_interp_spline(t, xs, k=k)(tt), make_interp_spline(t, ys, k=k)(tt), color=c, lw=1.8, zorder=2)
                else:
                    ax.plot(xs, ys, color=c, lw=1.8, zorder=2)
                for a, b in ([] if o.get("smooth") else zip(pts[:-1], pts[1:])):
                    ax.annotate("", xy=((a["x"] + b["x"]) / 2, (a["y"] + b["y"]) / 2), xytext=(a["x"], a["y"]),
                                arrowprops=dict(arrowstyle="-|>", color=c, lw=0, mutation_scale=14))
                ax.scatter(xs, ys, s=30, color=c, zorder=3)
            elif date_x:
                ax.plot(xs, ys, color=c, lw=1.8, marker="o" if len(xs) <= 40 else None, markersize=3.5, zorder=3)
            else:
                ax.scatter(xs, ys, s=34, color=c, alpha=0.85, edgecolor="white", lw=0.6, zorder=3)
            leg.append((s["name"], c, "line" if (date_x or ct == "connected_scatter") else "marker"))
            if ct != "scatter_trend" or len(pts) <= 25:
                _labels(ax, pts, c, o, small=len(pts) > 12)
        if ct == "scatter_trend" and len(allx) >= 3:
            ax_ = np.array(allx, float)
            ay = np.array(ally, float)
            slope, icpt = np.polyfit(ax_, ay, 1)
            r = float(np.corrcoef(ax_, ay)[0, 1])
            x0, x1 = float(ax_.min()), float(ax_.max())
            ax.plot([x0, x1], [slope * x0 + icpt, slope * x1 + icpt], color=st.ORANGE, lw=1.6, ls="--", zorder=4)
            leg.append((f"추세선 (R²={r * r:.2f})", st.ORANGE, "dashed"))
            notes.append(f"추세선: y = {slope:.4g}·x + {icpt:.4g}, 상관계수 r = {r:.3f}, R² = {r * r:.3f} (n={len(allx)})")
            computed.update(slope=round(float(slope), 6), intercept=round(float(icpt), 6), r=round(r, 4), r2=round(r * r, 4), n=len(allx))
        if ct == "quadrant":
            xm = as_number(o.get("x_split"), "options.x_split")
            ym = as_number(o.get("y_split"), "options.y_split")
            xm = float(np.median(allx)) if xm is None else xm
            ym = float(np.median(ally)) if ym is None else ym
            ax.axvline(xm, color=st.MUTED, lw=1, ls="--", zorder=1)
            ax.axhline(ym, color=st.MUTED, lw=1, ls="--", zorder=1)
            ql = [str(q) for q in as_list(o.get("quadrant_labels"), "options.quadrant_labels")]
            if len(ql) == 4:
                for (tx, ty, ha, va), q in zip(((0.98, 0.97, "right", "top"), (0.02, 0.97, "left", "top"), (0.02, 0.03, "left", "bottom"), (0.98, 0.03, "right", "bottom")), ql):
                    ax.text(tx, ty, q, transform=ax.transAxes, ha=ha, va=va, fontsize=9, fontweight="bold", color=st.MUTED, alpha=0.9)
            notes.append(f"사분면 기준선: x={st.fmt(xm, 2)}, y={st.fmt(ym, 2)}" + (" (중앙값)" if o.get("x_split") is None else ""))
        if o.get("diagonal"):
            lo, hi = min(allx + ally), max(allx + ally)
            pad = (hi - lo) * 0.05
            xx = np.array([lo - pad, hi + pad])
            ax.plot(xx, xx, color=st.INK2, lw=1, zorder=1)
            leg.append(("y = x", st.INK2, "line"))
            tol = as_number(o.get("tolerance"), "options.tolerance")
            if tol:
                ax.fill_between(xx, xx * (1 - tol / 100), xx * (1 + tol / 100), color=st.TEAL, alpha=0.12, lw=0, zorder=0)
                leg.append((f"허용 ±{st.fmt(tol)}%", "#CFE7E0", "patch"))
                out = 0
                for s in ser:
                    for p in s["points"]:
                        if p["y"] is not None and p["x"] and abs(p["y"] / p["x"] - 1) * 100 > tol + 1e-9:
                            out += 1
                            ax.scatter([p["x"]], [p["y"]], s=60, facecolor="none", edgecolor=st.BAD, lw=1.4, zorder=5)
                notes.append(f"허용 범위(±{st.fmt(tol)}%) 밖 {out}건(빨간 원)")
                computed["out_of_tolerance"] = out
        if ct == "time_series":
            for i, e in enumerate(as_list(o.get("events"), "options.events")):
                e = as_dict(e, f"events[{i}]")
                ex = _date(e.get("x", e.get("date")), f"events[{i}].x")
                ax.axvline(ex, color=st.ORANGE, lw=1.1, ls="--", zorder=2)
                ax.text(ex, 1.0, " " + str(e.get("label", "")), transform=ax.get_xaxis_transform(), ha="left", va="top", fontsize=7.8,
                        color=st.ORANGE, fontweight="bold")
        if ct == "control_chart":
            need(len(ser) == 1, "control_chart는 계열 1개만 받습니다")
            ys = np.array(ally, float)
            ucl, lcl, tgt = (as_number(o.get(k), f"options.{k}") for k in ("ucl", "lcl", "target"))
            auto = ucl is None and lcl is None
            mu, sd = float(ys.mean()), float(ys.std(ddof=1)) if len(ys) > 1 else 0.0
            if auto:
                ucl, lcl = mu + 3 * sd, mu - 3 * sd
            if ucl is not None and lcl is not None:
                ax.axhspan(lcl, ucl, color="#E6F2EE", zorder=0)
            n_out = 0
            for p in ser[0]["points"]:
                if p["y"] is not None and ((ucl is not None and p["y"] > ucl) or (lcl is not None and p["y"] < lcl)):
                    n_out += 1
                    ax.scatter([p["x"]], [p["y"]], s=40, color=st.BAD, zorder=5)
            for v, lab, col in ((ucl, "UCL" if auto else "상한", st.BAD), (lcl, "LCL" if auto else "하한", st.BAD),
                                (tgt if tgt is not None else (mu if auto else None), "기준" if tgt is not None else "평균", st.INK2)):
                if v is not None:
                    ax.axhline(v, color=col, lw=1, ls="--", zorder=2)
                    ref_texts.append(ax.text(1.0, v, f" {lab} {st.fmt(v, 2)}", transform=ax.get_yaxis_transform(), ha="left", va="center",
                                             fontsize=7.5, color=col))
            leg.append(("관리 한계 밖", st.BAD, "marker"))
            notes.append(f"관리 한계 {'평균±3σ (자동 계산)' if auto else '입력값'}: 하한 {st.fmt(lcl, 2)}, 상한 {st.fmt(ucl, 2)}. 이탈 {n_out}건(빨간 점)")
            computed.update(ucl=ucl, lcl=lcl, mean=round(mu, 4), sd=round(sd, 4), out=n_out)
            ax.set_position([0.1, 0.14, 0.8, top - 0.16])
        if date_x:
            loc = mdates.AutoDateLocator(minticks=4, maxticks=10)
            ax.xaxis.set_major_locator(loc)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc, formats=["%Y", "%-m월", "%-d일", "%H:%M", "%H:%M", "%S"],
                                                                     offset_formats=["", "%Y", "%Y년 %-m월", "%Y-%m-%d", "%Y-%m-%d", "%Y-%m-%d %H:%M"]))
        else:
            ax.xaxis.set_major_formatter(num_formatter())
        ax.yaxis.set_major_formatter(num_formatter())
        for k, setter in (("x", ax.set_xlim), ("y", ax.set_ylim)):
            lo, hi = o.get(f"{k}_min"), o.get(f"{k}_max")
            if lo is not None or hi is not None:
                setter(left=lo, right=hi) if k == "x" else setter(bottom=lo, top=hi)
        if o.get("x_log"):
            ax.set_xscale("log")
        if o.get("y_log"):
            ax.set_yscale("log")
        if args.get("x_label"):
            ax.set_xlabel(args["x_label"], color=st.MUTED)
        if args.get("y_label"):
            ax.set_ylabel(args["y_label"], color=st.MUTED)
        if legend:
            legend_top(fig, leg, title, sub, o)
        put_title(fig, title, sub, o)
        if len(ref_texts) > 1:
            from .. import declutter
            declutter.stack_vertical(fig, ax, ref_texts)  # 1.4.0: 관리 한계가 가까우면 오른쪽 이름표가 겹쳤다
        png = to_png(fig)
    rows = []
    for s in ser:
        for p in s["points"]:
            x = p["x"].strftime("%Y-%m-%d") if isinstance(p["x"], dt.datetime) else p["x"]
            rows.append([s["name"], p.get("label") or "", x, p["y"], p.get("size")])
    return Result(png, notes, computed, table=(["계열", "이름", args.get("x_label") or "x", args.get("y_label") or "y", "크기"], rows))
