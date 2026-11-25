"""재무·성과 — 불릿·KPI 카드·게이지·풋볼필드·캔들스틱·고가-저가-종가·주가+거래량. 국내 관례로 상승 빨강·하락 파랑."""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle, Wedge

from .. import style as st
from ..core import Result, axis_unit, figure, legend_top, num_formatter, put_title, style_axes, to_png, top_for
from ..errors import as_dict, as_list, as_number, need

EX_BARS = [{"date": "2026-08-01", "open": 50000, "high": 50500, "low": 49600, "close": 50100, "volume": 150000}]


def _bars(args):
    bs = as_list(args.get("bars"), "bars")
    need(len(bs) >= 2, "bars=[{date, open, high, low, close, volume}]가 2개 이상 필요합니다", example=EX_BARS)
    out = []
    for i, b in enumerate(bs):
        b = as_dict(b, f"bars[{i}]")
        out.append({"d": dt.date.fromisoformat(str(b.get("date"))[:10]), **{k: as_number(b.get(k), f"bars[{i}].{k}") for k in ("open", "high", "low", "close", "volume")}})
    out.sort(key=lambda r: r["d"])
    return out


def _price(ax, bars, ct, o):
    x = np.arange(len(bars))
    for i, b in enumerate(bars):
        up = (b["close"] or 0) >= (b["open"] if b["open"] is not None else (bars[i - 1]["close"] if i else b["close"]))
        c = st.UP if up else st.DOWN
        if b["high"] is not None and b["low"] is not None:
            ax.vlines(i, b["low"], b["high"], color=c, lw=0.9, zorder=2)
        if ct == "hlc":
            ax.hlines(b["close"], i, i + 0.32, color=c, lw=1.4, zorder=3)
        elif b["open"] is not None:
            lo, hi = sorted((b["open"], b["close"]))
            ax.add_patch(Rectangle((i - 0.32, lo), 0.64, max(hi - lo, (hi or 1) * 0.0008), facecolor=c, edgecolor=c, zorder=3))
    closes = np.array([b["close"] for b in bars], float)
    leg = [("상승", st.UP, "patch"), ("하락", st.DOWN, "patch")]
    for k, w in enumerate(as_list(o.get("ma"), "options.ma") or []):
        w = int(as_number(w, "options.ma"))
        if 1 < w < len(bars):
            ma = np.convolve(closes, np.ones(w) / w, mode="valid")
            c = [st.ORANGE, st.TEAL, st.PURPLE][k % 3]
            ax.plot(x[w - 1:], ma, color=c, lw=1.3, zorder=4)
            leg.append((f"{w}일 이동평균", c, "line"))
    ax.set_xlim(-0.8, len(bars) + 2.2)
    lo = min(b["low"] if b["low"] is not None else b["close"] for b in bars)
    hi = max(b["high"] if b["high"] is not None else b["close"] for b in bars)
    pad = (hi - lo) * 0.08
    ax.set_ylim(lo - pad, hi + pad)
    last = bars[-1]["close"]
    ax.annotate(st.fmt(last), (len(bars) - 1, last), xytext=(6, 0), textcoords="offset points", va="center", fontsize=st.LABEL_SIZE,
                fontweight="bold", color=st.UP if last >= bars[0]["close"] else st.DOWN)
    return leg


def _date_ticks(ax, bars):
    n = len(bars)
    step = max(1, n // 8)
    idx = list(range(0, n, step))
    ax.set_xticks(idx, [bars[i]["d"].strftime("%-m.%d") for i in idx])


def _market(ct, args, o):
    title, sub, unit = args.get("title"), args.get("subtitle"), args.get("unit")
    bars = _bars(args)
    with figure(3.6, o) as fig:
        top = top_for(fig, title, sub, o, True)
        if ct == "price_volume":
            ax = fig.add_axes([0.1, 0.34, 0.86, top - 0.36])
            axv = fig.add_axes([0.1, 0.1, 0.86, 0.2], sharex=ax)
        else:
            ax = fig.add_axes([0.1, 0.12, 0.86, top - 0.14])
            axv = None
        style_axes(ax, grid="y")
        leg = _price(ax, bars, ct, o)
        ax.yaxis.set_major_formatter(num_formatter())
        axis_unit(ax, unit)
        if axv is not None:
            style_axes(axv, grid="y")
            for i, b in enumerate(bars):
                up = (b["close"] or 0) >= (b["open"] or 0)
                axv.bar(i, b["volume"] or 0, color=st.UP if up else st.DOWN, alpha=0.55, width=0.7)
            axv.yaxis.set_major_formatter(num_formatter())
            axv.set_ylabel("거래량", color=st.MUTED, fontsize=7.5)
            ax.tick_params(labelbottom=False)
            _date_ticks(axv, bars)
        else:
            _date_ticks(ax, bars)
        legend_top(fig, leg, title, sub, o)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    first, last = bars[0]["close"], bars[-1]["close"]
    chg = (last / first - 1) * 100 if first else None
    notes = [f"기간 수익률 {chg:+.1f}% ({st.fmt(first)} → {st.fmt(last)})"] if chg is not None else []
    return Result(png, notes, {"return_pct": round(chg, 2) if chg is not None else None},
                  table=(["일자", "시가", "고가", "저가", "종가", "거래량"], [[b["d"].isoformat(), b["open"], b["high"], b["low"], b["close"], b["volume"]] for b in bars]))


def _bullet(args, o):
    title, sub = args.get("title"), args.get("subtitle")
    items = as_list(args.get("items"), "items")
    need(items, "items=[{name, actual, target, ranges:[미흡,보통,양호]}]가 필요합니다",
         example=[{"name": "매출", "actual": 82, "target": 100, "ranges": [60, 90, 120]}])
    n = len(items)
    rows = []
    with figure(max(1.6, 0.6 + 0.55 * n), o) as fig:
        top = top_for(fig, title, sub, o, True)
        for i, it in enumerate(items):
            it = as_dict(it, f"items[{i}]")
            a, t = as_number(it.get("actual"), f"items[{i}].actual"), as_number(it.get("target"), f"items[{i}].target")
            rg = [as_number(v, "ranges") for v in as_list(it.get("ranges"), f"items[{i}].ranges")] or [t * 0.6, t * 0.9, t * 1.2]
            h = (top - 0.06) / n
            ax = fig.add_axes([0.18, top - (i + 1) * h + h * 0.22, 0.74, h * 0.56])
            mx = max(rg + [a, t]) * 1.02
            prev = 0
            for k, r in enumerate(rg):
                ax.barh(0, r - prev, left=prev, height=1, color=["#D9D9D9", "#E6E6E6", "#F2F2F2"][min(k, 2)], zorder=1)
                prev = r
            ax.barh(0, a, height=0.36, color=st.NAVY, zorder=2)
            ax.vlines(t, -0.38, 0.38, color=st.ORANGE, lw=2.4, zorder=3)
            ax.text(a, 0, f" {st.fmt(a)}", va="center", ha="left", fontsize=st.LABEL_SIZE, fontweight="bold", color=st.NAVY, zorder=4)
            ax.set_xlim(0, mx)
            ax.set_ylim(-0.5, 0.5)
            ax.set_yticks([])
            for s_ in ax.spines.values():
                s_.set_visible(False)
            ax.tick_params(length=0, labelsize=7)
            ax.xaxis.set_major_formatter(num_formatter())
            name = str(it.get("name", ""))
            fig.text(0.17, top - (i + 1) * h + h * 0.5, f"{name}\n달성 {a / t * 100:.0f}%" if t else name, ha="right", va="center", fontsize=st.FONT_SIZE,
                     linespacing=1.3)
            rows.append([name, a, t] + rg)
        legend_top(fig, [("실적", st.NAVY, "patch"), ("목표", st.ORANGE, "line"), ("구간(미흡·보통·양호)", "#E0E0E0", "patch")], title, sub, o)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, table=(["항목", "실적", "목표", "구간1", "구간2", "구간3"], rows))


def _gauge(args, o):
    title, sub, unit = args.get("title"), args.get("subtitle"), args.get("unit") or ""
    v = as_number(args.get("value"), "value")
    need(v is not None, "value(게이지 값)가 필요합니다", example={"value": 72, "unit": "%"})
    lo = float(o.get("min") or 0)
    hi = float(o.get("max") or (100 if unit == "%" else max(v * 1.25, 1)))
    th = [as_number(x, "thresholds") for x in as_list(o.get("thresholds"), "options.thresholds")]
    with figure(2.6, o) as fig:
        top = top_for(fig, title, sub, o, False)
        ax = fig.add_axes([0.25, 0.02, 0.5, top - 0.04])
        ax.set_aspect("equal")
        ax.axis("off")
        cuts = [lo] + [t for t in th if lo < t < hi] + [hi]
        cols = [st.BAD, st.WARN, st.GOOD] if len(cuts) == 4 else ([st.WARN, st.GOOD] if len(cuts) == 3 else [st.LIGHT])
        for (a, b), c in zip(zip(cuts[:-1], cuts[1:]), cols):
            ax.add_patch(Wedge((0, 0), 1, 180 - (b - lo) / (hi - lo) * 180, 180 - (a - lo) / (hi - lo) * 180, width=0.12, facecolor=c, alpha=0.35, edgecolor="none"))
        frac = max(0, min(1, (v - lo) / (hi - lo)))
        ax.add_patch(Wedge((0, 0), 0.86, 180 - frac * 180, 180, width=0.22, facecolor=st.NAVY, edgecolor="none"))
        ang = math.radians(180 - frac * 180)
        ax.plot([0, 0.7 * math.cos(ang)], [0, 0.7 * math.sin(ang)], color=st.INK, lw=2)
        ax.scatter([0], [0], s=40, color=st.INK, zorder=3)
        ax.text(0, -0.22, f"{st.fmt(v)}{unit}", ha="center", va="center", fontsize=16, fontweight="bold", color=st.NAVY)
        if o.get("label"):
            ax.text(0, -0.42, str(o["label"]), ha="center", va="center", fontsize=8.5, color=st.MUTED)
        for t in cuts:
            a = math.radians(180 - (t - lo) / (hi - lo) * 180)
            ax.text(1.12 * math.cos(a), 1.12 * math.sin(a), st.fmt(t), ha="center", va="center", fontsize=7, color=st.MUTED)
        ax.set_xlim(-1.25, 1.25)
        ax.set_ylim(-0.55, 1.2)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["바깥 띠: 구간(빨강 미흡·주황 보통·청록 양호)"] if th else [], table=(["항목", "값", "최소", "최대"], [[o.get("label") or "값", v, lo, hi]]))


def _football(args, o):
    title, sub, unit = args.get("title"), args.get("subtitle"), args.get("unit") or ""
    rs = as_list(args.get("ranges"), "ranges")
    need(rs, "ranges=[{name, low, high}]가 필요합니다", example=[{"name": "DCF", "low": 41000, "high": 58000}])
    rows = []
    for i, r in enumerate(rs):
        r = as_dict(r, f"ranges[{i}]")
        lo, hi = as_number(r.get("low"), f"ranges[{i}].low"), as_number(r.get("high"), f"ranges[{i}].high")
        rows.append([str(r.get("name", "")), lo, hi, as_number(r.get("mid"), "mid") if r.get("mid") is not None else (lo + hi) / 2, st.color(r.get("color"), st.NAVY)])
    cur = as_dict(o.get("current"), "options.current") if o.get("current") else None
    n = len(rows)
    mx = max(r[2] for r in rows + ([[0, 0, as_number(cur.get("value"), "current")]] if cur else []))
    mn = min(r[1] for r in rows)
    with figure(max(1.8, 0.8 + 0.42 * n), o) as fig:
        top = top_for(fig, title, sub, o, False)
        ax = fig.add_axes([0.2, 0.14, 0.74, top - 0.18])
        style_axes(ax, grid="x")
        for i, (name, lo, hi, mid, c) in enumerate(rows):
            w = max(hi - lo, mx * 0.006)
            ax.barh(i, w, left=lo, height=0.55, color=c, zorder=2)
            ax.text(lo, i, st.fmt(lo) + " ", ha="right", va="center", fontsize=st.LABEL_SIZE, fontweight="bold", color=c)
            ax.text(hi, i, " " + st.fmt(hi), ha="left", va="center", fontsize=st.LABEL_SIZE, fontweight="bold", color=c)
            t = ax.text(lo + w / 2, i, st.fmt(mid), ha="center", va="center", fontsize=7.4, fontweight="bold", color="white", zorder=3)
            r = fig.canvas.get_renderer()
            bb = ax.transData.inverted().transform(t.get_window_extent(r))
            if bb[1][0] - bb[0][0] > w * 0.95:
                t.remove()
        if cur:
            cv = as_number(cur.get("value"), "options.current.value")
            ax.axvline(cv, color=st.ORANGE, lw=1.6, ls="--", zorder=4)
            ax.text(cv, 1.0, f" {cur.get('label') or '현재'} {st.fmt(cv)}", transform=ax.get_xaxis_transform(), ha="left", va="bottom",
                    fontsize=7.8, color=st.ORANGE, fontweight="bold")
        ax.set_yticks(range(n), [r[0] for r in rows])
        ax.invert_yaxis()
        span = mx - mn
        ax.set_xlim(max(0, mn - span * 0.25), mx + span * 0.15)
        ax.xaxis.set_major_formatter(num_formatter())
        axis_unit(ax, unit, "x")
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["막대 왼쪽 = 하단, 막대 안 흰 글자 = 중앙값(짧으면 생략), 오른쪽 = 상단"],
                  table=(["방법", "하단", "상단", "중앙"], [r[:4] for r in rows]))


def _kpi(args, o):
    title, sub = args.get("title"), args.get("subtitle")
    ks = as_list(args.get("kpis"), "kpis")
    need(ks, "kpis=[{name, value, unit, delta, delta_unit, spark}]가 필요합니다",
         example=[{"name": "매출", "value": 1284, "unit": "억원", "delta": 8.2, "delta_unit": "%", "spark": [980, 1040, 1284]}])
    need(len(ks) <= 8, "KPI 카드는 8개까지입니다")
    n = len(ks)
    ncol = min(n, 4)
    nrow = math.ceil(n / ncol)
    rows = []
    with figure(1.25 * nrow + 0.2, o) as fig:
        top = top_for(fig, title, sub, o, False)
        cw, ch = 0.98 / ncol, (top - 0.02) / nrow
        for i, k in enumerate(ks):
            k = as_dict(k, f"kpis[{i}]")
            r, c = divmod(i, ncol)
            x0, y0 = 0.01 + c * cw, top - (r + 1) * ch
            ax = fig.add_axes([x0 + 0.006, y0 + 0.02, cw - 0.012, ch - 0.03])
            ax.axis("off")
            ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.04", facecolor="#F5F7FB", edgecolor="#DCE2EC",
                                        transform=ax.transAxes))
            v = as_number(k.get("value"), f"kpis[{i}].value")
            d = as_number(k.get("delta"), f"kpis[{i}].delta")
            better = k.get("higher_is_better", True) not in (False, "false")
            good = d is None or (d >= 0) == better
            ax.text(0.07, 0.83, str(k.get("name", "")), transform=ax.transAxes, fontsize=8.5, color=st.INK2, va="center")
            vt = ax.text(0.07, 0.52, f"{st.fmt(v)}", transform=ax.transAxes, fontsize=17, fontweight="bold", color=st.INK, va="center")
            # 1.4.0: 단위 자리를 글자 수로 어림해 값과 단위 사이가 들쭉날쭉했고, 큰 수는 카드 밖으로 나갔다 → 값 글자 폭을 재서 바로 옆에 붙이고 카드에 맞춰 줄임
            ut = ax.annotate(str(k.get("unit") or ""), xy=(1, 0), xycoords=vt, xytext=(3, 1), textcoords="offset points", fontsize=8,
                             color=st.MUTED, va="bottom", ha="left")
            fig.canvas.draw()
            right = ax.bbox.x0 + ax.bbox.width * 0.95
            while vt.get_fontsize() > 10 and max(vt.get_window_extent().x1, ut.get_window_extent().x1 if ut.get_text() else 0) > right:
                vt.set_fontsize(vt.get_fontsize() - 1)
                fig.canvas.draw()
            if d is not None:
                ax.text(0.07, 0.18, f"{'▲' if d >= 0 else '▼'} {st.fmt(abs(d), 0 if float(d).is_integer() else 1)}{k.get('delta_unit') or ''}", transform=ax.transAxes, fontsize=8.5,
                        fontweight="bold", color=st.GOOD if good else st.BAD, va="center")
            sp = [as_number(x, "spark") for x in as_list(k.get("spark"), f"kpis[{i}].spark")]
            if len(sp) >= 2:
                sa = fig.add_axes([x0 + cw * 0.56, y0 + ch * 0.14, cw * 0.38, ch * 0.34])
                sa.axis("off")
                sa.plot(range(len(sp)), sp, color=st.NAVY, lw=1.4)
                sa.scatter([len(sp) - 1], [sp[-1]], s=10, color=st.NAVY)
            rows.append([k.get("name"), v, k.get("unit"), d, k.get("delta_unit")])
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["증감 색: 좋아진 방향 청록, 나빠진 방향 빨강(higher_is_better=false면 감소가 좋음)"],
                  table=(["지표", "값", "단위", "증감", "증감 단위"], rows))


def _progress(args, o):
    title, sub = args.get("title"), args.get("subtitle")
    items = as_list(args.get("items"), "items")
    need(items, "items=[{name, value, target}]가 필요합니다", example=[{"name": "A과제", "value": 60, "target": 100}])
    rows = []
    n = len(items)
    with figure(max(1.6, 0.6 + 0.4 * n), o) as fig:
        top = top_for(fig, title, sub, o, False)
        ax = fig.add_axes([0.2, 0.06, 0.7, top - 0.08])
        ax.axis("off")
        for i, it in enumerate(items):
            it = as_dict(it, f"items[{i}]")
            v, t = as_number(it.get("value"), "value"), as_number(it.get("target"), "target") or 100
            p = max(0, min(1, v / t))
            ax.barh(i, 1, color=st.LIGHT, height=0.5)
            c = st.GOOD if p >= 1 else st.NAVY
            ax.barh(i, p, color=c, height=0.5)
            ax.text(-0.02, i, str(it.get("name", "")), ha="right", va="center", fontsize=st.FONT_SIZE)
            ax.text(1.02, i, f"{p * 100:.0f}%", ha="left", va="center", fontsize=st.LABEL_SIZE, fontweight="bold", color=c)
            rows.append([it.get("name"), v, t, round(p * 100, 1)])
        ax.set_xlim(0, 1.12)
        ax.set_ylim(n - 0.5, -0.5)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, table=(["항목", "값", "목표", "진척(%)"], rows))


def draw(ct: str, args: dict, o: dict) -> Result:
    if ct in ("candlestick", "hlc", "price_volume"):
        return _market(ct, args, o)
    if ct == "bullet":
        return _bullet(args, o)
    if ct == "gauge":
        return _gauge(args, o)
    if ct == "football_field":
        return _football(args, o)
    if ct == "kpi_tiles":
        return _kpi(args, o)
    if ct == "progress":
        return _progress(args, o)
    raise ValueError(ct)
