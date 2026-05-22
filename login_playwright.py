"""블로그 로그인/로그아웃 자동화 — CDP + Playwright (완전 자동, 사람 개입 없음)"""
import time
import random
import os
from dotenv import load_dotenv
from browser import connect_cdp, get_or_create_page
from config import ACCOUNT_MAP

load_dotenv()

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

            # 드롭다운 열기: id 입력창 클릭 후 충분히 대기
            try:
                id_input.click()
                _rand_delay(page, 800, 1200)
            except Exception:
                pass

            # 저장된 계정 목록 드롭다운 탐색 — 모든 a/li/button 태그 텍스트로 매칭
            broad_selectors = [
                f'.account_list [data-id="{naver_id}"]',
                f'.account_list a[title="{naver_id}"]',
                f'#savedAccountList [data-id="{naver_id}"]',
                f'[data-id="{naver_id}"]',
                f'ul.account_list li a',
                f'.account_list li',
                f'#savedAccountList li',
                f'.saved_id_wrap li',
                f'.id_pw_wrap .id_save_wrap li',
            ]
            for selector in broad_selectors:
                items = page.locator(selector)
                try:
                    count = items.count()
                except Exception:
                    continue
                if count == 0:
                    continue

                for i in range(count):
                    item = items.nth(i)
                    try:
                        text = item.inner_text(timeout=1000).strip()
                        if naver_id in text:
                            item.click(timeout=3000)
                            log(f"[2/4] 계정 목록에서 '{naver_id}' 선택 완료 (selector={selector})")
                            selected = True
                            _rand_delay(page, 800, 1200)
                            break
                    except Exception:
                        # data-id 매칭 셀렉터는 텍스트 없이 바로 클릭
                        if f'[data-id="{naver_id}"]' in selector:
                            try:
                                item.click(timeout=3000)
                                log(f"[2/4] 계정 목록에서 '{naver_id}' 선택 완료 (data-id)")
                                selected = True
                                _rand_delay(page, 800, 1200)
                            except Exception:
                                pass
                        continue
                if selected:
                    break

            # JS 폴백: 드롭다운 재오픈 후 전체 요소에서 naver_id 탐색
            if not selected:
                try:
                    # 드롭다운이 닫혔을 수 있으므로 다시 클릭해서 열기
                    id_input.click()
                    _rand_delay(page, 600, 900)
                    clicked = page.evaluate(f"""
                        (id) => {{
                            const els = document.querySelectorAll('a, li, button, [role="option"], [data-id]');
                            for (const el of els) {{
                                const dataId = el.getAttribute('data-id') || '';
                                const text = el.textContent.trim();
                                if (dataId === id || text === id || text.startsWith(id)) {{
                                    el.click();
                                    return true;
                                }}
                            }}
                            return false;
                        }}
                    """, naver_id)
                    if clicked:
                        log(f"[2/4] JS 폴백으로 '{naver_id}' 선택 완료")
                        selected = True
                        _rand_delay(page, 800, 1200)
                except Exception:
                    pass

            if not selected:
                # 폴백: 현재 계정 로그아웃 후 로그인 페이지 재접속 → 목록 재확인
                log(f"[2/4] 계정 목록에서 '{naver_id}' 찾지 못함 — 로그아웃 후 재시도")
                try:
                    page.goto("https://nid.naver.com/nidlogin.logout", wait_until="domcontentloaded", timeout=15000)
                    _rand_delay(page, 2000, 3000)
                    page.goto(NAVER_LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
                    _rand_delay(page, 2000, 3000)
                    id_input = page.locator('#id')
                    id_input.wait_for(state="visible", timeout=10000)
                    id_input.click()
                    _rand_delay(page, 800, 1200)
                    # 재확인: 드롭다운에서 naver_id 탐색
                    for selector in [f'[data-id="{naver_id}"]', f'ul.account_list li a', f'.account_list li']:
                        items = page.locator(selector)
                        try:
                            count = items.count()
                        except Exception:
                            continue
                        for i in range(count):
                            item = items.nth(i)
                            try:
                                text = item.inner_text(timeout=1000).strip()
                                if naver_id in text or item.get_attribute("data-id") == naver_id:
                                    item.click(timeout=3000)
                                    log(f"[2/4] 로그아웃 후 재시도 — '{naver_id}' 선택 완료")
                                    selected = True
                                    _rand_delay(page, 800, 1200)
                                    break
                            except Exception:
                                try:
                                    item.click(timeout=3000)
                                    log(f"[2/4] 로그아웃 후 재시도 — '{naver_id}' 선택 완료 (data-id)")
                                    selected = True
                                    _rand_delay(page, 800, 1200)
                                except Exception:
                                    pass
                            if selected:
                                break
                        if selected:
                            break
                except Exception as e:
                    log(f"[2/4] 로그아웃 재시도 중 오류: {e}")

                if not selected:
                    # 최후 수단: ID + PW 직접 입력 (.env에 비밀번호 필수)
                    env_key = f"NAVER_{naver_id.upper()}_PW"
                    naver_pw = os.getenv(env_key)
                    if not naver_pw:
                        log(f"[2/4] ⛔ {env_key} 없음 — .env에 추가 필요 (로그인 중단)")
                        return False
                    log(f"[2/4] 로그아웃 후에도 드롭다운에서 '{naver_id}' 못 찾음 — ID/PW 직접 입력")
                    try:
                        id_input2 = page.locator('#id')
                        id_input2.wait_for(state="visible", timeout=8000)
                        # JS로 필드 값 완전히 지운 후 타이핑
                        page.evaluate("document.querySelector('#id').value = ''")
                        id_input2.click(click_count=3, timeout=3000)
                        _rand_delay(page, 300, 500)
                        id_input2.fill(naver_id)
                        _rand_delay(page, 500, 800)
                        pw_input2 = page.locator('#pw')
                        pw_input2.wait_for(state="visible", timeout=5000)
                        pw_input2.click(timeout=3000)
                        _rand_delay(page, 300, 500)
                        pw_input2.fill(naver_pw)
                        log(f"[2/4] ID/PW 직접 입력 완료 ({env_key})")
                        selected = True
                    except Exception as e:
                        log(f"[2/4] ID/PW 직접 입력 실패: {e}")

                if not selected:
                    log(f"[2/4] 모든 계정 선택 방법 실패 — 로그인 중단")
                    return False

        # 로그인 시도 (최대 2회 — 첫 번째 시도 후 네이버가 오류 페이지를 띄울 수 있음)
        for _attempt in range(2):
            log(f"[3/5] 비밀번호 자동완성 트리거... (시도 {_attempt+1}/2)")
            pw_input = page.locator('#pw')
            if pw_input.is_visible(timeout=3000):
                pw_input.click()
                _rand_delay(page, 800, 1200)

            log(f"[3/5] 로그인 버튼 클릭... (시도 {_attempt+1}/2)")
            # 여러 셀렉터 순서대로 시도 (네이버 로그인 버튼 HTML이 변경될 수 있음)
            _login_btn_selectors = [
                '#log\\.login',
                'button.btn_login',
                'button.btn_global',
                'button[type="submit"]',
                'input[type="submit"]',
            ]
            _clicked = False
            for _sel in _login_btn_selectors:
                try:
                    _btn = page.locator(_sel).first
                    if _btn.is_visible(timeout=2000):
                        _btn.click(timeout=5000)
                        log(f"[3/5] 로그인 버튼 클릭 완료 (selector: {_sel})")
                        _clicked = True
                        break
                except Exception:
                    continue

            # JS 폴백: id="log.login" 직접 클릭 시도
            if not _clicked:
                try:
                    _clicked = page.evaluate("""
                        () => {
                            const candidates = [
                                document.getElementById('log.login'),
                                document.querySelector('button.btn_login'),
                                document.querySelector('button.btn_global'),
                                document.querySelector('button[type="submit"]'),
                                document.querySelector('input[type="submit"]'),
                            ];
                            for (const el of candidates) {
                                if (el) { el.click(); return true; }
                            }
                            return false;
                        }
                    """)
                    if _clicked:
                        log("[3/5] 로그인 버튼 JS 폴백 클릭 완료")
                    else:
                        log("[3/5] ⚠ 로그인 버튼을 찾지 못함 — 계속 대기")
                except Exception as e:
                    log(f"[3/5] JS 폴백 오류: {e}")

            _rand_delay(page, 3000, 5000)

            log("[4/4] 로그인 완료 대기 중...")
            for i in range(20):
                current_url = page.url
                if "nidlogin" not in current_url and "naver.com" in current_url:
                    log(f"[완료] 네이버 로그인 성공! ({current_url})")
                    return True
                _rand_delay(page, 800, 1200)

            # 여전히 로그인 페이지면 재시도 (네이버 1차 오류 후 동일 자격증명 재시도)
            if "nidlogin" in page.url and _attempt == 0:
                log("[재시도] 1차 로그인 실패 — 동일 계정으로 재시도")
                continue
            break

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
        def log(msg):
            if on_log:
                on_log(msg)

        # 이미 로그인된 상태면 로그인 페이지를 거치지 않고 에디터로 바로 진행한다.
        pw = None
        try:
            pw, browser = connect_cdp(on_log)
            editor_url = config.get("editor_url") or f"https://blog.naver.com/{blog_id}/postwrite"
            page = get_or_create_page(browser, navigate_to=editor_url)
            _rand_delay(page, 2500, 3500)
            if "nidlogin" not in page.url and "nid.naver.com" not in page.url:
                # 에디터가 실제로 뜨는지 확인 (다른 계정 로그인 시 에디터 접근 불가)
                try:
                    page.wait_for_selector(".se-content", timeout=8000)
                    log(f"[로그인] 네이버 기존 로그인 세션 확인 — 바로 글쓰기 진행 ({page.url})")
                    return True
                except Exception:
                    expected = config.get("naver_id", blog_id)
                    log(f"[로그인] ⚠ 에디터 미로드 — 다른 계정 로그인 추정, {expected} 재로그인 진행")
                    page.goto("https://nid.naver.com/nidlogin.logout", wait_until="domcontentloaded", timeout=15000)
                    _rand_delay(page, 1500, 2500)
            log("[로그인] 네이버 로그인 필요 — 자동 로그인 진행")
            return login_naver(naver_id=config.get("naver_id"), on_log=on_log, page=page)
        finally:
            if pw:
                pw.stop()
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
