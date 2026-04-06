"""
다온나상점 — 상품명으로 도매꾹 검색 후 ID 수집 → daonna_compare.json 생성
사장님이 주신 리스트에서 도매꾹 상품번호를 찾아 등록 대기 목록 생성
CDP 포트 9223 사용
"""
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import quote

CDP_URL = "http://localhost:9223"
SUPPLIER_NICK = "yoowin7070"
OUTPUT_FILE = Path(__file__).parent / "daonna_compare.json"

# 사장님이 준 상품 리스트 (가격 있는 것만, 도매꾹 판매가 기준)
PRODUCTS_TO_REGISTER = [
    # 1~4
    {"name": "초강접 택배 박스 취급주의 코팅 스티커 낱장 6X6cm 1000매",    "price": "18000"},
    {"name": "국산 노루지 35g 소 180X270mm 500매",                          "price": "7000"},
    {"name": "국산 노루지 35g 소 135X135mm 1000매",                         "price": "7000"},
    {"name": "초강접 택배 박스 취급주의 코팅 스티커 낱장 7X9cm 1000매",    "price": "20500"},
    # 30~40 (35,36 가격 미정 스킵)
    {"name": "털 키링 무용수 핑크 민트",                                    "price": "2200"},
    {"name": "O링 9mm 100P",                                                "price": "3600"},
    {"name": "D고리 버클 은색 50P",                                         "price": "6100"},
    {"name": "구슬체인 100p 랜덤색상",                                      "price": "3100"},
    {"name": "A7 표정 미니 줄노트 2종 핑크 옐로우",                         "price": "800"},
    {"name": "투두 리스트 체크보드",                                        "price": "2950"},
    {"name": "파스텔 복 팔찌",                                              "price": "3900"},
    {"name": "복숭아 꽃 팔찌",                                              "price": "4900"},
    {"name": "커피머신 꾸미기 미니 자석",                                   "price": "10500"},
    # 41~53 (43~49 작업중 스킵)
    {"name": "미니 카페 냉장고 자석 8p 세트",                              "price": "7500"},
    {"name": "미니 카페 냉장고 자석 12p 세트",                             "price": "7000"},
    {"name": "D고리 버클 금색 50P",                                         "price": "6100"},
    {"name": "30mm 실버 열쇠 고리 이중오링 원형 키링 부자재 1묶음 50P",    "price": "3800"},
    {"name": "실버 8자형 버클 열쇠 고리 키링 부자재 1묶음 50P",            "price": "4200"},
    {"name": "실버 오픈형 오링 2컬러 실버 스틸 1묶음 100P",                "price": "2800"},
]


async def search_product_id(page, product_name: str) -> str | None:
    """도매꾹에서 상품명 + 공급사 검색 → 상품번호 반환"""
    query = quote(product_name)
    # 공급사 닉네임으로 필터링한 검색
    url = f"https://domeggook.com/main/search/search.php?searchWord={query}&sellerNick={SUPPLIER_NICK}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
    except Exception as e:
        print(f"  [검색] 페이지 로드 실패: {e}", flush=True)
        return None

    # 검색 결과에서 첫 번째 상품 ID 추출
    result = await page.evaluate("""
        () => {
            // 상품 링크에서 no= 파라미터 추출
            const links = [...document.querySelectorAll('a[href*="itemView"], a[href*="no="]')];
            for (const a of links) {
                const m = a.href.match(/[?&]no=(\d+)/);
                if (m && m[1].length > 5) return m[1];
            }
            // 대체: data-item-no 속성
            const el = document.querySelector('[data-item-no], [data-no]');
            if (el) return el.dataset.itemNo || el.dataset.no;
            return null;
        }
    """)

    if result:
        print(f"  [검색] '{product_name[:30]}' → ID: {result}", flush=True)
        return result

    # 공급사 필터 없이 재검색
    url2 = f"https://domeggook.com/main/search/search.php?searchWord={query}"
    try:
        await page.goto(url2, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
    except Exception:
        return None

    result2 = await page.evaluate("""
        () => {
            const links = [...document.querySelectorAll('a[href*="itemView"], a[href*="no="]')];
            for (const a of links) {
                const m = a.href.match(/[?&]no=(\d+)/);
                if (m && m[1].length > 5) return m[1];
            }
            return null;
        }
    """)

    if result2:
        print(f"  [검색] '{product_name[:30]}' → ID: {result2} (닉네임 미적용)", flush=True)
    else:
        print(f"  [검색] '{product_name[:30]}' → 찾지 못함 ❌", flush=True)

    return result2


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        print(f"[시작] 상품 {len(PRODUCTS_TO_REGISTER)}개 도매꾹 검색", flush=True)

        found = []
        not_found = []

        for product in PRODUCTS_TO_REGISTER:
            name = product["name"]
            price = product["price"]
            print(f"\n검색: {name}", flush=True)
            item_id = await search_product_id(page, name)
            if item_id:
                found.append({"id": item_id, "name": name, "price": price})
            else:
                not_found.append(name)

        print(f"\n[결과] 찾음: {len(found)}개 / 못찾음: {len(not_found)}개", flush=True)
        if not_found:
            print(f"미발견 상품: {not_found}", flush=True)

        # daonna_compare.json 저장
        output = {"missing_in_daonna": found, "total": len(found)}
        OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        Path("/tmp/daonna_compare.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\n✅ {OUTPUT_FILE} 저장 완료", flush=True)
        print(f"✅ /tmp/daonna_compare.json 저장 완료", flush=True)
        print("\n등록할 상품 목록:", flush=True)
        for p in found:
            print(f"  [{p['id']}] {p['name']} ({p['price']}원)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
