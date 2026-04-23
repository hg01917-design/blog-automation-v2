"""워커: goodisak 에디터 iframe 내부 스크롤 후 스크린샷"""
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

        # iframe 목록 확인
        frames = page.frames
        log(f"[워커] 전체 frame 수: {len(frames)}")
        for i, f in enumerate(frames):
            log(f"  frame[{i}] url={f.url}")

        # 에디터 iframe 찾기 (tinymce 또는 editor 포함)
        editor_frame = None
        for f in frames:
            if "tistory" in f.url or f.url == "about:blank" or f.url == "":
                # 에디터 body가 있는 frame 확인
                try:
                    body_len = f.evaluate("() => document.body ? document.body.innerHTML.length : 0")
                    log(f"  -> body length: {body_len}")
                    if body_len > 1000:
                        editor_frame = f
                        log(f"  -> 에디터 frame 선택: {f.url}")
                        break
                except Exception as e:
                    log(f"  -> evaluate 실패: {e}")

        if editor_frame:
            # 에디터 전체 높이 확인
            total_height = editor_frame.evaluate("() => document.body.scrollHeight")
            log(f"[워커] 에디터 body 전체 높이: {total_height}")

            # 여러 위치 스크롤하면서 스크린샷
            positions = [0, 500, 1000, 1500, 2000, 2500, 3000]
            for y in positions:
                editor_frame.evaluate(f"() => window.scrollTo(0, {y})")
                page.wait_for_timeout(600)
                path = os.path.join(IMAGES_DIR, f"editor_iframe_{y}.png")
                page.screenshot(path=path)
                log(f"[워커] 스크린샷: {path}")
        else:
            log("[워커] 에디터 frame을 찾지 못함 — 페이지 전체 스크린샷")
            # 페이지 전체 스크린샷
            path = os.path.join(IMAGES_DIR, "editor_full.png")
            page.screenshot(path=path, full_page=True)
            log(f"[워커] 전체 스크린샷: {path}")
            result = subprocess.run(
                ["python3", "tg_send.py", "--photo", path, "에디터 전체 (iframe 미발견)"],
                capture_output=True, text=True, cwd=BASE_DIR
            )
            log(f"[워커] 텔레그램: {result.stdout.strip()} {result.stderr.strip()}")
            return

        # 이미지가 보이는 구간 텔레그램 전송
        for y in positions:
            path = os.path.join(IMAGES_DIR, f"editor_iframe_{y}.png")
            result = subprocess.run(
                ["python3", "tg_send.py", "--photo", path, f"에디터 이미지 영역 scroll={y}"],
                capture_output=True, text=True, cwd=BASE_DIR
            )
            log(f"[워커] 텔레그램 scroll={y}: {result.stdout.strip()} {result.stderr.strip()}")
            page.wait_for_timeout(400)

        log("[워커] 완료.")

    finally:
        pw.stop()

if __name__ == "__main__":
    main()
