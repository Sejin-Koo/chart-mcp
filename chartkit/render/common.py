"""입력 정규화와 그리기 공통 조각."""
from __future__ import annotations

from typing import Any

from .. import style as st
from ..errors import ChartInputError, as_dict, as_list, as_number, need


def opts(o: Any) -> dict:
    return as_dict(o, "options") if o is not None else {}


def categories(args: dict) -> list[str]:
    cats = [str(c) for c in as_list(args.get("categories"), "categories")]
    need(len(cats) > 0, "categories(가로축 항목)가 비어 있습니다", hint="항목명 배열을 넣으세요", example=["1분기", "2분기", "3분기"])
    return cats


def series(args: dict, n: int | None = None, *, min_count: int = 1, max_count: int = 12) -> list[dict]:
    items = as_list(args.get("series"), "series")
    need(len(items) >= min_count, f"series(계열)가 {min_count}개 이상 필요합니다", example=[{"name": "매출", "values": [120, 138, 151]}])
    out = []
    for i, s in enumerate(items):
        s = as_dict(s, f"series[{i}]")
        vals = [as_number(v, f"series[{i}].values[{j}]") for j, v in enumerate(as_list(s.get("values", s.get("data")), f"series[{i}].values"))]
        if n is not None and len(vals) != n:
            raise ChartInputError(f"series[{i}]('{s.get('name', '')}')의 값 개수 {len(vals)}가 categories 개수 {n}와 다릅니다",
                                  hint="categories 순서대로 값을 하나씩 넣고, 값이 없으면 null을 넣으세요")
        d = dict(s)
        d["name"] = str(s.get("name") or f"계열{i + 1}")
        d["values"] = vals
        out.append(d)
    need(len(out) <= max_count, f"계열이 {len(out)}개로 너무 많습니다(최대 {max_count}개)", hint="작은 계열을 '기타'로 묶거나 그림을 나누세요")
    return out


def colors_for(ser: list[dict], *, wide: bool = False) -> list[str]:
    base = st.palette(len(ser), wide=wide)
    return [st.color(s.get("color"), base[i]) for i, s in enumerate(ser)]


def color_warn(n: int) -> list[str]:
    return [f"계열·조각이 {n}개로 6색을 넘습니다. 7번째부터 회색 단계로 그렸습니다 — 작은 항목은 '기타'로 묶는 것을 권합니다"] if n > st.MAX_COLORS else []


def nums(v: Any, where: str) -> list[float | None]:
    return [as_number(x, f"{where}[{i}]") for i, x in enumerate(as_list(v, where))]


def table_from_series(cats, ser, first="구분"):
    head = [first] + [s["name"] for s in ser]
    rows = [[c] + [s["values"][i] for s in ser] for i, c in enumerate(cats)]
    return head, rows


def target_lines(o: dict) -> list[dict]:
    out = []
    for i, t in enumerate(as_list(o.get("target_lines"), "options.target_lines")):
        t = {"value": t} if isinstance(t, (int, float, str)) else as_dict(t, f"target_lines[{i}]")
        out.append({"value": as_number(t.get("value"), f"target_lines[{i}].value"), "label": t.get("label") or "", "color": st.color(t.get("color"), st.INK2)})
    return out


def bands(o: dict) -> list[dict]:
    out = []
    for i, b in enumerate(as_list(o.get("bands"), "options.bands")):
        b = as_dict(b, f"bands[{i}]")
        out.append({"from": as_number(b.get("from"), f"bands[{i}].from"), "to": as_number(b.get("to"), f"bands[{i}].to"), "label": b.get("label") or "",
                    "color": st.color(b.get("color"), "#E6F2EE")})
    return out


def label_mode(o: dict, n_points: int, n_series: int) -> str:
    m = str(o.get("labels") or "").lower()
    if m in ("all", "last", "none"):
        return m
    if o.get("show_values") is False:
        return "none"
    return "all" if (n_points <= 8 and n_series <= 3) else "last"


def decimals_of(values) -> int:
    vals = [v for v in values if v is not None]
    if not vals:
        return 0
    if all(float(v).is_integer() for v in vals):
        return 0
    return 1 if max(abs(v) for v in vals) >= 1 else 2
