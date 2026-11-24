"""대한민국 지도 — 시·도 단계구분도·거품 지도. 경계는 maps/korea_sido.geo.json(17개 시·도).

- 시·도 이름은 '서울특별시'·'서울'·'Seoul' 모두 인식한다.
- 2026-07 광주·전남 통합(전남광주통합특별시) 이름이 오면 광주·전남 두 경계를 같은 값으로 칠한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from matplotlib.collections import PatchCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize, TwoSlopeNorm
from matplotlib.patches import Polygon

from .. import style as st
from ..core import Result, figure, put_title, to_png, top_for
from ..errors import ChartInputError, as_dict, as_list, as_number, need

SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
SIDO_ALIASES = {
    "서울특별시": "서울", "서울시": "서울", "seoul": "서울",
    "부산광역시": "부산", "부산시": "부산", "busan": "부산",
    "대구광역시": "대구", "대구시": "대구", "daegu": "대구",
    "인천광역시": "인천", "인천시": "인천", "incheon": "인천",
    "광주광역시": "광주", "광주시": "광주", "gwangju": "광주",
    "대전광역시": "대전", "대전시": "대전", "daejeon": "대전",
    "울산광역시": "울산", "울산시": "울산", "ulsan": "울산",
    "세종특별자치시": "세종", "세종시": "세종", "sejong": "세종",
    "경기도": "경기", "gyeonggi": "경기", "gyeonggi-do": "경기",
    "강원도": "강원", "강원특별자치도": "강원", "gangwon": "강원",
    "충청북도": "충북", "chungbuk": "충북", "chungcheongbuk-do": "충북",
    "충청남도": "충남", "chungnam": "충남", "chungcheongnam-do": "충남",
    "전라북도": "전북", "전북특별자치도": "전북", "jeonbuk": "전북", "jeollabuk-do": "전북",
    "전라남도": "전남", "jeonnam": "전남", "jeollanam-do": "전남",
    "경상북도": "경북", "gyeongbuk": "경북", "gyeongsangbuk-do": "경북",
    "경상남도": "경남", "gyeongnam": "경남", "gyeongsangnam-do": "경남",
    "제주특별자치도": "제주", "제주도": "제주", "jeju": "제주",
}
MERGED = {"전남광주통합특별시": ["광주", "전남"], "전남광주": ["광주", "전남"], "광주전남": ["광주", "전남"]}
COORDS = {
    "서울": (126.978, 37.566), "부산": (129.075, 35.180), "대구": (128.601, 35.871), "인천": (126.705, 37.456), "광주": (126.852, 35.160),
    "대전": (127.385, 36.351), "울산": (129.311, 35.539), "세종": (127.289, 36.480), "경기": (127.009, 37.275), "강원": (127.730, 37.885),
    "충북": (127.491, 36.636), "충남": (126.673, 36.659), "전북": (127.108, 35.820), "전남": (126.463, 34.816), "경북": (128.506, 36.576),
    "경남": (128.692, 35.238), "제주": (126.531, 33.500),
    "수원": (127.029, 37.264), "성남": (127.127, 37.420), "고양": (126.832, 37.658), "용인": (127.178, 37.241), "부천": (126.766, 37.503),
    "안산": (126.831, 37.322), "안양": (126.957, 37.394), "남양주": (127.216, 37.636), "화성": (126.831, 37.199), "평택": (127.113, 36.992),
    "의정부": (127.034, 37.738), "파주": (126.780, 37.760), "김포": (126.716, 37.615), "시흥": (126.803, 37.380), "광명": (126.865, 37.479),
    "하남": (127.215, 37.539), "오산": (127.077, 37.150), "이천": (127.443, 37.272),
    "춘천": (127.730, 37.881), "원주": (127.920, 37.342), "강릉": (128.876, 37.752),
    "청주": (127.489, 36.642), "충주": (127.926, 36.991), "천안": (127.114, 36.815), "아산": (127.002, 36.790), "오송": (127.326, 36.632),
    "전주": (127.148, 35.824), "익산": (126.957, 35.948), "군산": (126.737, 35.968),
    "목포": (126.392, 34.812), "여수": (127.662, 34.760), "순천": (127.487, 34.951),
    "포항": (129.343, 36.019), "구미": (128.344, 36.120), "경주": (129.224, 35.856), "안동": (128.729, 36.568),
    "창원": (128.681, 35.228), "김해": (128.889, 35.229), "진주": (128.108, 35.180), "양산": (129.037, 35.335), "거제": (128.621, 34.880),
    "서귀포": (126.560, 33.254),
}
_GEO = None
SEQ = LinearSegmentedColormap.from_list("seq", st.SEQUENTIAL)
DIV = LinearSegmentedColormap.from_list("div", st.DIVERGING)


def _geo():
    global _GEO
    if _GEO is None:
        g = json.loads((Path(__file__).resolve().parents[1] / "maps" / "korea_sido.geo.json").read_text(encoding="utf-8"))
        _GEO = {f["properties"]["name"]: f["geometry"] for f in g["features"]}
    return _GEO


def norm_region(name) -> list[str]:
    s = str(name).strip()
    k = s.replace(" ", "")
    if k in MERGED:
        return MERGED[k]
    if s in SIDO or s in COORDS:
        return [s]
    if k.lower() in SIDO_ALIASES:
        return [SIDO_ALIASES[k.lower()]]
    if k in SIDO_ALIASES:
        return [SIDO_ALIASES[k]]
    for suf in ("특례시", "광역시", "특별시", "시", "군"):
        if s.endswith(suf) and s[: -len(suf)] in COORDS:
            return [s[: -len(suf)]]
    return [s]


def _polys(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    return [p[0] for p in geom["coordinates"]]


def _base_map(ax, fill=None, edge="white"):
    geo = _geo()
    for name, g in geo.items():
        for ring in _polys(g):
            ax.add_patch(Polygon(np.array(ring), closed=True, facecolor=(fill or {}).get(name, "#E7EAF0"), edgecolor=edge, lw=0.6))
    ax.set_xlim(124.5, 131.0)
    ax.set_ylim(33.0, 38.7)
    ax.set_aspect(1.22)
    ax.axis("off")


def _centroid(name):
    rings = _polys(_geo()[name])
    ring = max(rings, key=len)
    a = np.array(ring)
    return float(a[:, 0].mean()), float(a[:, 1].mean())


def draw(ct: str, args: dict, o: dict) -> Result:
    title, sub, unit = args.get("title"), args.get("subtitle"), args.get("unit")
    regs = as_list(args.get("regions"), "regions")
    need(regs, "regions=[{name, value}]가 필요합니다", example=[{"name": "서울", "value": 1520}])
    notes = []
    if ct == "choropleth":
        vals, unknown, rows = {}, [], []
        for i, r in enumerate(regs):
            r = as_dict(r, f"regions[{i}]")
            v = as_number(r.get("value"), f"regions[{i}].value")
            names = norm_region(r.get("name"))
            if not all(n in SIDO for n in names):
                unknown.append(str(r.get("name")))
                continue
            for n in names:
                vals[n] = v
            rows.append([str(r.get("name")), v])
        if unknown:
            raise ChartInputError(f"시·도 이름을 알 수 없습니다: {', '.join(unknown)}", hint=f"다음 중 하나로 넣으세요: {', '.join(SIDO)}")
        vv = [v for v in vals.values() if v is not None]
        if o.get("diverging") or o.get("center") is not None:
            c = float(o.get("center") or 0)
            span = max(max(vv) - c, c - min(vv), 1e-9)
            cmap, norm = DIV, TwoSlopeNorm(vcenter=c, vmin=c - span, vmax=c + span)
        else:
            cmap, norm = SEQ, Normalize(min(vv) if min(vv) < 0 else 0, max(vv))
        fill = {}
        for n, v in vals.items():
            if v is not None:
                rgba = cmap(norm(v))
                fill[n] = "#%02X%02X%02X" % tuple(int(255 * c) for c in rgba[:3])
        missing = [n for n in SIDO if n not in vals]
        if missing:
            notes.append(f"값이 없는 시·도(회색): {', '.join(missing)}")
        with figure(4.4, o) as fig:
            top = top_for(fig, title, sub, o, False)
            ax = fig.add_axes([0.05, 0.02, 0.6, top - 0.04])
            _base_map(ax, fill)
            if o.get("show_labels", True) is not False:
                for n, v in vals.items():
                    if v is None or n not in _geo():
                        continue
                    x, y = _centroid(n)
                    if n in ("서울", "인천", "대전", "광주", "대구", "울산", "부산", "세종"):
                        continue
                    ax.text(x, y, f"{n}\n{st.fmt(v)}", ha="center", va="center", fontsize=6.8, color=st.ink_on(fill.get(n, "#E7EAF0")), linespacing=1.1)
            # 작은 광역시는 오른쪽 표로
            small = [(n, vals[n]) for n in ("서울", "인천", "세종", "대전", "광주", "대구", "울산", "부산") if n in vals]
            tx = fig.add_axes([0.66, 0.05, 0.32, top - 0.08])
            tx.axis("off")
            ranked = sorted(((n, v) for n, v in vals.items() if v is not None), key=lambda p: -p[1])
            tx.text(0, 1, f"순위{f' ({unit})' if unit else ''}", fontsize=8, fontweight="bold", color=st.INK, va="top", transform=tx.transAxes)
            for k, (n, v) in enumerate(ranked[:17]):
                y = 0.93 - k * 0.054
                tx.add_patch(Polygon([(0, y - 0.018), (0.06, y - 0.018), (0.06, y + 0.018), (0, y + 0.018)], closed=True, facecolor=fill[n], transform=tx.transAxes))
                tx.text(0.09, y, n, fontsize=7.4, va="center", transform=tx.transAxes, color=st.INK)
                tx.text(0.62, y, st.fmt(v), fontsize=7.4, va="center", ha="right", transform=tx.transAxes, color=st.INK, fontweight="bold" if k < 3 else "normal")
            if small:
                notes.append("지도에 이름이 작게 보이는 광역시 값은 오른쪽 순위 표에 있습니다")
            put_title(fig, title, sub, o)
            png = to_png(fig)
        return Result(png, notes, table=(["시·도", f"값{f'({unit})' if unit else ''}"], rows))
    # bubble_map
    pts, unknown = [], []
    for i, r in enumerate(regs):
        r = as_dict(r, f"regions[{i}]")
        v = as_number(r.get("value"), f"regions[{i}].value") or 0
        name = str(r.get("name"))
        if r.get("lat") is not None and r.get("lon") is not None:
            lon, lat = as_number(r["lon"], f"regions[{i}].lon"), as_number(r["lat"], f"regions[{i}].lat")
            need(32 < lat < 39.5 and 124 < lon < 132.5, f"regions[{i}]의 좌표가 대한민국 범위를 벗어납니다(lat {lat}, lon {lon})",
                 hint="lat은 위도(33~38.6), lon은 경도(124.6~131.9)입니다")
        else:
            nm = norm_region(name)[0]
            if nm not in COORDS:
                unknown.append(name)
                continue
            lon, lat = COORDS[nm]
        pts.append((name, lon, lat, v, r.get("group")))
    if unknown:
        raise ChartInputError(f"좌표표에 없는 지역: {', '.join(unknown)}", hint="해당 항목에 lat(위도)·lon(경도)을 직접 넣으세요",
                              example=[{"name": "향남제약단지", "lat": 37.13, "lon": 126.91, "value": 120}])
    vmax = max(p[3] for p in pts) or 1
    with figure(4.4, o) as fig:
        top = top_for(fig, title, sub, o, False)
        ax = fig.add_axes([0.05, 0.02, 0.6, top - 0.04])
        _base_map(ax)
        for name, lon, lat, v, g in sorted(pts, key=lambda p: -p[3]):
            ax.scatter([lon], [lat], s=40 + 900 * v / vmax, color=st.NAVY, alpha=0.55, edgecolor="white", lw=0.8, zorder=3)
            ax.text(lon + 0.12, lat + 0.06, name, fontsize=6.8, color=st.INK, zorder=4)
        tx = fig.add_axes([0.66, 0.05, 0.32, top - 0.08])
        tx.axis("off")
        tx.text(0, 1, f"순위{f' ({unit})' if unit else ''}", fontsize=8, fontweight="bold", color=st.INK, va="top", transform=tx.transAxes)
        for k, (name, *_, v, g) in enumerate(sorted(pts, key=lambda p: -p[3])[:17]):
            y = 0.93 - k * 0.054
            tx.text(0.0, y, name, fontsize=7.4, va="center", transform=tx.transAxes, color=st.INK)
            tx.text(0.62, y, st.fmt(v), fontsize=7.4, va="center", ha="right", transform=tx.transAxes, color=st.NAVY, fontweight="bold" if k < 3 else "normal")
        put_title(fig, title, sub, o)
        png = to_png(fig)
    return Result(png, ["원 넓이가 값에 비례합니다"], table=(["지역", "경도", "위도", "값"], [[p[0], p[1], p[2], p[3]] for p in pts]))
