"""엑셀 원본 — 자료 표 + (만들 수 있으면) 고칠 수 있는 엑셀 차트, 못 만들면 그림.

시트 '차트' 구성: 1행 제목, 2행 단위·안내, 4행부터 자료 표. 표 오른쪽에 차트(또는 그림).
행렬형(히트맵·민감도·상관·지도 값)은 표 자체에 색 단계(조건부 서식)를 입혀 고칠 수 있게 한다.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.chart import (AreaChart, BarChart, BubbleChart, DoughnutChart, LineChart, PieChart, RadarChart, Reference, ScatterChart,
                            Series, StockChart, SurfaceChart, SurfaceChart3D)
from openpyxl.chart.axis import ChartLines
from openpyxl.chart.data_source import NumDataSource, NumRef
from openpyxl.chart.error_bar import ErrorBars
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.marker import Marker
from openpyxl.chart.series import DataPoint
from openpyxl.chart.trendline import Trendline
from openpyxl.chart.updown_bars import UpDownBars
from openpyxl.drawing.image import Image as XLImage
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import style as st

FONT = "맑은 고딕"
HEAD_FILL = PatternFill("solid", fgColor="2E5395")
THIN = Side(style="thin", color="BFBFBF")
PAL = [c.lstrip("#") for c in st.PALETTE]
T0 = 4  # 표 머리행


def _hex(c):
    return str(c).lstrip("#").upper()


def _write_table(ws, head, rows, r0=T0, c0=1):
    for j, h in enumerate(head):
        cell = ws.cell(r0, c0 + j, h)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            if isinstance(v, (datetime, date)):
                v = v.isoformat()
            cell = ws.cell(r0 + 1 + i, c0 + j, v)
            cell.font = Font(name=FONT, size=10)
            cell.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cell.number_format = "#,##0" if float(v).is_integer() and abs(v) >= 1 else "#,##0.0#"
                cell.alignment = Alignment(horizontal="right")
            else:
                cell.alignment = Alignment(horizontal="left" if j == 0 else "center")
    for j, h in enumerate(head):
        w = max([len(str(h))] + [len(str(r[j])) if j < len(r) and r[j] is not None else 0 for r in rows[:200]])
        ws.column_dimensions[get_column_letter(c0 + j)].width = min(28, max(8, w * 1.6 + 2))
    return r0 + len(rows)


def _style_chart(ch, title=None, w=17, h=9):
    ch.width, ch.height = w, h
    if title:
        ch.title = title
    if getattr(ch, "legend", None) is not None:
        ch.legend.position = "t"
    return ch


def _color(s, c, line=False, fill=True):
    if fill:
        s.graphicalProperties.solidFill = c
    s.graphicalProperties.line.solidFill = c
    if line:
        s.graphicalProperties.line.width = 22000


def _labels(s, pos=None, num="#,##0"):
    s.dLbls = DataLabelList()
    s.dLbls.showVal = True
    s.dLbls.showSerName = s.dLbls.showCatName = s.dLbls.showLegendKey = s.dLbls.showPercent = False
    s.dLbls.numFmt = num
    if pos:
        s.dLbls.position = pos


def _nice(lo, hi, n=5):
    """축 최소값·눈금 간격을 1·2·2.5·5×10^k로(예: 47,900 → 46,000·2,000)."""
    import math
    span = (hi - lo) or abs(hi) or 1
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m for m in (1, 2, 2.5, 5, 10) if m * mag >= raw) * mag
    return math.floor(lo / step) * step, step


_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date_cells(ws, col, r0, r1):
    """열의 값이 모두 'YYYY-MM-DD' 글자이면 날짜 셀로 바꾸고 짧은 표시 형식을 준다(2026-11-24 — 엑셀 축에 '2026-01-01'이 그대로 찍혀 길었다).
    달 첫날뿐이면 yyyy.mm, 한 해 안이면 m/d, 여러 해면 yy.m.d. 돌려준 형식을 항목 축에도 쓴다."""
    vals = [ws.cell(r, col).value for r in range(r0, r1 + 1)]
    if not vals or not all(isinstance(v, str) and _ISO.match(v) for v in vals):
        return None
    ds = [date.fromisoformat(v) for v in vals]
    fmt = "yyyy.mm" if all(d.day == 1 for d in ds) else ("m/d" if len({d.year for d in ds}) == 1 else "yy.m.d")
    for r, d in zip(range(r0, r1 + 1), ds):
        c = ws.cell(r, col, d)
        c.number_format = fmt
        c.alignment = Alignment(horizontal="left")
    return fmt


def _ref(ws, c1, r1, c2=None, r2=None):
    return Reference(ws, min_col=c1, min_row=r1, max_col=c2 or c1, max_row=r2 or r1)


def _picture(ws, png, anchor):
    img = XLImage(io.BytesIO(png))
    ratio = 640 / img.width
    img.width, img.height = 640, int(img.height * ratio)
    ws.add_image(img, anchor)


def _show_axes(ch):
    """openpyxl 3.1은 축의 delete 값을 비워 두면 XML에 쓰지 않고, Excel은 그 축을 '삭제됨'으로 읽어 숨긴다
    (LibreOffice는 그대로 보여 줘 점검에서 안 보였다 — 2026-11-24 사용자 Excel 실측: 간트 축이 없음).
    일부러 숨긴 축(delete=True)만 두고 나머지는 모두 delete=False로 적는다. 합친 차트(bar += line)의 축도 같다."""
    for c in [ch] + list(getattr(ch, "_charts", []) or []):
        for nm in ("x_axis", "y_axis", "z_axis"):
            ax = getattr(c, nm, None)
            if ax is not None and getattr(ax, "delete", None) is None:
                try:
                    ax.delete = False
                except Exception:  # noqa: BLE001
                    pass
            # 주 눈금선: 연한 회색(D9D9D9 — Excel '배경 1, 15% 더 어둡게') 실선 0.75pt(사용자 지정 2026-11-24 — 엑셀·PPT·그림 통일)
            gl = getattr(ax, "majorGridlines", None) if ax is not None else None
            if gl is not None:
                from openpyxl.chart.shapes import GraphicalProperties
                from openpyxl.drawing.line import LineProperties
                gl.spPr = GraphicalProperties(ln=LineProperties(solidFill="D9D9D9", prstDash="solid", w=9525))


_C15 = "http://schemas.microsoft.com/office/drawing/2012/chart"


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ink(hexc):
    """막대·조각 색 위 글자색 — 파일 변환기 chart-spec.js inkOn과 같은 식(상대 휘도 0.36 초과면 짙은 회색, 아니면 흰색)."""
    h = (hexc or "").lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", h):
        return "262626"
    c = []
    for i in (0, 2, 4):
        v = int(h[i:i + 2], 16) / 255
        c.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    return "262626" if lum > 0.36 else "FFFFFF"


_A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'


def _txpr(color):
    return (f'<txPr {_A}><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
            f'</a:defRPr></a:pPr><a:endParaRPr lang="ko-KR"/></a:p></txPr>')


def _ser_fill(ser):
    """계열 자체 spPr(점·라벨·표식의 spPr 제외)의 채움: ('none'|'rgb'|'alpha'|None, 색)."""
    m = re.match(r"<idx val=\"\d+\"\s*/><order val=\"\d+\"\s*/>(?:<tx>.*?</tx>)?<spPr>(.*?)</spPr>", ser, re.S)
    if not m:
        return None, None
    sp = m.group(1)
    if re.match(r"<a:noFill\s*/>", sp):
        return "none", None
    f = re.match(r"<a:solidFill><a:srgbClr val=\"(\w+)\"\s*(/>|>(.*?)</a:srgbClr>)", sp, re.S)
    if f:
        return ("alpha" if f.group(3) and "alpha" in f.group(3) else "rgb"), f.group(1)
    return None, None


def _points(ser):
    out = {}
    for d in re.findall(r"<dPt>(.*?)</dPt>", ser, re.S):
        i = int(re.search(r"<idx val=\"(\d+)\"", d).group(1))
        if re.search(r"<spPr><a:noFill", d):
            out[i] = None
        else:
            f = re.search(r"<spPr><a:solidFill><a:srgbClr val=\"(\w+)\"", d)
            out[i] = f.group(1) if f else ""
    return out


def _set_axis(x, axid, fn):
    def rep(m):
        if re.search(rf"<axId val=\"{axid}\"", m.group(2)[:40]):
            return f"<{m.group(1)}>{fn(m.group(2))}</{m.group(1)}>"
        return m.group(0)
    return re.sub(r"<(catAx|valAx|dateAx|serAx)>(.*?)</\1>", rep, x, flags=re.S)


def _crosses_max(body):
    body = re.sub(r"<crosses(?:At)? val=\"[^\"]*\"\s*/>", "", body)
    return re.sub(r"(<crossAx val=\"\d+\"\s*/>)", r'\1<crosses val="max"/>', body, 1)


def _tick_low(pos):
    def f(body):
        if "<tickLblPos" in body:
            return re.sub(r"<tickLblPos val=\"\w+\"\s*/>", f'<tickLblPos val="{pos}"/>', body)
        ends = [m.end() for p in (r"</majorGridlines>", r"</minorGridlines>", r"</title>", r"<numFmt [^>]*/>", r"<majorTickMark [^>]*/>",
                                  r"<minorTickMark [^>]*/>", r"<axPos [^>]*/>") for m in re.finditer(p, body)]
        i = max(ends)
        return body[:i] + f'<tickLblPos val="{pos}"/>' + body[i:]
    return f


def polish_chart_xml(x: str) -> str:
    """읽기 좋게 다듬기(1.3.0 — 2026-11-24 사용자 Excel 점검: 범례가 그림 위에 겹침, 남색 막대 위 검은 숫자 등).
    - 숫자 형식: openpyxl은 numFmt의 필수 속성 sourceLinked를 빼고 써 Excel이 형식을 무시한다("1000" — 쉼표 없음).
    - 제목·범례: overlay가 없으면 Excel은 그림 영역 위에 겹쳐 그린다 → overlay 0.
    - 투명 보조 계열(폭포·간트·깔때기 바닥, 반원 도넛의 숨긴 반원)은 범례·라벨에서 뺀다.
    - 막대·영역·원 안쪽 라벨은 칠한 색에 따라 흰색/짙은 회색(파일 변환기 inkOn과 같은 식).
    - 꺾은선·분산형 계열의 smooth가 없으면 0(곡선으로 보이지 않게).
    - 막대 위에 겹친 영역(콤보)·채워진 방사형·거품은 반투명.
    - 항목 축 글자는 늘 아래·왼쪽(음수가 있어도 그림 안으로 들어가지 않게), 순서를 뒤집은 가로 막대의 값 축·뒤집은 값 축의 항목 축은 반대쪽 끝으로.
    - 누적 꺾은선 라벨은 맨 위 계열만 위, 나머지는 아래(같은 항목에서 겹치지 않게)."""
    # 숫자 형식
    x = re.sub(r"<numFmt formatCode=\"([^\"]*)\"\s*/>", r'<numFmt formatCode="\1" sourceLinked="0"/>', x)
    # 제목 겹침
    def title(m):
        b = m.group(1)
        if "<overlay" in b:
            return m.group(0)
        k = min([i for i in (b.find("<spPr"), b.find("<txPr")) if i >= 0] or [len(b)])
        return "<title>" + b[:k] + '<overlay val="0"/>' + b[k:] + "</title>"
    x = re.sub(r"<title>(.*?)</title>", title, x, flags=re.S)

    hidden_entries = []
    pie_like = ("pieChart", "pie3DChart", "doughnutChart", "ofPieChart")

    def group(m):
        typ, body = m.group(1), m.group(2)
        grouping = (re.search(r"<grouping val=\"(\w+)\"", body) or [None, ""])[1]
        bardir = (re.search(r"<barDir val=\"(\w+)\"", body) or [None, ""])[1]
        sers = re.findall(r"<ser>.*?</ser>", body, re.S)
        overlay_bar = typ == "areaChart" and "<barChart>" in x
        new = []
        for k, ser in enumerate(sers):
            s = ser[5:-6]
            kind, col = _ser_fill(s)
            sid = int(re.search(r"<idx val=\"(\d+)\"", s).group(1))
            pts = _points(s)
            if typ in pie_like:
                for i, c in pts.items():
                    if c is None:
                        hidden_entries.append(i)
            elif kind == "none":
                hidden_entries.append(sid)
            # 반투명
            alpha = None
            if overlay_bar:
                alpha = 45000
            elif typ == "radarChart" and 'radarStyle val="filled"' in body:
                alpha = 50000
            elif typ == "bubbleChart":
                alpha = 75000
            if alpha and kind == "rgb":
                s = re.sub(r"(<spPr><a:solidFill>)<a:srgbClr val=\"(\w+)\"\s*/>", rf'\1<a:srgbClr val="\2"><a:alpha val="{alpha}"/></a:srgbClr>', s, 1)
                if typ == "bubbleChart":
                    s = re.sub(r"(</a:solidFill><a:ln[^>]*>)<a:solidFill><a:srgbClr val=\"\w+\"\s*/>", r'\1<a:solidFill><a:srgbClr val="FFFFFF"/>', s, 1)
                kind = "alpha"
            # 곡선 끄기
            if typ in ("lineChart", "scatterChart") and "<smooth" not in s:
                # 계열 끝의 extLst(셀 값 라벨 범위) 앞 — 라벨(dLbl) 안의 extLst 앞에 넣으면 규격 위반(1.3.2)
                i = s.rfind("<extLst>") if s.endswith("</extLst>") else -1
                s = (s[:i] + '<smooth val="0"/>' + s[i:]) if i >= 0 else s + '<smooth val="0"/>'
            # 누적 꺾은선 라벨 자리
            if typ == "lineChart" and grouping in ("stacked", "percentStacked") and "<dLbls>" in s:
                pos = "t" if (grouping == "stacked" and k == len(sers) - 1) else "b"
                s = re.sub(r"<dLblPos val=\"\w+\"\s*/>", f'<dLblPos val="{pos}"/>', s)
            # 라벨 글자색
            dm = re.search(r"<dLbls>(.*?)</dLbls>", s, re.S)
            if dm and "<txPr" not in dm.group(1) and "<delete val=\"1\"" not in dm.group(1):
                d = dm.group(1)
                pos = (re.search(r"<dLblPos val=\"(\w+)\"", d) or [None, None])[1]
                if typ in ("pieChart", "pie3DChart", "ofPieChart") and pos is None:
                    pos = "ctr"
                    d = re.sub(r"(<showLegendKey)", r'<dLblPos val="ctr"/>\1', d, 1)
                inside = (typ in ("areaChart", "doughnutChart") or typ in pie_like and pos in ("ctr", "inEnd", "bestFit")
                          or typ == "barChart" and (pos in ("ctr", "inEnd", "inBase") or (pos is None and grouping in ("stacked", "percentStacked"))))
                if inside:
                    def ink(c):
                        return "262626" if (c is None or kind == "alpha") else _ink(c)
                    base = ink(col if kind in ("rgb", "alpha") else None)
                    inks = {i: ("262626" if c is None else (ink(c) if c else base)) for i, c in pts.items()}
                    head = ""
                    nf = (re.search(r"<numFmt [^>]*/>", d) or [""])[0]
                    show = "".join(re.findall(r"<show\w+ val=\"\d\"\s*/>", d))
                    pz = f'<dLblPos val="{pos}"/>' if (pos and "dLblPos" in d) else ""
                    for i in sorted(pts):
                        if pts[i] is None:
                            head += f'<dLbl><idx val="{i}"/><delete val="1"/></dLbl>'
                        elif inks[i] != base:
                            head += f'<dLbl><idx val="{i}"/>{nf}{_txpr(inks[i])}{pz}{show}</dLbl>'
                    j = max([mm.end() for mm in re.finditer(r"<numFmt [^>]*/>|<spPr>.*?</spPr>", d, re.S)] or [0])
                    d = head + d[:j] + _txpr(base) + d[j:]
                    s = s[:dm.start(1)] + d + s[dm.end(1):]
                elif d != dm.group(1):
                    s = s[:dm.start(1)] + d + s[dm.end(1):]
            new.append("<ser>" + s + "</ser>")
        for old, nw in zip(sers, new):
            body = body.replace(old, nw, 1)
        return f"<{typ}>{body}</{typ}>"

    x = re.sub(r"<(\w+Chart)>(.*?)</\1>", group, x, flags=re.S)

    # 범례: 겹치지 않게 + 투명 계열 빼기
    def legend(m):
        b = m.group(1)
        pm = re.match(r"<legendPos val=\"\w+\"\s*/>", b)
        p = pm.group(0) if pm else ""
        rest = b[len(p):]
        ent = "".join(f'<legendEntry><idx val="{i}"/><delete val="1"/></legendEntry>' for i in sorted(set(hidden_entries))
                      if f'<legendEntry><idx val="{i}"' not in rest)
        if "<overlay" not in rest:
            k = min([i for i in (rest.find("<spPr"), rest.find("<txPr")) if i >= 0] or [len(rest)])
            rest = rest[:k] + '<overlay val="0"/>' + rest[k:]
        return "<legend>" + p + ent + rest + "</legend>"
    x = re.sub(r"<legend>(.*?)</legend>", legend, x, flags=re.S)

    # 축 글자 자리
    axes = {}
    for m in re.finditer(r"<(catAx|valAx|dateAx|serAx)>(.*?)</\1>", x, re.S):
        b = m.group(2)
        axes[re.search(r"<axId val=\"(\d+)\"", b).group(1)] = (m.group(1), "maxMin" in b, 'delete val="1"' in b)
    for typ, body in re.findall(r"<(barChart|lineChart|areaChart|stockChart)>(.*?)</\1>", x, re.S):
        ids = re.findall(r"<axId val=\"(\d+)\"", body)
        if len(ids) != 2 or ids[0] not in axes or ids[1] not in axes:
            continue
        cat, val = ids
        if axes[cat][0] not in ("catAx", "dateAx") or axes[val][0] != "valAx":
            continue
        bardir = (re.search(r"<barDir val=\"(\w+)\"", body) or [None, ""])[1]
        if axes[cat][1] and bardir == "bar" and not axes[val][2]:
            x = _set_axis(x, val, _crosses_max)
        if axes[val][1] and not axes[cat][2]:
            x = _set_axis(x, cat, _crosses_max)
        elif not axes[cat][2]:
            x = _set_axis(x, cat, _tick_low("low"))
    return x


_ERRBAR_ORDER = ("errDir", "errBarType", "errValType", "noEndCap", "plus", "minus", "val", "spPr")


def fix_chart_xml(x: str) -> str:
    """openpyxl 3.1이 Excel 규격과 다르게 쓰는 차트 XML을 바로잡는다(1.2.7~1.2.9).
    - 오차막대: openpyxl은 <minus>를 <plus>보다 먼저 쓴다(규격은 plus → minus). Excel은 '내용에 문제가 있습니다 — 복구'를 띄운다.
    - 분산형: openpyxl은 scatterStyle을 비워 두면 쓰지 않는데 규격상 필수 요소다. 맨 앞에 lineMarker를 넣는다(선·표식은 계열 서식이 정함)."""
    import re

    def errbars(m):
        body = m.group(1)
        items = re.findall(r"(<(\w+)\b[^>]*?/>|<(\w+)\b[^>]*>.*?</\3>)", body, flags=re.S)
        if "".join(i[0] for i in items) != body:  # 예상 밖 모양이면 손대지 않는다
            return m.group(0)
        key = {n: i for i, n in enumerate(_ERRBAR_ORDER)}
        items.sort(key=lambda t: key.get(t[1] or t[2], 99))
        return "<errBars>" + "".join(i[0] for i in items) + "</errBars>"

    x = re.sub(r"<errBars>(.*?)</errBars>", errbars, x, flags=re.S)
    x = re.sub(r"<scatterChart>(?!\s*<scatterStyle)", '<scatterChart><scatterStyle val="lineMarker" />', x)

    def per_chart(m):
        # 스키마로는 통과하지만 Excel이 차트 종류별로 허용하지 않는 값(1.2.8):
        # - 데이터 레이블 위치(dLblPos): 영역·도넛·방사형·표면형은 지정 불가, 누적 막대는 outEnd 불가 등
        # - 오차막대 방향(errDir): 분산형·거품형에만 쓴다(막대·꺾은선은 값 축 방향이 정해져 있음)
        typ, body = m.group(1), m.group(2)
        if typ == "barChart":
            stacked = re.search(r'<grouping val="(stacked|percentStacked)"', body)
            ok = {"ctr", "inBase", "inEnd"} if stacked else {"ctr", "inBase", "inEnd", "outEnd"}
        else:
            ok = _DLBL_POS.get(typ)
        if ok is not None:
            body = re.sub(r'<dLblPos val="(\w+)"\s*/>', lambda d: d.group(0) if d.group(1) in ok else "", body)
        if typ not in ("scatterChart", "bubbleChart"):
            body = re.sub(r'<errDir val="\w+"\s*/>', "", body)
        return f"<{typ}>{body}</{typ}>"

    x = re.sub(r"<(\w+Chart)>(.*?)</\1>", per_chart, x, flags=re.S)

    # 축이 없는 축과 교차하도록 적혀 있으면 같은 차트 묶음의 다른 축으로 바로잡는다(1.2.9).
    defined = set(re.findall(r"<(?:catAx|valAx|dateAx|serAx)><axId val=\"(\d+)\"", x))
    partner = {}
    for body in re.findall(r"<\w+Chart>(.*?)</\w+Chart>", x, flags=re.S):
        ids = re.findall(r"<axId val=\"(\d+)\"", body)
        for i in ids:
            others = [j for j in ids if j != i and j in defined]
            if others:
                partner.setdefault(i, others[0])

    def cross(m):
        ax, i, mid, c = m.group(1), m.group(2), m.group(3), m.group(4)
        if c in defined or i not in partner:
            return m.group(0)
        return f'<{ax}><axId val="{i}"{mid}<crossAx val="{partner[i]}"'

    x = re.sub(r"<(catAx|valAx|dateAx|serAx)><axId val=\"(\d+)\"(.*?)<crossAx val=\"(\d+)\"", cross, x, flags=re.S)
    return polish_chart_xml(x)


_LINE_POS = {"t", "b", "l", "r", "ctr"}
_DLBL_POS = {"lineChart": _LINE_POS, "line3DChart": _LINE_POS, "scatterChart": _LINE_POS, "bubbleChart": _LINE_POS,
             "stockChart": _LINE_POS, "pieChart": {"bestFit", "ctr", "inEnd", "outEnd"},
             "pie3DChart": {"bestFit", "ctr", "inEnd", "outEnd"}, "ofPieChart": {"bestFit", "ctr", "inEnd", "outEnd"},
             "doughnutChart": set(), "areaChart": set(), "area3DChart": set(), "radarChart": set(),
             "surfaceChart": set(), "surface3DChart": set()}


def finish(data: bytes, wb) -> bytes:
    """저장한 통합문서를 마무리한다: 차트 XML 규격 보정(fix_chart_xml)과,
    openpyxl이 못 쓰는 '셀 값 라벨'(c15:datalabelsRange) 넣기.
    wb._range_labels: [{sheet, series(계열 이름), ref(라벨 셀 범위), texts}]"""
    items = getattr(wb, "_range_labels", None) or []
    import re
    import zipfile
    zin = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    for info in zin.infolist():
        b = zin.read(info.filename)
        if info.filename.startswith("xl/charts/chart") and info.filename.endswith(".xml"):
            x = b.decode("utf-8")
            changed = False
            for it in items:
                sh = "'" + it["sheet"] + "'!"
                def rep(m, it=it, sh=sh):
                    # 업무 파일 변환기(xlsx-bar.js cellLbl)와 같은 꼴 — 사용자 Excel에서 합계 라벨로 확인된 구조:
                    # 점마다 dLbl(글자 = CELLRANGE 필드) + 계열 dLbls 끝 showDataLabelsRange + 계열 끝 datalabelsRange(캐시는 차트 이름공간)
                    ser = m.group(0)
                    if f"<v>{_esc(it['series'])}</v>" not in ser or sh not in ser:
                        return ser
                    A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
                    rp = (f'<a:latin typeface="{FONT}"/><a:ea typeface="{FONT}"/><a:cs typeface="{FONT}"/>')
                    show = ('<showLegendKey val="0"/><showVal val="0"/><showCatName val="0"/><showSerName val="0"/>'
                            '<showPercent val="0"/><showBubbleSize val="0"/>')
                    nofill = '<spPr><a:noFill/><a:ln><a:noFill/></a:ln></spPr>'
                    col, sz = it.get("color", "404040"), it.get("size", 900)
                    pz = it.get("pos", "inBase")
                    posx = f'<dLblPos val="{pz}"/>' if pz else ""
                    pts = ""
                    for i in range(len(it["texts"])):
                        g = "{%08X-2B3C-4D5E-8F90-%012X}" % (abs(hash(it["ref"])) & 0xFFFFFFFF, 1000 + i)
                        pts += (f'<dLbl><idx val="{i}"/><layout/><tx><rich><a:bodyPr wrap="none" lIns="0" rIns="0"/><a:lstStyle/><a:p>'
                                f'<a:fld id="{g}" type="CELLRANGE"><a:rPr lang="ko-KR" sz="{sz}" b="0"><a:solidFill><a:srgbClr val="{col}"/></a:solidFill>{rp}</a:rPr>'
                                f'<a:t>[CELLRANGE]</a:t></a:fld></a:p></rich></tx>{nofill}{posx}{show}'
                                f'<extLst><ext uri="{{CE6537A1-D6FC-4f65-9D91-7224C49458BB}}" xmlns:c15="{_C15}"><c15:dlblFieldTable/>'
                                f'<c15:showDataLabelsRange val="1"/></ext></extLst></dLbl>')
                    txpr = (f'<txPr><a:bodyPr wrap="none" lIns="0" rIns="0"/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="{sz}" b="0"><a:solidFill>'
                            f'<a:srgbClr val="{col}"/></a:solidFill>{rp}</a:defRPr></a:pPr><a:endParaRPr lang="ko-KR"/></a:p></txPr>')
                    dl = (f'<dLbls {A}>{pts}{nofill}{txpr}{posx}{show}'
                          f'<extLst><ext uri="{{CE6537A1-D6FC-4f65-9D91-7224C49458BB}}" xmlns:c15="{_C15}"><c15:showDataLabelsRange val="1"/>'
                          f'<c15:showLeaderLines val="0"/></ext></extLst></dLbls>')
                    cache = "".join(f'<pt idx="{i}"><v>{_esc(t)}</v></pt>' for i, t in enumerate(it["texts"]))
                    ext_ser = (f'<extLst><ext uri="{{02D57815-91ED-43cb-92C2-25804820EDAC}}" xmlns:c15="{_C15}">'
                               f'<c15:datalabelsRange><c15:f>{_esc(it["ref"])}</c15:f><c15:dlblRangeCache>'
                               f'<ptCount val="{len(it["texts"])}"/>{cache}</c15:dlblRangeCache></c15:datalabelsRange></ext></extLst>')
                    if "<dLbls>" in ser:
                        ser = re.sub(r"<dLbls>.*?</dLbls>", lambda d: dl, ser, 1, flags=re.S)
                    else:  # 라벨이 없던 계열(거품 이름·포레스트 항목 이름): 계열 순서상 dLbls 자리(spPr·표식·dPt 뒤, 값 앞)에 넣는다
                        k = min([i for i in (ser.find("<trendline"), ser.find("<errBars"), ser.find("<cat>"), ser.find("<val>"), ser.find("<xVal>"), ser.find("<yVal>")) if i >= 0])
                        ser = ser[:k] + dl + ser[k:]
                    return ser.replace("</ser>", ext_ser + "</ser>")
                x2 = re.sub(r"<ser>.*?</ser>", rep, x, flags=re.S)
                if x2 != x:
                    x, changed = x2, True
            x2 = fix_chart_xml(x)
            if x2 != x:
                x, changed = x2, True
            if changed:
                b = x.encode("utf-8")
        zout.writestr(info, b)
    zout.close()
    return out.getvalue()


# ── 종류별 ─────────────────────────────────────────────
def _category(ws, r, ct, head, rows, last):
    """head = [구분, 계열...] — 꺾은선·영역·막대·혼합·범프·스트림."""
    a, o = r.meta["args"], r.meta["options"]
    n = len(rows)
    nser = len(head) - 1
    cats = _ref(ws, 1, T0 + 1, 1, last)
    roles = {s.get("name"): s for s in a.get("series", []) if isinstance(s, dict)}
    if ct == "combo":
        bar, ln = BarChart(), (AreaChart() if any(s.get("kind") == "area" for s in roles.values()) else LineChart())
        ln.y_axis.axId = 200
        ln.y_axis.crosses = "max"
        for j in range(nser):
            name = head[1 + j]
            s0 = roles.get(name, {})
            right = str(s0.get("axis", "")).lower() in ("right", "1", "secondary")
            kind = s0.get("kind") or s0.get("type") or ("bar" if j == 0 else "line")
            tgt = ln if (right or kind in ("line", "area")) and kind != "bar" else bar
            ser = Series(_ref(ws, 2 + j, T0 + 1, 2 + j, last), title=name)
            _color(ser, PAL[j % 6], line=tgt is ln, fill=not (tgt is ln and kind == "line"))
            _labels(ser, "outEnd" if tgt is bar else "t")
            tgt.series.append(ser)
        bar.set_categories(cats)
        ln.set_categories(cats)
        bar += ln
        return _style_chart(bar)
    if ct in ("bar", "bar_stacked", "bar_percent", "hbar", "hbar_stacked", "lollipop", "pictorial_bar", "polar_bar", "dumbbell"):
        ch = BarChart()
        ch.type = "bar" if ct in ("hbar", "hbar_stacked", "lollipop", "polar_bar", "dumbbell") else "col"
        ch.grouping = "stacked" if ct.endswith("stacked") else ("percentStacked" if ct.endswith("percent") else "clustered")
        if ch.grouping != "clustered":
            ch.overlap = 100
        if ch.type == "bar":
            ch.x_axis.scaling.orientation = "maxMin"
    elif ct in ("area", "area_stacked", "area_percent", "stream"):
        ch = AreaChart()
        ch.grouping = "standard" if ct == "area" else ("percentStacked" if ct.endswith("percent") else "stacked")
    else:
        ch = LineChart()
        if ct in ("line_stacked",):
            ch.grouping = "stacked"
        elif ct == "line_percent":
            ch.grouping = "percentStacked"
    for j in range(nser):
        name = head[1 + j]
        ser = Series(_ref(ws, 2 + j, T0 + 1, 2 + j, last), title=name)
        role = roles.get(name, {}).get("role")
        c = PAL[j % 6] if role not in ("lower", "upper") else "95ACD5"
        if isinstance(ch, LineChart):
            _color(ser, c, line=True, fill=False)
            ser.marker = Marker(symbol="circle", size=5)
            ser.marker.graphicalProperties.solidFill = c
            ser.marker.graphicalProperties.line.solidFill = c
            ser.smooth = False
            if role == "forecast":
                ser.graphicalProperties.line.dashStyle = "dash"
            if role in ("lower", "upper"):
                ser.graphicalProperties.line.dashStyle = "sysDot"
                ser.marker = Marker(symbol="none")
            if n <= 12 and nser <= 3 and role not in ("lower", "upper"):
                _labels(ser, "t", "#,##0.0#" if any(isinstance(x[1 + j], float) and not float(x[1 + j]).is_integer() for x in rows if x[1 + j] is not None) else "#,##0")
        else:
            _color(ser, c)
            if isinstance(ch, BarChart) and n <= 20:
                _labels(ser, "outEnd" if ch.grouping == "clustered" else "ctr")
        ch.series.append(ser)
    ch.set_categories(cats)
    if ct == "bump":
        ch.y_axis.scaling.orientation = "maxMin"
    # 기준선·허용 구간(U-01 등): 상수 열을 만들어 점선으로
    extra = list(o.get("target_lines") or []) + [b for b in (o.get("bands") or [])]
    if extra and isinstance(ch, LineChart):
        col = len(head) + 1
        k = 0
        for t in o.get("target_lines") or []:
            t = t if isinstance(t, dict) else {"value": t}
            ws.cell(T0, col + k, t.get("label") or "기준")
            for i in range(n):
                ws.cell(T0 + 1 + i, col + k, t.get("value"))
            ser = Series(_ref(ws, col + k, T0 + 1, col + k, last), title=t.get("label") or "기준")
            _color(ser, "404040", line=True, fill=False)
            ser.graphicalProperties.line.dashStyle = "dash"
            ser.marker = Marker(symbol="none")
            ch.series.append(ser)
            k += 1
        for b in o.get("bands") or []:
            for nm, v in ((f"{b.get('label') or '구간'} 하한", b.get("from")), (f"{b.get('label') or '구간'} 상한", b.get("to"))):
                ws.cell(T0, col + k, nm)
                for i in range(n):
                    ws.cell(T0 + 1 + i, col + k, v)
                ser = Series(_ref(ws, col + k, T0 + 1, col + k, last), title=nm)
                _color(ser, "2A9478", line=True, fill=False)
                ser.graphicalProperties.line.dashStyle = "sysDot"
                ser.marker = Marker(symbol="none")
                ch.series.append(ser)
                k += 1
        if o.get("y_min") is not None:
            ch.y_axis.scaling.min = o["y_min"]
        if o.get("y_max") is not None:
            ch.y_axis.scaling.max = o["y_max"]
    return _style_chart(ch)


def _pie(ws, r, ct, head, rows, last):
    a, o = r.meta["args"], r.meta["options"]
    n = len(rows)
    if ct == "half_donut":
        ch = DoughnutChart(holeSize=50)
        tot = sum(x[1] or 0 for x in rows)
        ws.cell(last + 1, 1, "(아래 반원 — 숨김)")
        ws.cell(last + 1, 2, tot)
        last += 1
        ch.firstSliceAng = 270
    elif ct == "donut":
        ch = DoughnutChart(holeSize=55)
    else:
        ch = PieChart()
    ser = Series(_ref(ws, 2, T0 + 1, 2, last), title=head[1])
    for i in range(last - T0):
        pt = DataPoint(idx=i)
        if ct == "half_donut" and i == n:
            pt.graphicalProperties.noFill = True
            pt.graphicalProperties.line.noFill = True
        else:
            pt.graphicalProperties.solidFill = PAL[i % 6]
        if ct == "pie_exploded" and ((o.get("highlight") and rows[i][0] == o.get("highlight")) or (not o.get("highlight") and i == max(range(n), key=lambda k: rows[k][1] or 0))):
            pt.explosion = 12
        ser.dPt.append(pt)
    _labels(ser, None, "0%")
    ser.dLbls.showVal = False
    ser.dLbls.showPercent = True
    ch.series.append(ser)
    ch.set_categories(_ref(ws, 1, T0 + 1, 1, last))
    return _style_chart(ch, w=13, h=9)


def _radar(ws, r, ct, head, rows, last):
    ch = RadarChart()
    ch.type = "filled" if ct == "radar_filled" else "marker"
    for j in range(len(head) - 1):
        ser = Series(_ref(ws, 2 + j, T0 + 1, 2 + j, last), title=head[1 + j])
        _color(ser, PAL[j % 6], line=True, fill=ct == "radar_filled")
        ch.series.append(ser)
    ch.set_categories(_ref(ws, 1, T0 + 1, 1, last))
    mx = r.meta["options"].get("max")
    if mx:
        ch.y_axis.scaling.max = mx
    return _style_chart(ch, w=13, h=10)


def _blocks_by_first(rows):
    """[계열, ...] 행을 계열별 연속 구간으로."""
    out, cur = [], None
    for i, row in enumerate(rows):
        if cur is None or row[0] != cur[0]:
            cur = [row[0], i, i]
            out.append(cur)
        else:
            cur[2] = i
    return out


def _xy(ws, r, ct, head, rows, last):
    """head = [계열, 이름, x, y, 크기]."""
    o = r.meta["options"]
    date_x = ct in ("time_series", "control_chart")
    blocks = _blocks_by_first(rows)
    if date_x:
        ch = LineChart()
        for k, (name, i0, i1) in enumerate(blocks):
            ser = Series(_ref(ws, 4, T0 + 1 + i0, 4, T0 + 1 + i1), title=name)
            _color(ser, PAL[k % 6], line=True, fill=False)
            ser.marker = Marker(symbol="circle", size=4)
            ch.series.append(ser)
        ch.set_categories(_ref(ws, 3, T0 + 1 + blocks[0][1], 3, T0 + 1 + blocks[0][2]))
        if ct == "control_chart":
            comp = r.computed
            col = 7
            n = blocks[0][2] - blocks[0][1] + 1
            for nm, v, c in (("상한", comp.get("ucl"), "C0392B"), ("하한", comp.get("lcl"), "C0392B"), ("기준", o.get("target", comp.get("mean")), "404040")):
                if v is None:
                    continue
                ws.cell(T0, col, nm)
                for i in range(n):
                    ws.cell(T0 + 1 + i, col, v)
                ser = Series(_ref(ws, col, T0 + 1, col, T0 + n), title=nm)
                _color(ser, c, line=True, fill=False)
                ser.graphicalProperties.line.dashStyle = "dash"
                ser.marker = Marker(symbol="none")
                ch.series.append(ser)
                col += 1
        return _style_chart(ch)
    if ct in ("bubble", "quadrant"):
        ch = BubbleChart()
        for k, (name, i0, i1) in enumerate(blocks):
            ser = Series(values=_ref(ws, 4, T0 + 1 + i0, 4, T0 + 1 + i1), xvalues=_ref(ws, 3, T0 + 1 + i0, 3, T0 + 1 + i1),
                         zvalues=_ref(ws, 5, T0 + 1 + i0, 5, T0 + 1 + i1), title=name)
            _color(ser, PAL[k % 6])
            ch.series.append(ser)
            ws.parent.__dict__.setdefault("_range_labels", []).append(
                {"sheet": ws.title, "series": name, "ref": f"'{ws.title}'!$B${T0 + 1 + i0}:$B${T0 + 1 + i1}", "pos": "r", "color": "404040",
                 "size": 800, "texts": [str(rows[i][1] or "") for i in range(i0, i1 + 1)]})
        ch.bubbleScale = 60
        if ct == "quadrant":
            # 사분면 기준선(그림과 같은 값: options.x_split·y_split, 없으면 중앙값)을 축 교차점으로 — 축 글자는 바깥쪽(low)에
            import statistics
            xs_ = [x[2] for x in rows if isinstance(x[2], (int, float))]
            ys_ = [x[3] for x in rows if isinstance(x[3], (int, float))]
            xm = o.get("x_split") if isinstance(o.get("x_split"), (int, float)) else statistics.median(xs_)
            ym = o.get("y_split") if isinstance(o.get("y_split"), (int, float)) else statistics.median(ys_)
            ch.x_axis.crossesAt, ch.y_axis.crossesAt = ym, xm
            ch.x_axis.tickLblPos = ch.y_axis.tickLblPos = "low"
        a_ = r.meta["args"]
        ch.x_axis.title = a_.get("x_label")
        ch.y_axis.title = a_.get("y_label")
        return _style_chart(ch)
    ch = ScatterChart()
    ch.style = 13
    for k, (name, i0, i1) in enumerate(blocks):
        ser = Series(_ref(ws, 4, T0 + 1 + i0, 4, T0 + 1 + i1), _ref(ws, 3, T0 + 1 + i0, 3, T0 + 1 + i1), title=name)
        c = PAL[k % 6]
        ser.marker = Marker(symbol="circle", size=6)
        ser.marker.graphicalProperties.solidFill = c
        ser.marker.graphicalProperties.line.solidFill = c
        if ct == "connected_scatter":
            ser.graphicalProperties.line.solidFill = c
            ser.smooth = bool(o.get("smooth"))
        else:
            ser.graphicalProperties.line.noFill = True
        if ct == "scatter_trend":
            from openpyxl.chart.data_source import NumFmt
            from openpyxl.chart.trendline import TrendlineLabel
            ser.trendline = Trendline(trendlineType="linear", dispRSqr=True, dispEq=True,
                                      trendlineLbl=TrendlineLabel(numFmt=NumFmt(formatCode="#,##0.000", sourceLinked=False)))
        ch.series.append(ser)
    if o.get("diagonal"):
        xs = [x[2] for x in rows if isinstance(x[2], (int, float))] + [x[3] for x in rows if isinstance(x[3], (int, float))]
        lo, hi = min(xs), max(xs)
        ws.cell(T0, 7, "기준선 x")
        ws.cell(T0, 8, "y = x")
        for i, v in enumerate((lo, hi)):
            ws.cell(T0 + 1 + i, 7, v)
            ws.cell(T0 + 1 + i, 8, v)
        ser = Series(_ref(ws, 8, T0 + 1, 8, T0 + 2), _ref(ws, 7, T0 + 1, 7, T0 + 2), title="y = x")
        ser.marker = Marker(symbol="none")
        ser.graphicalProperties.line.solidFill = "404040"
        ch.series.append(ser)
    a = r.meta["args"]
    ch.x_axis.title = a.get("x_label")
    ch.y_axis.title = a.get("y_label")
    return _style_chart(ch)


def _waterfall(ws, r, ct, head, rows, last):
    """합계·증가·감소 + 투명 바닥 계열을 옆 열에 계산해 누적 막대로."""
    a, o = r.meta["args"], r.meta["options"]
    cats = [x[0] for x in rows]
    totals = set(str(t) for t in (o.get("totals") or [])) or {cats[0], cats[-1]}
    col = len(head) + 2
    for j, nm in enumerate(("바닥(투명)", "합계", "증가", "감소")):
        ws.cell(T0, col + j, nm).font = Font(name=FONT, bold=True)
    run = 0.0
    for i, (c, v, _k) in enumerate(rows):
        rr = T0 + 1 + i
        if c in totals:
            v = v if v is not None else run
            run = v
            vals = (0, v, None, None)
        else:
            v = v or 0
            vals = (min(run, run + v), None, v if v > 0 else None, -v if v < 0 else None)
            run += v
        for j, x in enumerate(vals):
            ws.cell(rr, col + j, x)
    ch = BarChart()
    ch.grouping = "stacked"
    ch.overlap = 100
    for j, c in enumerate((None, "2E5395", "2A9478", "D2601A")):
        ser = Series(_ref(ws, col + j, T0 + 1, col + j, last), title=ws.cell(T0, col + j).value)
        if c is None:
            ser.graphicalProperties.noFill = True
            ser.graphicalProperties.line.noFill = True
        else:
            _color(ser, c)
            _labels(ser, "inEnd", {"2A9478": "+#,##0", "D2601A": "-#,##0"}.get(c, "#,##0"))
        ch.series.append(ser)
    ch.set_categories(_ref(ws, 1, T0 + 1, 1, last))
    return _style_chart(ch)


def _range_bars(ws, r, ct, head, rows, last):
    """풋볼필드(방법·하단·상단)·간트(작업·시작·종료)·깔때기 — 투명 바닥 + 길이 막대(가로)."""
    col = len(head) + 2
    if ct == "funnel":
        mx = max(x[1] or 0 for x in rows)
        ws.cell(T0, col, "바닥(투명)")
        ws.cell(T0, col + 1, head[1])
        for i, x in enumerate(rows):
            ws.cell(T0 + 1 + i, col, ((mx - (x[1] or 0)) / 2))
            ws.cell(T0 + 1 + i, col + 1, x[1])
    elif ct in ("gantt",):
        ws.cell(T0, col, "시작(일련번호)")
        ws.cell(T0, col + 1, "기간(일)")
        ws.cell(T0, col + 2, "글자 자리")
        ws.cell(T0, col + 3, "막대 옆 글")
        spans = [(date.fromisoformat(x[2]), date.fromisoformat(x[3])) for x in rows]
        one_year = len({d.year for se in spans for d in se}) == 1
        total = max(e for _, e in spans) - min(s for s, _ in spans)
        room = max(20, round(total.days * 0.2))
        for i, (s, e) in enumerate(spans):
            ws.cell(T0 + 1 + i, col, (s - date(1899, 12, 30)).days).number_format = "yy.mm.dd"
            ws.cell(T0 + 1 + i, col + 1, max((e - s).days, 1))
            ws.cell(T0 + 1 + i, col + 2, room)
            f = (lambda d: f"{d.month}/{d.day}") if one_year else (lambda d: f"{d:%y}.{d.month}.{d.day}")
            ws.cell(T0 + 1 + i, col + 3, f(s) if s == e else f"{f(s)}~{f(e)}")
        ws.cell(T0, col + 4, "축 형식")
        ws.cell(T0 + 1, col + 4, 'm"월"' if one_year else "yy.mm")
        # 눈금은 30.4일 간격이라 달 첫날에서 시작하면 2월이 짧아 '1월'이 두 번 찍힌다 — 첫날+2일에서 시작하면 눈금이 늘 그 달 초(1~4일)에 온다
        ws.cell(T0 + 2, col + 4, (date(min(s for s, _ in spans).year, min(s for s, _ in spans).month, 1) - date(1899, 12, 30)).days + 2)
    else:  # football_field: 방법·하단·상단·중앙
        ws.cell(T0, col, "하단")
        ws.cell(T0, col + 1, "폭(상단-하단)")
        for i, x in enumerate(rows):
            ws.cell(T0 + 1 + i, col, x[1])
            ws.cell(T0 + 1 + i, col + 1, f"={get_column_letter(3)}{T0 + 1 + i}-{get_column_letter(2)}{T0 + 1 + i}")
    ch = BarChart()
    ch.type = "bar"
    ch.grouping = "stacked"
    ch.overlap = 100
    ch.x_axis.scaling.orientation = "maxMin"
    base = Series(_ref(ws, col, T0 + 1, col, last), title=ws.cell(T0, col).value)
    base.graphicalProperties.noFill = True
    base.graphicalProperties.line.noFill = True
    ch.series.append(base)
    val = Series(_ref(ws, col + 1, T0 + 1, col + 1, last), title=ws.cell(T0, col + 1).value)
    _color(val, "2E5395")
    if ct == "funnel":
        _labels(val, "ctr")
    ch.series.append(val)
    if ct == "gantt":
        # 막대 오른쪽에 기간 글(2026-11-24 — 엑셀 간트에 일정 글이 없다는 지적). 투명한 '글자 자리' 계열을 막대 끝에 잇고,
        # 그 계열의 라벨을 셀 범위('막대 옆 글' 열)에서 가져온다(Excel 2013+ '셀 값' 라벨 — 저장 뒤 finish()가 XML에 넣음).
        gap = Series(_ref(ws, col + 2, T0 + 1, col + 2, last), title=ws.cell(T0, col + 2).value)
        gap.graphicalProperties.noFill = True
        gap.graphicalProperties.line.noFill = True
        gap.dLbls = DataLabelList()
        gap.dLbls.showVal = False
        gap.dLbls.showSerName = gap.dLbls.showCatName = gap.dLbls.showLegendKey = gap.dLbls.showPercent = False
        gap.dLbls.position = "inBase"
        ch.series.append(gap)
        cl = get_column_letter(col + 3)
        ws.parent.__dict__.setdefault("_range_labels", []).append(
            {"sheet": ws.title, "series": ws.cell(T0, col + 2).value, "ref": f"'{ws.title}'!${cl}${T0 + 1}:${cl}${last}",
             "texts": [ws.cell(T0 + 1 + i, col + 3).value for i in range(len(rows))]})
    ch.set_categories(_ref(ws, 1, T0 + 1, 1, last))
    if ct == "gantt":
        starts = [ws.cell(T0 + 1 + i, col).value for i in range(len(rows))]
        ends = [ws.cell(T0 + 1 + i, col).value + ws.cell(T0 + 1 + i, col + 1).value for i in range(len(rows))]
        ch.y_axis.scaling.min = ws.cell(T0 + 2, col + 4).value
        ch.y_axis.scaling.max = max(e + ws.cell(T0 + 1 + i, col + 2).value for i, e in enumerate(ends))
        ch.y_axis.number_format = ws.cell(T0 + 1, col + 4).value
        for k in range(3):
            ws.cell(T0 + k, col + 4).value = None
        ch.y_axis.crosses = "max"  # 항목 순서를 뒤집으면 날짜 축이 위로 가므로 아래로 내림
        for k, wdt in enumerate((14, 9, 11, 16)):
            ws.column_dimensions[get_column_letter(col + k)].width = wdt
        ch.y_axis.majorUnit = 30.4 if (max(ends) - min(starts)) <= 400 else 91.3
    elif ct == "football_field":
        lo, hi = min(x[1] for x in rows), max(x[2] for x in rows)
        ch.y_axis.scaling.min, ch.y_axis.majorUnit = _nice(lo - (hi - lo) * 0.15, hi)
        ch.y_axis.number_format = "#,##0"
        # 막대 왼쪽 끝에 하단, 오른쪽 끝 안쪽에 상단(2026-11-24 — 엑셀 풋볼필드에 범위 숫자가 없었다)
        _labels(base, "inEnd")
        cl = get_column_letter(3)
        ws.parent.__dict__.setdefault("_range_labels", []).append(
            {"sheet": ws.title, "series": ws.cell(T0, col + 1).value, "ref": f"'{ws.title}'!${cl}${T0 + 1}:${cl}${last}", "pos": "inEnd",
             "color": "FFFFFF", "size": 1000, "texts": [f"{x[2]:,.0f}" for x in rows]})
    elif ct == "funnel":
        # 깔때기의 값 축은 투명 바닥 때문에 뜻이 없다(2026-11-24 — 엑셀에 0~1,200 축이 위에 찍혔다)
        ch.y_axis.delete = True
        ch.y_axis.majorGridlines = None
    ch.legend = None
    return _style_chart(ch)


def _stock(ws, r, ct, head, rows, last):
    """head = [일자, 시가, 고가, 저가, 종가, 거래량]. 캔들(시·고·저·종), HLC(고·저·종)."""
    ch = StockChart()
    cols = [3, 4, 5] if ct == "hlc" else [2, 3, 4, 5]
    for c in cols:
        ser = Series(_ref(ws, c, T0 + 1, c, last), title=head[c - 1])
        ser.graphicalProperties.line.noFill = True
        ser.marker = Marker(symbol="none") if not (ct == "hlc" and c == 5) else Marker(symbol="dash", size=6)
        ch.series.append(ser)
    ch.set_categories(_ref(ws, 1, T0 + 1, 1, last))
    ch.hiLowLines = ChartLines()
    if ct != "hlc":
        from openpyxl.chart.shapes import GraphicalProperties
        ch.upDownBars = UpDownBars(gapWidth=60, upBars=ChartLines(spPr=GraphicalProperties(solidFill="C0392B")),
                                   downBars=ChartLines(spPr=GraphicalProperties(solidFill="2E5395")))
    ch.legend = None
    lo = min(x[3] for x in rows if x[3] is not None)
    hi = max(x[2] for x in rows if x[2] is not None)
    ch.y_axis.scaling.min, ch.y_axis.majorUnit = _nice(lo - (hi - lo) * 0.05, hi)
    ch.y_axis.number_format = "#,##0"
    out = [_style_chart(ch)]
    if ct == "price_volume":
        vb = BarChart()
        s = Series(_ref(ws, 6, T0 + 1, 6, last), title="거래량")
        _color(s, "95ACD5")
        vb.series.append(s)
        vb.set_categories(_ref(ws, 1, T0 + 1, 1, last))
        vb.legend = None
        out.append(_style_chart(vb, h=5))
    return out


def _surface(ws, r, ct, head, rows, last):
    ch = SurfaceChart3D() if ct == "surface_3d" else SurfaceChart()
    if ct == "contour":
        ch.wireframe = False
    data = Reference(ws, min_col=2, min_row=T0, max_col=len(head), max_row=last)
    ch.add_data(data, titles_from_data=True)
    ch.set_categories(_ref(ws, 1, T0 + 1, 1, last))
    return _style_chart(ch)


def _errorbars(ws, r, ct, head, rows, last):
    """head = [군, n, 평균, 하한, 상한] → 평균 막대/점 + 사용자 지정 오차(상한-평균, 평균-하한)."""
    col = len(head) + 2
    ws.cell(T0, col, "위 오차")
    ws.cell(T0, col + 1, "아래 오차")
    for i in range(len(rows)):
        rr = T0 + 1 + i
        ws.cell(rr, col, f"=E{rr}-C{rr}")
        ws.cell(rr, col + 1, f"=C{rr}-D{rr}")
    plus = NumDataSource(numRef=NumRef(f=f"'{ws.title}'!${get_column_letter(col)}${T0 + 1}:${get_column_letter(col)}${last}"))
    minus = NumDataSource(numRef=NumRef(f=f"'{ws.title}'!${get_column_letter(col + 1)}${T0 + 1}:${get_column_letter(col + 1)}${last}"))
    if ct == "errorbar_bar":
        ch = BarChart()
        ser = Series(_ref(ws, 3, T0 + 1, 3, last), title="평균")
        for i in range(len(rows)):
            pt = DataPoint(idx=i)
            pt.graphicalProperties.solidFill = PAL[i % 6]
            ser.dPt.append(pt)
    else:
        ch = LineChart()
        ser = Series(_ref(ws, 3, T0 + 1, 3, last), title="평균")
        ser.graphicalProperties.line.noFill = True
        ser.marker = Marker(symbol="circle", size=8)
        ser.marker.graphicalProperties.solidFill = "2E5395"
    ser.errBars = ErrorBars(errDir="y", errBarType="both", errValType="cust", plus=plus, minus=minus, noEndCap=False)
    _labels(ser, "r" if ct == "errorbar" else "outEnd", "#,##0.0")
    ch.series.append(ser)
    ch.set_categories(_ref(ws, 1, T0 + 1, 1, last))
    ch.legend = None
    return _style_chart(ch)


def _forest(ws, r, ct, head, rows, last):
    """forest 입력 rows=[{label, estimate, lower, upper, n}] → 가로 오차막대 산점도(y=순번)."""
    a = r.meta["args"]
    items = [x for x in (a.get("rows") or []) if isinstance(x, dict) and x.get("estimate") is not None]
    if not items:
        return None
    col = len(head) + 2
    for j, nm in enumerate(("항목", "추정치", "순번", "+오차", "-오차")):
        ws.cell(T0, col + j, nm)
    for i, it in enumerate(items):
        rr = T0 + 1 + i
        ws.cell(rr, col, it.get("label"))
        ws.cell(rr, col + 1, it.get("estimate"))
        ws.cell(rr, col + 2, len(items) - i)
        ws.cell(rr, col + 3, (it.get("upper") or it["estimate"]) - it["estimate"])
        ws.cell(rr, col + 4, it["estimate"] - (it.get("lower") or it["estimate"]))
    e = T0 + len(items)
    ch = ScatterChart()
    ser = Series(_ref(ws, col + 2, T0 + 1, col + 2, e), _ref(ws, col + 1, T0 + 1, col + 1, e), title="추정치(95% CI)")
    ser.marker = Marker(symbol="square", size=7)
    ser.marker.graphicalProperties.solidFill = "2E5395"
    ser.graphicalProperties.line.noFill = True
    L = get_column_letter
    ser.errBars = ErrorBars(errDir="x", errBarType="both", errValType="cust",
                            plus=NumDataSource(numRef=NumRef(f=f"'{ws.title}'!${L(col + 3)}${T0 + 1}:${L(col + 3)}${e}")),
                            minus=NumDataSource(numRef=NumRef(f=f"'{ws.title}'!${L(col + 4)}${T0 + 1}:${L(col + 4)}${e}")))
    ch.series.append(ser)
    # 2026-11-24 — 엑셀 포레스트에 항목 이름이 없고(세로축 숨김) 로그 10 축 최대 1에서 신뢰구간이 잘렸다.
    # 축은 2의 거듭제곱(0.25·0.5·1·2), 왼쪽에 한 칸 더 두어 그 자리에 항목 이름을 쓰고(투명 계열 + 셀 값 라벨), 1에 세로 기준선.
    import math
    lows = [it.get("lower") or it["estimate"] for it in items]
    highs = [it.get("upper") or it["estimate"] for it in items]
    xmin = 2 ** (math.floor(math.log2(min(lows + [1]))) - 2)
    xmax = 2 ** math.ceil(math.log2(max(highs + [1]) * 1.05))
    ws.cell(T0, col + 5, "이름 자리")
    ws.cell(T0, col + 6, "기준선 x")
    ws.cell(T0, col + 7, "기준선 y")
    for i in range(len(items)):
        ws.cell(T0 + 1 + i, col + 5, xmin)
    for i, (xv, yv) in enumerate(((1, 0.5), (1, len(items) + 0.5))):
        ws.cell(T0 + 1 + i, col + 6, xv)
        ws.cell(T0 + 1 + i, col + 7, yv)
    ref_ = Series(_ref(ws, col + 7, T0 + 1, col + 7, T0 + 2), _ref(ws, col + 6, T0 + 1, col + 6, T0 + 2), title="기준(1)")
    ref_.marker = Marker(symbol="none")
    ref_.graphicalProperties.line.solidFill = "7F7F7F"
    ref_.graphicalProperties.line.dashStyle = "dash"
    ch.series.append(ref_)
    nm = Series(_ref(ws, col + 2, T0 + 1, col + 2, e), _ref(ws, col + 5, T0 + 1, col + 5, e), title="항목 이름")
    nm.marker = Marker(symbol="none")
    nm.graphicalProperties.line.noFill = True
    ch.series.append(nm)
    L_ = get_column_letter(col)
    ws.parent.__dict__.setdefault("_range_labels", []).append(
        {"sheet": ws.title, "series": "항목 이름", "ref": f"'{ws.title}'!${L_}${T0 + 1}:${L_}${e}", "pos": "r", "color": "262626",
         "size": 900, "texts": [str(it.get("label") or "") for it in items]})
    ch.x_axis.scaling.logBase = 2
    ch.x_axis.scaling.min, ch.x_axis.scaling.max = xmin, xmax
    ch.x_axis.number_format = "0.0#"
    ch.x_axis.title = "HR (로그 척도)"
    ch.y_axis.scaling.min, ch.y_axis.scaling.max = 0.5, len(items) + 0.5
    ch.y_axis.delete = True
    ch.y_axis.majorGridlines = None
    ch.legend = None
    return _style_chart(ch)


def _heat(ws, r, ct, head, rows, last):
    o = r.meta["options"]
    rng = f"B{T0 + 1}:{get_column_letter(len(head))}{last}"
    if ct == "correlation" or o.get("diverging") or o.get("center") is not None or ct == "sensitivity_table":
        mid = o.get("center")
        rule = ColorScaleRule(start_type="min", start_color="2E5395", mid_type="num" if mid is not None else "percentile",
                              mid_value=mid if mid is not None else 50, mid_color="F2F2F2", end_type="max", end_color="D2601A")
    else:
        rule = ColorScaleRule(start_type="min", start_color="EEF2F9", end_type="max", end_color="1A335D")
    ws.conditional_formatting.add(rng, rule)
    if ct == "sensitivity_table" and o.get("base"):
        b = [str(x) for x in o["base"]]
        rnames = [str(x[0]) for x in rows]
        if len(b) == 2 and b[0] in rnames and b[1] in head:
            c = ws.cell(T0 + 1 + rnames.index(b[0]), head.index(b[1]) + 1)
            c.border = Border(*(Side(style="medium", color="D2601A"),) * 4)
            c.font = Font(name=FONT, bold=True)
    return None



# ── 표를 따로 만들어야 하는 차트(오른쪽에 '엑셀 차트용 표'를 둔다) ──────────────
def _side(ws, head_len, cols_head, rows, label="엑셀 차트용 표"):
    c0 = head_len + 2
    ws.cell(T0 - 1, c0, label).font = Font(name=FONT, bold=True, size=9, color="7F7F7F")
    last = _write_table(ws, cols_head, rows, T0, c0)
    return c0, last


def _cfb(ws, r, ct, head, rows, last):
    a = r.meta["args"]
    vis = [str(v) for v in a.get("visits") or []]
    gs = [g for g in a.get("groups") or [] if isinstance(g, dict)]
    ch_head = ["방문"] + [x for g in gs for x in (f"{g.get('name')} 평균", f"{g.get('name')} 오차")]
    tab = [[v] + [x for g in gs for x in ((g.get("mean") or [None] * len(vis))[i], (g.get("error") or [0] * len(vis))[i])] for i, v in enumerate(vis)]
    c0, e = _side(ws, len(head), ch_head, tab)
    ch = LineChart()
    L = get_column_letter
    for k, g in enumerate(gs):
        mc, ec = c0 + 1 + 2 * k, c0 + 2 + 2 * k
        ser = Series(_ref(ws, mc, T0 + 1, mc, e), title=g.get("name"))
        _color(ser, PAL[k % 6], line=True, fill=False)
        ser.marker = Marker(symbol="circle", size=6)
        ser.marker.graphicalProperties.solidFill = PAL[k % 6]
        ref = NumDataSource(numRef=NumRef(f=f"'{ws.title}'!${L(ec)}${T0 + 1}:${L(ec)}${e}"))
        ser.errBars = ErrorBars(errDir="y", errBarType="both", errValType="cust", plus=ref, minus=ref)
        ch.series.append(ser)
    ch.set_categories(_ref(ws, c0, T0 + 1, c0, e))
    ch.y_axis.title = "기저치 대비 변화"
    return _style_chart(ch), c0 + len(ch_head) + 1


def _ae(ws, r, ct, head, rows, last):
    a = r.meta["args"]
    arms = a.get("arms") or ["투여군", "위약군"]
    import math
    tab = []
    for t in a.get("terms") or []:
        pa, pb = t["a_events"] / t["a_n"] * 100, t["b_events"] / t["b_n"] * 100
        d = pa - pb
        se = math.sqrt(pa / 100 * (1 - pa / 100) / t["a_n"] + pb / 100 * (1 - pb / 100) / t["b_n"]) * 100
        tab.append([t["term"], round(pa, 2), round(pb, 2), round(d, 2), round(1.96 * se, 2)])
    tab.sort(key=lambda x: x[3])
    c0, e = _side(ws, len(head), ["이상반응", f"{arms[0]}(%)", f"{arms[1]}(%)", "위험차(%p)", "95% CI 반폭"], tab)
    bar = BarChart()
    bar.type = "bar"
    for k in range(2):
        ser = Series(_ref(ws, c0 + 1 + k, T0 + 1, c0 + 1 + k, e), title=f"{arms[k]}")
        _color(ser, PAL[k])
        _labels(ser, "outEnd", "0.0")
        bar.series.append(ser)
    bar.set_categories(_ref(ws, c0, T0 + 1, c0, e))
    bar.x_axis.scaling.orientation = "maxMin"
    bar.y_axis.title = "발생률(%)"
    rd = BarChart()
    rd.type = "bar"
    ser = Series(_ref(ws, c0 + 3, T0 + 1, c0 + 3, e), title="위험차(%p)")
    _color(ser, "2E5395")
    ref = NumDataSource(numRef=NumRef(f=f"'{ws.title}'!${get_column_letter(c0 + 4)}${T0 + 1}:${get_column_letter(c0 + 4)}${e}"))
    ser.errBars = ErrorBars(errDir="y", errBarType="both", errValType="cust", plus=ref, minus=ref)
    rd.series.append(ser)
    rd.set_categories(_ref(ws, c0, T0 + 1, c0, e))
    rd.x_axis.scaling.orientation = "maxMin"
    rd.legend = None
    rd.y_axis.title = "위험차(투여군−위약군, %p)와 95% CI"
    return [_style_chart(bar, h=8), _style_chart(rd, h=8)], c0 + 6


def _kpi_x(ws, r, ct, head, rows, last):
    a = r.meta["args"]
    ks = [k for k in a.get("kpis") or [] if isinstance(k, dict)]
    sp = [k for k in ks if k.get("spark")]
    if not sp:
        return None, None
    n = max(len(k["spark"]) for k in sp)
    tab = [[f"{i + 1}"] + [(k["spark"][i] if i < len(k["spark"]) else None) for k in sp] for i in range(n)]
    c0, e = _side(ws, len(head), ["시점"] + [k.get("name") for k in sp], tab, "추이(스파크라인 자료)")
    out = []
    for j, k in enumerate(sp):
        ch = LineChart()
        ser = Series(_ref(ws, c0 + 1 + j, T0 + 1, c0 + 1 + j, e), title=k.get("name"))
        _color(ser, "2E5395", line=True, fill=False)
        ch.series.append(ser)
        ch.legend = None
        ch.y_axis.delete = True
        ch.x_axis.delete = True
        ch.title = f"{k.get('name')} 추이"
        out.append(_style_chart(ch, w=8, h=4))
    for i in range(len(rows)):  # 증감 색
        rr = T0 + 1 + i
        d = ws.cell(rr, 4).value
        kk = ks[i] if i < len(ks) else {}
        good = d is None or ((d >= 0) == (kk.get("higher_is_better", True) not in (False, "false")))
        if d is not None:
            ws.cell(rr, 4).font = Font(name=FONT, bold=True, color="2A9478" if good else "C0392B")
    return out, c0 + len(sp) + 2


def _km_x(ws, r, ct, head, rows, last):
    from .render.legacy.clinical import km_estimate
    a = r.meta["args"]
    gs = [g for g in a.get("groups") or [] if isinstance(g, dict)]
    blocks, tab = [], []
    for g in gs:
        km = km_estimate(g["times"], g["events"])
        xs, ss = km["time"], km["surv"]
        i0 = len(tab)
        for i, (x, s_) in enumerate(zip(xs, ss)):
            if i:
                tab.append([g.get("name"), x, round(ss[i - 1] * 100, 2)])
            tab.append([g.get("name"), x, round(s_ * 100, 2)])
        tab.append([g.get("name"), max(g["times"]), round(ss[-1] * 100, 2)])
        blocks.append((g.get("name"), i0, len(tab) - 1))
    c0, e = _side(ws, len(head), ["군", "시간", "생존 확률(%)"], tab, "생존곡선(카플란-마이어 계산값)")
    ch = ScatterChart()
    for k, (nm, i0, i1) in enumerate(blocks):
        ser = Series(_ref(ws, c0 + 2, T0 + 1 + i0, c0 + 2, T0 + 1 + i1), _ref(ws, c0 + 1, T0 + 1 + i0, c0 + 1, T0 + 1 + i1), title=nm)
        ser.marker = Marker(symbol="none")
        ser.graphicalProperties.line.solidFill = PAL[k % 6]
        ser.graphicalProperties.line.width = 22000
        ch.series.append(ser)
    ch.y_axis.scaling.min, ch.y_axis.scaling.max = 0, 100
    ch.x_axis.title = "시간"
    ch.y_axis.title = "생존 확률(%)"
    return _style_chart(ch), c0 + 4


def _mekko_x(ws, r, ct, head, rows, last):
    """마리메코를 날짜축 누적 영역으로 흉내 낸다 — 열 경계마다 같은 x를 두 번 넣어 세로 경계를 만든다."""
    from openpyxl.chart.axis import DateAxis
    a = r.meta["args"]
    cats = [str(c) for c in a.get("categories") or []]
    ser = [s for s in a.get("series") or [] if isinstance(s, dict)]
    colsum = [sum((s["values"][j] or 0) for s in ser) for j in range(len(cats))]
    tot = sum(colsum) or 1
    tab, x = [], 0
    for j, c in enumerate(cats):
        w = round(colsum[j] / tot * 1000)
        shares = [round((s["values"][j] or 0) / colsum[j] * 100, 2) if colsum[j] else 0 for s in ser]
        tab.append([x + 1, c] + shares)
        tab.append([x + w, c] + shares)
        x += w
    c0, e = _side(ws, len(head), ["위치(폭 누적, ‰)", "열"] + [s.get("name") for s in ser], tab, "마리메코 흉내용 표(폭 = 열 비중)")
    ch = AreaChart()
    ch.grouping = "stacked"
    for k, s in enumerate(ser):
        sr = Series(_ref(ws, c0 + 2 + k, T0 + 1, c0 + 2 + k, e), title=s.get("name"))
        _color(sr, PAL[k % 6])
        sr.graphicalProperties.line.solidFill = "FFFFFF"
        ch.series.append(sr)
    ch.x_axis = DateAxis(crossAx=100)
    ch.x_axis.axPos = "b"
    ch.y_axis.crossAx = 500  # 기본값 10(없는 축)을 가리키면 Excel이 복구 창을 띄운다
    ch.x_axis.number_format = "0"
    ch.x_axis.majorTimeUnit = "days"
    ch.x_axis.delete = True
    ch.set_categories(_ref(ws, c0, T0 + 1, c0, e))
    ch.y_axis.scaling.max = 100
    ch.y_axis.title = "열 안 구성비(%)"
    return _style_chart(ch), c0 + len(ser) + 3


def _violin_x(ws, r, ct, head, rows, last):
    import numpy as np
    from scipy.stats import gaussian_kde
    a = r.meta["args"]
    gs = [g for g in a.get("groups") or [] if isinstance(g, dict)]
    tab, blocks = [], []
    for k, g in enumerate(gs):
        v = np.array([x for x in g["values"] if x is not None], float)
        grid = np.linspace(v.min(), v.max(), 30)
        d = gaussian_kde(v)(grid)
        d = d / d.max() * 0.38
        i0 = len(tab)
        for y, dd in zip(grid, d):
            tab.append([g.get("name"), round(k + 1 - dd, 4), round(float(y), 4)])
        for y, dd in zip(grid[::-1], d[::-1]):
            tab.append([g.get("name"), round(k + 1 + dd, 4), round(float(y), 4)])
        tab.append([g.get("name"), round(k + 1 - d[0], 4), round(float(grid[0]), 4)])
        blocks.append((g.get("name"), i0, len(tab) - 1))
    c0, e = _side(ws, len(head), ["군", "가로(군 번호 ± 밀도)", "값"], tab, "바이올린 윤곽(커널 밀도 계산값)")
    ch = ScatterChart()
    for k, (nm, i0, i1) in enumerate(blocks):
        sr = Series(_ref(ws, c0 + 2, T0 + 1 + i0, c0 + 2, T0 + 1 + i1), _ref(ws, c0 + 1, T0 + 1 + i0, c0 + 1, T0 + 1 + i1), title=nm)
        sr.marker = Marker(symbol="none")
        sr.graphicalProperties.line.solidFill = PAL[k % 6]
        sr.graphicalProperties.line.width = 19050
        ch.series.append(sr)
    ch.x_axis.scaling.min, ch.x_axis.scaling.max = 0.5, len(gs) + 0.5
    ch.x_axis.majorUnit = 1
    ch.x_axis.tickLblPos = "none"  # 가로 위치는 군 번호일 뿐이라 숫자를 쓰지 않는다(군 이름은 범례)
    ch.x_axis.majorGridlines = None
    return _style_chart(ch), c0 + 4


SPECIAL = {"change_from_baseline": _cfb, "ae_comparison": _ae, "kpi_tiles": _kpi_x, "km": _km_x, "marimekko": _mekko_x, "violin": _violin_x}
SPECIAL_NOTES = {"marimekko": "엑셀에는 마리메코가 없어 누적 영역(날짜축 기법)으로 흉내 냈습니다 — 오른쪽 표의 폭·구성비를 고치면 바뀝니다.",
                 "violin": "엑셀에는 바이올린이 없어 윤곽선을 산점도 선으로 그렸습니다(밀도는 계산값 — 원자료를 고쳐도 다시 계산되지 않습니다).",
                 "km": "생존곡선은 카플란-마이어 계산값입니다 — 원자료(왼쪽 표)를 고쳐도 다시 계산되지 않습니다.",
                 "kpi_tiles": "지표 값은 왼쪽 표, 추이는 작은 꺾은선 차트로 넣었습니다."}


NATIVE_CATEGORY = {"line", "line_marker", "line_stacked", "line_percent", "step_line", "area", "area_stacked", "area_percent", "line_band", "bar",
                   "bar_stacked", "bar_percent", "hbar", "hbar_stacked", "combo", "lollipop", "pictorial_bar", "polar_bar", "dumbbell", "bump", "stream"}
HEAT = {"heatmap", "correlation", "sensitivity_table", "choropleth", "cluster_heatmap", "waffle"}


def build(r, wb=None, sheet: str = "차트"):
    """엑셀 원본 바이트. wb를 주면 그 통합문서에 시트를 더하고 None을 돌려준다(시험용 모음)."""
    m = r.meta
    ct = m["chart_type"]
    head, rows = r.table if r.table else (["값"], [])
    rows = [list(x) for x in rows]
    own = wb is None
    if own:
        wb = Workbook()
        ws = wb.active
        ws.title = sheet
    else:
        ws = wb.create_sheet(sheet)
    ws.sheet_view.showGridLines = False
    ttl = m.get("title") or m.get("name")
    ws.cell(1, 1, ttl).font = Font(name=FONT, bold=True, size=13)
    ws.cell(2, 1, (f"단위: {m['unit']}  ·  " if m.get("unit") else "") + f"차트 종류: {m.get('name')} ({m.get('code') or ct})").font = Font(name=FONT, size=9, color="7F7F7F")
    if ct == "choropleth":
        head = head[:2]
    last = _write_table(ws, head, rows) if rows else T0
    dfmt = None
    if rows and (ct in NATIVE_CATEGORY or ct in ("candlestick", "hlc", "price_volume")):
        dfmt = _date_cells(ws, 1, T0 + 1, last)
    elif rows and ct in ("time_series", "control_chart"):
        dfmt = _date_cells(ws, 3, T0 + 1, last)
    charts, note, special_col = None, None, None
    try:
        if not rows:
            charts = None
        elif ct in NATIVE_CATEGORY:
            charts = _category(ws, r, ct, head, rows, last)
            if ct == "step_line":
                note = "엑셀에는 계단형 꺾은선이 없어 일반 꺾은선으로 넣었습니다(값은 같음)."
            if ct == "stream":
                note = "엑셀에는 스트림그래프가 없어 누적 영역으로 넣었습니다."
            if ct == "polar_bar":
                note = "엑셀에는 방사형 막대가 없어 가로 막대로 넣었습니다."
            if ct == "dumbbell":
                note = "엑셀에는 덤벨 차트가 없어 묶은 가로 막대로 넣었습니다."
        elif ct in ("pie", "donut", "pie_exploded", "half_donut", "rose"):
            charts = _pie(ws, r, ct, head, rows, last)
            if ct == "rose":
                note = "엑셀에는 나이팅게일 로즈가 없어 원형으로 넣었습니다."
        elif ct in ("radar", "radar_filled"):
            charts = _radar(ws, r, ct, head, rows, last)
        elif m["group"] == "xy":
            charts = _xy(ws, r, ct, head, rows, last)
        elif ct == "waterfall":
            charts = _waterfall(ws, r, ct, head, rows, last)
        elif ct in ("funnel", "football_field", "gantt"):
            charts = _range_bars(ws, r, ct, head, rows, last)
        elif ct in ("candlestick", "hlc", "price_volume"):
            charts = _stock(ws, r, ct, head, rows, last)
        elif ct in ("surface_3d", "contour"):
            charts = _surface(ws, r, ct, head, rows, last)
            if ct == "contour":
                note = "엑셀 등고선은 '표면형(위에서 본 모양)' 차트입니다. 색 단계는 엑셀이 정합니다."
        elif ct in ("errorbar", "errorbar_bar"):
            charts = _errorbars(ws, r, ct, head, rows, last)
        elif ct == "forest":
            charts = _forest(ws, r, ct, head, rows, last)
        elif ct in SPECIAL:
            charts, special_col = SPECIAL[ct](ws, r, ct, head, rows, last)
            note = SPECIAL_NOTES.get(ct)
        elif ct in HEAT:
            charts = _heat(ws, r, ct, head, rows, last)
            note = "표의 색 단계(조건부 서식)가 그림을 대신합니다 — 값을 고치면 색도 바뀝니다. 그림은 오른쪽에 함께 넣었습니다."
    except Exception as e:  # noqa: BLE001 — 엑셀 차트를 못 만들어도 표와 그림은 준다
        charts, note = None, f"엑셀 차트를 만들지 못해 그림으로 넣었습니다({type(e).__name__})."
    anchor_col = get_column_letter(special_col) if special_col else get_column_letter(max(len(head), 1) + 2 + (5 if ct in ("waterfall", "funnel", "football_field", "gantt", "errorbar", "errorbar_bar", "forest", "control_chart") else 0))
    if charts:
        for k, ch in enumerate(charts if isinstance(charts, list) else [charts]):
            if dfmt and ch.tagname in ("lineChart", "areaChart", "barChart", "stockChart"):
                ch.x_axis.number_format = dfmt
                ch.x_axis.auto = False  # 글자 축: 주말·빈 날을 띄우지 않는다(일별 주가)
            _show_axes(ch)
            ws.add_chart(ch, f"{anchor_col}{T0 + k * 19}")
    if not charts or ct in HEAT:
        _picture(ws, r.png, f"{anchor_col}{T0 if not charts else T0 + 40}")
        if not note:
            note = "이 차트 종류는 엑셀 차트로 만들 수 없어 그림을 넣었습니다. 자료 표는 아래에 있습니다."
    if note:
        ws.cell(3, 1, note).font = Font(name=FONT, size=9, color="D2601A")
    if r.notes:
        rr = max(last + 2, T0 + 2)
        ws.cell(rr, 1, "참고").font = Font(name=FONT, bold=True, size=9)
        for i, t in enumerate(r.notes):
            ws.cell(rr + 1 + i, 1, f"· {t}").font = Font(name=FONT, size=9, color="595959")
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    if not own:
        return None
    b = io.BytesIO()
    wb.save(b)
    return finish(b.getvalue(), wb)
