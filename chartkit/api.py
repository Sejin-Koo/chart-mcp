"""차트 그리기 입구 — 종류(코드·이름) 확인, 입력 정리, 그리기, 엑셀 원본.

    from chartkit import api
    r = api.draw("R-05", data={...}, title="...", unit="...", options={...})
    r.png  # bytes
    api.to_xlsx(r)  # bytes (엑셀 원본)
"""
from __future__ import annotations

import importlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .core import Result, setup_fonts
from .errors import ChartInputError, as_dict

GROUPS = {"category", "xy", "distribution", "matrix", "hierarchy", "flow", "timeline", "geo", "finance", "clinical", "omics", "misc"}


@lru_cache(maxsize=1)
def catalog() -> list[dict]:
    return json.loads((Path(__file__).parent / "catalog.json").read_text(encoding="utf-8"))


def _index():
    by_code, by_type = {}, {}
    for e in catalog():
        by_code[e["code"].upper()] = e
        by_type.setdefault(e["chart_type"], e)
    return by_code, by_type


# 원본 도구의 chart_type 이름 중 카탈로그 예시와 다른 이름으로도 부를 수 있게(같은 모듈이 그린다)
EXTRA_TYPES = {
    "line_band": "category", "line": "category", "line_marker": "category", "area": "category", "bar": "category", "bar_stacked": "category",
    "bar_percent": "category", "hbar": "category", "hbar_stacked": "category", "pie": "category", "donut": "category", "radar": "category",
    "histogram": "distribution", "progress": "finance", "scatter": "xy",
    # 1.5.0: 업무 에이전트 기본 그래프 — 계정 Word 그래프 코드 사본(입력은 중계 서버의 pngInput 결과, 목록에는 싣지 않음)
    "acct_basic": "acct",
    # 1.6.0: ```chart 블록의 ECharts option·기본 산점도를 서버 차트로 바꿔 그림(목록에는 싣지 않음)
    "compat": "compat",
}


def resolve(type_: str) -> tuple[str, str, dict | None]:
    """'R-05'·'km'·'카플란' 같은 값을 (모듈, chart_type, 카탈로그 항목)으로."""
    t = str(type_ or "").strip()
    by_code, by_type = _index()
    if t.upper() in by_code:
        e = by_code[t.upper()]
        return e["group"], e["chart_type"], e
    if t in by_type:
        e = by_type[t]
        return e["group"], t, e
    if t in EXTRA_TYPES:
        return EXTRA_TYPES[t], t, None
    for e in catalog():
        if t and (t in e["name"] or e["name"] in t):
            return e["group"], e["chart_type"], e
    raise ChartInputError(f"알 수 없는 차트 종류: {t!r}", hint="list_chart_types로 코드(예: R-05)나 chart_type(예: km)을 확인하세요")


def draw(type_: str, data: Any = None, *, title: str | None = None, subtitle: str | None = None, unit: str | None = None,
         options: Any = None, **extra) -> Result:
    group, ct, entry = resolve(type_)
    d = as_dict(data, "data") if data is not None else {}
    o = as_dict(options, "options") if options is not None else {}
    args = {**d, **{k: v for k, v in extra.items() if v is not None}}
    for k, v in (("title", title), ("subtitle", subtitle), ("unit", unit)):
        if v is not None:
            args[k] = v
    mod = importlib.import_module(f".render.{group}", __package__)
    from . import declutter
    tok_n, tok_e = declutter.NOTES.set([]), declutter.ENABLED.set(o.get("declutter", True) is not False)
    try:
        r = mod.draw(ct, args, o)
        dnotes = declutter.NOTES.get() or []
    finally:
        declutter.NOTES.reset(tok_n)
        declutter.ENABLED.reset(tok_e)
    for n_ in dnotes:
        if n_ not in r.notes:
            r.notes.append(n_)
    r.meta = {"code": entry["code"] if entry else None, "chart_type": ct, "name": entry["name"] if entry else ct, "group": group,
              "title": title, "unit": unit, "args": args, "options": o}
    fs = setup_fonts()
    if fs.get("warning"):
        r.notes.append(fs["warning"])
    return r


def list_types(code: str | None = None, tag: str | None = None) -> list[dict] | dict:
    if code:
        _, _, e = resolve(code)
        if e is None:
            raise ChartInputError(f"{code!r}는 카탈로그 코드가 아닙니다")
        return e
    out = []
    for e in catalog():
        if tag and tag not in e["tags"] and tag not in e["name"]:
            continue
        # 쓰임(when)·유의점(avoid — 이럴 때는 다른 차트): 차트를 고를 때 보는 판단 근거(2026-11-24, '보고서 차트 75종 활용 가이드'에서 옮김)
        out.append({k: e[k] for k in ("code", "chart_type", "name", "use", "when", "avoid", "tags") if k in e})
    return out


def to_xlsx(r: Result) -> bytes:
    from .excel import build
    return build(r)
