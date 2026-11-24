"""입력 오류 — 모델이 스스로 고쳐 다시 부를 수 있도록 '무엇이 틀렸고 어떻게 고치는지'와 예시를 함께 돌려준다."""
from __future__ import annotations

import json
from typing import Any


class ChartInputError(ValueError):
    def __init__(self, message: str, *, hint: str | None = None, example: Any = None):
        self.message = message
        self.hint = hint
        self.example = example
        super().__init__(self.render())

    def render(self) -> str:
        parts = [f"입력 오류: {self.message}"]
        if self.hint:
            parts.append(f"고치는 방법: {self.hint}")
        if self.example is not None:
            parts.append("올바른 입력 예시:\n" + json.dumps(self.example, ensure_ascii=False, indent=1))
        return "\n".join(parts)


def need(cond: bool, message: str, *, hint: str | None = None, example: Any = None) -> None:
    if not cond:
        raise ChartInputError(message, hint=hint, example=example)


def as_number(v: Any, where: str) -> float | None:
    """숫자로 바꾼다. '1,234'·'12.5%' 같은 문자열도 받아 준다(일부 클라이언트는 숫자를 문자열로 보낸다)."""
    if v is None or v == "" or v == "-":
        return None
    if isinstance(v, bool):
        raise ChartInputError(f"{where}에 참/거짓 값이 들어왔습니다", hint="숫자를 넣으세요")
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "").replace("%", "")
        try:
            return float(s)
        except ValueError:
            pass
    raise ChartInputError(f"{where}의 값 {v!r}을(를) 숫자로 읽을 수 없습니다", hint="쉼표·단위 없이 숫자만 넣으세요")


def as_list(v: Any, where: str) -> list:
    """배열을 받는다. JSON 문자열로 온 배열도 풀어 준다."""
    if v is None:
        return []
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except json.JSONDecodeError as e:
            raise ChartInputError(f"{where}는 배열이어야 합니다", hint="[...] 형식의 JSON 배열을 넣으세요") from e
    if not isinstance(v, list):
        raise ChartInputError(f"{where}는 배열이어야 합니다", hint="[...] 형식으로 넣으세요")
    return v


def as_dict(v: Any, where: str) -> dict:
    if v is None:
        return {}
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except json.JSONDecodeError as e:
            raise ChartInputError(f"{where}는 객체여야 합니다", hint="{...} 형식의 JSON 객체를 넣으세요") from e
    if not isinstance(v, dict):
        raise ChartInputError(f"{where}는 객체여야 합니다", hint="{...} 형식으로 넣으세요")
    return v
