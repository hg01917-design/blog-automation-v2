"""오케스트레이터 — 에이전트 팀 순차 실행, 체크포인트 지원"""
import sys
import time
import json
import textwrap
import traceback
import importlib
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import keyword_agent
import common_review_agent
import poster_agent
import fix_agent
import research_agent
from config import is_naver_blog

# .env 로드 (.app 번들 실행 시 프로젝트 루트 사용)
import os as _os
_env_path = Path(_os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent.parent))) / ".env"
if _env_path.exists():
    import os
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# .app 번들 안에서 실행 시 logs 폴더를 번들 밖(프로젝트 루트)으로 설정
if getattr(sys, "frozen", False):
    # sys.executable = .../Blog Automation v2.app/Contents/MacOS/Blog Automation v2
    _base_dir = Path(sys.executable).parent.parent.parent.parent.parent
else:
    _base_dir = Path(__file__).parent.parent
LOG_DIR = _base_dir / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

CHECKPOINT_FILE = LOG_DIR / "checkpoint.json"

# 기본 블로그 순서
DEFAULT_BLOG_ORDER = [
    "goodisak", "nolja100", "salim1su", "baremi542",
    "woll100", "phn0502", "triplog", "me1091",
    "blogspot_travel", "blogspot_it", "blogspot_daily",
]

MAX_WRITER_RETRIES = 2      # 검수 불합격 시 재생성 횟수

# 블로그 ID → 전용 에이전트 모듈명 매핑
BLOG_AGENT_MAP = {
    "goodisak":        "goodisak_agent",
    "nolja100":        "nolja100_agent",
    "salim1su":        "salim1su_agent",
    "baremi542":       "baremi542_agent",
    "woll100":         "woll100_agent",
    "phn0502":         "phn0502_agent",
    "triplog":         "triplog_agent",
    "me1091":          "me1091_agent",
    "blogspot_travel": "blogspot_travel_agent",
    "blogspot_it":     "blogspot_it_agent",
    "blogspot_daily":  "blogspot_daily_agent",
}

AGENTS_DIR = Path(__file__).parent


# ── 체크포인트 ──────────────────────────────────────────────────────────────

def _load_checkpoint() -> dict:
    """오늘 날짜의 체크포인트 로드. 없거나 날짜 다르면 빈 dict."""
    try:
        if CHECKPOINT_FILE.exists():
            data = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
            if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                return data
    except Exception:
        pass
    return {}


def _save_checkpoint(completed: list, next_blog):
    """완료된 블로그 목록 + 다음 블로그를 체크포인트에 저장."""
    data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "completed": completed,
        "next": next_blog,
        "updated_at": datetime.now().isoformat(),
    }
    CHECKPOINT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _clear_checkpoint():
    try:
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
    except Exception:
        pass


# ── 신규 블로그 감지 + 템플릿 자동 생성 ───────────────────────────────────

def _detect_new_blogs():
    """config.py의 ACCOUNTS와 agents/ 폴더를 비교해
    전용 에이전트가 없는 블로그를 감지하고 템플릿을 자동 생성한다."""
    try:
        import config
        accounts = config.ACCOUNTS
    except Exception as e:
        print(f"[오케스트레이터] config 로드 실패: {e}", flush=True)
        return

    existing_agents = {p.stem for p in AGENTS_DIR.glob("*_agent.py")}
    ts = datetime.now().strftime("%H:%M:%S")

    for account in accounts:
        blog_id = account["blog"]
        category = account.get("category", "미분류")
        mapped = BLOG_AGENT_MAP.get(blog_id)

        if mapped is None:
            # BLOG_AGENT_MAP에 매핑 없음 — 자동으로 추가
            new_name = f"{blog_id}_agent"
            BLOG_AGENT_MAP[blog_id] = new_name
            mapped = new_name
            print(f"[{ts}] [자기확장] '{blog_id}' 매핑 자동 추가 → {new_name}", flush=True)

        if mapped not in existing_agents:
            _generate_agent_template(blog_id, mapped, category)
            print(f"[{ts}] [자기확장] ✔ '{blog_id}' 템플릿 자동 생성: {mapped}.py", flush=True)
        else:
            print(f"[{ts}] [자기확장] ✔ '{blog_id}'({category}) → {mapped}.py 확인됨", flush=True)


def _generate_agent_template(blog_id: str, module_name: str, category: str):
    """신규 블로그용 에이전트 템플릿 파일을 자동 생성한다."""
    agent_file = AGENTS_DIR / f"{module_name}.py"
    if agent_file.exists():
        return  # 이미 존재하면 건드리지 않음

    template = textwrap.dedent(f'''\
        """auto-generated agent for {blog_id} — {category}"""
        import re
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent.parent))

        from claude_direct import generate_text
        from image_router import generate_images_for_blog as _img_router
        from overnight_run import _truncate_title

        BLOG_ID = "{blog_id}"
        PERSONA_RULE = "{category} 블로그 전문 정보 전달"


        def run(keyword: str, on_log=None, on_status=None):
            blog_id = BLOG_ID

            def log(msg):
                if on_log:
                    on_log(msg)

            if on_status:
                on_status("writer", "working")

            log(f"[{{blog_id}}] 페르소나: {{PERSONA_RULE}}")
            log(f"[작성] {{blog_id}} / \'{{keyword}}\' — Claude.ai 글 생성")
            raw = generate_text("", blog_id=blog_id, keyword=keyword, on_log=log)

            if not raw or "추출 실패" in raw:
                log("[작성] ⚠ 글 생성 실패")
                if on_status:
                    on_status("writer", "failed")
                return None

            result = _parse_raw(raw, keyword, log)
            if not result:
                if on_status:
                    on_status("writer", "failed")
                return None

            image_paths = {{}}
            if result["images"]:
                _is_naver = (blog_id == "salim1su")
                log(f"[작성] 이미지 {{len(result[\'images\'])}}개 생성 시작 (blog={{blog_id}})")
                image_paths = _img_router(blog_id, result["images"], skip_webp=_is_naver, on_log=log)

            result["image_paths"] = image_paths
            result["raw"] = raw

            log(f"[작성] ✓ 완료 — 제목: \\"{{result[\'title\']}}\\"")
            if on_status:
                on_status("writer", "done")
            return result


        def _parse_raw(raw, keyword, log):
            """===섹션=== 형식의 raw 텍스트를 파싱한다."""
            title_m = re.search(r"===제목===\\s*\\n(.*?)\\n*===제목끝===", raw, re.DOTALL)
            body_m  = re.search(r"===본문===\\s*\\n(.*?)\\n*===본문끝===", raw, re.DOTALL)
            tag_m   = re.search(r"===태그===\\s*\\n(.*?)\\n*===태그끝===", raw, re.DOTALL)
            img_m   = re.search(r"===이미지===\\s*\\n(.*?)\\n*===이미지끝===", raw, re.DOTALL)

            raw_title = title_m.group(1).strip().split("\\n")[0].strip() if title_m else keyword
            title = _truncate_title(raw_title, max_len=40)
            body  = body_m.group(1).strip() if body_m else raw

            if tag_m:
                tag_raw = tag_m.group(1).strip()
                tags = [t.strip() for line in tag_raw.split('\n') for t in line.split(',') if t.strip()]
            else:
                tags = [keyword]

            images = []
            if img_m:
                img_block = img_m.group(1)
                # [이미지N] 단위로 분할: split 결과 = [앞텍스트, index, 블록, index, 블록, ...]
                parts = re.split(r'\[이미지(\d+)\]', img_block)
                it = iter(parts[1:])
                for idx_str, block in zip(it, it):
                    prompt = re.search(r'Gemini\s*프롬프트\s*[:：]\s*(.+)', block)
                    fname  = re.search(r'파일명\s*[:：]\s*(.+)', block)
                    alt_m2 = re.search(r'\balt\s*[:：]\s*(.+)', block, re.IGNORECASE)
                    if prompt and fname:
                        images.append({{
                            "index": int(idx_str),
                            "prompt": prompt.group(1).strip(),
                            "filename": fname.group(1).strip(),
                            "alt": alt_m2.group(1).strip() if alt_m2 else "",
                        }})

            if images:
                defined = {{img["index"] for img in images}}
                body = re.sub(
                    r\'\\{{\\{{이미지(\\d+)\\}}\\}}\',
                    lambda m: "" if int(m.group(1)) not in defined else m.group(0),
                    body,
                )
            else:
                body = re.sub(r\'\\{{\\{{이미지\\d+\\}}\\}}\\n?\', "", body)

            plain = re.sub(r"##.*|{{{{.*?}}}}|\\[애드센스\\]|\\|.*", "", body)
            char_count = len(re.sub(r"\\s+", "", plain))

            log(f"[파싱] 제목: \\"{{title}}\\" ({{len(title)}}자)")
            log(f"[파싱] 본문: {{char_count}}자 / 태그: {{len(tags)}}개 / 이미지: {{len(images)}}개")

            if char_count < 100:
                log("[파싱] ⚠ 본문 너무 짧음")
                return None

            return {{"title": title, "body": body, "tags": tags, "images": images}}
    ''')

    agent_file.write_text(template, encoding="utf-8")


# ── 단일 실행 ───────────────────────────────────────────────────────────────

def run_single(blog_id: str, keyword: str = None, page_id: str = None,
               on_log=None, on_status=None, forced_title: str = None):
    """한 블로그에 대해 전체 파이프라인 실행.

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

    # ── 전용 writer 에이전트 동적 로드 ──
    agent_module_name = BLOG_AGENT_MAP.get(blog_id)
    active_writer = None
    if agent_module_name:
        agent_file = AGENTS_DIR / f"{agent_module_name}.py"
        if agent_file.exists():
            try:
                active_writer = importlib.import_module(agent_module_name)
                log(f"[오케스트레이터] 전용 에이전트 로드: {agent_module_name}")
            except Exception as e:
                log(f"[오케스트레이터] 전용 에이전트 로드 실패 ({agent_module_name}): {e}")
        else:
            log(f"[오케스트레이터] {agent_module_name}.py 없음")

    if active_writer is None:
        log(f"[오케스트레이터] '{blog_id}' 전용 에이전트 없음 — 건너뜀")
        return _fail(blog_id, keyword or "없음", "전용 에이전트 없음", logs)

    try:
        # ── 1. 키워드 선택 ──
        if keyword:
            kw_result = {"keyword": keyword, "page_id": page_id or ""}
            log(f"[키워드] 지정 키워드: '{keyword}'")
        else:
            kw_result = keyword_agent.run(blog_id, on_log=log, on_status=on_status)

        if not kw_result:
            return _fail(blog_id, keyword or "없음", "대기 키워드 없음", logs)

        keyword = kw_result["keyword"]
        page_id = kw_result["page_id"]

        research_context = None
        try:
            rs = research_agent.run(keyword, blog_id, on_log=log)
            if rs.get("success") and rs.get("context"):
                research_context = rs["context"]
                log(f"[오케스트레이터] 공통 리서치 완료 ({len(research_context)}자)")
            else:
                log("[오케스트레이터] 공통 리서치 결과 없음 — 기본 생성 진행")
        except Exception as _re:
            log(f"[오케스트레이터] 공통 리서치 오류 (무시): {_re}")

        # ── 2~3. 글 생성 + 통합 검수 (최대 MAX_WRITER_RETRIES회) ──
        result = None
        for attempt in range(1, MAX_WRITER_RETRIES + 1):
            if attempt > 1:
                log(f"[오케스트레이터] === 재생성 {attempt}/{MAX_WRITER_RETRIES} ===")

            result = active_writer.run(
                keyword,
                on_log=log,
                on_status=on_status,
                skip_images=True,
                extra_context=research_context,
            )
            if not result:
                continue

            review_keyword = result.get("used_keyword") or keyword
            review = common_review_agent.run(
                result, review_keyword, blog_id, on_log=log, on_status=on_status
            )
            if review["passed"]:
                result = review["result"]
                break

            issues = review["issues"]

            # 주제 불일치(키워드 없음)는 패치 불가 — 다음 루프에서 재생성
            if any("메인키워드" in i for i in issues):
                log(f"[오케스트레이터] 주제 불일치 감지 — 재생성 시도")
                result = None
                continue

            # 1차 수정: 단순 패턴 치환 (빠름)
            fixed = fix_agent.run(review["result"], issues, blog_id, on_log=log)
            if fixed:
                review2 = common_review_agent.run(
                    fixed, review_keyword, blog_id, on_log=log, on_status=on_status
                )
                if review2["passed"]:
                    log("[오케스트레이터] ✓ 패턴 치환 후 검수 통과")
                    result = review2["result"]
                    break
                issues = review2["issues"]

            # 2차 수정: Claude에 기존 글 + 이슈 전달해서 부분 수정
            # issues가 빈 리스트면 final_review 실패 — reason 문자열을 이슈로 사용
            issues_for_repair = issues if issues else [
                review.get("reason", "AI 패턴 및 자연스럽지 않은 문체 수정 필요")
            ]
            log(f"[오케스트레이터] 부분 수정 시도 ({len(issues_for_repair)}건)...")
            from claude_direct import repair_text
            # raw 없으면 원본 result에서 폴백
            raw_to_fix = (
                (fixed or review["result"]).get("raw", "")
                or result.get("raw", "")
            )
            if raw_to_fix:
                repaired_raw = repair_text(raw_to_fix, issues_for_repair, on_log=log)
                if repaired_raw:
                    # raw를 파싱해서 result 재구성
                    try:
                        repaired_result = active_writer._parse_raw(repaired_raw, keyword, log)
                        if repaired_result:
                            repaired_result["raw"] = repaired_raw
                            repaired_result["image_paths"] = result.get("image_paths", {})
                            review3 = common_review_agent.run(
                                repaired_result, review_keyword, blog_id, on_log=log, on_status=on_status
                            )
                            if review3["passed"]:
                                log("[오케스트레이터] ✓ 부분 수정 후 검수 통과")
                                result = review3["result"]
                                break
                    except Exception as e:
                        log(f"[오케스트레이터] 부분 수정 파싱 오류: {e}")
            else:
                log("[오케스트레이터] raw 텍스트 없음 — 부분 수정 건너뜀")

            log(f"[오케스트레이터] 검수 불합격 — 수정 후에도 미통과")
            result = None

        if not result:
            if keyword:
                from keyword_engine import db_handler as _db
                _db.set_keyword_status(keyword, "failed", blog_id)
            return _fail(blog_id, keyword, f"검수 불합격 ({MAX_WRITER_RETRIES}회)", logs)

        # ── 3-b. 검수 통과 후 이미지 생성 ──
        from image_router import generate_images_for_blog as _img_gen, generate_thumbnail
        _is_naver = is_naver_blog(blog_id)
        _img_paths = {}

        # 본문 이미지 생성 (이미지 명세가 있을 때만)
        # 에이전트가 이미 생성한 image_paths가 있으면 재사용 (Gemini 중복 호출 방지)
        _agent_img_paths = {k: v for k, v in (result.get("image_paths") or {}).items()
                            if k != 0 and v and __import__('pathlib').Path(v).is_file()}
        if _agent_img_paths:
            log(f"[오케스트레이터] 에이전트 생성 이미지 재사용: {sorted(_agent_img_paths.keys())}개")
            _img_paths = _agent_img_paths
        elif result.get("images"):
            try:
                log(f"[오케스트레이터] 검수 통과 → 이미지 {len(result['images'])}개 생성 시작")
                _img_paths = _img_gen(
                    blog_id=blog_id,
                    image_infos=result["images"],
                    skip_webp=_is_naver,
                    on_log=log,
                    title=result.get("title", ""),
                )
                log(f"[오케스트레이터] 이미지 {len(_img_paths)}개 생성 완료 — keys: {sorted(_img_paths.keys())}")
            except Exception as _ie:
                log(f"[오케스트레이터] 본문 이미지 생성 오류 (무시): {_ie}")

        # 썸네일은 항상 생성 (본문 이미지 유무와 무관)
        try:
            _thumb = generate_thumbnail(blog_id, keyword, result["title"], on_log=log)
            if _thumb:
                _img_paths[0] = _thumb
                # 도입부 끝(첫 번째 소제목 앞)에 {{이미지0}} 삽입 — 본문에 썸네일 표시
                _body = result.get("body", "")
                if _body and "{{이미지0}}" not in _body:
                    # [이미지N] 블록 안의 [H2]를 잡지 않도록 줄 시작(^) 앵커 필수
                    _h2 = re.search(r'^\s*(#{1,3}\s|\[H2\])', _body, re.MULTILINE)
                    _ins = _h2.start() if _h2 else len(_body)
                    result["body"] = (
                        _body[:_ins].rstrip() + "\n\n{{이미지0}}\n\n" + _body[_ins:].lstrip()
                    )
        except Exception as _te:
            log(f"[오케스트레이터] 썸네일 생성 오류 (무시): {_te}")

        log(f"[오케스트레이터] image_paths 확정: {sorted(_img_paths.keys())} ({len(_img_paths)}개)")
        result["image_paths"] = _img_paths

        # ── 4. 포스팅 (forced_title 지정 시 제목 교체) ──
        if forced_title and result:
            result["title"] = forced_title
            log(f"[오케스트레이터] ✎ 강제 제목 적용: '{forced_title}'")

        post_result = poster_agent.run(
            result, blog_id, keyword, page_id,
            on_log=log, on_status=on_status
        )

        if post_result["posted"]:
            # ── 5. 포스팅 후 검수 ──
            try:
                post_review = common_review_agent.run_post(
                    blog_id,
                    post_result["title"],
                    on_log=log,
                    on_status=on_status,
                )
                if not post_review["passed"]:
                    log(f"[오케스트레이터] 포스팅후검수 이슈 {len(post_review['issues'])}건 "
                        f"(fixed={post_review['fixed']}): "
                        f"{post_review['issues'][:2]}")
                else:
                    log("[오케스트레이터] ✓ 포스팅후검수 통과")
            except Exception as _pr_err:
                log(f"[오케스트레이터] 포스팅후검수 오류 (무시): {_pr_err}")

            return _success(blog_id, post_result["title"], logs)
        else:
            return _fail(blog_id, keyword, "포스팅 실패", logs)

    except Exception as e:
        log(f"[오케스트레이터] 치명적 오류: {e}")
        log(traceback.format_exc())
        try:
            if keyword:
                from keyword_engine import db_handler as _db
                _db.set_keyword_status(keyword, "failed", blog_id)
        except Exception:
            pass
        return _fail(blog_id, keyword or "알수없음", f"오류: {e}", logs)


# ── 전체 실행 (체크포인트 지원) ────────────────────────────────────────────

def run_all(blog_ids=None, on_log=None, on_status=None):
    """여러 블로그 순차 실행. 체크포인트에서 재개 가능.

    Returns:
        list[dict]: 각 블로그 결과
    """
    _detect_new_blogs()

    if blog_ids is None:
        blog_ids = DEFAULT_BLOG_ORDER

    # 체크포인트 로드
    cp = _load_checkpoint()
    completed_ids = set(cp.get("completed", []))
    if completed_ids:
        skipped = [b for b in blog_ids if b in completed_ids]
        if skipped and on_log:
            on_log(f"[오케스트레이터] 체크포인트 재개 — 완료된 블로그 건너뜀: {skipped}")

    results = []
    remaining = [b for b in blog_ids if b not in completed_ids]

    for i, blog_id in enumerate(remaining):
        next_blog = remaining[i + 1] if i + 1 < len(remaining) else None
        result = run_single(blog_id, on_log=on_log, on_status=on_status)
        results.append(result)

        # 체크포인트 저장
        completed_ids.add(blog_id)
        _save_checkpoint(list(completed_ids), next_blog)

        time.sleep(5)  # 블로그 간 쿨다운

    # 모든 블로그 완료 → 체크포인트 삭제
    _clear_checkpoint()
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
    result_file = LOG_DIR / "result.txt"
    lines = []
    if result_file.exists():
        lines = result_file.read_text(encoding="utf-8").splitlines()

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

    if args.all or not args.blog:
        results = run_all()
    else:
        result = run_single(args.blog, keyword=args.keyword)

    print("\n" + "="*50)
    print("[최종 결과]")
    print("="*50)
    result_file = LOG_DIR / "result.txt"
    if result_file.exists():
        content = result_file.read_text(encoding="utf-8")
        last_run = content.split("="*50)[-1] if "="*50 in content else content
        print(last_run)
