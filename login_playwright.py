"""블로그 로그인/로그아웃 자동화 — CDP + Playwright (완전 자동, 사람 개입 없음)"""
import time
import random
from browser import connect_cdp, get_or_create_page
from config import ACCOUNT_MAP

TISTORY_URL = "https://www.tistory.com"
TISTORY_LOGIN_URL = "https://www.tistory.com/auth/login"
NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"


def _rand_delay(page, min_ms=500, max_ms=1500):
    """사람처럼 랜덤 딜레이"""
    page.wait_for_timeout(random.randint(min_ms, max_ms))


def login_tistory(blog_id: str, on_log=None):
    """티스토리 카카오 로그인 — 완전 자동"""
    def log(msg):
        if on_log:
            on_log(msg)

    config = ACCOUNT_MAP.get(blog_id)
    if not config:
        raise ValueError(f"알 수 없는 블로그: {blog_id}")

    blog_url = f"https://{blog_id}.tistory.com/manage"
    pw, browser = connect_cdp(on_log)
    page = None

    try:
        # 기존 tistory/kakao 탭 정리
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        for p in context.pages:
            if "tistory.com" in p.url or "accounts.kakao" in p.url:
                try:
                    p.close()
                except Exception:
                    pass

        # ── 1단계: /auth/login 직접 이동 (새 탭) ──
        log("[1/5] 티스토리 로그인 페이지 이동 중...")
        page = context.new_page()
        page.goto(TISTORY_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        _rand_delay(page, 2000, 3000)

        # 이미 로그인 상태면 메인으로 리다이렉트됨
        if "auth/login" not in page.url and "accounts.kakao" not in page.url:
            log(f"[1/5] 로그인 리다이렉트됨 ({page.url}) — {blog_id} manage 진입 시도...")
            page.goto(blog_url, wait_until="domcontentloaded", timeout=30000)
            _rand_delay(page, 2000, 3000)
            # manage 페이지에 도달했는지 확인 (홈으로 리다이렉트 = 다른 계정 로그인 중)
            if "/manage" in page.url:
                log(f"[완료] {blog_id} manage 진입 완료! ({page.url})")
                return True
            else:
                log(f"[1/5] manage 접근 불가 ({page.url}) — Tistory 세션 초기화 후 재로그인")
                # Tistory 세션 강제 클리어 (logout URL 직접 이동)
                page.goto("https://www.tistory.com/auth/logout", wait_until="domcontentloaded", timeout=15000)
                _rand_delay(page, 2000, 3000)
                log(f"[1/5] Tistory 로그아웃 완료 ({page.url})")
                page.goto(TISTORY_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
                _rand_delay(page, 2000, 3000)
                log(f"[1/5] auth/login 재이동: {page.url}")

        log(f"[1/5] 현재 URL: {page.url}")

        # ── 2단계: "카카오계정으로 로그인" 버튼 클릭 ──
        if "auth/login" in page.url:
            log("[2/5] '카카오계정으로 로그인' 버튼 클릭...")
            kakao_btn = page.locator('a.btn_login.link_kakao_id')
            if kakao_btn.count() == 0:
                kakao_btn = page.locator('a[class*="kakao"]')
            kakao_btn.first.click(timeout=10000)
            _rand_delay(page, 3000, 5000)
            log(f"[2/5] 카카오 페이지 이동됨 ({page.url})")

        # 카카오 세션으로 자동 리다이렉트되어 tistory로 돌아왔는지 확인
        if "tistory.com" in page.url and "auth/login" not in page.url and "accounts.kakao" not in page.url:
            # manage 페이지 접근 가능한지 확인
            page.goto(blog_url, wait_until="domcontentloaded", timeout=30000)
            _rand_delay(page, 2000, 3000)
            if "/manage" in page.url:
                log(f"[완료] 카카오 세션으로 로그인 — {blog_id} manage 진입 완료!")
                return True
            else:
                log(f"[2/5] 자동 로그인 계정이 {blog_id} 관리자 아님 — Kakao 계정 전환 시도")
                # Tistory 로그아웃 후 재시도
                page.goto("https://www.tistory.com/auth/logout", wait_until="domcontentloaded", timeout=15000)
                _rand_delay(page, 2000, 3000)
                page.goto(TISTORY_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
                _rand_delay(page, 2000, 3000)
                if "auth/login" in page.url:
                    kakao_btn2 = page.locator('a.btn_login.link_kakao_id, a[class*="kakao"]').first
                    kakao_btn2.click(timeout=10000)
                    _rand_delay(page, 3000, 5000)
                    log(f"[2/5] 재시도 후 카카오 페이지: {page.url}")

        # ── 3단계: 카카오 계정 선택 (간편로그인 화면) ──
        kakao_id = config["kakao_id"]
        log(f"[3/5] 카카오 계정 선택 중: {kakao_id}...")

        # "다른 계정으로 로그인" 링크 클릭 (이미 다른 계정으로 자동로그인 방지)
        try:
            other_acc = page.locator(
                'a:has-text("다른 계정으로 로그인"), button:has-text("다른 계정으로 로그인"), '
                'a:has-text("계정 전환"), a:has-text("Switch account")'
            ).first
            if other_acc.is_visible(timeout=3000):
                log(f"[3/5] 다른 계정으로 로그인 클릭...")
                other_acc.click()
                _rand_delay(page, 2000, 3000)
        except Exception:
            pass

        # a.wrap_profile 안에 이메일/계정명이 포함된 항목 클릭
        account_clicked = False
        try:
            account_link = page.locator(f'a.wrap_profile:has-text("{kakao_id}")').first
            account_link.wait_for(state="visible", timeout=10000)
            log(f"[3/5] 계정 발견 — 클릭: {kakao_id}")
            account_link.click()
            account_clicked = True
            _rand_delay(page, 3000, 5000)
        except Exception:
            log(f"[3/5] 간편로그인 목록에 {kakao_id} 없음")

        # 간편로그인 없으면 ID/PW 입력 방식
        if not account_clicked:
            try:
                id_input = page.locator("input[name='loginId']")
                if id_input.is_visible(timeout=3000):
                    id_input.click()
                    _rand_delay(page, 1000, 2000)
                    current_val = id_input.input_value()
                    log(f"[3/5] 입력창 값: {current_val or '(비어있음)'}")

                    pw_input = page.locator("input[name='password']")
                    if pw_input.is_visible(timeout=3000):
                        pw_input.click()
                        _rand_delay(page, 500, 1000)

                    submit_btn = page.locator("button.submit, button[type='submit']").first
                    submit_btn.click()
                    _rand_delay(page, 3000, 5000)
            except Exception:
                pass

        # 동의 화면 처리
        try:
            agree_btn = page.locator(
                'button:has-text("동의하고 계속하기"), '
                'button:has-text("확인")'
            ).first
            if agree_btn.is_visible(timeout=3000):
                log("[3/5] 동의 버튼 클릭...")
                agree_btn.click()
                _rand_delay(page, 2000, 3000)
        except Exception:
            pass

        # ── 4단계: 로그인 완료 대기 ──
        log("[4/5] 티스토리 리다이렉트 대기 중...")
        logged_in = False
        for i in range(30):
            current_url = page.url
            if "tistory.com" in current_url and "auth/login" not in current_url and "kakao" not in current_url:
                log(f"[4/5] 티스토리 로그인 성공!")
                logged_in = True
                break
            _rand_delay(page, 800, 1200)

        if not logged_in:
            log(f"[실패] 로그인 미완료 — 현재 URL: {page.url}")
            return False

        # ── 5단계: 해당 블로그로 이동 ──
        log(f"[5/5] {blog_id} 블로그로 이동 중...")
        page.goto(blog_url, wait_until="domcontentloaded", timeout=30000)
        _rand_delay(page, 2000, 3000)
        if "/manage" in page.url:
            log(f"[완료] {blog_id} 블로그 진입 완료! ({page.url})")
            return True
        else:
            log(f"[실패] {blog_id} manage 진입 실패 — URL: {page.url} (계정 불일치 또는 세션 오류)")
            return False

    finally:
        try:
            if page:
                page.close()
        except Exception:
            pass
        pw.stop()


def login_naver(naver_id=None, on_log=None, page=None):
    """네이버 로그인 — Chrome 저장된 계정 자동완성 활용

    naver_id: 로그인할 네이버 ID. 자동완성 계정과 다를 경우 교체.
    page: 기존 Playwright page 객체. 전달 시 새 세션 생성 없이 재사용.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    # 기존 page가 전달된 경우: 새 Playwright 세션 없이 재사용
    _owns_session = page is None
    pw = None
    if _owns_session:
        pw, browser = connect_cdp(on_log)
        page = get_or_create_page(browser, navigate_to=NAVER_LOGIN_URL)
    else:
        page.goto(NAVER_LOGIN_URL, wait_until='domcontentloaded', timeout=15000)

    try:
        log("[1/4] 네이버 로그인 페이지 접속 중...")
        _rand_delay(page, 2000, 3000)

        if "nidlogin" not in page.url:
            log(f"[완료] 이미 네이버 로그인 상태 ({page.url})")
            return True

        log(f"[1/4] 로그인 페이지 로드됨 ({page.url})")

        log("[2/4] 자동완성 계정 확인 중...")
        id_input = page.locator('#id')
        id_input.wait_for(state="visible", timeout=10000)
        id_input.click()
        _rand_delay(page, 1000, 2000)
        current_id = id_input.input_value()

        if current_id:
            log(f"[2/4] 자동완성된 계정: {current_id}")
        else:
            log("[2/4] 자동완성 계정 없음")

        # 기대 계정과 다를 경우 — 저장된 계정 목록에서 선택 시도
        if naver_id and current_id != naver_id:
            log(f"[2/4] ⚠ 계정 불일치: 자동완성={current_id}, 필요={naver_id} — 계정 목록에서 선택 시도")
            selected = False

            # 저장된 계정 목록 드롭다운 탐색 (여러 셀렉터 시도)
            for selector in [
                f'.account_list [data-id="{naver_id}"]',
                f'.account_list a[title="{naver_id}"]',
                f'#savedAccountList [data-id="{naver_id}"]',
                f'ul.account_list li a',
            ]:
                items = page.locator(selector)
                try:
                    count = items.count()
                except Exception:
                    continue

                if selector.endswith('li a'):
                    # 텍스트로 매칭
                    for i in range(count):
                        item = items.nth(i)
                        try:
                            text = item.inner_text(timeout=1000).strip()
                            if naver_id in text:
                                item.click(timeout=3000)
                                log(f"[2/4] 계정 목록에서 '{naver_id}' 선택 완료")
                                selected = True
                                _rand_delay(page, 800, 1200)
                                break
                        except Exception:
                            continue
                elif count > 0:
                    items.first.click(timeout=3000)
                    log(f"[2/4] 계정 목록에서 '{naver_id}' 선택 완료")
                    selected = True
                    _rand_delay(page, 800, 1200)

                if selected:
                    break

            if not selected:
                log(f"[2/4] 계정 목록에서 찾지 못함 — ID 필드 직접 입력")
                id_input.click(click_count=3)
                _rand_delay(page, 300, 500)
                id_input.fill("")
                _rand_delay(page, 100, 200)
                id_input.type(naver_id, delay=random.randint(60, 120))
                _rand_delay(page, 500, 800)

        log("[3/5] 비밀번호 자동완성 트리거...")
        pw_input = page.locator('#pw')
        if pw_input.is_visible(timeout=3000):
            pw_input.click()
            _rand_delay(page, 800, 1200)

        log("[3/5] 로그인 버튼 클릭...")
        login_btn = page.locator('#log\\.login, button.btn_login, button[type="submit"]').first
        login_btn.click(timeout=5000)
        _rand_delay(page, 3000, 5000)

        log("[4/4] 로그인 완료 대기 중...")
        for i in range(20):
            current_url = page.url
            if "nidlogin" not in current_url and "naver.com" in current_url:
                log(f"[완료] 네이버 로그인 성공! ({current_url})")
                return True
            _rand_delay(page, 800, 1200)

        log(f"[실패] 로그인 미완료 — 현재 URL: {page.url}")
        return False

    finally:
        if _owns_session:
            try:
                if page:
                    page.close()
            except Exception:
                pass
            if pw:
                pw.stop()


def logout_tistory(on_log=None):
    """티스토리 로그아웃"""
    def log(msg):
        if on_log:
            on_log(msg)

    pw, browser = connect_cdp(on_log)
    try:
        log("[로그아웃] 티스토리 홈으로 이동...")
        page = get_or_create_page(browser, url_contains="tistory.com", navigate_to=TISTORY_URL)
        _rand_delay(page, 1500, 2500)
        # 홈으로 확실히 이동
        if "manage" in page.url or "newpost" in page.url:
            page.goto(TISTORY_URL, wait_until="domcontentloaded", timeout=15000)
            _rand_delay(page, 1500, 2500)
        page.evaluate("window.scrollTo(0, 0)")
        _rand_delay(page, 500, 1000)

        # 프로필 링크 (T 로고) 클릭 → 드롭다운 열기
        log("[로그아웃] 프로필 클릭...")
        profile_link = page.locator('a.link_profile').first
        if profile_link.is_visible(timeout=5000):
            profile_link.click(force=True)
            _rand_delay(page, 1000, 2000)

            # 드롭다운 맨 아래 로그아웃 버튼 클릭
            log("[로그아웃] 로그아웃 버튼 클릭...")
            logout_btn = page.locator('button.btn_logout').first
            logout_btn.wait_for(state="visible", timeout=5000)
            logout_btn.click()
            _rand_delay(page, 2000, 3000)
            log("[로그아웃] 티스토리 로그아웃 완료")
            return True

        log("[로그아웃] 프로필 버튼 없음 — 이미 로그아웃 상태")
        return True
    finally:
        pw.stop()


def logout_naver(on_log=None):
    """네이버 로그아웃"""
    def log(msg):
        if on_log:
            on_log(msg)

    pw, browser = connect_cdp(on_log)
    page = None
    try:
        log("[로그아웃] 네이버 로그아웃 시작...")
        page = get_or_create_page(browser, navigate_to="https://nid.naver.com/nidlogin.logout")
        _rand_delay(page, 2000, 3000)
        log(f"[로그아웃] 네이버 로그아웃 완료 ({page.url})")
        return True
    finally:
        try:
            if page:
                page.close()
        except Exception:
            pass
        pw.stop()


def login_blog(blog_id: str, on_log=None):
    """블로그ID에 맞는 로그인 실행"""
    config = ACCOUNT_MAP.get(blog_id)
    if not config:
        raise ValueError(f"알 수 없는 블로그: {blog_id}")

    if config["platform"] == "tistory":
        return login_tistory(blog_id, on_log)
    elif config["platform"] == "naver":
        return login_naver(naver_id=config.get("naver_id"), on_log=on_log)
    else:
        raise ValueError(f"지원하지 않는 플랫폼: {config['platform']}")


def logout_blog(blog_id: str, on_log=None):
    """블로그ID에 맞는 로그아웃 실행"""
    config = ACCOUNT_MAP.get(blog_id)
    if not config:
        raise ValueError(f"알 수 없는 블로그: {blog_id}")

    if config["platform"] == "tistory":
        return logout_tistory(on_log)
    elif config["platform"] == "naver":
        return logout_naver(on_log)
    else:
        raise ValueError(f"지원하지 않는 플랫폼: {config['platform']}")
