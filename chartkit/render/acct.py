"""업무 에이전트 기본 그래프(acct_basic) — 계정 Word 그래프 코드 사본(chartkit/acct/chart_png.py)으로 그린다(1.5.0, 2026-11-26).

입력(data)은 파일 변환기 lib/png-input.js의 pngInput(```chart 명세) 결과 — 중계 서버가 만든다. 계정 chart.js png가 쓰는 입력과 같아서
같은 명세면 계정 Word 그림과 같은 그림이 나온다. 그래프 규칙을 고칠 때는 계정 스킬(sys-file-builder)을 고치고 scripts/sync_acct.py로 사본을 옮긴다.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
from pathlib import Path

import matplotlib

from ..core import Result, setup_fonts
from ..errors import ChartInputError

_DIR = Path(__file__).resolve().parents[1] / "acct"
_mod = None


def _load():
    global _mod
    if _mod is None:
        spec = importlib.util.spec_from_file_location("chartkit_acct_chart_png", _DIR / "chart_png.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _mod = m
    return _mod


def draw(ct: str, args: dict, o: dict) -> Result:
    if not isinstance(args, dict) or not args.get("x") or "kind" not in args:
        raise ChartInputError("acct_basic 입력이 아닙니다(중계 서버가 만든 pngInput 결과를 넣으세요)")
    setup_fonts()  # 서버는 /tmp/chartkit-fonts에 맑은 고딕을 받아 둔다
    dirs = [d for d in (os.environ.get("FONT_DIR", ""), "/tmp/chartkit-fonts") if d and os.path.isdir(d)]
    if dirs:
        os.environ["CHART_FONT_DIRS"] = ":".join(dirs)
    m = _load()
    inp = {k: v for k, v in args.items() if k not in ("unit", "subtitle")}
    with tempfile.TemporaryDirectory() as d:
        sp, out = os.path.join(d, "in.json"), os.path.join(d, "out.png")
        with open(sp, "w", encoding="utf-8") as fh:
            json.dump(inp, fh, ensure_ascii=False)
        buf = io.StringIO()
        try:
            with matplotlib.rc_context(), contextlib.redirect_stdout(buf):
                # 서버 전역 서식(chartkit 눈금·축 색)을 지우고 matplotlib 기본값에서 시작 — 계정 PC에서 chart-png.py를 따로 돌릴 때와 같은 출발점
                matplotlib.rcdefaults()
                m.main(sp, out)
        except SystemExit as e:
            raise ChartInputError(f"기본 그래프를 그리지 못했습니다: {e}") from None
        info = {}
        for line in reversed(buf.getvalue().strip().splitlines()):
            try:
                info = json.loads(line)
                break
            except ValueError:
                continue
        png = Path(out).read_bytes()
    notes = list(info.get("notes") or [])
    issues = info.get("issues") or []
    if issues:
        notes.append(f"점검: {len(issues)}건({'; '.join(str(i) for i in issues[:3])})")
    return Result(png, notes=notes)
