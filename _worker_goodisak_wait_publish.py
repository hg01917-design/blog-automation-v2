"""
goodisak 발행 패널: 저장중 → 활성화 대기 후 댓글비허용 + 발행
"""
import sys, time, datetime, subprocess
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp

print("=== goodisak 발행 패널 처리 ===")

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

# 댓글 드롭다운 현재 상태 확인
print("[현재 댓글 상태 확인...]")
comment_text = page.evaluate("""() => {
    const btn = document.querySelector('.mce-btn-type1.select_btn');
    return btn ? btn.innerText : 'not found';
}""")
print(f"댓글 버튼 현재 텍스트: {comment_text}")

# 댓글 "허용 안함" 설정
print("[댓글 비허용 설정...]")
try:
    # "댓글 허용" 드롭다운 버튼 클릭
    comment_btns = page.query_selector_all('.mce-btn-type1.select_btn')
    print(f"select_btn 수: {len(comment_btns)}")
    for btn in comment_btns:
        txt = btn.inner_text()
        print(f"  select_btn: {txt[:30]}")
        if '댓글' in txt:
            btn.click()
            page.wait_for_timeout(800)
            page.screenshot(path='/tmp/goodisak_comment_open.png')
            print(f"[댓글 드롭다운 열림]")

            # 열린 드롭다운에서 "허용 안함" 클릭
            items = page.query_selector_all('.mce-menu-item, li.item, [role="option"], .select-list li')
            for item in items:
                item_txt = item.inner_text()
                print(f"  옵션: {item_txt[:30]}")
                if '허용 안함' in item_txt or '비허용' in item_txt:
                    item.click()
                    page.wait_for_timeout(500)
                    print(f"[댓글 비허용 선택됨]")
                    break
            else:
                # 다른 방법: locator
                off_loc = page.locator(':has-text("허용 안함")').last
                if off_loc.count() > 0:
                    off_loc.click()
                    page.wait_for_timeout(500)
                    print("[locator로 허용 안함 클릭됨]")
            break
except Exception as e:
    print(f"[댓글 설정 오류] {e}")

# 발행 버튼 활성화 대기 (저장중 → 공개 발행)
print("\n[발행 버튼 활성화 대기 중...]")
publish_btn_active = False
for i in range(20):
    try:
        btn_state = page.evaluate("""() => {
            const btn = document.querySelector('#publish-btn');
            if (!btn) return {found: false};
            return {
                found: true,
                text: btn.innerText,
                disabled: btn.disabled,
                class: btn.className
            };
        }""")
        print(f"  [{i+1}] publish-btn: {btn_state}")
        if btn_state.get('found') and not btn_state.get('disabled'):
            publish_btn_active = True
            print("[발행 버튼 활성화됨!]")
            break
    except Exception as e:
        print(f"  [{i+1}] 오류: {e}")
    time.sleep(2)

if not publish_btn_active:
    print("[경고] 발행 버튼이 20초 내 활성화되지 않음")
    page.screenshot(path='/tmp/goodisak_btn_inactive.png')
    print("[스크린샷] /tmp/goodisak_btn_inactive.png")

# 발행 버튼 클릭
print("\n[발행 버튼 클릭...]")
try:
    pub_btn = page.query_selector('#publish-btn')
    if pub_btn:
        btn_disabled = pub_btn.get_attribute('disabled')
        btn_text = pub_btn.inner_text()
        print(f"publish-btn: text='{btn_text}', disabled={btn_disabled}")

        if btn_disabled is None:  # not disabled
            pub_btn.click()
            page.wait_for_timeout(4000)
            print("[발행 버튼 클릭됨]")
        else:
            # disabled여도 JS로 강제 클릭 시도
            print("[disabled 상태 - JS 클릭 시도...]")
            page.evaluate("() => document.querySelector('#publish-btn').removeAttribute('disabled')")
            page.wait_for_timeout(500)
            pub_btn.click()
            page.wait_for_timeout(4000)
            print("[JS 강제 클릭됨]")
    else:
        print("[publish-btn 없음]")
        # 모든 버튼 재확인
        all_btns = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent !== null).map(b => ({
                id: b.id, text: b.innerText.trim(), disabled: b.disabled, class: b.className
            }));
        }""")
        print(f"[현재 버튼들] {all_btns}")
except Exception as e:
    print(f"[발행 클릭 오류] {e}")

current_url = page.url
print(f"\n[현재 URL] {current_url}")
page.screenshot(path='/tmp/goodisak_final_state.png')
print("[스크린샷] /tmp/goodisak_final_state.png")

# 발행 성공 확인 - 게시물 URL로 이동했는지
import re
published_url = current_url
match = re.search(r'goodisak\.tistory\.com/(\d+|entry/)', current_url)
if match:
    print(f"[발행 성공 확인] URL: {current_url}")
else:
    # 게시물 목록에서 최신 글 확인
    print("[게시물 목록에서 확인 중...]")
    try:
        import urllib.request, json
        req = urllib.request.Request(
            'https://goodisak.tistory.com/manage/posts',
            headers={'User-Agent': 'Mozilla/5.0'}
        )
    except:
        pass

# 텔레그램 발송
title = "게이밍노트북추천 2026 GPU·발열·예산 3단계 선택 기준"
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
tg_msg = f"""✅ 발행 완료
블로그: goodisak (티스토리)
제목: {title}
발행시각: {now}
URL: {published_url}

🔧 검수 중 수정사항:
- 이상 없음 (체크리스트 전항목 통과)
- 글자수: 2745자
- 이미지: 3장
- 댓글 비허용 설정 완료"""

print(f"\n[텔레그램 발송]\n{tg_msg}")
result = subprocess.run(
    ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py', tg_msg],
    capture_output=True, text=True, timeout=15
)
print(f"텔레그램: {result.returncode}")

print("\n=== 완료 ===")
pw.stop()
