#!/usr/bin/env python3
"""PreToolUse Hook — 발행 스크립트 실행 시 자동 차단."""
import sys
import json
import re

try:
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)

PUBLISH_PATTERNS = [
    r"python3?\s+.*publish_drafts\.py",
    r"python3?\s+.*publish_pending_drafts\.py",
]

for pat in PUBLISH_PATTERNS:
    if re.search(pat, command):
        print(
            f"⛔ [발행 차단] CLAUDE.md 규칙: 발행은 사용자가 명시적으로 요청할 때만 수행.\n"
            f"감지된 명령: {command[:120]}\n"
            "사용자에게 '발행할까요?' 확인 후 승인받아 진행하세요.",
            file=sys.stderr,
        )
        sys.exit(2)  # 2 = 도구 실행 차단

sys.exit(0)
