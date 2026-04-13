#!/bin/bash
# 도매꾹 상품등록봇 실행 래퍼 (오류 시 텔레그램 알림)
cd /Users/hana/Downloads/blog-automation-v2
PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
LOG=logs/daonna_cron.log
TOKEN=$(grep HanaAutobot .env | cut -d= -f2)
CHAT_ID=8674424194

echo "[daonna] === $(date) 시작 ===" >> "$LOG"

# Chrome 9223 확인 및 기동
bash "$(dirname "$0")/start_daonna_chrome.sh" >> "$LOG" 2>&1
if [ $? -ne 0 ]; then
    MSG="⚠️ 다온나 Chrome 9223 실행 실패%0A수동으로 Chrome을 9223 포트로 열어주세요."
    curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}&text=${MSG}" > /dev/null
    echo "[daonna] ❌ Chrome 9223 기동 실패 — 종료" >> "$LOG"
    exit 1
fi

$PYTHON daonna_run.py >> "$LOG" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    MSG="⚠️ 도매꾹 상품등록봇 오류 (exit $EXIT_CODE)%0A로그: tail -20 logs/daonna_cron.log"
    curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}&text=${MSG}" > /dev/null
    echo "[daonna] ❌ 오류 발생 (exit $EXIT_CODE) — 텔레그램 알림 전송" >> "$LOG"
else
    echo "[daonna] ✅ 완료" >> "$LOG"
fi
