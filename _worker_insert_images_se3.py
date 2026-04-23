"""워커: goodisak SE3 에디터에 이미지 삽입 (툴바 버튼 클릭 방식)"""
import os
import sys
import subprocess

sys.path.insert(0, "/Users/hana/Downloads/blog-automation-v2")
from browser import connect_cdp, get_or_create_page

BASE_DIR = "/Users/hana/Downloads/blog-automation-v2"
IMAGES_DIR = os.path.join(BASE_DIR, "images")

# 삽입할 이미지 파일 목록 (실제 존재하는 파일)
IMAGE_FILES = [
    os.path.join(IMAGES_DIR, "bing-gaming-1.jpg"),
    os.path.join(IMAGES_DIR, "bing-gaming-2.jpg"),
    os.path.join(IMAGES_DIR, "bing-gaming-3.jpg"),
    os.path.join(IMAGES_DIR, "bing-gaming-4.jpg"),
]

def log(msg):
    print(msg, flush=True)

def main():
    log("[워커] CDP 연결 중...")
    pw, browser = connect_cdp(on_log=log)

    try:
        page = get_or_create_page(browser, url_contains="goodisak.tistory.com/manage/newpost")
        log(f"[워커] 탭 URL: {page.url}")

        # 존재하는 이미지만 필터링
        images_to_insert = [f for f in IMAGE_FILES if os.path.exists(f)]
        log(f"[워커] 삽입할 이미지 {len(images_to_insert)}장: {[os.path.basename(f) for f in images_to_insert]}")

        if not images_to_insert:
            log("[워커] 삽입할 이미지가 없습니다!")
            return

        # 에디터 내 이미지 업로드 버튼 찾기
        # SE3 에디터 툴바에서 이미지 버튼 탐색
        log("[워커] 이미지 업로드 버튼 탐색 중...")

        # 툴바 버튼들 확인
        toolbar_btns = page.query_selector_all("[data-tiara-id], .toolbar button, .se-toolbar button, button[title*='이미지'], button[title*='image'], button[title*='Image']")
        log(f"[워커] 툴바 버튼 수: {len(toolbar_btns)}")
        for btn in toolbar_btns[:10]:
            try:
                title = btn.get_attribute("title") or btn.get_attribute("aria-label") or btn.inner_text()
                log(f"  버튼: {title[:50]}")
            except Exception:
                pass

        # SE3 에디터 이미지 버튼 선택자 시도 (여러 가지)
        img_btn_selectors = [
            "button[data-command='insertImage']",
            "button[data-type='image']",
            ".se-toolbar-item-image button",
            ".toolbar-image button",
            "button[title*='이미지']",
            "button[aria-label*='이미지']",
            "button[title*='사진']",
            "button[aria-label*='사진']",
            ".se-btn-image",
            "[class*='image'][role='button']",
        ]

        img_btn = None
        for sel in img_btn_selectors:
            btn = page.query_selector(sel)
            if btn:
                img_btn = btn
                log(f"[워커] 이미지 버튼 발견: {sel}")
                break

        if not img_btn:
            # 모든 버튼 목록 출력해서 디버깅
            all_btns = page.query_selector_all("button")
            log(f"[워커] 전체 button 수: {len(all_btns)}")
            for btn in all_btns:
                try:
                    title = btn.get_attribute("title") or btn.get_attribute("aria-label") or btn.get_attribute("class") or ""
                    if title:
                        log(f"  button: {title[:80]}")
                except Exception:
                    pass

            # 스크린샷 찍어서 현재 상태 확인
            path = os.path.join(IMAGES_DIR, "debug_toolbar.png")
            page.screenshot(path=path)
            subprocess.run(
                ["python3", "tg_send.py", "--photo", path, "이미지 버튼 탐색 실패 - 툴바 확인 필요"],
                capture_output=True, text=True, cwd=BASE_DIR
            )
            log("[워커] 이미지 버튼을 찾지 못했습니다. 스크린샷 전송됨.")
            return

        # 이미지 한 장씩 삽입
        for i, img_path in enumerate(images_to_insert):
            log(f"[워커] 이미지 {i+1}/{len(images_to_insert)} 삽입 중: {os.path.basename(img_path)}")

            # 이미지 버튼 클릭
            img_btn.click()
            page.wait_for_timeout(1500)

            # 파일 선택 input 기다리기
            try:
                # input[type=file] 대기
                file_input = page.wait_for_selector("input[type='file']", timeout=5000)
                log(f"[워커] 파일 input 발견")
                file_input.set_input_files(img_path)
                page.wait_for_timeout(3000)
                log(f"[워커] 이미지 {i+1} 업로드 완료")

                # 스크린샷
                path = os.path.join(IMAGES_DIR, f"after_insert_{i+1}.png")
                page.screenshot(path=path)
                subprocess.run(
                    ["python3", "tg_send.py", "--photo", path, f"이미지 {i+1} 삽입 후"],
                    capture_output=True, text=True, cwd=BASE_DIR
                )

            except Exception as e:
                log(f"[워커] 파일 input 오류: {e}")
                path = os.path.join(IMAGES_DIR, f"error_insert_{i+1}.png")
                page.screenshot(path=path)
                subprocess.run(
                    ["python3", "tg_send.py", "--photo", path, f"이미지 {i+1} 삽입 오류: {e}"],
                    capture_output=True, text=True, cwd=BASE_DIR
                )
                break

        log("[워커] 이미지 삽입 완료.")

    finally:
        pw.stop()

if __name__ == "__main__":
    main()
