#!/bin/bash
# 하나오토봇 tmux 세션 시작/재연결
# claude --dangerously-skip-permissions 로 항상 시작됨

DIR=/Users/hana/Downloads/blog-automation-v2
CLAUDE=/Users/hana/.local/bin/claude
SESSION=하나오토봇

# 이미 세션 있으면 attach
if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux attach-session -t "$SESSION"
    exit 0
fi

# 새 세션 생성: 창0 = claude (--dangerously-skip-permissions)
tmux new-session -d -s "$SESSION" -n "claude" -c "$DIR"
tmux send-keys -t "$SESSION:0" "cd $DIR && $CLAUDE --dangerously-skip-permissions --model claude-sonnet-4-6" Enter

# 창1 = connector (텔레그램 → claude 주입)
tmux new-window -t "$SESSION" -n "connector" -c "$DIR"
tmux send-keys -t "$SESSION:1" "cd $DIR && python3 telegram_connector.py" Enter

# 창0으로 포커스 이동 후 attach
tmux select-window -t "$SESSION:0"
tmux attach-session -t "$SESSION"
