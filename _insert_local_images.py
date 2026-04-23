#!/usr/bin/env python3
"""Blogger 이미지 삽입: 드롭다운 고정좌표 + Google Picker 내부 file input"""
import sys, json, re, time, urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

BLOGGER_BLOG_ID = "5956656339719895415"
POST_ID = "7327638874699086892"
IMAGES = [
    str(BASE_DIR / "images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-1.webp"),
    str(BASE_DIR / "images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-2.webp"),
    str(BASE_DIR / "images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-3.webp"),
    str(BASE_DIR / "images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-4.webp"),
    str(BASE_DIR / "images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-5.webp"),
]
edit_url = f"https://www.blogger.com/blog/post/edit/{BLOGGER_BLOG_ID}/{POST_ID}"

# 드롭다운 메뉴 '컴퓨터에서 업로드' 항목의 화면 좌표 (스크린샷으로 확인)
UPLOAD_X, UPLOAD_Y = 640, 212

def clear_images():
    from gsc_indexing import _get_access_token
    token = _get_access_token()
    get_url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/{POST_ID}"
    req = urllib.request.Request(get_url, headers={"Authorization": f"Bearer {token}"})
    post = json.loads(urllib.request.urlopen(req).read())
    content = post.get("content", "")
    clean = re.sub(r'<figure[^>]*>.*?</figure>', '', content, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'<img[^>]*/?>',  '', clean, flags=re.IGNORECASE)
    body = json.dumps({"content": clean}).encode()
    req = urllib.request.Request(get_url, data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
    }, method="PATCH")
    json.loads(urllib.request.urlopen(req).read())
    print(f"이미지 초기화: {len(clean)}자")

def wait_for_picker_frame(page, timeout=10):
    """Google Picker iframe 대기"""
    start = time.time()
    while time.time() - start < timeout:
        for f in page.frames:
            if "docs.google.com/picker" in f.url:
                return f
        time.sleep(0.5)
    return None

def insert_images():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = browser.contexts[0]
        page = ctx.new_page()

        print(f"에디터 열기: {edit_url}")
        page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)

        # 혹시 열린 것 닫기
        page.keyboard.press("Escape")
        time.sleep(1)

        # H2 요소
        editor_frame = None
        for frame in page.frames:
            if "post/edit" in frame.url:
                try:
                    if frame.locator("h2").count() > 0:
                        editor_frame = frame
                        break
                except:
                    pass
        h2_els = editor_frame.locator("h2").all() if editor_frame else []
        print(f"H2 요소: {len(h2_els)}개")

        img_btn = page.locator("div[role='button'][aria-label='이미지 삽입']").first

        for img_idx, img_path in enumerate(IMAGES):
            if not Path(img_path).exists():
                print(f"파일 없음: {img_path}")
                continue

            print(f"\n--- 이미지 {img_idx+1}/{len(IMAGES)}: {Path(img_path).name} ---")

            # H2 뒤에 커서 배치
            if editor_frame and img_idx < len(h2_els):
                try:
                    h2_els[img_idx].click()
                    page.keyboard.press("End")
                    page.keyboard.press("Enter")
                    time.sleep(0.3)
                except Exception as e:
                    print(f"  커서 배치 오류: {e}")

            # 이미지 버튼 클릭 (드롭다운 오픈)
            img_btn.click(force=True)
            time.sleep(1.5)

            # 드롭다운 확인 스크린샷
            page.screenshot(path=f"/tmp/drop_{img_idx}.png")

            # '컴퓨터에서 업로드' 고정 좌표 클릭
            print(f"  '컴퓨터에서 업로드' 클릭: ({UPLOAD_X}, {UPLOAD_Y})")
            page.mouse.click(UPLOAD_X, UPLOAD_Y)
            time.sleep(2)

            # Google Picker iframe 대기
            picker = wait_for_picker_frame(page, timeout=8)
            if picker:
                print(f"  Google Picker 발견!")
                page.screenshot(path=f"/tmp/picker_{img_idx}.png")

                # Picker 내부 탐색
                try:
                    picker.wait_for_load_state("domcontentloaded", timeout=5000)
                except:
                    pass
                time.sleep(1)

                # Picker의 file input 찾기
                file_inputs = picker.locator('input[type="file"]').all()
                print(f"  Picker file input: {len(file_inputs)}개")

                if file_inputs:
                    try:
                        file_inputs[0].set_input_files(img_path)
                        print(f"  ✅ set_input_files 성공!")
                        time.sleep(4)
                    except Exception as e:
                        print(f"  set_input_files 오류: {e}")
                        # file chooser 방식 시도
                        try:
                            with page.expect_file_chooser(timeout=10000) as fc_info:
                                file_inputs[0].click(force=True)
                            fc_info.value.set_files(img_path)
                            print(f"  ✅ file chooser 성공!")
                            time.sleep(4)
                        except Exception as e2:
                            print(f"  file chooser 오류: {e2}")
                            page.keyboard.press("Escape")
                            continue
                else:
                    # Picker 내 버튼 텍스트 확인
                    btns = picker.locator("button, [role='button']").all()
                    print(f"  Picker 버튼: {len(btns)}개")
                    for b in btns[:10]:
                        try:
                            print(f"    '{b.inner_text()[:30]}' visible={b.is_visible()}")
                        except:
                            pass

                    # '업로드' 또는 '컴퓨터에서' 버튼
                    for sel in [':has-text("업로드")', ':has-text("컴퓨터")', ':has-text("Upload")']:
                        try:
                            el = picker.locator(sel).first
                            if el.is_visible(timeout=2000):
                                print(f"  업로드 버튼 찾음: {sel}")
                                with page.expect_file_chooser(timeout=10000) as fc_info:
                                    el.click()
                                fc_info.value.set_files(img_path)
                                print(f"  ✅ 업로드 성공!")
                                time.sleep(4)
                                break
                        except Exception as e:
                            print(f"  {sel} 오류: {e}")

                # 선택 확인 버튼
                for ok_sel in ['button:has-text("선택")', 'button:has-text("삽입")', 'button:has-text("확인")']:
                    for ctx_frame in [page, picker]:
                        try:
                            btn = ctx_frame.locator(ok_sel).first
                            if btn.is_visible(timeout=2000):
                                btn.click()
                                print(f"  확인 클릭: {ok_sel}")
                                time.sleep(2)
                                break
                        except:
                            pass

            else:
                print("  Google Picker 없음 - 스크린샷 확인")
                page.screenshot(path=f"/tmp/no_picker_{img_idx}.png")
                page.keyboard.press("Escape")

            time.sleep(1)

        # 최종 저장
        page.screenshot(path="/tmp/final.png")
        try:
            update_btn = page.locator("div[role='button'][aria-label='업데이트']").first
            if update_btn.get_attribute("aria-disabled") != "true":
                update_btn.click(force=True)
                print("\n업데이트 저장 중...")
                time.sleep(5)
                print("저장 완료!")
            else:
                print("\n변경사항 없음")
        except Exception as e:
            print(f"저장 오류: {e}")

        page.close()

if __name__ == "__main__":
    print("=== Step 1: 기존 이미지 제거 ===")
    clear_images()
    print("\n=== Step 2: 이미지 삽입 ===")
    insert_images()
    print("\n완료!")
