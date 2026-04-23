#!/usr/bin/env python3
"""JS로 shadow DOM 요소 직접 클릭 테스트"""
import time
from playwright.sync_api import sync_playwright

BLOGGER_BLOG_ID = "5956656339719895415"
POST_ID = "7327638874699086892"
edit_url = f"https://www.blogger.com/blog/post/edit/{BLOGGER_BLOG_ID}/{POST_ID}"
TEST_IMG = "/Users/hana/Downloads/blog-automation-v2/images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-1.webp"

CLICK_UPLOAD_JS = """() => {
    let found = null;
    function traverse(node) {
        if (!node) return;
        if (node.shadowRoot) traverse(node.shadowRoot);
        let children = node.children || [];
        for (let i = 0; i < children.length; i++) {
            let child = children[i];
            let text = (child.textContent || '').trim();
            if (text.includes('컴퓨터에서 업로드')) {
                let rect = child.getBoundingClientRect();
                // 작은 요소이면서 높이가 80 미만인 것
                if (rect.width > 10 && rect.height > 10 && rect.height < 80 && rect.width < 600) {
                    if (!found || (rect.width * rect.height < found.area)) {
                        found = {el: child, area: rect.width * rect.height,
                                 x: rect.left, y: rect.top, w: rect.width, h: rect.height};
                    }
                }
            }
            traverse(child);
        }
    }
    traverse(document);
    if (found) {
        console.log('Found element:', found.x, found.y, found.w, found.h, found.el.tagName, found.el.textContent.slice(0, 50));
        found.el.click();  // JS 직접 클릭
        return {x: found.x, y: found.y, w: found.w, h: found.h, clicked: true};
    }
    return null;
}"""

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://localhost:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)
    page.keyboard.press("Escape")
    time.sleep(1)

    # 이미지 버튼 클릭
    img_btn = page.locator("div[role='button'][aria-label='이미지 삽입']").first
    img_btn.click(force=True)
    time.sleep(2)

    print("이미지 버튼 클릭 완료")
    page.screenshot(path="/tmp/debug_dropdown.png")
    print("드롭다운 스크린샷: /tmp/debug_dropdown.png")

    # JS로 직접 클릭
    result = page.evaluate(CLICK_UPLOAD_JS)
    print(f"JS 클릭 결과: {result}")
    time.sleep(3)

    page.screenshot(path="/tmp/debug_after_js_click.png")
    print("JS 클릭 후 스크린샷: /tmp/debug_after_js_click.png")

    # frames 확인
    print(f"\nframes: {len(page.frames)}")
    for f in page.frames:
        print(f"  {f.url[:100]}")

    # file inputs 확인
    print("\nfile inputs:")
    for fi, frame in enumerate(page.frames):
        try:
            inputs = frame.locator('input[type="file"]').all()
            if inputs:
                print(f"  Frame[{fi}]: {len(inputs)}개")
        except: pass

    # 콘솔 로그 확인
    page.close()
