#!/usr/bin/env python3
"""
블로그 자동화 오류 감지 및 텔레그램 보고 스크립트
매 1시간마다 실행 — 발행 실패/장기 미발행/봇 오류 감지
"""
import json
import os
import re
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

DIR = Path(__file__).parent
LOGS_DIR = DIR / "logs"

# .env 로드
env = {}
env_file = DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        m = re.match(r'^(\w+)=(.*)$', line.strip())
        if m:
            env[m.group(1)] = m.group(2)

BOT_TOKEN = env.get("CHECK_BOT_TOKEN", os.environ.get("CHECK_BOT_TOKEN", ""))
CHAT_ID = env.get("TELEGRAM_CHAT_ID", os.environ.get("TELEGRAM_CHAT_ID", "8674424194"))

# 블로그별 최대 허용 미발행 간격 (초)
MAX_GAP = {
    "nolja100":  8 * 3600,
    "goodisak":  8 * 3600,
    "baremi542": 8 * 3600,
    "triplog":   8 * 3600,
    "phn0502":   8 * 3600,
    "salim1su":  8 * 3600,
    "woll100":   8 * 3600,
    "me1091":    8 * 3600,
}


def send_telegram(text: str):
    if not BOT_TOKEN:
        print("[health_check] BOT_TOKEN 없음, 텔레그램 전송 스킵")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[health_check] 텔레그램 전송 실패: {e}")


def check_publish_times() -> list[str]:
    """마지막 발행 후 너무 오래된 블로그 감지"""
    issues = []
    times_file = LOGS_DIR / "blog_publish_times.json"
    if not times_file.exists():
        return ["blog_publish_times.json 없음"]

    try:
        times = json.loads(times_file.read_text())
    except Exception as e:
        return [f"blog_publish_times.json 파싱 오류: {e}"]

    now = time.time()
    for blog, last_ts in times.items():
        max_gap = MAX_GAP.get(blog, 8 * 3600)
        gap = now - last_ts
        if gap > max_gap:
            hours = gap / 3600
            issues.append(f"⚠️ {blog}: 마지막 발행 {hours:.1f}시간 전 (기준: {max_gap//3600}h)")
    return issues


def check_daily_run_log() -> list[str]:
    """크론 생성 로그에서 최근 오류 감지"""
    issues = []
    log_files = sorted(LOGS_DIR.glob("cron_gen_r*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not log_files:
        return []

    lines = log_files[0].read_text(errors="replace").splitlines()[-200:]
    skip_patterns = [r"DeprecationWarning", r"Use --trace-deprecation", r"\(Use `node", r"^\s*$"]
    error_patterns = [r"Error|ERROR|Exception|Traceback", r"failed|Failed|FAILED", r"timeout|Timeout"]

    found_errors = []
    for line in lines:
        if any(re.search(p, line) for p in skip_patterns):
            continue
        if any(re.search(p, line) for p in error_patterns):
            stripped = line.strip()
            if stripped not in found_errors:
                found_errors.append(stripped)

    if found_errors:
        unique = list(dict.fromkeys(found_errors))[:5]
        issues.append(f"📋 {log_files[0].name} 최근 오류:")
        issues.extend(f"  {e[:120]}" for e in unique)
    return issues


def check_publish_logs() -> list[str]:
    """각 블로그 발행 로그에서 최근 실패 감지"""
    issues = []
    skip_patterns = [r"DeprecationWarning", r"Use --trace-deprecation", r"\(Use `node"]
    for log_file in LOGS_DIR.glob("claude_publish_*.log"):
        blog = log_file.stem.replace("claude_publish_", "")
        lines = log_file.read_text(errors="replace").splitlines()[-50:]

        recent_errors = []
        for line in lines:
            if any(re.search(p, line) for p in skip_patterns):
                continue
            if re.search(r"Error|Failed|Traceback|401|403|timeout", line):
                recent_errors.append(line.strip())

        if recent_errors:
            issues.append(f"❌ {blog} 발행 로그 오류: {recent_errors[-1][:120]}")
    return issues


def check_overnight_run() -> list[str]:
    """overnight_run.py가 최근 14시간 내 실행됐는지 확인"""
    issues = []
    log_files = sorted(LOGS_DIR.glob("cron_gen_r*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not log_files:
        return ["⚠️ cron_gen 로그 없음 — overnight_run 미실행?"]

    last_run = log_files[0].stat().st_mtime
    hours_ago = (time.time() - last_run) / 3600
    if hours_ago > 14:
        issues.append(f"⚠️ overnight_run 마지막 실행 {hours_ago:.1f}시간 전 (14h 기준 초과)")
    return issues


def main():
    print(f"[health_check] 시작 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    all_issues = []
    all_issues += check_overnight_run()
    all_issues += check_publish_times()
    all_issues += check_publish_logs()
    all_issues += check_daily_run_log()

    if not all_issues:
        print("[health_check] 이상 없음")
        # 이상 없을 때는 텔레그램 전송 안 함 (스팸 방지)
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"🔍 블로그 자동화 점검 결과 ({now_str})\n\n"
    msg += "\n".join(all_issues)

    print(msg)
    send_telegram(msg)


if __name__ == "__main__":
    main()
