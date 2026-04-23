"""
goodisak 발행 옵션 패널에서 댓글 비허용 설정 후 최종 발행 클릭
"""
import sys, time, datetime, subprocess
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp

print("=== goodisak 발행 옵션 처리 ===")

pw, browser = connect_cdp()
ctx = browser.contexts[0]

page = None
for p in ctx.pages:
    if 'goodisak.tistory.com/manage/newpost' in p.url:
        page = p
        break

if page is None:
    print("[오류] newpost 탭 없음")
    pw.stop()
    sys.exit(1)

page.bring_to_front()
page.wait_for_timeout(1000)

# 현재 화면 스크린샷
page.screenshot(path='/tmp/goodisak_panel_current.png')
print("[스크린샷] /tmp/goodisak_panel_current.png")

# "댓글 허용" 드롭다운 찾기 및 클릭
print("\n[댓글 허용 드롭다운 찾기...]")
try:
    # 드롭다운 버튼 (스크린샷에서 "댓글 허용 v" 형태)
    comment_dropdown = page.query_selector('button:has-text("댓글 허용")')
    if comment_dropdown:
        comment_dropdown.click()
        page.wait_for_timeout(1000)
        print("[댓글 허용 드롭다운 클릭됨]")
        page.screenshot(path='/tmp/goodisak_comment_dropdown.png')
        print("[스크린샷] /tmp/goodisak_comment_dropdown.png")

        # 드롭다운 옵션에서 "댓글 허용 안함" 선택
        for sel in ['text=허용 안함', 'text=댓글 허용 안함', 'text=비허용', 'li:has-text("허용 안함")', '[data-value="0"]']:
            try:
                el = page.query_selector(sel)
                if el:
                    el.click()
                    page.wait_for_timeout(500)
                    print(f"[댓글 비허용 선택] {sel}")
                    break
            except:
                pass
        else:
            # locator로 시도
            off_loc = page.locator(':has-text("허용 안함")')
            cnt = off_loc.count()
            print(f"'허용 안함' 요소 수: {cnt}")
            if cnt > 0:
                off_loc.last.click()
                page.wait_for_timeout(500)
                print("[댓글 허용 안함 클릭됨]")
    else:
        # 다른 방법으로 댓글 드롭다운 찾기
        print("[댓글 허용 버튼 직접 탐색...]")
        all_btns = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button, .btn, [role="button"]')).map(b => ({
                text: b.innerText.trim(),
                class: b.className,
                visible: b.offsetParent !== null
            })).filter(b => b.visible && b.text.length > 0);
        }""")
        print(f"[가시 버튼들] {all_btns}")

        # '댓글' 포함 요소 모두 찾기
        comment_els = page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('*').forEach(el => {
                if (el.children.length === 0 && el.innerText && el.innerText.includes('댓글')) {
                    results.push({tag: el.tagName, text: el.innerText.trim(), class: el.className});
                }
            });
            return results.slice(0, 10);
        }""")
        print(f"[댓글 포함 요소] {comment_els}")

        # locator로 "댓글 허용" 클릭
        comment_loc = page.locator(':has-text("댓글 허용")').last
        if comment_loc.count() > 0:
            comment_loc.click()
            page.wait_for_timeout(1000)
            print("[댓글 허용 locator 클릭됨]")
            page.screenshot(path='/tmp/goodisak_comment_dropdown2.png')

            off_loc = page.locator(':has-text("허용 안함")').last
            if off_loc.count() > 0:
                off_loc.click()
                page.wait_for_timeout(500)
                print("[허용 안함 선택됨]")
except Exception as e:
    print(f"[댓글 처리 오류] {e}")

# 현재 상태 스크린샷
page.screenshot(path='/tmp/goodisak_before_publish_btn.png')
print("[스크린샷] /tmp/goodisak_before_publish_btn.png")

# 최종 발행 버튼 ("저장중" 또는 실제 발행 버튼) 클릭
print("\n[최종 발행 버튼 클릭...]")
try:
    # 패널 하단의 발행 확인 버튼
    # 스크린샷에서 "저장중"(회색)과 "취소"가 보임 - 실제 발행 후 확인 버튼 필요
    # 패널 열린 상태에서 발행 버튼 탐색
    all_visible_btns = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent !== null).map(b => ({
            text: b.innerText.trim(),
            class: b.className,
            id: b.id
        }));
    }""")
    print(f"[현재 가시 버튼들] {all_visible_btns}")

    # 발행 버튼 클릭 (공개 발행, 발행하기 등)
    clicked = False
    for btn_text in ['공개 발행', '발행하기', '발행', '저장']:
        try:
            btns = page.locator(f'button:has-text("{btn_text}")')
            cnt = btns.count()
            if cnt > 0:
                # 각 버튼 확인
                for i in range(cnt):
                    btn = btns.nth(i)
                    if btn.is_visible():
                        btn_cls = btn.get_attribute('class') or ''
                        print(f"  [{i}] '{btn_text}' 버튼: class={btn_cls}")
                        if '저장중' not in btn_cls and 'disabled' not in btn_cls:
                            btn.click()
                            page.wait_for_timeout(3000)
                            clicked = True
                            print(f"[발행 클릭] '{btn_text}'")
                            break
                if clicked:
                    break
        except Exception as e2:
            print(f"  [{btn_text}] 오류: {e2}")

    if not clicked:
        print("[발행 버튼 없음 - 직접 클릭 시도]")
        # 위치 기반 클릭 (우측 하단 발행 버튼)
        viewport = page.viewport_size
        print(f"뷰포트: {viewport}")
        # 이전 스크린샷 기준 "저장중" 버튼 위치 (약 743, 784)
        page.mouse.click(743, 784)
        page.wait_for_timeout(3000)
        print("[좌표 클릭] (743, 784)")
        clicked = True

    if clicked:
        current_url = page.url
        print(f"\n[현재 URL] {current_url}")
        page.screenshot(path='/tmp/goodisak_published_check.png')
        print("[스크린샷] /tmp/goodisak_published_check.png")

        # 발행 성공 여부 확인
        page_text = page.evaluate("() => document.body.innerText.substring(0, 200)")
        print(f"[페이지 내용] {page_text[:200]}")

except Exception as e:
    print(f"[발행 오류] {e}")

pw.stop()
print("\n=== 완료 ===")
