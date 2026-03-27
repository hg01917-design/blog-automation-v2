# salim1su 네이버 살림 전용 에이전트 — 주부 페르소나
"""salim1su 네이버 살림 전용 에이전트 — claude.ai 글 생성 + Gemini 이미지 생성"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_playwright import generate_text_with_fallback as generate_text
from gemini_image import generate_images
from overnight_run import _truncate_title

BLOG_ID = "salim1su"
PERSONA_RULE = (
    "퇴근후살림 블로그 운영자 본인 시점 — 하린(30대 중반, 주부+직장인, 세 자녀) 페르소나. "
    "체험형 문체(~더라구요/~했어요), 구체적 금액/수치 사용. "
    "판단 기준: '내가 이 살림 블로그 운영자라면 이렇게 쓸까?'"
)


def run(keyword: str, on_log=None, on_status=None):
    """글 + 이미지 생성 후 파싱된 결과를 반환한다.

    blog_id는 "salim1su"으로 고정됩니다.

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

    log(f"[{blog_id}] 페르소나 규칙 적용: {PERSONA_RULE}")

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
        tag_raw = tag_m.group(1).strip()
        tags = [t.strip() for line in tag_raw.split('\n') for t in line.split(',') if t.strip()]
    else:
        tags = [keyword]

    # 이미지 정보
    images = []
    if img_m:
        img_block = img_m.group(1)
        # [이미지N] 또는 [썸네일] 단위로 분할
        # [썸네일]은 index=0으로, [이미지N]은 N으로 처리
        parts = re.split(r'\[(이미지(\d+)|썸네일)\]', img_block)
        # split 결과: [앞텍스트, full_match, digit_or_None, 블록, ...]
        auto_idx = 1
        i = 1
        while i < len(parts) - 2:
            full_match = parts[i]      # "이미지1" 또는 "썸네일"
            digit_part = parts[i + 1]  # "1" 또는 None
            block      = parts[i + 2]
            i += 3

            if digit_part:
                idx = int(digit_part)
            else:
                idx = auto_idx  # 썸네일 → 다음 번호 자동 부여
            auto_idx = max(auto_idx, idx) + 1

            # Gemini / Ideogram / 기타 프롬프트 형식 모두 허용
            prompt = re.search(
                r'(?:Gemini|Ideogram|이미지|image)\s*프롬프트\s*[:：]\s*(.+)',
                block, re.IGNORECASE
            )
            fname  = re.search(r'파일명\s*[:：]\s*(.+)', block)
            alt_m2 = re.search(r'\balt\s*[:：]\s*(.+)', block, re.IGNORECASE)
            if prompt and fname:
                images.append({
                    "index": idx,
                    "prompt": prompt.group(1).strip(),
                    "filename": fname.group(1).strip(),
                    "alt": alt_m2.group(1).strip() if alt_m2 else "",
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
