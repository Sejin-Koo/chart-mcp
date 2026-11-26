"""업무 에이전트가 쓴 옛 형식 그림 → 이 서버 차트(1.6.0, 2026-11-26). 목록에는 싣지 않는다.

계정 채팅·업무 에이전트 모두 ```chart 블록에 ECharts 설정(option)이나 기본 산점도(type scatter)를 쓴 적이 있다.
그 형식을 이 서버 차트 입력으로 바꿔 그린다 — 화면(ECharts)마다 모양이 다르던 것을 서버 그림 한 가지로 맞추려는 것.
data에는 ```chart 블록 JSON을 그대로 넣는다(title·unit·option 또는 type·series). 바꿀 수 없는 모양이면 입력 오류(그리지 않음)."""
from __future__ import annotations

from ..errors import ChartInputError


def _num(v):
    try:
        if isinstance(v, dict):
            v = v.get("value")
        if isinstance(v, (list, tuple)):
            v = v[-1]
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _axis_data(ax):
    if isinstance(ax, list):
        ax = ax[0] if ax else {}
    d = (ax or {}).get("data") if isinstance(ax, dict) else None
    return [x.get("value", x.get("name")) if isinstance(x, dict) else x for x in (d or [])]


def _axis_name(ax):
    if isinstance(ax, list):
        ax = ax[0] if ax else {}
    return (ax or {}).get("name") if isinstance(ax, dict) else None


def _scatter(series, x_label=None, y_label=None):
    out = []
    for s in series:
        pts = []
        for p in s.get("data") or []:
            name = None
            if isinstance(p, dict):
                name, p = p.get("name"), p.get("value")
            if isinstance(p, (list, tuple)) and len(p) >= 2 and _num(p[0]) is not None and _num(p[1]) is not None:
                pt = {"x": _num(p[0]), "y": _num(p[1])}
                if name:
                    pt["label"] = str(name)
                pts.append(pt)
        if pts:
            out.append({"name": str(s.get("name") or "값"), "points": pts})
    if not out:
        raise ChartInputError("산점도 점이 없습니다")
    d = {"series": out}
    if x_label:
        d["x_label"] = str(x_label)
    if y_label:
        d["y_label"] = str(y_label)
    return "D-05", d, {}


def _tree_items(nodes, parent=None, out=None):
    out = [] if out is None else out
    for n in nodes or []:
        if not isinstance(n, dict) or not n.get("name"):
            continue
        it = {"name": str(n["name"])}
        if parent:
            it["parent"] = parent
        kids = n.get("children") or []
        if not kids and _num(n.get("value")) is not None:
            it["value"] = _num(n.get("value"))
        out.append(it)
        _tree_items(kids, it["name"], out)
    return out


def convert(spec: dict):
    """(차트 코드, data, options) — 못 바꾸면 ChartInputError."""
    opt = spec.get("option")
    if not isinstance(opt, dict):
        if str(spec.get("type") or "") == "scatter" and isinstance(spec.get("series"), list):
            return _scatter(spec["series"], spec.get("x_label") or spec.get("xAxisTitle"), spec.get("y_label") or spec.get("axisTitle"))
        raise ChartInputError("option(ECharts 설정)이나 산점도가 아닙니다")
    series = opt.get("series") or []
    if isinstance(series, dict):
        series = [series]
    types = {str((s or {}).get("type") or "") for s in series}
    if not series or len(types) != 1:
        raise ChartInputError("계열 종류가 하나인 option만 바꿉니다")
    t = types.pop()
    s0 = series[0]
    if t == "scatter":
        return _scatter(series, _axis_name(opt.get("xAxis")), _axis_name(opt.get("yAxis")))
    if t == "heatmap":
        cols, rows = _axis_data(opt.get("xAxis")), _axis_data(opt.get("yAxis"))
        if not cols or not rows:
            raise ChartInputError("히트맵 축 이름이 없습니다")
        vals = [[None] * len(cols) for _ in rows]
        for p in s0.get("data") or []:
            v = p.get("value") if isinstance(p, dict) else p
            if isinstance(v, (list, tuple)) and len(v) >= 3:
                xi, yi = v[0], v[1]
                xi = cols.index(xi) if not isinstance(xi, (int, float)) and xi in cols else xi
                yi = rows.index(yi) if not isinstance(yi, (int, float)) and yi in rows else yi
                if isinstance(xi, (int, float)) and isinstance(yi, (int, float)) and 0 <= int(yi) < len(rows) and 0 <= int(xi) < len(cols):
                    vals[int(yi)][int(xi)] = _num(v[2])
        return "F-09", {"rows": [str(r) for r in rows], "columns": [str(c) for c in cols], "values": vals}, {}
    if t == "radar":
        rad = opt.get("radar") or {}
        if isinstance(rad, list):
            rad = rad[0] if rad else {}
        ind = rad.get("indicator") or []
        cats = [str(i.get("name") if isinstance(i, dict) else i) for i in ind]
        mx = [_num(i.get("max")) for i in ind if isinstance(i, dict) and _num(i.get("max")) is not None]
        ser = []
        for s in series:
            for k, d in enumerate(s.get("data") or []):
                v = d.get("value") if isinstance(d, dict) else d
                if isinstance(v, (list, tuple)):
                    ser.append({"name": str((d.get("name") if isinstance(d, dict) else None) or s.get("name") or f"계열{k + 1}"), "values": [_num(x) for x in v]})
        if not cats or not ser:
            raise ChartInputError("레이더 항목·값이 없습니다")
        return "E-07", {"categories": cats, "series": ser}, ({"max": max(mx)} if mx else {})
    if t == "funnel":
        data = [d for d in (s0.get("data") or []) if isinstance(d, dict) and _num(d.get("value")) is not None]
        data.sort(key=lambda d: -_num(d.get("value")))
        if not data:
            raise ChartInputError("깔때기 값이 없습니다")
        return "C-13", {"categories": [str(d.get("name")) for d in data], "series": [{"name": str(s0.get("name") or "값"), "values": [_num(d["value"]) for d in data]}]}, {}
    if t == "gauge":
        d = (s0.get("data") or [{}])[0]
        v = _num(d)
        if v is None:
            raise ChartInputError("게이지 값이 없습니다")
        o = {}
        if isinstance(d, dict) and d.get("name"):
            o["label"] = str(d["name"])
        if _num(s0.get("max")) is not None:
            o["max"] = _num(s0.get("max"))
        return "F-01", {"value": v}, o
    if t == "treemap" or t == "sunburst":
        items = _tree_items(s0.get("data") or [])
        if not items:
            raise ChartInputError("트리맵 항목이 없습니다")
        return ("C-08" if t == "treemap" else "sunburst"), {"items": items}, {}
    if t == "sankey":
        links = [{"source": str(l.get("source")), "target": str(l.get("target")), "value": _num(l.get("value"))}
                 for l in (s0.get("links") or s0.get("edges") or []) if isinstance(l, dict) and _num(l.get("value")) is not None]
        if not links:
            raise ChartInputError("생키 연결이 없습니다")
        return "E-01", {"links": links}, {}
    raise ChartInputError(f"바꿀 수 없는 option 종류: {t}")


def draw(ct: str, args: dict, o: dict):
    from .. import api
    code, data, extra = convert(args)
    r = api.draw(code, data, title=args.get("title"), unit=args.get("unit"), options={**extra, **(o or {})})
    r.notes.append(f"옛 형식 그림을 서버 차트 {code}로 바꿔 그렸습니다")
    return r
