"""blogspot_travel 전용 에이전트 — travel.baremi542.com (Blogger API 발행)"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_playwright import generate_text_with_fallback as generate_text
from image_router import generate_images_for_blog as _img_router
from overnight_run import _truncate_title

try:
    from agents import fact_collect as _fact_collect
except ImportError:
    import fact_collect as _fact_collect

BLOG_ID = "blogspot_travel"
PERSONA_RULE = (
    "travel.baremi542.com 한국어 여행 블로그 운영자 본인 시점. "
    "구글 한국어 SEO 타겟. 장소/가게 1곳만 집중 작성 (나열형 절대 금지). "
    "마크다운 형식 필수 (## 소제목, **볼드**). 구분선(---, ***) 절대 금지. "
    "판단 기준: '독자가 이 글 하나로 여행 계획을 세울 수 있는가?'"
)


def run(keyword: str, on_log=None, on_status=None):
    blog_id = BLOG_ID

    def log(msg):
        if on_log:
            on_log(msg)

    if on_status:
        on_status("writer", "working")

    log(f"[{blog_id}] 페르소나 규칙 적용: {PERSONA_RULE}")

    fc = _fact_collect.collect(keyword, blog_id, on_log=log)

    log(f"[작성] {blog_id} / '{keyword}' — Claude.ai 글 생성")
    raw = generate_text("", blog_id=blog_id, keyword=keyword,
                        extra_context=fc["context"] if fc["success"] else None,
                        on_log=log)

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

    image_paths = {}
    if result["images"]:
        log(f"[작성] 이미지 {len(result['images'])}개 생성 시작 (blogspot_travel: Bing)")
        image_paths = _img_router(blog_id, result["images"], skip_webp=False, on_log=log, title=result.get("title", ""))
        log(f"[작성] 이미지 {len(image_paths)}개 생성 완료")

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

    # 마이리얼트립 쿠폰 배너 삽입 (여행 블로그 전용)
    try:
        from mrt_banner import insert_mrt_banner
        result["body"] = insert_mrt_banner(result["body"], keyword, blog_id, on_log=log)
    except Exception as _e:
        log(f"[MRT배너] 오류 — 스킵: {_e}")

    log(f"[작성] ✓ 완료 — 제목: \"{result['title']}\" / 본문: {len(result['body'])}자 / 태그: {len(result['tags'])}개")
    if on_status:
        on_status("writer", "done")
    return result


def _parse_raw(raw, keyword, log):
    title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
    body_m  = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", raw, re.DOTALL)
    tag_m   = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===", raw, re.DOTALL)
    img_m   = re.search(r"===이미지===\s*\n(.*?)\n*===이미지끝===", raw, re.DOTALL)

    raw_title = title_m.group(1).strip().split('\n')[0].strip() if title_m else keyword
    title = _truncate_title(raw_title, max_len=40)
    body = body_m.group(1).strip() if body_m else raw

    if tag_m:
        tags = [t.strip() for line in tag_m.group(1).strip().split('\n') for t in line.split(',') if t.strip()]
    else:
        tags = [keyword]

    if len(tags) < 10:
        pool = [p.strip() for p in re.split(r'[\s,]+', keyword) if p.strip() and len(p.strip()) > 1]
        for t in pool:
            if t not in tags:
                tags.append(t)
            if len(tags) >= 10:
                break

    images = []
    if img_m:
        img_block = img_m.group(1)
        parts = re.split(r'\[(이미지(\d+)|썸네일)\]', img_block)
        auto_idx = 1
        i = 1
        while i < len(parts) - 2:
            digit_part = parts[i + 1]
            block = parts[i + 2]
            i += 3
            idx = int(digit_part) if digit_part else auto_idx
            auto_idx = max(auto_idx, idx) + 1
            prompt = re.search(r'(?:프롬프트|image)\s*[:：]\s*(.+)', block, re.IGNORECASE)
            fname  = re.search(r'파일명\s*[:：]\s*(.+)', block)
            alt_m2 = re.search(r'\balt\s*[:：]\s*(.+)', block, re.IGNORECASE)
            if prompt and fname:
                images.append({"index": idx, "prompt": prompt.group(1).strip(),
                                "filename": fname.group(1).strip(),
                                "alt": alt_m2.group(1).strip() if alt_m2 else ""})

    if not images:
        body = re.sub(r'\{\{이미지\d+\}\}\n?', '', body)

    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
    char_count = len(re.sub(r"\s+", "", plain))

    log(f"[파싱] 제목: \"{title}\" ({len(title)}자) / 본문: {char_count}자 / 태그: {len(tags)}개 / 이미지: {len(images)}개")

    if char_count < 100:
        log("[파싱] ⚠ 본문이 너무 짧음")
        return None

    return {"title": title, "body": body, "tags": tags, "images": images}
