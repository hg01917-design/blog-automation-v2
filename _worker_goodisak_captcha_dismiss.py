"""
캡챠 팝업 닫고 발행 패널 재시도
"""
import sys, time, datetime, subprocess
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp

print("=== 캡챠 처리 및 발행 재시도 ===")

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
page.screenshot(path='/tmp/goodisak_captcha_state.png')
print("[스크린샷] /tmp/goodisak_captcha_state.png")

# 캡챠 닫기
print("\n[캡챠 닫기 시도...]")
try:
    # 닫기 버튼 (X)
    close_btns = page.query_selector_all('button.close, [aria-label="close"], .dkapcha-close, button:has-text("닫기")')
    for btn in close_btns:
        if btn.is_visible():
            btn.click()
            page.wait_for_timeout(500)
            print("[닫기 버튼 클릭됨]")
            break
    else:
        # ESC 키로 닫기
        page.keyboard.press('Escape')
        page.wait_for_timeout(500)
        print("[ESC 키로 닫기 시도]")

        # X 버튼 좌표 클릭 (스크린샷에서 약 480, 188)
        page.mouse.click(480, 188)
        page.wait_for_timeout(500)
        print("[X 버튼 좌표 클릭]")
except Exception as e:
    print(f"[캡챠 닫기 오류] {e}")

page.screenshot(path='/tmp/goodisak_after_captcha_close.png')
print("[스크린샷] /tmp/goodisak_after_captcha_close.png")

# 발행 패널 상태 확인
print("\n[발행 패널 상태 확인...]")
time.sleep(2)
publish_btn_state = page.evaluate("""() => {
    const btn = document.querySelector('#publish-btn');
    if (!btn) return 'not found';
    return {text: btn.innerText, disabled: btn.disabled, class: btn.className};
}""")
print(f"publish-btn: {publish_btn_state}")

# "저장중"이면 일반 자동저장 완료 대기
print("\n[발행 버튼 활성화 대기 (최대 60초)...]")
for i in range(30):
    state = page.evaluate("""() => {
        const btn = document.querySelector('#publish-btn');
        if (!btn) return {found: false, disabled: true, text: ''};
        return {found: true, text: btn.innerText.trim(), disabled: btn.disabled};
    }""")
    if state.get('found') and not state.get('disabled'):
        print(f"[{i+1}] 발행 버튼 활성화됨! text='{state.get('text')}'")
        break
    if i % 5 == 0:
        print(f"  [{i+1}] 아직 저장중... text='{state.get('text', '')}', disabled={state.get('disabled')}")
    time.sleep(2)
else:
    print("[경고] 60초 내 활성화 안 됨")
    # 패널을 닫고 다시 열기
    print("[패널 닫기 후 재시도...]")
    try:
        cancel_btn = page.query_selector('#unpublish-btn, button.btn-cancel')
        if cancel_btn and cancel_btn.is_visible():
            cancel_btn.click()
            page.wait_for_timeout(1000)
            print("[취소 버튼 클릭됨]")
    except:
        pass

    # 완료 버튼 다시 클릭
    time.sleep(3)
    print("[완료 버튼 다시 클릭...]")
    done_loc = page.locator('#publish-layer-btn')
    if done_loc.count() > 0:
        done_loc.first.click()
        page.wait_for_timeout(2000)
        print("[완료(publish-layer-btn) 클릭됨]")

    # 다시 대기
    for i in range(15):
        state = page.evaluate("""() => {
            const btn = document.querySelector('#publish-btn');
            if (!btn) return {found: false, disabled: True, text: ''};
            return {found: True, text: btn.innerText.trim(), disabled: btn.disabled};
        }""")
        if state.get('found') and not state.get('disabled'):
            print(f"[{i+1}] 발행 버튼 활성화됨! text='{state.get('text')}'")
            break
        time.sleep(2)

page.screenshot(path='/tmp/goodisak_publish_ready.png')
print("[스크린샷] /tmp/goodisak_publish_ready.png")

# 댓글 비허용 재확인 및 설정
print("\n[댓글 비허용 확인...]")
comment_text = page.evaluate("""() => {
    const btns = document.querySelectorAll('.mce-btn-type1.select_btn');
    return Array.from(btns).map(b => b.innerText.trim());
}""")
print(f"select_btn 현재: {comment_text}")

# 댓글 "허용 안함" 설정
for txt in (comment_text or []):
    if '댓글 허용' in txt:
        print("[댓글 비허용 재설정 필요]")
        comment_btn = page.locator('.mce-btn-type1.select_btn:has-text("댓글 허용")').first
        if comment_btn.count() > 0:
            comment_btn.click()
            page.wait_for_timeout(800)
            # "허용 안함" 옵션 클릭
            off_option = page.locator('text=허용 안함').last
            if off_option.count() > 0:
                off_option.click()
                page.wait_for_timeout(500)
                print("[댓글 허용 안함 선택됨]")
        break

# 최종 발행 버튼 클릭
print("\n[최종 발행 클릭...]")
try:
    pub_btn = page.query_selector('#publish-btn')
    if pub_btn:
        if not pub_btn.get_attribute('disabled'):
            pub_btn.click()
            page.wait_for_timeout(4000)
            print("[#publish-btn 클릭됨]")
        else:
            print(f"[여전히 disabled] 강제 클릭")
            # 마우스 실제 위치로 클릭 (스크린샷 위치 기준)
            box = pub_btn.bounding_box()
            if box:
                cx = box['x'] + box['width'] / 2
                cy = box['y'] + box['height'] / 2
                print(f"[마우스 클릭] ({cx}, {cy})")
                page.mouse.move(cx, cy)
                time.sleep(0.3)
                page.mouse.click(cx, cy)
                page.wait_for_timeout(4000)
            else:
                print("[박스 정보 없음]")
except Exception as e:
    print(f"[발행 클릭 오류] {e}")

final_url = page.url
print(f"\n[최종 URL] {final_url}")
page.screenshot(path='/tmp/goodisak_very_final.png')
print("[스크린샷] /tmp/goodisak_very_final.png")

pw.stop()
print("\n=== 완료 ===")
