"""워커: goodisak 에디터 이미지 영역 스크롤 후 스크린샷"""
import os
import sys
import subprocess

sys.path.insert(0, "/Users/hana/Downloads/blog-automation-v2")
from browser import connect_cdp, get_or_create_page

BASE_DIR = "/Users/hana/Downloads/blog-automation-v2"
IMAGES_DIR = os.path.join(BASE_DIR, "images")

def log(msg):
    print(msg, flush=True)

def main():
    os.makedirs(IMAGES_DIR, exist_ok=True)

    log("[워커] CDP 연결 중...")
    pw, browser = connect_cdp(on_log=log)

    try:
        page = get_or_create_page(browser, url_contains="goodisak.tistory.com/manage/newpost")
        log(f"[워커] 탭 URL: {page.url}")

        # 여러 스크롤 위치에서 스크린샷 찍기
        scroll_positions = [0, 500, 1000, 1500, 2000, 2500, 3000]

        for y in scroll_positions:
            page.evaluate(f"() => window.scrollTo(0, {y})")
            page.wait_for_timeout(600)
            path = os.path.join(IMAGES_DIR, f"editor_scroll_{y}.png")
            page.screenshot(path=path)
            log(f"[워커] 스크린샷 저장: {path}")

        # 이미지가 있는지 판단: 각 스크린샷을 텔레그램으로 전송
        # 일단 500, 1000, 1500 위치 3장을 묶어서 전송
        for y in [500, 1000, 1500, 2000]:
            path = os.path.join(IMAGES_DIR, f"editor_scroll_{y}.png")
            result = subprocess.run(
                ["python3", "tg_send.py", "--photo", path, f"에디터 이미지 영역 (scroll={y})"],
                capture_output=True, text=True,
                cwd=BASE_DIR
            )
            log(f"[워커] 텔레그램 전송 scroll={y}: {result.stdout.strip()} {result.stderr.strip()}")
            page.wait_for_timeout(500)

        log("[워커] 완료.")

    finally:
        pw.stop()

if __name__ == "__main__":
    main()
