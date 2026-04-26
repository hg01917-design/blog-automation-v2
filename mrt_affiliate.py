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
        if on_log:
            on_log(msg)
        else:
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
    """키워드로 상품 검색 → 상위 n개 상품 정보(제목/URL/가격/평점/리뷰수/지역) 반환."""
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

        // 상품 카드 컨테이너 탐색 (MRT 검색 결과 구조)
        const cards = document.querySelectorAll(
            'li[class*="offer"], li[class*="product"], div[class*="offer-card"], div[class*="product-card"], article'
        );

        const extractFromCard = (card) => {
            const link = card.querySelector('a[href]');
            if (!link) return null;
            const href = link.href || '';
            if (!/(experiences|offers|products)/.test(href)) return null;
            if (!/\\/\\d{4,}/.test(href)) return null;
            if (seen.has(href)) return null;

            // 제목
            const titleEl = card.querySelector('[class*="title"], [class*="name"], h2, h3');
            const title = (titleEl?.innerText || link.innerText || '').trim().replace(/\\s+/g, ' ').substring(0, 80);
            if (title.length < 5) return null;

            // 가격
            let price = '';
            const priceEl = card.querySelector('[class*="price"], [class*="amount"]');
            if (priceEl) price = priceEl.innerText.trim().replace(/\\s+/g, ' ').substring(0, 30);

            // 평점
            let rating = '';
            const ratingEl = card.querySelector('[class*="rating"], [class*="score"], [class*="star"]');
            if (ratingEl) {
                const txt = ratingEl.innerText.trim();
                const m = txt.match(/[0-9]+\\.?[0-9]*/);
                if (m) rating = m[0];
            }

            // 리뷰수
            let reviewCount = '';
            const reviewEl = card.querySelector('[class*="review"], [class*="count"]');
            if (reviewEl) {
                const txt = reviewEl.innerText.trim();
                const m = txt.match(/([0-9,]+)\\s*(?:개|건|명|reviews?)?/);
                if (m) reviewCount = m[1].replace(',', '');
            }

            // 지역/카테고리 태그
            let region = '';
            const regionEl = card.querySelector('[class*="tag"], [class*="location"], [class*="area"], [class*="category"]');
            if (regionEl) region = regionEl.innerText.trim().substring(0, 20);

            return { title, url: href, price, rating, reviewCount, region };
        };

        // 카드가 없으면 링크 기반 폴백
        if (cards.length === 0) {
            for (const el of document.querySelectorAll('a[href]')) {
                const href = el.href || '';
                if (!/(experiences|offers|products)/.test(href)) continue;
                if (!/\\/\\d{4,}/.test(href)) continue;
                if (seen.has(href)) continue;
                seen.add(href);
                const title = el.innerText.trim().replace(/\\s+/g, ' ').substring(0, 80);
                if (title.length < 5) continue;
                items.push({ title, url: href, price: '', rating: '', reviewCount: '', region: '' });
                if (items.length >= topN) break;
            }
            return items;
        }

        for (const card of cards) {
            const item = extractFromCard(card);
            if (!item) continue;
            seen.add(item.url);
            items.push(item);
            if (items.length >= topN) break;
        }
        return items;
    }""", top_n)

    return products


def format_products_as_context(products: list[dict], keyword: str) -> str:
    """검색 결과를 Claude 컨텍스트 문자열로 변환."""
    if not products:
        return ""
    lines = [f"[마이리얼트립 검색 결과 — '{keyword}']"]
    for p in products:
        parts = [f"- 상품명: {p['title']}"]
        if p.get("region"):
            parts.append(f"  지역: {p['region']}")
        if p.get("price"):
            parts.append(f"  가격: {p['price']}")
        if p.get("rating"):
            rev = f" ({p['reviewCount']}개 리뷰)" if p.get("reviewCount") else ""
            parts.append(f"  평점: {p['rating']}{rev}")
        parts.append(f"  URL: {p['url']}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


# ── 메인 함수 ─────────────────────────────────────────────────────────────────

def get_affiliate_links(keyword: str, top_n: int = 3, on_log=None) -> list[dict]:
    """키워드로 MRT 상품 검색 → API로 제휴 링크 생성.

    Returns:
        [{"title": str, "original_url": str, "affiliate_url": str | None}, ...]
    """
    from browser import connect_cdp

    def log(msg):
        if on_log:
            on_log(msg)
        else:
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
            "price": product.get("price", ""),
            "rating": product.get("rating", ""),
            "review_count": product.get("reviewCount", ""),
            "region": product.get("region", ""),
        })

    success = len([r for r in results if r['affiliate_url']])
    log(f"\n[MRT] 완료: {success}/{len(results)}개 링크 생성")
    return results


def get_affiliate_links_with_context(keyword: str, top_n: int = 3, on_log=None) -> tuple[list[dict], str]:
    """get_affiliate_links() + 상품 정보 컨텍스트 문자열도 함께 반환.

    Returns:
        (links, product_context_str)
        product_context_str: Claude extra_context에 주입용 상품 정보 요약
    """
    links = get_affiliate_links(keyword, top_n=top_n, on_log=on_log)
    if not links:
        return [], ""
    context = format_products_as_context(links, keyword)
    return links, context


def build_agent_mrt_context(keyword: str, on_log=None) -> str:
    """개별 포스팅 에이전트용 — MRT 상품 검색 후 Claude 프롬프트 주입 컨텍스트 반환.

    파이프라인과 동일한 형식: 상품 정보 + 링크 삽입 지시.
    실패 시 빈 문자열 반환 (발행 중단 없음).
    """
    def log(msg):
        if on_log:
            on_log(msg)

    try:
        search_kw = keyword.split()[0] if keyword.strip() else keyword
        log(f"[MRT] 검색어: '{search_kw}'")
        links = get_affiliate_links(search_kw, top_n=3, on_log=on_log)
        valid = [p for p in links if p.get("affiliate_url")]
        if not valid:
            log("[MRT] 관련 상품 없음 — 스킵")
            return ""

        ctx = "\n\n[마이리얼트립 상품 정보 — 글 작성 참고 자료]\n"
        ctx += "아래는 이 여행지에서 실제로 판매 중인 투어/체험 상품이다.\n"
        ctx += "상품명·가격·평점·리뷰수를 글 내용에 직접 반영해 구체성을 높여라.\n\n"
        for i, p in enumerate(valid, 1):
            ctx += f"{i}. {p['title'][:70]}"
            if p.get("region"):
                ctx += f" {p['region']}"
            ctx += f" {p.get('price', '')}\n"
            if p.get("rating"):
                rev = f" ({p.get('review_count','')}개 리뷰)" if p.get("review_count") else ""
                ctx += f"   평점: {p['rating']}{rev}\n"
            ctx += f"   예약링크: {p['affiliate_url']}\n"

        ctx += (
            "\n[마이리얼트립 제휴 링크 — 본문 2회 삽입 필수]\n"
            "글 최상단에 이 한 줄 삽입:\n"
            "「이 글에는 마이리얼트립 파트너스 프로그램을 통해 소정의 수수료를 받을 수 있는 제휴 링크가 포함되어 있습니다.」\n\n"
            "위 상품 중 글과 가장 관련된 것 1~2개 선택해서 아래 형식으로 2회 삽입:\n"
            "  1회차: 첫 번째 H2 소제목 시작 전 도입부 끝 — 후킹 문구 1줄 + 링크\n"
            "  2회차: Q&A 직후 마무리 문단 앞 — CTA + 링크\n"
            "링크 형식: <a href=\"예약링크\" target=\"_blank\" style=\"color:#1a73e8;font-weight:bold;\">상품명 예약하기</a>\n"
        )
        log(f"[MRT] {len(valid)}개 상품 컨텍스트 빌드 완료")
        return ctx
    except Exception as e:
        log(f"[MRT] 컨텍스트 빌드 실패 (무시): {e}")
        return ""


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
