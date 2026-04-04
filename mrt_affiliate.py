"""마이리얼트립 파트너 제휴 링크 자동 생성
흐름:
  키워드 → myrealtrip.com 검색 → 상품 URL 수집
        → 파트너 링크 생성기에 URL 입력 → 제휴 링크 반환

사용:
  from mrt_affiliate import get_affiliate_links
  links = get_affiliate_links("도쿄 디즈니랜드", top_n=3)
  # → [{"title": "...", "original_url": "...", "affiliate_url": "..."}, ...]
"""
import os
import re
import time
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

SEARCH_URL     = "https://www.myrealtrip.com/offers?q={query}"
LINK_GEN_URL   = "https://partner.myrealtrip.com/partnership-marketing/link-generator"
URL_INPUT_SEL  = 'input[placeholder*="마이리얼트립 상품 주소"]'
MAKE_LINK_BTN  = 'button[type="submit"]:has-text("홍보 링크 만들기")'


# ── 1. myrealtrip.com 상품 검색 ──────────────────────────────────────────────

def _search_products(page, keyword: str, top_n: int = 5) -> list[dict]:
    """키워드로 상품 검색 → 상위 n개 {title, url} 반환."""
    import urllib.parse
    q = urllib.parse.quote(keyword)
    page.goto(SEARCH_URL.format(query=q), wait_until="domcontentloaded", timeout=20000)

    # JS 렌더링 대기 — 상품 링크 나타날 때까지 최대 10초 폴링
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
        const links = [...document.querySelectorAll('a[href]')];
        for (const el of links) {
            const href = el.href || '';
            // experiences.myrealtrip.com/products/{id} 또는 myrealtrip.com/offers/{id}
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


# ── 2. 파트너 제휴 링크 생성 ─────────────────────────────────────────────────

def _generate_link(page, product_url: str, on_log=None) -> str | None:
    """상품 URL → 파트너 제휴 링크 반환."""
    def log(msg):
        if on_log:
            on_log(msg)
        print(msg, flush=True)

    # 링크 생성 페이지로 이동
    # 링크 생성 페이지로 이동 (항상 새로 이동하여 상태 초기화)
    page.goto(LINK_GEN_URL, wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)

    # 입력창 대기
    for _ in range(5):
        if page.locator(URL_INPUT_SEL).count() > 0:
            break
        time.sleep(1)

    # URL 입력
    try:
        inp = page.locator(URL_INPUT_SEL)
        if inp.count() == 0:
            log(f"  ⚠️ URL 입력창 없음 (URL: {page.url})")
            return None
        inp.first.click()
        inp.first.press("Control+a")
        inp.first.fill(product_url)
        time.sleep(1)
        log(f"  입력값 확인: {inp.first.input_value()[:60]}")
    except Exception as e:
        log(f"  URL 입력 실패: {e}")
        return None

    # "홍보 링크 만들기" 버튼 클릭 (Playwright locator 사용)
    try:
        # 여러 방법으로 버튼 탐색
        btn = None
        for sel in [
            'button:has-text("홍보 링크 만들기")',
            'button.css-6xm15k',
            'button[type="submit"]:first-of-type',
        ]:
            loc = page.locator(sel)
            if loc.count() > 0:
                btn = loc.first
                log(f"  버튼 셀렉터: {sel}")
                break

        if btn is None:
            # 마지막 수단: 첫 번째 submit 버튼
            all_btns = page.locator('button[type="submit"]')
            log(f"  submit 버튼 수: {all_btns.count()}")
            if all_btns.count() > 0:
                btn = all_btns.first

        if btn is None:
            log("  ⚠️ 버튼 없음")
            return None

        btn.click()
        log("  ✅ 홍보 링크 만들기 클릭")
        time.sleep(3)
    except Exception as e:
        log(f"  버튼 클릭 실패: {e}")
        return None

    # 생성된 링크 추출: myrealt.rip 단축 링크 최우선
    affiliate_url = page.evaluate("""() => {
        // 방법1: 페이지 본문에서 myrealt.rip / mrt.im 단축 링크 탐색 (최우선)
        const all = document.body.innerText;
        const m = all.match(/https?:\\/\\/(?:myrealt\\.rip|mrt\\.im)\\/\\S+/);
        if (m) return m[0];
        // 방법2: readonly input (결과 필드)
        const readonlyInp = document.querySelector('input[readonly]');
        if (readonlyInp && readonlyInp.value.startsWith('http')) return readonlyInp.value;
        // 방법3: 링크 복사 버튼 근처 input
        const copyBtns = [...document.querySelectorAll('button')].filter(
            b => b.innerText.includes('링크 복사') || b.innerText.includes('복사')
        );
        for (const btn of copyBtns) {
            const parent = btn.closest('div');
            if (parent) {
                const inp = parent.querySelector('input');
                if (inp && inp.value && inp.value.startsWith('http') && !inp.placeholder) return inp.value;
            }
        }
        return null;
    }""")

    if affiliate_url:
        log(f"  ✅ 제휴 링크: {affiliate_url}")
        return affiliate_url

    # 결과 못 찾으면 현재 페이지 상태 디버깅
    page_text = page.evaluate("() => document.body.innerText.substring(0, 400)")
    log(f"  ⚠️ 제휴 링크 추출 실패. 페이지 상태:\n{page_text}")
    return None


# ── 메인 함수 ─────────────────────────────────────────────────────────────────

def get_affiliate_links(keyword: str, top_n: int = 3, on_log=None) -> list[dict]:
    """키워드로 마이리얼트립 상품 검색 → 제휴 링크 반환.

    Returns:
        [{"title": str, "original_url": str, "affiliate_url": str | None}, ...]
    """
    from browser import connect_cdp

    def log(msg):
        if on_log:
            on_log(msg)
        print(msg, flush=True)

    results = []
    pw, browser = connect_cdp(on_log=on_log)

    try:
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()

        # 1. 상품 검색
        log(f"[MRT] '{keyword}' 검색 중...")
        products = _search_products(page, keyword, top_n=top_n)
        log(f"[MRT] 상품 {len(products)}개 발견")
        for p in products:
            log(f"  - {p['title']} → {p['url']}")

        if not products:
            log("[MRT] ⚠️ 검색 결과 없음")
            page.close()
            return []

        # 2. 각 상품 제휴 링크 생성
        for product in products:
            log(f"\n[MRT] 링크 생성: {product['title'][:40]}")
            affiliate_url = _generate_link(page, product["url"], on_log=on_log)
            results.append({
                "title": product["title"],
                "original_url": product["url"],
                "affiliate_url": affiliate_url,
            })
            time.sleep(1)

        page.close()

    except Exception as e:
        log(f"[MRT] 오류: {e}")
    finally:
        pw.stop()

    log(f"\n[MRT] 완료: {len([r for r in results if r['affiliate_url']])}개 링크 생성")
    return results


# ── 직접 실행 테스트 ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else "도쿄 디즈니랜드"
    print(f"\n키워드: {keyword}")
    links = get_affiliate_links(keyword, top_n=3)
    print("\n=== 결과 ===")
    for i, item in enumerate(links, 1):
        print(f"\n{i}. {item['title']}")
        print(f"   원본:   {item['original_url']}")
        print(f"   제휴:   {item['affiliate_url'] or '생성 실패'}")
