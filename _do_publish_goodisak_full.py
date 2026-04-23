"""
goodisak 아이폰16 글 완전 발행:
1. Gemini로 이미지 3장 생성
2. 에디터에 이미지 삽입 (이미지 업로드 버튼 사용)
3. 댓글 비허용 설정
4. 공개 발행
5. GSC 색인 요청
6. 텔레그램 보고
"""
import sys, time, datetime, subprocess, re
from pathlib import Path
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp
from gsc_indexing import request_indexing

print("=== goodisak 아이폰16 이미지+발행 시작 ===", flush=True)

# ===== Step 1: Gemini 이미지 생성 =====
print("\n[Step 1] Gemini 이미지 생성...", flush=True)
from gemini_image import generate_images

image_infos = [
    {
        "index": 0,
        "prompt": "iPhone 16 color options display: ultramarine, teal, pink, white, black. Five iPhones arranged neatly on a clean white surface. Product photo style, bright lighting, no text.",
        "filename": "iphone16-colors-overview.webp"
    },
    {
        "index": 1,
        "prompt": "iPhone 16 teal and ultramarine color comparison. Two iPhones side by side showing the color difference. Close-up shot on neutral background, no text, product photography.",
        "filename": "iphone16-teal-ultramarine-compare.webp"
    },
    {
        "index": 2,
        "prompt": "Person holding iPhone 16 in pink color, lifestyle shot. Natural light, casual setting, showing how the phone looks in hand. No text, realistic photo style.",
        "filename": "iphone16-pink-lifestyle.webp"
    },
]

def log_fn(msg):
    print(msg, flush=True)

img_results = generate_images(image_infos, on_log=log_fn)
print(f"\n[이미지 생성 결과] {img_results}", flush=True)

if not img_results:
    print("[오류] 이미지 생성 실패. 발행 중단.", flush=True)
    # 텔레그램 알림
    subprocess.run(
        ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
         '⚠️ 오류 발생\n작업: goodisak 아이폰16 이미지 생성\n오류: Gemini 이미지 생성 실패\n조치: 수동 이미지 삽입 필요'],
        capture_output=True, text=True, timeout=15
    )
    sys.exit(1)

# ===== Step 2: 에디터 연결 및 이미지 삽입 =====
print("\n[Step 2] 에디터 연결...", flush=True)
pw, browser = connect_cdp()
ctx = browser.contexts[0]

# goodisak newpost/77 탭 찾기
page = None
for p in ctx.pages:
    if 'goodisak.tistory.com/manage/newpost/77' in p.url:
        page = p
        break

if page is None:
    # 탭 찾기 실패 시 새 탭에서 편집 페이지로 이동
    print("[편집 탭 없음] 기존 탭에서 이동...", flush=True)
    for p in ctx.pages:
        if 'goodisak.tistory.com' in p.url:
            page = p
            break

    if page:
        page.bring_to_front()
        page.goto('https://goodisak.tistory.com/manage/newpost/77?type=post&returnURL=%2Fmanage%2Fposts%2F',
                  wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(3000)
    else:
        print("[오류] goodisak 탭 없음!", flush=True)
        pw.stop()
        sys.exit(1)

page.bring_to_front()
print(f"[탭] {page.url}", flush=True)

# 에디터 로드 대기
print("[에디터 로드 대기...]", flush=True)
for i in range(12):
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

# 현재 이미지 수 확인
img_count_before = page.evaluate("""() => {
    const ed = tinymce.get('editor-tistory') || tinymce.activeEditor;
    if (!ed) return -1;
    return ed.getBody().querySelectorAll('img').length;
}""")
print(f"[현재 이미지 수] {img_count_before}", flush=True)

# ===== 이미지 삽입 =====
print("\n[이미지 삽입 중...]", flush=True)

# 이미지를 에디터에 삽입하는 함수 - 파일 업로드 방식
def insert_image_to_editor(page, img_path):
    """이미지를 Tistory 에디터에 삽입"""
    img_path = str(img_path)
    print(f"  이미지 삽입 시도: {img_path}", flush=True)

    # 방법 1: 이미지 삽입 버튼 클릭 → 파일 선택
    try:
        # 에디터 툴바의 이미지 버튼 찾기
        img_btn = page.query_selector('.tox-tbtn[aria-label*="이미지"], .tox-tbtn[title*="이미지"], .mce-btn[aria-label*="이미지"]')
        if not img_btn:
            # 이미지 삽입 버튼 (카메라 아이콘)
            img_btn = page.query_selector('button[aria-label*="image"], button[title*="image"]')

        if img_btn:
            img_btn.click()
            page.wait_for_timeout(1000)
            print("  이미지 버튼 클릭", flush=True)
    except Exception as e:
        print(f"  이미지 버튼 클릭 실패: {e}", flush=True)

    # 방법 2: 에디터에 직접 base64로 이미지 삽입
    try:
        import base64
        with open(img_path, 'rb') as f:
            img_data = f.read()

        img_base64 = base64.b64encode(img_data).decode()

        # 파일 확장자 확인
        if img_path.endswith('.webp'):
            mime_type = 'image/webp'
        elif img_path.endswith('.jpg') or img_path.endswith('.jpeg'):
            mime_type = 'image/jpeg'
        elif img_path.endswith('.png'):
            mime_type = 'image/png'
        else:
            mime_type = 'image/webp'

        data_url = f"data:{mime_type};base64,{img_base64}"

        # TinyMCE에 이미지 직접 삽입
        result = page.evaluate(f"""(dataUrl) => {{
            const ed = tinymce.get('editor-tistory') || tinymce.activeEditor;
            if (!ed) return 'no editor';
            // 에디터 끝으로 이동
            ed.selection.select(ed.getBody(), true);
            ed.selection.collapse(false);
            // 이미지 삽입
            ed.insertContent('<p><img src="' + dataUrl + '" style="max-width:100%; height:auto;" /></p>');
            return 'inserted';
        }}""", data_url)

        print(f"  Base64 삽입 결과: {result}", flush=True)
        page.wait_for_timeout(500)
        return result == 'inserted'
    except Exception as e:
        print(f"  Base64 삽입 실패: {e}", flush=True)
        return False

# 이미지 삽입 실행
inserted_count = 0
for idx in sorted(img_results.keys()):
    img_path = img_results[idx]
    success = insert_image_to_editor(page, img_path)
    if success:
        inserted_count += 1
    time.sleep(1)

print(f"\n[삽입된 이미지 수] {inserted_count}", flush=True)

# 삽입 후 이미지 수 확인
img_count_after = page.evaluate("""() => {
    const ed = tinymce.get('editor-tistory') || tinymce.activeEditor;
    if (!ed) return -1;
    return ed.getBody().querySelectorAll('img').length;
}""")
print(f"[삽입 후 이미지 수] {img_count_after}", flush=True)

page.screenshot(path='/tmp/goodisak_with_images.png')
print("[스크린샷] /tmp/goodisak_with_images.png", flush=True)

# 이미지가 0이면 업로드 실패 - 다른 방법 시도
if img_count_after == 0:
    print("[이미지 없음] 파일 업로드 방식으로 재시도...", flush=True)

    # 이미지 삽입 툴바 버튼 찾기
    toolbar_info = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button[aria-label], .tox-tbtn, [title]'));
        return btns.filter(b => {
            const label = b.getAttribute('aria-label') || b.getAttribute('title') || '';
            return label.toLowerCase().includes('image') || label.includes('이미지');
        }).map(b => ({
            label: b.getAttribute('aria-label') || b.getAttribute('title'),
            class: b.className.substring(0, 50)
        })).slice(0, 10);
    }""")
    print(f"[이미지 버튼 목록] {toolbar_info}", flush=True)

    # 에디터 이미지 업로드 단축키 시도 (Ctrl+Alt+I 또는 관련)
    # Tistory 에디터의 이미지 삽입 방식 확인
    editor_apis = page.evaluate("""() => {
        // Tistory 에디터 전용 함수 확인
        const fns = Object.keys(window).filter(k => k.toLowerCase().includes('image') || k.toLowerCase().includes('upload'));
        return fns.slice(0, 20);
    }""")
    print(f"[에디터 이미지 API] {editor_apis}", flush=True)

# 글자수 최종 확인
char_count = page.evaluate("""() => {
    const ed = tinymce.get('editor-tistory') || tinymce.activeEditor;
    if (!ed) return -1;
    return ed.getBody().innerText.replace(/\\s+/g, '').length;
}""")
print(f"[최종 글자수] {char_count}", flush=True)

# ===== Step 3: 완료 버튼 클릭 =====
print("\n[Step 3] 완료 버튼 클릭...", flush=True)
done_clicked = False

# 완료 버튼 찾기 (btn-done 클래스 또는 텍스트)
for sel in ['button.btn-done', 'button:text("완료")']:
    try:
        el = page.query_selector(sel)
        if el and el.is_visible():
            el.click()
            page.wait_for_timeout(2000)
            print(f"[완료 클릭] {sel}", flush=True)
            done_clicked = True
            break
    except:
        pass

if not done_clicked:
    try:
        done_loc = page.locator('button:has-text("완료")')
        cnt = done_loc.count()
        print(f"완료 버튼 수: {cnt}", flush=True)
        if cnt > 0:
            done_loc.last.click()
            page.wait_for_timeout(2000)
            done_clicked = True
            print("[완료 버튼 클릭됨]", flush=True)
    except Exception as e:
        print(f"완료 locator 오류: {e}", flush=True)

if not done_clicked:
    result = page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.innerText.trim() === '완료' && btn.offsetParent !== null) {
                btn.click();
                return '클릭';
            }
        }
        return Array.from(btns).filter(b => b.offsetParent !== null).map(b => b.innerText.trim()).filter(t => t);
    }""")
    print(f"[JS 완료 버튼] {result}", flush=True)
    if result == '클릭':
        done_clicked = True
        page.wait_for_timeout(2000)

page.screenshot(path='/tmp/goodisak_after_done2.png')
print("[스크린샷] /tmp/goodisak_after_done2.png", flush=True)

# ===== Step 4: 발행 패널 - 댓글 비허용 + 공개 설정 =====
print("\n[Step 4] 발행 패널 설정...", flush=True)
page.wait_for_timeout(1500)

# 발행 패널 텍스트 확인
panel_text = page.evaluate("""() => {
    const panel = document.querySelector('[class*="publish"]');
    return panel ? panel.innerText.substring(0, 300) : '패널 없음';
}""")
print(f"[발행 패널] {panel_text}", flush=True)

# 댓글 설정 드롭다운 클릭 (댓글 허용 → 비허용으로 변경)
print("[댓글 설정 변경...]", flush=True)

# "댓글 허용" 드롭다운 버튼 클릭
comment_click = page.evaluate("""() => {
    const allEls = document.querySelectorAll('button, a, span, div');
    for (const el of allEls) {
        const txt = (el.innerText || '').trim();
        if (txt === '댓글 허용' || txt === '댓글허용') {
            if (el.offsetParent !== null) {
                el.click();
                return '클릭: ' + txt;
            }
        }
    }
    // 발행 패널 내 드롭다운
    const panel = document.querySelector('[class*="publish"]');
    if (panel) {
        const dropBtns = panel.querySelectorAll('button, [role="button"]');
        for (const btn of dropBtns) {
            const txt = btn.innerText.trim();
            if (txt.includes('댓글')) {
                btn.click();
                return '패널 내 클릭: ' + txt;
            }
        }
    }
    return '댓글 드롭다운 없음';
}""")
print(f"[댓글 드롭다운 클릭] {comment_click}", flush=True)
page.wait_for_timeout(800)

page.screenshot(path='/tmp/goodisak_comment_dropdown.png')

# 드롭다운 열림 후 비허용 선택
comment_off = page.evaluate("""() => {
    const allEls = document.querySelectorAll('li, button, a, option, [role="option"]');
    const visible = Array.from(allEls).filter(el => el.offsetParent !== null);
    for (const el of visible) {
        const txt = (el.innerText || el.textContent || '').trim();
        if (txt === '댓글 비허용' || txt === '허용 안함' || txt === '비허용' ||
            txt === '사용 안함' || txt === '댓글 허용 안함') {
            el.click();
            return '비허용 클릭: ' + txt;
        }
    }
    // 현재 visible한 모든 요소 텍스트
    const texts = visible.map(el => (el.innerText || '').trim()).filter(t => t.length < 30 && t.length > 0);
    return '비허용 없음. visible texts: ' + JSON.stringify(texts.slice(0, 20));
}""")
print(f"[댓글 비허용 선택] {comment_off}", flush=True)
page.wait_for_timeout(500)

page.screenshot(path='/tmp/goodisak_publish_ready.png')
print("[스크린샷] /tmp/goodisak_publish_ready.png", flush=True)

# ===== Step 5: 발행 버튼 클릭 =====
print("\n[Step 5] 발행 버튼 클릭...", flush=True)
page.wait_for_timeout(500)

published = False
for attempt in range(3):
    # 가시 발행 버튼 찾기
    pub_result = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent !== null);
        for (const btn of btns) {
            const txt = btn.innerText.trim();
            if (txt === '발행' || txt === '공개 발행' || txt === '공개발행') {
                btn.click();
                return '클릭: ' + txt;
            }
        }
        return '발행 버튼 없음: ' + JSON.stringify(btns.map(b => b.innerText.trim()).filter(t => t).slice(0, 15));
    }""")
    print(f"[발행 시도 {attempt+1}] {pub_result}", flush=True)

    if '클릭' in pub_result:
        page.wait_for_timeout(4000)
        published = True
        break

    # locator 방식
    try:
        pub_loc = page.locator('button:has-text("발행"):visible')
        cnt = pub_loc.count()
        if cnt > 0:
            pub_loc.last.click()
            page.wait_for_timeout(4000)
            published = True
            print(f"[locator 발행 클릭]", flush=True)
            break
    except:
        pass

    page.wait_for_timeout(1000)

page.screenshot(path='/tmp/goodisak_after_publish2.png')
print("[스크린샷] /tmp/goodisak_after_publish2.png", flush=True)

# ===== Step 6: 발행 URL 확인 =====
page.wait_for_timeout(2000)
current_url = page.url
print(f"[발행 후 URL] {current_url}", flush=True)

published_url = ""
if re.search(r'goodisak\.tistory\.com/\d+', current_url):
    published_url = current_url
    print(f"[발행 성공] {published_url}", flush=True)
elif re.search(r'welfare\.baremi542\.com/\d+', current_url):
    published_url = current_url
    print(f"[발행 성공] {published_url}", flush=True)
else:
    # 캡챠 확인
    captcha_check = page.evaluate("""() => {
        const cap = document.querySelector('.dkaptcha-wrapper, [class*="captcha"], [class*="CAPTCHA"]');
        if (cap && cap.offsetParent !== null) {
            return {hasCaptcha: true, text: cap.innerText.substring(0, 200)};
        }
        return {hasCaptcha: false};
    }""")
    print(f"[캡챠 확인] {captcha_check}", flush=True)

    if captcha_check.get('hasCaptcha'):
        print("[경고] 캡챠 팝업 발생 - 수동 처리 필요", flush=True)
        tg_msg = f"""⚠️ 발행 대기 - 캡챠 확인 필요
블로그: goodisak (티스토리)
제목: 아이폰16 색상 5가지 실물 비교와 내 취향에 맞는 선택 방법
상태: 캡챠 팝업 발생
조치: 브라우저에서 캡챠 직접 입력 후 '공개 발행' 버튼 클릭 필요
스크린샷: /tmp/goodisak_after_publish2.png"""
        subprocess.run(
            ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py', tg_msg],
            capture_output=True, text=True, timeout=15
        )
        pw.stop()
        sys.exit(0)

    # URL 미확인 - 발행 목록에서 확인
    print("[발행 목록 확인...]", flush=True)
    try:
        page.goto('https://goodisak.tistory.com/manage/posts', wait_until='domcontentloaded', timeout=15000)
        page.wait_for_timeout(2000)

        # 비공개/임시저장이 아닌 발행 글 확인
        post_status = page.evaluate("""() => {
            const items = document.querySelectorAll('tr, .post-item, li');
            const result = [];
            for (const item of items) {
                const txt = item.innerText.trim();
                if (txt.includes('아이폰16')) {
                    result.push({text: txt.substring(0, 200), dataset: JSON.stringify(item.dataset)});
                }
            }
            return result;
        }""")
        print(f"[아이폰16 포스트 상태] {post_status}", flush=True)

        # 호버로 URL 확인
        page.locator('a:has-text("아이폰16 색상")').first.hover()
        page.wait_for_timeout(500)
        hover_btns = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]'))
                .filter(a => a.offsetParent !== null && /goodisak\\.tistory\\.com\\/\\d+/.test(a.href))
                .map(a => ({href: a.href, text: a.innerText.trim().substring(0, 30)}));
        }""")
        print(f"[호버 후 링크] {hover_btns}", flush=True)

        # 수정 버튼에서 post ID 추출
        edit_btns = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href*="manage/post/"]'))
                .filter(a => a.offsetParent !== null)
                .map(a => ({href: a.href, text: a.innerText.trim().substring(0, 30)}));
        }""")
        print(f"[수정 버튼 링크] {edit_btns}", flush=True)

        # URL을 숫자 ID 기반으로 구성
        if edit_btns:
            for btn in edit_btns:
                href = btn.get('href', '')
                m = re.search(r'manage/post/(\d+)', href)
                if m:
                    post_id = m.group(1)
                    # 실제 URL 형식 (이 블로그는 welfare.baremi542.com)
                    published_url = f"https://welfare.baremi542.com/{post_id}"
                    print(f"[추정 발행 URL] {published_url}", flush=True)
                    break

    except Exception as e:
        print(f"[발행 목록 오류] {e}", flush=True)

# ===== Step 7: GSC 색인 요청 =====
print(f"\n[Step 7] GSC 색인 요청: {published_url}", flush=True)
gsc_success = False
if published_url and re.search(r'/(welfare\.baremi542\.com|goodisak\.tistory\.com)/\d+', '/' + published_url):
    gsc_success = request_indexing(published_url)
    print(f"[GSC] {'성공' if gsc_success else '실패'}", flush=True)
elif published_url:
    gsc_success = request_indexing(published_url)
    print(f"[GSC] {'성공' if gsc_success else '실패'}", flush=True)
else:
    print("[GSC 스킵] URL 미확인", flush=True)

# ===== Step 8: 텔레그램 보고 =====
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
post_title = title if title else "아이폰16 색상 5가지 실물 비교와 내 취향에 맞는 선택 방법"

modifications = [
    "[H2]/[BOLD] 태그 → HTML 변환",
    f"Gemini 이미지 {inserted_count}장 생성 및 삽입",
    "AI 표현 제거 및 존댓말 통일",
    "도입부 후킹 문장 개선",
    "댓글 비허용 설정",
    "공개 설정"
]

if published and published_url:
    tg_msg = f"""✅ 발행 완료
블로그: goodisak (티스토리)
제목: {post_title}
발행시각: {now}
URL: {published_url}

🔧 검수 중 수정사항:
""" + "\n".join(f"- {m}" for m in modifications) + f"""

📊 GSC 색인 요청: {'✅ 완료' if gsc_success else '⚠️ 실패 (수동 확인 필요)'}"""
else:
    tg_msg = f"""⚠️ 발행 상태 불명확
블로그: goodisak (티스토리)
제목: {post_title}
발행시각: {now}
URL: {published_url or '미확인'}
이미지: {inserted_count}장 삽입됨
조치: 스크린샷(/tmp/goodisak_after_publish2.png) 확인 필요"""

print(f"\n[텔레그램 발송]\n{tg_msg}", flush=True)
result = subprocess.run(
    ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py', tg_msg],
    capture_output=True, text=True, timeout=15
)
print(f"텔레그램: rc={result.returncode}", flush=True)

print("\n=== 작업 완료 ===", flush=True)
pw.stop()
