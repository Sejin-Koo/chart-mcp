"""chart-mcp — 보고서 차트 75종 MCP 서버(Vercel 파이썬 함수, ASGI).

- 전송: Streamable HTTP의 JSON 응답(POST /api/mcp). 무상태 — 세션을 두지 않는다.
- 게이트: ?k=<게이트키>. MCP_GATE_KEYS(쉼표 구분), MCP_GATE_MODE=enforce|observe (sys-mcp-gatekey).
- 프로토콜: initialize 협상은 지원 목록과 대조, 미지원 MCP-Protocol-Version 헤더는 400, 알림은 202.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import zlib
import os
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chartkit import api as chart_api  # noqa: E402
from chartkit.core import setup_fonts  # noqa: E402
from chartkit.excel import build as excel_build, finish as excel_finish  # noqa: E402
from chartkit.errors import ChartInputError  # noqa: E402

SERVER = {"name": "chart-mcp", "version": "1.3.0"}
SUPPORTED = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05", "2024-10-07"]
GATE_KEYS = [k.strip() for k in os.environ.get("MCP_GATE_KEYS", "").split(",") if k.strip()]
GATE_MODE = os.environ.get("MCP_GATE_MODE", "observe")

INSTRUCTIONS = (
    "보고서용 차트 75종을 그리는 서버입니다(맑은 고딕, 계정 보고서 색 규칙). "
    "list_chart_types로 코드(예: R-05)와 예시 입력을 확인한 뒤 draw_chart에 type·data를 넣어 부르세요. "
    "막대·꺾은선·원 같은 기본 그래프 28종과 도식(흐름도·조직도·SWOT·로드맵 등)은 이 서버가 아니라 보고서 변환기(```chart·```diagram)가 맡습니다."
)

TOOLS = [
    {
        "name": "list_chart_types",
        "description": "그릴 수 있는 차트 75종 목록(코드·chart_type·이름·용도·쓰임 when·유의점 avoid·분류). 차트를 고를 때는 when(언제 쓰는지)과 avoid(이럴 때는 다른 차트 — 대안이 적혀 있음)를 보고, 75종 전체 대신 tag로 걸러 보는 편이 빠르다. code를 주면 그 차트의 예시 입력(draw_chart에 그대로 넣을 수 있는 type·data·options)을 돌려준다. tag로 거르기: 비교·추이·구성·분포·상관·흐름·계층·성과·재무·일정·지리·유통·임상·오믹스·3D.",
        "inputSchema": {"type": "object", "properties": {
            "code": {"type": "string", "description": "차트 코드(예: R-05, G-03) 또는 chart_type(예: km)"},
            "tag": {"type": "string", "description": "분류 이름으로 거르기"}}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "draw_chart",
        "description": (
            "차트 한 개를 그린다. type은 코드(R-05) 또는 chart_type(km). data는 차트별 입력 객체 — 모양은 list_chart_types(code)의 example.data를 따른다. "
            "계산이 필요한 차트(카플란-마이어·log-rank·4PL·PK·추세선·관리도·상관계수 등)는 서버가 계산해 computed와 notes로 돌려준다. "
            "output: image(기본 — 그림을 바로 보여 줌), base64(그림을 글자로 — 페이지·다른 서버용), xlsx(엑셀 원본만). include_xlsx=true면 엑셀 원본(base64)도 함께. "
            "결과의 png_url·xlsx_url은 24시간 동안 게이트키 없이 열리는 받기 주소다 — 파일로 저장할 때는 이 주소를 내려받는다(curl -o 등)."),
        "inputSchema": {"type": "object", "required": ["type", "data"], "properties": {
            "type": {"type": "string", "description": "차트 코드 또는 chart_type"},
            "data": {"type": ["object", "string"], "description": "차트별 입력(예: {categories, series} / {groups:[...]} / {links:[...]} / {regions:[...]})"},
            "title": {"type": "string", "description": "그림 제목(엑셀 제목·자료 줄에 씀. 그림 안에는 options.show_title=true일 때만)"},
            "subtitle": {"type": "string"},
            "unit": {"type": "string", "description": "값의 단위(예: 억원, %, 명)"},
            "options": {"type": ["object", "string"], "description": "차트별 설정(예: target_lines, bands, highlight, error, base, today). 공통: show_title, width_in, height_in"},
            "output": {"type": "string", "enum": ["image", "base64", "xlsx"], "description": "돌려줄 형식(기본 image)"},
            "include_xlsx": {"type": ["boolean", "string"], "description": "엑셀 원본도 함께(base64)"},
        }},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "draw_charts_xlsx",
        "description": ("여러 차트의 엑셀 원본을 한 통합문서로 — 차트마다 시트 하나(시트 이름 '그림N', N은 fig_no 또는 순번). "
                        "보고서의 그림자료 엑셀을 만들 때 쓴다. 그리지 못한 차트는 사유를 warnings에 담고 건너뛴다."),
        "inputSchema": {"type": "object", "required": ["charts"], "properties": {
            "charts": {"type": "array", "items": {"type": "object"}, "description": "draw_chart와 같은 항목(type·data·title·unit·options)에 fig_no(그림 번호)를 더한 목록, 40개까지"},
            "title": {"type": "string", "description": "통합문서 제목(파일 속성)"}}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "chart_server_status",
        "description": "서버 상태 — 글꼴(맑은 고딕을 받았는지·대체 글꼴 경고), 게이트 모드, 버전. 비밀값은 돌려주지 않는다.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
]


# ---------- 받아 쓰는 주소(2026-11-24) ----------
# 계정 채팅의 Claude는 draw_chart 결과의 그림을 파일로 옮길 방법이 마땅치 않다(작은 결과는 글로만 들어와 다시 옮겨 적어야 하고,
# 셸에서 게이트키를 실어 부르면 자동 승인에 막힌다). 그래서 그린 입력을 서명한 주소(png_url·xlsx_url)를 함께 돌려준다.
# 주소에는 게이트키가 없고, 서명(서버 키로 만든 HMAC)과 만료 시각(24시간)으로만 열린다. 열 때 같은 입력으로 다시 그린다.
LINK_TTL = 24 * 3600
_HOST = {"v": os.environ.get("PUBLIC_HOST", "chart-mcp-one.vercel.app")}


def _link_key() -> bytes:
    sec = os.environ.get("CHART_LINK_SECRET") or ("link|" + ",".join(sorted(GATE_KEYS)))
    return hashlib.sha256(sec.encode()).digest()


def make_link(a: dict, fmt: str) -> str | None:
    body = {k: a.get(k) for k in ("type", "data", "title", "subtitle", "unit", "options") if a.get(k) is not None}
    body["exp"] = int(time.time()) + LINK_TTL
    body["fmt"] = fmt
    tok = base64.urlsafe_b64encode(zlib.compress(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(), 9)).decode().rstrip("=")
    sig = hmac.new(_link_key(), tok.encode(), hashlib.sha256).hexdigest()[:32]
    url = f"https://{_HOST['v']}/api/mcp?f={tok}&s={sig}"
    return url if len(url) <= 7500 else None


def open_link(tok: str, sig: str):
    good = hmac.new(_link_key(), tok.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(good, sig or ""):
        return None, "서명이 맞지 않습니다"
    body = json.loads(zlib.decompress(base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4))).decode())
    if int(body.get("exp", 0)) < time.time():
        return None, "주소가 만료됐습니다(24시간) — draw_chart를 다시 부르세요"
    return body, None


def _text(obj) -> dict:
    return {"type": "text", "text": obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)}


def _bool(v) -> bool:
    return v is True or str(v).lower() in ("true", "1", "yes")


def call_tool(name: str, a: dict) -> dict:
    if name == "list_chart_types":
        if a.get("code"):
            return {"content": [_text(chart_api.list_types(code=a["code"]))]}
        items = chart_api.list_types(tag=a.get("tag"))
        return {"content": [_text({"count": len(items), "types": items,
                                   "note": "code를 주면 예시 입력을 돌려줍니다. 기본 그래프 28종(막대·꺾은선·원 등)과 도식(흐름도·조직도·스윔레인·SWOT·2×2·로드맵 등)은 보고서 변환기가 맡습니다."})]}
    if name == "chart_server_status":
        fs = setup_fonts()
        return {"content": [_text({"server": SERVER, "font": {"family": fs.get("family"), "malgun": bool(fs.get("regular")),
                                                              "bold": bool(fs.get("bold")), "warning": fs.get("warning")},
                                   "font_source_configured": bool(os.environ.get("FONT_URL_REGULAR")), "gate_mode": GATE_MODE,
                                   "chart_types": len(chart_api.catalog())})]}
    if name == "draw_chart":
        t0 = time.time()
        r = chart_api.draw(a.get("type"), a.get("data"), title=a.get("title"), subtitle=a.get("subtitle"), unit=a.get("unit"), options=a.get("options"))
        out = (a.get("output") or "image").lower()
        meta = {"type": r.meta["code"] or r.meta["chart_type"], "name": r.meta["name"], "notes": r.notes, "computed": r.computed,
                "png_bytes": len(r.png), "ms": int((time.time() - t0) * 1000)}
        xlsx = chart_api.to_xlsx(r) if (out == "xlsx" or _bool(a.get("include_xlsx"))) else None
        pu, xu = make_link(a, "png"), make_link(a, "xlsx")
        if pu:
            meta["png_url"], meta["xlsx_url"] = pu, xu
            meta["link_note"] = "png_url·xlsx_url은 24시간 동안 열리는 받기 주소입니다(게이트키 없이 서명으로 열림). 파일로 저장하려면 이 주소를 내려받으세요."
        if xlsx is not None:
            meta["xlsx_bytes"] = len(xlsx)
        if out == "base64":
            meta["png_base64"] = base64.b64encode(r.png).decode()
            if xlsx is not None:
                meta["xlsx_base64"] = base64.b64encode(xlsx).decode()
            return {"content": [_text(meta)]}
        if out == "xlsx":
            meta["xlsx_base64"] = base64.b64encode(xlsx).decode()
            return {"content": [_text(meta)]}
        content = [{"type": "image", "data": base64.b64encode(r.png).decode(), "mimeType": "image/png"}, _text(meta)]
        if xlsx is not None:
            content.append(_text({"xlsx_base64": base64.b64encode(xlsx).decode()}))
        return {"content": content}
    if name == "draw_charts_xlsx":
        charts = a.get("charts")
        if isinstance(charts, str):
            charts = json.loads(charts)
        if not isinstance(charts, list) or not charts:
            return {"content": [_text("charts가 비어 있습니다")], "isError": True}
        from openpyxl import Workbook
        wb = Workbook()
        wb.remove(wb.active)
        warns, made, used = [], [], set()
        for i, c in enumerate(charts[:40]):
            if not isinstance(c, dict):
                continue
            no = c.get("fig_no") or (i + 1)
            sheet = f"그림{no}"
            while sheet in used:
                sheet += "_"
            try:
                ttl = c.get("title") or ""
                r = chart_api.draw(c.get("type"), c.get("data"), title=(f"[그림 {no}] {ttl}" if ttl else f"[그림 {no}]"),
                                   subtitle=c.get("subtitle"), unit=c.get("unit"), options=c.get("options"))
                excel_build(r, wb=wb, sheet=sheet)
                used.add(sheet)
                made.append({"fig_no": no, "sheet": sheet, "type": r.meta["code"] or r.meta["chart_type"]})
            except Exception as e:  # noqa: BLE001
                warns.append(f"그림 {no}: {e}")
        if not made:
            return {"content": [_text({"ok": False, "warnings": warns})], "isError": True}
        if a.get("title"):
            wb.properties.title = str(a["title"])[:200]
        bio = io.BytesIO()
        wb.save(bio)
        x = excel_finish(bio.getvalue(), wb)
        return {"content": [_text({"ok": True, "sheets": made, "warnings": warns, "xlsx_bytes": len(x),
                                   "xlsx_base64": base64.b64encode(x).decode()})]}
    return {"content": [_text(f"알 수 없는 도구: {name}")], "isError": True}


def handle_rpc(msg: dict):
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        req = params.get("protocolVersion")
        ver = req if req in SUPPORTED else SUPPORTED[0]
        return {"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": ver, "capabilities": {"tools": {"listChanged": False}},
                                                         "serverInfo": SERVER, "instructions": INSTRUCTIONS}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            return {"jsonrpc": "2.0", "id": mid, "result": call_tool(name, args)}
        except ChartInputError as e:
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [_text(e.render())], "isError": True}}
        except Exception as e:  # noqa: BLE001
            print("[error]", traceback.format_exc(), flush=True)
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [_text(f"그리기 오류: {type(e).__name__}: {e}")], "isError": True}}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def _label(k):
    if not k:
        return "none"
    parts = k.split("_")
    return parts[1] if len(parts) >= 3 else "unknown"


async def _read(receive) -> bytes:
    body = b""
    while True:
        m = await receive()
        body += m.get("body", b"")
        if not m.get("more_body"):
            return body


async def _send(send, status, payload=None, headers=None):
    body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    h = [(b"content-type", b"application/json; charset=utf-8"), (b"access-control-allow-origin", b"*")] + (headers or [])
    await send({"type": "http.response.start", "status": status, "headers": h})
    await send({"type": "http.response.body", "body": body})


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            m = await receive()
            if m["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif m["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] != "http":
        return
    method = scope.get("method", "GET")
    headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
    if headers.get("host") and not headers["host"].startswith(("localhost", "127.")):
        _HOST["v"] = headers["host"]
    if method == "GET" and "f=" in scope.get("query_string", b"").decode():
        q = parse_qs(scope.get("query_string", b"").decode())
        try:
            body, err = open_link((q.get("f") or [""])[0], (q.get("s") or [""])[0])
        except Exception as e:  # noqa: BLE001
            body, err = None, f"주소를 읽지 못했습니다: {type(e).__name__}"
        if err:
            await _send(send, 403, {"error": err})
            return
        try:
            r = chart_api.draw(body.get("type"), body.get("data"), title=body.get("title"), subtitle=body.get("subtitle"), unit=body.get("unit"), options=body.get("options"))
        except Exception as e:  # noqa: BLE001
            await _send(send, 400, {"error": f"{type(e).__name__}: {e}"})
            return
        if body.get("fmt") == "xlsx":
            data, ctype, ext = chart_api.to_xlsx(r), b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
        else:
            data, ctype, ext = r.png, b"image/png", "png"
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", ctype), (b"cache-control", b"private, max-age=3600"),
                                                                              (b"content-disposition", f'inline; filename="chart.{ext}"'.encode())]})
        await send({"type": "http.response.body", "body": data})
        return
    if method == "OPTIONS":
        await _send(send, 204, None, [(b"access-control-allow-methods", b"POST, GET, OPTIONS"),
                                      (b"access-control-allow-headers", b"content-type, accept, mcp-protocol-version, mcp-session-id")])
        return
    qs = parse_qs(scope.get("query_string", b"").decode())
    gk = (qs.get("k") or [None])[0]
    allowed = not GATE_KEYS or (gk in GATE_KEYS)
    print(f"[gate] mode={GATE_MODE} caller={_label(gk)} allowed={allowed}", flush=True)
    if not allowed and GATE_MODE == "enforce":
        await _send(send, 401, {"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "unauthorized"}})
        return
    if method == "GET":
        await _send(send, 405, {"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": "Method not allowed — POST로 JSON-RPC를 보내세요"}},
                    [(b"allow", b"POST, OPTIONS")])
        return
    pv = headers.get("mcp-protocol-version")
    if pv and pv not in SUPPORTED:
        await _send(send, 400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": f"Bad Request: Unsupported protocol version (supported versions: {', '.join(SUPPORTED)})"}})
        return
    raw = await _read(receive)
    try:
        msg = json.loads(raw or b"null")
    except json.JSONDecodeError:
        await _send(send, 400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
        return
    msgs = msg if isinstance(msg, list) else [msg]
    if not msgs or not all(isinstance(m, dict) for m in msgs):
        await _send(send, 400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}})
        return
    out = [handle_rpc(m) for m in msgs if "id" in m and m.get("method")]
    if not out:  # 알림·응답만 온 경우
        await _send(send, 202, None)
        return
    await _send(send, 200, out if isinstance(msg, list) else out[0])
