"""네이버 검색 API — Tistory URL 수집 + 블로그 발행량 조회"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

# .env 로드
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

CLIENT_ID = os.environ.get("NAVER_SEARCH_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("NAVER_SEARCH_CLIENT_SECRET", "")

# 다양한 카테고리 → 최대한 넓은 Tistory 블로그 풀 확보
SEARCH_QUERIES = [
    # 여행
    "국내여행 추천", "제주도 여행 후기", "부산 여행 추천", "강원도 여행",
    "경주 여행", "전주 여행", "속초 여행", "남해 여행",
    # 맛집/음식
    "서울 맛집 추천", "부산 맛집", "제주 맛집", "이자카야 추천",
    "혼밥 맛집", "분위기 좋은 카페",
    # 건강/뷰티
    "다이어트 방법", "피부 관리 방법", "영양제 추천", "운동 루틴",
    "탈모 예방", "눈 건강",
    # IT/가전
    "노트북 추천", "무선 이어폰 추천", "스마트폰 추천", "태블릿 추천",
    "공기청정기 추천", "로봇청소기 추천",
    # 생활/살림
    "생활비 절약 방법", "인테리어 추천", "가성비 가전",
    "청소 꿀팁", "냉장고 정리",
    # 육아/교육
    "육아 꿀팁", "아기 이유식", "유아 장난감 추천", "초등학생 학습",
    # 재테크/금융
    "재테크 방법", "적금 추천", "주식 투자 방법", "부동산 투자",
    # 취미/문화
    "독서 추천", "넷플릭스 추천", "캠핑 용품", "등산 코스",
    # 반려동물
    "강아지 키우기", "고양이 사료 추천",
    # 계절/시즌
    "벚꽃 명소", "단풍 명소", "여름 휴가지",
]


def _search(endpoint: str, query: str, display: int = 10) -> dict:
    params = urllib.parse.urlencode({"query": query, "display": display})
    req = urllib.request.Request(
        f"https://openapi.naver.com/v1/search/{endpoint}?{params}",
        headers={
            "X-Naver-Client-Id": CLIENT_ID,
            "X-Naver-Client-Secret": CLIENT_SECRET,
        },
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())


def collect_tistory_urls(queries: list = None, display: int = 20, on_log=None) -> set:
    """다양한 쿼리로 검색 → Tistory URL만 필터해서 반환"""
    queries = queries or SEARCH_QUERIES
    tistory_urls = set()

    for query in queries:
        try:
            data = _search("webkr.json", query, display)
            for item in data.get("items", []):
                url = item.get("link", "")
                # tistory.com 도메인만
                if re.search(r"https?://[^/]+\.tistory\.com", url):
                    # 블로그 루트 URL만 추출 (포스트 URL → 블로그 루트)
                    m = re.match(r"(https?://[^/]+\.tistory\.com)", url)
                    if m:
                        tistory_urls.add(m.group(1))
            if on_log:
                on_log(f"[naver_api] '{query}' → 누적 Tistory {len(tistory_urls)}개")
        except Exception as e:
            if on_log:
                on_log(f"[naver_api] '{query}' 오류: {e}")
        time.sleep(0.15)

    return tistory_urls


def get_blog_count(keyword: str) -> int:
    """키워드의 네이버 블로그 발행량 (total 결과 수)"""
    try:
        data = _search("blog.json", keyword, display=1)
        return int(data.get("total", 0))
    except Exception:
        return 0
