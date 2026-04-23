"""
goodisak 게이밍노트북 드래프트 정확한 발행
- 임시저장 숫자 버튼(팝업 트리거) 클릭
- 댓글 비허용 후 발행
"""
import sys, time, datetime, subprocess
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp

print("=== goodisak 드래프트 발행 (정확한 방법) ===")

pw, browser = connect_cdp()
ctx = browser.contexts[0]

# 새 페이지 생성하여 goodisak 에디터로 이동
print("[goodisak 에디터 새 탭 열기...]")
page = ctx.new_page()
page.goto('https://goodisak.tistory.com/manage/newpost/', wait_until='domcontentloaded', timeout=30000)
page.wait_for_timeout(4000)
print(f"[URL] {page.url}")

# 에디터 TinyMCE 로드 대기
print("[에디터 로드 대기...]")
for i in range(15):
    try:
        has_ed = page.evaluate("() => typeof tinymce !== 'undefined' && tinymce.activeEditor !== null")
        if has_ed:
            print(f"[에디터 준비됨] ({i+1}초)")
            break
    except:
        pass
    time.sleep(1)

page.screenshot(path='/tmp/gk_step1.png')
print("[스크린샷] /tmp/gk_step1.png")

# 임시저장 팝업 트리거 - 숫자 부분 클릭
print("\n[임시저장 팝업 열기...]")
try:
    # btn-draft 내의 숫자(임시저장 개수) 클릭
    # HTML: <span class="btn btn-draft"><a class="action">임시저장</a><span class="count">4</span></span>
    # "임시저장" a 태그는 페이지 이동 (현재 글 임시저장)
    # 숫자 span 클릭 시 팝업이 열림
    count_span = page.query_selector('.btn-draft .count, .btn-draft span:not(.action)')
    if count_span:
        print(f"[카운트 span 발견] {count_span.inner_text()}")
        count_span.click()
        page.wait_for_timeout(1500)
        print("[카운트 클릭됨]")
    else:
        # btn-draft 구조 탐색
        draft_html = page.evaluate("""() => {
            const btn = document.querySelector('.btn-draft, .btn.btn-draft');
            return btn ? btn.outerHTML : 'not found';
        }""")
        print(f"[btn-draft HTML] {draft_html[:200]}")

        # count 부분 찾기 (숫자)
        draft_btn = page.query_selector('.btn-draft')
        if draft_btn:
            # 내부 HTML 확인
            inner = draft_btn.inner_html()
            print(f"[내부 HTML] {inner[:200]}")
            # 두 번째 자식 (숫자 부분) 클릭
            children = page.evaluate("""() => {
                const btn = document.querySelector('.btn-draft');
                if (!btn) return [];
                return Array.from(btn.children).map(c => ({tag: c.tagName, text: c.innerText, class: c.className}));
            }""")
            print(f"[자식 요소] {children}")

            # 숫자가 있는 자식 클릭
            for child in children:
                if child['text'].strip().isdigit() or child['tag'] == 'EM':
                    # 두 번째 자식 클릭
                    second_child = page.evaluate("""() => {
                        const btn = document.querySelector('.btn-draft');
                        const children = Array.from(btn.children);
                        for (const c of children) {
                            if (c.innerText.trim().match(/^\\d+$/)) {
                                const rect = c.getBoundingClientRect();
                                return {x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                            }
                        }
                        return null;
                    }""")
                    if second_child:
                        page.mouse.click(second_child['x'], second_child['y'])
                        page.wait_for_timeout(1500)
                        print(f"[숫자 클릭] ({second_child['x']}, {second_child['y']})")
                    break
except Exception as e:
    print(f"[임시저장 팝업 오류] {e}")

page.screenshot(path='/tmp/gk_step2.png')
print("[스크린샷] /tmp/gk_step2.png")

# 팝업 확인 - 게이밍노트북 항목 찾기
print("\n[팝업에서 게이밍노트북 찾기...]")
try:
    popup_items = page.evaluate("""() => {
        // 레이어/팝업 내 아이템
        const selectors = [
            '.layer-draft li',
            '.draft-list li',
            '[class*="draft"] li',
            '.list-area li',
            '.post-list li',
        ];
        for (const sel of selectors) {
            const items = document.querySelectorAll(sel);
            if (items.length > 0) {
                return {selector: sel, items: Array.from(items).map(i => i.innerText.substring(0, 80))};
            }
        }
        // 팝업 내 텍스트 전체
        const layers = document.querySelectorAll('[class*="layer"], [class*="popup"], [class*="modal"]');
        for (const layer of layers) {
            if (layer.offsetParent !== null && layer.innerText) {
                return {selector: 'layer', text: layer.innerText.substring(0, 500)};
            }
        }
        return null;
    }""")
    print(f"[팝업 내용] {popup_items}")

    if popup_items and popup_items.get('items'):
        # 게이밍노트북 항목 클릭
        for i, item_txt in enumerate(popup_items['items']):
            if '게이밍' in item_txt or '노트북추천' in item_txt:
                print(f"[발견] 인덱스 {i}: {item_txt[:60]}")
                items = page.query_selector_all(popup_items['selector'])
                if i < len(items):
                    items[i].click()
                    page.wait_for_timeout(2000)
                    print("[항목 클릭됨]")
                break
    elif popup_items and popup_items.get('text'):
        if '게이밍' in popup_items['text']:
            # 좌표로 클릭
            gaming_loc = page.locator(':has-text("게이밍노트북")')
            cnt = gaming_loc.count()
            if cnt > 0:
                gaming_loc.first.click()
                page.wait_for_timeout(2000)
                print("[게이밍노트북 locator 클릭됨]")
except Exception as e:
    print(f"[팝업 항목 오류] {e}")

page.screenshot(path='/tmp/gk_step3.png')
print("[스크린샷] /tmp/gk_step3.png")

# 에디터에 글 로드 확인
time.sleep(2)
title = page.evaluate("""() => {
    const inp = document.querySelector('#post-title-inp, [placeholder="제목을 입력하세요"]');
    return inp ? inp.value : '';
}""")
print(f"[로드된 제목] '{title}'")

if '게이밍' not in title and '노트북' not in title:
    print("[경고] 게이밍노트북 글 로드 실패")
    # 현재 상태 출력
    all_txt = page.evaluate("() => document.body.innerText.substring(0, 500)")
    print(f"[페이지 텍스트] {all_txt[:300]}")
    pw.stop()
    sys.exit(1)

# 글자수/이미지 확인
char_count = page.evaluate("""() => {
    const ed = tinymce.get('editor-tistory') || tinymce.activeEditor;
    if (!ed) return -1;
    return ed.getBody().innerText.replace(/\\s+/g, '').length;
}""")
img_count = page.evaluate("""() => {
    const ed = tinymce.get('editor-tistory') || tinymce.activeEditor;
    if (!ed) return -1;
    return ed.getBody().querySelectorAll('img').length;
}""")
print(f"[글자수] {char_count}, [이미지] {img_count}")

# ===== 발행 처리 =====
print("\n=== 발행 패널 열기 ===")

# 완료 버튼(#publish-layer-btn) 클릭
print("[완료 버튼 클릭...]")
done_btn = page.query_selector('#publish-layer-btn')
if done_btn and done_btn.is_visible():
    done_btn.click()
    page.wait_for_timeout(2000)
    print("[#publish-layer-btn 클릭됨]")
else:
    # 위치 기반 클릭
    btn_pos = page.evaluate("""() => {
        const btn = document.querySelector('#publish-layer-btn');
        if (!btn) return null;
        const r = btn.getBoundingClientRect();
        return {x: r.x + r.width/2, y: r.y + r.height/2};
    }""")
    if btn_pos:
        page.mouse.click(btn_pos['x'], btn_pos['y'])
        page.wait_for_timeout(2000)
        print(f"[완료 좌표 클릭] {btn_pos}")

# 발행 버튼 활성화 대기
print("[발행 버튼 활성화 대기 (최대 60초)...]")
for i in range(30):
    state = page.evaluate("""() => {
        const btn = document.querySelector('#publish-btn');
        if (!btn) return {found: false, disabled: true, text: ''};
        return {found: true, text: btn.innerText.trim(), disabled: btn.disabled};
    }""")
    if state.get('found') and not state.get('disabled'):
        print(f"[활성화됨!] '{state['text']}'")
        break
    if i % 10 == 0:
        print(f"  [{i+1}] '{state.get('text', '')}' disabled={state.get('disabled')}")
    time.sleep(2)

page.screenshot(path='/tmp/gk_publish_panel.png')
print("[스크린샷] /tmp/gk_publish_panel.png")

# 댓글 비허용 설정
print("\n[댓글 비허용 설정...]")
try:
    comment_btns = page.query_selector_all('.mce-btn-type1.select_btn')
    for btn in comment_btns:
        txt = btn.inner_text()
        if '댓글 허용' in txt and '허용 안함' not in txt:
            btn.click()
            page.wait_for_timeout(800)
            off_option = page.locator(':has-text("허용 안함")').last
            if off_option.count() > 0:
                off_option.click()
                page.wait_for_timeout(500)
                print("[허용 안함 선택됨]")
            break
    else:
        print("[댓글 설정 확인] " + str([b.inner_text()[:20] for b in comment_btns]))
except Exception as e:
    print(f"[댓글 설정 오류] {e}")

# 발행 버튼 클릭
print("\n[발행 버튼 클릭...]")
try:
    pub_btn = page.query_selector('#publish-btn')
    if pub_btn:
        is_disabled = pub_btn.get_attribute('disabled')
        box = pub_btn.bounding_box()
        print(f"publish-btn: disabled={is_disabled}, box={box}")
        if box:
            cx = box['x'] + box['width'] / 2
            cy = box['y'] + box['height'] / 2
            page.mouse.move(cx, cy)
            time.sleep(0.5)
            page.mouse.click(cx, cy)
            page.wait_for_timeout(5000)
            print("[마우스 클릭됨]")
    else:
        print("[#publish-btn 없음]")
        # 가시 버튼 탐색
        visible = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent !== null).map(b => ({
                id: b.id, text: b.innerText.trim(), disabled: b.disabled
            })).filter(b => b.text.length > 0);
        }""")
        print(f"[가시 버튼] {visible}")
except Exception as e:
    print(f"[발행 클릭 오류] {e}")

final_url = page.url
print(f"\n[최종 URL] {final_url}")
page.screenshot(path='/tmp/gk_final.png')
print("[스크린샷] /tmp/gk_final.png")

pw.stop()
print("\n=== 완료 ===")
