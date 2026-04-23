#!/usr/bin/env python3
import time
from playwright.sync_api import sync_playwright

BLOGGER_BLOG_ID = "5956656339719895415"
POST_ID = "7327638874699086892"
edit_url = f"https://www.blogger.com/blog/post/edit/{BLOGGER_BLOG_ID}/{POST_ID}"
TEST_IMG = "/Users/hana/Downloads/blog-automation-v2/images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-1.webp"

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://localhost:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)
    page.keyboard.press("Escape")
    time.sleep(1)

    img_btn = page.locator("div[role='button'][aria-label='이미지 삽입']").first
    img_btn.click(force=True)
    time.sleep(2)

    page.screenshot(path="/tmp/d2_dropdown.png")
    print("드롭다운 스크린샷 저장")

    # "컴퓨터에서 업로드" 클릭 전 frames
    print(f"클릭 전 frames: {len(page.frames)}")

    # expect_file_chooser 방식
    print("expect_file_chooser 설정 후 클릭...")
    try:
        with page.expect_file_chooser(timeout=8000) as fc_info:
            page.mouse.click(640, 212)
        fc = fc_info.value
        print(f"✅ File chooser 발동! multiple={fc.is_multiple()}")
        fc.set_files(TEST_IMG)
        print("파일 선택 완료!")
        time.sleep(5)
        page.screenshot(path="/tmp/d2_after_upload.png")
        print("업로드 후 스크린샷 저장")
    except Exception as e:
        print(f"File chooser 실패: {e}")
        time.sleep(1)
        print(f"클릭 후 frames: {len(page.frames)}")
        for f in page.frames:
            print(f"  URL: {f.url[:120]}")
        page.screenshot(path="/tmp/d2_after_click.png")
        print("클릭 후 스크린샷 저장")

    page.close()
