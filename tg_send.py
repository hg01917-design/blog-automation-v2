"""텔레그램 전송 유틸 — Claude Code가 호출

사용법:
  python3 tg_send.py "텍스트 메시지"
  python3 tg_send.py --photo /path/to/image.jpg
  python3 tg_send.py --photo /path/to/image.jpg "캡션 텍스트"
"""
import json
import os
import sys
import urllib.parse
import urllib.request
import ssl
from pathlib import Path

# .env 로드
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

import subprocess as _sp
_tmux = _sp.run(["tmux", "display-message", "-p", "#S"], capture_output=True, text=True).stdout.strip()
if _tmux == "체크봇":
    TOKEN = os.environ.get("CHECK_BOT_TOKEN", "")
else:
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = "8674424194"

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def send_text(text: str) -> bool:
    """텍스트 메시지 전송 (4000자 초과 시 분할)"""
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN 없음")
        return False

    MAX = 4000
    success = True
    for i in range(0, max(len(text), 1), MAX):
        chunk = text[i:i + MAX]
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        params = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": chunk})
        try:
            resp = urllib.request.urlopen(
                f"{url}?{params}", timeout=30, context=_ctx
            )
            result = json.loads(resp.read())
            if not result.get("ok"):
                print(f"전송 실패: {result}")
                success = False
        except Exception as e:
            print(f"전송 오류: {e}")
            success = False
    return success


def send_photo(path: str, caption: str = "") -> bool:
    """이미지 전송"""
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN 없음")
        return False

    import mimetypes
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    file_path = Path(path)
    if not file_path.exists():
        print(f"파일 없음: {path}")
        return False

    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    boundary = "----TgBoundary"
    body = []

    def field(name, value):
        body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())

    field("chat_id", CHAT_ID)
    if caption:
        field("caption", caption)

    data = file_path.read_bytes()
    body.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{file_path.name}\"\r\nContent-Type: {mime}\r\n\r\n".encode()
        + data
        + b"\r\n"
    )
    body.append(f"--{boundary}--\r\n".encode())
    payload = b"".join(body)

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        resp = urllib.request.urlopen(req, timeout=30, context=_ctx)
        result = json.loads(resp.read())
        if result.get("ok"):
            return True
        else:
            print(f"이미지 전송 실패: {result}")
            return False
    except Exception as e:
        print(f"이미지 전송 오류: {e}")
        return False


def main():
    args = sys.argv[1:]
    if not args:
        print("사용법: python3 tg_send.py '메시지'")
        print("        python3 tg_send.py --photo /path/img.jpg '캡션'")
        return

    if args[0] == "--photo":
        path    = args[1] if len(args) > 1 else ""
        caption = args[2] if len(args) > 2 else ""
        ok = send_photo(path, caption)
    else:
        text = " ".join(args)
        ok = send_text(text)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
