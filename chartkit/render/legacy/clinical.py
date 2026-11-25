"""임상·약리 차트(matplotlib).

km(카플란-마이어) · forest(숲 그림) · change_from_baseline(기저치 대비 변화) · dose_response(용량-반응 4PL)
pk_curve(혈중농도-시간, AUC) · ae_comparison(이상사례 비교) · waterfall_plot(종양 반응) · swimmer(수영자 그림)
enrollment(환자 모집 현황) · consort(CONSORT 흐름도)

통계 계산은 자체 구현이며 tests/test_stats.py 에서 lifelines·scipy 결과와 대조한다.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
from matplotlib import patches
from matplotlib.lines import Line2D
from matplotlib.ticker import NullFormatter, PercentFormatter
from scipy import optimize, stats

from . import _st as st
from ...errors import ChartInputError, as_dict, as_list, as_number, need
from ._core import figure, g_fmt, num_fmt, title as put_title, to_bytes, top_margin

TYPES = ["km", "forest", "change_from_baseline", "dose_response", "pk_curve", "ae_comparison", "waterfall_plot", "swimmer", "enrollment", "consort"]
C = st.CATEGORICAL


# ── 통계 ────────────────────────────────────────────────────────
def km_estimate(times, events, alpha: float = 0.05) -> dict:
    """카플란-마이어 생존함수 + Greenwood 분산, log(-log) 변환 신뢰구간."""
    t = np.asarray(times, dtype=float)
    e = np.asarray(events, dtype=int)
    uniq = np.unique(t[e == 1])
    z = stats.norm.ppf(1 - alpha / 2)
    s, gw = 1.0, 0.0
    xs, ss, lo, hi, nrisk = [0.0], [1.0], [1.0], [1.0], [len(t)]
    for u in uniq:
        n = int((t >= u).sum())
        d = int(((t == u) & (e == 1)).sum())
        s *= 1 - d / n
        if n > d:
            gw += d / (n * (n - d))
        xs.append(float(u)); ss.append(s); nrisk.append(n)
        if 0 < s < 1:
            se = np.sqrt(gw) / abs(np.log(s))
            lo.append(s ** np.exp(z * se)); hi.append(s ** np.exp(-z * se))
        else:
            lo.append(s if s == 0 else 1.0); hi.append(1.0 if s > 0 else 0.0)
    if len(xs) > 1 and xs[1] == 0.0:  # 시간 0에 사건이 있으면 S(0) < 1 — 시작점(0, 1)을 대체
        xs, ss, lo, hi, nrisk = xs[1:], ss[1:], lo[1:], hi[1:], nrisk[1:]
    # 중앙값: S(t) ≤ 0.5가 되는 최소 t (SAS 정의). S가 정확히 0.5인 구간은 R(survival)은 구간 중점을 쓰므로 다를 수 있다
    med = next((x for x, v in zip(xs, ss) if v <= 0.5 + 1e-12), None)
    return {"time": xs, "surv": ss, "lower": lo, "upper": hi, "n_at_risk": nrisk, "median": med,
            "censor_times": sorted(t[e == 0].tolist()), "n": len(t), "events": int(e.sum())}


def surv_at(km: dict, x: float) -> float:
    idx = np.searchsorted(km["time"], x, side="right") - 1
    return km["surv"][max(idx, 0)]


def logrank(groups: list[tuple[np.ndarray, np.ndarray]]) -> dict:
    """k-표본 log-rank 검정(카이제곱, 자유도 k-1)과 2군일 때 Pike 근사 위험비."""
    k = len(groups)
    allt = np.concatenate([g[0] for g in groups])
    alle = np.concatenate([g[1] for g in groups])
    ev_times = np.unique(allt[alle == 1])
    O = np.zeros(k); E = np.zeros(k); V = np.zeros((k, k))
    for u in ev_times:
        n = np.array([(g[0] >= u).sum() for g in groups], dtype=float)
        d = np.array([((g[0] == u) & (g[1] == 1)).sum() for g in groups], dtype=float)
        N, D = n.sum(), d.sum()
        if N < 1:
            continue
        O += d
        E += D * n / N
        if N > 1:
            f = D * (N - D) / (N - 1)
            V += f * (np.diag(n / N) - np.outer(n, n) / N ** 2)
    oe = (O - E)[:-1]
    chi2 = float(oe @ np.linalg.pinv(V[:-1, :-1]) @ oe) if k > 1 else 0.0
    p = float(stats.chi2.sf(chi2, k - 1)) if k > 1 else 1.0
    out = {"chi2": chi2, "df": k - 1, "p": p, "observed": O.tolist(), "expected": E.tolist()}
    if k == 2 and all(E > 0) and all(O > 0):
        hr = (O[1] / E[1]) / (O[0] / E[0])
        se = np.sqrt(1 / E[0] + 1 / E[1])
        out["hr_pike"] = (float(hr), float(hr * np.exp(-1.96 * se)), float(hr * np.exp(1.96 * se)))
    return out


def four_pl(x, bottom, top, ec50, hill):
    return bottom + (top - bottom) / (1 + (ec50 / x) ** hill)


def fmt_p(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


# ── 차트 ────────────────────────────────────────────────────────
def render(chart_type: str, data: dict, title: str | None, subtitle: str | None, options: dict, width=None, height=None):
    need(chart_type in TYPES, f"chart_clinical에서 지원하지 않는 chart_type: {chart_type}", hint=f"다음 중 하나: {', '.join(TYPES)}")
    fn = globals()[f"_{chart_type}"]
    return fn(data or {}, title, subtitle, options or {}, width, height)


def _groups_te(data: dict) -> list[dict]:
    ex = [{"name": "위약", "times": [3, 5, 8, 12], "events": [1, 0, 1, 1]}, {"name": "투여", "times": [6, 9, 14, 20], "events": [1, 1, 0, 0]}]
    gs = as_list(data.get("groups"), "groups")
    need(gs, "km은 groups=[{name, times, events}]가 필요합니다(events: 사건 1, 중도절단 0)", example=ex)
    need(len(gs) <= 6, "km 그룹은 최대 6개입니다")
    out = []
    for i, g in enumerate(gs):
        g = as_dict(g, f"groups[{i}]")
        t = [as_number(x, f"groups[{i}].times") for x in as_list(g.get("times"), f"groups[{i}].times")]
        e = as_list(g.get("events"), f"groups[{i}].events")
        need(len(t) == len(e) and len(t) > 0, f"groups[{i}]의 times와 events 개수가 같아야 합니다", example=ex)
        ev = []
        for x in e:
            if isinstance(x, str):
                x = x.strip().lower()
                x = 1 if x in ("1", "true", "event", "사건", "사망", "진행") else 0
            ev.append(1 if x else 0)
        need(all(v is not None and v >= 0 for v in t), f"groups[{i}].times에 빈 값이나 음수가 있습니다")
        out.append({"name": str(g.get("name") or f"군{i + 1}"), "t": np.array(t, float), "e": np.array(ev, int)})
    return out


def _km(data, title, sub, o, w, h):
    gs = _groups_te(data)
    unit = o.get("time_unit", "개월")
    risk = o.get("risk_table", True)
    show_ci = o.get("show_ci", len(gs) <= 2)
    kms = [km_estimate(g["t"], g["e"]) for g in gs]
    tmax = as_number(o.get("x_max"), "options.x_max") or float(max(g["t"].max() for g in gs))
    step = as_number(o.get("tick_step"), "options.tick_step")
    if not step:
        raw = tmax / 6
        mag = 10 ** np.floor(np.log10(raw)) if raw > 0 else 1
        step = float(min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw))
    ticks = np.arange(0, tmax + step * 0.01, step)
    lr = logrank([(g["t"], g["e"]) for g in gs]) if len(gs) >= 2 else None
    warns, meta = [], {"groups": []}
    with figure(w, h or (620 if risk else 520)) as fig:
        nrow = len(gs)
        tm = top_margin(title, sub)
        if risk:
            rt_h = 0.045 * (nrow + 0.6)
            ax = fig.add_axes([0.1, 0.16 + rt_h, 0.86, tm - 0.16 - rt_h - 0.02])
            axr = fig.add_axes([0.1, 0.03, 0.86, rt_h], sharex=ax)
        else:
            ax = fig.add_axes([0.1, 0.12, 0.86, tm - 0.14])
        for i, (g, k) in enumerate(zip(gs, kms)):
            col = C[i]
            ax.step(k["time"] + [tmax], k["surv"] + [k["surv"][-1]], where="post", color=col, lw=2.2, label=f"{g['name']} (n={k['n']}, 사건 {k['events']})")
            if show_ci:
                ax.fill_between(k["time"] + [tmax], k["lower"] + [k["lower"][-1]], k["upper"] + [k["upper"][-1]], step="post", color=col, alpha=0.12, lw=0)
            cx = [c for c in k["censor_times"] if c <= tmax]
            ax.plot(cx, [surv_at(k, c) for c in cx], "|", color=col, ms=9, mew=1.5)
            if k["median"] is not None and o.get("show_median", True):
                ax.plot([0, k["median"], k["median"]], [0.5, 0.5, 0], ls=":", color=col, lw=1)
            meta["groups"].append({"name": g["name"], "n": k["n"], "events": k["events"], "median": k["median"]})
        ax.set_xlim(0, tmax)
        ax.set_ylim(0, 1.03)
        ax.set_xticks(ticks)
        ax.xaxis.set_major_formatter(g_fmt())
        ax.yaxis.set_major_formatter(num_fmt() if o.get("y_percent") is False else PercentFormatter(1.0, decimals=0))
        ax.set_ylabel(o.get("y_label", "생존 확률"))
        ax.set_xlabel(f"시간({unit})")
        ax.legend(loc="lower left" if o.get("legend_loc") is None else o["legend_loc"], handlelength=1.6)
        lines = []
        for i, k in enumerate(kms):
            med = "도달 안 함" if k["median"] is None else f"{k['median']:g}{unit}"
            lines.append(f"중앙 생존: {gs[i]['name']} {med}")
        if lr:
            txt = f"Log-rank {fmt_p(lr['p'])}"
            if "hr_pike" in lr:
                hr, a, b = lr["hr_pike"]
                txt += f"\nHR {hr:.2f} (95% CI {a:.2f}–{b:.2f}) ※{gs[1]['name']} vs {gs[0]['name']}, log-rank 근사"
            ax.text(0.98, 0.97, txt, transform=ax.transAxes, ha="right", va="top", fontsize=10, color=st.INK2,
                    bbox={"boxstyle": "round,pad=0.4", "fc": "white", "ec": st.GRID})
            meta["logrank"] = lr
        if risk:
            axr.set_ylim(-0.5, nrow - 0.5)
            axr.invert_yaxis()
            axr.set_yticks(range(nrow), [g["name"] for g in gs])
            for lab, col in zip(axr.get_yticklabels(), C):
                lab.set_color(col); lab.set_fontweight("bold")
            for i, g in enumerate(gs):
                for tk in ticks:
                    axr.text(tk, i, str(int((g["t"] >= tk).sum())), ha="center", va="center", fontsize=9.5, color=st.INK2)
            axr.grid(False)
            for sp in axr.spines.values():
                sp.set_visible(False)
            axr.tick_params(axis="x", length=0, labelbottom=False)
            axr.tick_params(axis="y", length=0, pad=14)
            axr.set_title("위험 대상자 수(Number at risk)", fontsize=10, loc="left", fontweight="normal", color=st.MUTED, pad=4)
            ax.tick_params(labelbottom=True)
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    warns.append("; ".join(lines))
    warns.append("세로 눈금 '|'은 중도절단, 점선은 중앙 생존시간. 음영은 95% 신뢰구간(log-log)" if show_ci else "세로 눈금 '|'은 중도절단, 점선은 중앙 생존시간")
    return res, warns, meta


def _fit_forest_labels(fig, ax, labs, ns):
    """하위군 이름이 길어 N 열 숫자와 겹치면: 줄이기(8.5pt) → 공백에서 두 줄 → 8pt(1.4.0)."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    right = (min(t.get_window_extent(r).x0 for t in ns) if ns else ax.bbox.x0) - 6

    def over():
        return [t for t in labs if t.get_window_extent(r).x1 > right]

    if not over():
        return
    for t in labs:
        t.set_fontsize(min(t.get_fontsize(), 9.5))
    for t in over():
        t.set_fontsize(8.5)
    wrapped = False
    for t in over():
        txt = t.get_text()
        lead = len(txt) - len(txt.lstrip(" "))
        body = txt.strip()
        sp = [k for k, ch in enumerate(body) if ch == " "]
        if sp:
            k = min(sp, key=lambda k: abs(k - len(body) / 2))
            t.set_text(" " * lead + body[:k] + "\n" + " " * lead + body[k + 1:])
            t.set_linespacing(1.0)
            wrapped = True
    if wrapped:  # 두 줄 이름이 위아래 줄과 붙지 않게 그림 높이를 늘린다
        w_, h_ = fig.get_size_inches()
        fig.set_size_inches(w_, h_ * 1.45)
        fig.canvas.draw()
    for t in over():
        t.set_fontsize(8)


def _forest(data, title, sub, o, w, h):
    rows = as_list(data.get("rows"), "rows")
    ex = [{"label": "전체", "estimate": 0.72, "lower": 0.58, "upper": 0.89, "overall": True}, {"label": "65세 미만", "estimate": 0.68, "lower": 0.5, "upper": 0.92, "n": 210}]
    need(rows, "forest는 rows=[{label, estimate, lower, upper}]가 필요합니다", example=ex)
    measure = str(o.get("measure", "HR"))
    log = o.get("log_scale", measure.upper() in ("HR", "OR", "RR", "IRR"))
    ref = as_number(o.get("ref"), "options.ref")
    ref = (1.0 if log else 0.0) if ref is None else ref
    items = []
    for i, r in enumerate(rows):
        r = as_dict(r, f"rows[{i}]")
        est = as_number(r.get("estimate"), f"rows[{i}].estimate")
        lo, hi = as_number(r.get("lower"), f"rows[{i}].lower"), as_number(r.get("upper"), f"rows[{i}].upper")
        if est is not None:
            need(lo is not None and hi is not None and lo <= est <= hi, f"rows[{i}]('{r.get('label')}')는 lower ≤ estimate ≤ upper 여야 합니다")
            if log:
                need(lo > 0, f"rows[{i}]: 로그 척도에서는 값이 0보다 커야 합니다(위험비·오즈비)", hint="차이(평균차 등)라면 options.log_scale=false, ref=0")
        items.append({"label": str(r.get("label", "")), "est": est, "lo": lo, "hi": hi, "n": r.get("n"), "overall": bool(r.get("overall")),
                      "header": est is None, "indent": int(r.get("indent", 0 if est is None else 1))})
    n = len(items)
    with figure(w, h or max(360, 120 + 30 * n)) as fig:
        tm = top_margin(title, sub)
        ax = fig.add_axes([0.40, 0.1, 0.36, tm - 0.16])
        ax.set_ylim(n - 0.5, -0.9)
        ax.set_yticks([])
        trans = ax.get_yaxis_transform()
        lab_texts, n_texts = [], []
        for i, it in enumerate(items):
            lab_texts.append(ax.text(-0.75, i, ("   " * it["indent"]) + it["label"], transform=trans, ha="left", va="center", fontsize=10.5,
                                     fontweight="bold" if (it["header"] or it["overall"]) else "normal", color=st.INK, clip_on=False))
            if it["n"] is not None:
                n_texts.append(ax.text(-0.08, i, str(it["n"]), transform=trans, ha="right", va="center", fontsize=10, color=st.INK2, clip_on=False))
            if it["est"] is None:
                continue
            if it["overall"]:
                dx = [it["lo"], it["est"], it["hi"], it["est"]]
                ax.add_patch(patches.Polygon(list(zip(dx, [i, i - 0.28, i, i + 0.28])), closed=True, fc=st.INK, ec=st.INK))
            else:
                ax.plot([it["lo"], it["hi"]], [i, i], color=st.INK2, lw=1.4)
                ax.plot([it["est"]], [i], "s", color=C[0], ms=8)
            ax.text(1.04, i, f"{it['est']:.2f} ({it['lo']:.2f}–{it['hi']:.2f})", transform=trans, ha="left", va="center", fontsize=10, color=st.INK2, clip_on=False)
        if any(it["n"] is not None for it in items):
            ax.text(-0.08, -0.85, "N", transform=trans, ha="right", va="center", fontsize=10, color=st.MUTED, fontweight="bold")
        ax.text(1.04, -0.85, f"{measure} (95% CI)", transform=trans, ha="left", va="center", fontsize=10, color=st.MUTED, fontweight="bold")
        ax.axvline(ref, color=st.INK, lw=1)
        if log:
            ax.set_xscale("log")
            ax.xaxis.set_major_formatter(g_fmt())
            ax.xaxis.set_minor_formatter(NullFormatter())
            vals = [v for it in items for v in (it["lo"], it["hi"]) if v]
            lo_, hi_ = min(vals + [ref]), max(vals + [ref])
            ax.set_xlim(lo_ / 1.15, hi_ * 1.15)
            cand = [0.1, 0.2, 0.25, 0.5, 1, 2, 4, 5, 10]
            ax.set_xticks([c for c in cand if lo_ / 1.15 <= c <= hi_ * 1.15])
        ax.grid(axis="y", visible=False)
        ax.spines["left"].set_visible(False)
        _fit_forest_labels(fig, ax, lab_texts, n_texts)
        fav = as_list(o.get("favours"), "options.favours")
        if len(fav) == 2:
            ax.text(0.0, -0.09, f"← {fav[0]}", transform=ax.transAxes, ha="left", va="top", fontsize=9.5, color=st.MUTED)
            ax.text(1.0, -0.09, f"{fav[1]} →", transform=ax.transAxes, ha="right", va="top", fontsize=9.5, color=st.MUTED)
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, [f"기준선 {ref:g}, {'로그' if log else '선형'} 척도. 마름모는 전체(overall) 추정치"], {}


def _visit_groups(data):
    ex = {"visits": ["기저", "4주", "8주", "12주"], "groups": [{"name": "위약", "mean": [0, -1.2, -1.5, -1.8], "error": [0, 0.4, 0.5, 0.5]}]}
    vis = [str(v) for v in as_list(data.get("visits"), "visits")]
    gs = as_list(data.get("groups"), "groups")
    need(vis and gs, "visits와 groups가 필요합니다", example=ex)
    out = []
    for i, g in enumerate(gs):
        g = as_dict(g, f"groups[{i}]")
        m = [as_number(x, f"groups[{i}].mean") for x in as_list(g.get("mean"), f"groups[{i}].mean")]
        e = [as_number(x, f"groups[{i}].error") for x in as_list(g.get("error"), f"groups[{i}].error")] or [None] * len(m)
        need(len(m) == len(vis) and len(e) == len(vis), f"groups[{i}]의 mean·error 개수가 visits 개수와 같아야 합니다", example=ex)
        out.append({"name": str(g.get("name", f"군{i + 1}")), "m": m, "e": e, "n": as_list(g.get("n"), f"groups[{i}].n")})
    return vis, out


def _change_from_baseline(data, title, sub, o, w, h):
    vis, gs = _visit_groups(data)
    with figure(w, h) as fig:
        ax = fig.add_axes([0.09, 0.13, 0.88, top_margin(title, sub) - 0.16])
        x = np.arange(len(vis))
        off = 0.06 * (np.arange(len(gs)) - (len(gs) - 1) / 2)
        for i, g in enumerate(gs):
            m = np.array([np.nan if v is None else v for v in g["m"]], float)
            e = np.array([np.nan if v is None else v for v in g["e"]], float)
            ax.errorbar(x + off[i], m, yerr=e, color=C[i], lw=2.2, marker="o", ms=6, capsize=4, label=g["name"])
            if o.get("show_last_value", True):
                last = np.where(~np.isnan(m))[0][-1]
                ax.annotate(f"{m[last]:+.2f}", (x[last] + off[i], m[last]), xytext=(8, 0), textcoords="offset points", va="center", fontsize=10, color=C[i])
        ax.axhline(0, color=st.INK2, lw=1)
        ax.set_xticks(x, vis)
        ax.set_ylabel(o.get("y_label", "기저치 대비 변화"))
        ax.legend(loc="best")
        stars = as_list(o.get("significance"), "options.significance")  # [{visit, label:'*'}]
        for s_ in stars:
            s_ = as_dict(s_, "significance[]")
            if str(s_.get("visit")) in vis:
                xi = vis.index(str(s_.get("visit")))
                ymax = max((g["m"][xi] or 0) + (g["e"][xi] or 0) for g in gs)
                ax.text(xi, ymax, str(s_.get("label", "*")), ha="center", va="bottom", fontsize=13, color=st.INK)
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, [f"오차막대: {o.get('error_label', '평균 ± 표준오차(SE)')} — options.error_label로 표기를 바꿀 수 있습니다"], {}


def _dose_response(data, title, sub, o, w, h):
    gs = as_list(data.get("groups"), "groups")
    ex = [{"name": "화합물 A", "dose": [0.01, 0.1, 1, 10, 100], "response": [2, 10, 48, 88, 97]}]
    need(gs, "dose_response는 groups=[{name, dose, response}]가 필요합니다", example=ex)
    meta = {"fits": []}
    warns = []
    unit = o.get("dose_unit", "μM")
    with figure(w, h) as fig:
        ax = fig.add_axes([0.09, 0.13, 0.86, top_margin(title, sub) - 0.16])
        for i, g in enumerate(gs):
            g = as_dict(g, f"groups[{i}]")
            x = np.array([as_number(v, "dose") for v in as_list(g.get("dose"), f"groups[{i}].dose")], float)
            y = np.array([as_number(v, "response") for v in as_list(g.get("response"), f"groups[{i}].response")], float)
            need(len(x) == len(y) and len(x) >= 4, f"groups[{i}]: dose·response 개수가 같고 4개 이상이어야 합니다(4PL 적합)", example=ex)
            need((x > 0).all(), f"groups[{i}]: 로그 축이므로 dose는 0보다 커야 합니다(대조군 0은 제외하거나 options.control로 표시)")
            name = str(g.get("name", f"군{i + 1}"))
            ax.plot(x, y, "o", color=C[i], ms=7, label=name)
            try:
                p0 = [float(y.min()), float(y.max()), float(np.exp(np.mean(np.log(x)))), 1.0]
                popt, pcov = optimize.curve_fit(four_pl, x, y, p0=p0, bounds=([-np.inf, -np.inf, 1e-12, 0.05], [np.inf, np.inf, np.inf, 20]), maxfev=20000)
                xx = np.logspace(np.log10(x.min() / 2), np.log10(x.max() * 2), 200)
                ax.plot(xx, four_pl(xx, *popt), color=C[i], lw=2)
                ec50 = popt[2]
                yhat = four_pl(x, *popt)
                r2 = 1 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum()
                ax.axvline(ec50, color=C[i], ls=":", lw=1)
                meta["fits"].append({"name": name, "bottom": popt[0], "top": popt[1], "ec50": ec50, "hill": popt[3], "r2": r2})
                warns.append(f"{name}: {o.get('ec_label', 'EC50')} = {ec50:.4g} {unit}, Hill {popt[3]:.2f}, R² {r2:.3f}")
            except (RuntimeError, ValueError) as e:
                warns.append(f"{name}: 4PL 적합 실패({e}) — 점만 표시")
        ax.set_xscale("log")
        ax.xaxis.set_major_formatter(g_fmt())
        ax.set_xlabel(f"용량·농도({unit}, 로그 척도)")
        ax.set_ylabel(o.get("y_label", "반응(%)"))
        ax.legend(loc="best")
        if meta["fits"]:
            txt = "\n".join(f"{f['name']}: {o.get('ec_label', 'EC50')} {f['ec50']:.3g} {unit}" for f in meta["fits"])
            ax.text(0.02, 0.97, txt, transform=ax.transAxes, ha="left", va="top", fontsize=10, color=st.INK2, bbox={"boxstyle": "round,pad=0.4", "fc": "white", "ec": st.GRID})
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, warns, meta


def _pk_params(t: np.ndarray, c: np.ndarray, n_terminal: int = 3) -> dict:
    i = int(np.nanargmax(c))
    auc = float(np.trapezoid(c, t)) if hasattr(np, "trapezoid") else float(np.trapz(c, t))
    out = {"cmax": float(c[i]), "tmax": float(t[i]), "auc_0_t": auc}
    tt, cc = t[i + 1:], c[i + 1:]
    m = cc > 0
    tt, cc = tt[m][-n_terminal:], cc[m][-n_terminal:]
    if len(tt) >= 3:
        slope, _ = np.polyfit(tt, np.log(cc), 1)
        if slope < 0:
            kel = -slope
            out["kel"] = float(kel)
            out["t_half"] = float(np.log(2) / kel)
            out["auc_0_inf"] = auc + float(c[np.where(c > 0)[0][-1]] / kel)
    return out


def _pk_curve(data, title, sub, o, w, h):
    gs = as_list(data.get("groups"), "groups")
    ex = [{"name": "100mg", "time": [0, 0.5, 1, 2, 4, 8, 12, 24], "conc": [0, 120, 210, 180, 110, 52, 25, 6], "sd": [0, 20, 30, 25, 18, 9, 5, 2]}]
    need(gs, "pk_curve는 groups=[{name, time, conc, sd?}]가 필요합니다", example=ex)
    semilog = o.get("semilog", False)
    unit_t, unit_c = o.get("time_unit", "h"), o.get("conc_unit", "ng/mL")
    meta, warns = {"params": []}, []
    with figure(w, h) as fig:
        if o.get("both_scales"):
            ax = fig.add_axes([0.08, 0.13, 0.4, top_margin(title, sub) - 0.16])
            ax2 = fig.add_axes([0.57, 0.13, 0.4, top_margin(title, sub) - 0.16])
            axes = [(ax, False), (ax2, True)]
        else:
            ax = fig.add_axes([0.09, 0.13, 0.86, top_margin(title, sub) - 0.16])
            axes = [(ax, semilog)]
        for i, g in enumerate(gs):
            g = as_dict(g, f"groups[{i}]")
            t = np.array([as_number(v, "time") for v in as_list(g.get("time"), f"groups[{i}].time")], float)
            c = np.array([as_number(v, "conc") for v in as_list(g.get("conc"), f"groups[{i}].conc")], float)
            sd = as_list(g.get("sd"), f"groups[{i}].sd")
            need(len(t) == len(c) and len(t) >= 3, f"groups[{i}]: time·conc 개수가 같고 3개 이상이어야 합니다", example=ex)
            name = str(g.get("name", f"군{i + 1}"))
            for a, lg in axes:
                tt, cc = (t[c > 0], c[c > 0]) if lg else (t, c)
                if sd:
                    sdv = np.array([as_number(v, "sd") or 0 for v in sd], float)
                    sdv = sdv[c > 0] if lg else sdv
                    a.errorbar(tt, cc, yerr=sdv, color=C[i], lw=2, marker="o", ms=5, capsize=3, label=name)
                else:
                    a.plot(tt, cc, color=C[i], lw=2, marker="o", ms=5, label=name)
            p = _pk_params(t, c)
            p["name"] = name
            meta["params"].append(p)
            s = f"{name}: Cmax {p['cmax']:.4g} {unit_c}, Tmax {p['tmax']:g} {unit_t}, AUC0-t {p['auc_0_t']:.4g} {unit_c}·{unit_t}"
            if "t_half" in p:
                s += f", t½ {p['t_half']:.3g} {unit_t}"
            warns.append(s)
        for a, lg in axes:
            if lg:
                a.set_yscale("log")
                a.yaxis.set_major_formatter(g_fmt())
            a.set_xlabel(f"투여 후 시간({unit_t})")
            a.set_ylabel(f"혈중 농도({unit_c}{', 로그' if lg else ''})")
            a.legend(loc="upper right")
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    warns.append("AUC는 선형 사다리꼴법, t½은 말단 3개 점의 로그-선형 회귀(비구획 분석 근사). 규제 제출용 수치는 검증된 PK 소프트웨어로 확인하세요")
    return res, warns, meta


def _ae_comparison(data, title, sub, o, w, h):
    terms = as_list(data.get("terms"), "terms")
    arms = [str(a) for a in as_list(data.get("arms"), "arms")] or ["투여군", "위약군"]
    ex = {"arms": ["투여군", "위약군"], "terms": [{"term": "두통", "a_events": 18, "a_n": 150, "b_events": 9, "b_n": 148}]}
    need(terms, "ae_comparison은 terms=[{term, a_events, a_n, b_events, b_n}]가 필요합니다", example=ex)
    rows = []
    for i, t in enumerate(terms):
        t = as_dict(t, f"terms[{i}]")
        ae, an, be, bn = (as_number(t.get(k), f"terms[{i}].{k}") for k in ("a_events", "a_n", "b_events", "b_n"))
        need(an and bn and an > 0 and bn > 0 and ae is not None and be is not None, f"terms[{i}]의 건수와 대상자 수가 필요합니다", example=ex)
        pa, pb = ae / an, be / bn
        rd = pa - pb
        se = np.sqrt(pa * (1 - pa) / an + pb * (1 - pb) / bn)
        rows.append({"term": str(t.get("term")), "pa": pa, "pb": pb, "rd": rd, "lo": rd - 1.96 * se, "hi": rd + 1.96 * se})
    rows.sort(key=lambda r: r["rd"], reverse=not o.get("ascending", False))
    n = len(rows)
    with figure(w, h or max(360, 140 + 28 * n)) as fig:
        tm = top_margin(title, sub)
        ax1 = fig.add_axes([0.24, 0.14, 0.36, tm - 0.21])
        ax2 = fig.add_axes([0.63, 0.14, 0.34, tm - 0.21], sharey=ax1)
        y = np.arange(n)
        ax1.scatter([r["pa"] * 100 for r in rows], y, color=C[1], s=40, label=arms[0], zorder=3)
        ax1.scatter([r["pb"] * 100 for r in rows], y, color=C[0], s=40, label=arms[1], zorder=3, marker="^")
        ax1.set_yticks(y, [r["term"] for r in rows])
        ax1.invert_yaxis()
        ax1.set_xlabel("발생률(%)")
        ax1.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2)
        for r, yy in zip(rows, y):
            ax2.plot([r["lo"] * 100, r["hi"] * 100], [yy, yy], color=st.INK2, lw=1.3)
            ax2.plot([r["rd"] * 100], [yy], "o", color=C[1] if r["rd"] > 0 else C[0], ms=6)
        ax2.axvline(0, color=st.INK, lw=1)
        ax2.set_xlabel("위험차(%p, 95% CI)")
        ax2.tick_params(labelleft=False)
        put_title(fig, ax1, title, sub)
        res = to_bytes(fig)
    return res, [f"왼쪽: 군별 발생률, 오른쪽: 위험차({arms[0]} − {arms[1]}) 와 Wald 95% CI. 위험차 순 정렬"], {"rows": rows}


def _waterfall_plot(data, title, sub, o, w, h):
    ps = as_list(data.get("patients"), "patients")
    ex = [{"id": "P01", "change": -45, "response": "PR"}, {"id": "P02", "change": 22, "response": "PD"}]
    need(ps, "waterfall_plot은 patients=[{id, change(최대 종양 크기 변화 %), response?}]가 필요합니다", example=ex)
    rows = []
    for i, p in enumerate(ps):
        p = as_dict(p, f"patients[{i}]")
        ch = as_number(p.get("change"), f"patients[{i}].change")
        resp = p.get("response")
        if not resp:
            resp = "CR" if ch <= -100 else ("PR" if ch <= -30 else ("PD" if ch >= 20 else "SD"))
        rows.append({"id": str(p.get("id", i + 1)), "ch": ch, "resp": str(resp).upper()})
    rows.sort(key=lambda r: -r["ch"])
    cmap = {"CR": "#0d366b", "PR": C[0], "SD": st.GRAY, "PD": C[7], "NE": "#e1e0d9"}
    with figure(w, h) as fig:
        ax = fig.add_axes([0.08, 0.1, 0.9, top_margin(title, sub) - 0.13])
        x = np.arange(len(rows))
        ax.bar(x, [r["ch"] for r in rows], color=[cmap.get(r["resp"], C[3]) for r in rows], width=0.8)
        ax.axhline(20, color=C[7], ls="--", lw=1); ax.axhline(-30, color=C[0], ls="--", lw=1); ax.axhline(0, color=st.INK, lw=1)
        ax.text(len(rows) - 0.5, 21, "+20% (PD)", ha="right", va="bottom", fontsize=9, color=C[7])
        ax.text(len(rows) - 0.5, -31, "−30% (PR)", ha="right", va="top", fontsize=9, color=C[0])
        ax.set_xticks(x, [r["id"] for r in rows] if len(rows) <= 40 else [""] * len(rows), rotation=90, fontsize=8)
        ax.set_ylabel("기저 대비 최대 종양 크기 변화(%)")
        ax.set_ylim(min(-105, min(r["ch"] for r in rows) - 5), max(40, max(r["ch"] for r in rows) + 10))
        ax.grid(axis="x", visible=False)
        present = [k for k in ("CR", "PR", "SD", "PD", "NE") if any(r["resp"] == k for r in rows)]
        ax.legend([patches.Patch(color=cmap[k]) for k in present], [f"{k} (n={sum(r['resp'] == k for r in rows)})" for k in present], loc="upper right", ncol=len(present))
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    orr = sum(r["resp"] in ("CR", "PR") for r in rows) / len(rows) * 100
    return res, [f"ORR(CR+PR) {orr:.1f}% (n={len(rows)}). 반응 미입력 환자는 RECIST 크기 기준으로만 분류했습니다(확정 반응 아님)"], {"orr": orr}


def _swimmer(data, title, sub, o, w, h):
    ps = as_list(data.get("patients"), "patients")
    ex = [{"id": "P01", "duration": 14.2, "group": "용량 A", "ongoing": True, "events": [{"time": 2.1, "type": "PR"}, {"time": 8.0, "type": "CR"}]}]
    need(ps, "swimmer는 patients=[{id, duration, group?, ongoing?, events?}]가 필요합니다", example=ex)
    rows, groups, etypes = [], [], []
    for i, p in enumerate(ps):
        p = as_dict(p, f"patients[{i}]")
        g = p.get("group")
        if g is not None and g not in groups:
            groups.append(g)
        evs = []
        for j, e in enumerate(as_list(p.get("events"), f"patients[{i}].events")):
            e = as_dict(e, f"patients[{i}].events[{j}]")
            et = str(e.get("type"))
            if et not in etypes:
                etypes.append(et)
            evs.append((as_number(e.get("time"), "events.time"), et))
        rows.append({"id": str(p.get("id", i + 1)), "d": as_number(p.get("duration"), f"patients[{i}].duration"), "g": g, "on": bool(p.get("ongoing")), "ev": evs})
    rows.sort(key=lambda r: r["d"] or 0)
    markers = ["D", "o", "s", "^", "v", "P", "X", "*"]
    ecol = [st.INK, C[2], C[3], C[7], C[4], C[6], C[5], C[1]]
    unit = o.get("time_unit", "개월")
    with figure(w, h or max(380, 120 + 22 * len(rows))) as fig:
        ax = fig.add_axes([0.1, 0.1, 0.86, top_margin(title, sub) - 0.13])
        y = np.arange(len(rows))
        cols = [C[groups.index(r["g"])] if r["g"] in groups else st.SEQUENTIAL[6] for r in rows]
        ax.barh(y, [r["d"] for r in rows], color=cols, height=0.62)
        mx = max(r["d"] or 0 for r in rows)
        for yy, r in zip(y, rows):
            for t, et in r["ev"]:
                k = etypes.index(et)
                ax.plot([t], [yy], markers[k % 8], color=ecol[k % 8], ms=7, mec="white", mew=0.8)
            if r["on"]:
                ax.annotate("", xy=(r["d"] + mx * 0.04, yy), xytext=(r["d"], yy), arrowprops={"arrowstyle": "-|>", "color": st.INK2, "lw": 1.2})
        ax.set_yticks(y, [r["id"] for r in rows], fontsize=8.5)
        ax.set_xlabel(f"치료 기간({unit})")
        ax.grid(axis="y", visible=False)
        hs = [patches.Patch(color=C[k], label=str(g)) for k, g in enumerate(groups)]
        hs += [Line2D([], [], marker=markers[k % 8], color=ecol[k % 8], ls="", label=et) for k, et in enumerate(etypes)]
        if any(r["on"] for r in rows):
            hs.append(Line2D([], [], marker=">", color=st.INK2, ls="", label="치료 지속 중"))
        ax.legend(handles=hs, loc="lower right")
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, [], {}


def _enrollment(data, title, sub, o, w, h):
    def series(key):
        out = []
        for i, r in enumerate(as_list(data.get(key), key)):
            r = as_dict(r, f"{key}[{i}]")
            try:
                d = date.fromisoformat(str(r.get("date"))[:10])
            except ValueError as e:
                raise ChartInputError(f"{key}[{i}].date가 날짜가 아닙니다") from e
            out.append((d, as_number(r.get("count"), f"{key}[{i}].count")))
        return sorted(out)
    ex = {"planned": [{"date": "2026-01-31", "count": 20}], "actual": [{"date": "2026-01-31", "count": 14}], "options": {"cumulative": False, "target": 200}}
    pl, ac = series("planned"), series("actual")
    need(pl or ac, "enrollment는 planned·actual=[{date, count}]가 필요합니다", example=ex)
    cum = not o.get("cumulative", False)  # 입력이 기간별 건수면 누적해 그린다
    target = as_number(o.get("target"), "options.target")
    meta = {}
    with figure(w, h) as fig:
        ax = fig.add_axes([0.08, 0.12, 0.88, top_margin(title, sub) - 0.15])
        for s, lab, col, ls in ((pl, "계획", st.GRAY, "--"), (ac, "실적", C[0], "-")):
            if not s:
                continue
            xs = [d for d, _ in s]
            ys = np.cumsum([v or 0 for _, v in s]) if cum else [v for _, v in s]
            ax.plot(xs, ys, ls=ls, color=col, lw=2.4, marker="o" if lab == "실적" else None, ms=4, label=lab)
            meta[lab] = float(ys[-1])
            ax.annotate(f"{ys[-1]:,.0f}", (xs[-1], ys[-1]), xytext=(6, 0), textcoords="offset points", va="center", color=col, fontsize=10)
        if target:
            ax.axhline(target, color=st.INK2, lw=1, ls=":")
            ax.text(ax.get_xlim()[0], target, f" 목표 {target:,.0f}명", va="bottom", fontsize=9.5, color=st.INK2)
        ax.set_ylabel("누적 등록 환자 수" if cum else "등록 환자 수")
        ax.yaxis.set_major_formatter(num_fmt())
        fig.autofmt_xdate(rotation=0, ha="center")
        import matplotlib.dates as mdates
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%y.%m"))
        ax.legend(loc="lower right")
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    warns = []
    if "계획" in meta and "실적" in meta and meta["계획"]:
        warns.append(f"현재 실적 {meta['실적']:,.0f}명 / 계획 {meta['계획']:,.0f}명 ({meta['실적'] / meta['계획'] * 100:.0f}%)")
    return res, warns, meta


def _consort(data, title, sub, o, w, h):
    ex = {"assessed": 420, "excluded": {"n": 120, "reasons": ["선정기준 미충족 (n=85)", "동의 철회 (n=35)"]}, "randomized": 300,
          "arms": [{"name": "투여군", "allocated": 150, "lost": 6, "discontinued": 10, "analyzed": 144}, {"name": "위약군", "allocated": 150, "lost": 4, "discontinued": 8, "analyzed": 146}]}
    need(data.get("assessed") is not None and data.get("arms"), "consort는 assessed, excluded, randomized, arms가 필요합니다", example=ex)
    arms = [as_dict(a, f"arms[{i}]") for i, a in enumerate(as_list(data.get("arms"), "arms"))]
    need(1 <= len(arms) <= 4, "arms는 1~4개입니다")
    exc = as_dict(data.get("excluded"), "excluded")
    warns = []
    assessed = as_number(data.get("assessed"), "assessed")
    rnd = as_number(data.get("randomized"), "randomized")
    if exc.get("n") is not None and rnd is not None and assessed is not None and assessed - as_number(exc["n"], "excluded.n") != rnd:
        warns.append(f"확인 필요: 적격성 평가 {assessed:.0f} − 제외 {as_number(exc['n'], 'n'):.0f} ≠ 무작위배정 {rnd:.0f}")
    if rnd is not None and abs(sum(as_number(a.get("allocated"), "allocated") or 0 for a in arms) - rnd) > 0:
        warns.append("확인 필요: 군별 배정 합계가 무작위배정 수와 다릅니다")
    with figure(w or 960, h or 700) as fig:
        ax = fig.add_axes([0, 0, 1, top_margin(title, sub) + 0.02])
        ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")

        def box(x, y, wd, ht, text, bold=False, fc="white"):
            ax.add_patch(patches.FancyBboxPatch((x - wd / 2, y - ht / 2), wd, ht, boxstyle="round,pad=0.3,rounding_size=0.8", fc=fc, ec=st.INK2, lw=1.1))
            ax.text(x, y, text, ha="center", va="center", fontsize=10, color=st.INK, fontweight="bold" if bold else "normal", linespacing=1.4)

        def arrow(x1, y1, x2, y2):
            ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops={"arrowstyle": "-|>", "color": st.INK2, "lw": 1.1})
        box(50, 92, 30, 6, f"적격성 평가 (n={assessed:,.0f})", bold=True)
        reasons = "\n".join(f"• {r}" for r in as_list(exc.get("reasons"), "excluded.reasons"))
        ex_h = 5 + 3 * len(as_list(exc.get("reasons"), "excluded.reasons"))
        box(80, 80, 34, ex_h, f"제외 (n={as_number(exc.get('n'), 'n') or 0:,.0f})" + (f"\n{reasons}" if reasons else ""))
        ax.plot([50, 50], [89, 73], color=st.INK2, lw=1.1)
        arrow(50, 80, 63, 80)
        box(50, 70, 26, 6, f"무작위배정 (n={rnd or 0:,.0f})", bold=True, fc="#eef4fc")
        k = len(arms)
        xs = [50] if k == 1 else list(np.linspace(22, 78, k))
        ax.plot([xs[0], xs[-1]], [62, 62], color=st.INK2, lw=1.1)
        ax.plot([50, 50], [67, 62], color=st.INK2, lw=1.1)
        bw = min(34, 90 / k - 4)
        for a, x in zip(arms, xs):
            arrow(x, 62, x, 57)
            box(x, 51.5, bw, 9, f"{a.get('name')}\n배정 (n={as_number(a.get('allocated'), 'allocated') or 0:,.0f})", bold=True)
            arrow(x, 47, x, 40.5)
            fl = [f"추적 실패 (n={as_number(a.get('lost'), 'lost') or 0:,.0f})", f"투여 중단 (n={as_number(a.get('discontinued'), 'discontinued') or 0:,.0f})"]
            fl += [str(r) for r in as_list(a.get("other"), "arms.other")]
            box(x, 34, bw, 4 + 3.2 * len(fl), "\n".join(fl))
            arrow(x, 34 - (4 + 3.2 * len(fl)) / 2 - 0.3, x, 18)
            box(x, 13, bw, 8, f"분석 (n={as_number(a.get('analyzed'), 'analyzed') or 0:,.0f})" + (f"\n{a.get('analysis_note')}" if a.get("analysis_note") else ""), bold=True)
        for lab, y in (("등록", 81), ("배정", 51.5), ("추적", 34), ("분석", 13)):
            ax.text(2, y, lab, fontsize=10, color=C[0], fontweight="bold", va="center")
        put_title(fig, ax, title, sub)
        res = to_bytes(fig)
    return res, warns or ["숫자 정합성(평가−제외=배정, 군별 합) 자동 점검 통과"], {}
