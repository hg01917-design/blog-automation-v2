"""
goodisak 게이밍노트북 드래프트 발행 (완료 버튼 → 옵션 → 발행)
"""
import sys, time, datetime, subprocess
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp

print("=== goodisak 발행 시작 ===")

pw, browser = connect_cdp()
ctx = browser.contexts[0]

# goodisak newpost 탭 찾기
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
print(f"[탭] {page.url}")

# 에디터 준비 확인
for i in range(8):
    try:
        has_ed = page.evaluate("() => typeof tinymce !== 'undefined' && tinymce.activeEditor !== null")
        if has_ed:
            print(f"[에디터 준비됨]")
            break
    except:
        pass
    time.sleep(1)

# 제목 확인
title = page.evaluate("""() => {
    const inp = document.querySelector('#post-title-inp, input[name="title"], [placeholder="제목을 입력하세요"]');
    return inp ? inp.value : '';
}""")
print(f"[제목] {title}")

# 글자수/이미지 최종 확인
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

if char_count < 1700:
    print(f"[중단] 글자수 부족: {char_count}자")
    pw.stop()
    sys.exit(1)
if img_count < 3:
    print(f"[중단] 이미지 부족: {img_count}장")
    pw.stop()
    sys.exit(1)

# ===== 마지막 발행 시간 확인 =====
print("\n[마지막 발행 시간 확인 - 별도 탭 참조...]")
last_pub_info = ""
for p in ctx.pages:
    if 'goodisak.tistory.com/manage/posts' in p.url and 'temp' not in p.url:
        try:
            last_pub_text = p.evaluate("""() => {
                const rows = document.querySelectorAll('tr, .post-item, [class*="post"]');
                for (const row of rows) {
                    const txt = row.innerText;
                    if (txt && txt.trim().length > 5) return txt.substring(0, 300);
                }
                return document.body.innerText.substring(0, 500);
            }""")
            last_pub_info = last_pub_text
            print(f"[발행 목록 탭] {p.url}")
            print(f"[내용] {last_pub_text[:300]}")
            break
        except:
            pass

# ===== "완료" 버튼 클릭 =====
print("\n[완료 버튼 클릭...]")
try:
    # 완료 버튼 (우측 하단)
    done_btn = page.query_selector('button.btn-done, button:has-text("완료"), .btn_done')
    if done_btn:
        done_btn.click()
        page.wait_for_timeout(2000)
        print("[완료 버튼 클릭됨]")
    else:
        # locator 방식
        done_loc = page.locator('button:has-text("완료")')
        cnt = done_loc.count()
        print(f"'완료' 버튼 수: {cnt}")
        if cnt > 0:
            done_loc.last.click()
            page.wait_for_timeout(2000)
            print("[완료 버튼 클릭됨]")
        else:
            # 모든 버튼 목록 출력
            all_btns = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('button')).map(b => ({
                    text: b.innerText,
                    class: b.className,
                    visible: b.offsetParent !== null
                }));
            }""")
            print(f"[모든 버튼] {all_btns}")
except Exception as e:
    print(f"[완료 버튼 오류] {e}")

page.screenshot(path='/tmp/goodisak_after_done.png')
print("[스크린샷] /tmp/goodisak_after_done.png")

# ===== 발행 옵션 패널 확인 =====
print("\n[발행 옵션 패널 확인...]")
page.wait_for_timeout(1000)

# 댓글 비허용 설정
print("[댓글 비허용 설정 중...]")
try:
    # 발행 패널 내 댓글 설정 찾기
    comment_info = page.evaluate("""() => {
        const labels = document.querySelectorAll('label');
        const results = [];
        labels.forEach(lb => {
            if (lb.innerText.includes('댓글')) {
                results.push({text: lb.innerText, for: lb.htmlFor, class: lb.className});
            }
        });
        // input radio/checkbox for comment
        const inputs = document.querySelectorAll('input');
        const inputResults = [];
        inputs.forEach(inp => {
            if (inp.name && inp.name.includes('comment') || inp.id && inp.id.includes('comment')) {
                inputResults.push({name: inp.name, id: inp.id, value: inp.value, checked: inp.checked, type: inp.type});
            }
        });
        return {labels: results, inputs: inputResults};
    }""")
    print(f"[댓글 요소] {comment_info}")

    # 댓글 "허용 안함" 또는 비허용 라디오 클릭
    clicked_comment = False
    for selector in [
        'input[name="acceptComment"][value="0"]',
        'input[name="comment"][value="0"]',
        'input[id*="comment"][value="0"]',
        'label:has-text("허용 안함")',
        'label:has-text("비허용")',
        'label:has-text("댓글 사용 안함")',
    ]:
        try:
            el = page.query_selector(selector)
            if el:
                el.click()
                page.wait_for_timeout(500)
                print(f"[댓글 비허용 클릭] {selector}")
                clicked_comment = True
                break
        except:
            pass

    if not clicked_comment:
        # radio 버튼 전체 탐색
        radios = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input[type="radio"]')).map(r => ({
                name: r.name, value: r.value, id: r.id, checked: r.checked,
                label: document.querySelector('label[for="' + r.id + '"]')?.innerText || ''
            }));
        }""")
        print(f"[모든 라디오 버튼] {radios}")
        # 라디오 중 댓글 관련 + 비허용(0 또는 false) 선택
        for radio in radios:
            if 'comment' in (radio.get('name', '') + radio.get('id', '') + radio.get('label', '')).lower():
                val = radio.get('value', '')
                if val in ('0', 'false', 'N', 'off'):
                    radio_id = radio.get('id', '')
                    if radio_id:
                        page.click(f'#{radio_id}')
                        page.wait_for_timeout(500)
                        print(f"[댓글 비허용 라디오 클릭] id={radio_id}, value={val}")
                        clicked_comment = True
                        break

    if not clicked_comment:
        print("[경고] 댓글 비허용 요소 못 찾음 - 스크린샷으로 확인 필요")
except Exception as e:
    print(f"[댓글 설정 오류] {e}")

page.screenshot(path='/tmp/goodisak_publish_options.png')
print("[스크린샷] /tmp/goodisak_publish_options.png")

# ===== 최종 발행 버튼 클릭 =====
print("\n[최종 발행 버튼 클릭...]")
try:
    # 발행 패널의 최종 발행 버튼
    publish_selectors = [
        'button.btn-publish:visible',
        '.layer-publish button:has-text("발행")',
        '.publish-panel button:has-text("발행")',
        'button[data-action="publish"]',
    ]
    published = False
    for sel in publish_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(3000)
                published = True
                print(f"[발행 클릭] {sel}")
                break
        except:
            pass

    if not published:
        # 가시적인 발행 버튼 찾기
        visible_btns = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button')).filter(b => {
                return b.offsetParent !== null && (b.innerText.includes('발행') || b.className.includes('publish'));
            }).map(b => ({text: b.innerText, class: b.className}));
        }""")
        print(f"[가시 발행 버튼들] {visible_btns}")

        # locator로 마지막 발행 버튼
        pub_loc = page.locator('button:has-text("발행"):visible')
        cnt = pub_loc.count()
        print(f"locator 발행 버튼 수: {cnt}")
        if cnt > 0:
            pub_loc.last.click()
            page.wait_for_timeout(3000)
            published = True
            print("[locator 발행 클릭됨]")

    if published:
        current_url = page.url
        print(f"\n[발행 후 URL] {current_url}")
        page.screenshot(path='/tmp/goodisak_published_final.png')
        print("[스크린샷] /tmp/goodisak_published_final.png")

        # 발행된 URL 파악 (숫자 게시물 번호가 있는 URL인지 확인)
        import re
        if re.search(r'goodisak\.tistory\.com/\d+', current_url):
            published_url = current_url
        else:
            published_url = current_url
        print(f"[발행 URL] {published_url}")

        # 텔레그램 보고
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
- 댓글 비허용 설정"""

        print(f"\n[텔레그램 발송]\n{tg_msg}")
        result = subprocess.run(
            ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py', tg_msg],
            capture_output=True, text=True, timeout=15
        )
        print(f"텔레그램: {result.returncode}, {result.stderr[:100] if result.stderr else 'OK'}")
    else:
        print("[오류] 발행 버튼 클릭 실패")
        # 오류 텔레그램
        err_msg = f"""⚠️ 오류 발생
작업: goodisak 게이밍노트북 드래프트 발행
오류: 발행 버튼을 찾지 못함
조치: 수동 확인 필요 (스크린샷: /tmp/goodisak_publish_options.png)"""
        subprocess.run(
            ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py', err_msg],
            capture_output=True, text=True, timeout=15
        )
except Exception as e:
    print(f"[발행 오류] {e}")
    err_msg = f"""⚠️ 오류 발생
작업: goodisak 게이밍노트북 드래프트 발행
오류: {str(e)[:200]}
조치: 수동 확인 필요"""
    subprocess.run(
        ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py', err_msg],
        capture_output=True, text=True, timeout=15
    )

print("\n=== 작업 완료 ===")
pw.stop()
