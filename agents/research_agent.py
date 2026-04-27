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

이 키워드로 정확하고 유용한 블로그 글을 쓰려면 어떤 정보를, 어디서 찾아야 할까요?
검색어와 검색 소스를 1~3개 알려주세요.

사용 가능한 검색 소스:
- 네이버뉴스: 최신 뉴스·정책 발표·사건사고
- 네이버블로그: 개인 후기·사용 경험·실용 팁
- 네이버쇼핑: 가격·스펙·모델 비교·최저가
- 공공API: 정부지원금·복지정책·국내 관광지 공식정보

소스 선택 기준:
- 가격·스펙·구매 → 네이버쇼핑
- 최신 뉴스·정책 발표 → 네이버뉴스
- 사용법·후기·방법·설정·문제해결 → 네이버블로그
- 정부지원금·복지·여행지 공식정보 → 공공API
- 여러 소스 동시 사용 가능 (더 풍부한 정보)

검색어 규칙:
- 짧고 명확하게 (2~4단어)
- SEO 수식어 제거 (추천, 총정리, 2026 등)
- 실제 검색창에 입력할 단어만

아래 형식으로만 답하세요 (다른 설명 없이):
검색1: [검색어] | [소스]
검색2: [검색어] | [소스]
검색3: [검색어] | [소스]"""

# 소스 이름 → 내부 키 매핑
_SOURCE_MAP = {
    "네이버쇼핑": "shopping", "쇼핑": "shopping",
    "네이버뉴스": "news",     "뉴스": "news",
    "네이버블로그": "blog",   "블로그": "blog",
    "공공api": "public",      "공공API": "public", "공공": "public",
}


def _ask_claude_for_plan(keyword: str, blog_id: str, on_log=None) -> list[tuple[str, str]]:
    """Claude CLI에 '무엇을 어디서 검색할지' 물어보고 (query, source) 리스트로 반환."""
    def log(msg):
        if on_log: on_log(msg)

    try:
        from claude_direct import _run_claude
    except ImportError:
        return [(_fc._info_search_keyword(keyword), "news")]

    blog_desc = _BLOG_DESC.get(blog_id, "블로그")
    prompt = _RESEARCH_PROMPT.format(keyword=keyword, blog_desc=blog_desc)

    log("[리서치] Claude에 검색 계획 요청 중...")
    raw = _run_claude(prompt, on_log=None, timeout=30, model_key="haiku")

    plan = []
    for line in raw.splitlines():
        # "검색1: 엘지그램 발열 | 네이버블로그" 형태 파싱
        m = re.match(r"검색\d\s*:\s*(.+?)\s*\|\s*(.+)", line.strip())
        if m:
            q = m.group(1).strip()
            src_raw = m.group(2).strip()
            src = _SOURCE_MAP.get(src_raw, _SOURCE_MAP.get(src_raw.replace(" ", ""), "news"))
            if 2 <= len(q) <= 30:
                plan.append((q, src))

    if plan:
        log(f"[리서치] Claude 검색 계획: {[(q, s) for q, s in plan]}")
        return plan

    # 파싱 실패 — | 없이 검색어만 있는 경우도 처리
    fallback = []
    for line in raw.splitlines():
        m = re.match(r"검색\d\s*:\s*(.+)", line.strip())
        if m:
            q = m.group(1).strip().split("|")[0].strip()
            if 2 <= len(q) <= 30:
                fallback.append((q, "news"))
    if fallback:
        log(f"[리서치] 소스 파싱 실패 — 뉴스 기본값 적용: {[q for q, _ in fallback]}")
        return fallback

    log("[리서치] 파싱 실패 — 키워드 자동 추출 사용")
    return [(_fc._info_search_keyword(keyword), "news")]


def run(keyword: str, blog_id: str, on_log=None) -> dict:
    """키워드에 필요한 정보를 Claude가 판단해서 수집.

    Returns:
        {"context": str, "success": bool, "queries": list[str]}
    """
    def log(msg):
        if on_log: on_log(msg)

    log(f"[리서치] 시작: blog={blog_id}, keyword='{keyword}'")

    # 1. Claude에게 검색어 + 소스 물어보기
    plan = _ask_claude_for_plan(keyword, blog_id, on_log)
    query_names = [q for q, _ in plan]

    # 2. Claude 계획대로 API 호출
    parts = []
    public_done = False

    for q, src in plan:
        log(f"[리서치] 검색: '{q}' → {src}")

        if src == "shopping":
            shop_kw = _fc._shopping_keyword(q)
            result = _fc._naver_shopping_facts(shop_kw, on_log)
            if result:
                parts.append(result)

        elif src == "news":
            result = _fc._naver_news_facts(q, on_log)
            if result:
                parts.append(result)

        elif src == "blog":
            result = _fc._naver_blog_facts(q, on_log)
            if result:
                parts.append(result)

        elif src == "public":
            if not public_done:
                from public_api import fetch_context_for_blog
                result = fetch_context_for_blog(blog_id, q, on_log=on_log)
                if result and len(result) > 50:
                    parts.insert(0, result)
                    public_done = True

    # 3. 공공API 자동 보완 — Claude가 요청 안 했어도 복지/여행 블로그는 항상 시도
    if not public_done and blog_id in ("baremi542", "nolja100", "triplog",
                                        "blogspot_travel", "salim1su", "woll100"):
        from public_api import fetch_context_for_blog
        api_kw = _fc._core_keyword(keyword)
        pub = fetch_context_for_blog(blog_id, api_kw, on_log=on_log)
        if pub and len(pub) > 50:
            parts.insert(0, pub)
            log("[리서치] 공공API 자동 보완 완료")

    if not parts:
        log("[리서치] 수집 실패 — 컨텍스트 없음")
        return {"context": "", "success": False, "queries": query_names}

    src_summary = ", ".join(f"{q}({s})" for q, s in plan)
    context = (
        f"## '{keyword}' 관련 수집 정보\n"
        f"검색: {src_summary}\n"
        f"아래 내용을 참고해 글을 작성하세요. "
        f"수치·사실만 추출해 자신의 문체로 재작성하고, 내용을 그대로 옮기지 마세요.\n"
        f"⚠️ 가격이 있으면 반드시 아래 데이터 범위 내에서만 작성하세요.\n\n"
        + "\n\n".join(parts)
    )

    log(f"[리서치] ✓ 완료 — {len(parts)}개 소스, {len(context)}자")
    return {"context": context, "success": True, "queries": query_names}
