"""워커: goodisak 에디터 현재 상태 스크린샷 찍기 (수정 없음)"""
import os
import sys
import subprocess

sys.path.insert(0, "/Users/hana/Downloads/blog-automation-v2")
from browser import connect_cdp, get_or_create_page

SCREENSHOT_PATH = "/Users/hana/Downloads/blog-automation-v2/images/editor_check.png"

def log(msg):
    print(msg, flush=True)

def main():
    os.makedirs("/Users/hana/Downloads/blog-automation-v2/images", exist_ok=True)

    log("[워커] CDP 연결 중...")
    pw, browser = connect_cdp(on_log=log)

    try:
        # goodisak.tistory.com/manage/newpost 탭 찾기
        page = get_or_create_page(browser, url_contains="goodisak.tistory.com/manage/newpost")
        log(f"[워커] 현재 탭 URL: {page.url}")

        if "goodisak.tistory.com/manage/newpost" not in page.url:
            log("[워커] goodisak 에디터 탭을 찾지 못했습니다. 모든 탭 목록:")
            for ctx in browser.contexts:
                for p in ctx.pages:
                    log(f"  - {p.url}")
        else:
            log("[워커] goodisak 에디터 탭 찾음!")

        # 스크린샷 찍기 (수정 없음)
        page.screenshot(path=SCREENSHOT_PATH)
        log(f"[워커] 스크린샷 저장: {SCREENSHOT_PATH}")

        # 텔레그램 전송
        result = subprocess.run(
            ["python3", "tg_send.py", "--photo", SCREENSHOT_PATH, "현재 에디터 상태 확인"],
            capture_output=True, text=True,
            cwd="/Users/hana/Downloads/blog-automation-v2"
        )
        log(f"[워커] 텔레그램 전송 결과: {result.stdout.strip()} {result.stderr.strip()}")

    finally:
        pw.stop()
        log("[워커] 완료.")

if __name__ == "__main__":
    main()
