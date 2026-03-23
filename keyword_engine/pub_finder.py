"""AdSense pub코드 추출 — Playwright headless로 JS 실행 후 정확히 추출"""
import re
import time
from pathlib import Path

PUB_PATTERN = re.compile(r"ca-pub-(\d{16})")


def find_pub_codes_playwright(urls: list, on_log=None) -> dict:
    """
    URL 리스트에서 AdSense pub코드 추출
    Playwright headless 사용 (JS 실행 → 정확한 감지)

    Returns:
        {url: pub_code} — pub코드 없으면 포함 안 됨
    """
    from playwright.sync_api import sync_playwright

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        for url in urls:
            try:
                page.goto(url, timeout=10000, wait_until="domcontentloaded")
                html = page.content()
                m = PUB_PATTERN.search(html)
                if m:
                    pub_code = f"ca-pub-{m.group(1)}"
                    results[url] = pub_code
                    if on_log:
                        on_log(f"[pub_finder] ✓ {url} → {pub_code}")
                else:
                    if on_log:
                        on_log(f"[pub_finder] ✗ {url}")
            except Exception as e:
                if on_log:
                    on_log(f"[pub_finder] 오류 {url}: {e}")
            time.sleep(0.3)

        browser.close()

    return results


def group_by_pub_code(pub_map: dict) -> dict:
    """
    {url: pub_code} → {pub_code: [url1, url2, ...]}
    같은 pub코드 = 같은 운영자
    """
    groups = {}
    for url, pub in pub_map.items():
        groups.setdefault(pub, []).append(url)
    # 사이트 수 많은 순으로 정렬
    return dict(sorted(groups.items(), key=lambda x: len(x[1]), reverse=True))


def find_pub_codes_fast(urls: list, on_log=None) -> dict:
    """
    urllib 경량 버전 — JS 없이 HTML 헤더만 체크 (빠름, 일부 누락 가능)
    Playwright 설치 안 된 환경용 폴백
    """
    import urllib.request

    results = {}
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

    for url in urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=6)
            chunk = resp.read(16384).decode("utf-8", errors="ignore")
            m = PUB_PATTERN.search(chunk)
            if m:
                pub_code = f"ca-pub-{m.group(1)}"
                results[url] = pub_code
                if on_log:
                    on_log(f"[pub_finder] ✓ {url} → {pub_code}")
            else:
                if on_log:
                    on_log(f"[pub_finder] ✗ {url}")
        except Exception:
            pass
        time.sleep(0.2)

    return results
