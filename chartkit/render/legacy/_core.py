"""원본 엔진의 core 인터페이스(figure·title·to_bytes·top_margin·num_fmt·g_fmt)를 chartkit 공통 설정으로 잇는다.

원본은 960×560px(100dpi) 기준으로 글자 크기를 정했다. 그 비율을 유지하려고 그림을 7.6in 폭으로 만들고,
저장할 때 보고서 폭 16cm·220dpi와 같은 픽셀 폭(약 1386px)이 되도록 dpi를 맞춘다.
그림 안 제목은 SHOW_TITLE이 켜졌을 때만 그린다(보고서·화면이 그림 밖에 제목을 단다).
"""
from __future__ import annotations

import contextvars
import io
from contextlib import contextmanager

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from ... import core as _c
from ... import style as _s

SHOW_TITLE = contextvars.ContextVar("show_title", default=False)
SIZE = contextvars.ContextVar("size", default=None)  # (w_in, h_in) 덮어쓰기
FONT_PATH = None
W_IN = 7.6
OUT_PX = int(_s.WIDTH_IN * _s.DPI)


@contextmanager
def figure(width=None, height=None, **kw):
    global FONT_PATH
    with _c.LOCK:
        _c.setup_fonts()
        FONT_PATH = _c._font_state["regular"]
        w_px, h_px = (width or 960), (height or 560)
        w, h = W_IN, W_IN * h_px / w_px
        if SIZE.get():
            w, h = SIZE.get()
        fig = plt.figure(figsize=(w, h), dpi=100, **kw)
        try:
            yield fig
        finally:
            plt.close(fig)


def title(fig, ax, text, sub):
    if not SHOW_TITLE.get():
        return
    if text:
        fig.text(0.012, 0.975, text, fontsize=13, fontweight="bold", color=_s.INK, va="top", ha="left")
    if sub:
        fig.text(0.012, 0.925 if text else 0.975, sub, fontsize=9, color=_s.MUTED, va="top", ha="left")


def top_margin(text, sub):
    if not SHOW_TITLE.get():
        return 0.95
    return 0.86 if (text and sub) else (0.89 if (text or sub) else 0.95)


def to_bytes(fig, formats=("png",)):
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=OUT_PX / fig.get_size_inches()[0], bbox_inches="tight", pad_inches=0.08)
    return {"png": b.getvalue()}


def num_fmt(decimals=None):
    def f(v, _pos=None):
        if decimals is not None:
            return f"{v:,.{decimals}f}"
        return f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:g}"
    return FuncFormatter(f)


def g_fmt():
    return FuncFormatter(lambda v, _p=None: f"{v:g}")
