"""쿠팡파트너스 API 연동 — 카테고리별 상품 링크 자동 삽입"""
# .env에 COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY 필요

import os
import hmac
import hashlib
import time
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

ACCESS_KEY = os.getenv("COUPANG_ACCESS_KEY", "")
SECRET_KEY = os.getenv("COUPANG_SECRET_KEY", "")

DOMAIN = "https://api-gateway.coupang.com"

BLOG_CATEGORY_MAP = {
    "salim1su": "생활용품",
    "goodisak": "전자기기",
    "nolja100": "여행용품",
}

DUMMY_PRODUCTS = {
    "생활용품": [
        {"name": "인기 생활용품 1위", "url": "https://link.coupang.com/a/dummy1"},
        {"name": "인기 생활용품 2위", "url": "https://link.coupang.com/a/dummy2"},
        {"name": "인기 생활용품 3위", "url": "https://link.coupang.com/a/dummy3"},
    ],
    "전자기기": [
        {"name": "인기 전자기기 1위", "url": "https://link.coupang.com/a/dummy4"},
        {"name": "인기 전자기기 2위", "url": "https://link.coupang.com/a/dummy5"},
        {"name": "인기 전자기기 3위", "url": "https://link.coupang.com/a/dummy6"},
    ],
    "여행용품": [
        {"name": "인기 여행용품 1위", "url": "https://link.coupang.com/a/dummy7"},
        {"name": "인기 여행용품 2위", "url": "https://link.coupang.com/a/dummy8"},
        {"name": "인기 여행용품 3위", "url": "https://link.coupang.com/a/dummy9"},
    ],
}


def _generate_hmac(method: str, path: str, query: str) -> dict:
    """HMAC-SHA256 인증 헤더 생성."""
    datetime_now = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    message = datetime_now + method + path + query
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    authorization = (
        f"CEA algorithm=HmacSHA256, access-key={ACCESS_KEY}, "
        f"signed-date={datetime_now}, signature={signature}"
    )
    return {"Authorization": authorization}


def create_affiliate_link(coupang_url: str, on_log=None) -> str:
    """쿠팡 상품 URL → 파트너스 단축 링크(link.coupang.com) 변환.

    이미 link.coupang.com 이면 그대로 반환.
    API 키 없거나 실패 시 원본 URL 반환.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    # 이미 파트너스 링크면 그대로
    if "link.coupang.com" in coupang_url:
        return coupang_url

    if not ACCESS_KEY or not SECRET_KEY:
        log("[쿠팡] API 키 없음 — 원본 URL 사용")
        return coupang_url

    try:
        import json as _json
        import urllib.request as _req

        path = "/v2/providers/affiliate_open_api/apis/openapi/deeplink"
        body = _json.dumps({"coupangUrls": [coupang_url]}).encode("utf-8")

        headers = _generate_hmac("POST", path, "")
        headers["Content-Type"] = "application/json;charset=UTF-8"

        url = f"{DOMAIN}{path}"
        request = _req.Request(url, data=body, headers=headers, method="POST")
        with _req.urlopen(request, timeout=10) as resp:
            data = _json.loads(resp.read().decode("utf-8"))

        shorten = data.get("data", [{}])[0].get("shortenUrl", "")
        if shorten:
            log(f"[쿠팡] 파트너스 링크 변환: {coupang_url[:50]} → {shorten}")
            return shorten

        log(f"[쿠팡] 변환 응답에 shortenUrl 없음: {data}")
        return coupang_url

    except Exception as e:
        log(f"[쿠팡] deeplink API 오류: {e}")
        return coupang_url


def search_products(keyword: str, category: str = "", limit: int = 3) -> list:
    """쿠팡파트너스 API로 상품을 검색한다.

    API 키가 없거나 호출 실패 시 더미 링크를 반환한다.

    Returns:
        list[dict]: [{"name": str, "url": str}, ...]
    """
    if not ACCESS_KEY or not SECRET_KEY or "여기에_키_입력" in ACCESS_KEY:
        fallback_key = category if category in DUMMY_PRODUCTS else "생활용품"
        return DUMMY_PRODUCTS.get(fallback_key, [])[:limit]

    try:
        import urllib.request
        import json

        path = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
        query_params = urllib.parse.urlencode({
            "keyword": keyword,
            "limit": limit,
        })
        headers = _generate_hmac("GET", path, query_params)
        headers["Content-Type"] = "application/json"

        url = f"{DOMAIN}{path}?{query_params}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        products = []
        for item in data.get("data", {}).get("productData", [])[:limit]:
            products.append({
                "name": item.get("productName", keyword),
                "url": item.get("productUrl", ""),
            })
        return products

    except Exception:
        fallback_key = category if category in DUMMY_PRODUCTS else "생활용품"
        return DUMMY_PRODUCTS.get(fallback_key, [])[:limit]


_NON_PRODUCT_WORDS = {
    "제거", "방법", "하는법", "팁", "절약", "정리", "청소법", "관리", "관리법",
    "사용법", "하기", "이유", "효과", "좋은", "집에서", "간단히", "쉽게", "빠르게",
    "직접", "알아보기", "알아보자", "총정리", "완벽", "비교", "추천", "후기",
    "리뷰", "정보", "기초", "기본", "쉬운", "초보", "따라하기",
}


def _extract_product_keyword(keyword: str) -> str:
    """Claude AI가 블로그 키워드에서 쿠팡 쇼핑 검색에 맞는 핵심 상품어를 자율 판단.

    예: '욕실 물때 제거 베이킹소다' → '베이킹소다'
    AI 실패 시 규칙 기반 폴백(마지막 1단어).
    """
    # AI 자율 추출 시도
    try:
        from claude_direct import _run_claude
        prompt = (
            f"블로그 키워드 '{keyword}'에서 쿠팡 쇼핑 검색창에 입력할 핵심 상품명만 추출해줘.\n"
            f"검색창에 실제로 입력할 단어 1~2개만 출력. 설명·번호·따옴표 없이 단어만."
        )
        result = _run_claude(prompt, timeout=30, model_key="haiku")
        if result:
            extracted = result.strip().splitlines()[0].strip().strip("'\"")
            if extracted and len(extracted) >= 2:
                return extracted
    except Exception:
        pass

    # 폴백: 규칙 기반 (마지막 비동작어 단어)
    words = keyword.split()
    if len(words) <= 1:
        return keyword
    product_words = [w for w in words if w not in _NON_PRODUCT_WORDS]
    return (product_words or words)[-1]


def get_affiliate_block(keyword: str, blog_id: str) -> str:
    """blog_id에 맞는 카테고리로 상품을 검색하고 마크다운 링크 블록을 반환한다.

    API 키가 없거나 오류 발생 시 빈 문자열을 반환한다 (글 발행 중단 없음).
    """
    if not ACCESS_KEY or not SECRET_KEY or "여기에_키_입력" in ACCESS_KEY:
        return ""

    try:
        category = BLOG_CATEGORY_MAP.get(blog_id, "생활용품")
        search_kw = _extract_product_keyword(keyword)
        products = search_products(search_kw, category=category, limit=3)

        if not products:
            return ""

        lines = ["\n\n---\n\n### 이 글과 함께 많이 본 상품\n"]
        for p in products:
            lines.append(f"- [{p['name']}]({p['url']})")
        lines.append("\n*이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.*\n")
        return "\n".join(lines)

    except Exception:
        return ""
