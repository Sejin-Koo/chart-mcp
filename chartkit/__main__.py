"""명령줄 — 계정 작업 공간에서 서버와 같은 코드로 그린다.

    python -m chartkit list [분류]
    python -m chartkit example R-05            # 예시 입력(JSON)
    python -m chartkit draw 명세.json 그림.png [엑셀.xlsx]

명세.json = {"type": "R-05", "data": {...}, "title": "...", "unit": "...", "options": {...}}
글꼴: 맑은 고딕을 FONT_DIR·~/.local/share/fonts 등에서 찾는다(없으면 대체 글꼴 + 경고).
"""
import json
import sys

from . import api


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "list":
        for e in api.list_types(tag=argv[1] if len(argv) > 1 else None):
            print(f"{e['code']}\t{e['chart_type']}\t{e['name']}")
        return 0
    if cmd == "example":
        print(json.dumps(api.list_types(code=argv[1])["example"], ensure_ascii=False, indent=1))
        return 0
    if cmd == "draw":
        spec = json.load(open(argv[1], encoding="utf-8"))
        r = api.draw(spec["type"], spec.get("data"), title=spec.get("title"), subtitle=spec.get("subtitle"), unit=spec.get("unit"),
                     options=spec.get("options"))
        open(argv[2], "wb").write(r.png)
        if len(argv) > 3:
            open(argv[3], "wb").write(api.to_xlsx(r))
        print(json.dumps({"name": r.meta["name"], "notes": r.notes, "computed": r.computed}, ensure_ascii=False, default=str))
        return 0
    print(f"알 수 없는 명령: {cmd}")
    return 2


sys.exit(main(sys.argv[1:]))
