"""Tistory RSS 피드에서 글 제목 대량 수집 + 키워드 추출"""
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

STOPWORDS = {
    "이것", "저것", "그것", "하는", "있는", "없는", "하기", "알아보기",
    "총정리", "완벽정리", "대해서", "대하여", "정리해", "알려드림",
    "입니다", "습니다", "해요", "이에요", "했어요", "해봤어요",
}

# 키워드로 쓸 수 없는 어미/조사 패턴
_BAD_ENDINGS = re.compile(
    r"(하는법$|하는 법$|이란$|이란\?$|란\?$|란$|일까$|일까\?$"
    r"|할까$|할까\?$|인지$|인지\?$|겠어$|겠죠$|했어$|됩니다$"
    r"|이에요$|예요$|거든$|거든요$|이죠$|이라고$|이라는$)"
)
_BAD_STARTS = re.compile(r"^(그|이|저|아|저기|여기|거기|무슨|어떤|어디|언제|왜|어떻게)\s")


def _fetch(url: str, timeout: int = 8) -> str:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read(524288).decode("utf-8", errors="ignore")  # 512KB
    except Exception:
        return ""


def collect_titles_from_rss(blog_url: str, on_log=None) -> list:
    """Tistory RSS에서 글 제목 수집"""
    rss_url = blog_url.rstrip("/") + "/rss"
    content = _fetch(rss_url)

    if not content or ("<rss" not in content and "<feed" not in content):
        if on_log:
            on_log(f"[rss] ✗ {blog_url}")
        return []

    titles = []
    # 정규식으로 먼저 시도 (CDATA/일반 title 모두 처리)
    found = re.findall(
        r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>",
        content, re.DOTALL
    )
    for t in found:
        t = t.strip()
        # 채널 제목(짧은 것)은 제외, RSS 피드 자체 제목 스킵
        if t and 4 <= len(t) <= 100 and not t.startswith("http"):
            titles.append(t)

    # 정규식 실패 시 ET 폴백
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


def collect_from_all(blog_urls: set, on_log=None) -> list:
    """여러 Tistory 블로그 RSS를 순회하며 전체 제목 수집"""
    all_titles = []
    success = 0
    for url in blog_urls:
        titles = collect_titles_from_rss(url, on_log)
        if titles:
            all_titles.extend(titles)
            success += 1
    if on_log:
        on_log(f"[rss] 총 {success}/{len(blog_urls)}개 블로그, {len(all_titles)}개 제목 수집")
    return all_titles


def extract_keywords_from_titles(titles: list, top_n: int = 100) -> list:
    """제목 리스트에서 검색 키워드 후보 추출 — 빈도 높은 순 top_n개 반환"""
    from collections import Counter
    freq: Counter = Counter()

    for title in titles:
        title = re.sub(r"<[^>]+>", "", title)
        title = re.sub(r"[^\w\s가-힣a-zA-Z0-9]", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        if not title or len(title) < 2:
            continue

        candidates = set()

        # 전체 제목
        clean = title.strip()
        if 2 <= len(clean.replace(" ", "")) <= 20 and re.search(r"[가-힣]{2,}", clean):
            candidates.add(clean)

        # 구분자로 분리
        parts = re.split(r"[\|\-·:,\[\]()【】『』「」::ㅣ]", title)
        for part in parts:
            part = part.strip()
            if part in STOPWORDS:
                continue
            if re.search(r"[가-힣]{2,}", part) and 2 <= len(part.replace(" ", "")) <= 20:
                candidates.add(part)

        # 2~3어절 조합
        words = [w for w in title.split() if len(w) >= 2 and re.search(r"[가-힣]", w)]
        for i in range(len(words)):
            for n in (2, 3):
                if i + n <= len(words):
                    phrase = " ".join(words[i: i + n])
                    char_len = len(phrase.replace(" ", ""))
                    if re.search(r"[가-힣]{2,}", phrase) and 4 <= char_len <= 20:
                        candidates.add(phrase)

        for k in candidates:
            if any(sw in k for sw in STOPWORDS):
                continue
            if _BAD_ENDINGS.search(k):
                continue
            if _BAD_STARTS.match(k):
                continue
            if not re.search(r"[가-힣]{2,}", k):
                continue
            freq[k] += 1

    # 빈도 높은 순으로 top_n개 반환
    return [kw for kw, _ in freq.most_common(top_n)]
