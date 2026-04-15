"""텔레그램 → Claude Code 터미널 커넥터 (하나오토봇)

텔레그램 메시지(텍스트/이미지)를 수신해 tmux 창에 직접 주입.
Claude Code가 처리 후 tg_send.py로 답장.

실행: python3 telegram_connector.py
환경변수: TELEGRAM_BOT_TOKEN, TARGET_PANE (기본: 하나오토봇:0.0)
"""
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
import ssl
from datetime import datetime
from pathlib import Path

# ── .env 로드 ────────────────────────────────────────────────────
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

TOKEN          = ""
ALLOWED_CHAT   = "8674424194"
TARGET_PANE    = os.environ.get("TARGET_PANE", "하나오토봇:0.0")
PROJECT_DIR    = Path(__file__).parent
LOG_DIR        = PROJECT_DIR / "logs"
PHOTO_DIR      = PROJECT_DIR / "logs" / "tg_photos"
OFFSET_FILE    = LOG_DIR / "connector_offset.json"

LOG_DIR.mkdir(exist_ok=True)
PHOTO_DIR.mkdir(exist_ok=True)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _api(method: str, params: dict = None) -> dict:
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        resp = urllib.request.urlopen(url, timeout=35, context=_ctx)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            return {"ok": False, "error": f"{e.code} {body.get('description', '')}"}
        except Exception:
            return {"ok": False, "error": str(e.code)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _download_file(file_id: str) -> str | None:
    """텔레그램 파일 다운로드 → 로컬 경로 반환"""
    info = _api("getFile", {"file_id": file_id})
    if not info.get("ok"):
        return None
    file_path = info["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    ext = Path(file_path).suffix or ".jpg"
    local = PHOTO_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_id[:8]}{ext}"
    try:
        req = urllib.request.urlopen(url, timeout=30, context=_ctx)
        local.write_bytes(req.read())
        return str(local)
    except Exception as e:
        _log(f"파일 다운로드 실패: {e}")
        return None


def _inject(text: str):
    """tmux paste-buffer로 Claude Code 창에 텍스트 주입 (긴 텍스트/특수문자 대응)"""
    import tempfile
    # 텍스트를 임시 파일에 써서 load-buffer로 주입 (send-keys는 긴 문자열 잘림)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        tmp = f.name
    try:
        subprocess.run(["tmux", "load-buffer", tmp], check=True)
        subprocess.run(["tmux", "paste-buffer", "-t", TARGET_PANE], check=True)
        subprocess.run(["tmux", "send-keys", "-t", TARGET_PANE, "", "Enter"], check=True)
    finally:
        os.unlink(tmp)


def _log(msg: str):
    line = f"[connector][{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)


def _load_offset() -> int:
    try:
        return json.loads(OFFSET_FILE.read_text()).get("offset", 0)
    except Exception:
        return 0


def _save_offset(offset: int):
    OFFSET_FILE.write_text(json.dumps({"offset": offset}))


def handle_update(update: dict):
    msg = update.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    if chat_id != ALLOWED_CHAT:
        return
    if msg.get("from", {}).get("is_bot"):
        return

    text    = (msg.get("text") or msg.get("caption") or "").strip()
    photos  = msg.get("photo")
    doc     = msg.get("document")

    # 이미지 처리
    if photos:
        # 가장 큰 해상도 선택
        file_id = photos[-1]["file_id"]
        _log(f"이미지 수신 (file_id: {file_id[:12]}...)")
        local_path = _download_file(file_id)
        if local_path:
            inject_msg = f"[텔레그램 이미지] {local_path}"
            if text:
                inject_msg += f"\n[캡션] {text}"
        else:
            inject_msg = f"[텔레그램 이미지 수신 실패]{' 캡션: ' + text if text else ''}"
        _inject(inject_msg)
        _log(f"이미지 주입 완료 → {TARGET_PANE}")
        return

    # 문서(파일) 처리
    if doc:
        file_id = doc["file_id"]
        fname   = doc.get("file_name", "파일")
        _log(f"파일 수신: {fname}")
        local_path = _download_file(file_id)
        if local_path:
            inject_msg = f"[텔레그램 파일] {fname} → {local_path}"
            if text:
                inject_msg += f"\n[캡션] {text}"
        else:
            inject_msg = f"[텔레그램 파일 수신 실패: {fname}]"
        _inject(inject_msg)
        _log(f"파일 주입 완료 → {TARGET_PANE}")
        return

    # 텍스트 처리
    if text:
        _log(f"텍스트 수신: {text[:60]}")
        _inject(f"[텔레그램] {text}")
        _log(f"텍스트 주입 완료 → {TARGET_PANE}")


def main():
    global TOKEN, TARGET_PANE, OFFSET_FILE

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default="")
    parser.add_argument("--token-var", default="TELEGRAM_BOT_TOKEN")
    parser.add_argument("--pane", default=None)
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    TOKEN = args.token or os.environ.get(args.token_var, "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not TOKEN:
        print(f"토큰 없음 — --token 또는 {args.token_var} 환경변수 설정 필요")
        return

    if args.pane:
        TARGET_PANE = args.pane
    # env var TARGET_PANE already loaded at module level; args.pane overrides if given

    name = args.name or args.token_var.replace("_TOKEN", "").lower()
    OFFSET_FILE = LOG_DIR / f"connector_{name}_offset.json"

    _log(f"시작 — 폴링 중 → {TARGET_PANE}")

    # 시작 시 기존 세션 탈취 (이전 폴러 강제 종료)
    _api("deleteWebhook", {"drop_pending_updates": "false"})
    _api("getUpdates", {"timeout": 0, "limit": 1})
    time.sleep(1)
    _log("세션 초기화 완료")

    offset = _load_offset()

    while True:
        result = _api("getUpdates", {
            "offset": offset,
            "timeout": 30,
            "allowed_updates": "message",
        })

        if not result.get("ok"):
            err = str(result.get("error", ""))
            if "409" in err:
                _log("⚠️ 409 — 세션 재탈취 시도")
                _api("getUpdates", {"timeout": 0, "limit": 1})
                time.sleep(3)
            else:
                _log(f"getUpdates 실패: {err}")
                time.sleep(5)
            continue

        for update in result.get("result", []):
            offset = update["update_id"] + 1
            _save_offset(offset)
            try:
                handle_update(update)
            except Exception as e:
                _log(f"처리 오류: {e}")


if __name__ == "__main__":
    main()
