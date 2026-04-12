"""이슈봇 전용 에이전트 — 트렌드 키워드 기반 정보성 포스팅 생성

블로그: issue01 (Tistory, 환경변수 ISSUE_BLOG_ID로 변경 가능)
전략: 이슈/트렌드 키워드 → 정보성 본문 → Gemini 이미지 → AdSense + 쿠팡링크
"""
import re
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_playwright import generate_text_with_fallback as generate_text
from image_router import generate_images_for_blog as _img_router
from overnight_run import _truncate_title

try:
    from agents import fact_collect as _fact_collect
except ImportError:
    import fact_collect as _fact_collect

BLOG_ID = os.getenv("ISSUE_BLOG_ID", "issue01")

PERSONA_RULE = (
    "이슈 정보 블로그 운영자 본인 시점 — 트렌드 분석가 페르소나. "
    "독자가 궁금해하는 핵심 정보를 빠르고 명확하게 전달. "
    "모바일 가독성 최우선 (짧은 문단, 소제목 자주). "
    "불확실한 수치는 '추정' 명시. 1인칭 체험 주장 금지. "
    "판단 기준: '이 이슈를 처음 접한 독자가 가장 알고 싶은 것은?'"
)

# Claude.ai 프롬프트 — Notion 페이지 없을 때 인라인 프롬프트 사용
INLINE_PROMPT = """당신은 이슈/트렌드 정보 블로그 운영자입니다.

키워드: {keyword}

아래 형식으로 블로그 포스팅을 작성하세요.

===제목===
(키워드 포함, 독자 궁금증 자극, 40자 이하, 문장형 어미 금지)
===제목끝===

===본문===
(아래 규칙 준수)
- 총 2000자 이상
- 마크다운 사용 금지 (**, ##, ___ 등 절대 금지)
- 소제목은 ##H2:소제목## 형식 사용
- 첫 문단: 키워드 관련 현황/배경 (200자 이상)
- 본문 구성: 원인/배경 → 핵심 내용 → 생활 연관성 → 독자 액션 포인트
- 이미지 위치: {{이미지1}} {{이미지2}} {{이미지3}} 을 각 섹션 사이에 배치
- 독자가 바로 활용 가능한 정보 위주
- 광고글 느낌 금지, 중립적 정보 제공
- [검증 필요] [출처 필요] 등 내부 마커 절대 사용 금지
===본문끝===

===태그===
(쉼표 구분, 10개, 키워드 관련 실제 검색어 위주)
===태그끝===

===이미지===
[이미지1]
Gemini 프롬프트: (키워드 관련 뉴스/정보 느낌의 영문 프롬프트, 30단어 이내)
파일명: issue_img1.jpg
alt: (한국어 이미지 설명)

[이미지2]
Gemini 프롬프트: (다른 각도/장면)
파일명: issue_img2.jpg
alt: (한국어 이미지 설명)

[이미지3]
Gemini 프롬프트: (관련 생활/인포그래픽 느낌)
파일명: issue_img3.jpg
alt: (한국어 이미지 설명)
===이미지끝===
"""


def run(keyword: str, on_log=None, on_status=None):
    """글 + 이미지 생성 후 파싱된 결과를 반환한다.

    Returns:
        dict with keys: title, body, tags, images, image_paths, raw
    """
    blog_id = BLOG_ID

    def log(msg):
        if on_log:
            on_log(msg)

    if on_status:
        on_status("writer", "working")

    log(f"[{blog_id}] 이슈봇 에이전트 실행: '{keyword}'")

    # 사전 팩트 수집 (선택적)
    extra_ctx = None
    try:
        fc = _fact_collect.collect(keyword, blog_id, on_log=log)
        if fc.get("success"):
            extra_ctx = fc["context"]
    except Exception as e:
        log(f"[{blog_id}] 팩트 수집 실패 (무시): {e}")

    # Claude.ai 글 생성 — 인라인 프롬프트 전달
    log(f"[작성] {blog_id} / '{keyword}' — Claude.ai 글 생성")
    prompt_with_kw = INLINE_PROMPT.format(keyword=keyword)
    raw = generate_text(
        prompt_with_kw,
        blog_id=blog_id,
        keyword=keyword,
        extra_context=extra_ctx,
        on_log=log,
    )

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

    # PIL 인포그래픽 카드 생성 (Gemini 대신 로컬 생성 — 무제한, 빠름)
    image_paths = {}
    try:
        from issue_card import generate_issue_cards
        card_paths = generate_issue_cards(
            title=result["title"],
            keyword=keyword,
            body=result["body"],
            count=3,
            on_log=log,
        )
        if card_paths:
            image_paths = card_paths
            # images 리스트를 카드 파일에 맞게 업데이트
            result["images"] = [
                {"index": idx, "prompt": "", "filename": Path(p).name, "alt": f"{keyword} 카드 {idx}"}
                for idx, p in card_paths.items()
            ]
            log(f"[작성] PIL 카드 {len(image_paths)}장 생성 완료")
    except Exception as e:
        log(f"[작성] PIL 카드 실패({e}) — Gemini 폴백")

    # Gemini 폴백 (PIL 실패 시)
    if not image_paths and result["images"]:
        log(f"[작성] Gemini 이미지 {len(result['images'])}개 생성 시작 (폴백)")
        image_paths = _img_router(
            blog_id, result["images"], skip_webp=False, on_log=log,
            title=result.get("title", "")
        )
        log(f"[작성] Gemini 이미지 {len(image_paths)}개 생성 완료")

        failed = [img for img in result["images"] if img["index"] not in image_paths]
        if failed:
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

    if len(tags) < 10:
        pool = [p.strip() for p in re.split(r'[\s,]+', keyword) if p.strip() and len(p.strip()) > 1]
        pool += [p.strip() for p in re.split(r'[\s,]+', raw_title) if p.strip() and len(p.strip()) > 1]
        for t in pool:
            if t not in tags:
                tags.append(t)
            if len(tags) >= 10:
                break

    # 이미지
    images = []
    if img_m:
        img_block = img_m.group(1)
        parts = re.split(r'\[(이미지(\d+)|썸네일)\]', img_block)
        auto_idx = 1
        i = 1
        while i < len(parts) - 2:
            full_match = parts[i]
            digit_part = parts[i + 1]
            block = parts[i + 2]
            i += 3
            idx = int(digit_part) if digit_part else auto_idx
            auto_idx = max(auto_idx, idx) + 1
            prompt = re.search(
                r'(?:Gemini|이미지|image)\s*프롬프트\s*[:：]\s*(.+)',
                block, re.IGNORECASE
            )
            fname = re.search(r'파일명\s*[:：]\s*(.+)', block)
            alt_m2 = re.search(r'\balt\s*[:：]\s*(.+)', block, re.IGNORECASE)
            if prompt and fname:
                images.append({
                    "index": idx,
                    "prompt": prompt.group(1).strip(),
                    "filename": fname.group(1).strip(),
                    "alt": alt_m2.group(1).strip() if alt_m2 else "",
                })

    if not images:
        log("[파싱] ⚠ 이미지 정보 없음 — 기본 3장 생성")
        images = [
            {"index": 1, "prompt": f"{keyword} information concept, clean minimal", "filename": "issue_img1.jpg", "alt": f"{keyword} 관련 이미지1"},
            {"index": 2, "prompt": f"{keyword} lifestyle detail shot", "filename": "issue_img2.jpg", "alt": f"{keyword} 관련 이미지2"},
            {"index": 3, "prompt": f"{keyword} overview background", "filename": "issue_img3.jpg", "alt": f"{keyword} 관련 이미지3"},
        ]
        if "{{이미지1}}" not in body:
            body = "{{이미지1}}\n\n" + body
        if "{{이미지2}}" not in body:
            mid = len(body) // 2
            body = body[:mid] + "\n\n{{이미지2}}\n\n" + body[mid:]
        if "{{이미지3}}" not in body:
            body = body + "\n\n{{이미지3}}"

    log(f"[파싱] 제목={title!r}, 본문={len(body)}자, 태그={len(tags)}개, 이미지={len(images)}개")
    return {
        "title": title,
        "body": body,
        "tags": tags,
        "images": images,
    }
