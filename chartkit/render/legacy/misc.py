"""기타 특수 차트(matplotlib): 바이올린·스트립(점 분포)·워드클라우드·벤 다이어그램·와플·3D 표면·3D 산점도·등고선.
"""
from __future__ import annotations

import numpy as np
from matplotlib import patches
from matplotlib.colors import LinearSegmentedColormap

from . import _st as st
from ...errors import as_dict, as_list, as_number, need
from . import _core as core
from ._core import figure, num_fmt, title as put_title, to_bytes, top_margin

TYPES = ["violin", "strip", "wordcloud", "venn", "waffle", "surface_3d", "scatter_3d", "contour"]
C = st.CATEGORICAL
SEQ_CMAP = LinearSegmentedColormap.from_list("seq", st.SEQUENTIAL)


def render(chart_type, data, title, sub, options, width=None, height=None):
    need(chart_type in TYPES, f"chart_misc에서 지원하지 않는 chart_type: {chart_type}", hint=f"다음 중 하나: {', '.join(TYPES)}")
    return globals()[f"_{chart_type}"](data or {}, title, sub, options or {}, width, height)


def _groups(data):
    ex = [{"name": "위약", "values": [5.1, 6.3, 4.8]}, {"name": "투여", "values": [8.4, 9.1, 7.7]}]
    gs = as_list(data.get("groups"), "groups")
    need(gs, "groups=[{name, values}]가 필요합니다", example=ex)
    out = []
    for i, g in enumerate(gs):
        g = as_dict(g, f"groups[{i}]")
        v = np.array([x for x in (as_number(y, f"groups[{i}].values") for y in as_list(g.get("values"), f"groups[{i}].values")) if x is not None], float)
        need(len(v) >= 2, f"groups[{i}]의 값이 2개 이상 필요합니다", example=ex)
        out.append((str(g.get("name", f"군{i + 1}")), v))
    return out


def _violin(data, title, sub, o, w, h):
    gs = _groups(data)
    with figure(w, h) as fig:
        ax = fig.add_axes([0.08, 0.1, 0.9, top_margin(title, sub) - 0.13])
        parts = ax.violinplot([v for _, v in gs], showextrema=False, widths=0.75)
        for i, b in enumerate(parts["bodies"]):
            b.set_facecolor(C[i % 8]); b.set_alpha(0.35); b.set_edgecolor(C[i % 8])
        for i, (_, v) in enumerate(gs):
            q1, q2, q3 = np.percentile(v, [25, 50, 75])
            ax.vlines(i + 1, q1, q3, color=st.INK, lw=5)
            ax.scatter([i + 1], [q2], color="white", s=22, zorder=3, edgecolor=st.INK)
        ax.set_xticks(range(1, len(gs) + 1), [n for n, _ in gs])
        ax.set_ylabel(o.get("y_label", ""))
        ax.grid(axis="x", visible=False)
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, ["바이올린: 커널 밀도 추정 분포. 굵은 선: 사분위 범위, 흰 점: 중앙값"], {}


def _strip(data, title, sub, o, w, h):
    gs = _groups(data)
    rng = np.random.default_rng(0)
    with figure(w, h) as fig:
        ax = fig.add_axes([0.08, 0.1, 0.9, top_margin(title, sub) - 0.13])
        for i, (_, v) in enumerate(gs):
            ax.scatter(i + rng.uniform(-0.18, 0.18, len(v)), v, s=22, color=C[i % 8], alpha=0.7, lw=0)
            m = v.mean()
            ax.hlines(m, i - 0.28, i + 0.28, color=st.INK, lw=2)
            if o.get("show_mean_label", True):
                ax.text(i + 0.31, m, f"{m:.3g}", va="center", fontsize=9.5, color=st.INK)
        ax.set_xticks(range(len(gs)), [f"{n}\n(n={len(v)})" for n, v in gs])
        ax.set_ylabel(o.get("y_label", ""))
        ax.grid(axis="x", visible=False)
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, ["점: 개별 관측값(가로 위치는 겹침 방지용 무작위 이동), 가로선: 평균"], {}


def _wordcloud(data, title, sub, o, w, h):
    from wordcloud import WordCloud
    words = as_list(data.get("words"), "words")
    need(words, "wordcloud는 words=[{text, weight}]가 필요합니다", example=[{"text": "부작용", "weight": 42}, {"text": "복용편의", "weight": 30}])
    freq = {}
    for i, x in enumerate(words):
        x = as_dict(x, f"words[{i}]")
        wv = as_number(x.get("weight"), f"words[{i}].weight")
        if wv and wv > 0:
            freq[str(x.get("text"))] = wv
    need(freq, "weight가 0보다 큰 단어가 없습니다")
    W, H = (w or 960), (h or 560)
    with figure(W, H) as fig:
        tm = top_margin(title, sub)
        palette = [st.SEQUENTIAL[12], st.SEQUENTIAL[9], st.SEQUENTIAL[7], C[1], st.SEQUENTIAL[5]]
        wc = WordCloud(font_path=core.FONT_PATH, width=int(W * 2), height=int(H * tm * 2), background_color="white", prefer_horizontal=1.0,
                       random_state=int(o.get("seed", 7)), max_words=int(o.get("max_words", 120)), relative_scaling=0.5, margin=4,
                       color_func=lambda word, font_size, position, orientation, random_state=None, **kw: palette[sum(map(ord, word)) % len(palette)] if not o.get("single_color") else st.SEQUENTIAL[10])
        wc.generate_from_frequencies(freq)
        ax = fig.add_axes([0.01, 0.01, 0.98, tm - 0.02])
        ax.imshow(wc.to_array(), interpolation="bilinear")
        ax.axis("off")
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, ["글자 크기 ∝ 가중치(빈도). 위치·방향은 의미가 없습니다. 정확한 비교는 막대 차트를 쓰세요"], {}


def _venn(data, title, sub, o, w, h):
    sets = as_dict(data.get("sets"), "sets")
    need(2 <= len(sets) <= 3, "venn은 sets에 집합 2~3개가 필요합니다({이름: [항목...]})", example={"sets": {"A제약 거래처": ["병원1", "병원2"], "B제약 거래처": ["병원2", "병원3"]}})
    names = list(sets)
    S = [set(map(str, as_list(sets[n], f"sets.{n}"))) for n in names]
    with figure(w, h) as fig:
        ax = fig.add_axes([0.05, 0.02, 0.9, top_margin(title, sub) - 0.04])
        ax.set_aspect("equal"); ax.axis("off")
        if len(S) == 2:
            cen, r = [(-0.55, 0), (0.55, 0)], 1.0
            regions = {(0,): S[0] - S[1], (1,): S[1] - S[0], (0, 1): S[0] & S[1]}
            pos = {(0,): (-1.0, 0), (1,): (1.0, 0), (0, 1): (0, 0)}
            ax.set_xlim(-1.9, 1.9); ax.set_ylim(-1.3, 1.4)
        else:
            cen, r = [(-0.55, 0.35), (0.55, 0.35), (0, -0.55)], 1.0
            a, b, c = S
            regions = {(0,): a - b - c, (1,): b - a - c, (2,): c - a - b, (0, 1): (a & b) - c, (0, 2): (a & c) - b, (1, 2): (b & c) - a, (0, 1, 2): a & b & c}
            pos = {(0,): (-1.0, 0.6), (1,): (1.0, 0.6), (2,): (0, -1.1), (0, 1): (0, 0.75), (0, 2): (-0.62, -0.35), (1, 2): (0.62, -0.35), (0, 1, 2): (0, 0.05)}
            ax.set_xlim(-1.9, 1.9); ax.set_ylim(-1.8, 1.6)
        for i, (x, y) in enumerate(cen):
            ax.add_patch(patches.Circle((x, y), r, fc=C[i], alpha=0.22, ec=C[i], lw=2))
            lx = x + (-0.4 if x < 0 else (0.4 if x > 0 else 0))
            ly = y + (r + 0.12 if y >= 0 else -r - 0.12)
            ax.text(lx, ly, f"{names[i]} ({len(S[i])})", ha="center", va="bottom" if y >= 0 else "top", fontsize=12, fontweight="bold", color=C[i])
        for k, items in regions.items():
            ax.text(*pos[k], f"{len(items):,}", ha="center", va="center", fontsize=15, fontweight="bold", color=st.INK)
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, ["원 크기는 고정(면적 비례 아님). 숫자는 각 영역에만 속한 항목 수"], {"regions": {"&".join(names[i] for i in k): len(v) for k, v in regions.items()}}


def _waffle(data, title, sub, o, w, h):
    cats = [str(c) for c in as_list(data.get("categories"), "categories")]
    vals = [as_number(v, "values") or 0 for v in as_list(data.get("values"), "values")]
    need(cats and len(cats) == len(vals), "waffle은 categories와 values(같은 개수)가 필요합니다", example={"categories": ["전문약", "일반약"], "values": [72, 28]})
    need(len(cats) <= 8, "waffle 항목은 최대 8개입니다")
    tot = sum(vals)
    need(tot > 0, "values 합계가 0입니다")
    raw = [v / tot * 100 for v in vals]
    cells = [int(np.floor(x)) for x in raw]
    for i in np.argsort([-(x - np.floor(x)) for x in raw])[: 100 - sum(cells)]:  # 최대 잉여 배분(합 100칸 보장)
        cells[i] += 1
    with figure(w, h) as fig:
        tm = top_margin(title, sub)
        ax = fig.add_axes([0.04, 0.04, 0.55, tm - 0.07])
        ax.set_aspect("equal"); ax.axis("off")
        k = 0
        colors = []
        for i, n in enumerate(cells):
            colors += [C[i]] * n
        for idx, col in enumerate(colors):
            r, c = divmod(idx, 10)
            ax.add_patch(patches.FancyBboxPatch((c, 9 - r), 0.86, 0.86, boxstyle="round,pad=0,rounding_size=0.12", fc=col, ec="none"))
        ax.set_xlim(-0.2, 10); ax.set_ylim(-0.2, 10)
        for i, (c_, v, n) in enumerate(zip(cats, vals, cells)):
            fig.text(0.63, tm - 0.12 - i * 0.075, "■", color=C[i], fontsize=16, va="center")
            fig.text(0.66, tm - 0.12 - i * 0.075, f"{c_}  {raw[i]:.1f}%  ({v:,.0f})", fontsize=12, va="center", color=st.INK)
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, ["한 칸 = 1%. 반올림 합이 100칸이 되도록 최대 잉여 방식으로 배분"], {"cells": dict(zip(cats, cells))}


def _grid_xyz(data):
    ex = {"x": [1, 2, 3], "y": [10, 20], "z": [[1, 2, 3], [2, 3, 5]]}
    x = np.array([as_number(v, "x") for v in as_list(data.get("x"), "x")], float)
    y = np.array([as_number(v, "y") for v in as_list(data.get("y"), "y")], float)
    z = np.array([[as_number(v, "z") for v in as_list(r, "z[]")] for r in as_list(data.get("z"), "z")], float)
    need(len(x) >= 2 and len(y) >= 2 and z.shape == (len(y), len(x)), f"z는 y개수×x개수({len(y)}×{len(x)}) 2차원 배열이어야 합니다(현재 {z.shape})", example=ex)
    return x, y, z


def _surface_3d(data, title, sub, o, w, h):
    x, y, z = _grid_xyz(data)
    X, Y = np.meshgrid(x, y)
    with figure(w, h) as fig:
        ax = fig.add_axes([0.0, 0.0, 0.92, top_margin(title, sub)], projection="3d")
        surf = ax.plot_surface(X, Y, z, cmap=SEQ_CMAP, edgecolor="white", lw=0.3, antialiased=True)
        ax.set_xlabel(o.get("x_label", "x")); ax.set_ylabel(o.get("y_label", "y")); ax.set_zlabel(o.get("z_label", "z"))
        ax.view_init(elev=float(o.get("elev", 28)), azim=float(o.get("azim", -55)))
        fig.colorbar(surf, ax=ax, shrink=0.55, pad=0.08)
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, ["3D는 시점에 따라 값이 왜곡돼 보입니다. 정확한 읽기는 contour(등고선)나 heatmap을 함께 쓰세요"], {}


def _contour(data, title, sub, o, w, h):
    x, y, z = _grid_xyz(data)
    with figure(w, h) as fig:
        ax = fig.add_axes([0.09, 0.11, 0.8, top_margin(title, sub) - 0.14])
        cf = ax.contourf(x, y, z, levels=int(o.get("levels", 12)), cmap=SEQ_CMAP)
        cs = ax.contour(x, y, z, levels=cf.levels, colors="white", linewidths=0.6)
        ax.clabel(cs, fmt=lambda v: f"{v:.3g}", fontsize=8, colors=st.INK)
        if o.get("mark_max", True):
            iy, ix = np.unravel_index(np.nanargmax(z), z.shape)
            ax.plot(x[ix], y[iy], "*", color=st.UP, ms=14, mec="white")
        ax.set_xlabel(o.get("x_label", "x")); ax.set_ylabel(o.get("y_label", "y"))
        ax.grid(False)
        fig.colorbar(cf, cax=fig.add_axes([0.91, 0.11, 0.018, top_margin(title, sub) - 0.14]))
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, ["별표: 격자 안 최댓값 위치"], {}


def _scatter_3d(data, title, sub, o, w, h):
    gs = as_list(data.get("groups"), "groups")
    need(gs, "scatter_3d는 groups=[{name, points:[[x,y,z],...]}]가 필요합니다", example=[{"name": "A", "points": [[1, 2, 3], [2, 3, 1]]}])
    with figure(w, h) as fig:
        ax = fig.add_axes([0.0, 0.0, 1.0, top_margin(title, sub)], projection="3d")
        for i, g in enumerate(gs):
            g = as_dict(g, f"groups[{i}]")
            p = np.array([[as_number(v, "point") for v in as_list(q, "points[]")] for q in as_list(g.get("points"), f"groups[{i}].points")], float)
            need(p.ndim == 2 and p.shape[1] == 3, f"groups[{i}].points는 [x, y, z] 목록이어야 합니다")
            ax.scatter(p[:, 0], p[:, 1], p[:, 2], s=26, color=C[i % 8], alpha=0.8, label=str(g.get("name", i)), depthshade=True)
        ax.set_xlabel(o.get("x_label", "x")); ax.set_ylabel(o.get("y_label", "y")); ax.set_zlabel(o.get("z_label", "z"))
        ax.view_init(elev=float(o.get("elev", 22)), azim=float(o.get("azim", -60)))
        if len(gs) > 1:
            ax.legend(loc="upper right")
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, ["3D 산점도는 정적 이미지에서 깊이 판단이 어렵습니다. PCA 결과라면 2차원(PC1×PC2) 산점도를 함께 제시하세요"], {}
