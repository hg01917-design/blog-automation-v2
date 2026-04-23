"""
쿠팡 베스트셀러 스크래핑 - 새 탭 생성 방식
각 카테고리마다 새 탭을 생성해서 봇 탐지 우회
"""
import asyncio
import json
import urllib.request
import websockets
import time

_CMD_ID = 0

def next_id():
    global _CMD_ID
    _CMD_ID += 1
    return _CMD_ID


async def send_cmd(ws, method, params=None):
    cid = next_id()
    msg = {"id": cid, "method": method, "params": params or {}}
    await ws.send(json.dumps(msg))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        data = json.loads(raw)
        if data.get("id") == cid:
            return data


async def nav_click(ws, url, wait=10):
    nav_js = f"""
(function() {{
    var a = document.createElement('a');
    a.href = '{url}';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}})()
"""
    await send_cmd(ws, "Runtime.evaluate", {"expression": nav_js, "returnByValue": True})
    await asyncio.sleep(wait)
    check = await send_cmd(ws, "Runtime.evaluate", {
        "expression": "location.href + ' | items:' + document.querySelectorAll('li[class*=\"ProductUnit_productUnit\"]').length",
        "returnByValue": True
    })
    return check.get("result", {}).get("result", {}).get("value", "")


async def extract_products(ws):
    extract_js = """
(function() {
    var items = document.querySelectorAll('li[class*="ProductUnit_productUnit"]');
    var results = [];
    Array.from(items).slice(0, 60).forEach(function(el) {
        var name = '';
        var imgEl = el.querySelector('img[alt]');
        if (imgEl) name = imgEl.alt.trim();

        var price = '';
        var pEl = el.querySelector('[class*="Price"], [class*="price"]');
        if (pEl) price = pEl.innerText.trim().split('\\n')[0];

        var reviews = '0';
        var allText = el.innerText;
        var revMatch = allText.match(/\\(([0-9,]+)\\)/);
        if (revMatch) reviews = revMatch[1].replace(/,/g, '');

        var href = '';
        var linkEl = el.querySelector('a[href*="/vp/products/"]');
        if (linkEl) {
            var rawHref = linkEl.getAttribute('href');
            href = rawHref.startsWith('http') ? rawHref : 'https://www.coupang.com' + rawHref;
            href = href.split('?')[0];
        }

        if (name && href) results.push({name: name, price: price, reviews: reviews, url: href});
    });
    return {url: location.href, count: items.length, products: results};
})()
"""
    ext_r = await send_cmd(ws, "Runtime.evaluate", {"expression": extract_js, "returnByValue": True})
    return ext_r.get("result", {}).get("result", {}).get("value", {})


async def create_tab(browser_ws_url):
    async with websockets.connect(browser_ws_url, max_size=5 * 1024 * 1024) as bws:
        cid = next_id()
        msg = {"id": cid, "method": "Target.createTarget", "params": {"url": "about:blank"}}
        await bws.send(json.dumps(msg))
        while True:
            raw = await asyncio.wait_for(bws.recv(), timeout=30)
            data = json.loads(raw)
            if data.get("id") == cid:
                return data.get("result", {}).get("targetId")


async def close_tab(browser_ws_url, target_id):
    try:
        async with websockets.connect(browser_ws_url, max_size=5 * 1024 * 1024) as bws:
            cid = next_id()
            msg = {"id": cid, "method": "Target.closeTarget", "params": {"targetId": target_id}}
            await bws.send(json.dumps(msg))
            await asyncio.wait_for(bws.recv(), timeout=10)
    except Exception:
        pass


async def scrape_category(browser_ws_url, target_url, cat_name):
    """새 탭을 생성해서 카테고리 스크래핑"""
    target_id = await create_tab(browser_ws_url)
    if not target_id:
        print(f"  [{cat_name}] 탭 생성 실패")
        return []

    tab_ws_url = f"ws://localhost:9222/devtools/page/{target_id}"
    print(f"  [{cat_name}] 새 탭: {target_id[:20]}...")

    try:
        async with websockets.connect(tab_ws_url, max_size=20 * 1024 * 1024) as ws:
            await send_cmd(ws, "Page.enable")
            await send_cmd(ws, "Runtime.enable")

            result = await nav_click(ws, target_url, wait=12)
            print(f"  → {result[:100]}")

            val = await extract_products(ws)
            products = val.get("products", [])
            print(f"  추출: {val.get('count')} items → {len(products)} 상품")
            if products:
                print(f"  샘플: {products[0]}")
            return products
    finally:
        await close_tab(browser_ws_url, target_id)


async def main():
    ver = json.loads(urllib.request.urlopen("http://localhost:9222/json/version", timeout=5).read())
    browser_ws_url = ver["webSocketDebuggerUrl"]

    # 올바른 카테고리 ID 사용 (eventCategory=breadcrumb 없이 먼저 시도)
    categories_to_try = [
        ("주방가전", [
            "https://www.coupang.com/np/categories/445736?listSize=60&sorter=saleCountDESC&eventCategory=breadcrumb",
            "https://www.coupang.com/np/categories/445736?eventCategory=breadcrumb",
        ]),
        ("식품", [
            "https://www.coupang.com/np/categories/393760?listSize=60&sorter=saleCountDESC&eventCategory=breadcrumb",
            "https://www.coupang.com/np/categories/393760?eventCategory=breadcrumb",
        ]),
        ("건강식품", [
            "https://www.coupang.com/np/categories/503714?listSize=60&sorter=saleCountDESC&eventCategory=breadcrumb",
            "https://www.coupang.com/np/categories/503714?eventCategory=breadcrumb",
        ]),
        ("뷰티/헤어가전", [
            "https://www.coupang.com/np/categories/333478?listSize=60&sorter=saleCountDESC&eventCategory=breadcrumb",
        ]),
    ]

    all_results = {}

    for cat_name, urls in categories_to_try:
        print(f"\n[{cat_name}]")
        products = []
        for url in urls:
            products = await scrape_category(browser_ws_url, url, cat_name)
            if products:
                break
            await asyncio.sleep(5)

        all_results[cat_name] = products

    # 기존 생활가전 결과 로드
    try:
        with open('/Users/hana/Downloads/blog-automation-v2/coupang_bestseller_raw.json', 'r', encoding='utf-8') as f:
            existing = json.load(f)
        for k, v in existing.items():
            if v and k not in all_results:
                all_results[k] = v
    except Exception:
        pass

    # 결과 저장
    with open('/Users/hana/Downloads/blog-automation-v2/coupang_bestseller_raw.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print("\n\n=== 리뷰 1000개 이상 필터링 결과 ===\n")
    all_filtered = []

    for cat, products in all_results.items():
        filtered = []
        for p in products:
            rev_str = str(p.get('reviews', '0')).replace(',', '').strip()
            try:
                rv = int(rev_str) if rev_str.isdigit() else 0
            except Exception:
                rv = 0
            if rv >= 1000:
                filtered.append({**p, 'category': cat, 'review_count': rv})
        filtered.sort(key=lambda x: x['review_count'], reverse=True)
        all_filtered.extend(filtered)

        print(f"\n[{cat}] 리뷰 1000+ 상품: {len(filtered)}개")
        for p in filtered[:10]:
            print(f"  {p['name'][:45]} | {p['price']} | {p['review_count']}개 | {p['url'][:70]}")

    with open('/Users/hana/Downloads/blog-automation-v2/coupang_bestseller_filtered.json', 'w', encoding='utf-8') as f:
        json.dump(all_filtered, f, ensure_ascii=False, indent=2)

    print(f"\n\n총 리뷰 1000+ 상품: {len(all_filtered)}개")
    print("저장: coupang_bestseller_filtered.json")


if __name__ == "__main__":
    asyncio.run(main())
