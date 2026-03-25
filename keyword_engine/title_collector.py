"""Tistory RSS 피드에서 글 제목 대량 수집 + 키워드 추출"""
import re
import urllib.request
import xml.etree.ElementTree as ET

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# ── 제목 정제 패턴 ─────────────────────────────────────────

# 제목 앞 접두어
_HEAD = re.compile(
    r"^(안녕하세요[\.\s]*|오늘은\s*|오늘의\s*|이번에는\s*|이번주\s*|최근\s*)"
)

# 조건절/역접 — 이 앞까지만 키워드 (ex: "밤티 뜻 모르면" → "밤티 뜻")
_COND = re.compile(r"\s+(모르면|없으면|있으면|알면|된다면|하면|이라면|라면|이면|한다면)\b.*$")

# "X하는 방법/법/하기" → "X방법" (동사어미 압축)
_VERB_METHOD = re.compile(r"([가-힣a-zA-Z]+)(하는|되는|만드는|쓰는|받는|보는)\s*(방법|법|하기)")

# 꼬리말 — 반복 제거
_TAILS = re.compile(
    r"\s*(총정리|완벽정리|한눈에보기|한눈에|알아보기|알아보자|알아봐요"
    r"|알려드림|알려드립니다|살펴보기|소개합니다|소개해요|해봤어요|해봤습니다"
    r"|해볼게요|모아봤어요|모아봤습니다|꿀팁모음|꿀팁|팁모음|활용법|활용팁"
    r"|입니다|합니다|해요|이에요|했어요|이었습니다"
    r"|하는법|하는방법|만드는법|만드는방법)\s*$",
    re.IGNORECASE,
)

# 숫자/영문 꼬리 (TOP 10, BEST 5, 2024 등)
_NUM_TAIL = re.compile(r"\s+(TOP|top|BEST|Best|best|\d+위?편?화?개?)\s*$")

# 구분자
_SEP = re.compile(r"\s*[\|\-·ㅣ:：]\s*")

# 끝 조사 제거: "외장 하드가" → "외장 하드"
_PARTICLE = re.compile(
    r"(가|이|은|는|을|를|의|에서|으로|로|와|과|도|만|까지|부터|한테|에게|께서)$"
)

# 꼬리 동사형: "절약하는" → "절약"
_VERB_TAIL = re.compile(r"([가-힣]+)(하는|되는|만드는|있는|없는|쓰는|받는|보는)$")

# 이것/저것/그것/슬랭 필터 — 포함 시 전체 버림
_NOISE_WORDS = re.compile(r"이것까지|저것까지|모름주의|주의보|난리났|난리남|난리난|핵꿀팁|레전드|ㅋㅋ|ㅠㅠ")


def _clean_title(title: str) -> str:
    """제목 → 핵심 검색 키워드"""
    title = re.sub(r"<[^>]+>", "", title)
    title = re.sub(r"[^\w\s가-힣a-zA-Z0-9]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()

    # 노이즈 포함 제목 전체 버림
    if _NOISE_WORDS.search(title):
        return ""

    # 앞 접두어 제거
    title = _HEAD.sub("", title).strip()

    # 구분자 기준 첫 파트만
    title = _SEP.split(title)[0].strip()

    # 조건절 이전까지만
    title = _COND.sub("", title).strip()

    # "X하는 방법" → "X방법"
    title = _VERB_METHOD.sub(r"\1\3", title)

    # 꼬리말 반복 제거
    for _ in range(3):
        prev = title
        title = _TAILS.sub("", title).strip()
        title = _NUM_TAIL.sub("", title).strip()
        if title == prev:
            break

    # 꼬리 동사형 제거: "절약하는" → "절약"
    title = _VERB_TAIL.sub(r"\1", title).strip()

    # 끝 조사 제거: "외장 하드가" → "외장 하드"
    title = _PARTICLE.sub("", title).strip()

    # 최대 4어절로 제한
    words = title.split()
    if len(words) > 4:
        title = " ".join(words[:4])

    return title


def _fetch(url: str, timeout: int = 8) -> str:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read(524288).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def collect_titles_from_rss(blog_url: str, on_log=None) -> list:
    """RSS에서 글 제목 수집"""
    if "blog.naver.com" in blog_url or "rss.blog.naver.com" in blog_url:
        rss_url = blog_url
    else:
        rss_url = blog_url.rstrip("/") + "/rss"

    content = _fetch(rss_url)
    if not content or ("<rss" not in content and "<feed" not in content):
        if on_log:
            on_log(f"[rss] ✗ {blog_url}")
        return []

    titles = []
    found = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", content, re.DOTALL)
    for t in found[1:]:  # 첫 번째는 채널/블로그 이름 → 스킵
        t = t.strip()
        if t and 4 <= len(t) <= 100 and not t.startswith("http"):
            titles.append(t)

    if not titles:
        try:
            root = ET.fromstring(content)
            for item in root.iter("item"):
                t = item.find("title")
                if t is not None and t.text:
                    titles.append(t.text.strip())
            for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
                t = entry.find("{http://www.w3.org/2005/Atom}title")
                if t is not None and t.text:
                    titles.append(t.text.strip())
        except Exception:
            pass

    if on_log and titles:
        on_log(f"[rss] ✓ {blog_url} → {len(titles)}개 제목")
    return titles[:80]


def collect_titles_playwright(blog_url: str, on_log=None) -> list:
    """Playwright로 블로그 포스트 목록 페이지 크롤링 — RSS보다 많은 제목 수집"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    titles = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            ).new_page()
            # 블로그 인덱스/태그 페이지 시도
            for path in ["", "/category", "/tag"]:
                try:
                    page.goto(blog_url.rstrip("/") + path, timeout=10000, wait_until="domcontentloaded")
                    # 포스트 제목 선택자 시도 (Tistory 일반 구조)
                    for sel in ["h2.tit_post", "h3.tit_post", ".post-title", "h2.title",
                                "a.link_post", ".item-subject", ".post_header h2", ".entry-title"]:
                        els = page.query_selector_all(sel)
                        for el in els:
                            t = el.inner_text().strip()
                            if t and 4 <= len(t) <= 100:
                                titles.append(t)
                    if titles:
                        break
                except Exception:
                    continue
            browser.close()
    except Exception as e:
        if on_log:
            on_log(f"[playwright] 오류 {blog_url}: {e}")

    if on_log and titles:
        on_log(f"[playwright] ✓ {blog_url} → {len(titles)}개 제목")
    return titles[:100]


def collect_from_all(blog_urls: set, use_playwright: bool = False, on_log=None) -> list:
    """여러 블로그 RSS(+Playwright)를 순회하며 전체 제목 수집"""
    all_titles = []
    success = 0
    for url in blog_urls:
        titles = collect_titles_from_rss(url, on_log)
        # RSS에서 적게 수집됐으면 Playwright로 보완
        if use_playwright and len(titles) < 10:
            pw_titles = collect_titles_playwright(url, on_log)
            if pw_titles:
                titles = list(set(titles + pw_titles))
        if titles:
            all_titles.extend(titles)
            success += 1
    if on_log:
        on_log(f"[수집] 총 {success}/{len(blog_urls)}개 블로그, {len(all_titles)}개 제목")
    return all_titles


def extract_keywords_from_titles(titles: list, top_n: int = 100) -> list:
    """
    제목에서 핵심 키워드 추출.
    - 제목당 1개 키워드 (변형 양산 방지)
    - 빈도 높은 순 top_n개 반환
    """
    from collections import Counter
    freq: Counter = Counter()

    for raw in titles:
        kw = _clean_title(raw)
        if not kw:
            continue
        if not re.search(r"[가-힣]{2,}", kw):
            continue

        char_len = len(kw.replace(" ", ""))
        if char_len < 2 or char_len > 20:
            continue

        freq[kw] += 1

    return [kw for kw, _ in freq.most_common(top_n)]
