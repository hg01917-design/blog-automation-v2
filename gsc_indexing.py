"""
gsc_indexing.py
Google Indexing API를 사용해 발행된 글 URL을 색인 요청
"""
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

TOKEN_PATH = Path(__file__).parent / "gsc_token.json"
CLIENT_SECRET_PATH = Path(__file__).parent / "client_secret.json"
INDEXING_API = "https://indexing.googleapis.com/v3/urlNotifications:publish"


def _load_token() -> dict:
    if not TOKEN_PATH.exists():
        return {}
    return json.loads(TOKEN_PATH.read_text())


def _save_token(token: dict):
    TOKEN_PATH.write_text(json.dumps(token, indent=2))


def _refresh_access_token(token: dict) -> dict:
    """refresh_token으로 새 access_token 발급"""
    secret = json.loads(CLIENT_SECRET_PATH.read_text())["installed"]
    data = urllib.parse.urlencode({
        "client_id": secret["client_id"],
        "client_secret": secret["client_secret"],
        "refresh_token": token["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(secret["token_uri"], data=data)
    resp = urllib.request.urlopen(req, timeout=10).read()
    new_token = json.loads(resp)
    token["access_token"] = new_token["access_token"]
    token["expires_in"] = new_token.get("expires_in", 3600)
    token["issued_at"] = time.time()
    _save_token(token)
    return token


def _get_access_token() -> str:
    token = _load_token()
    if not token or "access_token" not in token:
        raise RuntimeError("gsc_token.json 없음 — OAuth 인증 먼저 실행 필요")

    # 만료 여부 확인 (여유 60초)
    issued_at = token.get("issued_at", 0)
    expires_in = token.get("expires_in", 3600)
    if time.time() > issued_at + expires_in - 60:
        token = _refresh_access_token(token)

    return token["access_token"]


def request_indexing(url: str) -> bool:
    """URL을 Google Indexing API에 색인 요청. 성공 시 True."""
    try:
        access_token = _get_access_token()
        body = json.dumps({"url": url, "type": "URL_UPDATED"}).encode("utf-8")
        req = urllib.request.Request(
            INDEXING_API,
            data=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        resp = urllib.request.urlopen(req, timeout=10).read()
        result = json.loads(resp)
        notify_time = result.get("urlNotificationMetadata", {}).get("latestUpdate", {}).get("notifyTime", "")
        print(f"[GSC] 색인 요청 완료: {url} → {notify_time}", flush=True)
        return True
    except Exception as e:
        print(f"[GSC] 색인 요청 실패 ({url}): {e}", flush=True)
        return False
