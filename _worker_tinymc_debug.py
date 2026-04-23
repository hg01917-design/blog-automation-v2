"""워커: TinyMCE 에디터 구조 파악"""
import os
import sys
import subprocess
import json

sys.path.insert(0, "/Users/hana/Downloads/blog-automation-v2")
from browser import connect_cdp, get_or_create_page

BASE_DIR = "/Users/hana/Downloads/blog-automation-v2"
IMAGES_DIR = os.path.join(BASE_DIR, "images")

def log(msg):
    print(msg, flush=True)

def main():
    log("[워커] CDP 연결 중...")
    pw, browser = connect_cdp(on_log=log)

    try:
        page = get_or_create_page(browser, url_contains="goodisak.tistory.com/manage/newpost")
        log(f"[워커] 탭 URL: {page.url}")

        # TinyMCE 버튼 목록 파악
        btns = page.query_selector_all("button")
        log(f"[워커] 전체 버튼 {len(btns)}개:")
        for btn in btns:
            try:
                cls = btn.get_attribute("class") or ""
                title = btn.get_attribute("title") or ""
                aria = btn.get_attribute("aria-label") or ""
                inner = btn.inner_text()[:30] if btn.inner_text() else ""
                if cls or title or aria or inner:
                    log(f"  class={cls[:60]} title={title} aria={aria} text={inner}")
            except Exception:
                pass

        # iframe 목록
        log("\n[워커] iframe 목록:")
        iframes = page.query_selector_all("iframe")
        for i, f in enumerate(iframes):
            src = f.get_attribute("src") or f.get_attribute("id") or ""
            log(f"  iframe[{i}] src/id={src}")

        # TinyMCE 이미지 관련 버튼 탐색
        log("\n[워커] mce 관련 요소:")
        mce_els = page.query_selector_all("[class*='mce']")
        for el in mce_els[:20]:
            try:
                cls = el.get_attribute("class") or ""
                title = el.get_attribute("title") or ""
                tag = el.evaluate("el => el.tagName")
                log(f"  {tag} class={cls[:60]} title={title}")
            except Exception:
                pass

        # 스크린샷
        path = os.path.join(IMAGES_DIR, "debug_mce.png")
        page.screenshot(path=path)
        subprocess.run(
            ["python3", "tg_send.py", "--photo", path, "TinyMCE 에디터 구조 확인"],
            capture_output=True, text=True, cwd=BASE_DIR
        )
        log(f"[워커] 스크린샷: {path}")

    finally:
        pw.stop()

if __name__ == "__main__":
    main()
