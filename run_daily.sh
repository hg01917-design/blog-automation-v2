#!/bin/bash
PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
CLAUDE=/Users/hana/.local/bin/claude
DIR=/Users/hana/Downloads/blog-automation-v2
cd "$DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 데일리 블로그 자동화 시작 ===" >> "$DIR/logs/daily_run.log"

# 1. overnight_run.py — 콘텐츠 생성 + 임시저장
echo "[$(date '+%Y-%m-%d %H:%M:%S')] overnight_run 시작" >> "$DIR/logs/daily_run.log"
$PYTHON "$DIR/overnight_run.py" >> "$DIR/logs/daily_run.log" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] overnight_run 완료" >> "$DIR/logs/daily_run.log"

# 2. Claude Code 에이전트 — 임시저장 글 검수 + 발행 (Playwright 사용)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Claude Code 에이전트 시작" >> "$DIR/logs/daily_run.log"
$CLAUDE -p "세션 시작. 먼저 Notion 현황판(3356d296-d9c1-81f0-992d-c8c15693085d)과 블로그 에이전트 페이지(3356d296-d9c1-81fc-969d-de0dfa04f463)를 읽어서 이전 세션 상태 파악해. 그 다음 overnight_run.py가 방금 완료됐으니 CLAUDE.md 규칙대로 각 블로그 임시저장 글 검수하고 발행해줘. 이미지 3장 이상, 본문 1700자 이상, 태그 확인. 같은 블로그 3.5시간 간격 지켜서 3라운드 반복. 완료 후 Notion 현황판 오늘 발행 결과로 업데이트해줘." \
  --dangerously-skip-permissions \
  --add-dir "$DIR" \
  >> "$DIR/logs/daily_run.log" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Claude Code 에이전트 완료" >> "$DIR/logs/daily_run.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 데일리 완료 ===" >> "$DIR/logs/daily_run.log"
