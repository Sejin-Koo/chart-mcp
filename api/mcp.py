"""chart-mcp — 보고서 차트 75종 MCP 서버(Vercel 파이썬 함수, ASGI).

- 전송: Streamable HTTP의 JSON 응답(POST /api/mcp). 무상태 — 세션을 두지 않는다.
- 게이트: ?k=<게이트키>. MCP_GATE_KEYS(쉼표 구분), MCP_GATE_MODE=enforce|observe (sys-mcp-gatekey).
- 프로토콜: initialize 협상은 지원 목록과 대조, 미지원 MCP-Protocol-Version 헤더는 400, 알림은 202.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chartkit import api as chart_api  # noqa: E402
from chartkit.core import setup_fonts  # noqa: E402
from chartkit.errors import ChartInputError  # noqa: E402

SERVER = {"name": "chart-mcp", "version": "1.0.0"}
SUPPORTED = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05", "2024-10-07"]
GATE_KEYS = [k.strip() for k in os.environ.get("MCP_GATE_KEYS", "").split(",") if k.strip()]
GATE_MODE = os.environ.get("MCP_GATE_MODE", "observe")

INSTRUCTIONS = (
    "보고서용 차트 75종을 그리는 서버입니다(맑은 고딕, 계정 보고서 색 규칙). "
    "list_chart_types로 코드(예: R-05)와 예시 입력을 확인한 뒤 draw_chart에 type·data를 넣어 부르세요. "
    "막대·꺾은선·원 같은 기본 그래프 28종과 도식 3종은 이 서버가 아니라 보고서 변환기(```chart·```diagram)가 맡습니다."
)

TOOLS = [
    {
        "name": "list_chart_types",
        "description": "그릴 수 있는 차트 75종 목록(코드·chart_type·이름·용도·분류). code를 주면 그 차트의 예시 입력(draw_chart에 그대로 넣을 수 있는 type·data·options)을 돌려준다. tag로 거르기: 비교·추이·구성·분포·상관·흐름·계층·성과·재무·일정·지리·유통·임상·오믹스·3D.",
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
            "output: image(기본 — 그림을 바로 보여 줌), base64(그림을 글자로 — 페이지·다른 서버용), xlsx(엑셀 원본만). include_xlsx=true면 엑셀 원본(base64)도 함께."),
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
        "name": "chart_server_status",
        "description": "서버 상태 — 글꼴(맑은 고딕을 받았는지·대체 글꼴 경고), 게이트 모드, 버전. 비밀값은 돌려주지 않는다.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
]


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
                                   "note": "code를 주면 예시 입력을 돌려줍니다. 기본 그래프 28종(막대·꺾은선·원 등)과 도식 3종은 보고서 변환기가 맡습니다."})]}
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
