#!/usr/bin/env python3
"""JS interceptor로 파일 인풋 가로채기 테스트"""
import time
from playwright.sync_api import sync_playwright

BLOGGER_BLOG_ID = "5956656339719895415"
POST_ID = "7327638874699086892"
edit_url = f"https://www.blogger.com/blog/post/edit/{BLOGGER_BLOG_ID}/{POST_ID}"
TEST_IMG = "/Users/hana/Downloads/blog-automation-v2/images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-1.webp"

INTERCEPTOR_SCRIPT = """
    // file input의 click을 가로채서 네이티브 다이얼로그 억제
    const origProto = HTMLInputElement.prototype;
    const origClick = origProto.click;
    origProto.click = function() {
        if (this.type === 'file') {
            console.log('[INTERCEPT] file input click 감지!');
            window.__capturedFileInput = this;
            // 네이티브 다이얼로그 억제 (origClick 호출 안 함)
            return;
        }
        return origClick.call(this);
    };
    console.log('[INTERCEPT] File input interceptor 설치 완료');
"""

FIND_JS = """() => {
    let best = null;
    function traverse(node) {
        if (!node) return;
        if (node.shadowRoot) traverse(node.shadowRoot);
        let children = node.children || [];
        for (let i = 0; i < children.length; i++) traverse(children[i]);
        let text = (node.textContent || '').trim();
        if (text.includes('컴퓨터에서 업로드')) {
            let rect = node.getBoundingClientRect();
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

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://localhost:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    # JS 인터셉터 설치 (페이지 로드 시 실행)
    page.add_init_script(INTERCEPTOR_SCRIPT)
    print("인터셉터 스크립트 추가")

    page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)
    print(f"현재 URL: {page.url}")

    # 이미지 버튼 클릭
    img_btn = page.locator("div[role='button'][aria-label='이미지 삽입']").first
    img_btn.click()
    time.sleep(1.5)

    # 메뉴 항목 찾기
    rect = page.evaluate(FIND_JS)
    print(f"메뉴 항목 위치: {rect}")

    if rect:
        print(f"클릭: ({rect['x']:.0f}, {rect['y']:.0f}) 크기: {rect['w']:.0f}x{rect['h']:.0f}")
        page.mouse.click(rect['x'], rect['y'])
        time.sleep(1)

        # 캡처된 file input 확인
        captured = page.evaluate("() => window.__capturedFileInput ? 'CAPTURED' : 'NOT_CAPTURED'")
        print(f"file input 캡처: {captured}")

        if captured == 'CAPTURED':
            # set_input_files로 파일 설정
            try:
                page.evaluate("""(path) => {
                    window.__capturedFileInput.id = '__tempInput123';
                }""", TEST_IMG)
                page.locator("#__tempInput123").set_input_files(TEST_IMG)
                print("✅ set_input_files 성공!")
                time.sleep(3)
                page.screenshot(path="/tmp/after_set_files.png")
                print("스크린샷: /tmp/after_set_files.png")
            except Exception as e:
                print(f"set_input_files 오류: {e}")
        else:
            # 인터셉터가 없는 경우 - 그냥 set_input_files 시도
            print("일반 방식: input[type=file] set_input_files 시도")
            try:
                file_input = page.locator("input[type='file']").first
                if file_input.count() > 0:
                    file_input.set_input_files(TEST_IMG)
                    print("✅ 직접 set_input_files 성공!")
                else:
                    print("❌ file input 없음")
            except Exception as e:
                print(f"오류: {e}")

    page.close()
