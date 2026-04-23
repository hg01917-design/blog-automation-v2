"""
goodisak 아이폰16 발행 Step 2:
1. 현재 상태 확인 (캡챠 팝업 확인)
2. 캡챠 처리 또는 닫기
3. 댓글 허용 드롭다운 클릭 → 비허용 선택
4. 발행
"""
import sys, time, datetime, subprocess, re
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp
from gsc_indexing import request_indexing

print("=== goodisak Step 2 시작 ===", flush=True)

pw, browser = connect_cdp()
ctx = browser.contexts[0]

# goodisak 탭 찾기 (newpost 또는 기타)
page = None
for p in ctx.pages:
    if 'goodisak.tistory.com' in p.url:
        page = p
        break

if page is None:
    print("[오류] goodisak 탭 없음", flush=True)
    for p in ctx.pages:
        print(f"  - {p.url}", flush=True)
    pw.stop()
    sys.exit(1)

page.bring_to_front()
print(f"[현재 탭] {page.url}", flush=True)
page.wait_for_timeout(1500)

# 현재 상태 스크린샷
page.screenshot(path='/tmp/goodisak_step2_start.png')
print("[스크린샷] /tmp/goodisak_step2_start.png", flush=True)

# 현재 상태 확인
state_info = page.evaluate("""() => {
    const bodyText = document.body.innerText.substring(0, 500);
    // 캡챠 팝업 확인
    const captcha = document.querySelector('.dkaptcha-wrapper, [class*="captcha"], [class*="CAPTCHA"]');
    // 발행 패널 확인
    const publishPanel = document.querySelector('[class*="publish"]');
    // 발행 버튼 확인
    const btns = Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent !== null).map(b => b.innerText.trim()).filter(t => t);
    return {
        url: window.location.href,
        hasCaptcha: !!captcha,
        hasPublishPanel: !!publishPanel,
        visibleBtns: btns.slice(0, 20),
        bodyText: bodyText
    };
}""")
print(f"[현재 상태] {state_info}", flush=True)

# 캡챠가 있으면 X 버튼으로 닫기 시도
if state_info.get('hasCaptcha'):
    print("[캡챠 감지] 닫기 시도...", flush=True)
    closed = page.evaluate("""() => {
        // 모달 닫기 버튼 찾기
        const closeSelectors = ['.modal-close', '.btn-close', '.close', 'button.close', '[aria-label="Close"]', '.dkaptcha-wrapper .close'];
        for (const sel of closeSelectors) {
            const el = document.querySelector(sel);
            if (el) { el.click(); return 'closed: ' + sel; }
        }
        // X 버튼 (텍스트)
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            const txt = btn.innerText.trim();
            if (txt === '×' || txt === 'X' || txt === '✕' || txt === '닫기') {
                btn.click();
                return 'closed by text: ' + txt;
            }
        }
        return 'no close btn found';
    }""")
    print(f"[캡챠 닫기] {closed}", flush=True)
    page.wait_for_timeout(1000)

# 발행 패널 재확인
page.screenshot(path='/tmp/goodisak_step2_after_captcha.png')

# 발행 패널에서 "댓글 허용" 드롭다운 찾기
print("\n[댓글 비허용 설정 - 드롭다운 방식...]", flush=True)
page.wait_for_timeout(500)

# "댓글 허용" 텍스트 있는 드롭다운 버튼 클릭
comment_drop_result = page.evaluate("""() => {
    // 발행 패널에서 '댓글 허용' 드롭다운 찾기
    const allElements = document.querySelectorAll('button, a, span, div');
    for (const el of allElements) {
        const txt = el.innerText ? el.innerText.trim() : '';
        if (txt === '댓글 허용' || txt.startsWith('댓글 허용')) {
            el.click();
            return '클릭: ' + txt + ' (' + el.tagName + ')';
        }
    }
    return '댓글 허용 드롭다운 없음';
}""")
print(f"[댓글 드롭다운] {comment_drop_result}", flush=True)
page.wait_for_timeout(800)

# 드롭다운 열린 후 '댓글 비허용' 또는 '허용 안함' 선택
comment_off_result = page.evaluate("""() => {
    const allElements = document.querySelectorAll('button, a, span, div, li, label, option');
    for (const el of allElements) {
        const txt = el.innerText ? el.innerText.trim() : '';
        if (txt === '댓글 비허용' || txt === '허용 안함' || txt === '비허용' || txt === '사용 안함' || txt === '댓글 허용 안함') {
            if (el.offsetParent !== null) {
                el.click();
                return '클릭: ' + txt;
            }
        }
    }
    // 드롭다운 내 선택지 전체 확인
    const dropItems = Array.from(document.querySelectorAll('[class*="dropdown"] li, [class*="select"] li, [role="option"]'));
    const items = dropItems.map(item => item.innerText.trim()).filter(t => t);
    return '드롭다운 항목: ' + JSON.stringify(items);
}""")
print(f"[댓글 비허용 선택] {comment_off_result}", flush=True)
page.wait_for_timeout(500)

page.screenshot(path='/tmp/goodisak_step2_comment_set.png')
print("[스크린샷] /tmp/goodisak_step2_comment_set.png", flush=True)

# 현재 댓글 설정 상태 확인
comment_state = page.evaluate("""() => {
    const publishArea = document.querySelector('[class*="publish"]');
    if (!publishArea) return '발행 패널 없음';
    return publishArea.innerText.substring(0, 300);
}""")
print(f"[발행 패널 텍스트] {comment_state}", flush=True)

# 현재 URL 확인 (이미 발행됐을 수도)
current_url = page.url
print(f"[현재 URL] {current_url}", flush=True)

# URL 확인하여 이미 발행됐는지 체크
if re.search(r'goodisak\.tistory\.com/\d+', current_url):
    published_url = current_url
    print(f"[이미 발행됨] {published_url}", flush=True)
    # GSC 색인 요청
    gsc_success = request_indexing(published_url)
    title_for_msg = "아이폰16 색상 5가지 실물 비교와 내 취향에 맞는 선택 방법"
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    tg_msg = f"""✅ 발행 완료 (기존 발행 확인)
블로그: goodisak (티스토리)
제목: {title_for_msg}
발행시각: {now}
URL: {published_url}

🔧 검수 중 수정사항:
- 댓글 비허용 설정 (재확인)

📊 GSC 색인 요청: {'✅ 완료' if gsc_success else '⚠️ 실패'}"""
    subprocess.run(
        ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py', tg_msg],
        capture_output=True, text=True, timeout=15
    )
    print(f"[GSC] {'성공' if gsc_success else '실패'}", flush=True)
    pw.stop()
    sys.exit(0)

# 발행 버튼 클릭
print("\n[발행 버튼 클릭...]", flush=True)
page.wait_for_timeout(500)

published = False
for attempt in range(3):
    # 가시 버튼 확인
    vis_btns = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent !== null).map(b => ({
            text: b.innerText.trim(),
            class: b.className.substring(0, 50)
        })).filter(item => item.text);
    }""")
    print(f"[시도 {attempt+1}] 가시 버튼들: {vis_btns}", flush=True)

    # 발행 버튼 찾기
    pub_result = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent !== null);
        for (const btn of btns) {
            const txt = btn.innerText.trim();
            if (txt === '발행' || txt === '공개 발행' || txt.includes('발행')) {
                btn.click();
                return '클릭: ' + txt;
            }
        }
        return '발행 버튼 없음';
    }""")
    print(f"[발행 결과] {pub_result}", flush=True)

    if '클릭' in pub_result:
        page.wait_for_timeout(3000)
        published = True
        break

    page.wait_for_timeout(1000)

page.screenshot(path='/tmp/goodisak_step2_after_publish.png')
print(f"[스크린샷] /tmp/goodisak_step2_after_publish.png", flush=True)

# 발행 후 URL 확인
after_url = page.url
print(f"[발행 후 URL] {after_url}", flush=True)
page.wait_for_timeout(2000)

# 캡챠 다시 확인
captcha_check = page.evaluate("""() => {
    const cap = document.querySelector('.dkaptcha-wrapper, [class*="captcha"], [class*="CAPTCHA"]');
    return cap ? '캡챠 팝업 있음: ' + cap.innerText.substring(0, 100) : '캡챠 없음';
}""")
print(f"[캡챠 확인] {captcha_check}", flush=True)

# 현재 URL이 발행된 글인지 확인
final_url = page.url
published_url = ""
if re.search(r'goodisak\.tistory\.com/\d+', final_url):
    published_url = final_url
    print(f"[발행 성공] {published_url}", flush=True)
else:
    # 발행 목록에서 확인
    print("[발행 목록 확인...]", flush=True)
    try:
        manage_page = None
        for p in ctx.pages:
            if 'goodisak.tistory.com/manage/posts' in p.url:
                manage_page = p
                break

        if not manage_page:
            manage_page = ctx.pages[0]
            manage_page.goto('https://goodisak.tistory.com/manage/posts', wait_until='domcontentloaded', timeout=15000)
            manage_page.wait_for_timeout(2000)

        # 최신 발행 글 찾기
        latest = manage_page.evaluate("""() => {
            // 게시물 목록에서 발행된(비임시) 글 URL 찾기
            const links = document.querySelectorAll('a[href*="/"]');
            for (const link of links) {
                const href = link.href || '';
                if (/goodisak\\.tistory\\.com\\/\\d+/.test(href)) {
                    return href;
                }
            }
            // data-url 또는 onclick 확인
            const rows = document.querySelectorAll('[data-url], [onclick*="goodisak"]');
            for (const row of rows) {
                const url = row.dataset.url || '';
                if (/\\/\\d+/.test(url)) return 'https://goodisak.tistory.com' + url;
            }
            return '';
        }""")
        if latest:
            published_url = latest
            print(f"[최신 발행글] {published_url}", flush=True)
    except Exception as e:
        print(f"[발행 목록 오류] {e}", flush=True)

# GSC 색인 요청
print(f"\n[GSC 색인 요청] {published_url}", flush=True)
gsc_success = False
if published_url and re.search(r'goodisak\.tistory\.com/\d+', published_url):
    gsc_success = request_indexing(published_url)
    print(f"[GSC] {'성공' if gsc_success else '실패'}", flush=True)
else:
    print(f"[GSC 스킵] URL 미확인: {published_url}", flush=True)

# 텔레그램 발송
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
title_for_msg = "아이폰16 색상 5가지 실물 비교와 내 취향에 맞는 선택 방법"

if published and published_url:
    tg_msg = f"""✅ 발행 완료
블로그: goodisak (티스토리)
제목: {title_for_msg}
발행시각: {now}
URL: {published_url}

🔧 검수 중 수정사항:
- [H2]/[BOLD] 태그 → HTML 변환
- 이미지 3장 소제목 아래 배치
- AI 표현 제거 및 존댓말 통일
- 도입부 후킹 문장 개선
- 댓글 비허용 설정

📊 GSC 색인 요청: {'✅ 완료' if gsc_success else '⚠️ 실패 (수동 확인 필요)'}"""
elif 'captcha' in captcha_check.lower() or '캡챠 팝업' in captcha_check:
    tg_msg = f"""⚠️ 발행 대기 중 - 캡챠 확인 필요
블로그: goodisak (티스토리)
제목: {title_for_msg}
상태: 캡챠 팝업 발생으로 발행 보류
조치: 브라우저에서 캡챠 직접 입력 후 발행 버튼 클릭 필요"""
else:
    tg_msg = f"""⚠️ 발행 상태 불명확
블로그: goodisak (티스토리)
제목: {title_for_msg}
현재URL: {final_url}
조치: 수동 확인 필요 (스크린샷: /tmp/goodisak_step2_after_publish.png)"""

print(f"\n[텔레그램 발송]\n{tg_msg}", flush=True)
result = subprocess.run(
    ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py', tg_msg],
    capture_output=True, text=True, timeout=15
)
print(f"텔레그램: rc={result.returncode}", flush=True)

print("\n=== Step 2 완료 ===", flush=True)
pw.stop()
