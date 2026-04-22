"""
google_harvester.py — 구글 상위 블로그 사이트 수집 → pub코드 추출 → 파워 운영자 RSS 수집

파이프라인:
  1. 구글 검색 (Tistory/WordPress 포함 모든 블로그) → 상위 URL 수집
  2. Playwright(새 페이지)로 각 사이트 방문 → AdSense pub코드 추출 (JS 렌더링 포함)
  3. pub코드별 사이트 수 집계 → MIN_SITES_PER_PUB 이상 = 파워 운영자
  4. 파워 운영자 사이트 RSS → 최신 글 제목 수집 → seed 키워드화
  5. seed → 네이버 자동완성 롱테일 확장 → DB 저장
"""
import re
import time
import sqlite3
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import os

_root = Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent.parent)))
_env = _root / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

DB_PATH = _root / "keyword_engine" / "engine.db"
PUB_PATTERN = re.compile(r"ca-pub-(\d{14,16})")
TISTORY_PATTERN = re.compile(r"https?://([a-zA-Z0-9\-]+)\.tistory\.com")
# 블로그/워드프레스/일반 도메인 패턴 — 구글 검색 결과에서 추출
BLOG_URL_PATTERN = re.compile(r"https?://([a-zA-Z0-9\-]+\.[a-zA-Z0-9\-\.]+)/")
# 수집 제외 도메인 (검색엔진/소셜/쇼핑/포털/여행예약)
_SKIP_DOMAINS = {
    "google", "youtube", "facebook", "instagram", "twitter", "naver", "kakao",
    "daum", "wikipedia", "namuwiki", "gmarket", "coupang", "11st", "amazon",
    "netflix", "apple", "microsoft", "github", "stackoverflow",
    "pstatic.net", "nate.com", "zum.com",
    "hanatour", "klook", "kkday", "myrealtrip", "tripstore", "ybtour",
    "modetour", "onlinetour", "interpark", "expedia", "getyourguide",
    "visitkorea", "visitbusan", "visitseoul", "go.kr",
}
# 뉴스/언론/기업 도메인 판별 키워드 (domain host 포함 여부로 체크)
_NEWS_KEYWORDS = {
    "news", "press", "times", "daily", "herald", "tribune", "journal",
    "media", "cast", "joongang", "hankyung", "hankyung", "chosun",
    "seoul", "donga", "yonhap", "yna", "sbs", "kbs", "mbc", "jtbc",
    "newsis", "news1", "mt.co", "fnnews", "pressian", "wikitree",
    "sportsseoul", "stardailynews", "weeklytoday", "discoverynews",
    "ibabynews", "topstarnews", "tournews", "ardentnews", "jeonmae",
    "mhns", "greenpostkorea", "biztribune", "sisacast", "gukjenews",
    "joongangenews", "pinpointnews", "businesskorea", "ezyeconomy",
    "travie",  # 여행 잡지
    "marieclairekorea", "gqkorea", "elle.co",  # 패션잡지
    "efnews", "gybelife", "ss78.co",
}

MIN_SITES_PER_PUB = 30  # 파워 운영자 기준: 30개 이상 사이트 (역검색 기준)
GOOGLE_NUM = 100         # 구글 검색 결과 수 (최대 100)
MAX_PAGES = 2            # 페이지당 10개 × 최대 10페이지 → 최대 100개

CATEGORY_QUERIES = {
    "여행": [
        "제주도 여행 코스 블로그", "부산 여행 추천 후기", "강원도 여행 명소 정리",
        "속초 여행 코스 2박3일", "경주 여행 일정 블로그", "전주 한옥마을 여행 후기",
        "여수 여행 코스 블로그", "통영 여행 추천 코스", "남해 여행 명소 블로그",
        "국내 여행지 추천 블로그", "당일치기 여행 코스 서울근교", "국내 호텔 추천 후기",
        "해외여행 추천 블로그", "동남아 여행 코스 후기", "일본 여행 코스 블로그",
    ],
    "IT": [
        "아이폰 추천 비교 블로그", "갤럭시 추천 후기", "노트북 추천 가성비 블로그",
        "무선 이어폰 추천 비교", "태블릿 추천 블로그", "공기청정기 추천 후기",
        "로봇청소기 추천 비교 블로그", "스마트워치 추천 2025", "모니터 추천 후기",
        "OTT 요금제 비교 블로그", "넷플릭스 요금 정리", "게이밍 노트북 추천",
    ],
    "살림": [
        "전기요금 절약 방법 블로그", "생활비 줄이기 후기", "식비 절약 방법 정리",
        "청소 꿀팁 블로그", "냉장고 정리법 후기", "세탁 꿀팁 블로그",
        "관리비 절약 방법", "통신비 절약 후기", "도시가스 절약 방법",
    ],
    "정부지원금": [
        "청년 지원금 신청 방법 블로그", "정부지원금 종류 총정리", "복지 혜택 총정리 블로그",
        "기초생활수급자 혜택 정리", "실업급여 신청 방법", "육아휴직 급여 계산",
        "출산 지원금 신청 블로그", "청년도약계좌 후기", "주거급여 신청 방법",
    ],
    "교통": [
        "인천공항 버스 시간표 정리", "공항버스 요금 블로그", "KTX 예매 방법",
        "고속버스 예매 후기", "시외버스 요금 정리", "공항철도 소요시간 블로그",
    ],
    "영화": [
        "영화 추천 2025 블로그", "넷플릭스 신작 추천", "영화 결말 해석 블로그",
        "드라마 추천 후기", "OTT 추천 비교 블로그", "공포 영화 추천 정리",
    ],
}


def log(msg, on_log=None):
    print(msg, flush=True)
    if on_log:
        on_log(msg)


# ── 1단계: 구글 검색 → 블로그 URL 수집 (Tistory + WordPress 등 모두) ──────────

def _extract_root_url(href: str) -> str | None:
    """검색 결과 href에서 개인 블로그 루트 도메인 URL 추출. 뉴스/언론/예약 사이트는 None."""
    try:
        parsed = urllib.parse.urlparse(href)
        host = parsed.netloc.lower()
        if not host or parsed.scheme not in ("http", "https"):
            return None
        # 1. 제외 도메인 (포털/쇼핑/예약)
        for skip in _SKIP_DOMAINS:
            if skip in host:
                return None
        # 2. 뉴스/언론 도메인 키워드 필터
        for kw in _NEWS_KEYWORDS:
            if kw in host:
                return None
        return f"{parsed.scheme}://{host}"
    except Exception:
        return None


def naver_search_blogs(query: str, max_results: int = 100) -> list[str]:
    """네이버 블로그 검색 → 티스토리·WordPress 루트 URL 목록 반환 (urllib, 브라우저 불필요)."""
    urls = []
    seen = set()

    for start in range(1, max_results + 1, 10):
        search_url = (
            f"https://search.naver.com/search.naver"
            f"?where=blog&query={urllib.parse.quote(query)}&start={start}"
        )
        try:
            req = urllib.request.Request(
                search_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/124.0.0.0 Safari/537.36",
                    "Accept-Language": "ko-KR,ko;q=0.9",
                    "Referer": "https://www.naver.com/",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            # 결과 링크 추출
            hrefs = re.findall(r'href="(https?://[^"]+)"', html)
            found = 0
            for href in hrefs:
                root = _extract_root_url(href)
                if root and root not in seen:
                    seen.add(root)
                    urls.append(root)
                    found += 1
            if found == 0:
                break
            time.sleep(1.2)
        except Exception:
            break

    return urls


def daum_search_blogs(query: str, max_results: int = 100) -> list[str]:
    """다음 블로그 검색 → 티스토리·WordPress 루트 URL 목록 반환."""
    urls = []
    seen = set()

    for page_num in range(1, (max_results // 10) + 2):
        search_url = (
            f"https://search.daum.net/search"
            f"?w=blog&q={urllib.parse.quote(query)}&page={page_num}"
        )
        try:
            req = urllib.request.Request(
                search_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/124.0.0.0 Safari/537.36",
                    "Accept-Language": "ko-KR,ko;q=0.9",
                    "Referer": "https://www.daum.net/",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            hrefs = re.findall(r'href="(https?://[^"]+)"', html)
            found = 0
            for href in hrefs:
                root = _extract_root_url(href)
                if root and root not in seen:
                    seen.add(root)
                    urls.append(root)
                    found += 1
            if found == 0:
                break
            time.sleep(1.2)
        except Exception:
            break

    return urls


def collect_all_blog_urls(category: str, page=None, on_log=None) -> list[str]:
    """카테고리별 쿼리로 네이버+다음 블로그 검색 → 전체 블로그 URL 수집 (Tistory + WordPress 등).
    page 파라미터는 호환성 유지용 (사용 안 함)."""
    queries = CATEGORY_QUERIES.get(category, [])
    all_urls = []
    seen = set()

    for q in queries:
        # 네이버 블로그 검색
        log(f"[네이버] '{q}' 검색 중...", on_log)
        naver_urls = naver_search_blogs(q, max_results=GOOGLE_NUM)
        new = [u for u in naver_urls if u not in seen]
        seen.update(new)
        all_urls.extend(new)
        log(f"[네이버] '{q}' → {len(new)}개 (누적 {len(all_urls)}개)", on_log)
        time.sleep(1.5)

        # 다음 블로그 검색
        daum_urls = daum_search_blogs(q, max_results=50)
        new_d = [u for u in daum_urls if u not in seen]
        seen.update(new_d)
        all_urls.extend(new_d)
        if new_d:
            log(f"[다음] '{q}' → {len(new_d)}개 추가 (누적 {len(all_urls)}개)", on_log)
        time.sleep(1.5)

    log(f"[수집] 총 {len(all_urls)}개 블로그 URL 수집 완료 (Tistory+WordPress 등)", on_log)
    return all_urls


# 하위 호환 별칭
def google_search_blogs(query, page=None, max_results=100):
    return naver_search_blogs(query, max_results)


def google_search_tistory(query, page=None, max_results=100):
    return naver_search_blogs(query, max_results)


def collect_all_tistory_urls(category, page=None, on_log=None):
    return collect_all_blog_urls(category, page, on_log)


# ── 2단계: pub코드 추출 (Playwright — JS 렌더링) ────────────────────────────

def extract_pub_codes_playwright(urls: list[str], page, on_log=None) -> dict[str, str]:
    """{url: pub_code} 딕셔너리 반환. Playwright로 각 사이트 방문."""
    results = {}
    for i, url in enumerate(urls):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=10000)
            page.wait_for_timeout(800)
            html = page.content()
            m = PUB_PATTERN.search(html)
            if m:
                pub_code = f"ca-pub-{m.group(1)}"
                results[url] = pub_code
                log(f"[pub] ({i+1}/{len(urls)}) ✓ {url.split('//')[1][:30]} → {pub_code}", on_log)
            else:
                log(f"[pub] ({i+1}/{len(urls)}) pub코드 없음: {url.split('//')[1][:30]}", on_log)
        except Exception as e:
            log(f"[pub] ({i+1}/{len(urls)}) 오류: {url.split('//')[1][:30]} — {e}", on_log)
        time.sleep(0.3)
    return results


# ── 3단계: pub코드 역검색 → 파워 운영자 전체 사이트 수집 ────────────────────

def reverse_lookup_pub_code(pub_code: str, page=None, max_results: int = 200) -> list[str]:
    """SpyOnWeb으로 pub코드 역검색 → 같은 pub코드를 쓰는 모든 사이트 수집.
    spyonweb.com에 pub코드 직접 조회 → 연관 도메인 목록 파싱."""
    sites = []
    seen = set()

    # SpyOnWeb: pub코드로 연관 사이트 조회
    url = f"https://spyonweb.com/{urllib.parse.quote(pub_code)}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # SpyOnWeb 결과: 도메인 목록 파싱
        # 패턴: <a href="/domain.com"> 또는 도메인 링크
        domains = re.findall(r'href="https?://([a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,})"', html)
        domains += re.findall(r'href="/([a-zA-Z0-9\-]+\.[a-zA-Z0-9\-\.]+)"', html)
        for domain in domains:
            domain = domain.strip("/").lower()
            if not domain or "spyonweb" in domain or "." not in domain:
                continue
            root = f"https://{domain}"
            if root not in seen:
                seen.add(root)
                sites.append(root)
        time.sleep(2)
    except Exception:
        pass

    # DNSlytics 보조 조회
    if len(sites) < 5:
        url2 = f"https://dnslytics.com/adsense/{urllib.parse.quote(pub_code)}"
        try:
            req2 = urllib.request.Request(url2, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            })
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                html2 = resp2.read().decode("utf-8", errors="ignore")
            domains2 = re.findall(r'href="https?://([a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,})"', html2)
            for domain in domains2:
                root = f"https://{domain.lower()}"
                if root not in seen and "dnslytics" not in root:
                    seen.add(root)
                    sites.append(root)
            time.sleep(1)
        except Exception:
            pass

    return sites


def find_power_publishers(pub_map: dict[str, str], page=None, min_sites: int = MIN_SITES_PER_PUB, on_log=None) -> dict[str, list[str]]:
    """SpyOnWeb/DNSlytics로 pub코드 역검색 → 파워 운영자(min_sites개 이상) 사이트 목록 반환."""
    unique_pubs = list(set(pub_map.values()))
    log(f"[역검색] {len(unique_pubs)}개 pub코드 SpyOnWeb 역검색 시작 (기준: {min_sites}개+)", on_log)

    power: dict[str, list[str]] = {}
    for i, pub_code in enumerate(unique_pubs):
        sites = reverse_lookup_pub_code(pub_code, max_results=300)
        log(f"[역검색] ({i+1}/{len(unique_pubs)}) {pub_code} → {len(sites)}개 사이트", on_log)
        if len(sites) >= min_sites:
            power[pub_code] = sites
            log(f"[파워] ★ {pub_code}: {len(sites)}개 사이트 — 파워 운영자!", on_log)
        time.sleep(1)

    return power


# ── 4단계: RSS → 최신 글 제목 수집 ─────────────────────────────────────────

def _fetch_rss_titles(url: str, max_titles: int = 20) -> list[str]:
    """RSS 피드에서 최신 글 제목 추출. Tistory(/rss) + WordPress(/feed) 모두 지원."""
    base = url.rstrip("/")
    candidates = [base + "/rss", base + "/feed", base + "/feed/rss2"]
    for rss_url in candidates:
        try:
            req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
            root_el = ET.fromstring(content)
            titles = []
            for item in root_el.iter("item"):
                title_el = item.find("title")
                if title_el is not None and title_el.text:
                    title = title_el.text.strip()
                    if len(title) > 5:
                        titles.append(title)
                if len(titles) >= max_titles:
                    break
            if titles:
                return titles
        except Exception:
            continue
    return []


def collect_power_publisher_titles(power_pubs: dict[str, list[str]], on_log=None) -> list[str]:
    """파워 운영자 전체 사이트 RSS → 최신 글 제목 수집."""
    all_titles = []
    total_sites = sum(len(v) for v in power_pubs.values())
    log(f"[RSS] 파워 운영자 {len(power_pubs)}명 / {total_sites}개 사이트 RSS 수집 시작", on_log)

    def _fetch(url):
        return _fetch_rss_titles(url)

    with ThreadPoolExecutor(max_workers=10) as pool:
        all_urls = [url for sites in power_pubs.values() for url in sites]
        futures = {pool.submit(_fetch, url): url for url in all_urls}
        for fut in as_completed(futures):
            titles = fut.result()
            all_titles.extend(titles)

    # 중복 제거
    seen = set()
    unique = []
    for t in all_titles:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    log(f"[RSS] 총 {len(unique)}개 고유 제목 수집 완료", on_log)
    return unique


# ── 5단계: 제목 → seed 키워드 → 롱테일 확장 → DB 저장 ───────────────────────

def _clean_title_to_keyword(title: str) -> str:
    """제목에서 핵심 검색 키워드 추출. 자동완성에 맞게 15자 이내로 압축."""
    import html as _html
    title = _html.unescape(title)
    title = re.sub(r"<[^>]+>", "", title)
    # 꼬리말 제거
    title = re.sub(
        r"\s*(총정리|완벽정리|알아보기|알아보자|소개합니다|해봤어요|꿀팁|입니다|합니다|해요|정리|후기|리뷰)\s*$",
        "", title, flags=re.IGNORECASE
    )
    # 구분자 기준 앞부분만
    title = re.split(r"[|｜ㅣ\-·:：]", title)[0]
    title = re.sub(r"\s+", " ", title).strip()
    if not title or len(title) < 5:
        return ""
    # 15자 초과 시: 첫 공백 기준 앞 2~3 어절만 추출
    if len(title) > 15:
        words = title.split()
        title = " ".join(words[:3]) if len(words) >= 3 else " ".join(words[:2])
    return title if len(title) >= 5 else ""


def _naver_autocomplete(keyword: str, max_results: int = 10) -> list[str]:
    """네이버 자동완성 API → 연관 롱테일 키워드."""
    try:
        encoded = urllib.parse.quote(keyword)
        url = f"https://ac.search.naver.com/nx/ac?q={encoded}&q_enc=UTF-8&st=100&frm=nv&r_format=json&r_enc=UTF-8&r_lt=10&r_unicode=0&t_koreng=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("items", [[]])[0]
        return [item[0] for item in items[:max_results] if item]
    except Exception:
        return []


def _naver_related(keyword: str, max_results: int = 8) -> list[str]:
    """네이버 블로그 검색 연관검색어."""
    try:
        encoded = urllib.parse.quote(keyword)
        url = f"https://search.naver.com/search.naver?where=blog&query={encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        tags = re.findall(r'<a[^>]+class="[^"]*relate[^"]*"[^>]*>([^<]+)</a>', html)
        if not tags:
            tags = re.findall(r'"relatedQuery"\s*:\s*"([^"]+)"', html)
        return [t.strip() for t in tags[:max_results] if t.strip()]
    except Exception:
        return []


def expand_to_longtail(seed_keywords: list[str], category: str, on_log=None) -> list[str]:
    """seed 키워드 → 자동완성 + 연관검색어로 롱테일 확장."""
    all_longtails = set()
    for i, kw in enumerate(seed_keywords[:50]):  # 상위 50개 seed만
        ac = _naver_autocomplete(kw)
        rel = _naver_related(kw)
        longtails = ac + rel
        all_longtails.update(longtails)
        if (i + 1) % 10 == 0:
            log(f"[롱테일] {i+1}/{min(len(seed_keywords),50)}개 처리 → 누적 {len(all_longtails)}개", on_log)
        time.sleep(0.2)
    log(f"[롱테일] 총 {len(all_longtails)}개 롱테일 확장 완료", on_log)
    return list(all_longtails)


def save_keywords_to_db(keywords: list[str], category: str, on_log=None):
    """키워드 → DB 저장 (중복 스킵)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    saved = 0
    skipped = 0
    for kw in keywords:
        kw = kw.strip()
        if not kw or len(kw) < 5:
            continue
        exists = conn.execute(
            "SELECT 1 FROM keywords WHERE keyword=?", (kw,)
        ).fetchone()
        if exists:
            skipped += 1
            continue
        from datetime import datetime
        conn.execute(
            "INSERT INTO keywords(keyword, score, volume, pub_count, created_at, category, status) "
            "VALUES(?,?,?,?,?,?,?)",
            (kw, 0.0, 0, 0, datetime.now().isoformat(), category, "pending")
        )
        saved += 1
    conn.commit()
    conn.close()
    log(f"[DB] {saved}개 저장 / {skipped}개 중복 스킵", on_log)
    return saved


def save_sites_to_db(pub_map: dict[str, str], category: str):
    """수집된 사이트 + pub코드 DB 저장."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            url TEXT PRIMARY KEY,
            pub_code TEXT,
            category TEXT,
            discovered_at TEXT
        )
    """)
    # 기존 테이블에 컬럼 누락 시 마이그레이션
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(sites)")}
    for col, typedef in [("category", "TEXT"), ("discovered_at", "TEXT")]:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE sites ADD COLUMN {col} {typedef}")
    from datetime import datetime
    now = datetime.now().isoformat()
    for url, pub in pub_map.items():
        conn.execute(
            "INSERT OR REPLACE INTO sites(url, pub_code, category, discovered_at) VALUES(?,?,?,?)",
            (url, pub, category, now)
        )
    # pub코드 없는 사이트도 저장
    conn.commit()
    conn.close()


# ── 메인 실행 ────────────────────────────────────────────────────────────────

def run(category: str = "여행", on_log=None) -> int:
    """전체 파이프라인 실행. 저장된 키워드 수 반환."""
    from browser import connect_cdp

    log(f"\n{'='*55}", on_log)
    log(f"  Google Harvester — 카테고리: {category}", on_log)
    log(f"{'='*55}", on_log)

    blog_urls: list[str] = []
    power_pubs: dict[str, list[str]] = {}

    pw, browser = connect_cdp(on_log=on_log)
    try:
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()

        # 1. 구글 검색 → 블로그 URL 수집 (전용 페이지)
        search_page = ctx.new_page()
        blog_urls = collect_all_blog_urls(category, search_page, on_log)
        search_page.close()  # 구글 검색 페이지 닫기 — pub코드 추출용 새 페이지 필요

        if not blog_urls:
            log("[오류] 블로그 URL 수집 실패", on_log)
            return 0

        # 2. pub코드 추출 (새 페이지로 — 구글 CAPTCHA 상태 격리)
        log(f"\n[pub] {len(blog_urls)}개 사이트 pub코드 추출 중...", on_log)
        pub_page = ctx.new_page()
        pub_map = extract_pub_codes_playwright(blog_urls, pub_page, on_log)
        pub_page.close()
        log(f"[pub] pub코드 확인: {len(pub_map)}개 / {len(blog_urls)}개", on_log)

        # DB에 사이트 저장
        save_sites_to_db(pub_map, category)

        # 3. SpyOnWeb/DNSlytics pub코드 역검색 → 파워 운영자 선별
        power_pubs = find_power_publishers(pub_map, min_sites=MIN_SITES_PER_PUB, on_log=on_log)
        log(f"\n[파워] pub코드 {len(power_pubs)}개 ({MIN_SITES_PER_PUB}개 이상 사이트 운영자)", on_log)
        for pub, sites in sorted(power_pubs.items(), key=lambda x: -len(x[1]))[:10]:
            log(f"  {pub}: {len(sites)}개 사이트", on_log)

    finally:
        pw.stop()

    # 4. 파워 운영자 RSS → 최신 제목 수집
    if not power_pubs:
        log("[경고] 파워 운영자 없음 — 전체 사이트 RSS 수집으로 폴백", on_log)
        power_pubs = {"all": blog_urls[:50]}

    raw_titles = collect_power_publisher_titles(power_pubs, on_log)

    # 제목 → seed 키워드 정제
    seeds = []
    seen = set()
    for title in raw_titles:
        kw = _clean_title_to_keyword(title)
        if kw and kw not in seen:
            seen.add(kw)
            seeds.append(kw)
    log(f"\n[seed] {len(seeds)}개 seed 키워드 추출", on_log)

    # 5. 롱테일 확장
    longtails = expand_to_longtail(seeds, category, on_log)

    # seed + longtail 모두 저장
    all_keywords = list(set(seeds + longtails))
    saved = save_keywords_to_db(all_keywords, category, on_log)

    log(f"\n{'='*55}", on_log)
    log(f"  완료: {saved}개 신규 키워드 저장 (카테고리: {category})", on_log)
    log(f"{'='*55}\n", on_log)
    return saved


if __name__ == "__main__":
    import sys
    category = sys.argv[1] if len(sys.argv) > 1 else "여행"
    run(category)
