#!/usr/bin/env python3
"""차트 명세(막대·꺾은선·영역·원·도넛·혼합) → Word용 PNG(계정 스킬 sys-file-builder).
scripts/chart.js가 정리한 명세(lib/chart-spec.js normalize 결과)를 받아 그린다 — 직접 부르지 말고 chart.js png를 쓴다.
  python3 scripts/chart-png.py <정리된명세.json> <출력.png>
규칙(ref-report-visualization 3·4·6절): 같은 색·같은 범주 순서, 막대 끝 같은 색 굵은 숫자, 누적 막대는 안쪽 흰 숫자 + 오른쪽 합계,
범례는 플롯 위쪽 한 줄(색의 의미), 격자는 연회색 세로선만, 맑은 고딕, 본문 폭 16cm·220dpi."""
import json, os, subprocess, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.ticker
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Patch
from matplotlib.lines import Line2D


# 주 눈금선: 연한 회색(D9D9D9) 실선 — 사용자 지정 2026-11-24(Excel·PowerPoint 차트·채팅 그림과 통일)
GRID_KW = {"color": "#D9D9D9", "linestyle": "-", "linewidth": 0.8}

def find_fonts():
    """맑은 고딕 TTF 경로(보통체·굵은체). 없으면 오류 — ref-report-common-style 3절 절차로 먼저 설치."""
    paths = []
    try:
        out = subprocess.run(["fc-list", ":family=Malgun Gothic", "file"], capture_output=True, text=True).stdout
        paths = [l.split(":")[0].strip() for l in out.splitlines() if l.strip()]
    except FileNotFoundError:
        pass
    # CHART_FONT_DIRS(':'로 구분): 차트 서버(chart-mcp)처럼 글꼴을 다른 곳(/tmp 등)에 받아 두는 곳에서 이 파일 사본을 쓸 때(2026-11-26)
    extra = [d for d in os.environ.get("CHART_FONT_DIRS", "").split(":") if d]
    for d in extra + [os.path.expanduser("~/.local/share/fonts"), "/usr/share/fonts", "/usr/local/share/fonts"]:
        for root, _, files in os.walk(d) if os.path.isdir(d) else []:
            for f in files:
                if f.lower() in ("malgun.ttf", "malgunbd.ttf"):
                    paths.append(os.path.join(root, f))
    paths = sorted(set(paths))
    if not paths:
        sys.exit("맑은 고딕 글꼴(malgun.ttf)을 찾지 못했습니다 — ref-report-common-style 3절대로 설치한 뒤 다시 실행하세요")
    return paths


def fmt(v, f):
    if v is None:
        return ""
    f = f or "#,##0"
    pct = f.endswith("%")
    dec = len(f.split(".")[1].rstrip("%")) if "." in f else 0
    x = v * 100 if pct else v
    s = f"{abs(x):,.{dec}f}" if "," in f else f"{abs(x):.{dec}f}"
    return ("-" if x < 0 else "") + s + ("%" if pct else "")


def ink_on(hexc):
    """막대 색 위 숫자 색 — 밝은 색이면 진한 회색, 어두운 색이면 흰색(chart-spec.js inkOn과 같은 식)"""
    h = str(hexc or "").lstrip("#")
    if len(h) != 6:
        return "#FFFFFF"
    c = []
    for i in (0, 2, 4):
        v = int(h[i:i + 2], 16) / 255
        c.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return "#262626" if 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] > 0.36 else "#FFFFFF"


def label_w(t, pt):
    """숫자 라벨 폭(인치) — pptx-native-chart.js labelW와 같은 근사"""
    w = 0.0
    for ch in str(t):
        w += 0.56 if ch.isdigit() else 0.28 if ch in ",." else 0.85 if ch == "%" else 0.36 if ch == "-" else 0.95 if ord(ch) >= 0x1100 else 0.6
    return w * pt / 72


def spread_line_labels(pts, gap, last_only):
    """같은 x의 꺾은선 라벨 자리 정하기(xlsx-bar.js lineMoves·PowerPoint 차트와 같은 규칙).
    pts: [(k, y)] → {k: (y_text, va, ha)}. gap = 라벨 한 줄 높이(값 단위).
    끝 점만 라벨이면 점 오른쪽에 두고 겹치는 무리를 위아래로 벌린다. 점마다 라벨이면 겹치는 무리의 맨 위 점은 위, 맨 아래 점은 아래, 사이 점은 오른쪽."""
    out = {}
    pts = sorted(pts, key=lambda z: z[1])
    groups = []
    for j, q in enumerate(pts):
        if j and q[1] - pts[j - 1][1] < gap:
            groups[-1].append(q)
        else:
            groups.append([q])
    for g in groups:
        if last_only:
            ps = [y for _, y in g]
            for j in range(1, len(ps)):
                ps[j] = max(ps[j], ps[j - 1] + gap)
            sh = sum(ps[j] - g[j][1] for j in range(len(g))) / len(g)
            for j, (k, y) in enumerate(g):
                out[k] = (ps[j] - sh, "center", "left")
            continue
        if len(g) == 1:
            out[g[0][0]] = (None, "bottom", "center")
            continue
        out[g[-1][0]] = (None, "bottom", "center")
        out[g[0][0]] = ("below", "top", "center")
        mid = g[1:-1]
        ps = [y for _, y in mid]
        for j in range(1, len(ps)):
            ps[j] = max(ps[j], ps[j - 1] + gap)
        sh = (sum(ps[j] - mid[j][1] for j in range(len(mid))) / len(mid)) if mid else 0
        for j, (k, y) in enumerate(mid):
            out[k] = (ps[j] - sh, "center", "left")
    return out


def main(spec_path, out_path):
    sp = json.load(open(spec_path, encoding="utf-8"))
    for p in find_fonts():
        fm.fontManager.addfont(p)
    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 9})
    n, x, series = sp["n"], sp["x"], sp["series"]
    H = sp["orient"] == "h"
    W = 16 / 2.54
    # 세로 막대는 범주가 많아도 3.4in까지만(2026-11-25 — 24개월이면 8.2in로 길쭉해졌다). 가로 막대는 전처럼 범주 수에 비례
    h_in = sp.get("heightIn") or (round(1.0 + 0.3 * n, 2) if H else min(3.4, round(1.0 + 0.3 * n, 2)))
    top = sp.get("legendTop") or (round(1 - 0.3 / h_in, 3) if sp["legend"] else 1.0)
    amax = sp["axisMax"]
    # 값 축 아래 끝: 음수가 있으면 axisMin까지(2026-11-25 — 0으로 고정해 음수 막대가 아예 안 보이고 숫자만 축 밑에 떠 있었다)
    amin = min(0, sp.get("axisMin") or 0) if not sp.get("stacked") else 0
    if amin < 0:  # 음수 막대 끝 바깥 숫자 자리
        amin -= (amax - amin) * 0.12
    off = sp.get("labelOffset")
    if off is None:
        off = amax * 0.01
    kind = sp.get("kind", "bar")
    if kind == "butterfly":
        return draw_butterfly(sp, out_path, W)
    if kind in ("line", "area", "combo"):
        return draw_xy(sp, out_path, W, n, x, series)
    if kind == "pie":
        return draw_pie(sp, out_path, W, n, x, series)
    fig, ax = plt.subplots(figsize=(W, h_in))
    bar = ax.barh if H else ax.bar
    kw = "height" if H else "width"
    cum = [0.0] * n
    tops = []  # 누적 막대 조각의 위 경계(계열선용)
    ns = len(series)
    grouped = not sp["stacked"] and ns > 1  # 묶은 막대: 범주마다 계열을 나란히(폭 0.8을 계열 수로 나눔)
    bw = 0.8 / ns if grouped else 0.6
    # 그림 영역 대략 크기(인치)와 값 1당 인치 — 얇은 누적 조각·좁은 막대 판정용
    plot_w = W - 0.9
    plot_h = max(0.6, h_in - (0.55 if sp["legend"] else 0.3))
    per_val = (plot_w if H else plot_h) / (amax or 1)
    # 묶은 세로 막대: 숫자가 막대 폭보다 넓으면 세워(90°) 달고 값 축을 늘린다(PowerPoint 차트 rotateIfCrowded와 같은 규칙)
    rot = False
    if grouped and not H:
        bar_in = plot_w / max(1, n) * bw
        widest = max([label_w(fmt(v, sp["seriesFmts"][k][i]) if "seriesFmts" in sp else fmt(v, sp["labelFormat"]), 9) for k, s_ in enumerate(series) for i, v in enumerate(s_["data"]) if v is not None] or [0])
        if widest > bar_in * 1.05:
            rot = True
            peak = max([v for s_ in series for v in s_["data"] if v is not None] or [0])
            room = 0.95 - (widest + 0.12) / plot_h
            if peak > 0 and room > 0.35 and amax < peak / room:
                amax = peak / room
    for k, s in enumerate(series):
        vals = [v or 0 for v in s["data"]]
        colors = ["#" + c for c in sp["barColors"][k]]
        pos = [i + (k - (ns - 1) / 2) * bw for i in range(n)] if grouped else x
        if sp["stacked"]:
            bar(x, vals, **{kw: 0.6, ("left" if H else "bottom"): cum}, color=colors)
        else:
            bar(pos, vals, **{kw: bw}, color=colors)
        for i, v in enumerate(s["data"]):
            if v is None:
                continue
            p_ = pos[i] if grouped else i
            if sp["stacked"]:
                c = cum[i] + v / 2
                t = fmt(v, sp["innerFormat"])
                # 조각이 숫자보다 얇으면 숫자를 빼고(합계는 남음), 숫자 색은 조각 색에 따라 흰색·진한 회색
                # 막대 폭(가로 막대는 두께)보다 숫자가 넓어도 뺀다 — 2026-11-25 범주 13개 누적 막대에서 30,621이 "0,62"로 잘림
                slot_in = (plot_h if H else plot_w) / max(1, n) * 0.6
                if (v * per_val) < ((label_w(t, 7.6) + 0.04) if H else 0.15) or (0.15 if H else label_w(t, 7.6) + 0.04) > slot_in:
                    continue
                ax.text(*((c, i) if H else (i, c)), t, ha="center", va="center", color=ink_on(colors[i]), fontweight="bold", fontsize=7.6)
            else:
                t = fmt(v, sp["seriesFmts"][k][i]) if "seriesFmts" in sp else fmt(v, sp["labelFormats"].get(str(i), sp["labelFormat"]))
                neg = v < 0  # 음수 막대는 숫자를 막대 끝 바깥(아래·왼쪽)에(2026-11-25)
                if H:
                    ax.text(v - off if neg else v + off, p_, t, va="center", ha="right" if neg else "left", color=colors[i], fontweight="bold")
                elif rot:
                    ax.text(p_, v - off if neg else v + off, t, ha="center", va="top" if neg else "bottom", rotation=90, color=colors[i], fontweight="bold")
                else:
                    ax.text(p_, v - off if neg else v + off, t, ha="center", va="top" if neg else "bottom", color=colors[i], fontweight="bold")
        if sp["stacked"]:
            cum = [a + (b or 0) for a, b in zip(cum, s["data"])]
            tops.append(list(cum))
    # 누적 막대 계열선: 막대 사이를 조각 경계끼리 가는 회색 선으로 잇는다(엑셀 '계열선'과 같음, 명세 series_lines: false면 끔 — 2026-11-28)
    if sp["stacked"] and sp.get("seriesLines", True) and n > 1:
        for tp in tops:
            for i in range(n - 1):
                a_, b_ = [i + 0.3, i + 0.7], [tp[i], tp[i + 1]]
                ax.plot(*((b_, a_) if H else (a_, b_)), color="#7F7F7F", lw=0.7, zorder=1.5, solid_capstyle="butt")
    tot_txt = []
    if sp["stacked"] and sp["showTotal"]:
        for i, t in enumerate(sp["totals"]):
            if H:
                ax.text(t + off, i, fmt(t, sp["totalFormat"]), ha="left", va="center", color="#" + sp["totalColor"], fontweight="bold")
            else:
                tot_txt.append(ax.text(i, t + off, fmt(t, sp["totalFormat"]), ha="center", va="bottom", color="#" + sp["totalColor"], fontweight="bold"))
    if grouped:  # 숫자 위치로 그렸으므로 범주 이름을 눈금에 단다
        (ax.set_yticks if H else ax.set_xticks)(list(range(n)))
        (ax.set_yticklabels if H else ax.set_xticklabels)(x)
    if H:
        ax.invert_yaxis(); ax.set_xlim(amin, amax)
        for s_ in ["top", "right", "left"]:
            ax.spines[s_].set_visible(False)
        ax.xaxis.grid(True, **GRID_KW); ax.tick_params(axis="y", length=0)
        if sp["axisTitle"]:
            ax.set_xlabel(sp["axisTitle"])
    else:
        ax.set_ylim(amin, amax)
        if amin < 0:
            ax.axhline(0, color="#BFBFBF", lw=0.8, zorder=1)
        for s_ in ["top", "right", "left"]:
            ax.spines[s_].set_visible(False)
        ax.yaxis.grid(True, **GRID_KW); ax.tick_params(axis="x", length=0)
        # 범주 이름이 칸보다 넓으면(“충북전남광주대구”처럼 붙던 것) 그 이름만 두 줄로 나누고(띄어쓰기·가운뎃점, 없으면 가운데),
        # 그래도 넓으면 글자를 8pt로, 그래도 넓으면 30° 기울인다
        slot = plot_w / max(1, n)
        lim = slot * 0.92
        def wid(c):
            return max(label_w(ln, 9) for ln in str(c).split("\n"))
        def split2(c):
            c = str(c)
            # 날짜·숫자 이름("2024.01")은 나누지 않는다("2024\n.01"로 깨졌다) — 범주가 많으면(13개 이상) 나누지 않고 기울이기·건너뛰기에 맡긴다(2026-11-25)
            if "\n" in c or label_w(c, 9) <= lim or n > 12 or all(ch in "0123456789.-/ " for ch in c):
                return c
            for sep in (" ", "·", "/"):
                if sep in c:
                    k = min((i for i, ch in enumerate(c) if ch == sep), key=lambda i: abs(i - len(c) / 2))
                    return c[:k + (1 if sep != " " else 0)].rstrip() + "\n" + c[k + 1:].lstrip()
            h = (len(c) + 1) // 2
            return c[:h] + "\n" + c[h:]
        if max([wid(c) for c in x] or [0]) > lim:
            labs = [split2(c) for c in x]
            ax.set_xticks(list(range(n)))
            ax.set_xticklabels(labs)
            w2 = max([wid(c) for c in labs] or [0])
            if w2 > lim:
                if w2 * 8 / 9 <= lim:
                    ax.tick_params(axis="x", labelsize=8)
                else:
                    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", rotation_mode="anchor")
        if sp["axisTitle"]:
            ax.set_ylabel(sp["axisTitle"])
    # 값 축 눈금: 천 단위 쉼표(꺾은선·혼합의 style_val_axis와 같은 규칙 — 2026-11-24, 막대만 쉼표가 빠져 "2500"으로 나왔다)
    vfmt = (lambda v, _: f"{v:,.1f}") if amax < 10 else (lambda v, _: f"{v:,.0f}")
    (ax.xaxis if H else ax.yaxis).set_major_formatter(matplotlib.ticker.FuncFormatter(vfmt))
    ax.set_axisbelow(True)
    if sp["legend"]:
        hs = [Patch(color="#" + l["color"], label=l["text"]) if l["color"] else Line2D([], [], linestyle="none", label="(" + l["text"] + ")") for l in sp["legend"]]
        # 한 줄이 그림 폭을 넘으면(긴 이름 여러 개) 열 수를 줄여 여러 줄로 — 한 줄로 두면 양 끝이 잘렸다(2026-11-26)
        nc = len(hs)
        leg = fig.legend(handles=hs, loc="upper center", ncol=nc, frameon=False, bbox_to_anchor=(0.5, 1.0))
        rend = fig.canvas.get_renderer()
        while nc > 1 and leg.get_window_extent(rend).width > fig.bbox.width * 0.98:
            nc -= 1
            leg.remove()
            leg = fig.legend(handles=hs, loc="upper center", ncol=nc, frameon=False, bbox_to_anchor=(0.5, 1.0))
        rows = -(-len(hs) // nc)
        if rows > 1:  # matplotlib은 세로(열)부터 채우므로, 읽는 순서가 가로(행)로 이어지게 다시 놓는다
            leg.remove()
            hs2 = [hs[r * nc + c] for c in range(nc) for r in range(rows) if r * nc + c < len(hs)]
            leg = fig.legend(handles=hs2, loc="upper center", ncol=nc, frameon=False, bbox_to_anchor=(0.5, 1.0))
        if rows > 1 and not sp.get("legendTop"):
            top = round(top - (rows - 1) * 0.2 / h_in, 3)
        fig._tl_rect = (0, 0, 1, top); fig.tight_layout(rect=fig._tl_rect)
    else:
        fig.tight_layout()
    # 누적 막대 합계 숫자가 이웃 합계와 붙으면(범주가 많을 때 — 2026-11-25 범주 13개에서 12,169·10,770이 겹침)
    # 배치가 끝난 뒤 실제 글자 상자를 재서 겹치지 않을 때까지 함께 줄인다(하한 7pt)
    if tot_txt:
        fig.canvas.draw(); rend = fig.canvas.get_renderer()
        while tot_txt[0].get_fontsize() > 7:
            bx = [tt.get_window_extent(rend) for tt in tot_txt]
            if not any(bx[j].overlaps(bx[j + 1]) for j in range(len(bx) - 1)):
                break
            for tt in tot_txt:
                tt.set_fontsize(tt.get_fontsize() - 0.5)
    # 점검: 라벨이 그림 밖으로 나가거나 라벨끼리 겹치지 않는지(겹치면 경고만 — 그림은 만든다)
    finish(fig, [ax], out_path)


def draw_butterfly(sp, out_path, W):
    """양쪽 가로 막대(lib/butterfly.js와 같은 모양): 가운데 항목 이름, 왼쪽·오른쪽 막대, 막대 가운데 흰 숫자(짧으면 바깥 계열 색)."""
    x, L, R = sp["x"], sp["left"], sp["right"]
    n = len(x)
    h_in = sp.get("heightIn") or round(1.1 + 0.42 * n, 2)
    fig, ax = plt.subplots(figsize=(W, h_in))
    M = max([v for v in L["data"] + R["data"] if v is not None] or [1])
    name_w = max(label_w(t, 10) for t in x) + 0.25
    plot_w = W - 0.4
    frac = min(0.42, max(0.1, name_w / plot_w))
    G = 2 * M * 1.08 * frac / (1 - frac) / 2  # 가운데 반쪽 폭(값 단위)
    unit_in = plot_w / (2 * (M * 1.08 + G))
    ys = list(range(n))
    def side(d, sign, color):
        for i, v in enumerate(d["data"]):
            if v is None:
                continue
            ax.barh(i, sign * v, left=sign * G, height=0.62, color="#" + color)
            t = fmt(v, sp["labelFormat"])
            end = sign * (G + v)
            if v * unit_in >= label_w(t, 9) + 0.1:  # 막대 가운데(2026-11-21 사용자 결정)
                ax.text(sign * (G + v / 2), i, t, ha="center", va="center", color=ink_on(color), fontsize=9, fontweight="bold")
            else:
                ax.text(end + sign * M * 0.015, i, t, ha="left" if sign > 0 else "right", va="center", color="#" + color, fontsize=9, fontweight="bold")
    side(L, -1, L["color"]); side(R, 1, R["color"])
    for i, t in enumerate(x):
        ax.text(0, i, t, ha="center", va="center", fontsize=10, fontweight="bold", color="#262626")
    lim = (M * 1.08 + G)
    ax.set_xlim(-lim, lim); ax.set_ylim(n - 0.5, -0.5)
    ax.axis("off")
    hs = [Patch(color="#" + L["color"], label=L["name"]), Patch(color="#" + R["color"], label=R["name"])]
    fig.legend(handles=hs, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0, 1, round(1 - 0.3 / h_in, 3)))
    finish(fig, [ax], out_path)


def finish(fig, axes, out_path):
    """겹침 정리(chart_declutter — 차트 서버와 같은 코드: 축 이름 줄이기→기울이기→건너뛰기, 숫자 줄이기→세우기→생략) 뒤
    점검: 라벨이 그림 밖으로 나가거나 라벨끼리 겹치지 않는지(겹치면 경고만 — 그림은 만든다)"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import chart_declutter as dc
    tok = dc.NOTES.set([])
    dc.run(fig)
    notes = dc.NOTES.get()
    dc.NOTES.reset(tok)
    rect = getattr(fig, "_tl_rect", None)
    if notes:  # 기울인 이름 등으로 늘어난 자리를 다시 잡는다
        fig.tight_layout(rect=rect) if rect else fig.tight_layout()
    fig.canvas.draw()
    rend = fig.canvas.get_renderer(); fb = fig.bbox
    texts = [t for a in axes for t in a.texts if t.get_text() and t.get_visible()]  # 정리 단계가 숨긴 숫자는 점검에서 뺀다(2026-11-26)
    boxes = [t.get_window_extent(rend) for t in texts]
    issues = []
    for i, b in enumerate(boxes):
        if b.x0 < fb.x0 - 0.5 or b.x1 > fb.x1 + 0.5 or b.y0 < fb.y0 - 0.5 or b.y1 > fb.y1 + 0.5:
            issues.append(f"라벨 '{texts[i].get_text()}'이 그림 밖으로 나감")
        for j in range(i + 1, len(boxes)):
            if b.overlaps(boxes[j]):
                issues.append(f"라벨 '{texts[i].get_text()}'·'{texts[j].get_text()}'이 겹침")
    fig.savefig(out_path, dpi=220)
    plt.close(fig)
    print(json.dumps({"out": out_path, "issues": issues, "notes": notes}, ensure_ascii=False))


def legend_top(fig, sp, h_in):
    top = sp.get("legendTop") or (round(1 - 0.3 / h_in, 3) if sp["legend"] else 1.0)
    if sp["legend"]:
        hs = [Patch(color="#" + l["color"], label=l["text"]) if l["color"] else Line2D([], [], linestyle="none", label="(" + l["text"] + ")") for l in sp["legend"]]
        # 한 줄이 그림 폭을 넘으면(긴 이름 여러 개) 열 수를 줄여 여러 줄로 — 한 줄로 두면 양 끝이 잘렸다(2026-11-26)
        nc = len(hs)
        leg = fig.legend(handles=hs, loc="upper center", ncol=nc, frameon=False, bbox_to_anchor=(0.5, 1.0))
        rend = fig.canvas.get_renderer()
        while nc > 1 and leg.get_window_extent(rend).width > fig.bbox.width * 0.98:
            nc -= 1
            leg.remove()
            leg = fig.legend(handles=hs, loc="upper center", ncol=nc, frameon=False, bbox_to_anchor=(0.5, 1.0))
        rows = -(-len(hs) // nc)
        if rows > 1:  # matplotlib은 세로(열)부터 채우므로, 읽는 순서가 가로(행)로 이어지게 다시 놓는다
            leg.remove()
            hs2 = [hs[r * nc + c] for c in range(nc) for r in range(rows) if r * nc + c < len(hs)]
            leg = fig.legend(handles=hs2, loc="upper center", ncol=nc, frameon=False, bbox_to_anchor=(0.5, 1.0))
        if rows > 1 and not sp.get("legendTop"):
            top = round(top - (rows - 1) * 0.2 / h_in, 3)
        fig._tl_rect = (0, 0, 1, top); fig.tight_layout(rect=fig._tl_rect)
    else:
        fig.tight_layout()


def style_val_axis(ax, lo, hi, title):
    ax.set_ylim(lo, hi)
    for s_ in ["top", "right", "left"]:
        ax.spines[s_].set_visible(False)
    ax.yaxis.grid(True, **GRID_KW); ax.tick_params(axis="x", length=0)
    if title:
        ax.set_ylabel(title)
    if hi - lo < 10:
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.1f}"))
    else:
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_axisbelow(True)


def draw_xy(sp, out_path, W, n, x, series):
    """꺾은선·영역·혼합(막대+꺾은선, 보조축) — Excel 차트(lib/xlsx-bar.js)와 같은 색·라벨 규칙"""
    h_in = sp.get("heightIn") or 2.6
    fig, ax = plt.subplots(figsize=(W, h_in))
    kind = sp["kind"]; types = sp["seriesType"]; axes_ = sp["seriesAxis"]; mask = sp["labelMask"]; sf = sp["seriesFmts"]
    ax2 = ax.twinx() if sp.get("comboAxis") else None
    lo, hi = sp["axisMin"], sp["axisMax"]
    off = sp.get("labelOffset")
    if off is None:
        off = (hi - lo) * 0.02
    pos = list(range(n))
    # 꺾은선 숫자 라벨 겹침 풀기 — 같은 축의 꺾은선끼리, 같은 x에서(라벨 한 줄 높이 ≈ 9pt × 1.35)
    line_place = {}
    plot_h = max(0.8, h_in - 0.75)
    for axis_id in (0, 1):
        ks = [k for k, t in enumerate(types) if t == "line" and (axes_[k] if ax2 is not None else 0) == axis_id]
        if len(ks) < 2:
            continue
        a_lo, a_hi = (lo, hi) if axis_id == 0 else (sp["axis2Min"], sp["axis2Max"])
        gap = (9 * 1.35 / 72 + 0.02) / plot_h * (a_hi - a_lo)
        for i in range(n):
            pts = [(k, series[k]["data"][i]) for k in ks if series[k]["data"][i] is not None and mask[k][i]]
            if len(pts) < 2:
                continue
            last_only = all(all(bool(mask[k][j]) == (j == n - 1) for j in range(n)) for k, _ in pts)
            for k, pl in spread_line_labels(pts, gap, last_only).items():
                line_place[(k, i)] = pl
    bars = [k for k, t in enumerate(types) if t == "bar"]
    nb = len(bars); bw = 0.8 / nb if nb > 1 else 0.6
    # 혼합 차트 막대 숫자가 범주 칸보다 넓으면(월 24개 등) 옆 숫자와 붙는다 — 칸에 맞게 글자를 줄이고(6.5pt까지), 그래도 넓으면 세운다(2026-11-25)
    bar_fs, bar_rot = 9, False
    if bars and kind == "combo":
        slot = (W - 0.9 - (0.6 if ax2 is not None else 0)) / max(1, n) * (0.92 if nb == 1 else bw)
        mw = max([label_w(fmt(v, sf[k][i]), 9) for k in bars for i, v in enumerate(series[k]["data"]) if v is not None and mask[k][i]] or [0])
        if mw > slot:
            bar_fs = max(6.5, 9 * slot / mw)
            bar_rot = mw * bar_fs / 9 > slot
            if bar_rot:
                bar_fs = 9
    cum = [0.0] * n
    for k, s in enumerate(series):
        c = "#" + s["color"]; vals = s["data"]
        a = ax2 if (ax2 is not None and axes_[k] == 1) else ax
        aoff = off if a is ax else (sp["axis2Max"] - sp["axis2Min"]) * 0.02
        if types[k] == "bar":
            j = bars.index(k)
            px = [i + (j - (nb - 1) / 2) * bw for i in pos] if nb > 1 else pos
            colors = ["#" + cc for cc in sp["barColors"][k]]
            a.bar(px, [v or 0 for v in vals], width=bw, color=colors, zorder=2)
            for i, v in enumerate(vals):
                if v is not None and mask[k][i]:
                    a.text(px[i], v + aoff, fmt(v, sf[k][i]), ha="center", va="bottom", color=colors[i], fontweight="bold", zorder=5,
                           fontsize=bar_fs, rotation=90 if bar_rot else 0)
            continue
        idx = [i for i, v in enumerate(vals) if v is not None]
        ys = [vals[i] for i in idx]
        if types[k] == "area":
            if sp["stacked"]:
                base = [cum[i] for i in idx]; top_ = [cum[i] + vals[i] for i in idx]
                a.fill_between(idx, base, top_, color=c, alpha=0.85, linewidth=0, zorder=2)
                a.plot(idx, top_, color=c, lw=1.5, zorder=3)
                for i in idx:
                    if mask[k][i]:
                        # 양 끝 점의 라벨은 영역 안쪽으로 붙인다(가운데 정렬이면 절반이 영역 밖 흰 바탕에 걸려 안 보임)
                        ha = "left" if i == idx[0] and len(idx) > 1 else "right" if i == idx[-1] and len(idx) > 1 else "center"
                        a.text(i + (0.04 if ha == "left" else -0.04 if ha == "right" else 0), cum[i] + vals[i] / 2, fmt(vals[i], sf[k][i]), ha=ha, va="center", color="white", fontweight="bold", fontsize=7.3, zorder=5)
                for i in idx:
                    cum[i] += vals[i]
            else:
                a.fill_between(idx, [0] * len(idx), ys, color=c, alpha=0.35, linewidth=0, zorder=2)
                a.plot(idx, ys, color=c, lw=1.5, zorder=3)
                for i in idx:
                    if mask[k][i]:
                        a.text(i, vals[i] + aoff * 1.6, fmt(vals[i], sf[k][i]), ha="center", va="bottom", color=c, fontweight="bold", zorder=5)
            continue
        a.plot(idx, ys, color=c, lw=2.25, marker="o", ms=5, mfc=c, mec="white", mew=0.8, zorder=4, solid_capstyle="round")
        for i in idx:
            if mask[k][i]:
                place = line_place.get((k, i))
                if place is None:
                    a.text(i, vals[i] + aoff * 1.6, fmt(vals[i], sf[k][i]), ha="center", va="bottom", color=c, fontweight="bold", zorder=5)
                elif place[0] == "below":
                    a.text(i, vals[i] - aoff * 1.6, fmt(vals[i], sf[k][i]), ha="center", va="top", color=c, fontweight="bold", zorder=5)
                elif place[0] is None:
                    a.text(i, vals[i] + aoff * 1.6, fmt(vals[i], sf[k][i]), ha="center", va="bottom", color=c, fontweight="bold", zorder=5)
                else:
                    a.text(i + 0.07, place[0], fmt(vals[i], sf[k][i]), ha="left", va="center", color=c, fontweight="bold", zorder=5)
    ax.set_xticks(pos); ax.set_xticklabels(x)
    # 범주 이름이 칸보다 넓으면(월 24개를 "24.11"처럼 한 줄로 쓴 경우 등) 30도 기울인다 — 막대 차트와 같은 처리(2026-11-25)
    slot_x = (W - 0.9 - (0.6 if ax2 is not None else 0)) / max(1, n)
    rows_ = [str(c).split("\n") for c in x]
    crowded = any((label_w(a_[j], 9) + label_w(b_[j], 9)) / 2 > slot_x * 0.95
                  for a_, b_ in zip(rows_, rows_[1:]) for j in range(min(len(a_), len(b_))))
    if crowded:
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right", rotation_mode="anchor")
    # 끝 점 오른쪽 라벨이 있으면 오른쪽 여백을 조금 늘린다
    ax.set_xlim(-0.5, n - 0.5 + (0.25 if any(pl[2] == "left" and i == n - 1 for (k, i), pl in line_place.items()) else 0))
    style_val_axis(ax, lo, hi, sp["axisTitle"])
    if ax2 is not None:
        ax2.set_ylim(sp["axis2Min"], sp["axis2Max"])
        for s_ in ["top", "left"]:
            ax2.spines[s_].set_visible(False)
        ax2.spines["right"].set_color("#BFBFBF")
        if sp.get("axis2Title"):
            ax2.set_ylabel(sp["axis2Title"])
        r2 = sp["axis2Max"] - sp["axis2Min"]
        ax2.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter((lambda v, _: f"{v:,.1f}") if r2 < 10 else (lambda v, _: f"{v:,.0f}")))
        if sp.get("axis2HideNeg"):
            # 선을 막대 위 띠로 올리려고 보조축 아래를 음수로 내린 경우 — 눈금은 0 이상만(Excel·PowerPoint 형식 '#,##0;;0'과 같음)
            st_ = sp.get("axis2Step") or (sp["axis2Max"] / 4)
            ax2.set_yticks([i * st_ for i in range(int(round(sp["axis2Max"] / st_)) + 1)])
            ax2.set_ylim(sp["axis2Min"], sp["axis2Max"])
    legend_top(fig, sp, h_in)
    if ax2 is not None and bars:
        lift_axis2(fig, ax, ax2, sp, [k for k, t in enumerate(types) if t != "bar" and axes_[k] == 1], series)
    finish(fig, [ax] + ([ax2] if ax2 is not None else []), out_path)


def lift_axis2(fig, ax, ax2, sp, ks, series):
    """혼합 차트: 막대 숫자를 세우거나 줄인 뒤 실제 높이를 재서, 보조축 선의 가장 낮은 점이 막대·숫자 띠 위에 오게 한다(2026-11-25 —
    chart-spec.js의 '막대 높이 + 10%'는 세운 숫자 높이를 몰라 24개월 혼합에서 선이 세운 숫자를 가로질렀다). 차트 서버 1.4.0과 같은 식."""
    vals = [v for k in ks for v in series[k]["data"] if v is not None]
    if not vals:
        return
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import chart_declutter as dc
    rect = getattr(fig, "_tl_rect", None)
    dc.run(fig)
    fig.tight_layout(rect=rect) if rect else fig.tight_layout()
    fig.canvas.draw()
    rr = fig.canvas.get_renderer()
    tops = [t.get_window_extent(rr).y1 for t in ax.texts if t.get_visible() and t.get_text().strip()] + [p.get_window_extent(rr).y1 for p in ax.patches]
    if not tops:
        return
    f = min(0.85, (max(tops) - ax.bbox.y0) / ax.bbox.height + 0.06)
    lo2, hi2 = ax2.get_ylim()
    mn = min(vals)
    need_lo = (mn - f * hi2) / (1 - f)
    if need_lo < lo2:
        ticks = [t for t in ax2.get_yticks() if t >= 0] if sp.get("axis2HideNeg") else None
        ax2.set_ylim(need_lo, hi2)
        if ticks is not None:
            ax2.set_yticks([t for t in ticks if t <= hi2])
            ax2.set_ylim(need_lo, hi2)


PIE_FS, PIE_FS_RING, PIE_FS_OUT = 11.5, 9.5, 10  # 한 줄 비율, 고리 안 두 줄(값/(비율)), 바깥 — 원·도넛 조각 라벨(기본 9pt는 원에 비해 작음 — 2026-11-13 사용자 의견)


def draw_pie(sp, out_path, W, n, x, series):
    """원·도넛 — 12시 방향에서 시계 방향(Excel firstSliceAng 0과 같음), 조각 사이 흰 선. 원은 바깥에 조각 색 굵은 라벨, 도넛은 고리 안 흰 라벨"""
    h_in = sp.get("heightIn") or 2.8
    fig, ax = plt.subplots(figsize=(W, h_in))
    vals = series[0]["data"]; colors = ["#" + c for c in sp["barColors"][0]]
    hole = sp.get("hole") or 0
    wp = {"edgecolor": "white", "linewidth": 1.5}
    if hole:
        wp["width"] = 1 - hole
    wedges, _ = ax.pie(vals, colors=colors, startangle=90, counterclock=False, wedgeprops=wp)
    import math
    ax.set_aspect("equal"); ax.apply_aspect()  # 겹침 판정(화면 좌표)이 최종 모양과 같게 먼저 맞춘다
    out_boxes, ring_boxes = [], []
    rend = fig.canvas.get_renderer()

    def place_out(i, ang, t):
        # 바깥에 이끌선과 함께 — 앞서 단 바깥 라벨과 겹치면 원 둘레 방향(시계 방향)으로 민다
        r0, r = 1.0, 1.18
        ax.plot([r0 * math.cos(ang), r * math.cos(ang)], [r0 * math.sin(ang), r * math.sin(ang)], color="#7F7F7F", lw=0.9)
        cx, cy = (r + 0.03) * math.cos(ang), (r + 0.03) * math.sin(ang)
        tx = ax.text(cx, cy, t, ha="left" if cx > 0.05 else "right" if cx < -0.05 else "center", va="center", color="#404040", fontweight="bold", fontsize=PIE_FS_OUT)
        for _ in range(20):
            bb = tx.get_window_extent(rend).expanded(1.05, 1.15)
            if not any(bb.overlaps(o) for o in out_boxes):
                break
            cx, cy = cx + 0.09 * math.sin(ang), cy - 0.09 * math.cos(ang)
            tx.set_position((cx, cy))
        out_boxes.append(tx.get_window_extent(rend))

    for i, w in enumerate(wedges):
        t = sp["pieTexts"][i] if sp["pieTexts"] else ""
        if not t:
            continue
        ang = math.radians((w.theta1 + w.theta2) / 2)
        out = bool(sp.get("pieOut") and sp["pieOut"][i])
        if not hole and sp.get("pieInside") and not out:
            # 구멍 없는 원(비율만): 조각 안(반지름 0.62)에 비율
            ax.text(0.62 * math.cos(ang), 0.62 * math.sin(ang), t, ha="center", va="center", color=ink_on(colors[i]), fontweight="bold", fontsize=PIE_FS)
            continue
        if hole and not out:
            # 고리 안 두 줄(값 / (비율)), 글자 색은 조각 색에 따라(계정 변환기 inkOn과 같음)
            r = 1 - (1 - hole) / 2
            t2 = sp["pieLines"][i] if sp.get("pieLines") else t
            tr = ax.text(r * math.cos(ang), r * math.sin(ang), t2, ha="center", va="center", color=ink_on(colors[i]), fontweight="bold", fontsize=PIE_FS_RING if "\n" in t2 else PIE_FS, linespacing=1.25)
            # 이웃 조각의 고리 안 라벨과 겹치면(작은 조각이 나란히 있을 때) 바깥 이끌선 라벨로 옮긴다(2026-11-26)
            bb = tr.get_window_extent(rend).expanded(1.04, 1.04)
            if any(bb.overlaps(o) for o in ring_boxes):
                tr.remove()
                place_out(i, ang, t)
            else:
                ring_boxes.append(bb)
        elif (hole or sp.get("pieInside")) and out:
            # 얇은 조각(6% 미만)은 바깥에 이끌선과 함께
            place_out(i, ang, t)
        else:
            r = 1.12; cx, cy = r * math.cos(ang), r * math.sin(ang)
            ax.text(cx, cy, t, ha="left" if cx > 0.05 else "right" if cx < -0.05 else "center", va="center", color=colors[i], fontweight="bold", fontsize=PIE_FS_OUT)
    # 가운데 작은 원에 전체 합계와 (100%)
    cl = sp.get("center")
    if hole and cl:
        from matplotlib.patches import Circle
        ax.add_patch(Circle((0, 0), hole * 0.9, facecolor="white", edgecolor="#D9E2F3", lw=1.2, zorder=5))
        t1 = ax.text(0, 0.07, cl[0], ha="center", va="center", color="#1F3864", fontweight="bold", fontsize=12, zorder=6)
        t2 = ax.text(0, -0.13, cl[1], ha="center", va="center", color="#595959", fontsize=8.5, zorder=6)
        # 합계 글자가 가운데 원 폭의 80%를 넘지 않게 줄인다
        rend = fig.canvas.get_renderer()
        p0, p1 = ax.transData.transform((-hole * 0.9, 0)), ax.transData.transform((hole * 0.9, 0))
        for _ in range(10):
            if t1.get_window_extent(rend).width <= (p1[0] - p0[0]) * 0.8 or t1.get_fontsize() <= 7:
                break
            t1.set_fontsize(t1.get_fontsize() - 1); t2.set_fontsize(max(6.5, t1.get_fontsize() * 0.7))
    ax.set_aspect("equal")
    legend_top(fig, sp, h_in)
    finish(fig, [ax], out_path)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
