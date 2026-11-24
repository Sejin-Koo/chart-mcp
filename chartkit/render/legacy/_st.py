"""원본(pharma-chart-mcp) matplotlib 엔진이 쓰던 이름을 계정 보고서 색으로 잇는다."""
from ... import style as _s

CATEGORICAL = _s.PALETTE + ["#8C8C8C", "#595959"]
from matplotlib.colors import LinearSegmentedColormap as _L, to_hex as _hex
_cm = _L.from_list("s", _s.SEQUENTIAL)
SEQUENTIAL = [_hex(_cm(i / 12)).upper() for i in range(13)]  # 원본과 같은 13단계
DIVERGING = _s.DIVERGING
GRAY = _s.GRAY
INK = _s.INK
INK2 = _s.INK2
MUTED = _s.MUTED
GRID = _s.GRID
AXIS = _s.AXIS
UP = _s.UP
DOWN = _s.DOWN
