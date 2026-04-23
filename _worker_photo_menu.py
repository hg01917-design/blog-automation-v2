"""워커: TinyMCE 이미지 버튼 → 사진 메뉴 선택 → 파일 업로드"""
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

def get_image_btn_pos(page):
    """TinyMCE 이미지 버튼 위치 반환"""
    return page.evaluate("""() => {
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

def main():
    log("[워커] CDP 연결 중...")
    pw, browser = connect_cdp(on_log=log)

    try:
        page = get_or_create_page(browser, url_contains="goodisak.tistory.com/manage/newpost")
        log(f"[워커] 탭 URL: {page.url}")

        # 현재 에디터 상태 스크린샷
        path = os.path.join(IMAGES_DIR, "current_state.png")
        page.screenshot(path=path)
        subprocess.run(
            ["python3", "tg_send.py", "--photo", path, "현재 에디터 상태 (삽입 전)"],
            capture_output=True, text=True, cwd=BASE_DIR
        )

        images_to_insert = [f for f in IMAGE_FILES if os.path.exists(f)]
        log(f"[워커] 삽입할 이미지 {len(images_to_insert)}장")

        for i, img_path in enumerate(images_to_insert):
            log(f"\n=== 이미지 {i+1}/{len(images_to_insert)}: {os.path.basename(img_path)} ===")

            # 1. 이미지 버튼 클릭
            pos = get_image_btn_pos(page)
            if not pos:
                log("[워커] 이미지 버튼 못 찾음!")
                break

            log(f"[워커] 이미지 버튼 클릭: ({pos['x']:.0f}, {pos['y']:.0f})")
            page.mouse.click(pos['x'], pos['y'])
            page.wait_for_timeout(1000)

            # 2. 드롭다운에서 "사진" 메뉴 항목 클릭
            photo_item = None
            menu_items = page.query_selector_all(".mce-menu-item")
            log(f"[워커] 드롭다운 {len(menu_items)}개 아이템")
            for item in menu_items:
                text = item.inner_text().strip()
                log(f"  메뉴: [{text}]")
                if text == "사진":
                    photo_item = item
                    break

            if photo_item:
                box = photo_item.bounding_box()
                if box:
                    log(f"[워커] '사진' 메뉴 클릭: ({box['x']+box['width']/2:.0f}, {box['y']+box['height']/2:.0f})")
                    page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                    page.wait_for_timeout(1500)
            else:
                log("[워커] '사진' 메뉴 없음! 메뉴 닫고 다음 방법 시도")
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                continue

            # 3. file input 탐색
            file_input = page.query_selector("input[type='file']")
            if not file_input:
                # 잠시 기다린 후 재시도
                page.wait_for_timeout(1000)
                file_input = page.query_selector("input[type='file']")

            if file_input:
                log(f"[워커] file input 발견, 파일 설정: {os.path.basename(img_path)}")
                file_input.set_input_files(img_path)
                page.wait_for_timeout(5000)

                # 업로드 완료 - 확인 버튼
                for sel in [
                    "button:has-text('확인')",
                    "button:has-text('삽입')",
                    "button:has-text('업로드')",
                    ".mce-primary button",
                    ".btn-primary",
                ]:
                    btn = page.query_selector(sel)
                    if btn:
                        box = btn.bounding_box()
                        if box:
                            log(f"[워커] 확인 버튼 클릭: {sel}")
                            page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                            page.wait_for_timeout(2000)
                        break

                path = os.path.join(IMAGES_DIR, f"inserted_{i+1}.png")
                page.screenshot(path=path)
                subprocess.run(
                    ["python3", "tg_send.py", "--photo", path, f"이미지 {i+1} 삽입 후"],
                    capture_output=True, text=True, cwd=BASE_DIR
                )
                log(f"[워커] 이미지 {i+1} 완료")
            else:
                log("[워커] file input 없음!")
                path = os.path.join(IMAGES_DIR, f"no_input_{i+1}.png")
                page.screenshot(path=path)
                subprocess.run(
                    ["python3", "tg_send.py", "--photo", path, f"file input 없음 {i+1}"],
                    capture_output=True, text=True, cwd=BASE_DIR
                )

        # 최종
        path = os.path.join(IMAGES_DIR, "final_after_insert.png")
        page.screenshot(path=path)
        subprocess.run(
            ["python3", "tg_send.py", "--photo", path, "이미지 삽입 최종 상태"],
            capture_output=True, text=True, cwd=BASE_DIR
        )
        log("[워커] 완료.")

    finally:
        pw.stop()

if __name__ == "__main__":
    main()
