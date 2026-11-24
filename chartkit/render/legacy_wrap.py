"""원본 matplotlib 엔진(임상·오믹스·특수 차트)을 chartkit 결과 형식으로 감싼다."""
from __future__ import annotations

from ..core import Result
from .legacy import _core


def _flatten(data: dict):
    """입력 data에서 엑셀에 넣을 표를 만든다 — 첫 번째 '객체 배열' 키를 펼치고, 같은 길이 배열은 행으로 늘린다."""
    for key, v in data.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            scalar_keys, array_keys = [], []
            for it in v:
                for k, x in it.items():
                    if isinstance(x, list):
                        if k not in array_keys:
                            array_keys.append(k)
                    elif k not in scalar_keys:
                        scalar_keys.append(k)
            head = scalar_keys + array_keys
            rows = []
            for it in v:
                arrs = [it.get(k) if isinstance(it.get(k), list) else [] for k in array_keys]
                n = max([len(a) for a in arrs] + [1])
                for i in range(n):
                    row = [it.get(k) for k in scalar_keys]
                    for a in arrs:
                        x = a[i] if i < len(a) else None
                        row.append(x if not isinstance(x, (list, dict)) else str(x))
                    rows.append(row)
            return head, rows
        if isinstance(v, dict) and v and all(isinstance(x, list) for x in v.values()):  # venn sets 등
            keys = list(v)
            n = max(len(v[k]) for k in keys)
            return keys, [[(v[k][i] if i < len(v[k]) else None) for k in keys] for i in range(n)]
    if all(isinstance(data.get(k), list) for k in ("x", "y")):  # surface·contour
        z = data.get("z") or []
        return ["y \\ x"] + list(data["x"]), [[y] + list(z[i] if i < len(z) else []) for i, y in enumerate(data["y"])]
    return ["키", "값"], [[k, str(v)] for k, v in data.items() if k not in ("title", "subtitle", "unit")]


def make(module):
    def draw(ct: str, args: dict, o: dict) -> Result:
        data = {k: v for k, v in args.items() if k not in ("title", "subtitle", "unit", "options")}
        tok = _core.SHOW_TITLE.set(bool(o.get("show_title")))
        tok2 = _core.SIZE.set((float(o["width_in"]) * 1.2, float(o["height_in"]) * 1.2) if o.get("width_in") and o.get("height_in") else None)
        try:
            res, warns, meta = module.render(ct, data, args.get("title"), args.get("subtitle"), o, None, None)
        finally:
            _core.SHOW_TITLE.reset(tok)
            _core.SIZE.reset(tok2)
        return Result(res["png"], warns, meta, table=_flatten(data))
    return draw
