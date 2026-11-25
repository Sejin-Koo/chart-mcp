"""계층 구조와 비중 — 트리맵·선버스트·마리메코."""
from __future__ import annotations

import math

import numpy as np
from matplotlib.patches import Rectangle, Wedge

from .. import style as st
from ..core import Result, figure, legend_top, put_title, to_png, top_for
from ..errors import as_dict, as_list, as_number, need
from .common import categories, series

EX = [{"name": "전문약"}, {"name": "순환기", "parent": "전문약", "value": 420}, {"name": "건기식", "value": 90}]


def _tree(args):
    """items(평면 목록, parent) 또는 tree(중첩) → 루트 노드 목록 [{name, value, children}]. 부모 값은 자식 합."""
    if args.get("tree") is not None:
        t = args["tree"]
        if isinstance(t, str):
            import json
            t = json.loads(t)
        roots = t if isinstance(t, list) else ([t] if not as_dict(t, "tree").get("children") or as_dict(t, "tree").get("value") is not None else as_dict(t, "tree")["children"])

        def norm(n):
            n = as_dict(n, "tree")
            ch = [norm(c) for c in as_list(n.get("children"), "children")]
            v = as_number(n.get("value"), "value")
            return {"name": str(n.get("name", "")), "value": sum(c["value"] for c in ch) if ch else (v or 0), "children": ch}
        return [norm(r) for r in roots]
    items = as_list(args.get("items"), "items")
    need(items, "items=[{name, parent, value}] 또는 tree가 필요합니다", example=EX)
    nodes, order = {}, []
    for i, it in enumerate(items):
        it = as_dict(it, f"items[{i}]")
        name = str(it.get("name") or "")
        need(name, f"items[{i}].name이 비어 있습니다", example=EX)
        nodes[name] = {"name": name, "parent": str(it["parent"]) if it.get("parent") not in (None, "") else None,
                       "own": as_number(it.get("value"), f"items[{i}].value") or 0, "children": []}
        order.append(name)
    roots = []
    for nm in order:
        n = nodes[nm]
        if n["parent"]:
            need(n["parent"] in nodes, f"'{nm}'의 parent '{n['parent']}'가 items에 없습니다", hint="부모 항목도 items에 넣으세요", example=EX)
            nodes[n["parent"]]["children"].append(n)
        else:
            roots.append(n)

    def total(n):
        n["value"] = sum(total(c) for c in n["children"]) if n["children"] else n["own"]
        return n["value"]
    for r in roots:
        total(r)
    return roots


def _squarify(values, x, y, w, h):
    """정사각형에 가까운 비율로 사각형을 나눈다(Bruls 알고리즘). values는 내림차순 정렬된 양수.
    0 이하 값은 넓이 0 사각형으로 돌려준다(1.4.0 — 자식 없는 0값 상위 항목이 있으면 0으로 나누기 오류)."""
    vals_all = list(values)
    pos_idx = [i for i, v in enumerate(vals_all) if v and v > 0]
    if len(pos_idx) < len(vals_all):
        sub = _squarify([vals_all[i] for i in pos_idx], x, y, w, h) if pos_idx else []
        out = [(x, y, 0, 0)] * len(vals_all)
        for k, i in enumerate(pos_idx):
            out[i] = sub[k]
        return out
    rects = []
    vals = list(values)
    tot = sum(vals)
    if tot <= 0:
        return [(x, y, 0, 0)] * len(vals)
    scale = w * h / tot
    areas = [v * scale for v in vals]

    def worst(row, length):
        s = sum(row)
        return max(max(length * length * r / (s * s), (s * s) / (length * length * r)) for r in row)

    i = 0
    while i < len(areas):
        length = min(w, h)
        row = [areas[i]]
        i += 1
        while i < len(areas) and worst(row + [areas[i]], length) <= worst(row, length):
            row.append(areas[i])
            i += 1
        s = sum(row)
        if w >= h:
            cw = s / h
            yy = y
            for a in row:
                rects.append((x, yy, cw, a / cw))
                yy += a / cw
            x += cw
            w -= cw
        else:
            ch = s / w
            xx = x
            for a in row:
                rects.append((xx, y, a / ch, ch))
                xx += a / ch
            y += ch
            h -= ch
    return rects


def _treemap(args, o):
    title, sub, unit = args.get("title"), args.get("subtitle"), args.get("unit")
    roots = sorted(_tree(args), key=lambda n: -n["value"])
    cols = st.palette(len(roots), wide=True)
    total = sum(r["value"] for r in roots)
    rows = []
    with figure(3.6, o) as fig:
        top = top_for(fig, title, sub, o, True)
        ax = fig.add_axes([0.01, 0.01, 0.98, top - 0.02])
        ax.axis("off")
        ax._box_labels = []
        W, H = 1.6, 1.0
        rects = _squarify([r["value"] for r in roots], 0, 0, W, H)
        for r, (x, y, w, h), c in zip(roots, rects, cols):
            kids = sorted(r["children"], key=lambda n: -n["value"])
            if kids:
                kr = _squarify([k["value"] for k in kids], x, y, w, h)
                for k, (kx, ky, kw, kh) in zip(kids, kr):
                    ax.add_patch(Rectangle((kx, ky), kw, kh, facecolor=c, edgecolor="white", lw=1.2, alpha=0.92))
                    _box_label(ax, kx, ky, kw, kh, k["name"], k["value"], total, c, unit)
                    rows.append([r["name"], k["name"], k["value"], round(k["value"] / total * 100, 1)])
                ax.add_patch(Rectangle((x, y), w, h, fill=False, edgecolor="white", lw=3.5))
            else:
                ax.add_patch(Rectangle((x, y), w, h, facecolor=c, edgecolor="white", lw=3.5))
                _box_label(ax, x, y, w, h, r["name"], r["value"], total, c, unit)
                rows.append([r["name"], "", r["value"], round(r["value"] / total * 100, 1)])
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        _fit_box_labels(fig, ax)
        leg = [(f"{r['name']} {st.fmt(r['value'])}{unit or ''} ({r['value'] / total * 100:.0f}%)", c, "patch") for r, c in zip(roots, cols)]
        legend_top(fig, leg, title, sub, o, ncol=_legend_cols(fig, leg))
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["트리맵: 사각형 넓이가 값에 비례합니다. 같은 색 = 같은 상위 항목"], table=(["상위", "항목", "값", "비율(%)"], rows))


def _box_label(ax, x, y, w, h, name, v, total, c, unit):
    if w * h < 0.004:
        return
    fs = 8.5 if w * h > 0.06 else 7.2
    t = ax.text(x + 0.015, y + 0.03, f"{name}\n{st.fmt(v)}{unit or ''} ({v / total * 100:.0f}%)", ha="left", va="top", fontsize=fs, color=st.ink_on(c),
                fontweight="bold", linespacing=1.3, clip_on=True)
    pct = f"{v / total * 100:.0f}%"
    ax._box_labels.append((t, w, h, (f"{name}\n{pct}", f"{_wrap(name)}\n{pct}", name, _wrap(name), pct)))


def _wrap(name: str) -> str:
    """긴 이름을 두 줄로(공백이 있으면 공백에서, 없으면 가운데에서)."""
    name = str(name)
    if len(name) <= 4:
        return name
    if " " in name:
        k = min((abs(i - len(name) / 2), i) for i, ch in enumerate(name) if ch == " ")[1]
        return name[:k] + "\n" + name[k + 1:]
    k = (len(name) + 1) // 2
    return name[:k] + "\n" + name[k:]


def _fit_box_labels(fig, ax):
    """칸보다 큰 이름은 줄이기 → '이름+비율' → 이름만 → 비율만 → 생략(1.4.0 — 긴 이름이 칸 밖으로 잘렸다)."""
    from .. import declutter
    fig.canvas.draw()
    sx = abs(ax.transData.transform((1, 0))[0] - ax.transData.transform((0, 0))[0])
    sy = abs(ax.transData.transform((0, 1))[1] - ax.transData.transform((0, 0))[1])
    hidden = 0
    for t, w, h, fb in ax._box_labels:
        if not declutter.fit_in(fig, t, w * sx - 0.03 * sx, h * sy - 0.04 * sy, fallbacks=fb):
            hidden += 1
    if hidden:
        declutter._note(f"작은 칸 {hidden}개는 이름을 넣을 자리가 없어 생략했습니다(값은 범례·엑셀 원본 표)")


def _legend_cols(fig, items):
    """범례 글이 길면 한 줄에 넣을 칸 수를 줄인다(그림 폭을 넘지 않게)."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath
    fp = FontProperties(family=__import__("matplotlib").rcParams["font.family"], size=st.FONT_SIZE - 0.5)
    widths = [TextPath((0, 0), lab, prop=fp).get_extents().width / 72 + 0.45 for lab, _, _ in items]  # 인치(표식·간격 포함)
    W = fig.get_size_inches()[0] * 0.96
    for ncol in range(min(len(items), 6), 0, -1):
        rows = [widths[i:i + ncol] for i in range(0, len(widths), ncol)]
        colw = [max((r[c] for r in rows if c < len(r)), default=0) for c in range(ncol)]
        if sum(colw) <= W:
            return ncol
    return 1


def _sunburst(args, o):
    title, sub, unit = args.get("title"), args.get("subtitle"), args.get("unit")
    roots = _tree(args)
    cols = st.palette(len(roots), wide=True)
    total = sum(r["value"] for r in roots)
    rows = []
    with figure(3.6, o) as fig:
        top = top_for(fig, title, sub, o, False)
        ax = fig.add_axes([0.05, 0.02, 0.9, top - 0.04])
        ax.set_aspect("equal")
        ax.axis("off")
        labels = []

        def ring(nodes, a0, a1, depth, color, parent_total):
            a = a0
            tot = sum(n["value"] for n in nodes) or 1
            for k, n in enumerate(nodes):
                sw = (a1 - a0) * n["value"] / tot
                r_in, r_out = 0.3 + 0.33 * depth, 0.3 + 0.33 * (depth + 1)
                c = color if depth == 0 else _tint(color, 0.25 + 0.5 * k / max(1, len(nodes)))
                ax.add_patch(Wedge((0, 0), r_out, 90 - a - sw, 90 - a, width=r_out - r_in - 0.01, facecolor=c, edgecolor="white", lw=1.2))
                mid = math.radians(90 - a - sw / 2)
                rr = (r_in + r_out) / 2
                if sw > 4:
                    rot = (math.degrees(mid) % 360)
                    rot = rot - 180 if 90 < rot < 270 else rot
                    pct = f"{n['value'] / total * 100:.0f}%"
                    t = ax.text(rr * math.cos(mid), rr * math.sin(mid), f"{n['name']}\n{pct}", ha="center", va="center",
                                fontsize=7.4 if depth else 8.2, color=st.ink_on(c), fontweight="bold", rotation=rot if depth else 0, linespacing=1.15)
                    labels.append((t, (r_out - r_in) * 0.85, rr * math.radians(sw) * 0.85, depth,
                                   (f"{_wrap(n['name'])}\n{pct}", f"{n['name']} {pct}", n["name"], _wrap(n["name"]), pct)))
                rows.append(["  " * depth + n["name"], n["value"], round(n["value"] / total * 100, 1)])
                if n["children"]:
                    ring(n["children"], a, a + sw, depth + 1, color if depth else c, n["value"])
                a += sw
        a = 0
        for r, c in zip(roots, cols):
            sw = 360 * r["value"] / total
            ring([r], a, a + sw, 0, c, total)
            a += sw
        ax.text(0, 0, f"{st.fmt(total)}\n{unit or '합계'}", ha="center", va="center", fontsize=9, fontweight="bold", color=st.INK)
        lim = 0.3 + 0.33 * _depth(roots) + 0.05
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        _fit_ring_labels(fig, ax, labels)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["선버스트: 안쪽이 상위 항목, 바깥이 하위 항목. 각도가 비중입니다"], table=(["항목", "값", "비율(%)"], rows))


def _fit_ring_labels(fig, ax, labels):
    """고리 칸 안에 이름을 맞춘다(1.4.0 — 긴 이름이 칸을 넘어 이웃 칸 이름과 겹쳤다).
    바깥 고리 글은 반지름 방향으로 쓰므로 글 폭 ≤ 고리 두께, 글 높이 ≤ 호 길이. 안쪽 고리(가로 글)는 두 방향 중 넓은 쪽."""
    from .. import declutter
    fig.canvas.draw()
    s = abs(ax.transData.transform((1, 0))[0] - ax.transData.transform((0, 0))[0])
    hidden = 0
    for t, thick, arc, depth, fb in labels:
        if depth:
            w, h = thick * s, arc * s
        else:  # 안쪽 고리는 가로 글 — 고리 두께보다 조금 넓게까지만
            w, h = thick * s * 1.15, min(arc, thick * 1.2) * s
        if not declutter.fit_in(fig, t, w, h, fallbacks=fb):
            hidden += 1
    if hidden:
        declutter._note(f"좁은 칸 {hidden}개는 이름을 넣을 자리가 없어 생략했습니다(값은 엑셀 원본 표)")


def _depth(nodes):
    return max((1 + _depth(n["children"]) for n in nodes), default=0)


def _tint(hexc, t):
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % (int(r + (255 - r) * t), int(g + (255 - g) * t), int(b + (255 - b) * t))


def _marimekko(args, o):
    title, sub, unit = args.get("title"), args.get("subtitle"), args.get("unit")
    cats = categories(args)
    ser = series(args, len(cats))
    cols = st.palette(len(ser))
    m = np.array([[v or 0 for v in s["values"]] for s in ser], float)  # 계열 × 열
    colsum = m.sum(axis=0)
    total = colsum.sum()
    need(total > 0, "마리메코 값 합계가 0입니다")
    widths = colsum / total
    with figure(3.6, o) as fig:
        top = top_for(fig, title, sub, o, True)
        ax = fig.add_axes([0.07, 0.12, 0.9, top - 0.14])
        x = 0.0
        rows = []
        col_labels = []
        for j, c in enumerate(cats):
            y = 0.0
            for i, s in enumerate(ser):
                hgt = m[i, j] / colsum[j] if colsum[j] else 0
                ax.add_patch(Rectangle((x, y), widths[j], hgt, facecolor=cols[i], edgecolor="white", lw=1.5))
                if hgt > 0.07 and widths[j] > 0.06:
                    ax.text(x + widths[j] / 2, y + hgt / 2, f"{hgt * 100:.0f}%", ha="center", va="center", fontsize=st.LABEL_SIZE, fontweight="bold",
                            color=st.ink_on(cols[i]))
                rows.append([c, s["name"], m[i, j], round(hgt * 100, 1), round(widths[j] * 100, 1)])
                y += hgt
            col_labels.append((widths[j], ax.text(x + widths[j] / 2, -0.04, f"{c}\n({widths[j] * 100:.0f}%)", ha="center", va="top",
                                                   fontsize=st.FONT_SIZE - 0.5)))
            x += widths[j]
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xticks([])
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1], ["0%", "25%", "50%", "75%", "100%"])
        for s_ in ("top", "right", "bottom"):
            ax.spines[s_].set_visible(False)
        ax.spines["left"].set_color(st.AXIS)
        from .. import declutter
        declutter.fit_row(fig, [t for _, t in sorted(col_labels, key=lambda z: -z[0])])  # 넓은 열 이름부터 남긴다
        legend_top(fig, [(s["name"], c, "patch") for s, c in zip(ser, cols)], title, sub, o)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["마리메코: 막대 폭 = 열 전체 크기의 비중, 막대 안 높이 = 열 안의 구성비"],
                  table=(["열", "계열", "값", "열 안 비율(%)", "열 폭(%)"], rows))


def draw(ct: str, args: dict, o: dict) -> Result:
    if ct == "treemap":
        return _treemap(args, o)
    if ct == "sunburst":
        return _sunburst(args, o)
    if ct == "marimekko":
        return _marimekko(args, o)
    raise ValueError(ct)
