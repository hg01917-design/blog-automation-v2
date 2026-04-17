"""CDP 브라우저 연결 공통 모듈 — Profile 1 전용"""
import subprocess
import time
import socket
import json
import urllib.request
from pathlib import Path
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
        import sys as _sys
        if _sys.platform == "win32":
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True
            )
            for line in result.stdout.splitlines():
                if f":{CDP_PORT}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True)
        else:
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
    import os, sys as _sys
    if _sys.platform == "win32":
        user_data_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "Google", "ChromeDebug"
        )
    else:
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


_CURSOR_JS = """() => {
    if (document.getElementById('_bot_cursor')) return;
    const cur = document.createElement('div');
    cur.id = '_bot_cursor';
    cur.style.cssText = 'position:fixed;top:0;left:0;pointer-events:none;z-index:2147483647;';
    cur.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
        <path d="M 0 0 L 0 20 L 4.5 15.5 L 8 22 L 10 21 L 6.5 14.5 L 13 14.5 Z"
              fill="white" stroke="black" stroke-width="1.2" stroke-linejoin="round"/>
    </svg>`;
    document.body.appendChild(cur);
    document.addEventListener('mousemove', e => {
        cur.style.left = e.clientX + 'px';
        cur.style.top = e.clientY + 'px';
    }, true);
}"""


def _apply_stealth(page):
    """실제 Chrome CDP 연결에서는 stealth 불필요. 마우스 커서 시각화만 적용."""
    try:
        # add_init_script: 페이지 이동 시마다 자동 재주입
        page.add_init_script(f"({_CURSOR_JS})()")
        # 현재 페이지에도 즉시 적용
        page.evaluate(f"({_CURSOR_JS})()")
    except Exception:
        pass


def get_or_create_page(browser, url_contains=None, navigate_to=None):
    """기존 탭에서 url_contains 매칭 탭을 찾거나, 없으면 첫 번째 기존 탭 반환.
    navigate_to가 지정된 경우에만 새 탭 생성."""
    if url_contains:
        for ctx in browser.contexts:
            for p in ctx.pages:
                if url_contains in p.url:
                    _apply_stealth(p)
                    return p

    context = browser.contexts[0] if browser.contexts else browser.new_context()

    # navigate_to 없이 호출 시: 기존 탭 재사용 (새 탭 열지 않음)
    if not navigate_to:
        if context.pages:
            page = context.pages[0]
            _apply_stealth(page)
            return page

    page = context.new_page()
    _apply_stealth(page)
    if navigate_to:
        page.goto(navigate_to, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
    return page


def see(page, question: str = "현재 화면 상태를 설명해줘. 어떤 버튼/팝업/오류가 있는지 포함해서.", on_log=None) -> str:
    """현재 브라우저 화면을 스크린샷 찍어 Claude Code CLI로 분석.

    사용 예:
        result = see(page, "이미지 다운로드 버튼이 보이나요?")
        result = see(page, "로그인이 성공했나요?")
    """
    import subprocess
    import os
    import tempfile

    def log(msg):
        if on_log:
            on_log(msg)

    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name

        page.screenshot(path=tmp_path, full_page=False)

        prompt = f"{question}\n\n스크린샷 파일: {tmp_path}\n(Read 툴로 이미지를 읽어서 답해줘. 한국어로 간결하게.)"
        claude_bin = Path.home() / ".local" / "bin" / "claude"

        result = subprocess.run(
            [str(claude_bin), "--dangerously-skip-permissions", "--print", prompt],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent),
            timeout=60,
            env={**os.environ, "HOME": str(Path.home())},
        )
        answer = (result.stdout or "").strip()
        log(f"[👁️ 화면분석] {answer[:300]}")
        return answer

    except Exception as e:
        log(f"[👁️] 화면분석 실패: {e}")
        return ""
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
