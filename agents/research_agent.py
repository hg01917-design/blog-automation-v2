"""리서치 에이전트 — Claude가 스스로 검색어 판단 후 Naver API 실행"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from agents import fact_collect as _fc
except ImportError:
    import fact_collect as _fc

# 블로그별 성격 설명 (Claude에게 컨텍스트 제공)
_BLOG_DESC = {
    "goodisak":      "IT·전자제품·금융 정보 블로그",
    "nolja100":      "국내외 여행 블로그",
    "salim1su":      "생활정보·살림·육아 블로그",
    "baremi542":     "정부지원금·복지·생활정책 블로그",
    "woll100":       "교통·대중교통 정보 블로그",
    "phn0502":       "영화·드라마·OTT 블로그",
    "triplog":       "여행 블로그",
    "me1091":        "제품 리뷰·쇼핑 블로그",
    "blogspot_it":   "IT·테크 블로그",
    "blogspot_travel": "여행 블로그",
    "blogspot_daily":  "생활정보 블로그",
}

_RESEARCH_PROMPT = """블로그 글 키워드: "{keyword}"
블로그 유형: {blog_desc}

이 키워드로 정확하고 유용한 블로그 글을 쓰려면 어떤 정보를 찾아야 할까요?
네이버에서 실제로 검색할 검색어를 1~2개만 알려주세요.

규칙:
- 검색어는 짧고 명확하게 (2~4단어)
- SEO 수식어 제거 (추천, 방법, 총정리, 2026 등 빼기)
- 실제로 검색창에 입력할 단어만
- 가격/스펙 필요 시 → 제품명만
- 방법/설정/문제 필요 시 → 제품명+핵심주제
- 정책/지원금 필요 시 → 제도명

아래 형식으로만 답하세요 (다른 설명 없이):
검색1: [검색어]
검색2: [검색어]"""


def _ask_claude_for_queries(keyword: str, blog_id: str, on_log=None) -> list[str]:
    """Claude CLI에 검색어를 물어보고 리스트로 반환."""
    def log(msg):
        if on_log: on_log(msg)

    try:
        from claude_direct import _run_claude
    except ImportError:
        return [_fc._info_search_keyword(keyword)]

    blog_desc = _BLOG_DESC.get(blog_id, "블로그")
    prompt = _RESEARCH_PROMPT.format(keyword=keyword, blog_desc=blog_desc)

    log(f"[리서치] Claude에 검색어 요청 중...")
    raw = _run_claude(prompt, on_log=None, timeout=30, model_key="haiku")

    queries = []
    for line in raw.splitlines():
        m = re.match(r"검색\d\s*:\s*(.+)", line.strip())
        if m:
            q = m.group(1).strip()
            if 2 <= len(q) <= 30:
                queries.append(q)

    if queries:
        log(f"[리서치] Claude 제안 검색어: {queries}")
        return queries

    # Claude 응답 파싱 실패 시 폴백
    log(f"[리서치] 파싱 실패 — 키워드 자동 추출 사용")
    return [_fc._info_search_keyword(keyword)]


def _is_price_query(query: str) -> bool:
    """가격/스펙 조회가 필요한 검색어인지 판단."""
    price_hints = ["가격", "얼마", "스펙", "사양", "구매", "최저가"]
    return any(h in query for h in price_hints) or _fc._is_it_product(query)


def run(keyword: str, blog_id: str, on_log=None) -> dict:
    """키워드에 필요한 정보를 Claude가 판단해서 수집.

    Returns:
        {"context": str, "success": bool, "queries": list[str]}
    """
    def log(msg):
        if on_log: on_log(msg)

    log(f"[리서치] 시작: blog={blog_id}, keyword='{keyword}'")

    # 1. Claude에게 검색어 물어보기
    queries = _ask_claude_for_queries(keyword, blog_id, on_log)

    # 2. 각 검색어로 API 호출
    parts = []
    for q in queries:
        log(f"[리서치] 검색 실행: '{q}'")

        if _is_price_query(q):
            # 가격/스펙 → 쇼핑 API
            shop_kw = _fc._shopping_keyword(q)
            result = _fc._naver_shopping_facts(shop_kw, on_log)
            if result:
                parts.append(result)
                continue

        # 정보성 → 뉴스 우선, 블로그 보완
        news = _fc._naver_news_facts(q, on_log)
        if news:
            parts.append(news)

        blog = _fc._naver_blog_facts(q, on_log)
        if blog:
            parts.append(blog)

    # 3. 공공API도 병행 (복지/여행 블로그)
    from public_api import fetch_context_for_blog
    api_kw = _fc._core_keyword(keyword)
    pub = fetch_context_for_blog(blog_id, api_kw, on_log=on_log)
    if pub and len(pub) > 50:
        parts.insert(0, pub)  # 공공API 결과를 앞에 배치 (신뢰도 높음)

    if not parts:
        log("[리서치] 수집 실패 — 컨텍스트 없음")
        return {"context": "", "success": False, "queries": queries}

    context = (
        f"## '{keyword}' 관련 수집 정보\n"
        f"검색어: {', '.join(queries)}\n"
        f"아래 내용을 참고해 글을 작성하세요. "
        f"수치·사실만 추출해 자신의 문체로 재작성하고, 내용을 그대로 옮기지 마세요.\n"
        f"⚠️ 가격이 있으면 반드시 아래 데이터 범위 내에서만 작성하세요.\n\n"
        + "\n\n".join(parts)
    )

    log(f"[리서치] ✓ 완료 — {len(parts)}개 소스, {len(context)}자")
    return {"context": context, "success": True, "queries": queries}
