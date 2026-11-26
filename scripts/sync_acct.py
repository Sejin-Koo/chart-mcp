"""계정 Word 그래프 코드(sys-file-builder scripts/chart-png.py·chart_declutter.py) 사본을 chartkit/acct/로 옮기고 SOURCE.json에 버전·해시를 남긴다.
업무 에이전트의 기본 그래프(막대·꺾은선·영역·원·도넛·혼합·양쪽 가로 막대)를 계정과 같은 코드로 그리기 위한 사본이다 — 사본을 직접 고치지 말고
원본 스킬을 고친 뒤 이 스크립트로 옮긴다.
    python scripts/sync_acct.py <sys-file-builder 스킬 폴더>     # 복사
    python scripts/sync_acct.py --check                          # 사본이 SOURCE.json과 같은지(직접 고친 흔적이 없는지)
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

DST = Path(__file__).resolve().parents[1] / "chartkit" / "acct"
FILES = {"scripts/chart-png.py": "chart_png.py", "scripts/chart_declutter.py": "chart_declutter.py"}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "--check":
        src = json.loads((DST / "SOURCE.json").read_text(encoding="utf-8"))
        bad = [f for f, h in src["files"].items() if sha(DST / f) != h]
        if bad:
            sys.exit(f"사본이 원본 해시와 다릅니다(직접 고친 흔적): {bad} — 원본 스킬을 고친 뒤 sync_acct.py로 옮기세요")
        print(f"acct 사본 확인: sys-file-builder {src['version']}, 파일 {len(src['files'])}개 일치")
        return
    skill = Path(sys.argv[1])
    files = {}
    for s, d in FILES.items():
        shutil.copyfile(skill / s, DST / d)
        files[d] = sha(DST / d)
    ver = (skill / "VERSION").read_text().strip() if (skill / "VERSION").exists() else "unknown"
    (DST / "SOURCE.json").write_text(json.dumps({"skill": "sys-file-builder", "version": ver, "files": files}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"복사 완료: sys-file-builder {ver} → chartkit/acct ({len(files)}개)")


if __name__ == "__main__":
    main()
