"""salim1su 전용 에이전트 — naver_agent 기반 + 세부 키워드 확장 + 키워드 자체 수집"""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from agents import naver_agent as _base
except ImportError:
    import naver_agent as _base

from claude_direct import generate_text
from image_router import generate_images_for_blog as _img_router
from overnight_run import _truncate_title, check_duplicate_post
from keyword_engine.db_handler import fetch_next_pending, set_keyword_status as _db_set_status
from keyword_crawler import _is_banned

try:
    import coupang_api
    _COUPANG_AVAILABLE = True
except ImportError:
    _COUPANG_AVAILABLE = False

BLOG_ID = "salim1su"
PERSONA_RULE = _base.PERSONA_RULE
_parse_raw = _base._parse_raw

_POLICY_KEYWORD_PATTERNS = [
    r"지원금", r"보조금", r"복지", r"바우처", r"급여", r"수당", r"감면",
    r"저소득", r"차상위", r"기초생활", r"수급자", r"취약계층",
    r"통신비\s*(지원|감면)", r"에너지바우처", r"주거급여", r"생계급여",
    r"정부지원", r"복지로", r"정부24",
]

# 쿠팡파트너스 삽입 허용 키워드 (제품 관련)
_COUPANG_PRODUCT_KEYWORDS = {
    "생활용품", "주방용품", "청소", "세제", "주방", "세탁",
    "수납", "정리함", "청소기", "걸레", "수세미", "바구니",
    "냄비", "프라이팬", "식기", "보관용기", "밀폐용기",
    "욕실", "화장실", "방향제", "섬유유연제", "세정제",
    "수건", "이불", "베개", "생필품", "가정용품",
}

# 쿠팡 삽입 금지 키워드 (정보성)
_COUPANG_BLOCK_KEYWORDS = {
    "전기요금", "도시가스", "가스요금", "수도요금", "관리비",
    "절약", "아끼는", "요금", "지원금", "보조금", "복지",
    "신청방법", "신청하는", "혜택", "정책", "제도",
}


def _needs_coupang(keyword: str, body: str = "") -> bool:
    """키워드/본문이 쿠팡 제품 링크가 필요한 내용인지 판단."""
    kw_lower = keyword.lower()
    # 금지 키워드 먼저 체크 (정보성 → 삽입 금지)
    for block in _COUPANG_BLOCK_KEYWORDS:
        if block in kw_lower or block in keyword:
            return False
    # 허용 키워드 체크 (제품 관련 → 삽입 허용)
    for allow in _COUPANG_PRODUCT_KEYWORDS:
        if allow in kw_lower or allow in keyword:
            return True
    # 본문에서 제품 관련 단어 등장 빈도 확인 (3회 이상이면 제품성 글로 판단)
    if body:
        count = sum(body.count(w) for w in _COUPANG_PRODUCT_KEYWORDS)
        if count >= 3:
            return True
    return False


def _collect_keyword(on_log=None):
    """SQLite DB에서 salim1su 대기 키워드를 수집한다.

    - 금칙어(banned) 또는 중복 발행 키워드는 건너뜀
    - 유효 키워드 발견 시 상태를 'in_progress'로 업데이트하고 keyword 반환
    - 없으면 None 반환
    """
    def log(msg):
        if on_log:
            on_log(msg)

    def _move_to_blog(keyword: str, target_blog: str, category: str, reason: str):
        log(f"[키워드수집] '{keyword}' — {reason}, {target_blog}로 이동")
        _db_set_status(keyword, "failed", blog_id=BLOG_ID)
        try:
            import sqlite3 as _sqlite3
            _db_path = Path(__file__).parent.parent / "keyword_engine" / "engine.db"
            with _sqlite3.connect(str(_db_path)) as _conn:
                _conn.execute("UPDATE keywords SET category = ?, status = 'pending' WHERE keyword = ?", (category, keyword))
                _conn.execute(
                    "INSERT OR IGNORE INTO keyword_blog_status (keyword, blog_id, status, updated_at) VALUES (?, ?, 'pending', datetime('now'))",
                    (keyword, target_blog),
                )
        except Exception as e:
            log(f"[키워드수집] 이동 처리 실패 (무시): {e}")

    def _is_policy_keyword(keyword: str) -> bool:
        return any(re.search(p, keyword) for p in _POLICY_KEYWORD_PATTERNS)

    # 부적합 키워드가 앞에 있어도 멈추지 않고 다음 후보를 계속 찾는다.
    for _ in range(10):
        keyword = fetch_next_pending(BLOG_ID)
        if not keyword:
            log("[키워드수집] 대기 키워드 없음")
            return None

        if _is_policy_keyword(keyword):
            _move_to_blog(keyword, "baremi542", "정부지원금", "정책/복지성 키워드")
            continue

        if _is_banned(keyword, BLOG_ID):
            log(f"[키워드수집] '{keyword}' — 금칙어, 건너뜀")
            _db_set_status(keyword, "failed", blog_id=BLOG_ID)
            continue

        break
    else:
        log("[키워드수집] 살림 블로그에 맞는 대기 키워드 없음")
        return None

    # salim1su 주제 필터: 지역명+업종 서비스 키워드 차단 → 기타로 이동
    _LOCAL_SERVICE_PATTERNS = [
        r'.{1,5}(에어컨|세탁기|보일러)(청소|분해|설치|이전|수리)',
        r'.{1,5}청소업체',
        r'(에어컨|세탁기|보일러)(청소|분해|설치|이전)(비용|가격|업체)',
        r'^(군포|시흥|수원|부천|인천|대전|대구|부산|광주|울산|천안|청주|전주)',
    ]
    import re as _re
    if any(_re.search(p, keyword) for p in _LOCAL_SERVICE_PATTERNS):
        _move_to_blog(keyword, "기타", "기타", "살림 블로그 주제 부적합 (지역서비스)")
        return None

    is_dup, matched = check_duplicate_post(BLOG_ID, keyword, on_log=log)
    if is_dup:
        log(f"[키워드수집] '{keyword}' — 중복 발행 ('{matched}'), 건너뜀")
        _db_set_status(keyword, "failed", blog_id=BLOG_ID)
        return None

    _db_set_status(keyword, "in_progress", blog_id=BLOG_ID)
    log(f"[키워드수집] '{keyword}' 수집 완료 → 진행중")
    return keyword


def _expand_keyword(keyword: str, on_log=None) -> str:
    """키워드를 살림이 블로그에 맞는 롱테일로 스마트 확장.

    단순 나열 요청이 아닌, 키워드 의도(DIY/서비스/절약/정보)를 판단해서
    살림이 독자가 실제로 검색할 법한 롱테일 1개를 선택.
    확장 실패 시 원본 키워드 반환.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    # 띄어쓰기가 있으면 이미 롱테일 → 건너뜀
    if " " in keyword.strip():
        log(f"[키워드확장] '{keyword}' — 이미 롱테일, 확장 생략")
        return keyword

    log(f"[키워드확장] '{keyword}' — 스마트 롱테일 확장 시작")

    expand_prompt = (
        "살림이(salim1su)는 30~40대 주부(5인 가족: 남편+본인+자녀 3명)가 운영하는 네이버 살림 블로그야.\n"
        "살림·청소·절약·생활정보·정부혜택을 다루고, 독자도 비슷한 주부층이야.\n\n"
        f"키워드 '{keyword}'를 이 블로그 독자가 실제로 네이버에서 검색할 법한 "
        f"구체적인 롱테일 키워드 5개로 확장해줘.\n\n"
        "키워드만 한 줄에 하나씩. 번호·설명·이유 없이."
    )

    try:
        from claude_direct import _run_claude
        response = _run_claude(expand_prompt, timeout=60, model_key="sonnet")
        if not response:
            log(f"[키워드확장] 응답 없음 — 원본 키워드 사용")
            return keyword

        # 응답에서 첫 번째 유효한 줄 선택
        lines = [
            line.strip() for line in response.strip().splitlines()
            if line.strip()
            and "===" not in line
            and not line.strip()[0].isdigit()
            and len(line.strip()) >= 5
            and "예시" not in line
            and "키워드" not in line
        ]
        if lines:
            expanded = lines[0]
            log(f"[키워드확장] '{keyword}' → '{expanded}' (sonnet 판단)")
            return expanded
        else:
            log(f"[키워드확장] 파싱 실패 — 원본 키워드 사용")
            return keyword
    except Exception as e:
        log(f"[키워드확장] 오류: {e} — 원본 키워드 사용")
        return keyword


def run(keyword: str = None, on_log=None, on_status=None, skip_images=False, extra_context=None):
    """글 + 이미지 생성 후 파싱된 결과를 반환한다.

    blog_id는 "salim1su"으로 고정됩니다.
    keyword=None 이면 _collect_keyword()로 직접 수집 (자체 완결 모드).
    단어 1개(띄어쓰기 없음)인 키워드는 claude.ai로 롱테일 확장 후 글 생성.

    Returns:
        dict: {
            "title": str,
            "body": str,
            "tags": list,
            "images": list[dict],
            "image_paths": dict,
            "raw": str,
        } or None
    """
    blog_id = BLOG_ID

    def log(msg):
        if on_log:
            on_log(msg)

    if on_status:
        on_status("writer", "working")

    # keyword가 없으면 SQLite DB에서 직접 수집
    if keyword is None:
        keyword = _collect_keyword(on_log=log)
        if not keyword:
            if on_status:
                on_status("writer", "failed")
            return None

    log(f"[{blog_id}] 페르소나 규칙 적용: {PERSONA_RULE}")

    # 1단계: 단어 1개 키워드면 세부 롱테일로 확장
    actual_keyword = _expand_keyword(keyword, on_log=log)

    # 2단계: 공통 리서치 컨텍스트 사용
    extra_ctx = extra_context

    # 3단계: Claude.ai 글 생성 (확장된 키워드로)
    log(f"[작성] {blog_id} / '{actual_keyword}' — Claude.ai 글 생성")
    raw = generate_text("", blog_id=blog_id, keyword=actual_keyword,
                        extra_context=extra_ctx,
                        on_log=log)

    if not raw or "추출 실패" in raw:
        log("[작성] 글 생성 실패")
        if on_status:
            on_status("writer", "failed")
        return None

    # 디버그: raw 전체 저장 (이미지 파싱 확인용)
    try:
        import tempfile, os
        dbg_path = os.path.join(tempfile.gettempdir(), "salim_raw_debug.txt")
        with open(dbg_path, "w", encoding="utf-8") as f:
            f.write(raw)
        log(f"[디버그] raw 저장됨: {dbg_path}")
    except Exception:
        pass

    # 파싱
    result = _parse_raw(raw, actual_keyword, log)
    if not result:
        if on_status:
            on_status("writer", "failed")
        return None

    # Gemini 이미지 생성 — 본문 이미지는 H2 소제목 개수와 동일하게만 생성
    # 썸네일은 orchestrator/posting pipeline에서 image_paths[0]으로 별도 생성한다.
    image_paths = {}

    # H2 소제목 개수 계산 — ## 마크다운 또는 [H2]...[/H2] 마커 모두 지원
    _body_txt = result["body"]
    h2_md = sum(1 for line in _body_txt.splitlines() if line.startswith("## "))
    h2_tag = len(re.findall(r'\[H2\]', _body_txt))
    h2_count = max(h2_md, h2_tag)
    required_count = h2_count
    log(f"[작성] H2 소제목 {h2_count}개 감지 (## {h2_md}개 / [H2] {h2_tag}개) → 이미지 {required_count}개 필요")

    # Claude가 썸네일을 이미지 목록에 섞어 주거나 H2보다 많이 만든 경우 본문용만 유지한다.
    if required_count > 0:
        result["images"] = [img for img in result["images"] if int(img.get("index", 0)) > 0][:required_count]
    else:
        result["images"] = []

    # 파싱된 이미지 목록이 부족하면 H2 소제목 기반 프롬프트로 채우기
    if len(result["images"]) < required_count:
        shortage = required_count - len(result["images"])
        # ## 또는 [H2] 소제목 텍스트 추출
        h2_lines = [l.lstrip('#').strip() for l in _body_txt.splitlines() if l.startswith("## ")]
        if not h2_lines:
            h2_lines = re.findall(r'\[H2\](.*?)\[/H2\]', _body_txt)
        log(f"[작성] 이미지 프롬프트 부족 ({len(result['images'])}개) → {shortage}개 H2 기반 프롬프트 생성")
        for i in range(shortage):
            idx = len(result["images"]) + 1
            h2_text = h2_lines[i] if i < len(h2_lines) else actual_keyword
            result["images"].append({
                "index": idx,
                "prompt": (
                    f"Korean home living scene: {h2_text}. "
                    "Bright natural light, clean tidy Korean apartment interior, "
                    "realistic style, no text, no watermark, no people. 16:9 ratio."
                ),
                "filename": f"img_{idx:02d}.jpg",
                "alt": f"{h2_text} 관련 이미지",
            })

    # 본문에 {{이미지N}} 마커가 없으면 H2 소제목 뒤에만 주입한다.
    # 남는 이미지를 글 상단에 몰아넣지 않는다.
    if result["images"] and not re.search(r'\{\{이미지[1-9]\d*\}\}', result["body"]):
        log("[작성] 본문에 이미지 마커 없음 → H2 소제목 뒤에 주입")
        body_lines = result["body"].split('\n')
        new_lines = []
        img_idx = 1
        total_imgs = len(result["images"])
        for line in body_lines:
            new_lines.append(line)
            if (line.startswith('## ') or re.match(r'\s*\[H2\].+?\[/H2\]\s*$', line)) and img_idx <= total_imgs:
                new_lines.append(f'{{{{이미지{img_idx}}}}}')
                img_idx += 1
        result["body"] = '\n'.join(new_lines)
        log(f"[작성] 이미지 마커 {img_idx - 1}개 주입 완료")

    if result["images"] and not skip_images:
        log(f"[작성] 이미지 {len(result['images'])}개 생성 시작 (salim1su: Gemini→Bing→Pollinations)")
        image_paths = _img_router("salim1su", result["images"], skip_webp=True, on_log=log, title=result.get("title", ""))
        log(f"[작성] 이미지 {len(image_paths)}개 생성 완료")

        # 생성 실패한 이미지 제거 + 본문 마커 정리
        failed = [img for img in result["images"] if img["index"] not in image_paths]
        if failed:
            for img in failed:
                log(f"[작성] ⚠ 이미지 {img['index']} 생성 실패 — 마커 제거")
            result["images"] = [img for img in result["images"] if img["index"] in image_paths]
            defined = {img["index"] for img in result["images"]}
            result["body"] = re.sub(
                r'\{\{이미지(\d+)\}\}\n?',
                lambda m: "" if int(m.group(1)) not in defined else m.group(0),
                result["body"],
            )

    result["image_paths"] = image_paths
    result["raw"] = raw
    result["used_keyword"] = actual_keyword

    # 쿠팡파트너스 블록 조건부 삽입
    if _COUPANG_AVAILABLE and _needs_coupang(actual_keyword, result["body"]):
        try:
            affiliate_block = coupang_api.get_affiliate_block(actual_keyword, BLOG_ID)
            if affiliate_block:
                result["body"] = result["body"] + affiliate_block
                log("[작성] 쿠팡파트너스 블록 삽입 완료")
            else:
                log("[작성] 쿠팡파트너스 블록 없음 (API 키 미설정 또는 결과 없음)")
        except Exception as e:
            log(f"[작성] 쿠팡파트너스 블록 삽입 오류 (스킵): {e}")
    else:
        log(f"[작성] 쿠팡파트너스 삽입 건너뜀 — 정보성 키워드 또는 모듈 없음")

    log(f"[작성] 완료 — 제목: \"{result['title']}\" / 본문: {len(result['body'])}자 / 태그: {len(result['tags'])}개")
    if on_status:
        on_status("writer", "done")
    return result
