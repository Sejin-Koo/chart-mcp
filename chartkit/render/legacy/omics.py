"""오믹스·바이오마커 차트(matplotlib): 볼케이노 플롯 · 군집 히트맵(덴드로그램).
"""
from __future__ import annotations

import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from scipy.cluster import hierarchy as sch
from scipy.spatial.distance import pdist

from . import _st as st
from ...errors import as_dict, as_list, as_number, need
from ._core import figure, title as put_title, to_bytes, top_margin

TYPES = ["volcano", "cluster_heatmap"]
C = st.CATEGORICAL


def render(chart_type, data, title, sub, options, width=None, height=None):
    need(chart_type in TYPES, f"chart_omics에서 지원하지 않는 chart_type: {chart_type}", hint=f"다음 중 하나: {', '.join(TYPES)}")
    return (_volcano if chart_type == "volcano" else _cluster)(data or {}, title, sub, options or {}, width, height)


def _volcano(data, title, sub, o, w, h):
    genes = as_list(data.get("genes"), "genes")
    ex = [{"name": "TP53", "log2fc": 2.1, "p": 0.0003}, {"name": "EGFR", "log2fc": -1.4, "p": 0.02}]
    need(len(genes) >= 3, "volcano는 genes=[{name, log2fc, p}]가 필요합니다(p는 보정 p값 권장)", example=ex)
    fc_cut = as_number(o.get("fc_cut"), "options.fc_cut") or 1.0
    p_cut = as_number(o.get("p_cut"), "options.p_cut") or 0.05
    top_n = int(as_number(o.get("label_top"), "options.label_top") or 10)
    names, fc, p = [], [], []
    for i, g in enumerate(genes):
        g = as_dict(g, f"genes[{i}]")
        names.append(str(g.get("name", i)))
        fc.append(as_number(g.get("log2fc"), f"genes[{i}].log2fc"))
        pv = as_number(g.get("p"), f"genes[{i}].p")
        need(pv is not None and 0 <= pv <= 1, f"genes[{i}].p는 0~1 사이 p값이어야 합니다(−log10 변환 전 값)")
        p.append(max(pv, 1e-300))
    fc, p = np.array(fc, float), np.array(p, float)
    nl = -np.log10(p)
    up = (fc >= fc_cut) & (p < p_cut)
    dn = (fc <= -fc_cut) & (p < p_cut)
    ns = ~(up | dn)
    with figure(w, h) as fig:
        ax = fig.add_axes([0.08, 0.12, 0.88, top_margin(title, sub) - 0.15])
        ax.scatter(fc[ns], nl[ns], s=10, color=st.GRAY, alpha=0.6, lw=0, label=f"유의하지 않음 ({ns.sum()})")
        ax.scatter(fc[up], nl[up], s=16, color=st.UP, alpha=0.85, lw=0, label=f"증가 ({up.sum()})")
        ax.scatter(fc[dn], nl[dn], s=16, color=st.DOWN, alpha=0.85, lw=0, label=f"감소 ({dn.sum()})")
        ax.axvline(fc_cut, color=st.MUTED, ls="--", lw=0.9); ax.axvline(-fc_cut, color=st.MUTED, ls="--", lw=0.9)
        ax.axhline(-np.log10(p_cut), color=st.MUTED, ls="--", lw=0.9)
        sig = np.where(up | dn)[0]
        order = sig[np.argsort(-(nl[sig] * np.abs(fc[sig])))][:top_n]
        placed: list[tuple[float, float]] = []
        xr, yr = (abs(fc).max() or 1) * 2, (nl.max() or 1)
        for k in order:  # 가까운 이름끼리 겹치지 않게 아래로 비켜 놓는다
            dy = 3
            while any(abs(px - fc[k]) / xr < 0.06 and abs(py - (nl[k] + dy / 30)) / yr < 0.035 for px, py in placed) and dy > -60:
                dy -= 11
            placed.append((fc[k], nl[k] + dy / 30))
            ax.annotate(names[k], (fc[k], nl[k]), xytext=(5 if fc[k] >= 0 else -5, dy), textcoords="offset points", fontsize=8.5, color=st.INK,
                        ha="left" if fc[k] >= 0 else "right", arrowprops={"arrowstyle": "-", "color": st.MUTED, "lw": 0.5} if dy != 3 else None)
        ax.set_xlabel("log2 배수 변화(Fold change)")
        ax.set_ylabel(f"−log10({o.get('p_label', '보정 p값')})")
        lim = max(abs(fc).max() * 1.08, fc_cut * 1.5)
        ax.set_xlim(-lim, lim)
        ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, markerscale=1.5)
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, [f"기준: |log2FC| ≥ {fc_cut:g}, p < {p_cut:g}. 증가 {up.sum()}개, 감소 {dn.sum()}개. 상위 {len(order)}개 이름 표시"], {"up": int(up.sum()), "down": int(dn.sum())}


def _cluster(data, title, sub, o, w, h):
    rows = [str(r) for r in as_list(data.get("rows"), "rows")]
    cols = [str(c) for c in as_list(data.get("columns"), "columns")]
    vals = as_list(data.get("values"), "values")
    ex = {"rows": ["GeneA", "GeneB", "GeneC"], "columns": ["S1", "S2", "S3", "S4"], "values": [[1, 2, 1.5, 3], [5, 4, 6, 5], [2, 2, 1, 1]]}
    need(rows and cols and len(vals) == len(rows), "cluster_heatmap은 rows, columns, values(행×열)가 필요합니다", example=ex)
    m = np.array([[as_number(v, f"values[{i}]") for v in as_list(r, f"values[{i}]")] for i, r in enumerate(vals)], float)
    need(m.shape == (len(rows), len(cols)), f"values 모양 {m.shape}가 rows×columns ({len(rows)}×{len(cols)})와 다릅니다", example=ex)
    need(not np.isnan(m).any(), "군집 히트맵은 빈 값을 허용하지 않습니다. 결측을 대체하거나 해당 행을 제외하세요")
    scale = o.get("scale", "row")
    z = m.copy()
    if scale == "row":
        sd = z.std(axis=1, ddof=1, keepdims=True)
        z = (z - z.mean(axis=1, keepdims=True)) / np.where(sd == 0, 1, sd)
    method, metric = o.get("method", "average"), o.get("metric", "correlation" if len(cols) >= 3 else "euclidean")
    def link(a):
        if len(a) < 2:
            return None
        d = pdist(a, metric=metric)
        d = np.nan_to_num(d, nan=0.0)
        return sch.linkage(d, method=method)
    lr = link(z) if o.get("cluster_rows", True) else None
    lc = link(z.T) if o.get("cluster_cols", True) else None
    with figure(w, h or max(480, 140 + 16 * len(rows))) as fig:
        tm = top_margin(title, sub)
        dh = 0.12 if lc is not None else 0
        ax_h = fig.add_axes([0.2, 0.08, 0.62, tm - 0.1 - dh])
        ri = list(range(len(rows)))
        ci = list(range(len(cols)))
        if lr is not None:
            axr = fig.add_axes([0.04, 0.08, 0.15, tm - 0.1 - dh])
            dr = sch.dendrogram(lr, orientation="left", no_labels=True, ax=axr, color_threshold=0, above_threshold_color=st.INK2)
            ri = dr["leaves"][::-1]
            axr.axis("off")
        if lc is not None:
            axc = fig.add_axes([0.2, tm - dh + 0.005, 0.62, dh - 0.01])
            dc = sch.dendrogram(lc, no_labels=True, ax=axc, color_threshold=0, above_threshold_color=st.INK2)
            ci = dc["leaves"]
            axc.axis("off")
        zz = z[np.ix_(ri, ci)]
        if scale == "row":
            lim = np.nanmax(np.abs(zz)) or 1
            cmap = LinearSegmentedColormap.from_list("div", [st.DOWN, "#f0efec", st.UP])
            im = ax_h.imshow(zz, aspect="auto", cmap=cmap, vmin=-lim, vmax=lim, interpolation="nearest")
        else:
            cmap = LinearSegmentedColormap.from_list("seq", st.SEQUENTIAL)
            im = ax_h.imshow(zz, aspect="auto", cmap=cmap, interpolation="nearest")
        ax_h.set_yticks(range(len(ri)), [rows[i] for i in ri] if len(rows) <= 60 else [""] * len(ri), fontsize=8)
        ax_h.yaxis.tick_right()
        ax_h.set_xticks(range(len(ci)), [cols[i] for i in ci], rotation=90 if max(len(c) for c in cols) > 3 else 0, fontsize=8.5)
        ax_h.grid(False)
        for sp in ax_h.spines.values():
            sp.set_visible(False)
        cax = fig.add_axes([0.91, 0.08, 0.015, 0.25])
        cb = fig.colorbar(im, cax=cax)
        cb.set_label("행 Z점수" if scale == "row" else o.get("value_label", "값"), fontsize=9)
        cb.outline.set_visible(False)
        put_title(fig, ax_h, title, sub)
        res = to_bytes(fig)
    return res, [f"군집: {method} 연결, 거리 {metric}. 색: {'행별 Z점수(빨강 높음·파랑 낮음)' if scale == 'row' else '원값'}"], {"row_order": [rows[i] for i in ri], "col_order": [cols[i] for i in ci]}
