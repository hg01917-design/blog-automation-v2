#!/bin/bash
# 천하무적 키워드 엔진 — 백그라운드 실행
# 사용법:
#   직접: bash keyword_engine/run_bg.sh
#   특정 블로그: bash keyword_engine/run_bg.sh --blog nolja100
#   Playwright 없이: bash keyword_engine/run_bg.sh --no-playwright

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/keyword_engine_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 천하무적 키워드 엔진 시작" | tee -a "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 인자: $*" | tee -a "$LOG_FILE"

cd "$PROJECT_DIR"

# Python 직접 실행 (API 비용 없음 — Naver 검색 무료 API + Playwright)
python3 -m keyword_engine.main "$@" 2>&1 | tee -a "$LOG_FILE"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 완료" | tee -a "$LOG_FILE"
