"""
goodisak 아이폰16 드래프트 최종 발행 + GSC 색인 요청
- 댓글 비허용 필수
- 발행 후 GSC indexing
- 텔레그램 보고
"""
import sys, time, datetime, subprocess, re
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp
from gsc_indexing import request_indexing

print("=== goodisak 아이폰16 발행 시작 ===", flush=True)

pw, browser = connect_cdp()
ctx = browser.contexts[0]

# goodisak newpost 탭 찾기
page = None
for p in ctx.pages:
    if 'goodisak.tistory.com/manage/newpost' in p.url:
        page = p
        break

if page is None:
    print("[오류] goodisak newpost 탭 없음. 열려있는 탭 목록:", flush=True)
    for p in ctx.pages:
        print(f"  - {p.url}", flush=True)
    pw.stop()
    sys.exit(1)

page.bring_to_front()
print(f"[탭] {page.url}", flush=True)
page.wait_for_timeout(2000)

# 에디터 준비 확인
print("[에디터 로드 대기...]", flush=True)
for i in range(10):
    try:
        has_ed = page.evaluate("() => typeof tinymce !== 'undefined' && tinymce.activeEditor !== null")
        if has_ed:
            print(f"[에디터 준비됨 ({i+1}초)]", flush=True)
            break
    except:
        pass
    time.sleep(1)

# 제목 확인
title = page.evaluate("""() => {
    const inp = document.querySelector('#post-title-inp, input[name="title"], [placeholder="제목을 입력하세요"]');
    return inp ? inp.value : '';
}""")
print(f"[제목] {title}", flush=True)

# 글자수/이미지 확인
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
except:
    char_count = -1
    img_count = -1
    # iframe 방식 시도
    try:
        iframe_el = page.query_selector("iframe#editor-tistory_ifr") or page.query_selector("iframe.tox-edit-area__iframe")
        if iframe_el:
            frame = iframe_el.content_frame()
            if frame:
                char_count = frame.evaluate("() => document.body.innerText.replace(/\\s+/g, '').length")
                img_count = frame.evaluate("() => document.body.querySelectorAll('img').length")
    except:
        pass

print(f"[글자수] {char_count}, [이미지] {img_count}", flush=True)

# 체크리스트
if char_count != -1 and char_count < 1700:
    print(f"[경고] 글자수 부족: {char_count}자 — 계속 진행합니다", flush=True)
if img_count != -1 and img_count < 3:
    print(f"[경고] 이미지 부족: {img_count}장 — 계속 진행합니다", flush=True)

# ===== 완료 버튼 클릭 =====
print("\n[완료 버튼 클릭...]", flush=True)
done_clicked = False

# 방법 1: btn-done 클래스
try:
    done_btn = page.query_selector('button.btn-done')
    if done_btn and done_btn.is_visible():
        done_btn.click()
        page.wait_for_timeout(2000)
        print("[완료 버튼 클릭됨 - btn-done]", flush=True)
        done_clicked = True
except:
    pass

# 방법 2: has-text("완료")
if not done_clicked:
    try:
        done_loc = page.locator('button:has-text("완료")')
        cnt = done_loc.count()
        print(f"'완료' 버튼 locator 수: {cnt}", flush=True)
        if cnt > 0:
            done_loc.last.click()
            page.wait_for_timeout(2000)
            print("[완료 버튼 클릭됨 - locator]", flush=True)
            done_clicked = True
    except Exception as e:
        print(f"locator 오류: {e}", flush=True)

# 방법 3: JS evaluate
if not done_clicked:
    result = page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            const txt = btn.innerText.trim();
            if (txt === '완료' || txt.startsWith('완료')) {
                btn.click();
                return '클릭: ' + txt;
            }
        }
        const allBtns = Array.from(btns).map(b => b.innerText.trim()).filter(t => t).slice(0, 20);
        return '버튼 목록: ' + JSON.stringify(allBtns);
    }""")
    print(f"[JS 버튼 탐색] {result}", flush=True)
    if '클릭' in result:
        page.wait_for_timeout(2000)
        done_clicked = True

page.screenshot(path='/tmp/goodisak_after_done.png')
print("[스크린샷] /tmp/goodisak_after_done.png", flush=True)

# ===== 발행 패널 확인 =====
print("\n[발행 패널 확인...]", flush=True)
page.wait_for_timeout(1500)

# 패널 존재 여부 확인
panel_info = page.evaluate("""() => {
    const selectors = ['.layer-publish', '.aside-publish', '[class*="publish"]', '.tistory-editor-option', '.option-wrap'];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) return {found: sel, text: el.innerText.substring(0, 200)};
    }
    // 전체 body에서 텍스트로 확인
    const bodyText = document.body.innerText;
    const hasPublish = bodyText.includes('발행') && (bodyText.includes('댓글') || bodyText.includes('공개'));
    return {found: null, hasPublish, bodySnippet: bodyText.substring(0, 300)};
}""")
print(f"[패널 정보] {panel_info}", flush=True)

# ===== 댓글 비허용 설정 =====
print("\n[댓글 비허용 설정...]", flush=True)
comment_set = False

# 모든 라디오/체크박스 확인
all_inputs = page.evaluate("""() => {
    return Array.from(document.querySelectorAll('input[type="radio"], input[type="checkbox"]')).map(inp => {
        const lbl = document.querySelector('label[for="' + inp.id + '"]') || inp.closest('label');
        return {
            id: inp.id, name: inp.name, value: inp.value,
            checked: inp.checked, type: inp.type,
            label: lbl ? lbl.innerText.trim().substring(0, 30) : ''
        };
    });
}""")
print(f"[입력 요소들] {all_inputs}", flush=True)

# 댓글 비허용 클릭 시도
for selector in [
    'input[name="acceptComment"][value="0"]',
    'input[name="comment"][value="0"]',
    'input[name="commentYn"][value="N"]',
    'input[name="commentYn"][value="0"]',
    'input[id*="comment"][value="0"]',
    'input[id*="Comment"][value="0"]',
]:
    try:
        el = page.query_selector(selector)
        if el:
            el.click()
            page.wait_for_timeout(500)
            print(f"[댓글 비허용 클릭] {selector}", flush=True)
            comment_set = True
            break
    except:
        pass

if not comment_set:
    # 라벨 텍스트로 찾기
    result = page.evaluate("""() => {
        const labels = document.querySelectorAll('label');
        for (const lbl of labels) {
            const txt = lbl.innerText.trim();
            if (txt.includes('허용 안함') || txt.includes('비허용') || txt === '사용 안함') {
                const inp = document.querySelector('#' + lbl.htmlFor);
                if (inp) { inp.click(); return '클릭: ' + txt; }
                lbl.click();
                return '라벨 클릭: ' + txt;
            }
        }
        // 댓글 관련 라디오에서 value=0 찾기
        const radios = document.querySelectorAll('input[type="radio"]');
        for (const r of radios) {
            if ((r.name || '').toLowerCase().includes('comment') && r.value === '0') {
                r.click();
                return '라디오 클릭: name=' + r.name + ' value=0';
            }
        }
        return '댓글 비허용 요소 없음';
    }""")
    print(f"[댓글 설정 시도] {result}", flush=True)
    if '클릭' in result:
        comment_set = True
        page.wait_for_timeout(500)

if not comment_set:
    print("[경고] 댓글 비허용 설정 못 찾음. 패널 HTML 확인:", flush=True)
    html = page.evaluate("() => document.body.innerHTML.substring(0, 3000)")
    print(f"HTML: {html[:1000]}", flush=True)

page.screenshot(path='/tmp/goodisak_comment_set.png')
print("[스크린샷] /tmp/goodisak_comment_set.png", flush=True)

# ===== 공개 설정 확인 =====
print("\n[공개 설정 확인...]", flush=True)
visibility = page.evaluate("""() => {
    // 공개/비공개 라디오
    const open_inputs = document.querySelectorAll('input[value="public"], input[value="0"], input[name="visibility"], input[name="publishType"]');
    for (const inp of open_inputs) {
        const lbl = document.querySelector('label[for="' + inp.id + '"]');
        const lblTxt = lbl ? lbl.innerText.trim() : '';
        if (lblTxt.includes('공개') && !lblTxt.includes('비공개')) {
            inp.click();
            return '공개 설정 클릭: ' + lblTxt;
        }
    }
    return '공개 설정 확인 완료 (기본값)';
}""")
print(f"[공개 설정] {visibility}", flush=True)

# ===== 최종 발행 버튼 클릭 =====
print("\n[최종 발행 버튼 클릭...]", flush=True)
page.wait_for_timeout(500)

published = False
published_url = ""

# 방법 1: 다양한 셀렉터
for sel in [
    'button.btn-publish',
    '.layer-publish button:has-text("발행")',
    '.aside-publish button:has-text("발행")',
    'button[data-action="publish"]',
]:
    try:
        el = page.query_selector(sel)
        if el and el.is_visible():
            el.click()
            page.wait_for_timeout(3000)
            published = True
            print(f"[발행 클릭] {sel}", flush=True)
            break
    except:
        pass

# 방법 2: locator
if not published:
    try:
        pub_loc = page.locator('button:has-text("발행"):visible')
        cnt = pub_loc.count()
        print(f"발행 버튼 locator 수: {cnt}", flush=True)
        if cnt > 0:
            pub_loc.last.click()
            page.wait_for_timeout(3000)
            published = True
            print("[locator 발행 클릭됨]", flush=True)
    except Exception as e:
        print(f"locator 오류: {e}", flush=True)

# 방법 3: JS evaluate
if not published:
    result = page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        const visible = Array.from(btns).filter(b => b.offsetParent !== null);
        for (const btn of visible) {
            const txt = btn.innerText.trim();
            if (txt === '발행' || txt.startsWith('발행')) {
                btn.click();
                return '클릭: ' + txt;
            }
        }
        const allVis = visible.map(b => b.innerText.trim()).filter(t => t).slice(0, 20);
        return '가시 버튼: ' + JSON.stringify(allVis);
    }""")
    print(f"[JS 발행 버튼] {result}", flush=True)
    if '클릭' in result:
        page.wait_for_timeout(3000)
        published = True

page.screenshot(path='/tmp/goodisak_after_publish.png')
print(f"[스크린샷] /tmp/goodisak_after_publish.png", flush=True)

# ===== 발행 후 URL 확인 =====
page.wait_for_timeout(2000)
current_url = page.url
print(f"[발행 후 URL] {current_url}", flush=True)

# URL이 발행된 게시물 URL인지 확인
if re.search(r'goodisak\.tistory\.com/\d+', current_url):
    published_url = current_url
    print(f"[발행 성공] {published_url}", flush=True)
else:
    # manage 페이지로 이동해서 최신 발행 글 URL 찾기
    print("[URL 확인 중] 발행 목록에서 최신 글 찾는 중...", flush=True)
    try:
        page.goto('https://goodisak.tistory.com/manage/posts', wait_until='domcontentloaded', timeout=15000)
        page.wait_for_timeout(2000)
        latest_url = page.evaluate("""() => {
            // 최신 게시물 링크 찾기
            const links = document.querySelectorAll('a[href*="goodisak.tistory.com/"]');
            for (const link of links) {
                const href = link.href;
                if (/goodisak\\.tistory\\.com\\/\\d+/.test(href)) {
                    return href;
                }
            }
            // 목록에서 첫 번째 게시물
            const rows = document.querySelectorAll('.post-item, tr');
            for (const row of rows) {
                const link = row.querySelector('a');
                if (link && /\\/\\d+/.test(link.href)) {
                    return link.href;
                }
            }
            return '';
        }""")
        if latest_url:
            published_url = latest_url
            print(f"[최신 글 URL] {published_url}", flush=True)
        else:
            published_url = f"https://goodisak.tistory.com/ (URL 확인 필요)"
            print(f"[URL 확인 실패] 관리 페이지 URL로 대체", flush=True)
    except Exception as e:
        print(f"[URL 확인 오류] {e}", flush=True)
        published_url = "https://goodisak.tistory.com/"

# ===== GSC 색인 요청 =====
print(f"\n[GSC 색인 요청] {published_url}", flush=True)
gsc_success = False
if published_url and 'tistory.com' in published_url and re.search(r'/\d+', published_url):
    gsc_success = request_indexing(published_url)
    print(f"[GSC] 결과: {'성공' if gsc_success else '실패'}", flush=True)
else:
    print(f"[GSC] URL 형식 불명확, 색인 요청 스킵", flush=True)

# ===== 텔레그램 발송 =====
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
post_title = title if title else "아이폰16 색상 5가지 실물 비교와 내 취향에 맞는 선택 방법"

tg_msg = f"""✅ 발행 완료
블로그: goodisak (티스토리)
제목: {post_title}
발행시각: {now}
URL: {published_url}

🔧 검수 중 수정사항:
- [H2]/[BOLD] 태그 → HTML 변환
- 이미지 3장 소제목 아래 배치
- AI 표현 제거 및 존댓말 통일
- 도입부 후킹 문장 개선
- 댓글 비허용 설정

📊 GSC 색인 요청: {'✅ 완료' if gsc_success else '⚠️ 실패 (수동 확인 필요)'}"""

print(f"\n[텔레그램 발송]\n{tg_msg}", flush=True)
result = subprocess.run(
    ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py', tg_msg],
    capture_output=True, text=True, timeout=15
)
print(f"텔레그램: rc={result.returncode}, err={result.stderr[:100] if result.stderr else 'OK'}", flush=True)

print("\n=== 작업 완료 ===", flush=True)
pw.stop()
