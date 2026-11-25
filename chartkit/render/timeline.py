"""일정·연혁·개발 단계 — 간트·타임라인·신약 파이프라인."""
from __future__ import annotations

import datetime as dt

import matplotlib.dates as mdates
from matplotlib.patches import FancyBboxPatch

from .. import style as st
from ..core import Result, figure, legend_top, put_title, style_axes, to_png, top_for
from ..errors import ChartInputError, as_dict, as_list, as_number, need

DEFAULT_PHASES = ["후보물질", "전임상", "임상 1상", "임상 2상", "임상 3상", "허가 신청", "허가"]
PHASE_ALIASES = {
    "discovery": 0, "후보": 0, "탐색": 0, "후보물질": 0,
    "preclinical": 1, "전임상": 1, "비임상": 1,
    "phase1": 2, "p1": 2, "1상": 2, "임상1상": 2, "phasei": 2,
    "phase2": 3, "p2": 3, "2상": 3, "임상2상": 3, "phaseii": 3, "phase2a": 3, "phase2b": 3, "2a상": 3, "2b상": 3,
    "phase3": 4, "p3": 4, "3상": 4, "임상3상": 4, "phaseiii": 4,
    "nda": 5, "bla": 5, "filing": 5, "허가신청": 5, "신청": 5,
    "approved": 6, "허가": 6, "승인": 6, "출시": 6, "launch": 6,
}
EX_GANTT = [{"name": "IND 제출", "start": "2026-01-05", "end": "2026-02-20", "group": "규제"}]


def _d(v, where):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError as e:
        raise ChartInputError(f"{where}가 날짜(YYYY-MM-DD)가 아닙니다: {v!r}", example=EX_GANTT) from e


def _phase(v, phases, where):
    s = str(v).strip()
    if s in phases:
        return phases.index(s)
    key = s.lower().replace(" ", "").replace("-", "").replace("_", "")
    if phases == DEFAULT_PHASES and key in PHASE_ALIASES:
        return PHASE_ALIASES[key]
    if key.isdigit() and 0 <= int(key) < len(phases):
        return int(key)
    raise ChartInputError(f"{where}의 단계 '{s}'를 알 수 없습니다", hint=f"다음 중 하나로 넣으세요: {', '.join(phases)}")


def _date_axis(ax, d0, d1):
    span = (d1 - d0).days
    # 눈금 수를 그림 폭에 맞춘다(2026-11-24 — 7년 남짓한 간트에 6개월 눈금 17개가 붙어 "22.0923.03…"으로 겹침).
    # 보이는 범위(xlim — 오른쪽 기간 글 자리 포함)로 재서 눈금이 10개를 넘지 않는 가장 촘촘한 간격을 고르고, 1년 이상 간격이면 연도만 쓴다
    a, b = ax.get_xlim()
    months = max(1.0, (b - a) / 30.44)
    step = next((m for m in (1, 2, 3, 6, 12, 24, 36, 60) if months / m <= 10), 120)
    if step >= 12:
        ax.xaxis.set_major_locator(mdates.YearLocator(step // 12))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=step))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%y.%m" if span > 300 else "%-m월"))


def _gantt(args, o):
    title, sub = args.get("title"), args.get("subtitle")
    tasks = as_list(args.get("tasks"), "tasks")
    need(tasks, "tasks=[{name, start, end, group}]가 필요합니다", example=EX_GANTT)
    rows = []
    for i, t in enumerate(tasks):
        t = as_dict(t, f"tasks[{i}]")
        s = _d(t.get("start"), f"tasks[{i}].start")
        e = _d(t.get("end") or t.get("start"), f"tasks[{i}].end")
        need(e >= s, f"tasks[{i}]의 end가 start보다 앞섭니다", example=EX_GANTT)
        rows.append({"name": str(t.get("name", f"작업{i + 1}")), "s": s, "e": e, "g": t.get("group") or "", "p": as_number(t.get("progress"), "progress")})
    groups = []
    for r in rows:
        if r["g"] not in groups:
            groups.append(r["g"])
    pal = st.palette(len(groups), wide=True)
    gc = {g: pal[i] for i, g in enumerate(groups)}
    today = _d(o["today"], "options.today") if o.get("today") else None
    d0 = min(r["s"] for r in rows)
    d1 = max(r["e"] for r in rows)
    n = len(rows)
    with figure(max(2.0, 0.8 + 0.32 * n), o) as fig:
        top = top_for(fig, title, sub, o, len(groups) > 1 and any(groups))
        ax = fig.add_axes([0.2, 0.1, 0.77, top - 0.12])
        style_axes(ax, grid="x")
        for i, r in enumerate(rows):
            c = gc[r["g"]]
            if r["s"] == r["e"]:
                ax.scatter([mdates.date2num(r["s"])], [i], marker="D", s=60, color=c, zorder=3)
                ax.text(mdates.date2num(r["s"]) + 3, i, r["s"].strftime(" %m.%d"), va="center", fontsize=7.4, color=c)
            else:
                x0 = mdates.date2num(r["s"])
                w = mdates.date2num(r["e"]) - x0
                ax.barh(i, w, left=x0, height=0.56, color=c, alpha=0.35 if r["p"] is not None else 1, zorder=2)
                if r["p"] is not None:
                    ax.barh(i, w * max(0, min(1, r["p"])), left=x0, height=0.56, color=c, zorder=3)
        # 막대 오른쪽에 기간 글(2026-11-24 — 날짜가 없어 일정이 읽히지 않는다는 지적). 끄기 options.dates=false
        show_dates = str(o.get("dates", True)).lower() not in ("false", "0", "no")
        one_year = d0.year == d1.year
        dfmt = (lambda d: f"{d.month}/{d.day}") if one_year else (lambda d: d.strftime("%y.%m.%d").replace(".0", "."))
        if show_dates:
            for i, r in enumerate(rows):
                if r["s"] == r["e"]:
                    continue
                ax.text(mdates.date2num(r["e"]) + max(2, (d1 - d0).days * 0.008), i, f"{dfmt(r['s'])}~{dfmt(r['e'])}",
                        va="center", ha="left", fontsize=st.LABEL_SIZE, color="#404040", zorder=5)
            if one_year:
                ax.text(1.0, -0.13, f"{d0.year}년", transform=ax.transAxes, ha="right", va="top", fontsize=st.LABEL_SIZE, color="#7F7F7F")
        if today:
            ax.axvline(mdates.date2num(today), color=st.BAD, lw=1.2, ls="--", zorder=4)
            ax.text(mdates.date2num(today), 0.0, " 오늘", transform=ax.get_xaxis_transform(), color=st.BAD, fontsize=7.6, va="bottom", ha="left")
        ax.set_yticks(range(n), [r["name"] for r in rows])
        ax.invert_yaxis()
        pad = max(7, (d1 - d0).days * 0.03)
        right = pad * 2 + ((d1 - d0).days * (0.17 if one_year else 0.24) if show_dates else 0)
        ax.set_xlim(mdates.date2num(d0) - pad, mdates.date2num(d1) + right)
        _date_axis(ax, d0, d1)
        if len(groups) > 1 and any(groups):
            legend_top(fig, [(g, gc[g], "patch") for g in groups if g], title, sub, o)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["마름모: 시작일과 종료일이 같은 마일스톤"] if any(r["s"] == r["e"] for r in rows) else [],
                  table=(["작업", "그룹", "시작", "종료", "진척"], [[r["name"], r["g"], r["s"].isoformat(), r["e"].isoformat(), r["p"]] for r in rows]))


def _tl_lines(lab: str, n: int = 11) -> list[str]:
    """긴 사건 이름을 n자 안팎으로 줄 바꿈(띄어쓰기 자리 우선, 최대 3줄)."""
    out, cur = [], ""
    for w in lab.split():
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= n:
            cur += " " + w
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    lines = []
    for ln in out:
        while len(ln) > int(n * 1.4):
            lines.append(ln[:n])
            ln = ln[n:]
        lines.append(ln)
    if len(lines) > 3:
        lines = lines[:2] + [lines[2][: n - 1] + "…"]
    return lines or [""]


def _timeline(args, o):
    title, sub = args.get("title"), args.get("subtitle")
    evs = as_list(args.get("events"), "events")
    need(evs, "events=[{date, label}]가 필요합니다", example=[{"date": "2026-01-15", "label": "IND 승인"}])
    items = sorted([(_d(as_dict(e, f"events[{i}]").get("date"), f"events[{i}].date"), str(as_dict(e, "e").get("label", ""))) for i, e in enumerate(evs)])
    # 사건이 몰린 구간에서 이름표가 겹치지 않게(2026-11-24 — 카카오 연혁 14건이 2025.12~2026.08에 몰려 글자가 서로 덮임):
    # 이름표 폭을 실제 글꼴로 재서 위·아래와 단(최대 4단)을 고르고, 단이 늘면 그림 높이를 늘린다. 긴 이름은 11자 안팎으로 줄 바꿈
    with figure(2.4, o) as fig:
        w_in = fig.get_size_inches()[0]
        aw = 0.92 * w_in
        x = [mdates.date2num(d) for d, _ in items]
        pad = max(20, (x[-1] - x[0]) * 0.06)
        lo, hi = x[0] - pad * 1.6, x[-1] + pad * 1.6
        per_in = (hi - lo) / aw
        rend = fig.canvas.get_renderer()
        texts = []
        for d, lab in items:
            body = [d.strftime("%Y.%m")] + _tl_lines(lab)
            t = fig.text(0, 0, "\n".join(body), fontsize=st.LABEL_SIZE, fontweight="bold", linespacing=1.3)
            bb = t.get_window_extent(rend)
            t.remove()
            texts.append((body, bb.width / fig.dpi + 0.08, bb.height / fig.dpi))
        step = max(h for _, _, h in texts) + 0.12
        placed = {}  # (side, level) -> [(x0, x1)]
        slots, prev = [], -1
        for k, xx in enumerate(x):
            wl = texts[k][1]
            xi = (xx - lo) / per_in
            a, b = xi - wl / 2, xi + wl / 2
            s0 = -prev
            cands = [(s, lv) for lv in range(4) for s in (s0, -s0)]
            best = None
            for c in cands:
                if all(b <= p0 or a >= p1 for p0, p1 in placed.get(c, [])):
                    best = c
                    break
            if best is None:  # 4단 모두 막히면 겹침이 가장 적은 자리
                best = min(cands, key=lambda c: sum(max(0, min(b, p1) - max(a, p0)) for p0, p1 in placed.get(c, [])))
            placed.setdefault(best, []).append((a, b))
            slots.append(best)
            prev = best[0]
        n_up = 1 + max([lv for s, lv in slots if s > 0], default=-1)
        n_dn = 1 + max([lv for s, lv in slots if s < 0], default=-1)
        base = 0.2
        up_in = base + n_up * step if n_up else 0.15
        dn_in = base + n_dn * step if n_dn else 0.15
        plot_h = up_in + dn_in + 0.1
        fig.set_size_inches(w_in, max(2.4, plot_h + 0.35))
        top = top_for(fig, title, sub, o, False)
        h_in = fig.get_size_inches()[1]
        avail = (top - 0.04) * h_in
        bot = 0.04 + max(0.0, (avail - plot_h) / 2) / h_in
        ax = fig.add_axes([0.04, bot, 0.92, plot_h / h_in])
        ax.axis("off")
        ax.set_xlim(lo, hi)
        ax.set_ylim(-dn_in - 0.05, up_in + 0.05)
        ax.plot([x[0] - pad, x[-1] + pad], [0, 0], color=st.NAVY, lw=2.2, zorder=1)
        for k, ((d, lab), xx) in enumerate(zip(items, x)):
            side, lv = slots[k]
            y = side * (base + lv * step)
            ax.plot([xx, xx], [0, y], color=st.GRAY, lw=1, zorder=1)
            ax.scatter([xx], [0], s=70, color=st.ORANGE if k == len(items) - 1 else st.NAVY, zorder=3, edgecolor="white", lw=1.2)
            body = texts[k][0]
            txt = "\n".join(body) if side > 0 else "\n".join(body[1:] + body[:1])
            ax.text(xx, y, txt, ha="center", va="bottom" if side > 0 else "top", fontsize=st.LABEL_SIZE, color=st.INK,
                    linespacing=1.3, fontweight="bold", zorder=4,
                    bbox=dict(boxstyle="square,pad=0.15", facecolor="white", edgecolor="none"))
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, table=(["날짜", "내용"], [[d.isoformat(), lab] for d, lab in items]))


def _pipeline(args, o):
    title, sub = args.get("title"), args.get("subtitle")
    phases = [str(p) for p in as_list(args.get("phases"), "phases")] or DEFAULT_PHASES
    items = as_list(args.get("items"), "items")
    need(items, "items=[{name, indication, phase, group}]가 필요합니다", example=[{"name": "GV-001", "indication": "알츠하이머", "phase": "임상 2상"}])
    rows = []
    for i, it in enumerate(items):
        it = as_dict(it, f"items[{i}]")
        k = _phase(it.get("phase"), phases, f"items[{i}].phase")
        rows.append({"name": str(it.get("name", "")), "ind": str(it.get("indication") or ""), "k": k, "g": it.get("group") or "",
                     "p": as_number(it.get("progress"), "progress")})
    groups = []
    for r in rows:
        if r["g"] not in groups:
            groups.append(r["g"])
    pal = st.palette(len(groups), wide=True)
    gc = {g: pal[i] for i, g in enumerate(groups)}
    n, P = len(rows), len(phases)
    with figure(max(2.0, 0.9 + 0.38 * n), o) as fig:
        top = top_for(fig, title, sub, o, len(groups) > 1 and any(groups))
        ax = fig.add_axes([0.26, 0.04, 0.72, top - 0.12])
        ax.set_xlim(0, P)
        ax.set_ylim(n - 0.5, -0.9)
        for s_ in ax.spines.values():
            s_.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        for j, p in enumerate(phases):
            ax.text(j + 0.5, -0.75, p, ha="center", va="center", fontsize=7.8, color=st.INK2, fontweight="bold")
            if j:
                ax.axvline(j, zorder=0, **st.GRID_KW)
        for i, r in enumerate(rows):
            c = gc[r["g"]]
            # 진척은 단계 안 비율(0~1). 1보다 크면 %로 보고(40 → 0.4), 0~1로 자른다(1.4.0 — 큰 값이면 막대가 그림 밖 수만 픽셀로 뻗었다)
            p_ = r["p"]
            if p_ is not None and p_ > 1:
                p_ = p_ / 100
            end = r["k"] + (max(0.05, min(1.0, p_)) if p_ is not None else 0.85)
            ax.add_patch(FancyBboxPatch((0.05, i - 0.26), end - 0.05, 0.52, boxstyle="round,pad=0,rounding_size=0.18", facecolor=c, edgecolor="none", zorder=2))
            ax.text(-0.08, i, f"{r['name']}", ha="right", va="bottom", fontsize=st.FONT_SIZE, fontweight="bold", color=st.INK, transform=ax.transData, clip_on=False)
            ax.text(-0.08, i, r["ind"], ha="right", va="top", fontsize=7.6, color=st.MUTED, clip_on=False)
            ax.text(end - 0.08, i, phases[r["k"]], ha="right", va="center", fontsize=7.4, color=st.ink_on(c), fontweight="bold", zorder=3)
        if len(groups) > 1 and any(groups):
            legend_top(fig, [(g, gc[g], "patch") for g in groups if g], title, sub, o)
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, table=(["후보물질", "적응증", "단계", "그룹"], [[r["name"], r["ind"], phases[r["k"]], r["g"]] for r in rows]))


def draw(ct: str, args: dict, o: dict) -> Result:
    if ct == "gantt":
        return _gantt(args, o)
    if ct == "timeline":
        return _timeline(args, o)
    if ct == "pipeline":
        return _pipeline(args, o)
    raise ValueError(ct)
