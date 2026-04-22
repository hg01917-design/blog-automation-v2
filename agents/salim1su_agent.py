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
    from agents import fact_collect as _fact_collect
except ImportError:
    import fact_collect as _fact_collect

try:
    import coupang_api
    _COUPANG_AVAILABLE = True
except ImportError:
    _COUPANG_AVAILABLE = False

BLOG_ID = "salim1su"
PERSONA_RULE = _base.PERSONA_RULE
_parse_raw = _base._parse_raw

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

    keyword = fetch_next_pending(BLOG_ID)
    if not keyword:
        log("[키워드수집] 대기 키워드 없음")
        return None

    if _is_banned(keyword, BLOG_ID):
        log(f"[키워드수집] '{keyword}' — 금칙어, 건너뜀")
        _db_set_status(keyword, "failed", blog_id=BLOG_ID)
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
    """단어 1개(띄어쓰기 없음)인 키워드를 세부 롱테일로 확장.

    claude.ai에 세부 롱테일 키워드 5개를 요청하고 첫 번째 줄을 반환.
    확장 실패 시 원본 키워드 반환.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    # 띄어쓰기가 있으면 이미 롱테일 → 건너뜀
    if " " in keyword.strip():
        log(f"[키워드확장] '{keyword}' — 이미 롱테일, 확장 생략")
        return keyword

    log(f"[키워드확장] '{keyword}' — 세부 롱테일 확장 시작")

    expand_prompt = (
        f"키워드: {keyword}\n"
        "이 키워드로 네이버 블로그에 쓸 수 있는 세부 롱테일 키워드 5개 뽑아줘.\n"
        "조건: 실제 검색할 것 같은 표현, 중복 의미 없이, 번호 없이 한 줄에 하나씩만"
    )

    try:
        response = generate_text(expand_prompt, blog_id=BLOG_ID, keyword=keyword, on_log=log)
        if not response or "추출 실패" in response:
            log(f"[키워드확장] 응답 없음 — 원본 키워드 사용")
            return keyword

        # 응답에서 첫 번째 비어있지 않은 줄 선택
        lines = [line.strip() for line in response.strip().splitlines() if line.strip()]
        if lines:
            expanded = lines[0]
            log(f"[키워드확장] '{keyword}' → '{expanded}'")
            return expanded
        else:
            log(f"[키워드확장] 파싱 실패 — 원본 키워드 사용")
            return keyword
    except Exception as e:
        log(f"[키워드확장] 오류: {e} — 원본 키워드 사용")
        return keyword


def run(keyword: str = None, on_log=None, on_status=None):
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

    # 2단계: 사전 팩트 수집
    fc = _fact_collect.collect(actual_keyword, blog_id, on_log=log)

    # 3단계: Claude.ai 글 생성 (확장된 키워드로)
    log(f"[작성] {blog_id} / '{actual_keyword}' — Claude.ai 글 생성")
    raw = generate_text("", blog_id=blog_id, keyword=actual_keyword,
                        extra_context=fc["context"] if fc["success"] else None,
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

    # Gemini 이미지 생성 — H2 소제목 개수 + 썸네일 1개 기준으로 이미지 수 보정
    image_paths = {}

    # H2 소제목(## 로 시작하는 줄) 개수 계산
    h2_count = sum(1 for line in result["body"].splitlines() if line.startswith("## "))
    required_count = h2_count + 1  # H2 개수 + 썸네일 1개
    log(f"[작성] H2 소제목 {h2_count}개 감지 → 이미지 {required_count}개 필요")

    # 파싱된 이미지 목록이 부족하면 H2 소제목 기반 프롬프트로 채우기
    if len(result["images"]) < required_count:
        shortage = required_count - len(result["images"])
        h2_lines = [l.lstrip('#').strip() for l in result["body"].splitlines() if l.startswith("## ")]
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

    # 본문에 {{이미지N}} 마커가 없으면 H2 소제목 뒤에 주입
    if result["images"] and not re.search(r'\{\{이미지\d+\}\}', result["body"]):
        log("[작성] 본문에 이미지 마커 없음 → H2 소제목 뒤에 주입")
        body_lines = result["body"].split('\n')
        new_lines = []
        img_idx = 1
        total_imgs = len(result["images"])
        for line in body_lines:
            new_lines.append(line)
            if line.startswith('## ') and img_idx <= total_imgs:
                new_lines.append(f'{{{{이미지{img_idx}}}}}')
                img_idx += 1
        # 남은 이미지 마커는 본문 맨 앞에 추가
        while img_idx <= total_imgs:
            new_lines.insert(0, f'{{{{이미지{img_idx}}}}}')
            img_idx += 1
        result["body"] = '\n'.join(new_lines)
        log(f"[작성] 이미지 마커 {total_imgs}개 주입 완료")

    if result["images"]:
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
