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
    loc = mdates.MonthLocator(interval=1 if span <= 400 else (3 if span <= 1100 else 6))
    ax.xaxis.set_major_locator(loc)
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


def _timeline(args, o):
    title, sub = args.get("title"), args.get("subtitle")
    evs = as_list(args.get("events"), "events")
    need(evs, "events=[{date, label}]가 필요합니다", example=[{"date": "2026-01-15", "label": "IND 승인"}])
    items = sorted([(_d(as_dict(e, f"events[{i}]").get("date"), f"events[{i}].date"), str(as_dict(e, "e").get("label", ""))) for i, e in enumerate(evs)])
    d0, d1 = items[0][0], items[-1][0]
    with figure(2.4, o) as fig:
        top = top_for(fig, title, sub, o, False)
        ax = fig.add_axes([0.04, 0.1, 0.92, top - 0.12])
        ax.axis("off")
        x = [mdates.date2num(d) for d, _ in items]
        pad = max(20, (x[-1] - x[0]) * 0.06)
        ax.plot([x[0] - pad, x[-1] + pad], [0, 0], color=st.NAVY, lw=2.2, zorder=1)
        for k, ((d, lab), xx) in enumerate(zip(items, x)):
            up = 1 if k % 2 == 0 else -1
            ax.plot([xx, xx], [0, 0.55 * up], color=st.GRAY, lw=1, zorder=1)
            ax.scatter([xx], [0], s=70, color=st.ORANGE if k == len(items) - 1 else st.NAVY, zorder=3, edgecolor="white", lw=1.2)
            ax.text(xx, 0.6 * up, f"{d.strftime('%Y.%m')}\n{lab}" if up > 0 else f"{lab}\n{d.strftime('%Y.%m')}", ha="center",
                    va="bottom" if up > 0 else "top", fontsize=st.LABEL_SIZE, color=st.INK, linespacing=1.3,
                    fontweight="bold")
        ax.set_xlim(x[0] - pad * 1.6, x[-1] + pad * 1.6)
        ax.set_ylim(-1.4, 1.4)
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
            end = r["k"] + (r["p"] if r["p"] is not None else 0.85)
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
