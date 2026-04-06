"""
다온나상점 상품등록 런처
=======================
사전 준비:
  1. Chrome을 CDP 포트 9223으로 실행 중이어야 함
     → 이미 실행 중이면 생략
  2. domeggook.com 탭: 셀러센터 로그인 상태
  3. gemini.google.com 탭: 열려 있어야 썸네일 자동 생성

실행 방법:
  python daonna_run.py           # 오늘 최대 10개 등록
  python daonna_run.py 5         # 오늘 최대 5개 등록
  python daonna_run.py --collect # 수집만 (등록 안 함)
  python daonna_run.py --upload  # 수집 스킵, 등록만

흐름:
  1단계) daonna_collector.py → 미등록 상품 목록 수집
  2단계) daonna_upload_bot.py → 상품 등록 + Gemini 썸네일 생성
"""
import asyncio
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
COMPARE_FILE = Path("/tmp/daonna_compare.json")


def run_step(script: str, args: list[str] = []) -> bool:
    cmd = [sys.executable, str(PROJECT_DIR / script)] + args
    print(f"\n{'='*60}", flush=True)
    print(f"▶ {' '.join(cmd)}", flush=True)
    print(f"{'='*60}", flush=True)
    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    args = sys.argv[1:]

    collect_only = "--collect" in args
    upload_only  = "--upload"  in args
    max_count    = next((a for a in args if a.isdigit()), "10")

    # 1단계: 수집
    if not upload_only:
        print("\n[1단계] 공급사 상품 수집 중...", flush=True)
        ok = run_step("daonna_collector.py")
        if not ok:
            print("❌ 수집 실패 — 종료", flush=True)
            sys.exit(1)
        if not COMPARE_FILE.exists():
            print(f"❌ {COMPARE_FILE} 파일 없음 — 종료", flush=True)
            sys.exit(1)
        print("✅ 수집 완료", flush=True)

        if collect_only:
            print("\n(--collect 옵션: 수집만 완료)", flush=True)
            return

    # 2단계: 등록
    print(f"\n[2단계] 상품 등록 시작 (최대 {max_count}개)...", flush=True)
    ok = run_step("daonna_upload_bot.py", [max_count])
    if ok:
        print("\n✅ 등록 완료", flush=True)
    else:
        print("\n⚠️ 등록 중 오류 발생 — progress.json 확인", flush=True)


if __name__ == "__main__":
    main()
