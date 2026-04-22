"""
google_harvester.py — 구글 상위 100개 Tistory 사이트 수집 → pub코드 추출 → 파워 운영자 RSS 수집

파이프라인:
  1. 구글 검색 `keyword site:tistory.com` → 상위 100개 Tistory URL (페이지네이션)
  2. Playwright로 각 사이트 방문 → AdSense pub코드 추출 (JS 렌더링 포함)
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

MIN_SITES_PER_PUB = 5   # 파워 운영자 기준: 5개 이상 사이트
GOOGLE_NUM = 100         # 구글 검색 결과 수 (최대 100)
MAX_PAGES = 2            # 페이지당 10개 × 최대 10페이지 → 최대 100개

CATEGORY_QUERIES = {
    "여행": [
        "제주도 여행 코스", "부산 여행 추천", "강원도 여행 명소",
        "속초 여행 코스", "경주 여행 일정", "전주 한옥마을 여행",
        "여수 여행 코스", "통영 여행 추천", "남해 여행 명소",
        "국내 여행지 추천", "당일치기 여행 코스", "국내 호텔 추천",
        "해외여행 추천", "동남아 여행", "일본 여행 코스",
    ],
    "IT": [
        "아이폰 추천", "갤럭시 추천", "노트북 추천 가성비",
        "무선 이어폰 추천", "태블릿 추천", "공기청정기 추천",
        "로봇청소기 추천", "스마트워치 추천", "모니터 추천",
        "OTT 요금제 비교", "넷플릭스 요금", "게이밍 노트북",
    ],
    "살림": [
        "전기요금 절약", "생활비 줄이기", "식비 절약 방법",
        "청소 꿀팁", "냉장고 정리법", "세탁 꿀팁",
        "관리비 절약", "통신비 절약", "도시가스 절약",
    ],
    "정부지원금": [
        "청년 지원금", "정부지원금 종류", "복지 혜택 총정리",
        "기초생활수급자 혜택", "실업급여 신청", "육아휴직 급여",
        "출산 지원금", "청년도약계좌", "주거급여 신청",
    ],
    "교통": [
        "인천공항 버스 시간표", "공항버스 요금", "KTX 예매",
        "고속버스 예매", "시외버스 요금", "공항철도 소요시간",
    ],
    "영화": [
        "영화 추천 2025", "넷플릭스 신작", "영화 결말 해석",
        "드라마 추천", "OTT 추천", "공포 영화 추천",
    ],
}


def log(msg, on_log=None):
    print(msg, flush=True)
    if on_log:
        on_log(msg)


# ── 1단계: 구글 검색 → Tistory URL 수집 ────────────────────────────────────

def google_search_tistory(query: str, page, max_results: int = 100) -> list[str]:
    """구글에서 `query site:tistory.com` 검색 → Tistory 루트 URL 목록 반환."""
    urls = []
    seen = set()

    for start in range(0, max_results, 10):
        search_url = (
            f"https://www.google.com/search"
            f"?q={urllib.parse.quote(query + ' site:tistory.com')}"
            f"&num=10&start={start}&hl=ko&gl=kr"
        )
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1200)

            links = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => e.href)"
            )
            found = 0
            for link in links:
                m = TISTORY_PATTERN.match(link)
                if m:
                    root = f"https://{m.group(1)}.tistory.com"
                    if root not in seen:
                        seen.add(root)
                        urls.append(root)
                        found += 1
            if found == 0:
                break  # 결과 없음 → 중단
            time.sleep(1.5)
        except Exception as e:
            break

    return urls


def collect_all_tistory_urls(category: str, page, on_log=None) -> list[str]:
    """카테고리별 쿼리로 구글 검색 → 전체 Tistory URL 수집."""
    queries = CATEGORY_QUERIES.get(category, [])
    all_urls = []
    seen = set()

    for q in queries:
        log(f"[구글] '{q} site:tistory.com' 검색 중...", on_log)
        urls = google_search_tistory(q, page, max_results=GOOGLE_NUM)
        new = [u for u in urls if u not in seen]
        seen.update(new)
        all_urls.extend(new)
        log(f"[구글] '{q}' → {len(urls)}개 (누적 {len(all_urls)}개)", on_log)
        time.sleep(2)

    log(f"[구글] 총 {len(all_urls)}개 Tistory URL 수집 완료", on_log)
    return all_urls


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


# ── 3단계: 파워 운영자 선별 ─────────────────────────────────────────────────

def find_power_publishers(pub_map: dict[str, str], min_sites: int = MIN_SITES_PER_PUB) -> dict[str, list[str]]:
    """{pub_code: [url, ...]} 중 min_sites 이상인 파워 운영자만 반환."""
    groups: dict[str, list[str]] = {}
    for url, pub in pub_map.items():
        groups.setdefault(pub, []).append(url)

    power = {pub: sites for pub, sites in groups.items() if len(sites) >= min_sites}
    return power


# ── 4단계: RSS → 최신 글 제목 수집 ─────────────────────────────────────────

def _fetch_rss_titles(url: str, max_titles: int = 20) -> list[str]:
    """RSS 피드에서 최신 글 제목 추출."""
    rss_url = url.rstrip("/") + "/rss"
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
        return titles
    except Exception:
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
    """제목에서 핵심 검색 키워드 추출."""
    import html as _html
    title = _html.unescape(title)
    title = re.sub(r"<[^>]+>", "", title)
    # 꼬리말 제거
    title = re.sub(
        r"\s*(총정리|완벽정리|알아보기|알아보자|소개합니다|해봤어요|꿀팁|입니다|합니다|해요)\s*$",
        "", title, flags=re.IGNORECASE
    )
    # 구분자 기준 앞부분만
    title = re.split(r"[|｜ㅣ\-·]", title)[0]
    title = re.sub(r"\s+", " ", title).strip()
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

    pw, browser = connect_cdp(on_log=on_log)
    try:
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()

        # 1. 구글 검색 → Tistory URL 수집
        tistory_urls = collect_all_tistory_urls(category, page, on_log)
        if not tistory_urls:
            log("[오류] Tistory URL 수집 실패", on_log)
            return 0

        # 2. pub코드 추출 (Playwright)
        log(f"\n[pub] {len(tistory_urls)}개 사이트 pub코드 추출 중...", on_log)
        pub_map = extract_pub_codes_playwright(tistory_urls, page, on_log)
        log(f"[pub] pub코드 확인: {len(pub_map)}개 / {len(tistory_urls)}개", on_log)

        # DB에 사이트 저장
        save_sites_to_db(pub_map, category)

        # 3. 파워 운영자 선별
        power_pubs = find_power_publishers(pub_map, min_sites=MIN_SITES_PER_PUB)
        log(f"\n[파워] pub코드 {len(power_pubs)}개 ({MIN_SITES_PER_PUB}개 이상 사이트 운영자)", on_log)
        for pub, sites in sorted(power_pubs.items(), key=lambda x: -len(x[1]))[:10]:
            log(f"  {pub}: {len(sites)}개 사이트", on_log)

        page.close()
    finally:
        pw.stop()

    # 4. 파워 운영자 RSS → 최신 제목 수집
    if not power_pubs:
        log("[경고] 파워 운영자 없음 — 전체 사이트 RSS 수집으로 폴백", on_log)
        # 폴백: 수집된 전체 사이트 사용
        power_pubs = {"all": tistory_urls[:50]}

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
