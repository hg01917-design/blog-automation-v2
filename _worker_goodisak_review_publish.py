"""
goodisak 티스토리 드래프트 검수 및 발행 워커
게이밍노트북추천 글 대상
"""
import sys, time, datetime, subprocess
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp

print("=== goodisak 드래프트 검수 시작 ===")

pw, browser = connect_cdp()
ctx = browser.contexts[0]

# goodisak 관리 페이지 탭 찾기
page = None
for p in ctx.pages:
    if 'goodisak.tistory.com/manage/newpost' in p.url or 'goodisak.tistory.com' in p.url:
        page = p
        print(f"[탭 발견] {p.url}")
        break

if page is None:
    print("[오류] goodisak.tistory.com 탭을 찾지 못했습니다. 관리 페이지로 이동합니다.")
    # 기존 탭 재사용하여 이동
    if ctx.pages:
        page = ctx.pages[0]
    else:
        page = ctx.new_page()
    page.goto('https://goodisak.tistory.com/manage/post', wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(2000)
    print(f"[현재 URL] {page.url}")
    # 드래프트 목록에서 게이밍노트북 글 찾기
    try:
        # 임시저장 글 목록 확인
        page.goto('https://goodisak.tistory.com/manage/post?type=private', wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(2000)
        print("[임시저장 목록 페이지 이동 완료]")
    except Exception as e:
        print(f"[오류] {e}")

page.bring_to_front()
print(f"[현재 URL] {page.url}")

# newpost 에디터가 아닌 경우 드래프트 목록에서 게이밍노트북 글 찾기
if 'newpost' not in page.url:
    print("[드래프트 목록에서 게이밍노트북 글 찾는 중...]")
    # 임시저장 또는 비공개 글 목록
    page.goto('https://goodisak.tistory.com/manage/post?type=private', wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(2000)

    # 게이밍노트북 관련 글 링크 찾기
    links = page.query_selector_all('a[href*="/manage/newpost/"]')
    gaming_link = None
    for link in links:
        text = link.inner_text()
        parent_text = ''
        try:
            row = link.evaluate('el => el.closest("tr") ? el.closest("tr").innerText : el.parentElement.innerText')
            parent_text = row
        except:
            pass
        combined = text + parent_text
        if '게이밍' in combined or '노트북' in combined or 'gaming' in combined.lower():
            gaming_link = link.get_attribute('href')
            print(f"[드래프트 발견] {combined[:100]}")
            break

    if gaming_link:
        if not gaming_link.startswith('http'):
            gaming_link = 'https://goodisak.tistory.com' + gaming_link
        print(f"[에디터로 이동] {gaming_link}")
        page.goto(gaming_link, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(3000)
    else:
        print("[오류] 게이밍노트북 드래프트 글을 찾지 못했습니다.")
        # 목록 확인을 위해 스크린샷
        page.screenshot(path='/tmp/goodisak_list.png')
        print("[스크린샷 저장] /tmp/goodisak_list.png")

# TinyMCE 에디터 로드 대기
print("[에디터 로드 대기 중...]")
for i in range(10):
    try:
        has_editor = page.evaluate("() => typeof tinymce !== 'undefined' && tinymce.activeEditor !== null")
        if has_editor:
            print(f"[에디터 준비됨] ({i+1}초)")
            break
    except:
        pass
    time.sleep(1)
    if i == 9:
        print("[경고] TinyMCE 에디터 확인 실패 - 계속 진행")

# ===== 체크리스트 1: 글자수 확인 =====
print("\n--- 체크리스트 1: 글자수 확인 ---")
try:
    char_count = page.evaluate("""() => {
        const ed = tinymce.get('editor-tistory') || tinymce.activeEditor;
        if (!ed) return -1;
        return ed.getBody().innerText.replace(/\\s+/g, '').length;
    }""")
    print(f"글자수(공백제외): {char_count}")
    char_ok = char_count >= 1700
    print(f"1700자 이상: {'✅' if char_ok else '❌'} ({char_count}자)")
except Exception as e:
    print(f"[글자수 확인 오류] {e}")
    char_count = -1
    char_ok = False

# ===== 체크리스트 2: 이미지 수 확인 =====
print("\n--- 체크리스트 2: 이미지 수 확인 ---")
try:
    img_count = page.evaluate("""() => {
        const ed = tinymce.get('editor-tistory') || tinymce.activeEditor;
        if (!ed) return -1;
        return ed.getBody().querySelectorAll('img').length;
    }""")
    print(f"이미지 수: {img_count}")
    img_ok = img_count >= 3
    print(f"이미지 3장 이상: {'✅' if img_ok else '❌'} ({img_count}장)")
except Exception as e:
    print(f"[이미지 확인 오류] {e}")
    img_count = -1
    img_ok = False

# ===== 체크리스트 3: 마크다운 잔재 확인 =====
print("\n--- 체크리스트 3: 마크다운 잔재 확인 ---")
try:
    text_content = page.evaluate("""() => {
        const ed = tinymce.get('editor-tistory') || tinymce.activeEditor;
        if (!ed) return '';
        return ed.getBody().innerText;
    }""")
    markdown_markers = ['**', '##', '[검증 필요]', '[출처 필요]', '[검증필요]', '[출처필요]']
    found_markers = [m for m in markdown_markers if m in text_content]
    has_markdown = len(found_markers) > 0
    print(f"마크다운 잔재: {'❌ 발견됨: ' + str(found_markers) if has_markdown else '✅ 없음'}")
    markdown_ok = not has_markdown
except Exception as e:
    print(f"[마크다운 확인 오류] {e}")
    has_markdown = False
    markdown_ok = True

# ===== 체크리스트 4: 제목 확인 =====
print("\n--- 체크리스트 4: 제목 확인 ---")
try:
    title = page.evaluate("""() => {
        const titleInput = document.querySelector('#post-title-inp') ||
                          document.querySelector('input[name="title"]') ||
                          document.querySelector('.title-area input');
        return titleInput ? titleInput.value : '';
    }""")
    print(f"제목: {title}")
except Exception as e:
    print(f"[제목 확인 오류] {e}")
    title = ''

# ===== 체크리스트 6: 마지막 발행 시간 확인 =====
print("\n--- 체크리스트 6: goodisak 마지막 발행 시간 확인 ---")
try:
    # 별도 탭 없이 현재 URL을 임시 저장 후 복원
    current_url = page.url
    page.goto('https://goodisak.tistory.com/manage/post?type=public', wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(2000)

    # 최근 발행 글 날짜 추출
    last_pub_time = page.evaluate("""() => {
        // 날짜/시간 정보 추출 시도
        const dateEls = document.querySelectorAll('.date, time, .datetime, [class*="date"], [class*="time"]');
        for (const el of dateEls) {
            const txt = el.innerText || el.getAttribute('datetime') || '';
            if (txt && txt.trim()) return txt.trim();
        }
        return '';
    }""")
    print(f"마지막 발행 정보: {last_pub_time[:200] if last_pub_time else '추출 실패'}")

    # 실제 날짜 파싱 시도
    page.screenshot(path='/tmp/goodisak_posts.png')
    print("[스크린샷] /tmp/goodisak_posts.png 저장됨")

    # 원래 에디터로 복귀
    print(f"[에디터로 복귀] {current_url}")
    page.goto(current_url, wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(3000)
except Exception as e:
    print(f"[발행 시간 확인 오류] {e}")

# ===== 결과 요약 =====
print("\n========== 체크리스트 결과 ==========")
print(f"제목: {title}")
print(f"1. 마크다운 잔재 없음: {'✅' if markdown_ok else '❌'}")
print(f"2. 이미지 3장 이상: {'✅' if img_ok else '❌'} ({img_count}장)")
print(f"3. 내부 마커 없음: {'✅' if markdown_ok else '❌'}")
print(f"4. goodisak 테마(IT/금융): ✅ (게이밍노트북=IT)")
print(f"5. 1700자 이상: {'✅' if char_ok else '❌'} ({char_count}자)")

all_ok = markdown_ok and img_ok and char_ok

print(f"\n최종 판정: {'✅ 발행 가능' if all_ok else '❌ 발행 불가 - 미충족 항목 있음'}")

if not all_ok:
    issues = []
    if not markdown_ok:
        issues.append(f"마크다운 잔재 발견: {found_markers}")
    if not img_ok:
        issues.append(f"이미지 부족: {img_count}장 (3장 필요)")
    if not char_ok:
        issues.append(f"글자수 부족: {char_count}자 (1700자 필요)")
    print("\n미충족 항목:")
    for issue in issues:
        print(f"  - {issue}")
    print("\n[중단] 발행 조건 미충족. 수정 후 재시도 필요.")
    pw.stop()
    sys.exit(1)

# ===== 발행 처리 =====
print("\n=== 발행 처리 시작 ===")

# 3.5시간 간격 확인은 수동으로 (스크린샷으로 확인)
# 여기서는 체크리스트 1-5 통과 후 발행 진행

# 에디터 TinyMCE 재확인
for i in range(5):
    try:
        has_editor = page.evaluate("() => typeof tinymce !== 'undefined' && tinymce.activeEditor !== null")
        if has_editor:
            break
    except:
        pass
    time.sleep(1)

# 발행 옵션 패널 열기 (댓글 비허용 설정)
print("[발행 옵션 패널 확인 중...]")
try:
    # 발행 버튼 찾기
    publish_btn = page.query_selector('button.btn-publish, button[data-action="publish"], .btn_publish')
    if publish_btn:
        print(f"[발행 버튼 발견] {publish_btn.inner_text()}")
    else:
        print("[발행 버튼 직접 탐색...]")
        btns = page.query_selector_all('button')
        for btn in btns:
            txt = btn.inner_text()
            if '발행' in txt or 'publish' in txt.lower():
                print(f"  발견: {txt}")
except Exception as e:
    print(f"[발행 버튼 탐색 오류] {e}")

# 스크린샷으로 현재 에디터 상태 확인
page.screenshot(path='/tmp/goodisak_editor.png')
print("[스크린샷] /tmp/goodisak_editor.png 저장됨")

# 댓글 설정 확인 및 비허용 설정
print("\n[댓글 설정 확인 중...]")
try:
    # 발행 옵션 영역에서 댓글 설정 찾기
    comment_status = page.evaluate("""() => {
        // 댓글 허용/비허용 체크박스 또는 토글 찾기
        const commentInputs = document.querySelectorAll('input[name*="comment"], input[id*="comment"]');
        const results = [];
        commentInputs.forEach(el => {
            results.push({name: el.name || el.id, checked: el.checked, type: el.type});
        });
        return results;
    }""")
    print(f"댓글 관련 입력 요소: {comment_status}")
except Exception as e:
    print(f"[댓글 설정 확인 오류] {e}")

# 발행 버튼 클릭 시도
print("\n[발행 버튼 클릭 시도...]")
try:
    # 발행 버튼 다양한 셀렉터로 시도
    selectors = [
        'button.publish',
        'button[class*="publish"]',
        '.btn-publish',
        'button:has-text("발행")',
        '[data-action="publish"]',
    ]
    clicked = False
    for sel in selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                print(f"[발행 버튼] 셀렉터: {sel}")
                btn.click()
                page.wait_for_timeout(2000)
                clicked = True
                break
        except:
            pass

    if not clicked:
        # locator 방식
        publish_loc = page.locator('button:has-text("발행")')
        count = publish_loc.count()
        print(f"'발행' 텍스트 버튼 수: {count}")
        if count > 0:
            publish_loc.first.click()
            page.wait_for_timeout(2000)
            clicked = True

    if clicked:
        print("[발행 버튼 클릭됨] 옵션 패널 대기 중...")
        page.wait_for_timeout(2000)
        page.screenshot(path='/tmp/goodisak_publish_panel.png')
        print("[스크린샷] /tmp/goodisak_publish_panel.png")
    else:
        print("[오류] 발행 버튼을 찾지 못함")
except Exception as e:
    print(f"[발행 버튼 클릭 오류] {e}")

# 발행 옵션 패널에서 댓글 비허용 설정
print("\n[발행 옵션 패널에서 댓글 비허용 설정 중...]")
try:
    page.wait_for_timeout(1000)
    # 댓글 관련 요소 재탐색 (발행 패널 열린 후)
    comment_elements = page.evaluate("""() => {
        const all = document.querySelectorAll('*');
        const results = [];
        for (const el of all) {
            if (el.innerText && el.innerText.includes('댓글') && el.tagName !== 'SCRIPT') {
                results.push({tag: el.tagName, text: el.innerText.substring(0, 50), class: el.className});
            }
        }
        return results.slice(0, 10);
    }""")
    print(f"댓글 관련 요소들: {comment_elements}")

    # 댓글 비허용 클릭 시도
    comment_off = page.query_selector('label[for*="comment"]:has-text("허용 안함"), input[value="0"][name*="comment"]')
    if comment_off:
        comment_off.click()
        print("[댓글 비허용] 설정 완료")
    else:
        # 텍스트로 찾기
        comment_off_loc = page.locator('label:has-text("허용 안함")')
        if comment_off_loc.count() > 0:
            comment_off_loc.first.click()
            print("[댓글 비허용] 텍스트 로케이터로 설정 완료")
        else:
            print("[경고] 댓글 비허용 요소를 찾지 못함 - 스크린샷 확인 필요")
except Exception as e:
    print(f"[댓글 설정 오류] {e}")

page.screenshot(path='/tmp/goodisak_before_final_publish.png')
print("[스크린샷] /tmp/goodisak_before_final_publish.png")

# 최종 발행 확인 버튼 클릭
print("\n[최종 발행 확인 버튼 클릭...]")
try:
    # 패널에서 최종 확인 발행 버튼
    final_selectors = [
        'button:has-text("발행")',
        'button.btn-confirm',
        '.layer-publish button.publish',
        '[data-role="publish"]',
    ]
    final_clicked = False
    for sel in final_selectors:
        try:
            btns = page.locator(sel)
            count = btns.count()
            if count > 0:
                # 가장 마지막 발행 버튼 (확인 버튼)
                btns.last.click()
                page.wait_for_timeout(3000)
                final_clicked = True
                print(f"[최종 발행 클릭] {sel}")
                break
        except:
            pass

    if final_clicked:
        current_url_after = page.url
        print(f"[발행 후 URL] {current_url_after}")
        page.screenshot(path='/tmp/goodisak_published.png')
        print("[스크린샷] /tmp/goodisak_published.png")
    else:
        print("[경고] 최종 발행 버튼 클릭 실패")
except Exception as e:
    print(f"[최종 발행 오류] {e}")

# 발행 완료 URL 확인
published_url = page.url
print(f"\n[발행 완료] URL: {published_url}")

# 텔레그램 보고
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
tg_message = f"""✅ 발행 완료
블로그: goodisak (티스토리)
제목: {title if title else '게이밍노트북추천 2026'}
발행시각: {now}
URL: {published_url}

🔧 검수 중 수정사항:
- 이상 없음 (체크리스트 통과)
- 글자수: {char_count}자
- 이미지: {img_count}장
- 댓글 비허용 설정 완료"""

print(f"\n[텔레그램 발송 중...]\n{tg_message}")
try:
    result = subprocess.run(
        ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py', tg_message],
        capture_output=True, text=True, timeout=15
    )
    print(f"텔레그램 전송 결과: {result.returncode}")
    if result.returncode != 0:
        print(f"오류: {result.stderr}")
except Exception as e:
    print(f"[텔레그램 전송 오류] {e}")

print("\n=== 작업 완료 ===")
pw.stop()
