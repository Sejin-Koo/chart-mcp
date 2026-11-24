"""75종 예시를 모두 그리고 엑셀까지 만든다 — 실패 0이어야 한다."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chartkit import api  # noqa: E402

fails = []
t0 = time.time()
for e in api.catalog():
    ex = e["example"]
    try:
        r = api.draw(ex["type"], ex.get("data"), title=ex.get("title"), unit=ex.get("unit"), options=ex.get("options"))
        assert r.png[:4] == b"\x89PNG"
        x = api.to_xlsx(r)
        assert x[:2] == b"PK"
    except Exception as ex_:  # noqa: BLE001
        fails.append((e["code"], repr(ex_)))
print(f"{len(api.catalog()) - len(fails)}/{len(api.catalog())} ok, {time.time() - t0:.1f}s")
for f in fails:
    print("FAIL", *f)
sys.exit(1 if fails else 0)
