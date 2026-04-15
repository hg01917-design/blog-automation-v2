"""phn0502 웨이브 추천영화 키워드 밀도 수정 + 발행"""
import sys, time, re, random
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp, get_or_create_page
import publish_drafts as _pd

def log(msg):
    print(msg, flush=True)

REPLACEMENTS = ["이 플랫폼", "해당 서비스", "스트리밍 서비스", "동영상 플랫폼", "OTT 서비스"]

def fix_keyword_density(content, keyword="웨이브", target_pct=3.5):
    plain = re.sub(r'<[^>]+>', '', content)
    total_words = len(plain.split())
    kw_count = sum(1 for w in plain.split() if keyword in w)
    density = (kw_count / total_words * 100) if total_words > 0 else 0
    log(f"수정 전: '{keyword}' {kw_count}회/{total_words}단어 = {density:.1f}%")

    if density <= 4.0:
        log("키워드 밀도 OK — 수정 불필요")
        return content, density

    target_count = int(total_words * target_pct / 100)
    remove_count = max(0, kw_count - target_count)
    log(f"제거 목표: {remove_count}개 (목표 ~{target_count}회, {target_pct}%)")

    fixed = content
    removed = 0
    first_idx = fixed.find(keyword)
    for _ in range(remove_count):
        idx = fixed.rfind(keyword)
        if idx < 0 or idx == first_idx:
            break
        repl = random.choice(REPLACEMENTS)
        fixed = fixed[:idx] + repl + fixed[idx+len(keyword):]
        removed += 1

    new_plain = re.sub(r'<[^>]+>', '', fixed)
    new_words = len(new_plain.split())
    new_count = sum(1 for w in new_plain.split() if keyword in w)
    new_density = (new_count / new_words * 100) if new_words > 0 else 0
    log(f"수정 후: '{keyword}' {new_count}회/{new_words}단어 = {new_density:.1f}% (제거 {removed}개)")
    return fixed, new_density


log("=== phn0502 웨이브 추천영화 수정 시작 ===")
pw, browser = connect_cdp(on_log=log)
ctx = browser.contexts[0]

# 기존 탭 중 tistory 탭 찾기 (또는 첫 번째 탭 사용)
page = None
for p in ctx.pages:
    if 'tistory.com' in p.url:
        page = p
        break
if not page:
    page = ctx.pages[0]

log(f"사용 탭: {page.url}")

# beforeunload 무력화
try:
    page.evaluate("window.onbeforeunload = null")
except Exception:
    pass

# ── 1단계: phn0502 manage 접근 ──
log("=== Step 1: phn0502 manage 이동 ===")
page.goto("https://phn0502.tistory.com/manage", wait_until="domcontentloaded", timeout=30000)
time.sleep(3)
log(f"현재 URL: {page.url}")

# ── 2단계: 로그인 처리 ──
if "/manage" not in page.url:
    log("=== Step 2: 로그인 필요 — 로그아웃 후 재시도 ===")
    # 현재 세션 로그아웃
    try:
        page.evaluate("window.onbeforeunload = null")
    except Exception:
        pass
    page.goto("https://www.tistory.com/auth/logout", wait_until="domcontentloaded", timeout=15000)
    time.sleep(2)
    log(f"로그아웃 후 URL: {page.url}")

    # 로그인 페이지 이동
    page.goto("https://www.tistory.com/auth/login", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    log(f"로그인 페이지: {page.url}")

    # 카카오 버튼 클릭
    try:
        kakao_btn = page.locator('a.btn_login.link_kakao_id, a[class*="kakao"]').first
        kakao_btn.click(timeout=10000)
        time.sleep(4)
        log(f"카카오 클릭 후: {page.url}")
    except Exception as e:
        log(f"카카오 버튼 클릭 실패: {e}")
        pw.stop()
        sys.exit(1)

    # 계정 선택 (baremi542)
    try:
        acc = page.locator('a.wrap_profile:has-text("baremi542")').first
        acc.wait_for(state="visible", timeout=10000)
        acc.click()
        time.sleep(4)
        log(f"baremi542 계정 선택 후: {page.url}")
    except Exception as e:
        log(f"계정 선택 실패 (이미 baremi542 로그인 상태일 수 있음): {e}")

    # 동의 버튼
    try:
        agree = page.locator('button:has-text("동의하고 계속하기"), button:has-text("확인")').first
        if agree.is_visible(timeout=3000):
            agree.click()
            time.sleep(2)
    except Exception:
        pass

    # 로그인 완료 대기
    for i in range(30):
        url = page.url
        log(f"로그인 대기 {i+1}/30: {url[:60]}")
        if "tistory.com" in url and "auth/login" not in url and "kakao" not in url:
            log("Tistory 로그인 완료!")
            break
        time.sleep(1)
    else:
        log(f"로그인 실패 — URL: {page.url}")
        pw.stop()
        sys.exit(1)

    # manage 재이동
    page.goto("https://phn0502.tistory.com/manage", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    log(f"manage 이동 후: {page.url}")

    if "/manage" not in page.url:
        log("manage 접근 실패")
        pw.stop()
        sys.exit(1)

log("=== Step 3: 에디터 이동 ===")
try:
    page.evaluate("window.onbeforeunload = null")
except Exception:
    pass
page.goto("https://phn0502.tistory.com/manage/newpost/", wait_until="domcontentloaded", timeout=30000)
time.sleep(4)
log(f"에디터 URL: {page.url}")

# 임시저장 버튼 클릭
log("=== Step 4: 임시저장 드래프트 로드 ===")
count_btn = page.query_selector('a.count[aria-label*="임시저장"]')
if not count_btn:
    log("임시저장 버튼 없음 — 임시저장 글 없음")
    pw.stop()
    sys.exit(1)
count_btn.click()
time.sleep(2)

# 드래프트 목록에서 첫 번째 글 클릭 (a.link_info 셀렉터)
draft_links = page.query_selector_all('a.link_info')
log(f"드래프트 개수: {len(draft_links)}")
if not draft_links:
    log("드래프트 없음 — 임시저장 글이 없거나 이미 발행됨")
    pw.stop()
    sys.exit(1)

# 첫 번째 항목의 제목 확인
first_link = draft_links[0]
draft_title_text = (first_link.text_content() or '').strip()
log(f"드래프트 제목: {draft_title_text}")
first_link.click()
time.sleep(4)

# TinyMCE 로드 대기
log("=== Step 5: TinyMCE 로드 대기 ===")
for i in range(30):
    try:
        has_tinymce = page.evaluate("() => typeof tinymce !== 'undefined' && tinymce.activeEditor !== null")
        if has_tinymce:
            log(f"TinyMCE 로드됨 ({i+1}회 시도)")
            break
    except Exception:
        pass
    time.sleep(1)
else:
    log("TinyMCE 로드 실패")
    pw.stop()
    sys.exit(1)

# 콘텐츠 가져오기
content = page.evaluate("() => tinymce.activeEditor.getContent()")
title_el = page.query_selector('#post-title-inp') or page.query_selector('#title')
title = title_el.input_value().strip() if title_el else "웨이브 추천영화"
log(f"제목: {title}")
log(f"콘텐츠 길이: {len(content)}자")

# ── 키워드 밀도 수정 ──
log("=== Step 6: 키워드 밀도 수정 ===")
fixed_content, new_density = fix_keyword_density(content, "웨이브")

if fixed_content != content:
    page.evaluate("(c) => tinymce.activeEditor.setContent(c)", fixed_content)
    log("콘텐츠 업데이트 완료")
    time.sleep(2)

# ── 발행 (_tistory_publish_private 사용) ──
log("=== Step 7: 발행 시작 ===")
ok = _pd._tistory_publish_private(page, "phn0502")
log(f"발행 결과: {ok}")

log(f"최종 URL: {page.url}")
log("=== 완료 ===")
pw.stop()
