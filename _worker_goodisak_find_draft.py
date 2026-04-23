"""
goodisak 임시저장 드래프트 목록에서 게이밍노트북 글 찾기 및 발행
"""
import sys, time, datetime, subprocess
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp

print("=== goodisak 드래프트 찾기 ===")

pw, browser = connect_cdp()
ctx = browser.contexts[0]

# 현재 탭 목록 확인
print("[현재 탭 목록]")
for i, p in enumerate(ctx.pages):
    print(f"  [{i}] {p.url}")

# goodisak 탭 찾기
page = None
for p in ctx.pages:
    if 'goodisak.tistory.com' in p.url:
        page = p
        break

if page is None:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

page.bring_to_front()
print(f"[사용 탭] {page.url}")

# 임시저장 버튼 클릭 (하단 좌측 "임시저장 4" 버튼)
print("\n[임시저장 목록 버튼 클릭...]")
try:
    # 임시저장 버튼 찾기
    draft_btn = page.query_selector('button:has-text("임시저장")')
    if draft_btn:
        draft_btn.click()
        page.wait_for_timeout(1500)
        page.screenshot(path='/tmp/goodisak_drafts.png')
        print("[스크린샷] /tmp/goodisak_drafts.png")
    else:
        print("[경고] 임시저장 버튼 찾기 실패")
        # 임시저장 숫자 버튼 시도
        btns = page.query_selector_all('button')
        for btn in btns:
            txt = btn.inner_text()
            if '임시저장' in txt:
                print(f"  발견: {txt}")
                btn.click()
                page.wait_for_timeout(1500)
                break
except Exception as e:
    print(f"[오류] {e}")

# 드래프트 목록 팝업/레이어에서 게이밍노트북 찾기
print("\n[드래프트 목록에서 게이밍노트북 찾기...]")
try:
    draft_items = page.evaluate("""() => {
        // 모달/레이어 안의 임시저장 글 목록
        const results = [];
        const items = document.querySelectorAll('.draft-list li, .saved-list li, [class*="draft"] li, [class*="temp"] li');
        items.forEach(item => {
            results.push({text: item.innerText, html: item.innerHTML.substring(0, 200)});
        });
        // 모든 목록 아이템 시도
        if (results.length === 0) {
            const allLi = document.querySelectorAll('li');
            allLi.forEach(li => {
                if (li.innerText && (li.innerText.includes('게이밍') || li.innerText.includes('노트북'))) {
                    results.push({text: li.innerText.substring(0, 100), tag: 'li'});
                }
            });
        }
        return results;
    }""")
    print(f"드래프트 항목: {draft_items}")
except Exception as e:
    print(f"[오류] {e}")

# 팝업 스크린샷 확인
page.screenshot(path='/tmp/goodisak_draft_popup.png')
print("[스크린샷] /tmp/goodisak_draft_popup.png")

# 게이밍노트북 항목 클릭 시도
print("\n[게이밍노트북 항목 클릭 시도...]")
try:
    gaming_loc = page.locator('text=게이밍')
    count = gaming_loc.count()
    print(f"'게이밍' 텍스트 요소 수: {count}")
    if count > 0:
        gaming_loc.first.click()
        page.wait_for_timeout(2000)
        print("[클릭됨]")
    else:
        # 노트북 텍스트
        notebook_loc = page.locator('text=노트북')
        count2 = notebook_loc.count()
        print(f"'노트북' 텍스트 요소 수: {count2}")
        if count2 > 0:
            notebook_loc.first.click()
            page.wait_for_timeout(2000)
            print("[노트북 클릭됨]")
except Exception as e:
    print(f"[클릭 오류] {e}")

page.screenshot(path='/tmp/goodisak_after_click.png')
print("[스크린샷] /tmp/goodisak_after_click.png")

# 에디터에 글이 로드되었는지 확인
print("\n[에디터 글 로드 확인...]")
try:
    for i in range(8):
        try:
            title = page.evaluate("""() => {
                const inp = document.querySelector('#post-title-inp, input[name="title"], .title-area input, [placeholder="제목을 입력하세요"]');
                return inp ? inp.value : '';
            }""")
            if title and len(title) > 0:
                print(f"[제목 로드됨] {title}")
                break
        except:
            pass
        time.sleep(1)
    else:
        print("[경고] 제목 미로드 - 상태 확인 필요")
        title = ''
except Exception as e:
    print(f"[제목 확인 오류] {e}")
    title = ''

# 글자수/이미지 확인
print("\n[콘텐츠 확인...]")
try:
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
    print(f"글자수: {char_count}, 이미지: {img_count}")
except Exception as e:
    print(f"[콘텐츠 확인 오류] {e}")
    char_count = -1
    img_count = -1

pw.stop()
print("\n=== 완료 ===")
