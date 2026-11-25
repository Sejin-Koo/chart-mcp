"""흐름과 관계 — 산키·네트워크 관계도·원형 관계도."""
from __future__ import annotations

import math

import numpy as np
from matplotlib.patches import FancyArrowPatch, PathPatch, Rectangle
from matplotlib.path import Path

from .. import style as st
from ..core import Result, figure, legend_top, put_title, to_png, top_for
from ..errors import as_dict, as_list, as_number, need

EX = [{"source": "제조사", "target": "도매", "value": 820}, {"source": "도매", "target": "약국", "value": 500}]


def _links(args, need_value=False):
    ls = as_list(args.get("links"), "links")
    need(ls, "links=[{source, target, value}]가 필요합니다", example=EX)
    out = []
    for i, l in enumerate(ls):
        l = as_dict(l, f"links[{i}]")
        s, t = str(l.get("source", "")), str(l.get("target", ""))
        need(s and t, f"links[{i}]에 source·target이 필요합니다", example=EX)
        v = as_number(l.get("value"), f"links[{i}].value")
        if need_value:
            need(v is not None and v > 0, f"links[{i}]의 value가 0보다 커야 합니다(산키는 흐름량이 필요)", example=EX)
        out.append((s, t, v if v is not None else 1.0))
    return out


def _groups(args):
    g = {}
    for i, n in enumerate(as_list(args.get("nodes"), "nodes")):
        n = as_dict(n, f"nodes[{i}]")
        g[str(n.get("name"))] = n.get("group")
    return g


def _sankey(args, o):
    title, sub, unit = args.get("title"), args.get("subtitle"), args.get("unit")
    links = _links(args, need_value=True)
    names = []
    for s, t, _ in links:
        for x in (s, t):
            if x not in names:
                names.append(x)
    # 단계(열) — 가장 긴 선행 경로 길이. 순환 검사
    level = {n: 0 for n in names}
    for _ in range(len(names) + 1):
        changed = False
        for s, t, _ in links:
            if level[t] < level[s] + 1:
                level[t] = level[s] + 1
                changed = True
        if not changed:
            break
    else:
        need(False, "산키에 순환(A→B→A)이 있습니다", hint="단계별로 이름을 구분하세요(예: '도매(입고)'·'도매(출고)')")
    need(all(level[n] <= len(names) for n in names), "산키에 순환이 있습니다", hint="단계별로 이름을 구분하세요")
    if str(o.get("align", "justify")) == "justify":
        mx = max(level.values())
        for n in names:
            if not any(s == n for s, _, _ in links):
                level[n] = mx
    nlev = max(level.values()) + 1
    inflow = {n: sum(v for s, t, v in links if t == n) for n in names}
    outflow = {n: sum(v for s, t, v in links if s == n) for n in names}
    size = {n: max(inflow[n], outflow[n]) for n in names}
    cols_by = {}
    groups = _groups(args)
    gnames = []
    for n in names:
        g = groups.get(n) or n
        if g not in gnames:
            gnames.append(g)
    gpal = st.palette(len(gnames), wide=True) if len(gnames) <= 6 else None
    for n in names:
        g = groups.get(n) or n
        cols_by[n] = gpal[gnames.index(g)] if gpal else st.PALETTE[level[n] % 6]
    per_level = [[n for n in names if level[n] == k] for k in range(nlev)]
    tot_max = max(sum(size[n] for n in lv) for lv in per_level)
    gap = 0.04
    scale = (1 - gap * (max(len(lv) for lv in per_level) - 1)) / tot_max
    pos = {}
    for k, lv in enumerate(per_level):
        used = sum(size[n] for n in lv) * scale + gap * (len(lv) - 1)
        y = (1 - used) / 2
        for n in lv:
            h = size[n] * scale
            pos[n] = [k, y, h]
            y += h + gap
    with figure(3.8, o) as fig:
        top = top_for(fig, title, sub, o, False)
        ax = fig.add_axes([0.02, 0.02, 0.96, top - 0.04])
        ax.axis("off")
        nw = 0.035
        xcoord = lambda k: 0.06 + k * (0.88 / max(1, nlev - 1))  # noqa: E731
        out_off = {n: 0.0 for n in names}
        in_off = {n: 0.0 for n in names}
        for s, t, v in sorted(links, key=lambda l: (pos[l[0]][1], pos[l[1]][1])):
            hs = v * scale
            x0 = xcoord(pos[s][0]) + nw / 2
            x1 = xcoord(pos[t][0]) - nw / 2
            y0 = pos[s][1] + out_off[s]
            y1 = pos[t][1] + in_off[t]
            out_off[s] += hs
            in_off[t] += hs
            xm = (x0 + x1) / 2
            verts = [(x0, y0), (xm, y0), (xm, y1), (x1, y1), (x1, y1 + hs), (xm, y1 + hs), (xm, y0 + hs), (x0, y0 + hs), (x0, y0)]
            codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.CLOSEPOLY]
            ax.add_patch(PathPatch(Path(verts, codes), facecolor=cols_by[s], alpha=0.28, edgecolor="none"))
        col_texts = {}
        for n in names:
            k, y, h = pos[n]
            x = xcoord(k)
            ax.add_patch(Rectangle((x - nw / 2, y), nw, h, facecolor=cols_by[n], edgecolor="none"))
            right = k < nlev - 1
            t = ax.text(x + (nw / 2 + 0.01) * (1 if right else -1), y + h / 2, f"{n}\n{st.fmt(size[n])}{unit or ''}", ha="left" if right else "right",
                        va="center", fontsize=st.LABEL_SIZE, color=st.INK, linespacing=1.2)
            col_texts.setdefault(k, []).append((size[n], t, x + (nw / 2) * (1 if right else -1)))
        ax.set_xlim(0, 1)
        ax.set_ylim(1.02, -0.02)
        # 같은 열의 이름표가 겹치면 위아래로 벌림(1.4.0 — 작은 노드 이름이 서로 겹쳤다). 큰 노드부터 남긴다.
        from .. import declutter
        for k, items in col_texts.items():
            items.sort(key=lambda z: -z[0])
            declutter.stack_vertical(fig, ax, [t for _, t, _ in items], leader_x=items[0][2])
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["산키: 띠의 굵기가 흐름량입니다"], table=(["출발", "도착", "값"], [list(l) for l in links]))


def _network(args, o, circular=False):
    title, sub = args.get("title"), args.get("subtitle")
    links = _links(args)
    groups = _groups(args)
    names = []
    for s, t, _ in links:
        for x in (s, t):
            if x not in names:
                names.append(x)
    for n in groups:
        if n not in names:
            names.append(n)
    gnames = []
    for n in names:
        g = groups.get(n) or "기타"
        if g not in gnames:
            gnames.append(g)
    gpal = st.palette(len(gnames), wide=True)
    col = {n: gpal[gnames.index(groups.get(n) or "기타")] for n in names}
    deg = {n: sum(v for s, t, v in links if n in (s, t)) for n in names}
    N = len(names)
    if circular:
        pos = {n: (math.cos(math.pi / 2 - 2 * math.pi * i / N), math.sin(math.pi / 2 - 2 * math.pi * i / N)) for i, n in enumerate(names)}
    else:
        import networkx as nx
        g = nx.Graph()
        g.add_nodes_from(names)
        g.add_weighted_edges_from(links)
        pos = nx.kamada_kawai_layout(g) if N <= 60 else nx.spring_layout(g, seed=7, k=2.5 / math.sqrt(max(N, 1)), iterations=300)
        xs_, ys_ = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
        sx = (max(xs_) - min(xs_)) or 1
        sy = (max(ys_) - min(ys_)) or 1
        if sy > sx:  # 가로로 긴 그림에 맞춰 눕힌다
            pos = {n: (p[1], p[0]) for n, p in pos.items()}
            sx, sy = sy, sx
            xs_, ys_ = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
        pos = {n: ((p[0] - min(xs_)) / sx * 3.2 - 1.6, (p[1] - min(ys_)) / sy * 2 - 1) for n, p in pos.items()}
    vmax = max(v for *_, v in links) or 1
    dmax = max(deg.values()) or 1
    directed = bool(o.get("directed"))
    with figure(3.8, o) as fig:
        top = top_for(fig, title, sub, o, len(gnames) > 1)
        ax = fig.add_axes([0.04, 0.03, 0.92, top - 0.05])
        if circular:
            ax.set_aspect("equal")
        ax.axis("off")
        for s, t, v in links:
            (x0, y0), (x1, y1) = pos[s], pos[t]
            lw = 0.8 + 3.2 * v / vmax
            if circular:
                ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), connectionstyle="arc3,rad=0.25", arrowstyle="-|>" if directed else "-",
                                             mutation_scale=10, lw=lw, color=st.GRAY, alpha=0.9, shrinkA=10, shrinkB=10, zorder=1))
            else:
                ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>" if directed else "-", mutation_scale=10, lw=lw, color=st.GRAY,
                                             alpha=0.9, shrinkA=9, shrinkB=9, zorder=1))
        for n in names:
            x, y = pos[n]
            r = 120 + 520 * deg[n] / dmax
            ax.scatter([x], [y], s=r, color=col[n], edgecolor="white", lw=1.2, zorder=3)
            off = 1.18 if circular else 1.0
            if circular:
                ax.text(x * off, y * off, n, ha="center", va="center", fontsize=st.FONT_SIZE - 0.5, color=st.INK, zorder=4)
            else:
                ax.annotate(n, (x, y), xytext=(0, -math.sqrt(r) / 2 - 3), textcoords="offset points", ha="center", va="top",
                            fontsize=st.FONT_SIZE - 0.5, color=st.INK, zorder=4)
        xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
        pad = 0.3
        ax.set_xlim(min(xs) - pad, max(xs) + pad)
        ax.set_ylim(min(ys) - pad, max(ys) + pad)
        if len(gnames) > 1:
            legend_top(fig, [(g, c, "marker") for g, c in zip(gnames, gpal)], title, sub, o)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["관계도: 원 크기 = 연결 강도 합, 선 굵기 = 연결 값" + (" (배치는 자동 계산 — 위치 자체에는 의미가 없습니다)" if not circular else "")],
                  table=(["출발", "도착", "값"], [list(l) for l in links]))


def draw(ct: str, args: dict, o: dict) -> Result:
    if ct == "sankey":
        return _sankey(args, o)
    if ct == "network":
        return _network(args, o)
    if ct == "circular_network":
        return _network(args, o, circular=True)
    raise ValueError(ct)
