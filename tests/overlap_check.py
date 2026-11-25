"""글자 겹침 점검 — 그림을 저장하기 직전에 글자 상자끼리 겹치는지, 축 밖으로 잘리는지, 선이 숫자를 가로지르는지 잰다.

    python tests/overlap_check.py                 # 75종 예시 + 부하 변형(큰 수·긴 이름·많은 항목)
    python tests/overlap_check.py --only F-09     # 한 종류만
    python tests/overlap_check.py --save out/     # 그림도 저장(눈으로 확인용)

판정(100dpi 그림 좌표, 픽셀):
- text×text: 두 글자 상자(회전 글자는 회전 사각형)가 가로·세로 모두 1.5px 넘게 겹침
- clip: 축 안에 잘리는 글자(clip_on)가 축 밖으로 2px 넘게 나감
- line×text: 데이터 선(범례·눈금선 제외)이 숫자 글자 상자 안쪽(가장자리 20% 뺀 영역)을 지남
의도한 겹침(같은 자리 글자 두 겹 등)은 ALLOW에 적는다.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import numpy as np  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.text import Text  # noqa: E402

from chartkit import api  # noqa: E402

FOUND: list[dict] = []
_orig_savefig = Figure.savefig


# ── 글자 상자 ───────────────────────────────────────────────
def _rect(t: Text, r):
    """회전 사각형(중심·반폭·반높이·각도). 축 정렬 상자의 중심 = 회전 사각형의 중심."""
    bb = t.get_window_extent(r)
    if bb.width <= 0 or bb.height <= 0:
        return None
    ang = math.radians(t.get_rotation() % 180)
    if abs(math.sin(ang)) < 1e-3 or abs(math.cos(ang)) < 1e-3:
        return (bb.x0 + bb.width / 2, bb.y0 + bb.height / 2, bb.width / 2, bb.height / 2, 0.0, bb)
    rot = t.get_rotation()
    t.set_rotation(0)
    b0 = t.get_window_extent(r)
    t.set_rotation(rot)
    return (bb.x0 + bb.width / 2, bb.y0 + bb.height / 2, b0.width / 2, b0.height / 2, ang, bb)


def _corners(R):
    cx, cy, hw, hh, a, _ = R
    c, s = math.cos(a), math.sin(a)
    return [(cx + dx * c - dy * s, cy + dx * s + dy * c) for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]


def _sat_overlap(A, B, tol=1.5):
    """분리축 정리 — 모든 축에서 겹친 길이가 tol 넘으면 겹침. 최소 겹친 길이를 돌려준다(없으면 0)."""
    ca, cb = _corners(A), _corners(B)
    m = float("inf")
    for R in (A, B):
        a = R[4]
        for ax_ in ((math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))):
            pa = [x * ax_[0] + y * ax_[1] for x, y in ca]
            pb = [x * ax_[0] + y * ax_[1] for x, y in cb]
            ov = min(max(pa), max(pb)) - max(min(pa), min(pb))
            if ov <= tol:
                return 0.0
            m = min(m, ov)
    return m


def _texts(fig, r):
    out = []
    tick_ids = set()
    for ax in fig.axes:
        hidden = (not ax.axison) or (not ax.get_visible())
        for axis in (ax.xaxis, ax.yaxis):
            for tk in axis.get_major_ticks() + axis.get_minor_ticks():
                for lab in (tk.label1, tk.label2):
                    tick_ids.add(id(lab))
            if hidden or not axis.get_visible():
                continue
            try:
                drawn = axis._update_ticks()  # 실제로 그려지는 눈금
            except Exception:  # noqa: BLE001
                drawn = []
            for tk in drawn:
                for lab in (tk.label1, tk.label2):
                    if lab.get_visible() and lab.get_text().strip() and matplotlib.colors.to_rgba(lab.get_color())[3] > 0:
                        out.append(("tick", lab))
    for t in fig.findobj(Text):
        if id(t) in tick_ids or not t.get_visible() or not t.get_text().strip():
            continue
        if t.get_alpha() == 0 or matplotlib.colors.to_rgba(t.get_color())[3] == 0:
            continue
        # 보이지 않는 조상(숨긴 축)의 글자는 뺀다
        ax = t.axes
        if ax is not None and not ax.get_visible():
            continue
        out.append(("text", t))
    res = []
    for kind, t in out:
        try:
            R = _rect(t, r)
        except Exception:  # noqa: BLE001
            continue
        if R:
            res.append((kind, t, R))
    return res


NUM = re.compile(r"^[\s+\-−▲▼△▽(]*[\d.,]+\s*(%|%p|배|x|억|만|천|원|조|건|개|명|대|pt|p|일|개월|년|위)?\)?\s*$")


def _check(fig, tag):
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    items = _texts(fig, r)
    issues = []
    # text × text
    for i in range(len(items)):
        ki, ti, Ri = items[i]
        for j in range(i + 1, len(items)):
            kj, tj, Rj = items[j]
            bi, bj = Ri[5], Rj[5]
            if bi.x1 < bj.x0 or bj.x1 < bi.x0 or bi.y1 < bj.y0 or bj.y1 < bi.y0:
                continue
            if ti.get_text() == tj.get_text() and abs(bi.x0 - bj.x0) < 1 and abs(bi.y0 - bj.y0) < 1:
                continue  # 같은 글자 두 겹(테두리 효과)
            ov = _sat_overlap(Ri, Rj)
            if ov > 0:
                issues.append({"kind": "text×text", "a": ti.get_text()[:30], "b": tj.get_text()[:30], "px": round(ov, 1)})
    # clip
    for k, t, R in items:
        if not t.get_clip_on() or t.axes is None or (t.get_clip_box() is None and t.get_clip_path() is None):
            continue  # 주석(annotate)은 잘림 상자가 없어 축 밖에도 그려진다
        cb = t.get_clip_box() or t.axes.bbox
        b = R[5]
        out = max(cb.x0 - b.x0, b.x1 - cb.x1, cb.y0 - b.y0, b.y1 - cb.y1)
        if out > 2:
            issues.append({"kind": "clip", "a": t.get_text()[:30], "px": round(out, 1)})
    # line × number text
    # 흰 글자는 표식·막대 위에 얹은 글자라 선이 지나도 가려진다 — 뺀다
    nums = [(t, R) for k, t, R in items if k == "text" and NUM.match(t.get_text().replace("\n", " "))
            and sum(matplotlib.colors.to_rgb(t.get_color())) < 2.7]
    if nums:
        for ax in fig.axes:
            for ln in ax.get_lines():
                if not ln.get_visible() or ln.get_linestyle() in ("None", "none", "") or ln.get_linewidth() < 0.8:
                    continue
                if ln.get_label().startswith("_child") is False and ln.get_label().startswith("_") is False and False:
                    pass
                xy = ln.get_xydata()
                if xy is None or len(xy) < 2:
                    continue
                try:
                    P = ln.get_transform().transform(np.asarray(xy, float))
                except Exception:  # noqa: BLE001
                    continue
                P = P[np.isfinite(P).all(axis=1)]
                if len(P) < 2:
                    continue
                # 선분 촘촘히 샘플
                seg = []
                for a_, b_ in zip(P[:-1], P[1:]):
                    n = max(2, int(np.hypot(*(b_ - a_)) / 2))
                    seg.append(np.linspace(a_, b_, n))
                S = np.vstack(seg)
                for t, R in nums:
                    if (t.axes is not ax and t.axes is not None) or t.get_bbox_patch() is not None:
                        continue
                    b = R[5]
                    mx, my = b.width * 0.2, b.height * 0.25
                    inside = (S[:, 0] > b.x0 + mx) & (S[:, 0] < b.x1 - mx) & (S[:, 1] > b.y0 + my) & (S[:, 1] < b.y1 - my)
                    if inside.any():
                        issues.append({"kind": "line×text", "a": t.get_text()[:30], "b": (ln.get_label() or "")[:20]})
    if issues:
        FOUND.append({"tag": tag, "issues": issues})
    return issues


CUR = {"tag": None}


def _patched_savefig(self, *a, **k):
    try:
        _check(self, CUR["tag"])
    except Exception as e:  # noqa: BLE001
        FOUND.append({"tag": CUR["tag"], "issues": [{"kind": "checker-error", "a": repr(e)[:120]}]})
    return _orig_savefig(self, *a, **k)


Figure.savefig = _patched_savefig


# ── 부하 변형 ───────────────────────────────────────────────
HANGUL = re.compile(r"[가-힣]")
DATE = re.compile(r"^\d{4}[-./]\d{1,2}([-./]\d{1,2})?$")
SKIP_NUM_KEYS = {"p", "pvalue", "p_value", "padj", "q", "lo", "hi", "time", "t", "event", "events", "status", "dose", "conc",
                 "x", "lat", "lon", "start", "end", "min", "max", "target", "level", "rank", "year", "month", "day", "n_at_risk"}


def lengthen(obj, suffix="권역본부"):
    """한글이 든 이름에 같은 꼬리말을 붙인다(참조 관계가 깨지지 않게 모든 곳에 똑같이)."""
    if isinstance(obj, dict):
        return {k: (v if k in ("type", "kind", "color", "shape", "direction", "status") else lengthen(v, suffix)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [lengthen(v, suffix) for v in obj]
    if isinstance(obj, str) and HANGUL.search(obj) and not DATE.match(obj) and len(obj) <= 12:
        return obj + suffix
    return obj


def bignum(obj, f=1234.567, key=None):
    if isinstance(obj, dict):
        return {k: bignum(v, f, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [bignum(v, f, key) for v in obj]
    if isinstance(obj, bool) or key in SKIP_NUM_KEYS:
        return obj
    if isinstance(obj, (int, float)):
        return obj * f
    return obj


TEMPORAL = re.compile(r"^(\d{2,4}[.\-/년]?\s*\d{0,2}월?|\d{1,2}월|\d{4}|[1-4]Q|Q[1-4]|\d{2}\.\d{1,2})$")
NAME_KEYS = ("name", "label", "category", "item", "task", "region", "id", "source", "target")


def _ext_list(lst, n, N):
    """길이 n 목록을 N개로 늘린다(숫자는 결정적 변동을 주며 되풀이)."""
    out = list(lst)
    for i in range(n, N):
        v = lst[i % n]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            v = round(v * (0.82 + 0.36 * ((i * 37) % 11) / 10), 2)
        elif isinstance(v, list):
            v = copy.deepcopy(v)
        out.append(v)
    return out


def _many_cats(obj, n, N):
    if isinstance(obj, dict):
        return {k: _many_cats(v, n, N) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) == n and all(isinstance(x, (int, float, type(None), list)) and not isinstance(x, bool) for x in obj):
            obj = _ext_list(obj, n, N)
        return [_many_cats(v, n, N) for v in obj]
    return obj


def many(data, N=24):
    """항목을 24개 안팎으로 늘린다 — categories가 있으면 그 길이의 숫자 목록을 함께 늘리고, 없으면 객체 목록을 복제한다."""
    if not isinstance(data, dict):
        return data
    d = copy.deepcopy(data)
    cats = d.get("categories")
    if isinstance(cats, list) and cats and all(isinstance(c, str) for c in cats):
        n = len(cats)
        if n >= N:
            N = n * 2
        if all(TEMPORAL.match(c.strip()) for c in cats):
            new = [f"{2024 + i // 12}.{i % 12 + 1:02d}" for i in range(N)]
        else:
            new = [cats[i % n] + ("" if i < n else str(i // n + 1)) for i in range(N)]
        d = _many_cats(d, n, N)
        d["categories"] = new
        return d
    # 점 목록(series[].points)은 계열이 아니라 점을 늘린다
    if isinstance(d.get("series"), list) and d["series"] and isinstance(d["series"][0], dict) and "points" in d["series"][0]:
        for s_ in d["series"]:
            pts = s_.get("points") or []
            if pts and isinstance(pts[0], dict):
                add = []
                for r_ in range(1, 3):
                    for p in pts:
                        p2 = dict(p)
                        for kk in ("x", "y"):
                            if isinstance(p2.get(kk), (int, float)):
                                p2[kk] = round(p2[kk] * (1 + 0.06 * r_) + 0.7 * r_, 2)
                        if isinstance(p2.get("label"), str):
                            p2["label"] = f"{p2['label']}-{r_ + 1}"
                        add.append(p2)
                s_["points"] = pts + add
        return d
    for k, v in list(d.items()):
        if isinstance(v, list) and v and isinstance(v[0], dict) and len(v) < N:
            n = len(v)
            reps = max(2, round(N / max(n, 1)))
            reps = min(reps, max(2, 30 // max(n, 1)))
            out = []
            for r_ in range(reps):
                for it in v:
                    it2 = copy.deepcopy(it)
                    if r_:
                        for nk in NAME_KEYS:
                            if isinstance(it2.get(nk), str):
                                it2[nk] = f"{it2[nk]}{r_ + 1}"
                        for nk, nv in list(it2.items()):
                            if isinstance(nv, (int, float)) and not isinstance(nv, bool) and nk not in SKIP_NUM_KEYS:
                                it2[nk] = round(nv * (0.8 + 0.07 * r_), 3)
                    out.append(it2)
            d[k] = out
            return d
    return d


def variants(ex):
    yield "base", ex
    yield "long", {**ex, "data": lengthen(ex.get("data"))}
    yield "big", {**ex, "data": bignum(ex.get("data"))}
    yield "many", {**ex, "data": many(ex.get("data"))}
    yield "manybig", {**ex, "data": bignum(many(ex.get("data")))}


def run(only=None, save=None, extra_specs=None):
    specs = []
    for e in api.catalog():
        if only and e["code"] not in only:
            continue
        for vn, ex in variants(copy.deepcopy(e["example"])):
            specs.append((f"{e['code']}:{vn}", ex))
    for tag, ex in extra_specs or []:
        if only and tag.split(":")[0] not in only:
            continue
        specs.append((tag, ex))
    errs = []
    for tag, ex in specs:
        CUR["tag"] = tag
        try:
            res = api.draw(ex["type"], ex.get("data"), title=ex.get("title"), unit=ex.get("unit"), options=ex.get("options"))
            from PIL import Image
            import io as _io
            W_, H_ = Image.open(_io.BytesIO(res.png)).size
            if W_ > 3000 or H_ > 4000:
                FOUND.append({"tag": tag, "issues": [{"kind": "size", "a": f"{W_}x{H_}"}]})
            if save:
                Path(save).mkdir(parents=True, exist_ok=True)
                (Path(save) / f"{tag.replace(':', '_')}.png").write_bytes(res.png)
        except Exception as e:  # noqa: BLE001
            errs.append((tag, repr(e)[:150]))
    return specs, errs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--save")
    ap.add_argument("--extra", help="추가 명세 JSON 파일([[태그, 명세], …])")
    ap.add_argument("--json")
    a = ap.parse_args()
    extra = json.load(open(a.extra, encoding="utf-8")) if a.extra else None
    specs, errs = run(a.only, a.save, extra)
    bad = {f["tag"] for f in FOUND}
    for f in FOUND:
        kinds = {}
        for i in f["issues"]:
            kinds.setdefault(i["kind"], []).append(i)
        s = "; ".join(f"{k} {len(v)}건 (예: {v[0].get('a')!r}↔{v[0].get('b', '')!r} {v[0].get('px', '')})" for k, v in kinds.items())
        print(f"{f['tag']}\t{s}")
    print(f"\n점검 {len(specs)}건, 겹침 있는 그림 {len(bad)}건, 그리기 오류 {len(errs)}건")
    for t, e in errs:
        print("ERR", t, e)
    if a.json:
        json.dump({"found": FOUND, "errors": errs}, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
