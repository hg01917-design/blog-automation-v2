#!/bin/bash
# Chrome 9223 (다온나 전용) 실행 확인 및 기동
# 이미 실행 중이면 아무것도 하지 않음

PORT=9223
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

if lsof -i :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "[daonna-chrome] 포트 $PORT 이미 열림 — 생략"
    exit 0
fi

echo "[daonna-chrome] Chrome $PORT 시작..."
"$CHROME" \
    --remote-debugging-port=$PORT \
    --no-first-run \
    --no-default-browser-check \
    --profile-directory="Default" \
    &>/dev/null &

# 최대 15초 대기
for i in $(seq 1 15); do
    sleep 1
    if lsof -i :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "[daonna-chrome] ✅ 포트 $PORT 준비 완료 (${i}초)"
        exit 0
    fi
done

echo "[daonna-chrome] ❌ 포트 $PORT 열기 실패"
exit 1
