#!/bin/bash
# 아침 7시 순차 실행: 블로그오토메이션 → 쿠팡리뷰봇
ulimit -n 65536
PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
DIR=/Users/hana/Downloads/blog-automation-v2
TOKEN=$(grep HanaAutobot "$DIR/.env" | cut -d= -f2)
CHAT_ID=8674424194

tg_notify() {
    curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" \
        --data-urlencode "text=$1" > /dev/null
}

echo "[$(date)] 블로그 자동화 시작" | tee -a $DIR/logs/morning_run.log
cd $DIR
$PYTHON overnight_run.py >> $DIR/logs/morning_run.log 2>&1
if [ $? -ne 0 ]; then
    tg_notify "⚠️ overnight_run 오류
로그: tail -30 logs/morning_run.log"
fi

echo "[$(date)] 쿠팡 리뷰봇 시작" | tee -a $DIR/logs/morning_run.log
$PYTHON me1091_bot.py >> $DIR/logs/morning_run.log 2>&1
if [ $? -ne 0 ]; then
    tg_notify "⚠️ me1091_bot 오류
로그: tail -30 logs/morning_run.log"
fi

echo "[$(date)] 아침 실행 완료" | tee -a $DIR/logs/morning_run.log
