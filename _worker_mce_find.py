"""워커: TinyMCE 이미지 버튼 정확한 위치 파악"""
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

        # TinyMCE 툴바 버튼들의 위치와 정보 수집
        result = page.evaluate("""() => {
            // 모든 mce 관련 div 버튼
            const btns = document.querySelectorAll('.mce-btn, .mce-widget.mce-btn');
            return Array.from(btns).map(el => {
                const rect = el.getBoundingClientRect();
                const icon = el.querySelector('i[class*="mce-i-"]');
                return {
                    cls: el.className,
                    title: el.getAttribute('title') || '',
                    iconClass: icon ? icon.className : '',
                    visible: rect.width > 0 && rect.height > 0,
                    x: rect.x,
                    y: rect.y,
                    w: rect.width,
                    h: rect.height,
                };
            });
        }""")

        log(f"[워커] mce 버튼 수: {len(result)}")
        for r in result:
            log(f"  icon={r['iconClass'][:40]} title={r['title']} visible={r['visible']} pos=({r['x']:.0f},{r['y']:.0f})")

        # 이미지 버튼 위치 찾기
        img_btn_info = None
        for r in result:
            if 'mce-i-image' in r.get('iconClass', '') and r['visible']:
                img_btn_info = r
                log(f"[워커] 이미지 버튼 찾음: pos=({r['x']:.0f},{r['y']:.0f}), size=({r['w']:.0f}x{r['h']:.0f})")
                break

        if img_btn_info:
            # 실제 페이지에서 해당 위치의 요소 찾아서 클릭
            cx = img_btn_info['x'] + img_btn_info['w'] / 2
            cy = img_btn_info['y'] + img_btn_info['h'] / 2
            log(f"[워커] 마우스 클릭: ({cx:.0f}, {cy:.0f})")
            page.mouse.click(cx, cy)
            page.wait_for_timeout(2000)

            path = os.path.join(IMAGES_DIR, "after_img_btn_click.png")
            page.screenshot(path=path)
            subprocess.run(
                ["python3", "tg_send.py", "--photo", path, "이미지 버튼 클릭 후 팝업 확인"],
                capture_output=True, text=True, cwd=BASE_DIR
            )
            log(f"[워커] 스크린샷: {path}")

            # file input 확인
            file_input = page.query_selector("input[type='file']")
            log(f"[워커] file input: {file_input}")

            # 팝업 내용 확인
            popups = page.query_selector_all(".mce-window, [role='dialog'], .mce-floatpanel")
            log(f"[워커] 팝업 수: {len(popups)}")
            for p in popups:
                log(f"  팝업 class: {p.get_attribute('class')}")
                # 팝업 내 탭/버튼 확인
                tabs = p.query_selector_all(".mce-tab, button, input")
                for t in tabs:
                    log(f"    요소: {t.evaluate('el => el.tagName')} class={t.get_attribute('class')} text={t.inner_text()[:30]}")
        else:
            log("[워커] 가시적인 이미지 버튼을 찾지 못했습니다.")
            # 전체 스크린샷
            path = os.path.join(IMAGES_DIR, "debug_no_imgbtn.png")
            page.screenshot(path=path)
            subprocess.run(
                ["python3", "tg_send.py", "--photo", path, "이미지 버튼 없음 - 에디터 확인"],
                capture_output=True, text=True, cwd=BASE_DIR
            )

    finally:
        pw.stop()

if __name__ == "__main__":
    main()
