"""
쿠팡 베스트셀러 스크래핑 - WebSocket CDP
카테고리 리다이렉트 방지를 위해 Fetch 인터셉트 + 다양한 접근법
"""
import asyncio
import json
import time
import urllib.request
import websockets

CMD_ID = 0


async def send_cmd(ws, method, params=None):
    global CMD_ID
    CMD_ID += 1
    msg = {"id": CMD_ID, "method": method, "params": params or {}}
    await ws.send(json.dumps(msg))
    cur_id = CMD_ID
    # 이벤트 메시지 수신 - id 매칭 응답 찾기
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        data = json.loads(raw)
        if data.get("id") == cur_id:
            return data


async def wait_for_nav(ws, timeout=25):
    """loadEventFired 이벤트 대기"""
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(deadline - time.time(), 1)
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5))
                data = json.loads(raw)
                method = data.get("method", "")
                if method in ("Page.loadEventFired", "Page.frameNavigated"):
                    return True
            except asyncio.TimeoutError:
                break
    except Exception:
        pass
    return False


async def scrape_coupang_api(ws_url, cat_url, cat_name):
    """CDP를 통해 쿠팡 카테고리 API 직접 호출"""
    async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
        await send_cmd(ws, "Page.enable")
        await send_cmd(ws, "Runtime.enable")
        await send_cmd(ws, "Network.enable")

        # 쿠팡 카테고리 API를 fetch로 직접 호출 (현재 페이지에서)
        # 현재 URL 확인
        url_r = await send_cmd(ws, "Runtime.evaluate", {
            "expression": "location.href",
            "returnByValue": True
        })
        current_url = url_r.get("result", {}).get("result", {}).get("value", "")
        print(f"\n[{cat_name}] 현재 URL: {current_url[:60]}", flush=True)

        # 쿠팡 도메인인지 확인 후 fetch로 카테고리 데이터 요청
        # 카테고리 ID 추출
        import re
        m = re.search(r'/categories/(\d+)', cat_url)
        cat_id = m.group(1) if m else "494460"

        # 쿠팡 내부 API 엔드포인트 시도
        fetch_js = f"""
(async function() {{
    try {{
        // 방법 1: 카테고리 API 직접 요청
        var apiUrl = 'https://www.coupang.com/np/categories/{cat_id}?listSize=60&sorter=saleCountDESC';

        var resp = await fetch(apiUrl, {{
            headers: {{
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'ko-KR,ko;q=0.9',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }},
            credentials: 'include'
        }});

        var html = await resp.text();
        return {{
            status: resp.status,
            finalUrl: resp.url,
            htmlLength: html.length,
            hasBabyProduct: html.includes('baby-product'),
            htmlSample: html.substring(0, 500)
        }};
    }} catch(e) {{
        return {{error: e.message}};
    }}
}})()
"""
        fetch_r = await send_cmd(ws, "Runtime.evaluate", {
            "expression": fetch_js,
            "returnByValue": True,
            "awaitPromise": True,
            "timeout": 20000
        })
        fetch_val = fetch_r.get("result", {}).get("result", {}).get("value", {})
        print(f"  Fetch 결과: status={fetch_val.get('status')}, finalUrl={str(fetch_val.get('finalUrl',''))[:80]}", flush=True)
        print(f"  HTML 길이: {fetch_val.get('htmlLength')}, baby-product 포함: {fetch_val.get('hasBabyProduct')}", flush=True)

        if fetch_val.get("hasBabyProduct"):
            # HTML에서 상품 파싱 (fetch 응답으로 DOMParser 사용)
            parse_js = f"""
(async function() {{
    var apiUrl = 'https://www.coupang.com/np/categories/{cat_id}?listSize=60&sorter=saleCountDESC';
    var resp = await fetch(apiUrl, {{credentials: 'include'}});
    var html = await resp.text();

    var parser = new DOMParser();
    var doc = parser.parseFromString(html, 'text/html');

    var items = doc.querySelectorAll('li.baby-product');
    var results = [];
    items.forEach(function(el) {{
        var name = (el.querySelector('.name') || el.querySelector('[class*="name"]'))?.innerText?.trim() || '';
        var price = (el.querySelector('.price-value') || el.querySelector('[class*="price-value"]'))?.innerText?.trim() || '';
        var reviews = (el.querySelector('.rating-total-count') || el.querySelector('[class*="rating-total"]'))?.innerText?.replace(/[^0-9,]/g,'').replace(/,/g,'') || '0';
        var linkEl = el.querySelector('a[href*="/vp/products/"]') || el.querySelector('a');
        var href = linkEl ? linkEl.href : '';
        if (name && href) results.push({{name, price, reviews, url: href}});
    }});
    return {{count: items.length, products: results.slice(0, 60)}};
}})()
"""
            parse_r = await send_cmd(ws, "Runtime.evaluate", {
                "expression": parse_js,
                "returnByValue": True,
                "awaitPromise": True,
                "timeout": 20000
            })
            val = parse_r.get("result", {}).get("result", {}).get("value", {})
            products = val.get("products", [])
            print(f"  DOMParser 추출: {val.get('count')} items → {len(products)} 상품", flush=True)
            return products

        # 방법 2: 페이지 navigate 후 XHR/Fetch 인터셉트
        print(f"  페이지 네비게이션 시도...", flush=True)
        await send_cmd(ws, "Page.navigate", {"url": cat_url})
        await asyncio.sleep(7)

        # 리다이렉트 후 최종 URL 확인
        url_r2 = await send_cmd(ws, "Runtime.evaluate", {
            "expression": "location.href",
            "returnByValue": True
        })
        final_url = url_r2.get("result", {}).get("result", {}).get("value", "")
        print(f"  최종 URL: {final_url[:80]}", flush=True)

        # 상품 추출
        js_extract = """
(function() {
    var items = document.querySelectorAll('li.baby-product');
    if (!items.length) items = document.querySelectorAll('li[class*="products-"]');
    if (!items.length) items = document.querySelectorAll('li[class*="product"]');

    var results = [];
    Array.from(items).slice(0, 60).forEach(function(el) {
        var name = '';
        var nameEl = el.querySelector('.name') || el.querySelector('[class*="name"]');
        if (nameEl) name = nameEl.innerText.trim();

        var price = '';
        var priceEl = el.querySelector('.price-value') || el.querySelector('[class*="price-value"]');
        if (priceEl) price = priceEl.innerText.trim();

        var reviews = '0';
        var revEl = el.querySelector('.rating-total-count') || el.querySelector('[class*="rating-total"]');
        if (revEl) reviews = revEl.innerText.replace(/[^0-9,]/g,'').replace(/,/g,'');

        var href = '';
        var linkEl = el.querySelector('a[href*="/vp/products/"]') || el.querySelector('a');
        if (linkEl) href = linkEl.href || '';

        if (name && href) results.push({name, price, reviews, url: href});
    });
    return {url: location.href, count: items.length, products: results};
})()
"""
        extract_r = await send_cmd(ws, "Runtime.evaluate", {
            "expression": js_extract,
            "returnByValue": True
        })
        val = extract_r.get("result", {}).get("result", {}).get("value", {})
        products = val.get("products", [])
        print(f"  페이지에서 추출: {val.get('count')} items → {len(products)} 상품", flush=True)
        if products:
            print(f"  샘플: {products[0]}", flush=True)
        return products


async def main():
    categories = [
        ("생활가전", "https://www.coupang.com/np/categories/494460?listSize=60&sorter=saleCountDESC"),
        ("주방가전", "https://www.coupang.com/np/categories/494461?listSize=60&sorter=saleCountDESC"),
        ("식품",    "https://www.coupang.com/np/categories/194085?listSize=60&sorter=saleCountDESC"),
        ("건강식품", "https://www.coupang.com/np/categories/194158?listSize=60&sorter=saleCountDESC"),
        ("뷰티",   "https://www.coupang.com/np/categories/194195?listSize=60&sorter=saleCountDESC"),
    ]

    # 기존 쿠팡 탭 찾기
    resp = urllib.request.urlopen("http://localhost:9222/json", timeout=5)
    tabs = json.loads(resp.read())
    coupang_tab = next((t for t in tabs if "coupang.com" in t.get("url", "") and t.get("type") == "page"), None)

    if not coupang_tab:
        print("쿠팡 탭 없음. 첫 번째 page 탭 사용.", flush=True)
        coupang_tab = next((t for t in tabs if t.get("type") == "page"), None)

    if not coupang_tab:
        print("사용 가능한 탭 없음.", flush=True)
        return

    ws_url = coupang_tab["webSocketDebuggerUrl"]
    original_url = coupang_tab["url"]
    print(f"탭: {coupang_tab['id']}", flush=True)

    results = {}
    for cat_name, url in categories:
        try:
            products = await scrape_coupang_api(ws_url, url, cat_name)
            results[cat_name] = products
        except Exception as e:
            print(f"  [{cat_name}] 오류: {e}", flush=True)
            import traceback; traceback.print_exc()
            results[cat_name] = []
        await asyncio.sleep(3)

    # 원래 URL 복구
    try:
        async with websockets.connect(ws_url, max_size=5 * 1024 * 1024) as ws:
            await send_cmd(ws, "Page.navigate", {"url": original_url})
        print(f"\n원래 URL 복구", flush=True)
    except Exception as e:
        print(f"복구 실패: {e}", flush=True)

    # 결과 저장
    with open('/Users/hana/Downloads/blog-automation-v2/coupang_bestseller_raw.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n\n=== 리뷰 1000개 이상 필터링 결과 ===\n", flush=True)
    all_filtered = []
    for cat, products in results.items():
        filtered = []
        for p in products:
            rev_str = str(p.get('reviews', '0')).replace(',', '').strip()
            try:
                rev_count = int(rev_str) if rev_str.isdigit() else 0
            except:
                rev_count = 0
            if rev_count >= 1000:
                filtered.append({**p, 'category': cat, 'review_count': rev_count})
        filtered.sort(key=lambda x: x['review_count'], reverse=True)
        all_filtered.extend(filtered)

        print(f"\n[{cat}] 리뷰 1000+ 상품: {len(filtered)}개")
        for p in filtered[:10]:
            print(f"  {p['name'][:45]} | {p['price']} | {p['review_count']}개 | {p['url'][:80]}")

    with open('/Users/hana/Downloads/blog-automation-v2/coupang_bestseller_filtered.json', 'w', encoding='utf-8') as f:
        json.dump(all_filtered, f, ensure_ascii=False, indent=2)

    print(f"\n총 리뷰 1000+ 상품: {len(all_filtered)}개")
    print("저장: coupang_bestseller_filtered.json")


if __name__ == "__main__":
    asyncio.run(main())
