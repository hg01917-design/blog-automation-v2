"""오케스트레이터 — 에이전트 팀 순차 실행, 사람 개입 없음"""
import sys
import time
import traceback
import importlib
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import keyword_agent
import writer_agent
import review_agent
import final_review_agent
import poster_agent

# .env 로드
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    import os
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 기본 블로그 순서
DEFAULT_BLOG_ORDER = ["goodisak", "nolja100", "salim1su"]

MAX_WRITER_RETRIES = 3       # review 불합격 시 재생성
MAX_FINAL_RETRIES = 2        # final_review 불합격 시 재생성

# 블로그 ID → 전용 에이전트 모듈명 매핑
BLOG_AGENT_MAP = {
    "goodisak": "it_agent",
    "nolja100": "nolja_agent",
    "salim1su": "naver_agent",
    "baremi542": "wordpress_agent",
}

AGENTS_DIR = Path(__file__).parent


def _detect_new_blogs():
    """config.py의 ACCOUNTS와 agents/ 폴더의 *_agent.py 파일을 비교해
    전용 에이전트가 없는 블로그를 감지하고 경고 로그를 출력한다."""
    try:
        import config
        accounts = config.ACCOUNTS
    except Exception as e:
        print(f"[오케스트레이터] config 로드 실패: {e}", flush=True)
        return

    # agents/ 폴더에 존재하는 *_agent.py 파일 수집 (orchestrator 제외)
    existing_agents = {
        p.stem
        for p in AGENTS_DIR.glob("*_agent.py")
    }

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [자기확장 감지] 등록된 에이전트: {sorted(existing_agents)}", flush=True)

    for account in accounts:
        blog_id = account["blog"]
        category = account.get("category", "미분류")
        mapped_agent = BLOG_AGENT_MAP.get(blog_id)

        if mapped_agent is None:
            # BLOG_AGENT_MAP에 매핑 자체가 없는 경우
            print(
                f"[{ts}] [자기확장 감지] ⚠ '{blog_id}'({category}) — "
                f"BLOG_AGENT_MAP에 매핑이 없습니다. 추가가 필요합니다.",
                flush=True,
            )
        elif mapped_agent not in existing_agents:
            # 매핑은 있지만 파일이 없는 경우
            print(
                f"[{ts}] [자기확장 감지] ⚠ '{blog_id}'({category}) → "
                f"agents/{mapped_agent}.py 없음. 전용 에이전트 생성이 필요합니다.",
                flush=True,
            )
        else:
            print(
                f"[{ts}] [자기확장 감지] ✔ '{blog_id}'({category}) → "
                f"{mapped_agent}.py 확인됨",
                flush=True,
            )


def run_single(blog_id: str, keyword: str = None, page_id: str = None,
               on_log=None, on_status=None):
    """한 블로그에 대해 전체 파이프라인 실행.

    keyword/page_id가 None이면 keyword_agent가 자동 선택.

    Returns:
        dict: {"success": bool, "title": str, "blog_id": str, "reason": str}
    """
    logs = []

    def log(msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        logs.append(line)
        print(line, flush=True)
        if on_log:
            on_log(msg)

    log(f"{'='*50}")
    log(f"[오케스트레이터] {blog_id} 파이프라인 시작")
    log(f"{'='*50}")

    # ── 전용 writer 에이전트 동적 로드 (없으면 기본 writer_agent 폴백) ──
    agent_module_name = BLOG_AGENT_MAP.get(blog_id)
    active_writer = writer_agent  # 기본값
    if agent_module_name:
        agent_file = AGENTS_DIR / f"{agent_module_name}.py"
        if agent_file.exists():
            try:
                active_writer = importlib.import_module(agent_module_name)
                log(f"[오케스트레이터] 전용 에이전트 로드: {agent_module_name}")
            except Exception as e:
                log(f"[오케스트레이터] 전용 에이전트 로드 실패 ({agent_module_name}): {e} — writer_agent 폴백")
        else:
            log(f"[오케스트레이터] {agent_module_name}.py 없음 — writer_agent 폴백")
    else:
        log(f"[오케스트레이터] BLOG_AGENT_MAP 미등록 블로그 '{blog_id}' — writer_agent 폴백")

    try:
        # ── 1. 키워드 선택 ──
        if keyword and page_id:
            kw_result = {"keyword": keyword, "page_id": page_id}
            log(f"[키워드] 지정 키워드: '{keyword}'")
        else:
            kw_result = keyword_agent.run(blog_id, on_log=log, on_status=on_status)

        if not kw_result:
            return _fail(blog_id, keyword or "없음", "대기 키워드 없음", logs)

        keyword = kw_result["keyword"]
        page_id = kw_result["page_id"]

        # ── 2~3. 글 생성 + 자동 검수 (최대 3회) ──
        result = None
        for attempt in range(1, MAX_WRITER_RETRIES + 1):
            if attempt > 1:
                log(f"[오케스트레이터] === 재생성 {attempt}/{MAX_WRITER_RETRIES} ===")

            # 2. 글 생성
            result = active_writer.run(blog_id, keyword, on_log=log, on_status=on_status)
            if not result:
                continue

            # 3. 자동 검수
            review = review_agent.run(
                result, keyword, blog_id, on_log=log, on_status=on_status
            )
            if review["passed"]:
                result = review["result"]
                break

            # 불합격 — 재생성
            log(f"[오케스트레이터] 자동 검수 불합격 — 재생성 시도")
            result = None

        if not result:
            from overnight_run import update_keyword_status
            update_keyword_status(page_id, "실패", memo="검수 불합격")
            return _fail(blog_id, keyword, "자동 검수 불합격 (3회)", logs)

        # ── 4. 최종 검토 (최대 2회) ──
        for attempt in range(1, MAX_FINAL_RETRIES + 1):
            if attempt > 1:
                log(f"[오케스트레이터] === 최종검토 재시도 {attempt}/{MAX_FINAL_RETRIES} ===")
                # 재생성
                result = active_writer.run(blog_id, keyword, on_log=log, on_status=on_status)
                if not result:
                    break

            final = final_review_agent.run(
                result, keyword, blog_id, on_log=log, on_status=on_status
            )
            if final["passed"]:
                result = final["result"]
                break

            log(f"[오케스트레이터] 최종 검토 불합격: {final['reason'][:100]}")
            result = None

        if not result:
            from overnight_run import update_keyword_status
            update_keyword_status(page_id, "실패", memo="최종검토 불합격")
            return _fail(blog_id, keyword, "최종 검토 불합격", logs)

        # ── 5. 포스팅 ──
        post_result = poster_agent.run(
            result, blog_id, keyword, page_id,
            on_log=log, on_status=on_status
        )

        if post_result["posted"]:
            return _success(blog_id, post_result["title"], logs)
        else:
            return _fail(blog_id, keyword, "포스팅 실패", logs)

    except Exception as e:
        log(f"[오케스트레이터] 치명적 오류: {e}")
        log(traceback.format_exc())
        try:
            if page_id:
                from overnight_run import update_keyword_status
                update_keyword_status(page_id, "실패", memo=f"오류: {str(e)[:50]}")
        except Exception:
            pass
        return _fail(blog_id, keyword or "알수없음", f"오류: {e}", logs)


def run_all(blog_ids=None, on_log=None, on_status=None):
    """여러 블로그 순차 실행.

    Returns:
        list[dict]: 각 블로그 결과
    """
    # 새 블로그/전용 에이전트 누락 여부 자동 감지
    _detect_new_blogs()

    if blog_ids is None:
        blog_ids = DEFAULT_BLOG_ORDER

    results = []
    for blog_id in blog_ids:
        result = run_single(blog_id, on_log=on_log, on_status=on_status)
        results.append(result)
        time.sleep(5)  # 블로그 간 쿨다운

    # 결과 저장
    _save_results(results)
    return results


def _success(blog_id, title, logs):
    result = {
        "success": True,
        "blog_id": blog_id,
        "title": title,
        "reason": "발행 완료",
        "logs": logs,
    }
    _save_results([result])
    return result


def _fail(blog_id, keyword, reason, logs):
    result = {
        "success": False,
        "blog_id": blog_id,
        "title": keyword,
        "reason": reason,
        "logs": logs,
    }
    _save_results([result])
    return result


def _save_results(results):
    """결과를 logs/result.txt에 저장"""
    result_file = LOG_DIR / "result.txt"

    lines = []
    # 기존 내용 읽기
    if result_file.exists():
        lines = result_file.read_text(encoding="utf-8").splitlines()

    # 구분선 + 날짜
    lines.append("")
    lines.append(f"{'='*50}")
    lines.append(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"{'='*50}")

    for r in results:
        if r["success"]:
            lines.append(f"✅ 발행 완료: {r['title']} ({r['blog_id']})")
        else:
            lines.append(f"❌ 실패: {r['title']} - {r['reason']}")

    result_file.write_text("\n".join(lines), encoding="utf-8")


# ─── 단독 실행 ───
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog", type=str, help="블로그 ID")
    parser.add_argument("--keyword", type=str, help="키워드 (지정 시)")
    parser.add_argument("--all", action="store_true", help="전체 블로그 순환")
    args = parser.parse_args()

    if args.all:
        results = run_all()
    elif args.blog:
        result = run_single(args.blog, keyword=args.keyword)
    else:
        results = run_all()

    print("\n" + "="*50)
    print("[최종 결과]")
    print("="*50)
    result_file = LOG_DIR / "result.txt"
    if result_file.exists():
        # 마지막 실행 결과만 출력
        content = result_file.read_text(encoding="utf-8")
        last_run = content.split("="*50)[-1] if "="*50 in content else content
        print(last_run)
