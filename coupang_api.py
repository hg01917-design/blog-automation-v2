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


def get_affiliate_block(keyword: str, blog_id: str) -> str:
    """blog_id에 맞는 카테고리로 상품을 검색하고 마크다운 링크 블록을 반환한다.

    API 키가 없거나 오류 발생 시 빈 문자열을 반환한다 (글 발행 중단 없음).
    """
    if not ACCESS_KEY or not SECRET_KEY or "여기에_키_입력" in ACCESS_KEY:
        return ""

    try:
        category = BLOG_CATEGORY_MAP.get(blog_id, "생활용품")
        products = search_products(keyword, category=category, limit=3)

        if not products:
            return ""

        lines = ["\n\n---\n\n### 이 글과 함께 많이 본 상품\n"]
        for p in products:
            lines.append(f"- [{p['name']}]({p['url']})")
        lines.append("\n*이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.*\n")
        return "\n".join(lines)

    except Exception:
        return ""
