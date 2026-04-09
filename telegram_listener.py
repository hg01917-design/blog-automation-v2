"""상시 실행 텔레그램 리스너

사용자 메시지 수신 시 claude --print 호출 (blocking).
overnight_run.py와 별개로 항상 실행.

실행: python3 telegram_listener.py
"""
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

# .env 로드
_env = Path(__file__).parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_CHAT_ID = "8674424194"
CLAUDE_BIN = "/Users/hana/.local/bin/claude"
PROJECT_DIR = str(Path(__file__).parent)
LOG_DIR = Path(PROJECT_DIR) / "logs"
LOG_DIR.mkdir(exist_ok=True)
OFFSET_FILE = LOG_DIR / "telegram_offset.json"

import urllib.request, urllib.parse, ssl

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _api(method, params=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        resp = urllib.request.urlopen(url, timeout=35, context=_ctx)
        return json.loads(resp.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _send(chat_id, text):
    _api("sendMessage", {"chat_id": chat_id, "text": text})


def _load_offset():
    try:
        return json.loads(OFFSET_FILE.read_text()).get("offset", 0)
    except Exception:
        return 0


def _save_offset(offset):
    OFFSET_FILE.write_text(json.dumps({"offset": offset}))


def _log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_DIR / "telegram_listener.log", "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# 현재 claude 실행 중인지 추적 (동시 실행 방지)
_claude_running = False


def _call_claude(chat_id, text, message_id):
    global _claude_running
    if _claude_running:
        _log(f"[리스너] Claude 이미 실행 중 — 대기 후 처리: {text[:30]}")
        # 메시지 큐에 넣는 대신 5초 대기 후 재시도
        time.sleep(5)
        if _claude_running:
            _send(chat_id, "⏳ 이전 작업 처리 중입니다. 잠시 후 다시 보내주세요.")
            return

    _claude_running = True
    prompt = (
        f"텔레그램 메시지 수신 (chat_id={chat_id}, message_id={message_id}):\n"
        f"{text}\n\n"
        f"위 메시지를 처리하고 텔레그램(chat_id={chat_id})으로 응답해줘."
    )
    _log(f"[리스너] Claude 호출: {text[:50]}")
    try:
        log_file = LOG_DIR / "telegram_claude.log"
        with open(log_file, "a") as fh:
            fh.write(f"\n=== {datetime.now()} ===\n사용자: {text}\n")
            subprocess.run(
                [CLAUDE_BIN, "--print", "--no-markdown", prompt],
                cwd=PROJECT_DIR,
                stdout=fh,
                stderr=subprocess.STDOUT,
                timeout=300,  # 5분 타임아웃
            )
    except subprocess.TimeoutExpired:
        _log("[리스너] Claude 타임아웃 (5분)")
        _send(chat_id, "⚠️ 처리 시간이 너무 길어졌어. 다시 시도해줘.")
    except Exception as e:
        _log(f"[리스너] Claude 실행 실패: {e}")
    finally:
        _claude_running = False


def main():
    if not BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN 없음 — 종료")
        return

    _log("=" * 50)
    _log(f"텔레그램 리스너 시작")
    _log("=" * 50)

    offset = _load_offset()
    _log(f"offset: {offset}")

    while True:
        result = _api("getUpdates", {
            "offset": offset,
            "timeout": 30,
            "allowed_updates": "message",
        })

        if not result.get("ok"):
            _log(f"getUpdates 실패: {result.get('error', '')}")
            time.sleep(5)
            continue

        updates = result.get("result", [])
        for update in updates:
            offset = update["update_id"] + 1
            _save_offset(offset)

            msg = update.get("message", {})
            chat_id = str(msg.get("chat", {}).get("id", ""))
            text = (msg.get("text") or "").strip()
            message_id = msg.get("message_id", 0)

            # 허가된 chat_id만 처리
            if chat_id != ALLOWED_CHAT_ID:
                continue
            if not text:
                continue
            # 봇 자신이 보낸 메시지 무시
            if msg.get("from", {}).get("is_bot"):
                continue

            _log(f"메시지: {text[:60]}")
            _call_claude(chat_id, text, message_id)


if __name__ == "__main__":
    main()
