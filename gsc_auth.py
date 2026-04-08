"""
gsc_auth.py
Google OAuth 재인증 — Indexing API + Search Console (webmasters) 스코프 동시 요청
실행: python3 gsc_auth.py
"""
import json
import time
import urllib.request
import urllib.parse
import webbrowser
import http.server
import threading
from pathlib import Path

TOKEN_PATH = Path(__file__).parent / "gsc_token.json"
CLIENT_SECRET_PATH = Path(__file__).parent / "client_secret.json"

SCOPES = [
    "https://www.googleapis.com/auth/indexing",
    "https://www.googleapis.com/auth/webmasters",
    "https://www.googleapis.com/auth/adsense",
]

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"

_auth_code = None


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        _auth_code = qs.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write("<h2>인증 완료! 이 창을 닫아도 됩니다.</h2>".encode("utf-8"))

    def log_message(self, *args):
        pass


def _load_env():
    import os
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def run_auth():
    import os
    global _auth_code
    _load_env()

    # .env 우선, 없으면 client_secret.json fallback
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not client_id and CLIENT_SECRET_PATH.exists():
        secret = json.loads(CLIENT_SECRET_PATH.read_text())["installed"]
        client_id = secret["client_id"]
        client_secret = secret["client_secret"]
    if not client_id:
        print("오류: GOOGLE_CLIENT_ID 환경변수 또는 client_secret.json 필요")
        return

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urllib.parse.urlencode({
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        })
    )

    print(f"\n브라우저가 열립니다. Google 계정으로 로그인 후 권한 허용하세요.")
    print(f"URL: {auth_url}\n")

    # 로컬 서버 (콜백 수신)
    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _Handler)
    t = threading.Thread(target=server.handle_request)
    t.start()

    webbrowser.open(auth_url)
    t.join(timeout=300)

    if not _auth_code:
        print("인증 시간 초과")
        return

    # 코드 → 토큰 교환
    data = urllib.parse.urlencode({
        "code": _auth_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()
    token_uri = "https://oauth2.googleapis.com/token"
    req = urllib.request.Request(token_uri, data=data)
    try:
        raw = urllib.request.urlopen(req, timeout=10).read()
        resp = json.loads(raw)
    except Exception as e:
        import traceback
        # 오류 응답 본문 출력
        if hasattr(e, 'read'):
            print("Google 오류 응답:", e.read().decode())
        traceback.print_exc()
        return

    token = {
        "access_token": resp["access_token"],
        "refresh_token": resp.get("refresh_token", ""),
        "expires_in": resp.get("expires_in", 3600),
        "issued_at": time.time(),
        "scopes": SCOPES,
    }
    TOKEN_PATH.write_text(json.dumps(token, indent=2))
    print(f"\n✅ 토큰 저장 완료: {TOKEN_PATH}")
    print(f"   스코프: {', '.join(SCOPES)}")


if __name__ == "__main__":
    run_auth()
