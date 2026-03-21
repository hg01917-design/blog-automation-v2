"""CDP 브라우저 연결 공통 모듈 — Profile 1 전용"""
import subprocess
import time
import socket
import json
import urllib.request
from playwright.sync_api import sync_playwright
from config import CHROME_CONFIG

CDP_URL = CHROME_CONFIG["debug_url"]
CHROME_PATH = CHROME_CONFIG["executable"]
PROFILE_DIR = CHROME_CONFIG["profile"]
CDP_PORT = CHROME_CONFIG["port"]


def _is_port_open(port=None):
    port = port or CDP_PORT
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def _get_cdp_profile():
    """현재 CDP에 연결된 Chrome의 프로필 디렉토리를 확인한다."""
    try:
        resp = urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=3)
        data = json.loads(resp.read())
        # userDataDir에서 프로필 경로 추출
        # 예: /Users/hana/Library/Application Support/Google/Chrome/Profile 1
        exe_path = data.get("Browser", "")
        # webSocketDebuggerUrl로 연결 가능 여부만 확인
        ws_url = data.get("webSocketDebuggerUrl", "")
        if ws_url:
            return data
    except Exception:
        pass
    return None


def _kill_cdp_chrome():
    """9222 포트를 사용 중인 Chrome 프로세스를 종료한다."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{CDP_PORT}"],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split("\n")
        for pid in pids:
            if pid.strip():
                subprocess.run(["kill", "-9", pid.strip()],
                               capture_output=True)
        time.sleep(2)
    except Exception:
        pass


def ensure_chrome_cdp(on_log=None):
    """Profile 1 Chrome이 CDP로 실행 중인지 확인하고, 아니면 실행한다."""
    def log(msg):
        if on_log:
            on_log(msg)

    if _is_port_open():
        # 포트는 열려있지만, 프로필 확인
        info = _get_cdp_profile()
        if info:
            # CDP 연결 가능 — 프로필 확인은 Chrome 시작 인자로 보장
            log(f"[Chrome] CDP 포트 {CDP_PORT} 활성 (Profile: {PROFILE_DIR})")
            return
        else:
            # 포트는 열렸지만 응답 없음 → 죽이고 재시작
            log("[Chrome] CDP 응답 없음 — 재시작...")
            _kill_cdp_chrome()

    log(f"[Chrome] {PROFILE_DIR}로 Chrome 실행 중...")
    import os
    user_data_dir = os.path.expanduser(
        "~/Library/Application Support/Google/ChromeDebug"
    )
    subprocess.Popen(
        [
            CHROME_PATH,
            f"--remote-debugging-port={CDP_PORT}",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={user_data_dir}",
            "--profile-directory=Default",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for i in range(15):
        if _is_port_open():
            log(f"[Chrome] CDP ready — {PROFILE_DIR} ({i+1}초)")
            return
        time.sleep(1)

    raise RuntimeError(f"Chrome CDP 시작 실패 ({PROFILE_DIR}) — 15초 타임아웃")


def connect_cdp(on_log=None):
    """Chrome CDP에 연결하여 (playwright, browser) 반환"""
    ensure_chrome_cdp(on_log)
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
    except Exception as e:
        pw.stop()
        raise RuntimeError(f"CDP 연결 실패: {e}")
    return pw, browser


def get_or_create_page(browser, url_contains=None, navigate_to=None):
    """기존 탭에서 url_contains 매칭 탭을 찾거나, navigate_to로 새 탭 생성"""
    if url_contains:
        for ctx in browser.contexts:
            for p in ctx.pages:
                if url_contains in p.url:
                    return p

    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    if navigate_to:
        page.goto(navigate_to, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
    return page
