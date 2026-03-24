"""스케줄러 — 7시~23시 사이 랜덤 간격으로 에이전트 파이프라인 실행"""
import os
import sys
import time
import random
import signal
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "agents"))

# .env 로드
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 설정
START_HOUR = 7
END_HOUR = 23
MIN_INTERVAL_MIN = 60    # 최소 간격 (분)
MAX_INTERVAL_MIN = 180   # 최대 간격 (분)
BLOG_ORDER = ["goodisak", "nolja100", "salim1su"]

# 키워드 엔진 — 매일 오전 8시 자동 실행
KEYWORD_ENGINE_HOUR = 8

_running = True
_keyword_engine_last_run = None  # 마지막 키워드 수집 날짜


def _signal_handler(sig, frame):
    global _running
    print("\n[스케줄러] 종료 신호 수신, 정리 중...")
    _running = False


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    # 로그 파일에도 기록
    log_file = LOG_DIR / "scheduler.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def is_active_hours():
    """현재 시각이 활동 시간(7~23시)인지 확인"""
    hour = datetime.now().hour
    return START_HOUR <= hour < END_HOUR


def next_active_time():
    """다음 활동 시간 시작까지 대기할 초 계산"""
    now = datetime.now()
    if now.hour >= END_HOUR:
        # 내일 7시
        tomorrow = now + timedelta(days=1)
        target = tomorrow.replace(hour=START_HOUR, minute=0, second=0)
    elif now.hour < START_HOUR:
        # 오늘 7시
        target = now.replace(hour=START_HOUR, minute=0, second=0)
    else:
        return 0
    return (target - now).total_seconds()


def get_random_interval():
    """랜덤 간격(분) 반환 — 블로그 간 자연스러운 시간차"""
    return random.randint(MIN_INTERVAL_MIN, MAX_INTERVAL_MIN) * 60


def run_cycle():
    """한 사이클: 블로그 순서대로 에이전트 실행"""
    from agents import orchestrator

    log("=" * 50)
    log("[스케줄러] 새 사이클 시작")
    log("=" * 50)

    results = []
    for blog_id in BLOG_ORDER:
        if not _running:
            break
        if not is_active_hours():
            log(f"[스케줄러] 활동 시간 종료 — {blog_id} 건너뜀")
            break

        log(f"[스케줄러] {blog_id} 파이프라인 시작")
        try:
            result = orchestrator.run_single(blog_id, on_log=log)
            results.append(result)

            if result["success"]:
                log(f"[스케줄러] {blog_id} 발행 완료: {result['title']}")
            else:
                log(f"[스케줄러] {blog_id} 실패: {result['reason']}")
        except Exception as e:
            log(f"[스케줄러] {blog_id} 오류: {e}")
            results.append({
                "success": False, "blog_id": blog_id,
                "title": "오류", "reason": str(e),
            })

        # 블로그 간 쿨다운 (5~15분 랜덤)
        if blog_id != BLOG_ORDER[-1] and _running and is_active_hours():
            cooldown = random.randint(5, 15) * 60
            log(f"[스케줄러] 다음 블로그까지 {cooldown // 60}분 대기")
            _sleep(cooldown)

    # 결과 요약 저장
    _save_cycle_result(results)
    return results


def _save_cycle_result(results):
    """사이클 결과를 result.txt에 저장"""
    result_file = LOG_DIR / "result.txt"
    lines = []
    if result_file.exists():
        lines = result_file.read_text(encoding="utf-8").splitlines()

    lines.append("")
    lines.append("=" * 50)
    lines.append(f"스케줄러 실행: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 50)

    for r in results:
        if r["success"]:
            lines.append(f"  {r['blog_id']}: {r['title']}")
        else:
            lines.append(f"  {r['blog_id']}: {r['reason']}")

    success = sum(1 for r in results if r["success"])
    lines.append(f"결과: {success}/{len(results)} 성공")

    result_file.write_text("\n".join(lines), encoding="utf-8")
    log(f"[스케줄러] 결과 저장 완료 ({success}/{len(results)})")


def _sleep(seconds):
    """중단 가능한 sleep"""
    end = time.time() + seconds
    while time.time() < end and _running:
        time.sleep(min(5, end - time.time()))


def run_keyword_engine():
    """천하무적 키워드 엔진 — 하루 1회 실행"""
    global _keyword_engine_last_run
    today = datetime.now().date()

    if _keyword_engine_last_run == today:
        return  # 오늘 이미 실행함

    log("[키워드엔진] 시작 — pub코드 역분석 + Tistory RSS 수집")
    try:
        from keyword_engine.main import run as run_engine
        # 4개 블로그 전체에 적재
        for blog_id in ["goodisak", "nolja100", "salim1su", "baremi542"]:
            run_engine(blog_id=blog_id, push_to_notion=True, on_log=log)
        _keyword_engine_last_run = today
        log("[키워드엔진] 완료")
    except Exception as e:
        log(f"[키워드엔진] 오류: {e}")


def main():
    log("[스케줄러] 시작")
    log(f"[스케줄러] 활동 시간: {START_HOUR}:00 ~ {END_HOUR}:00")
    log(f"[스케줄러] 간격: {MIN_INTERVAL_MIN}~{MAX_INTERVAL_MIN}분")
    log(f"[스케줄러] 블로그: {', '.join(BLOG_ORDER)}")

    while _running:
        # 활동 시간 확인
        if not is_active_hours():
            wait = next_active_time()
            wake_time = datetime.now() + timedelta(seconds=wait)
            log(f"[스케줄러] 비활동 시간 — {wake_time.strftime('%H:%M')}까지 대기")
            _sleep(wait)
            continue

        # 키워드 엔진 — 매일 오전 8시 1회 실행
        if datetime.now().hour == KEYWORD_ENGINE_HOUR:
            run_keyword_engine()

        # 사이클 실행
        run_cycle()

        if not _running:
            break

        # 다음 사이클까지 랜덤 대기
        interval = get_random_interval()
        next_run = datetime.now() + timedelta(seconds=interval)

        # 다음 실행이 활동 시간 밖이면 조정
        if next_run.hour >= END_HOUR or next_run.hour < START_HOUR:
            log(f"[스케줄러] 다음 사이클이 비활동 시간 — 내일로 연기")
            wait = next_active_time()
            if wait > 0:
                _sleep(wait)
            continue

        log(f"[스케줄러] 다음 사이클: {next_run.strftime('%H:%M')} ({interval // 60}분 후)")
        _sleep(interval)

    log("[스케줄러] 종료")


if __name__ == "__main__":
    main()
