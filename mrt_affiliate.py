"""마이리얼트립 파트너 제휴 링크 자동 생성 (공식 API 사용)

흐름:
  키워드 → myrealtrip.com 검색(Playwright) → 상품 URL 수집
        → POST /v1/mylink API → myrealt.rip 단축 제휴 링크 반환

API:
  Base: https://partner-ext-api.myrealtrip.com
  Auth: Authorization: Bearer {MRT_API_KEY}
  Link: POST /v1/mylink  body: {"targetUrl": "..."}
  Response: {"data": {"mylink": "https://myrealt.rip/..."}}

사용:
  from mrt_affiliate import get_affiliate_links, create_affiliate_link
  links = get_affiliate_links("도쿄 디즈니랜드", top_n=3)
  link  = create_affiliate_link("https://www.myrealtrip.com/offers/71825")
"""
import os
import re
import time
import json
import urllib.request
import urllib.parse
from pathlib import Path

# .env 로드
_root = Path(__file__).parent
_env = _root / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

SEARCH_URL   = "https://www.myrealtrip.com/offers?q={query}"
API_BASE     = "https://partner-ext-api.myrealtrip.com"
MYLINK_PATH  = "/v1/mylink"


def _api_headers() -> dict:
    api_key = os.environ.get("MRT_API_KEY", "")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }


# ── API: 제휴 링크 생성 ──────────────────────────────────────────────────────

def create_affiliate_link(target_url: str, on_log=None) -> str | None:
    """MRT 공식 API로 targetUrl → myrealt.rip 단축 제휴 링크 생성."""
    def log(msg):
        if on_log: on_log(msg)
        print(msg, flush=True)

    if not target_url or not target_url.startswith("http"):
        log(f"[MRT API] 잘못된 URL: {target_url}")
        return None

    api_key = os.environ.get("MRT_API_KEY", "")
    if not api_key:
        log("[MRT API] MRT_API_KEY 없음 — .env 확인")
        return None

    try:
        body = json.dumps({"targetUrl": target_url}).encode()
        req = urllib.request.Request(
            f"{API_BASE}{MYLINK_PATH}",
            data=body,
            headers=_api_headers(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read().decode())
            mylink = resp.get("data", {}).get("mylink")
            if mylink:
                log(f"[MRT API] ✅ 제휴 링크 생성: {target_url[:50]} → {mylink}")
                return mylink
            log(f"[MRT API] 응답에 mylink 없음: {resp}")
            return None
    except urllib.error.HTTPError as e:
        body_err = e.read().decode()[:200]
        log(f"[MRT API] HTTP {e.code}: {body_err}")
        return None
    except Exception as e:
        log(f"[MRT API] 오류: {e}")
        return None


# ── Playwright: 상품 검색 (키워드 → URL 목록) ─────────────────────────────

def _search_products(page, keyword: str, top_n: int = 5) -> list[dict]:
    """키워드로 상품 검색 → 상위 n개 {title, url} 반환."""
    q = urllib.parse.quote(keyword)
    page.goto(SEARCH_URL.format(query=q), wait_until="domcontentloaded", timeout=20000)

    for _ in range(10):
        time.sleep(1)
        count = page.evaluate("""() =>
            [...document.querySelectorAll('a[href]')]
            .filter(el => /(experiences|offers)\\.myrealtrip\\.com\\/products\\/\\d+/.test(el.href) ||
                          /myrealtrip\\.com\\/offers\\/\\d+/.test(el.href))
            .length
        """)
        if count > 0:
            break

    products = page.evaluate("""(topN) => {
        const seen = new Set();
        const items = [];
        for (const el of document.querySelectorAll('a[href]')) {
            const href = el.href || '';
            if (!/(experiences|offers|products)/.test(href)) continue;
            if (!/\\/\\d{4,}/.test(href)) continue;
            if (seen.has(href)) continue;
            seen.add(href);
            const title = el.innerText.trim().replace(/\\s+/g, ' ').substring(0, 80);
            if (title.length < 5) continue;
            items.push({ title, url: href });
            if (items.length >= topN) break;
        }
        return items;
    }""", top_n)

    return products


# ── 메인 함수 ─────────────────────────────────────────────────────────────────

def get_affiliate_links(keyword: str, top_n: int = 3, on_log=None) -> list[dict]:
    """키워드로 MRT 상품 검색 → API로 제휴 링크 생성.

    Returns:
        [{"title": str, "original_url": str, "affiliate_url": str | None}, ...]
    """
    from browser import connect_cdp

    def log(msg):
        if on_log: on_log(msg)
        print(msg, flush=True)

    results = []
    pw, browser = connect_cdp(on_log=on_log)

    try:
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()

        # 1. 상품 검색 (Playwright)
        log(f"[MRT] '{keyword}' 검색 중...")
        products = _search_products(page, keyword, top_n=top_n)
        log(f"[MRT] 상품 {len(products)}개 발견")
        for p in products:
            log(f"  - {p['title'][:50]} → {p['url']}")

        page.close()

    except Exception as e:
        log(f"[MRT] 검색 오류: {e}")
        products = []
    finally:
        pw.stop()

    if not products:
        log("[MRT] ⚠️ 검색 결과 없음")
        return []

    # 2. API로 제휴 링크 생성 (Playwright 세션 종료 후)
    for product in products:
        log(f"\n[MRT] 링크 생성: {product['title'][:40]}")
        affiliate_url = create_affiliate_link(product["url"], on_log=on_log)
        results.append({
            "title": product["title"],
            "original_url": product["url"],
            "affiliate_url": affiliate_url,
        })

    success = len([r for r in results if r['affiliate_url']])
    log(f"\n[MRT] 완료: {success}/{len(results)}개 링크 생성")
    return results


# ── 하위 호환: Playwright 기반 함수 (더 이상 사용 안 함) ─────────────────────

def _ensure_partner_login(page, on_log=None) -> bool:
    """[Deprecated] API 전환으로 더 이상 사용하지 않음. 항상 True 반환."""
    return True


# ── 직접 실행 테스트 ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    kw = sys.argv[1] if len(sys.argv) > 1 else "도쿄 디즈니랜드"
    links = get_affiliate_links(kw, top_n=3)
    print("\n=== 결과 ===")
    for l in links:
        print(f"  {l['title'][:40]}")
        print(f"  제휴: {l['affiliate_url']}")
