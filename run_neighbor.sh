#!/bin/bash
# 0~3600초 랜덤 대기 후 neighbor_automation.py 실행 (17:00 시작 → 17:00~18:00 사이 실행)
DELAY=$((RANDOM % 3600))
echo "[이웃추가] ${DELAY}초 후 시작 ($(date))"
sleep $DELAY
cd /Users/hana/Downloads/blog-automation-v2
PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3

echo "[이웃추가] === salim1su 시작 ==="
$PYTHON neighbor_automation.py salim1su

echo "[이웃추가] 60초 대기 후 me1091 시작..."
sleep 60

echo "[이웃추가] === me1091 시작 ==="
$PYTHON neighbor_automation.py me1091
