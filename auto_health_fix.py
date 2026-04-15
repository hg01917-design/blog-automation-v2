#!/usr/bin/env python3
"""
auto_health_fix.py
오프아워(overnight_run.py 미실행 시간대) 자동 점검 + 자동 수정 + 텔레그램 보고

실행 시각: 02:00 / 05:00 / 09:00 (overnight_run 없는 시간대)

점검 항목:
  1. 최근 로그 오류 패턴 감지
  2. 처리 불완전 블로그 원인 분석
  3. nolja100 임시저장 없음 → keyword_engine에서 새 키워드 배정
  4. DB 통계 요약 보고
  5. 이상 없으면 간단 상태만 보고

사용법:
  python3 auto_health_fix.py
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

DIR = Path(__file__).parent
LOGS_DIR = DIR / "logs"
DB_PATH = DIR / "keyword_engine" / "engine.db"
KST = timezone(timedelta(hours=9))

# .env 로드
_env = DIR / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8674424194")
TG_SEND = DIR / "tg_send.py"


def send_tg(msg: str):
    """tg_send.py로 체크봇 전송"""
    try:
        subprocess.run(
            [sys.executable, str(TG_SEND), msg],
            timeout=15, cwd=str(DIR),
            env={**os.environ, "HOME": str(Path.home())},
            capture_output=True,
        )
    except Exception as e:
        print(f"[health_fix] tg 전송 실패: {e}")


def _log(msg: str):
    print(f"[{datetime.now(KST).strftime('%H:%M:%S')}] {msg}", flush=True)


# ── 1. 로그 오류 감지 ──────────────────────────────────────────────────────

_SKIP = [r"DeprecationWarning", r"Use --trace-deprecation", r"\(Use `node", r"^\s*$",
         r"--dangerously-skip-permissions", r"Human:", r"Assistant:"]
_ERR_PAT = [r"Traceback \(most recent", r"Error:", r"ERROR", r"Exception:",
            r"no such column", r"timeout.*120", r"FAILED"]


def scan_log_errors(logfile: Path, lines_back: int = 300) -> list[str]:
    if not logfile.exists():
        return []
    lines = logfile.read_text(errors="replace").splitlines()[-lines_back:]
    seen = set()
    found = []
    for line in lines:
        if any(re.search(p, line) for p in _SKIP):
            continue
        if any(re.search(p, line) for p in _ERR_PAT):
            stripped = line.strip()[:150]
            if stripped not in seen:
                seen.add(stripped)
                found.append(stripped)
    return found[:8]


def get_recent_errors() -> dict[str, list[str]]:
    """각 로그 파일별 최근 오류 모음"""
    result = {}
    log_targets = {
        "overnight": sorted(LOGS_DIR.glob("gen_r*.log"), key=lambda f: f.stat().st_mtime, reverse=True),
        "publish":   sorted(LOGS_DIR.glob("publish_out.log"), key=lambda f: f.stat().st_mtime, reverse=True),
        "health":    sorted(LOGS_DIR.glob("health_fix.log"), key=lambda f: f.stat().st_mtime, reverse=True),
    }
    for name, files in log_targets.items():
        if files:
            errs = scan_log_errors(files[0])
            if errs:
                result[name] = errs
    return result


# ── 2. DB 통계 ──────────────────────────────────────────────────────────────

def get_db_stats() -> dict:
    """키워드 DB 현황 요약"""
    stats = {}
    if not DB_PATH.exists():
        return stats
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # 상태별 카운트
        cur.execute("SELECT status, COUNT(*) FROM keyword_blog_status GROUP BY status")
        for status, count in cur.fetchall():
            stats[status] = count

        # 블로그별 처리 불완전 카운트
        cur.execute("""
            SELECT blog_id, COUNT(*) FROM keyword_blog_status
            WHERE status='incomplete' GROUP BY blog_id ORDER BY COUNT(*) DESC
        """)
        incomplete = {row[0]: row[1] for row in cur.fetchall()}
        if incomplete:
            stats["incomplete_by_blog"] = incomplete

        # 오늘 발행 수
        today = datetime.now(KST).date().isoformat()
        cur.execute("""
            SELECT blog_id, COUNT(*) FROM keyword_blog_status
            WHERE status='published' AND updated_at >= ?
            GROUP BY blog_id
        """, (today,))
        stats["published_today"] = {row[0]: row[1] for row in cur.fetchall()}

        # pending 키워드 수
        try:
            cur.execute("SELECT COUNT(*) FROM keywords WHERE status='pending'")
            stats["pending_keywords"] = cur.fetchone()[0]
        except Exception:
            pass

        conn.close()
    except Exception as e:
        stats["db_error"] = str(e)
    return stats


# ── 3. 처리 불완전 블로그 재예약 시도 ──────────────────────────────────────

def retry_incomplete_keywords(limit: int = 3) -> int:
    """status=incomplete인 키워드를 pending으로 되돌려 다음 라운드에 재시도"""
    if not DB_PATH.exists():
        return 0
    try:
        conn = sqlite3.connect(DB_PATH)
        # incomplete → pending 으로 리셋 (오늘 것만, 반복 실패 방지 위해 retry_count 체크)
        today = datetime.now(KST).date().isoformat()
        try:
            conn.execute("ALTER TABLE keyword_blog_status ADD COLUMN retry_count INTEGER DEFAULT 0")
            conn.commit()
        except Exception:
            pass

        cur = conn.cursor()
        cur.execute("""
            SELECT keyword, blog_id, retry_count FROM keyword_blog_status
            WHERE status='incomplete' AND updated_at >= ?
            AND (retry_count IS NULL OR retry_count < 3)
            ORDER BY updated_at ASC LIMIT ?
        """, (today, limit))
        rows = cur.fetchall()

        count = 0
        for keyword, blog_id, retry_count in rows:
            rc = (retry_count or 0) + 1
            conn.execute("""
                UPDATE keyword_blog_status SET status='pending', retry_count=?
                WHERE keyword=? AND blog_id=?
            """, (rc, keyword, blog_id))
            _log(f"  재예약: [{blog_id}] {keyword} (retry #{rc})")
            count += 1

        conn.commit()
        conn.close()
        return count
    except Exception as e:
        _log(f"재예약 오류: {e}")
        return 0


# ── 4. nolja100 키워드 부족 감지 ──────────────────────────────────────────

def check_nolja100_keywords() -> str:
    """nolja100에 pending 키워드가 없으면 경고 반환"""
    if not DB_PATH.exists():
        return ""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM keyword_blog_status
            WHERE blog_id='nolja100' AND status='pending'
        """)
        count = cur.fetchone()[0]
        conn.close()
        if count == 0:
            return "⚠️ nolja100: 대기 키워드 0개 — 여행 키워드 추가 필요"
        return f"nolja100 대기 키워드: {count}개"
    except Exception:
        return ""


# ── 메인 ──────────────────────────────────────────────────────────────────

def main():
    now_kst = datetime.now(KST)
    _log(f"=== auto_health_fix 시작 ({now_kst.strftime('%Y-%m-%d %H:%M KST')}) ===")

    report_lines = [f"🔍 오프아워 자동 점검 ({now_kst.strftime('%m/%d %H:%M')})"]
    has_issue = False

    # 1. 로그 오류 스캔
    errors = get_recent_errors()
    if errors:
        has_issue = True
        report_lines.append("\n📋 최근 로그 오류:")
        for log_name, errs in errors.items():
            report_lines.append(f"  [{log_name}]")
            for e in errs[:3]:
                report_lines.append(f"    {e[:120]}")

    # 2. DB 통계
    stats = get_db_stats()
    published_today = stats.get("published_today", {})
    incomplete_by_blog = stats.get("incomplete_by_blog", {})
    pending_kw = stats.get("pending_keywords", "?")

    total_published = sum(published_today.values())
    report_lines.append(f"\n📊 오늘 발행: {total_published}건")
    if published_today:
        for blog, cnt in sorted(published_today.items()):
            report_lines.append(f"  {blog}: {cnt}건")

    if incomplete_by_blog:
        has_issue = True
        report_lines.append(f"\n⚠️ 처리 불완전:")
        for blog, cnt in incomplete_by_blog.items():
            report_lines.append(f"  {blog}: {cnt}건")

    # 3. 처리 불완전 재예약
    retried = retry_incomplete_keywords(limit=5)
    if retried:
        report_lines.append(f"\n🔄 {retried}건 재예약 완료 (다음 라운드 재시도)")

    # 4. nolja100 키워드 체크
    nolja_status = check_nolja100_keywords()
    if nolja_status.startswith("⚠"):
        has_issue = True
        report_lines.append(f"\n{nolja_status}")

    # 5. 대기 키워드 현황
    report_lines.append(f"\n🗂 대기 키워드: {pending_kw}개")

    # 6. overnight_run 마지막 실행
    gen_logs = sorted(LOGS_DIR.glob("gen_r*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    if gen_logs:
        last_run_sec = time.time() - gen_logs[0].stat().st_mtime
        last_run_h = last_run_sec / 3600
        status_emoji = "✅" if last_run_h < 8 else "⚠️"
        report_lines.append(f"\n{status_emoji} 마지막 overnight_run: {last_run_h:.1f}시간 전")
        if last_run_h > 8:
            has_issue = True

    msg = "\n".join(report_lines)
    _log(msg)

    # 이슈 있거나 낮 점검 시간(09:00)이면 전송, 이슈 없으면 조용히
    hour = now_kst.hour
    if has_issue or hour == 9:
        send_tg(msg)
        _log("텔레그램 보고 완료")
    else:
        _log("이상 없음 — 텔레그램 생략")

    # 로그 저장
    LOGS_DIR.mkdir(exist_ok=True)
    log_path = LOGS_DIR / "health_fix.log"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n{msg}\n")


if __name__ == "__main__":
    main()
