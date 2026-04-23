"""워커: TinyMCE 이미지 버튼 클릭 후 file input으로 이미지 삽입"""
import os
import sys
import subprocess

sys.path.insert(0, "/Users/hana/Downloads/blog-automation-v2")
from browser import connect_cdp, get_or_create_page

BASE_DIR = "/Users/hana/Downloads/blog-automation-v2"
IMAGES_DIR = os.path.join(BASE_DIR, "images")

IMAGE_FILES = [
    os.path.join(IMAGES_DIR, "gaming-laptop-1-1.jpg"),
    os.path.join(IMAGES_DIR, "gaming-laptop-1-2.jpg"),
    os.path.join(IMAGES_DIR, "gaming-laptop-1-3.jpg"),
    os.path.join(IMAGES_DIR, "gaming-laptop-1-4.jpg"),
]

def log(msg):
    print(msg, flush=True)

def click_image_btn(page):
    """TinyMCE 이미지 버튼을 mouse.click으로 클릭"""
    result = page.evaluate("""() => {
        const btns = document.querySelectorAll('.mce-btn, .mce-widget.mce-btn');
        for (const el of btns) {
            const icon = el.querySelector('i.mce-i-image');
            if (!icon) continue;
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                return { x: rect.x + rect.width/2, y: rect.y + rect.height/2 };
            }
        }
        return null;
    }""")
    if result:
        page.mouse.click(result['x'], result['y'])
        page.wait_for_timeout(1500)
        return True
    return False

def main():
    log("[워커] CDP 연결 중...")
    pw, browser = connect_cdp(on_log=log)

    try:
        page = get_or_create_page(browser, url_contains="goodisak.tistory.com/manage/newpost")
        log(f"[워커] 탭 URL: {page.url}")

        images_to_insert = [f for f in IMAGE_FILES if os.path.exists(f)]
        log(f"[워커] 삽입할 이미지 {len(images_to_insert)}장")

        # 먼저 현재 에디터에 이미지가 몇 개 있는지 확인 (iframe 내부)
        editor_frame = None
        for f in page.frames:
            if "tistory_ifr" in f.url or f.name == "editor-tistory_ifr":
                editor_frame = f
                break
        # iframe이 src가 about:blank일 수 있음 - name으로 찾기
        if not editor_frame:
            for ctx in browser.contexts:
                for p in ctx.pages:
                    if p == page:
                        for f in p.frames:
                            try:
                                cnt = f.evaluate("() => document.querySelectorAll('img').length")
                                if cnt >= 0:
                                    url = f.url
                                    log(f"  frame url={url} img={cnt}")
                                    if cnt > 0:
                                        editor_frame = f
                            except Exception:
                                pass

        for i, img_path in enumerate(images_to_insert):
            log(f"\n=== 이미지 {i+1}/{len(images_to_insert)}: {os.path.basename(img_path)} ===")

            # 이미지 버튼 클릭
            clicked = click_image_btn(page)
            if not clicked:
                log("[워커] 이미지 버튼 못 찾음")
                break

            # 드롭다운이 뜰 경우 첫 번째 메뉴 항목("내 PC에서 올리기" 등) 클릭
            # 잠시 후 메뉴 아이템 확인
            page.wait_for_timeout(800)
            menu_items = page.query_selector_all(".mce-menu-item, .mce-floatpanel .mce-menu-item-normal")
            if menu_items:
                log(f"[워커] 드롭다운 메뉴 {len(menu_items)}개 아이템")
                for item in menu_items:
                    text = item.inner_text().strip()
                    log(f"  메뉴: {text}")
                # 첫 번째 항목 클릭 (파일 업로드 관련)
                rect = menu_items[0].bounding_box()
                if rect:
                    page.mouse.click(rect['x'] + rect['width']/2, rect['y'] + rect['height']/2)
                    page.wait_for_timeout(1000)

            # file input 찾아서 파일 설정
            file_input = page.query_selector("input[type='file']")
            if file_input:
                log(f"[워커] file input 발견, 파일 설정: {os.path.basename(img_path)}")
                file_input.set_input_files(img_path)
                page.wait_for_timeout(4000)

                # 업로드 완료 후 팝업에서 확인/삽입 버튼 클릭
                for sel in ["button:has-text('확인')", "button:has-text('삽입')", "button:has-text('업로드')", ".mce-primary", ".btn-primary"]:
                    btn = page.query_selector(sel)
                    if btn:
                        log(f"[워커] 확인 버튼 클릭: {sel}")
                        try:
                            box = btn.bounding_box()
                            if box:
                                page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                                page.wait_for_timeout(2000)
                        except Exception as e:
                            log(f"[워커] 확인 버튼 클릭 오류: {e}")
                        break

                # 스크린샷
                path = os.path.join(IMAGES_DIR, f"inserted_{i+1}.png")
                page.screenshot(path=path)
                subprocess.run(
                    ["python3", "tg_send.py", "--photo", path, f"이미지 {i+1} 삽입 후"],
                    capture_output=True, text=True, cwd=BASE_DIR
                )
                log(f"[워커] 이미지 {i+1} 완료, 스크린샷: {path}")
            else:
                log("[워커] file input 없음!")
                path = os.path.join(IMAGES_DIR, f"no_input_{i+1}.png")
                page.screenshot(path=path)
                subprocess.run(
                    ["python3", "tg_send.py", "--photo", path, f"file input 없음 - 이미지 {i+1}"],
                    capture_output=True, text=True, cwd=BASE_DIR
                )
                break

        # 최종 상태
        path = os.path.join(IMAGES_DIR, "final_state.png")
        page.screenshot(path=path)
        subprocess.run(
            ["python3", "tg_send.py", "--photo", path, "최종 에디터 상태"],
            capture_output=True, text=True, cwd=BASE_DIR
        )
        log("[워커] 완료.")

    finally:
        pw.stop()

if __name__ == "__main__":
    main()
