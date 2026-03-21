"""블로그 방문자 수 수집 + 레벨 자동 분류"""

# 레벨 기준
# 초급 (일 방문자 0~100):   월 검색량 100~500
# 중급 (일 방문자 100~500): 월 검색량 500~3000
# 고급 (일 방문자 500+):    월 검색량 3000+

from config import ACCOUNT_MAP

# 블로그 ID → 레벨 수동 매핑 (추후 방문자 수 크롤링으로 자동화 예정)
BLOG_LEVELS = {
    "goodisak": "초급",
    "nolja100": "초급",
    "salim1su": "초급",
}

# 레벨별 키워드 검색량 범위
LEVEL_RANGES = {
    "초급": (100, 500),
    "중급": (500, 3000),
    "고급": (3000, 999999),
}

# 레벨별 일 방문자 기준
LEVEL_VISITORS = {
    "초급": (0, 100),
    "중급": (100, 500),
    "고급": (500, 999999),
}


def get_blog_level(blog_id: str) -> dict:
    """블로그 레벨 정보 반환.

    Args:
        blog_id: 블로그 ID (예: "goodisak", "salim1su")

    Returns:
        dict: {
            "level": "초급" | "중급" | "고급",
            "daily_visitors": int,
            "keyword_range": (min, max),
        }
    """
    # config.py 플랫폼 확인
    account = ACCOUNT_MAP.get(blog_id, {})
    platform = account.get("platform", "unknown")

    # TODO: 플랫폼별 방문자 수 크롤링 구현 예정
    #   - tistory: 티스토리 관리자 페이지 통계 크롤링
    #   - naver: 네이버 블로그 통계 API 또는 크롤링
    # 현재는 BLOG_LEVELS 수동 매핑 기반으로 레벨 결정

    level = BLOG_LEVELS.get(blog_id, "초급")  # 기본값: 초급

    # 레벨에 따른 대표 일 방문자 수 (수동 설정, 추후 실제 크롤링값으로 대체)
    visitor_range = LEVEL_VISITORS.get(level, (0, 100))
    daily_visitors = visitor_range[0]  # 하한값을 기본 대표값으로 사용

    keyword_range = LEVEL_RANGES.get(level, (100, 500))

    return {
        "level": level,
        "daily_visitors": daily_visitors,
        "keyword_range": keyword_range,
        "platform": platform,
    }
