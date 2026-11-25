"""값의 분포 — 상자 수염·누적분포(ECDF)·평균+오차막대(점·막대). 히스토그램도 받는다."""
from __future__ import annotations

import math

import numpy as np

from .. import style as st
from ..core import Result, axis_unit, figure, legend_top, num_formatter, put_title, style_axes, to_png, top_for
from ..errors import as_dict, as_list, as_number, need

EX = [{"name": "위약", "values": [5.1, 6.3, 4.8]}, {"name": "투여", "values": [8.4, 9.1, 7.7]}]


def _groups(args, allow_summary=False):
    gs = as_list(args.get("groups"), "groups")
    need(gs, "groups=[{name, values}]가 필요합니다", example=EX)
    out = []
    for i, g in enumerate(gs):
        g = as_dict(g, f"groups[{i}]")
        name = str(g.get("name") or f"군{i + 1}")
        if allow_summary and g.get("mean") is not None:
            out.append({"name": name, "mean": as_number(g["mean"], f"groups[{i}].mean"), "error": as_number(g.get("error"), f"groups[{i}].error") or 0,
                        "lower": as_number(g.get("lower"), "lower"), "upper": as_number(g.get("upper"), "upper"), "n": g.get("n"), "values": None})
            continue
        v = np.array([x for x in (as_number(y, f"groups[{i}].values") for y in as_list(g.get("values"), f"groups[{i}].values")) if x is not None], float)
        need(len(v) >= 2, f"groups[{i}]('{name}')의 값이 2개 이상 필요합니다", example=EX)
        out.append({"name": name, "values": v, "color": g.get("color")})
    return out


def _err(v, kind):
    n = len(v)
    sd = float(np.std(v, ddof=1))
    if kind == "sd":
        return sd
    se = sd / math.sqrt(n)
    if kind == "se":
        return se
    from scipy import stats
    return float(stats.t.ppf(0.975, n - 1) * se)


def draw(ct: str, args: dict, o: dict) -> Result:
    title, sub, unit = args.get("title"), args.get("subtitle"), args.get("unit")
    gs = _groups(args, allow_summary=ct in ("errorbar", "errorbar_bar"))
    cols = [st.color(g.get("color"), c) for g, c in zip(gs, st.palette(len(gs), wide=len(gs) > 3))]
    notes, computed, rows = [], {}, []
    n = len(gs)
    legend = ct in ("ecdf", "histogram") and n > 1
    with figure(3.3, o) as fig:
        top = top_for(fig, title, sub, o, legend)
        ax = fig.add_axes([0.1, 0.13, 0.86, top - 0.15])
        style_axes(ax, grid="y" if ct != "ecdf" else "both")
        if ct == "boxplot":
            bp = ax.boxplot([g["values"] for g in gs], widths=0.5, patch_artist=True, showfliers=True,
                            medianprops=dict(color="white", lw=2), whiskerprops=dict(color=st.INK2), capprops=dict(color=st.INK2),
                            flierprops=dict(marker="o", markersize=4, markerfacecolor=st.ORANGE, markeredgecolor="none"))
            for b, c in zip(bp["boxes"], cols):
                b.set_facecolor(c)
                b.set_edgecolor(c)
            if o.get("show_points"):
                rng = np.random.default_rng(0)
                for i, g in enumerate(gs):
                    ax.scatter(i + 1 + rng.uniform(-0.12, 0.12, len(g["values"])), g["values"], s=8, color=st.INK2, alpha=0.5, zorder=3)
            side = []
            for i, g in enumerate(gs):
                q1, med, q3 = np.percentile(g["values"], [25, 50, 75])
                side.append((ax.text(i + 1.3, med, st.fmt(med), va="center", ha="left", fontsize=st.LABEL_SIZE, fontweight="bold", color=cols[i]),
                             i + 1.75))
                rows.append([g["name"], len(g["values"]), float(np.min(g["values"])), float(q1), float(med), float(q3), float(np.max(g["values"])), float(np.mean(g["values"]))])
            ax.set_xticks(range(1, n + 1), [g["name"] for g in gs])
            from .. import declutter
            declutter.fit_width(fig, ax, side, what="중앙값")  # 1.4.0 — 그룹이 많으면 옆 상자를 덮었다
            notes.append("상자: 사분위 범위(25~75%), 흰 선: 중앙값, 수염: 1.5×IQR 안의 최솟값·최댓값, 주황 점: 이상값")
            head = ["군", "n", "최솟값", "Q1", "중앙값", "Q3", "최댓값", "평균"]
        elif ct == "histogram":
            bins = int(o.get("bins") or 10)
            allv = np.concatenate([g["values"] for g in gs])
            edges = np.histogram_bin_edges(allv, bins=bins)
            for g, c in zip(gs, cols):
                ax.hist(g["values"], bins=edges, color=c, alpha=0.75 if n > 1 else 1, edgecolor="white", density=bool(o.get("density")))
            head = ["구간 시작", "구간 끝"] + [g["name"] for g in gs]
            counts = [np.histogram(g["values"], bins=edges)[0] for g in gs]
            rows = [[float(edges[k]), float(edges[k + 1])] + [int(cn[k]) for cn in counts] for k in range(len(edges) - 1)]
        elif ct == "ecdf":
            for g, c in zip(gs, cols):
                v = np.sort(g["values"])
                y = np.arange(1, len(v) + 1) / len(v) * 100
                ax.step(np.concatenate([[v[0]], v]), np.concatenate([[0], y]), where="post", color=c, lw=2)
                med = float(np.median(v))
                ax.plot([med], [50], "o", color=c, markersize=4)
                rows += [[g["name"], float(a), float(b)] for a, b in zip(v, y)]
            ax.axhline(50, color=st.MUTED, lw=0.8, ls=":")
            ax.set_ylim(0, 102)
            ax.set_ylabel("누적 비율(%)", color=st.MUTED)
            if unit:
                ax.set_xlabel(f"({unit})", color=st.MUTED)
            head = ["군", "값", "누적 비율(%)"]
            notes.append("누적분포: 가로축 값 이하인 관측치의 비율. 점선은 50%(중앙값) 위치")
        else:  # errorbar · errorbar_bar
            kind = str(o.get("error") or "ci95").lower()
            lab = {"sd": "±SD", "se": "±SE", "ci95": "95% CI"}.get(kind, "95% CI")
            means, lo, hi = [], [], []
            for g in gs:
                if g.get("values") is None:
                    m = g["mean"]
                    l_ = g["lower"] if g.get("lower") is not None else m - g["error"]
                    u_ = g["upper"] if g.get("upper") is not None else m + g["error"]
                    nn = g.get("n")
                else:
                    m = float(np.mean(g["values"]))
                    e = _err(g["values"], kind)
                    l_, u_, nn = m - e, m + e, len(g["values"])
                means.append(m)
                lo.append(l_)
                hi.append(u_)
                rows.append([g["name"], nn, m, l_, u_])
            x = np.arange(n)
            yerr = [np.array(means) - np.array(lo), np.array(hi) - np.array(means)]
            if ct == "errorbar_bar":
                ax.bar(x, means, color=cols, width=0.55, zorder=2)
                ax.errorbar(x, means, yerr=yerr, fmt="none", ecolor=st.INK, elinewidth=1.3, capsize=6, zorder=3)
                side = [(ax.text(i + 0.3, m, st.fmt(m), ha="left", va="bottom", fontsize=st.LABEL_SIZE, fontweight="bold", color=cols[i]), i + 0.72)
                        for i, m in enumerate(means)]
                ax.set_ylim(0, max(hi) * 1.15)
                from .. import declutter
                declutter.fit_width(fig, ax, side, what="평균")
            else:
                side = []
                for i in range(n):
                    ax.errorbar([i], [means[i]], yerr=[[yerr[0][i]], [yerr[1][i]]], fmt="o", color=cols[i], ecolor=cols[i], elinewidth=1.8,
                                capsize=7, markersize=7, zorder=3)
                    side.append((ax.text(i + 0.12, means[i], st.fmt(means[i]), ha="left", va="center", fontsize=st.LABEL_SIZE, fontweight="bold",
                                         color=cols[i]), i + 0.85))
                span = max(hi) - min(lo)
                ax.set_ylim(min(lo) - span * 0.25, max(hi) + span * 0.2)
                ax.set_xlim(-0.5, n - 0.3)
                from .. import declutter
                declutter.fit_width(fig, ax, side, what="평균")
            ax.set_xticks(x, [g["name"] for g in gs])
            if all(g.get("values") is None for g in gs) and not o.get("error"):
                lab = "입력한 오차(±error 또는 lower~upper)"
            notes.append(f"점·막대: 평균, 오차막대: {lab}" + (" (원자료에서 계산)" if any(g.get('values') is not None for g in gs) else ""))
            head = ["군", "n", "평균", "하한", "상한"]
            computed["error"] = kind
        if ct != "ecdf":
            ax.yaxis.set_major_formatter(num_formatter())
            axis_unit(ax, unit)
        else:
            ax.xaxis.set_major_formatter(num_formatter())
        if legend:
            legend_top(fig, [(g["name"], c, "line" if ct == "ecdf" else "patch") for g, c in zip(gs, cols)], title, sub, o)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, notes, computed, table=(head, rows))
