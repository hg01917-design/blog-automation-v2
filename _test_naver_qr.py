"""네이버 QR 단축링크 생성 자동화 테스트"""
import sys
import time
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp, get_or_create_page

def log(msg):
    print(msg, flush=True)

def main():
    log("[1] CDP Chrome(9222) 연결 중...")
    pw, browser = connect_cdp(on_log=log)

    try:
        log("[2] naver.com 탭 찾기 (me1091 계정)...")
        page = get_or_create_page(browser, url_contains="naver.com")
        log(f"    현재 탭 URL: {page.url}")

        log("[3] https://qr.naver.com/create 접속...")
        page.goto("https://qr.naver.com/create", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        log(f"    접속 후 URL: {page.url}")

        # 스크린샷 찍어서 UI 확인
        screenshot_path = "/tmp/qr_before.png"
        page.screenshot(path=screenshot_path)
        log(f"[4] 스크린샷 저장: {screenshot_path}")

        # 로그인 여부 확인 - URL이 login 페이지인지
        current_url = page.url
        if "login" in current_url or "nid.naver.com" in current_url:
            log("[!] 로그인이 필요합니다. me1091 계정으로 로그인 시도...")
            import os
            naver_id = "me1091"
            naver_pw = os.environ.get("NAVER_ME1091_PW", "")
            if not naver_pw:
                # .env에서 직접 로드
                env_path = '/Users/hana/Downloads/blog-automation-v2/.env'
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("NAVER_ME1091_PW="):
                            naver_pw = line.strip().split("=", 1)[1]
                            break

            page.wait_for_timeout(1000)
            # ID 입력
            id_input = page.locator("#id")
            if id_input.count() > 0:
                id_input.click()
                id_input.fill(naver_id)
                time.sleep(0.3)
                pw_input = page.locator("#pw")
                pw_input.click()
                pw_input.fill(naver_pw)
                time.sleep(0.3)
                # 로그인 버튼 클릭
                login_btn = page.locator("#log\.login")
                if login_btn.count() > 0:
                    login_btn.click()
                else:
                    page.keyboard.press("Enter")
                page.wait_for_timeout(3000)
                log(f"    로그인 후 URL: {page.url}")
                # 로그인 후 qr.naver.com/create 재접속
                if "qr.naver.com" not in page.url:
                    page.goto("https://qr.naver.com/create", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)
                    log(f"    재접속 후 URL: {page.url}")
            else:
                log("[!] 로그인 폼을 찾을 수 없음")
                return
        else:
            log("[5] 로그인 상태 확인됨. URL 입력창 찾기...")

        # URL 입력창 찾기 — 여러 selector 시도
        url_input = None
        selectors = [
            "input[type='url']",
            "input[placeholder*='URL']",
            "input[placeholder*='url']",
            "input[placeholder*='링크']",
            "input[placeholder*='입력']",
            ".url_input input",
            "#url",
            "input[name='url']",
            "input[class*='url']",
            "input[class*='input']",
        ]

        for sel in selectors:
            locator = page.locator(sel)
            if locator.count() > 0:
                url_input = locator.first
                log(f"    URL 입력창 발견: {sel}")
                break

        if not url_input:
            # 전체 input 목록 확인
            inputs = page.locator("input").all()
            log(f"    페이지의 input 개수: {len(inputs)}")
            for i, inp in enumerate(inputs):
                try:
                    attrs = {
                        'type': inp.get_attribute('type'),
                        'placeholder': inp.get_attribute('placeholder'),
                        'name': inp.get_attribute('name'),
                        'id': inp.get_attribute('id'),
                        'class': inp.get_attribute('class'),
                    }
                    log(f"    input[{i}]: {attrs}")
                except Exception:
                    pass

            if inputs:
                url_input = inputs[0]
                log("    첫 번째 input 사용")
            else:
                log("[!] URL 입력창을 찾을 수 없음")
                page.screenshot(path="/tmp/qr_no_input.png")
                return

        log("[6] 테스트 URL 입력: https://app.baremi542.com")
        url_input.click()
        url_input.fill("https://app.baremi542.com")
        page.wait_for_timeout(500)

        log("[7] 생성 버튼 클릭...")
        # 생성 버튼 찾기
        btn_selectors = [
            "button[type='submit']",
            "button:has-text('생성')",
            "button:has-text('만들기')",
            "button:has-text('확인')",
            "button:has-text('단축')",
            ".btn_create",
            ".create_btn",
            "input[type='submit']",
        ]
        btn = None
        for sel in btn_selectors:
            locator = page.locator(sel)
            if locator.count() > 0:
                btn = locator.first
                log(f"    버튼 발견: {sel}")
                break

        if not btn:
            # 모든 버튼 출력
            buttons = page.locator("button").all()
            log(f"    페이지 버튼 개수: {len(buttons)}")
            for i, b in enumerate(buttons):
                try:
                    log(f"    button[{i}]: text={b.inner_text()}, class={b.get_attribute('class')}")
                except Exception:
                    pass
            if buttons:
                btn = buttons[0]
                log("    첫 번째 버튼 사용")

        if btn:
            btn.click()
            page.wait_for_timeout(3000)
        else:
            log("[!] 생성 버튼을 찾을 수 없음")

        # 결과 스크린샷
        screenshot_after = "/tmp/qr_after.png"
        page.screenshot(path=screenshot_after)
        log(f"[8] 결과 스크린샷: {screenshot_after}")

        log("[9] 생성된 단축 URL 추출...")
        # m.site.naver.com 또는 네이버 단축 URL 패턴 찾기
        result_url = ""

        # 페이지에서 m.site.naver.com 포함 텍스트 찾기
        content = page.content()
        import re
        patterns = [
            r'https?://m\.site\.naver\.com/[A-Za-z0-9]+',
            r'https?://naver\.me/[A-Za-z0-9]+',
            r'https?://me\.naver\.com/[A-Za-z0-9]+',
        ]
        for pat in patterns:
            matches = re.findall(pat, content)
            if matches:
                result_url = matches[0]
                log(f"    단축 URL 발견: {result_url}")
                break

        # 텍스트 기반 locator로도 시도
        if not result_url:
            result_locators = [
                "input[readonly]",
                ".short_url",
                ".result_url",
                "[class*='short']",
                "[class*='result']",
                "[class*='url']",
            ]
            for sel in result_locators:
                locator = page.locator(sel)
                if locator.count() > 0:
                    try:
                        val = locator.first.input_value() or locator.first.inner_text()
                        if val and ("naver" in val or "http" in val):
                            result_url = val.strip()
                            log(f"    결과 URL ({sel}): {result_url}")
                            break
                    except Exception:
                        pass

        if not result_url:
            log("[!] 단축 URL을 추출하지 못했습니다. 스크린샷으로 확인하세요.")

        log("[10] 텔레그램으로 결과 전송...")
        import subprocess
        cwd = '/Users/hana/Downloads/blog-automation-v2'

        if result_url:
            msg = f"테스트 결과: {result_url}"
        else:
            msg = "테스트 완료 - 단축 URL 추출 실패 (스크린샷 확인)"

        subprocess.run(
            ['python3', 'tg_send.py', msg],
            cwd=cwd, check=False
        )

        # 결과 스크린샷도 전송
        subprocess.run(
            ['python3', 'tg_send.py', '--photo', screenshot_after, 'QR 생성 화면'],
            cwd=cwd, check=False
        )

        # 초기 화면 스크린샷도 전송 (참고용)
        subprocess.run(
            ['python3', 'tg_send.py', '--photo', screenshot_path, 'QR 페이지 초기 화면'],
            cwd=cwd, check=False
        )

        log("[완료] 테스트 종료")

    finally:
        pw.stop()

if __name__ == "__main__":
    main()
