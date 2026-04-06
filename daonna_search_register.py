"""
다온나상점 — domemedb.domeggook.com에서 유유팩토리 전체 상품 수집
→ 사장님 리스트와 매칭 → daonna_compare.json 생성
CDP 포트 9223 사용
"""
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import quote

CDP_URL = "http://localhost:9223"
SUPPLIER_NICK = "유유팩토리"
BASE_URL = "https://domemedb.domeggook.com/index/item/supplyList.php"
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


def keyword_overlap(a: str, b: str) -> float:
    """두 상품명의 키워드 겹침 비율 (0~1) — 부분 문자열 포함"""
    def tokens(s):
        s = s.lower()
        return re.findall(r'[가-힣]{2,}|[a-z0-9]+(?:[xX×][0-9]+)?', s)

    ta = tokens(a)
    tb = tokens(b)
    if not ta or not tb:
        return 0.0

    # 색상/방향 등 공통 노이즈 제거
    STOPWORDS = {'랜덤', '색상', '컬러', '블랙', '화이트', '실버', '골드', '금색', '은색', '부자재', '세트'}

    def is_match(tok_a, tok_b):
        # 정확히 같거나 한쪽이 다른쪽의 부분 문자열
        return tok_a == tok_b or tok_a in tok_b or tok_b in tok_a

    matched_a = sum(
        1 for t in ta
        if t not in STOPWORDS and any(is_match(t, u) for u in tb if u not in STOPWORDS)
    )
    # 노이즈 제거한 ta 기준
    effective_ta = [t for t in ta if t not in STOPWORDS]
    if not effective_ta:
        return 0.0
    return matched_a / len(effective_ta)


async def collect_all_products(page) -> list:
    """domemedb에서 유유팩토리 전체 상품 수집 (pagenum=0,1,2... URL 방식)"""
    all_products = []
    seen = set()

    for pagenum in range(100):  # 최대 100페이지 (50개씩 = 최대 5000개)
        url = (
            f"{BASE_URL}?pagenum={pagenum}&mode=search&fromOversea=0"
            f"&pageLimit=50&sf=nick&sw={quote(SUPPLIER_NICK)}"
        )
        print(f"[수집] 페이지 {pagenum + 1} (pagenum={pagenum})...", flush=True)
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        products = await page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('div.sub_cont_text1').forEach(card => {
                    const text = card.innerText || '';
                    const numMatch = text.match(/\\d{7,9}/);
                    if (!numMatch) return;
                    const id = numMatch[0];
                    const nameMatch = text.match(/\\d{7,9}\\n([^\\n]+)/);
                    const name = nameMatch ? nameMatch[1].trim() : '';
                    if (id && name) results.push({ id, name });
                });
                return results;
            }
        """)

        if not products:
            print(f"  → 상품 없음, 수집 종료 (총 {len(all_products)}개)", flush=True)
            break

        new_count = 0
        for p in products:
            if p["id"] not in seen:
                seen.add(p["id"])
                all_products.append(p)
                new_count += 1

        print(f"  → {new_count}개 신규 (누적: {len(all_products)}개)", flush=True)

        if new_count == 0:
            print(f"  → 중복만 있음, 수집 종료", flush=True)
            break

    print(f"[수집] 총 {len(all_products)}개 수집 완료", flush=True)
    return all_products


def match_products(all_products: list) -> list:
    """수집된 전체 상품에서 사장님 리스트와 매칭"""
    # 이미 사용된 상품 ID 추적 (같은 ID가 여러 user_product에 매칭되지 않도록)
    used_ids = set()
    result = []

    for user_prod in PRODUCTS_TO_REGISTER:
        user_name = user_prod["name"]
        best_score = 0.0
        best_match = None

        for scraped in all_products:
            if scraped["id"] in used_ids:
                continue
            score = keyword_overlap(user_name, scraped["name"])
            if score > best_score:
                best_score = score
                best_match = scraped

        THRESHOLD = 0.4
        if best_match and best_score >= THRESHOLD:
            used_ids.add(best_match["id"])
            result.append({
                "id": best_match["id"],
                "name": best_match["name"],
                "price": user_prod["price"],
                "_user_name": user_name,
                "_score": round(best_score, 2),
            })
            print(f"  ✅ [{best_match['id']}] {best_match['name'][:40]}")
            print(f"       ← {user_name[:40]} (score={best_score:.2f})")
        else:
            print(f"  ❌ 미매칭: {user_name[:40]} (best_score={best_score:.2f})")

    return result


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        print(f"[시작] 유유팩토리 상품 전체 수집", flush=True)

        # 1. 전체 상품 수집
        all_products = await collect_all_products(page)

        if not all_products:
            print("❌ 상품 수집 실패 — 브라우저에서 domemedb.domeggook.com 접속 상태 확인 필요", flush=True)
            return

        # 2. 사장님 리스트와 매칭
        print(f"\n[매칭] 총 {len(PRODUCTS_TO_REGISTER)}개 상품 매칭 시작...", flush=True)
        matched = match_products(all_products)

        print(f"\n[결과] 매칭: {len(matched)}/{len(PRODUCTS_TO_REGISTER)}개", flush=True)

        # 3. 저장
        output = {"missing_in_daonna": matched, "total": len(matched)}
        OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        Path("/tmp/daonna_compare.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\n✅ {OUTPUT_FILE} 저장 완료", flush=True)
        print(f"✅ /tmp/daonna_compare.json 저장 완료", flush=True)
        print("\n등록할 상품 목록:", flush=True)
        for p in matched:
            print(f"  [{p['id']}] {p['name'][:40]} ({p['price']}원)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
