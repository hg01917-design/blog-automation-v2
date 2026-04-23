#!/usr/bin/env python3
"""기발행된 Blogger 글에 이미지를 삽입하는 스크립트 (Shadow DOM 대응)"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BLOGGER_BLOG_ID = "5956656339719895415"  # tech.baremi542.com (blogspot_it)
POST_ID = "7327638874699086892"
IMAGES = [
    "/Users/hana/Downloads/blog-automation-v2/images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-1.webp",
    "/Users/hana/Downloads/blog-automation-v2/images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-2.webp",
    "/Users/hana/Downloads/blog-automation-v2/images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-3.webp",
    "/Users/hana/Downloads/blog-automation-v2/images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-4.webp",
    "/Users/hana/Downloads/blog-automation-v2/images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-5.webp",
]

edit_url = f"https://www.blogger.com/blog/post/edit/{BLOGGER_BLOG_ID}/{POST_ID}"

FIND_UPLOAD_ITEM_JS = """() => {
    let best = null;
    function traverse(node) {
        if (!node) return;
        if (node.shadowRoot) traverse(node.shadowRoot);
        let children = node.children || [];
        for (let i = 0; i < children.length; i++) traverse(children[i]);
        let text = (node.textContent || '').trim();
        if (text.includes('컴퓨터에서 업로드')) {
            let rect = node.getBoundingClientRect();
            // 작은 요소만 (높이 80px 미만, 너비 600px 미만, 표시되어 있음)
            if (rect.width > 10 && rect.height > 10 && rect.height < 80 && rect.width < 600) {
                let area = rect.width * rect.height;
                if (!best || area < best.area) {
                    best = {x: rect.left + rect.width/2, y: rect.top + rect.height/2, w: rect.width, h: rect.height, area: area};
                }
            }
        }
    }
    traverse(document);
    return best;
}"""

def log(msg):
    print(msg, flush=True)

def click_upload_menu(page):
    """Shadow DOM 내 '컴퓨터에서 업로드' 클릭 위치 반환 후 mouse.click"""
    rect = page.evaluate(FIND_UPLOAD_ITEM_JS)
    if not rect:
        log("Shadow DOM에서 '컴퓨터에서 업로드' 못 찾음")
        return False
    log(f"  클릭 위치: ({rect['x']:.0f}, {rect['y']:.0f}), 크기: {rect['w']:.0f}x{rect['h']:.0f}")
    page.mouse.click(rect['x'], rect['y'])
    return True

def insert_images():
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = browser.contexts[0]
        page = ctx.new_page()

        log(f"에디터 열기: {edit_url}")
        page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(6)
        log(f"현재 URL: {page.url}")

        # 에디터 frame 내 H2 수집
        editor_frame = None
        for frame in page.frames:
            if "post/edit" in frame.url:
                try:
                    if frame.locator("h2").count() > 0:
                        editor_frame = frame
                        log(f"에디터 frame 발견: H2 {frame.locator('h2').count()}개")
                        break
                except:
                    pass

        h2_els = editor_frame.locator("h2").all() if editor_frame else []
        log(f"H2 요소: {len(h2_els)}개")

        img_btn = page.locator("div[role='button'][aria-label='이미지 삽입']").first

        # 각 이미지 삽입
        for img_idx, img_path in enumerate(IMAGES):
            if not Path(img_path).exists():
                log(f"파일 없음: {img_path}")
                continue

            log(f"\n--- 이미지 {img_idx+1}/{len(IMAGES)}: {Path(img_path).name} ---")

            # H2 뒤에 커서 배치
            if editor_frame and img_idx < len(h2_els):
                try:
                    h2_els[img_idx].click()
                    page.keyboard.press("End")
                    page.keyboard.press("Enter")
                    log(f"H2[{img_idx}] 다음에 커서 배치")
                    time.sleep(0.5)
                except Exception as e:
                    log(f"커서 배치 오류: {e}")

            # 이미지 버튼 클릭
            img_btn.click()
            log("이미지 삽입 버튼 클릭")
            time.sleep(1.5)

            # file chooser expect → shadow DOM 클릭
            try:
                with page.expect_file_chooser(timeout=12000) as fc_info:
                    ok = click_upload_menu(page)
                    if not ok:
                        log("업로드 메뉴 클릭 실패")
                        page.keyboard.press("Escape")
                        continue
                fc = fc_info.value
                fc.set_files(img_path)
                log(f"✅ 파일 선택: {Path(img_path).name}")
                time.sleep(5)
            except Exception as e:
                log(f"file chooser 실패: {e}")
                page.keyboard.press("Escape")
                time.sleep(1)
                continue

            # 스크린샷 - 업로드 후
            page.screenshot(path=f"/tmp/blogger_upload_{img_idx}.png")
            log(f"업로드 후 스크린샷: /tmp/blogger_upload_{img_idx}.png")

            # 확인 버튼 (있으면)
            for ok_sel in ['button:has-text("선택")', 'button:has-text("확인")', 'button:has-text("삽입")']:
                try:
                    btn = page.locator(ok_sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        log(f"확인 버튼 클릭: {ok_sel}")
                        time.sleep(2)
                        break
                except:
                    pass

            time.sleep(1)

        # 최종 스크린샷
        page.screenshot(path="/tmp/blogger_final.png")
        log("\n최종 스크린샷: /tmp/blogger_final.png")

        # 업데이트 저장
        try:
            # aria-disabled='false' 인 업데이트 버튼
            update_btn = page.locator("div[role='button'][aria-label='업데이트']").first
            update_btn.wait_for(state="visible", timeout=5000)
            # disabled가 아닌지 확인
            disabled = update_btn.get_attribute("aria-disabled")
            if disabled == "true":
                log("업데이트 버튼 disabled - 변경사항 없음?")
            else:
                update_btn.click()
                log("업데이트 클릭 - 저장 중...")
                time.sleep(5)
                log("저장 완료!")
        except Exception as e:
            log(f"저장 오류: {e}")

        page.close()

    log("\n=== 완료 ===")

insert_images()
