"""AdSense pub코드 추출 — Playwright headless로 JS 실행 후 정확히 추출"""
import re
import time
import threading
from pathlib import Path

PUB_PATTERN = re.compile(r"ca-pub-(\d{16})")


def find_pub_codes_playwright(urls: list, on_log=None, workers: int = 5) -> dict:
    """
    URL 리스트에서 AdSense pub코드 추출
    Playwright headless + 다중 페이지 병렬 처리 (기본 5 워커)

    Returns:
        {url: pub_code} — pub코드 없으면 포함 안 됨
    """
    from playwright.sync_api import sync_playwright
    from concurrent.futures import ThreadPoolExecutor

    results = {}
    lock = threading.Lock()
    url_chunks = [urls[i::workers] for i in range(workers)]

    def _worker(chunk):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = ctx.new_page()
            for url in chunk:
                try:
                    page.goto(url, timeout=10000, wait_until="domcontentloaded")
                    html = page.content()
                    m = PUB_PATTERN.search(html)
                    if m:
                        pub_code = f"ca-pub-{m.group(1)}"
                        with lock:
                            results[url] = pub_code
                        if on_log:
                            on_log(f"[pub_finder] ✓ {url} → {pub_code}")
                except Exception:
                    pass
            browser.close()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_worker, url_chunks))

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


def find_pub_codes_fast(urls: list, on_log=None, workers: int = 8) -> dict:
    """
    urllib 경량 버전 — JS 없이 HTML 헤더만 체크 (빠름, 일부 누락 가능)
    ThreadPoolExecutor로 병렬 처리 (기본 20 워커)
    """
    import ssl
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor

    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    results = {}
    lock = threading.Lock()
    # SSL 인증서 검증 비활성화 (외부 블로그 - 다양한 인증서 환경)
    _ctx = ssl.create_default_context()
    _ctx.check_hostname = False
    _ctx.verify_mode = ssl.CERT_NONE

    def _fetch(url):
        try:
            req = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=6, context=_ctx)
            chunk = resp.read(16384).decode("utf-8", errors="ignore")
            m = PUB_PATTERN.search(chunk)
            if m:
                pub_code = f"ca-pub-{m.group(1)}"
                with lock:
                    results[url] = pub_code
                if on_log:
                    on_log(f"[pub_finder] ✓ {url} → {pub_code}")
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_fetch, urls))

    return results
