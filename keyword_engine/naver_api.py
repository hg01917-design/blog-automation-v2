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

# 블로그별 전용 검색 쿼리 (경쟁 블로그 풀 확보용)
BLOG_QUERIES = {
    "goodisak": [
        # IT 제품 리뷰/추천
        "갤럭시 S25 후기", "아이폰 16 추천", "맥북 추천 2025",
        "노트북 추천 가성비", "무선 이어폰 추천", "태블릿 추천",
        "공기청정기 추천", "로봇청소기 추천", "스마트워치 추천",
        "게이밍 노트북 추천", "2in1 노트북 추천", "미니PC 추천",
        "블루투스 스피커 추천", "모니터 추천", "웹캠 추천",
        "OTT 요금제 비교", "넷플릭스 요금제", "티빙 요금제",
    ],
    "nolja100": [
        # 국내 여행 정보
        "제주도 여행 코스", "부산 여행 추천", "강원도 여행",
        "경주 여행 명소", "전주 한옥마을", "속초 여행 코스",
        "남해 여행 추천", "여수 여행", "통영 여행",
        "국립공원 등산 코스", "캠핑장 추천", "글램핑 추천",
        "봄 여행지 추천", "드라이브 코스", "당일치기 여행",
        "가족 여행지 추천", "커플 여행지 추천",
    ],
    "salim1su": [
        # 생활비 절약 / 가정 살림
        "전기요금 절약 방법", "가스비 줄이는 법", "관리비 절약",
        "통신비 절약 방법", "식비 절약 방법", "생활비 줄이기",
        "청소 꿀팁", "냉장고 정리", "주방 정리 방법",
        "세탁 꿀팁", "옷 정리법", "인테리어 셀프",
        "재활용 분리수거 방법", "에너지 절약 방법",
        "가성비 가전 추천", "중고 가전 구입 팁",
    ],
    "baremi542": [
        # 정부지원금 / 복지
        "정부지원금 종류", "복지 혜택 총정리", "청년 지원금",
        "기초생활수급자 혜택", "차상위계층 혜택", "장애인 지원금",
        "육아휴직 급여", "출산 지원금", "임신 지원금",
        "노인 복지 혜택", "실업급여 신청방법", "국민취업지원제도",
        "에너지 바우처", "문화누리카드", "의료급여",
        "주거급여 신청", "교육급여", "청년도약계좌",
    ],
}

# 폴백용 통합 쿼리
SEARCH_QUERIES = [q for queries in BLOG_QUERIES.values() for q in queries]


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
