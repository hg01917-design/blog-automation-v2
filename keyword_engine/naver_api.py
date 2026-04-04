"""네이버 검색 API — Tistory URL 수집 + 블로그 발행량 조회"""
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path


def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None

# .env 로드
_env = Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent.parent))) / ".env"
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
    resp = urllib.request.urlopen(req, timeout=10, context=_ssl_ctx())
    return json.loads(resp.read())


def _extract_tistory_root(url: str):
    m = re.match(r"(https?://[^/]+\.tistory\.com)", url)
    return m.group(1) if m else None


def collect_tistory_urls(queries: list = None, display: int = 100, on_log=None) -> set:
    """다양한 쿼리로 검색 → Tistory URL만 필터해서 반환.
    webkr.json 권한 없으면 Playwright CDP로 자동 폴백.
    """
    queries = queries or SEARCH_QUERIES
    tistory_urls = set()
    webkr_ok = True

    for query in queries:
        # 1) 웹 검색 (webkr.json)
        if webkr_ok:
            try:
                data = _search("webkr.json", query, min(display, 100))
                for item in data.get("items", []):
                    root = _extract_tistory_root(item.get("link", ""))
                    if root:
                        tistory_urls.add(root)
            except Exception as e:
                err_str = str(e)
                if "401" in err_str or "403" in err_str:
                    webkr_ok = False  # 권한 없음 — 이후 시도 중단
                    if on_log:
                        on_log(f"[naver_api] webkr 권한 없음 → Playwright 모드로 전환")
                elif on_log:
                    on_log(f"[naver_api] webkr '{query}' 오류: {e}")

        # 2) 블로그 검색 (blog.json — Tistory 포스트 URL 확보)
        try:
            data = _search("blog.json", query, min(display, 100))
            for item in data.get("items", []):
                root = _extract_tistory_root(item.get("link", ""))
                if root:
                    tistory_urls.add(root)
        except Exception as e:
            if on_log:
                on_log(f"[naver_api] blog '{query}' 오류: {e}")

        if on_log:
            on_log(f"[naver_api] '{query}' → 누적 Tistory {len(tistory_urls)}개")
        time.sleep(0.2)

    # webkr 권한 없으면 Playwright로 구글 검색 폴백
    if not webkr_ok and len(tistory_urls) < 50:
        if on_log:
            on_log("[naver_api] Playwright 폴백으로 구글 검색 시작...")
        pw_urls = collect_tistory_urls_playwright(queries[:10], on_log=on_log)
        tistory_urls |= pw_urls

    return tistory_urls


def collect_tistory_urls_playwright(queries: list, on_log=None) -> set:
    """Playwright CDP로 구글 검색 → Tistory URL 수집 (webkr.json 폴백용)"""
    tistory_urls = set()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp("http://localhost:9222")
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            except Exception:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                )
            page = ctx.new_page()
            for query in queries:
                try:
                    search_url = f"https://www.google.com/search?q={urllib.parse.quote(query + ' site:tistory.com')}&num=20"
                    page.goto(search_url, timeout=15000, wait_until="domcontentloaded")
                    page.wait_for_timeout(1500)
                    links = page.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(e => e.href)"
                    )
                    for link in links:
                        root = _extract_tistory_root(link)
                        if root:
                            tistory_urls.add(root)
                    if on_log:
                        on_log(f"[playwright] '{query}' → 누적 {len(tistory_urls)}개")
                    time.sleep(1.5)
                except Exception as e:
                    if on_log:
                        on_log(f"[playwright] '{query}' 오류: {e}")
            page.close()
    except Exception as e:
        if on_log:
            on_log(f"[playwright] 초기화 오류: {e}")
    return tistory_urls


def get_blog_count(keyword: str) -> int:
    """키워드의 네이버 블로그 발행량 (total 결과 수)"""
    try:
        data = _search("blog.json", keyword, display=1)
        return int(data.get("total", 0))
    except Exception:
        return 0


def get_autocomplete(keyword: str, max_results: int = 10) -> list:
    """네이버 자동완성 API로 연관 키워드 확장.
    Returns: list of suggestion strings
    """
    try:
        params = urllib.parse.urlencode({
            "q": keyword, "q_enc": "UTF-8", "st": 100,
            "frm": "nv", "r_format": "json", "r_enc": "UTF-8",
        })
        req = urllib.request.Request(
            f"https://ac.search.naver.com/nx/ac?{params}",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.naver.com"},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode("utf-8"))
        items = data.get("items", [[]])[0]
        return [item[0] for item in items[:max_results] if item]
    except Exception:
        return []


def get_related_searches(keyword: str, max_results: int = 10) -> list:
    """네이버 블로그 검색 연관검색어 수집.
    Returns: list of related keyword strings
    """
    suggestions = []
    try:
        # 네이버 검색 페이지에서 연관검색어 파싱
        params = urllib.parse.urlencode({"query": keyword, "where": "nexearch"})
        req = urllib.request.Request(
            f"https://search.naver.com/search.naver?{params}",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        )
        resp = urllib.request.urlopen(req, timeout=8)
        html = resp.read().decode("utf-8")
        # 연관검색어 패턴
        matches = re.findall(r'"query":"([^"]+)"', html)
        seen = set()
        for m in matches:
            if m not in seen and m != keyword and len(m) > 3:
                suggestions.append(m)
                seen.add(m)
            if len(suggestions) >= max_results:
                break
    except Exception:
        pass
    return suggestions


def expand_keywords_with_autocomplete(base_keywords: list, on_log=None) -> list:
    """기본 키워드 목록에서 자동완성 조합으로 키워드 확장.
    Returns: 기존 + 확장된 키워드 합친 list (중복 제거)
    """
    expanded = list(base_keywords)
    seen = set(base_keywords)
    for kw in base_keywords[:20]:  # 상위 20개 기본 키워드만 확장
        suggestions = get_autocomplete(kw)
        for s in suggestions:
            if s not in seen and len(s) > 4:
                expanded.append(s)
                seen.add(s)
        time.sleep(0.1)
    if on_log:
        on_log(f"[자동완성] {len(base_keywords)}개 → {len(expanded)}개로 확장")
    return expanded
