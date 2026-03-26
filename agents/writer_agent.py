"""작성 에이전트 — claude.ai 글 생성 + Gemini 이미지 생성"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_playwright import generate_text_with_fallback as generate_text
from gemini_image import generate_images
from overnight_run import _truncate_title

try:
    import coupang_api
    import agoda_api
    _AFFILIATE_AVAILABLE = True
except Exception:
    _AFFILIATE_AVAILABLE = False


def run(blog_id: str, keyword: str, on_log=None, on_status=None):
    """글 + 이미지 생성 후 파싱된 결과를 반환한다.

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
    def log(msg):
        if on_log:
            on_log(msg)

    if on_status:
        on_status("writer", "working")

    # 1. Claude.ai 글 생성
    log(f"[작성] {blog_id} / '{keyword}' — Claude.ai 글 생성")
    raw = generate_text("", blog_id=blog_id, keyword=keyword, on_log=log)

    if not raw or "추출 실패" in raw:
        log("[작성] ⚠ 글 생성 실패")
        if on_status:
            on_status("writer", "failed")
        return None

    # 2. 파싱
    result = _parse_raw(raw, keyword, log)
    if not result:
        if on_status:
            on_status("writer", "failed")
        return None

    # 3. Gemini 이미지 생성
    image_paths = {}
    if result["images"]:
        log(f"[작성] Gemini 이미지 {len(result['images'])}개 생성 시작")
        image_paths = generate_images(result["images"], on_log=log)
        log(f"[작성] 이미지 {len(image_paths)}개 생성 완료")

    result["image_paths"] = image_paths
    result["raw"] = raw

    # 4. 제휴마케팅 블록 삽입
    if _AFFILIATE_AVAILABLE:
        try:
            if blog_id == "nolja100":
                affiliate_block = agoda_api.get_hotel_block(keyword)
            else:
                affiliate_block = coupang_api.get_affiliate_block(keyword, blog_id)
            if affiliate_block:
                result["body"] = result["body"] + affiliate_block
                log("[작성] 제휴 링크 블록 삽입 완료")
        except Exception:
            pass  # API 오류 시 조용히 스킵

    log(f"[작성] ✓ 완료 — 제목: \"{result['title']}\" / 본문: {len(result['body'])}자 / 태그: {len(result['tags'])}개")
    if on_status:
        on_status("writer", "done")
    return result


def _parse_raw(raw, keyword, log):
    """===섹션=== 형식의 raw 텍스트를 파싱한다."""
    title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
    body_m = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", raw, re.DOTALL)
    tag_m = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===", raw, re.DOTALL)
    img_m = re.search(r"===이미지===\s*\n(.*?)\n*===이미지끝===", raw, re.DOTALL)

    # 제목
    if title_m:
        raw_title = title_m.group(1).strip().split('\n')[0].strip()
    else:
        raw_title = keyword
    title = _truncate_title(raw_title, max_len=40)

    # 본문
    body = body_m.group(1).strip() if body_m else raw

    # 태그
    if tag_m:
        tag_line = tag_m.group(1).strip().split('\n')[0].strip()
        tags = [t.strip() for t in tag_line.split(",") if t.strip()]
    else:
        tags = [keyword]

    # 이미지 정보
    images = []
    if img_m:
        for m in re.finditer(
            r"\[이미지(\d+)\]\s*\n- Gemini프롬프트:\s*(.+)\n- 파일명:\s*(.+)\n- alt:\s*(.+)",
            img_m.group(1),
        ):
            images.append({
                "index": int(m.group(1)),
                "prompt": m.group(2).strip(),
                "filename": m.group(3).strip(),
                "alt": m.group(4).strip(),
            })

    # {{이미지N}} 마커가 본문에 있지만 이미지 정보가 없으면 마커 제거
    if images:
        defined_indices = {img["index"] for img in images}
        def _remove_unmatched_marker(m):
            return "" if int(m.group(1)) not in defined_indices else m.group(0)
        body = re.sub(r'\{\{이미지(\d+)\}\}', _remove_unmatched_marker, body)
    else:
        # 이미지 섹션 자체가 없으면 모든 마커 제거
        body = re.sub(r'\{\{이미지\d+\}\}\n?', '', body)

    # 본문 글자수 확인
    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
    char_count = len(re.sub(r"\s+", "", plain))

    log(f"[파싱] 제목: \"{title}\" ({len(title)}자)")
    log(f"[파싱] 본문: {char_count}자 (순수 텍스트)")
    log(f"[파싱] 태그: {len(tags)}개 / 이미지: {len(images)}개")

    if char_count < 100:
        log("[파싱] ⚠ 본문이 너무 짧음")
        return None

    return {
        "title": title,
        "body": body,
        "tags": tags,
        "images": images,
    }
