#!/bin/bash
CLAUDE=/Users/hana/.local/bin/claude
DIR=/Users/hana/Downloads/blog-automation-v2
cd "$DIR"

# 이미 Claude Code 에이전트 실행 중이면 중복 실행 방지
if pgrep -f "claude" > /dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Claude 에이전트 이미 실행 중 — 스킵" >> "$DIR/logs/daily_run.log"
    exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Claude Code 에이전트 시작 (낮 재시작)" >> "$DIR/logs/daily_run.log"
$CLAUDE -p "CLAUDE.md 규칙대로 각 블로그 임시저장 글 검수하고 발행해줘. 이미지 3장 이상, 본문 1700자 이상, 태그 확인. 같은 블로그 3.5시간 간격 지켜서 3라운드 반복. 완료 후 Notion 현황판(3356d296-d9c1-81f0-992d-c8c15693085d) 업데이트해줘." \
  --dangerously-skip-permissions \
  --add-dir "$DIR" \
  >> "$DIR/logs/daily_run.log" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Claude Code 에이전트 완료" >> "$DIR/logs/daily_run.log"
