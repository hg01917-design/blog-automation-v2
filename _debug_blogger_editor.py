#!/usr/bin/env python3
"""Blogger 에디터 UI 탐색 스크립트 - 이미지 삽입 버튼 찾기"""
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

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://localhost:9222")
    ctx = browser.contexts[0]

    # 새 페이지 생성해서 에디터 열기
    page = ctx.new_page()
    print(f"에디터 열기: {edit_url}")
    page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(6)  # 에디터 로딩 대기

    print(f"현재 URL: {page.url}")

    # 스크린샷
    page.screenshot(path="/tmp/blogger_editor_1.png", full_page=False)
    print("스크린샷 저장: /tmp/blogger_editor_1.png")

    # iframe 확인
    frames = page.frames
    print(f"\niframe 수: {len(frames)}")
    for f in frames:
        print(f"  URL: {f.url[:100]}")

    # contenteditable 확인
    editors = page.locator("[contenteditable='true']").all()
    print(f"\ncontenteditable 요소: {len(editors)}개")

    # 모든 버튼 aria-label 출력
    btns = page.locator("button[aria-label]").all()
    print(f"\nbutton[aria-label] 목록 ({len(btns)}개):")
    for i, btn in enumerate(btns):
        try:
            label = btn.get_attribute("aria-label")
            visible = btn.is_visible()
            print(f"  [{i}] '{label}' (visible={visible})")
        except:
            pass

    # div[role='button'] 확인
    div_btns = page.locator("div[role='button'][aria-label]").all()
    print(f"\ndiv[role='button'] 목록 ({len(div_btns)}개):")
    for i, btn in enumerate(div_btns):
        try:
            label = btn.get_attribute("aria-label")
            visible = btn.is_visible()
            print(f"  [{i}] '{label}' (visible={visible})")
        except:
            pass

    page.close()

print("\n탐색 완료")
