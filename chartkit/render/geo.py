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


def _base_map(ax, fill=None, edge="white", edges=None, xlim=(124.5, 131.0)):
    geo = _geo()
    # 큰 시·도부터 칠한다 — 바깥 경계만 칠하므로 경기가 서울을, 전남이 광주를 덮지 않게(작은 시·도를 나중에)
    def area(g):
        a = np.array(max(_polys(g), key=len))
        return float((a[:, 0].max() - a[:, 0].min()) * (a[:, 1].max() - a[:, 1].min()))
    for name, g in sorted(geo.items(), key=lambda kv: -area(kv[1])):
        for ring in _polys(g):
            ax.add_patch(Polygon(np.array(ring), closed=True, facecolor=(fill or {}).get(name, "#E7EAF0"), edgecolor=(edges or {}).get(name, edge), lw=0.6))
    ax.set_xlim(*xlim)
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
        # 표시 단위(group): 통합 지역(전남광주 등)은 두 경계를 같은 색으로 칠하되 이름·순위·값은 한 번만 쓴다(2026-11-24 — 순위표에 광주·전남이 같은 값으로 두 줄 나오던 결함)
        vals, unknown, rows, groups = {}, [], [], []
        for i, r in enumerate(regs):
            r = as_dict(r, f"regions[{i}]")
            v = as_number(r.get("value"), f"regions[{i}].value")
            raw = str(r.get("name")).strip()
            names = norm_region(raw)
            if not all(n in SIDO for n in names):
                unknown.append(raw)
                continue
            for n in names:
                vals[n] = v
            label = ("전남광주" if set(names) == {"광주", "전남"} else raw.replace(" ", "")) if len(names) > 1 else names[0]
            groups.append({"label": label, "members": names, "v": v})
            rows.append([raw, v])
        if unknown:
            raise ChartInputError(f"시·도 이름을 알 수 없습니다: {', '.join(unknown)}", hint=f"다음 중 하나로 넣으세요: {', '.join(SIDO)}")
        vv = [v for v in vals.values() if v is not None]
        need(vv, "값이 있는 시·도가 없습니다")
        if o.get("diverging") or o.get("center") is not None:
            c = float(o.get("center") or 0)
            span = max(max(vv) - c, c - min(vv), 1e-9)
            cmap, norm = DIV, TwoSlopeNorm(vcenter=c, vmin=c - span, vmax=c + span)
        else:
            cmap, norm = SEQ, Normalize(min(vv) if min(vv) < 0 else 0, max(vv))
        fill, edges = {}, {}
        for n, v in vals.items():
            if v is not None:
                rgba = cmap(norm(v))
                fill[n] = "#%02X%02X%02X" % tuple(int(255 * c) for c in rgba[:3])
        for g in groups:
            if len(g["members"]) > 1:  # 통합 지역은 안쪽 경계선을 지워 한 지역으로 보이게
                for n in g["members"]:
                    if n in fill and n in ("광주",):
                        edges[n] = fill[n]
        missing = [n for n in SIDO if n not in vals]
        if missing:
            notes.append(f"값이 없는 시·도(회색): {', '.join(missing)}")
        SMALL_L = {"서울": 38.05, "인천": 37.45, "세종": 36.88, "대전": 36.08, "광주": 35.30}
        # 이끌선과 겹치지 않게 옮긴 이름 자리(경기는 서울 선, 충남은 세종·대전 선, 경북은 대구 선을 피함)
        LABEL_AT = {"경기": (127.22, 37.86), "제주": (126.55, 33.12), "충남": (126.72, 36.47), "경북": (128.78, 36.52)}
        SMALL_R = {"대구": 36.25, "울산": 35.72, "부산": 35.12}
        with figure(4.4, o) as fig:
            top = top_for(fig, title, sub, o, False)
            ax = fig.add_axes([0.02, 0.02, 0.64, top - 0.04])
            _base_map(ax, fill, edges=edges, xlim=(123.6, 131.4))
            if o.get("show_labels", True) is not False:
                for g in groups:
                    if g["v"] is None:
                        continue
                    if len(g["members"]) > 1:  # 통합 지역 — 가장 큰 경계의 가운데에 한 번
                        main = max(g["members"], key=lambda n: len(max(_polys(_geo()[n]), key=len)))
                        x, y = _centroid(main)
                        ax.text(x, y, f"{g['label']}\n{st.fmt(g['v'])}", ha="center", va="center", fontsize=6.8, color=st.ink_on(fill.get(main, "#E7EAF0")), linespacing=1.1, zorder=6)
                        continue
                    n = g["members"][0]
                    x, y = _centroid(n)
                    if n in SMALL_L or n in SMALL_R:  # 작은 시·도는 이끌선 이름표(지도 밖 왼쪽·오른쪽)
                        left = n in SMALL_L
                        lx, ly = (125.25, SMALL_L[n]) if left else (130.05, SMALL_R[n])
                        ax.plot([x, lx + (0.05 if left else -0.05)], [y, ly], color="#7F7F7F", lw=0.6, zorder=5)
                        ax.text(lx, ly, f"{n} {st.fmt(g['v'])}", ha="right" if left else "left", va="center", fontsize=6.8, color=st.INK, zorder=6)
                        continue
                    x, y = LABEL_AT.get(n, (x, y))
                    fc = fill.get(n, "#E7EAF0")  # 이름 뒤에 그 지역 색 바탕 — 경계선이 글자를 가르지 않게(제주는 섬 아래에 바탕 없이)
                    if n == "제주":
                        ax.text(x, y, f"{n} {st.fmt(g['v'])}", ha="center", va="top", fontsize=6.8, color=st.INK, zorder=6)
                        continue
                    ax.text(x, y, f"{n}\n{st.fmt(g['v'])}", ha="center", va="center", fontsize=6.8, color=st.ink_on(fc), linespacing=1.1, zorder=6,
                            bbox=dict(facecolor=fc, edgecolor="none", pad=0.15, alpha=0.95))
            tx = fig.add_axes([0.68, 0.05, 0.30, top - 0.08])
            tx.axis("off")
            ranked = sorted((g for g in groups if g["v"] is not None), key=lambda g: -g["v"])
            tx.text(0, 1, f"순위{f' ({unit})' if unit else ''}", fontsize=8, fontweight="bold", color=st.INK, va="top", transform=tx.transAxes)
            for k, g in enumerate(ranked[:17]):
                y = 0.93 - k * 0.054
                col = fill.get(g["members"][0], "#E7EAF0")
                tx.add_patch(Polygon([(0, y - 0.018), (0.06, y - 0.018), (0.06, y + 0.018), (0, y + 0.018)], closed=True, facecolor=col, transform=tx.transAxes))
                tx.text(0.09, y, f"{k + 1}. {g['label']}", fontsize=7.4, va="center", transform=tx.transAxes, color=st.INK)
                tx.text(0.72, y, st.fmt(g["v"]), fontsize=7.4, va="center", ha="right", transform=tx.transAxes, color=st.INK, fontweight="bold" if k < 3 else "normal")
            if any(len(g["members"]) > 1 for g in groups):
                notes.append("통합 지역(" + ", ".join(g["label"] for g in groups if len(g["members"]) > 1) + ")은 옛 경계 두 곳을 같은 색으로 칠하고 이름·순위는 한 번만 씁니다")
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
