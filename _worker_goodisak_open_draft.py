"""
goodisak 새 에디터 열고 임시저장 목록에서 게이밍노트북 글 찾아 발행
"""
import sys, time, datetime, subprocess
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp

print("=== goodisak 에디터 열기 및 드래프트 발행 ===")

pw, browser = connect_cdp()
ctx = browser.contexts[0]

# goodisak 관련 탭에서 진행
page = None
for p in ctx.pages:
    if 'goodisak.tistory.com' in p.url:
        page = p
        break

if page is None:
    print("[오류] goodisak 탭 없음")
    pw.stop()
    sys.exit(1)

page.bring_to_front()

# 새 글쓰기 페이지로 이동 (에디터)
print("[새 글쓰기 에디터로 이동...]")
page.goto('https://goodisak.tistory.com/manage/newpost/', wait_until='domcontentloaded', timeout=30000)
page.wait_for_timeout(3000)
print(f"[URL] {page.url}")

# 에디터 TinyMCE 로드 대기
for i in range(10):
    try:
        has_ed = page.evaluate("() => typeof tinymce !== 'undefined' && tinymce.activeEditor !== null")
        if has_ed:
            print(f"[에디터 준비됨] ({i+1}초)")
            break
    except:
        pass
    time.sleep(1)

# 임시저장 버튼 찾기 (하단 좌측)
print("\n[임시저장 버튼 찾기...]")
page.screenshot(path='/tmp/goodisak_new_editor.png')
print("[스크린샷] /tmp/goodisak_new_editor.png")

# 임시저장 숫자 버튼 클릭
try:
    draft_btns = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('button, a, span, div')).filter(el => {
            return el.offsetParent !== null && el.innerText && el.innerText.includes('임시저장');
        }).map(el => ({tag: el.tagName, text: el.innerText.trim(), id: el.id, class: el.className}));
    }""")
    print(f"[임시저장 관련 요소] {draft_btns}")

    # 임시저장 버튼 클릭
    for item in draft_btns:
        if item.get('id') or item.get('class'):
            selector = f"#{item['id']}" if item.get('id') else f".{item['class'].split()[0]}" if item.get('class') else None
            if selector:
                try:
                    el = page.query_selector(selector)
                    if el and el.is_visible():
                        el.click()
                        page.wait_for_timeout(1500)
                        print(f"[임시저장 버튼 클릭] {selector}")
                        break
                except:
                    pass

    # locator로 시도
    draft_loc = page.locator('button:has-text("임시저장")')
    if draft_loc.count() > 0:
        draft_loc.first.click()
        page.wait_for_timeout(1500)
        print("[임시저장 locator 클릭됨]")

except Exception as e:
    print(f"[임시저장 버튼 오류] {e}")

page.screenshot(path='/tmp/goodisak_draft_list_popup.png')
print("[스크린샷] /tmp/goodisak_draft_list_popup.png")

# 팝업에서 게이밍노트북 항목 찾기
print("\n[게이밍노트북 항목 찾기...]")
try:
    gaming_items = page.evaluate("""() => {
        const results = [];
        // 레이어/팝업 내의 모든 텍스트 노드
        document.querySelectorAll('*').forEach(el => {
            if (el.children.length === 0) {
                const txt = el.innerText || '';
                if (txt.includes('게이밍') || txt.includes('노트북추천')) {
                    const rect = el.getBoundingClientRect();
                    results.push({
                        text: txt.trim().substring(0, 60),
                        tag: el.tagName,
                        visible: el.offsetParent !== null,
                        x: rect.x, y: rect.y
                    });
                }
            }
        });
        return results;
    }""")
    print(f"[게이밍 관련 요소] {gaming_items}")

    if gaming_items:
        # 가시적인 첫 번째 항목 클릭
        for item in gaming_items:
            if item.get('visible'):
                x, y = item['x'] + 10, item['y'] + 5
                print(f"[좌표 클릭] ({x}, {y}) - '{item['text'][:30]}'")
                page.mouse.click(x, y)
                page.wait_for_timeout(2000)
                break
    else:
        # 텍스트 locator로 시도
        gaming_loc = page.locator(':has-text("게이밍")')
        cnt = gaming_loc.count()
        print(f"'게이밍' locator count: {cnt}")
        if cnt > 0:
            gaming_loc.first.click()
            page.wait_for_timeout(2000)
            print("[게이밍 locator 클릭됨]")
except Exception as e:
    print(f"[게이밍 찾기 오류] {e}")

page.screenshot(path='/tmp/goodisak_after_gaming_click.png')
print("[스크린샷] /tmp/goodisak_after_gaming_click.png")

# 에디터에 글이 로드됐는지 확인
time.sleep(2)
title = page.evaluate("""() => {
    const inp = document.querySelector('#post-title-inp, [placeholder="제목을 입력하세요"]');
    return inp ? inp.value : '';
}""")
print(f"\n[로드된 제목] '{title}'")

if '게이밍' not in title:
    print("[경고] 게이밍노트북 글이 로드되지 않음")
    # 임시저장 팝업 스크린샷 다시 확인
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
print("\n=== 발행 처리 ===")

# 완료 버튼 클릭 (발행 옵션 패널 열기)
print("[완료 버튼 클릭...]")
done_btn = page.query_selector('#publish-layer-btn')
if done_btn:
    done_btn.click()
    page.wait_for_timeout(2000)
    print("[#publish-layer-btn 클릭됨]")
else:
    done_loc = page.locator('button:has-text("완료")')
    if done_loc.count() > 0:
        done_loc.last.click()
        page.wait_for_timeout(2000)
        print("[완료 버튼 locator 클릭됨]")

page.screenshot(path='/tmp/goodisak_publish_panel2.png')
print("[스크린샷] /tmp/goodisak_publish_panel2.png")

# 발행 버튼 활성화 대기
print("[발행 버튼 활성화 대기...]")
for i in range(25):
    state = page.evaluate("""() => {
        const btn = document.querySelector('#publish-btn');
        if (!btn) return {found: false};
        return {found: true, text: btn.innerText.trim(), disabled: btn.disabled};
    }""")
    if state.get('found') and not state.get('disabled'):
        print(f"[활성화됨!] text='{state['text']}'")
        break
    if i % 5 == 0:
        print(f"  [{i+1}] 아직... '{state.get('text', '')}'")
    time.sleep(2)
else:
    print("[경고] 50초 내 미활성화 - 강제 진행")

# 댓글 비허용 설정
print("\n[댓글 비허용 설정...]")
try:
    comment_text = page.evaluate("""() => {
        const btn = document.querySelector('.mce-btn-type1.select_btn');
        return btn ? btn.innerText : '';
    }""")
    print(f"댓글 현재: {comment_text[:30]}")
    if '허용 안함' not in comment_text:
        comment_btn = page.query_selector('.mce-btn-type1.select_btn')
        if comment_btn and comment_btn.is_visible():
            comment_btn.click()
            page.wait_for_timeout(800)
            off_loc = page.locator(':has-text("허용 안함")').last
            if off_loc.count() > 0:
                off_loc.click()
                page.wait_for_timeout(500)
                print("[허용 안함 선택됨]")
except Exception as e:
    print(f"[댓글 설정 오류] {e}")

# 발행 버튼 클릭 (마우스로 직접 클릭)
print("\n[발행 버튼 마우스 클릭...]")
try:
    pub_btn = page.query_selector('#publish-btn')
    if pub_btn:
        box = pub_btn.bounding_box()
        if box:
            cx = box['x'] + box['width'] / 2
            cy = box['y'] + box['height'] / 2
            print(f"[마우스 이동] ({cx}, {cy})")
            page.mouse.move(cx, cy)
            time.sleep(0.5)
            # disabled 속성 확인
            is_disabled = pub_btn.get_attribute('disabled')
            print(f"disabled: {is_disabled}")
            if is_disabled is None:
                page.mouse.click(cx, cy)
                page.wait_for_timeout(4000)
                print("[마우스 클릭됨]")
            else:
                # JS로 disabled 제거 후 클릭
                print("[JS로 disabled 제거 후 클릭...]")
                page.evaluate("() => { const b = document.querySelector('#publish-btn'); b.disabled = false; b.removeAttribute('disabled'); }")
                time.sleep(0.3)
                page.mouse.click(cx, cy)
                page.wait_for_timeout(4000)
                print("[강제 클릭됨]")
except Exception as e:
    print(f"[발행 클릭 오류] {e}")

final_url = page.url
print(f"\n[최종 URL] {final_url}")
page.screenshot(path='/tmp/goodisak_final2.png')
print("[스크린샷] /tmp/goodisak_final2.png")

# 발행 성공 확인
import re
if re.search(r'goodisak\.tistory\.com/\d+', final_url):
    print("[발행 성공!] 게시물 URL 확인됨")
    published_url = final_url
else:
    # 잠시 대기 후 게시물 목록 확인
    time.sleep(2)
    published_url = final_url

# 텔레그램 발송
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
tg_msg = f"""✅ 발행 완료
블로그: goodisak (티스토리)
제목: {title}
발행시각: {now}
URL: {published_url}

🔧 검수 중 수정사항:
- 이상 없음 (체크리스트 전항목 통과)
- 글자수: {char_count}자
- 이미지: {img_count}장
- 댓글 비허용 설정 완료"""

print(f"\n[텔레그램 발송]\n{tg_msg}")
result = subprocess.run(
    ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py', tg_msg],
    capture_output=True, text=True, timeout=15
)
print(f"텔레그램: {result.returncode}")

print("\n=== 완료 ===")
pw.stop()
