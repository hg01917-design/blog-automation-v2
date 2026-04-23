"""워커: TinyMCE 에디터에 이미지 삽입 (툴바 이미지 버튼 클릭)"""
import os
import sys
import subprocess

sys.path.insert(0, "/Users/hana/Downloads/blog-automation-v2")
from browser import connect_cdp, get_or_create_page

BASE_DIR = "/Users/hana/Downloads/blog-automation-v2"
IMAGES_DIR = os.path.join(BASE_DIR, "images")

# 삽입할 이미지 파일 목록
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

        images_to_insert = [f for f in IMAGE_FILES if os.path.exists(f)]
        log(f"[워커] 삽입할 이미지: {[os.path.basename(f) for f in images_to_insert]}")

        # TinyMCE 이미지 버튼: .mce-i-image의 부모 버튼(div)
        # 실제 클릭 가능 요소는 .mce-i-image를 감싸는 .mce-widget.mce-btn
        for i, img_path in enumerate(images_to_insert):
            log(f"\n[워커] === 이미지 {i+1}/{len(images_to_insert)} 삽입: {os.path.basename(img_path)} ===")

            # 이미지 버튼 찾기 (mce-i-image 아이콘의 부모 버튼)
            img_btn = page.query_selector(".mce-i-image")
            if not img_btn:
                log("[워커] .mce-i-image 버튼을 찾지 못했습니다.")
                break

            # 부모 클릭 가능 요소 찾기
            btn_container = page.query_selector(".mce-widget.mce-btn:has(.mce-i-image)")
            if not btn_container:
                # 직접 아이콘 클릭
                log("[워커] 컨테이너 없음, 아이콘 직접 클릭")
                btn_container = img_btn

            log(f"[워커] 이미지 버튼 클릭")
            btn_container.click()
            page.wait_for_timeout(1500)

            # 클릭 후 화면 확인
            path = os.path.join(IMAGES_DIR, f"after_click_{i+1}.png")
            page.screenshot(path=path)
            log(f"[워커] 클릭 후 스크린샷: {path}")

            # 파일 input 탐색
            file_input = page.query_selector("input[type='file']")
            if file_input:
                log(f"[워커] file input 발견, 파일 설정 중...")
                file_input.set_input_files(img_path)
                page.wait_for_timeout(3000)

                # 업로드 완료 확인 버튼 (확인/삽입/OK 등)
                for confirm_sel in ["button:has-text('확인')", "button:has-text('삽입')", "button:has-text('OK')", ".mce-primary button", ".tox-button--primary"]:
                    confirm_btn = page.query_selector(confirm_sel)
                    if confirm_btn:
                        log(f"[워커] 확인 버튼 클릭: {confirm_sel}")
                        confirm_btn.click()
                        page.wait_for_timeout(2000)
                        break

                path = os.path.join(IMAGES_DIR, f"after_upload_{i+1}.png")
                page.screenshot(path=path)
                subprocess.run(
                    ["python3", "tg_send.py", "--photo", path, f"이미지 {i+1} 업로드 후 에디터 상태"],
                    capture_output=True, text=True, cwd=BASE_DIR
                )
                log(f"[워커] 이미지 {i+1} 업로드 완료")
            else:
                log("[워커] file input 없음 — 다이얼로그/팝업 확인 필요")
                # 현재 화면에 어떤 요소가 떴는지 확인
                dialogs = page.query_selector_all(".mce-window, .mce-container.mce-panel, [role='dialog']")
                log(f"[워커] 다이얼로그 수: {len(dialogs)}")
                for d in dialogs:
                    log(f"  dialog class: {d.get_attribute('class')}")

                # 팝업이 떴을 경우 닫고 다음 방법 시도
                esc_btn = page.query_selector(".mce-close")
                if esc_btn:
                    esc_btn.click()
                    page.wait_for_timeout(500)
                break

        # 최종 스크린샷
        path = os.path.join(IMAGES_DIR, "final_editor.png")
        page.screenshot(path=path)
        subprocess.run(
            ["python3", "tg_send.py", "--photo", path, "이미지 삽입 완료 - 최종 에디터 상태"],
            capture_output=True, text=True, cwd=BASE_DIR
        )
        log(f"[워커] 최종 스크린샷: {path}")
        log("[워커] 완료.")

    finally:
        pw.stop()

if __name__ == "__main__":
    main()
