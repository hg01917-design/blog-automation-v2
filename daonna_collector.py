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
SUPPLIER_ALL_FILE = Path(__file__).parent / "daonna_supplier_all.json"
SC_ITEM_LIST_URL = "https://domeggook.com/sc/item/lstAll"
OUTPUT_FILE = Path(__file__).parent / "daonna_compare.json"
PROGRESS_FILE = Path("/tmp/daonna_upload_progress.json")


def load_progress() -> set:
    if PROGRESS_FILE.exists():
        d = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        return set(d.get("done", [])) | set(d.get("failed", []))
    return set()


async def collect_supplier_products(page) -> list:
    """daonna_supplier_all.json에서 공급사 상품 목록 로드"""
    if not SUPPLIER_ALL_FILE.exists():
        print(f"❌ {SUPPLIER_ALL_FILE} 없음", flush=True)
        return []
    data = json.loads(SUPPLIER_ALL_FILE.read_text(encoding="utf-8"))
    products = data.get("products", data) if isinstance(data, dict) else data
    print(f"[수집] {SUPPLIER_ALL_FILE.name}에서 {len(products)}개 로드", flush=True)
    return products


async def collect_registered_products(page) -> set:
    """공급사센터 /sc/item/lstAll 에서 이미 등록된 상품 번호 수집"""
    print(f"[비교] 공급사센터 등록 상품 수집 중...", flush=True)
    registered_codes = set()

    page_num = 1
    while True:
        url = f"{SC_ITEM_LIST_URL}?page={page_num}&rows=100"
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        codes = await page.evaluate(r"""
            () => {
                const codes = [];
                // 수정 링크에서 상품번호 추출
                document.querySelectorAll('a[href*="/sc/item/reg"], a[href*="itemNo="], a[href*="no="]').forEach(a => {
                    const m = a.href.match(/[?&](?:itemNo|no)=(\d+)/);
                    if (m) codes.push(m[1]);
                });
                // 테이블 내 상품번호 셀
                document.querySelectorAll('td[data-label="상품번호"], td.item-no').forEach(el => {
                    const v = el.innerText.trim();
                    if (v) codes.push(v);
                });
                return [...new Set(codes)];
            }
        """)

        if codes:
            registered_codes.update(codes)
            print(f"  페이지 {page_num}: {len(codes)}개 (누적: {len(registered_codes)}개)", flush=True)
        else:
            print(f"  페이지 {page_num}: 없음, 종료", flush=True)
            break

        has_next = await page.evaluate("""
            () => !!document.querySelector('a[class*="next"], a[title*="다음"], .pagination .next')
        """)
        if not has_next:
            break
        page_num += 1
        if page_num > 50:
            break

    print(f"[비교] 공급사센터 등록 상품 총 {len(registered_codes)}개", flush=True)
    return registered_codes


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]

        # domeggook 탭 우선 사용, 없으면 첫 번째 탭
        pages = ctx.pages
        page = next((p for p in pages if "domeggook" in p.url), None)
        if page is None:
            page = pages[0] if pages else await ctx.new_page()

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
