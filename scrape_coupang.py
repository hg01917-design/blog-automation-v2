from playwright.sync_api import sync_playwright
import time, json, re

categories = [
    ("생활가전", "https://www.coupang.com/np/categories/494460?listSize=60&sorter=saleCountDESC"),
    ("주방가전", "https://www.coupang.com/np/categories/494461?listSize=60&sorter=saleCountDESC"),
    ("식품",    "https://www.coupang.com/np/categories/194085?listSize=60&sorter=saleCountDESC"),
    ("건강식품", "https://www.coupang.com/np/categories/194158?listSize=60&sorter=saleCountDESC"),
    ("뷰티",   "https://www.coupang.com/np/categories/194195?listSize=60&sorter=saleCountDESC"),
]

results = {}

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://localhost:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    for cat_name, url in categories:
        print(f"\n[{cat_name}] 접속 중...", flush=True)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)

            # 현재 페이지의 HTML 구조 확인
            html_snippet = page.evaluate("""() => {
                const body = document.body.innerHTML;
                return body.substring(0, 3000);
            }""")
            print(f"  HTML 앞부분: {html_snippet[:500]}", flush=True)

            products = page.evaluate("""() => {
                // 다양한 셀렉터 시도
                let items = document.querySelectorAll('li.baby-product');
                console.log('baby-product:', items.length);
                if (!items || items.length === 0) {
                    items = document.querySelectorAll('li[class*="products-"]');
                    console.log('products-:', items.length);
                }
                if (!items || items.length === 0) {
                    items = document.querySelectorAll('li[class*="product"]');
                    console.log('product:', items.length);
                }
                if (!items || items.length === 0) {
                    items = document.querySelectorAll('article');
                    console.log('article:', items.length);
                }
                if (!items || items.length === 0) {
                    items = document.querySelectorAll('[data-id]');
                    console.log('data-id:', items.length);
                }

                return Array.from(items).slice(0, 60).map(el => {
                    let name = '';
                    const nameEl = el.querySelector('.name') ||
                                   el.querySelector('[class*="name"]') ||
                                   el.querySelector('span[class*="Name"]') ||
                                   el.querySelector('div[class*="Name"]');
                    if (nameEl) name = nameEl.innerText.trim();

                    let price = '';
                    const priceEl = el.querySelector('.price-value') ||
                                    el.querySelector('[class*="price-value"]') ||
                                    el.querySelector('[class*="Price"]') ||
                                    el.querySelector('strong');
                    if (priceEl) price = priceEl.innerText.trim();

                    let reviews = '0';
                    const revEl = el.querySelector('.rating-total-count') ||
                                  el.querySelector('[class*="rating-total"]') ||
                                  el.querySelector('[class*="review"]') ||
                                  el.querySelector('[class*="Review"]');
                    if (revEl) reviews = revEl.innerText.replace(/[^0-9,]/g,'').replace(',','');

                    let href = '';
                    const linkEl = el.querySelector('a[href*="/vp/products/"]') ||
                                   el.querySelector('a[href*="coupang"]') ||
                                   el.querySelector('a');
                    if (linkEl) href = linkEl.href;

                    return { name, price, reviews, url: href, tag: el.tagName, cls: el.className.substring(0,50) };
                }).filter(p => p.name || p.url);
            }""")

            print(f"  추출 수: {len(products)}", flush=True)
            for p in products[:3]:
                print(f"  샘플: {p}", flush=True)
            results[cat_name] = products

        except Exception as e:
            print(f"  오류: {e}", flush=True)
            results[cat_name] = []

    page.close()

with open('/Users/hana/Downloads/blog-automation-v2/coupang_bestseller_raw.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n=== 저장 완료: coupang_bestseller_raw.json ===", flush=True)

# 필터링 결과
print("\n=== 리뷰 1000개 이상 필터링 ===\n", flush=True)
for cat, products in results.items():
    filtered = []
    for p in products:
        rev_str = str(p.get('reviews', '0')).replace(',', '').replace('(','').replace(')','').strip()
        try:
            rev_count = int(rev_str) if rev_str.isdigit() else 0
        except:
            rev_count = 0
        if rev_count >= 1000:
            filtered.append({**p, 'review_count': rev_count})
    filtered.sort(key=lambda x: x['review_count'], reverse=True)
    print(f"\n[{cat}] 리뷰 1000+ 상품: {len(filtered)}개")
    for p in filtered[:10]:
        print(f"  {p['name'][:45]} | {p['price']} | {p['review_count']}개 | {p['url'][:80]}")
