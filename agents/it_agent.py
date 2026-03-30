# goodisak IT 전용 에이전트 — 트러블슈터 페르소나
"""goodisak IT 전용 에이전트 — claude.ai 글 생성 + Gemini 이미지 생성"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_playwright import generate_text_with_fallback as generate_text
from gemini_image import generate_images
from overnight_run import _truncate_title

try:
    from agents import fact_collect as _fact_collect
except ImportError:
    import fact_collect as _fact_collect

BLOG_ID = "goodisak"
PERSONA_RULE = (
    "굳이삭 IT 블로그 운영자 본인 시점 — 트러블슈터(해결사) 페르소나. "
    "판단 기준: '내가 이 블로그 운영자라면 이렇게 쓸까?' "
    "결론 먼저, 원인→해결 순서, 존댓말(~습니다/~세요/~해요)"
)


def run(keyword: str, on_log=None, on_status=None):
    """글 + 이미지 생성 후 파싱된 결과를 반환한다.

    blog_id는 "goodisak"으로 고정됩니다.

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

    # 1. 사전 팩트 수집
    fc = _fact_collect.collect(keyword, blog_id, on_log=log)

    # 2. Claude.ai 글 생성
    log(f"[작성] {blog_id} / '{keyword}' — Claude.ai 글 생성")
    raw = generate_text("", blog_id=blog_id, keyword=keyword,
                        extra_context=fc["context"] if fc["success"] else None,
                        on_log=log)

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
    # 문장형 어미 제거 (명사형으로 변환)
    raw_title = re.sub(
        r'\s*(을|를)?\s*(알아보겠습니다|살펴보겠습니다|정리해보겠습니다|알아볼게요|살펴볼게요|정리해볼게요)\.?$',
        '', raw_title
    ).strip()
    raw_title = re.sub(
        r'\s*(합니다|해요|입니다|에요|습니다|세요|있어요|있습니다|드립니다)\.?$',
        '', raw_title
    ).strip()
    title = _truncate_title(raw_title, max_len=40)

    # 본문
    body = body_m.group(1).strip() if body_m else raw

    # 태그
    if tag_m:
        tag_raw = tag_m.group(1).strip()
        tags = [t.strip() for line in tag_raw.split('\n') for t in line.split(',') if t.strip()]
    else:
        tags = [keyword]

    # 태그 10개 자동 보충
    if len(tags) < 10:
        pool = [p.strip() for p in re.split(r'[\s,]+', keyword) if p.strip() and len(p.strip()) > 1]
        pool += [p.strip() for p in re.split(r'[\s,]+', raw_title) if p.strip() and len(p.strip()) > 1]
        for t in pool:
            if t not in tags:
                tags.append(t)
            if len(tags) >= 10:
                break

    # 이미지 정보 — [썸네일] + [이미지N] 형식 모두 지원
    images = []
    if img_m:
        img_block = img_m.group(1)
        parts = re.split(r'\[(이미지(\d+)|썸네일)\]', img_block)
        auto_idx = 1
        i = 1
        while i < len(parts) - 2:
            full_match = parts[i]
            digit_part = parts[i + 1]
            block      = parts[i + 2]
            i += 3
            idx = int(digit_part) if digit_part else auto_idx
            auto_idx = max(auto_idx, idx) + 1
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

    # {{이미지N}} 마커 처리
    if images:
        defined_indices = {img["index"] for img in images}
        _seen_img = set()
        def _dedup_marker(m):
            idx = int(m.group(1))
            if idx not in defined_indices or idx in _seen_img:
                return ""
            _seen_img.add(idx)
            return m.group(0)
        body = re.sub(r'\{\{이미지(\d+)\}\}', _dedup_marker, body)
    else:
        # 이미지 섹션 없으면 키워드 기반 기본 이미지 2개 자동 생성
        body = re.sub(r'\{\{이미지\d+\}\}\n?', '', body)
        slug = re.sub(r'[^\w가-힣]', '-', keyword.strip()).strip('-')
        images = [
            {
                "index": 1,
                "prompt": f"{keyword} 관련 정보 인포그래픽, 깔끔한 아이콘 스타일, 파란색 테마",
                "filename": f"{slug}-info.webp",
                "alt": f"{keyword} 정보 이미지",
            },
            {
                "index": 2,
                "prompt": f"{keyword} 실용적인 팁과 방법 안내, 현대적 일러스트 스타일",
                "filename": f"{slug}-guide.webp",
                "alt": f"{keyword} 가이드 이미지",
            },
        ]
        # 본문의 첫 H2 뒤와 두 번째 H2 뒤에 이미지 마커 삽입
        body_lines = body.split('\n')
        h2_idx = [i for i, l in enumerate(body_lines) if l.strip().startswith('## ')]
        for offset, (pos, marker) in enumerate(
            [(h2_idx[i] + 1, f'{{{{이미지{i+1}}}}}') for i in range(min(2, len(h2_idx)))]
        ):
            body_lines.insert(pos + offset, marker)
        body = '\n'.join(body_lines)
        log(f"[파싱] 이미지 섹션 없음 → 키워드 기반 이미지 {len(images)}개 자동 생성")

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
