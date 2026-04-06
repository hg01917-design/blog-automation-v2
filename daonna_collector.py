"""
다온나상점 — 도매매 공급사 상품 수집 + 미등록 상품 비교
- 도매매에서 공급사(유유팩토리) 상품 전체 수집
- 다온나상점 도매꾹 셀러센터 등록 상품과 비교
- 미등록 상품 목록 → daonna_compare.json 저장
- CDP 포트 9223 사용
"""
import asyncio
import json
import re
import sys
from pathlib import Path

CDP_URL = "http://localhost:9223"
SUPPLIER_NICK = "유유팩토리"
DOMEME_SEARCH_URL = "https://www.domeme.com"
SELLER_LIST_URL = "https://domeggook.com/main/mySell/my_sellList.php"
OUTPUT_FILE = Path(__file__).parent / "daonna_compare.json"
PROGRESS_FILE = Path("/tmp/daonna_upload_progress.json")


def load_progress() -> set:
    if PROGRESS_FILE.exists():
        d = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        return set(d.get("done", [])) | set(d.get("failed", []))
    return set()


async def collect_supplier_products(page) -> list:
    """도매매에서 공급사 닉네임으로 검색 후 전체 상품 수집"""
    print(f"[수집] 도매매 접속 중...", flush=True)
    await page.goto(DOMEME_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)

    print(f"[수집] 현재 URL: {page.url}", flush=True)

    # 공급사 닉네임 검색 필드 찾기
    # 도매매 검색창에 공급사 닉네임 입력
    searched = False
    # 공급사 검색 URL 직접 시도
    search_urls = [
        f"https://www.domeme.com/search?supplier={SUPPLIER_NICK}",
        f"https://www.domeme.com/product/list?sellerNick={SUPPLIER_NICK}",
        f"https://domeggook.com/ssl/domeme/list.php?sellerNick={SUPPLIER_NICK}",
    ]

    for url in search_urls:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)
            # 상품 목록이 있는지 확인
            count = await page.evaluate("() => document.querySelectorAll('[class*=\"item\"], [class*=\"product\"], li.goods').length")
            if count > 0:
                print(f"[수집] 상품 목록 발견: {url} ({count}개)", flush=True)
                searched = True
                break
        except Exception:
            pass

    if not searched:
        # 검색창에서 직접 공급사 검색
        print(f"[수집] 직접 검색 시도...", flush=True)
        await page.goto(DOMEME_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # 공급사 닉네임 검색 셀렉터 시도
        nick_selectors = [
            'input[placeholder*="공급사"]',
            'input[name*="seller"]',
            'input[name*="supplier"]',
            'input[id*="seller"]',
            'input[id*="supplier"]',
            'input[placeholder*="닉네임"]',
        ]
        for sel in nick_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.fill(SUPPLIER_NICK)
                    await el.press("Enter")
                    await asyncio.sleep(3)
                    searched = True
                    print(f"[수집] 공급사 검색 완료: {sel}", flush=True)
                    break
            except Exception:
                pass

    print(f"[수집] 현재 URL: {page.url}", flush=True)

    # 전체 상품 수집 (페이지네이션)
    all_products = []
    page_num = 1

    while True:
        print(f"[수집] 페이지 {page_num} 스크랩 중...", flush=True)
        await asyncio.sleep(1)

        products = await page.evaluate("""
            () => {
                const results = [];
                // 다양한 상품 카드 셀렉터 시도
                const cards = [
                    ...document.querySelectorAll('.item-list li, .goods-list li, .product-list li'),
                    ...document.querySelectorAll('[class*="item-card"], [class*="goods-item"], [class*="product-item"]'),
                    ...document.querySelectorAll('ul.goods > li, ul.item > li'),
                ];
                const seen = new Set();
                for (const card of cards) {
                    // 상품 번호 추출
                    const link = card.querySelector('a[href*="itemView"], a[href*="no="], a[href*="item_no="]');
                    if (!link) continue;
                    const m = link.href.match(/[?&]no=(\d+)/) || link.href.match(/item[_-]?no=(\d+)/);
                    if (!m) continue;
                    const id = m[1];
                    if (seen.has(id)) continue;
                    seen.add(id);

                    // 상품명
                    const nameEl = card.querySelector('.goods-name, .item-name, .product-name, [class*="title"], strong, p.name');
                    const name = nameEl ? nameEl.innerText.trim() : '';

                    // 가격
                    const priceEl = card.querySelector('.price, .goods-price, [class*="price"]');
                    const price = priceEl ? priceEl.innerText.trim() : '';

                    if (id && name) results.push({id, name, price});
                }
                return results;
            }
        """)

        if products:
            all_products.extend(products)
            print(f"  → {len(products)}개 추출 (누적: {len(all_products)}개)", flush=True)
        else:
            print(f"  → 상품 없음, 수집 종료", flush=True)
            break

        # 다음 페이지 버튼
        next_btn = page.locator('a.next, button.next, [class*="next"]:not([disabled]), a[title="다음"], a[aria-label="다음"]').first
        try:
            if await next_btn.is_visible(timeout=2000):
                await next_btn.click()
                await asyncio.sleep(2)
                page_num += 1
            else:
                break
        except Exception:
            break

        if page_num > 50:  # 안전 제한
            break

    print(f"[수집] 공급사 상품 총 {len(all_products)}개 수집 완료", flush=True)
    return all_products


async def collect_registered_products(page) -> set:
    """다온나상점 셀러센터에서 이미 등록된 상품 itemCode 수집"""
    print(f"[비교] 셀러센터 등록 상품 수집 중...", flush=True)
    registered_codes = set()

    # 셀러센터 상품 목록 — 여러 페이지 순회
    page_num = 1
    while True:
        url = f"{SELLER_LIST_URL}?page={page_num}&pageCount=100"
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        codes = await page.evaluate("""
            () => {
                const codes = [];
                // 상품 코드 (itemCode 열)
                document.querySelectorAll('td.itemCode, td[data-label="상품코드"], input[name="itemCode[]"]').forEach(el => {
                    const val = (el.innerText || el.value || '').trim();
                    if (val) codes.push(val);
                });
                // 링크에서 no= 파라미터 추출도 시도
                document.querySelectorAll('a[href*="my_sellModify"], a[href*="itemNo="]').forEach(a => {
                    const m = a.href.match(/itemNo=(\d+)/);
                    if (m) codes.push(m[1]);
                });
                return [...new Set(codes)];
            }
        """)

        if codes:
            registered_codes.update(codes)
            print(f"  페이지 {page_num}: {len(codes)}개 (누적: {len(registered_codes)}개)", flush=True)
        else:
            break

        # 다음 페이지 있는지 확인
        has_next = await page.evaluate("""
            () => {
                const next = document.querySelector('a.next, a[title="다음페이지"]');
                return !!next;
            }
        """)
        if not has_next:
            break
        page_num += 1
        if page_num > 50:
            break

    print(f"[비교] 셀러센터 등록 상품 총 {len(registered_codes)}개", flush=True)
    return registered_codes


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]

        # 기존 탭 재사용
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # 1. 공급사 상품 수집
        supplier_products = await collect_supplier_products(page)

        if not supplier_products:
            print("❌ 공급사 상품 수집 실패 — 도매매 페이지 구조 확인 필요", flush=True)
            # 현재 페이지 URL과 구조를 출력해서 디버깅
            print(f"현재 URL: {page.url}", flush=True)
            html_snippet = await page.evaluate("() => document.body.innerHTML.substring(0, 2000)")
            print(f"HTML 앞부분:\n{html_snippet}", flush=True)
            return

        # 2. 셀러센터 등록 상품 수집
        registered = await collect_registered_products(page)

        # 3. 진행 완료/실패 항목도 제외
        already_done = load_progress()
        registered.update(already_done)

        # 4. 비교 — 미등록 상품 추출
        missing = [p for p in supplier_products if p["id"] not in registered]
        print(f"\n[결과] 공급사: {len(supplier_products)}개 | 등록: {len(registered)}개 | 미등록: {len(missing)}개", flush=True)

        # 5. 저장
        output = {"missing_in_daonna": missing, "total": len(missing)}
        OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        # /tmp에도 복사 (daonna_upload_bot이 읽는 위치)
        Path("/tmp/daonna_compare.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\n✅ 저장 완료: {OUTPUT_FILE}", flush=True)
        print(f"✅ 저장 완료: /tmp/daonna_compare.json", flush=True)
        if missing:
            print(f"\n미등록 샘플 5개:", flush=True)
            for p in missing[:5]:
                print(f"  {p['id']} | {p['name'][:40]} | {p['price']}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
