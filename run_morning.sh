#!/bin/bash
# 아침 7시 순차 실행: 블로그오토메이션 → 쿠팡리뷰봇
PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
DIR=/Users/hana/Downloads/blog-automation-v2

echo "[$(date)] 블로그 자동화 시작" | tee -a $DIR/logs/morning_run.log
cd $DIR
$PYTHON overnight_run.py >> $DIR/logs/morning_run.log 2>&1

echo "[$(date)] 쿠팡 리뷰봇 시작" | tee -a $DIR/logs/morning_run.log
$PYTHON me1091_bot.py >> $DIR/logs/morning_run.log 2>&1

echo "[$(date)] 아침 실행 완료" | tee -a $DIR/logs/morning_run.log
