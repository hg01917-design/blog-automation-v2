"""쿠팡파트너스 페이지 구조 분석 스크립트"""
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp

LOG = []

def log(msg):
    print(msg)
    LOG.append(msg)

def run():
    pw, browser = connect_cdp(log)
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()

    try:
        # ── 1. 파트너스 메인 접속 ──────────────────────────────────────────
        log("\n=== [1] 파트너스 메인 페이지 ===")
        page.goto("https://partners.coupang.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        log(f"현재 URL: {page.url}")
        log(f"페이지 제목: {page.title()}")

        # 로그인 여부 확인
        is_logged_in = page.evaluate("""() => {
            // 로그인 상태 힌트
            return {
                url: location.href,
                hasLogoutBtn: !!document.querySelector('a[href*="logout"], button[class*="logout"]'),
                hasLoginBtn: !!document.querySelector('a[href*="login"], button[class*="login"]'),
                userInfo: document.querySelector('.user-name, .user_name, [class*="userNickname"]')?.innerText || '',
                navMenu: [...document.querySelectorAll('nav a, .gnb a')].map(a => a.innerText.trim()).filter(t => t).slice(0,8),
            };
        }""")
        log(f"로그인 상태: {json.dumps(is_logged_in, ensure_ascii=False)}")

        # ── 2. 상품 링크 만들기 페이지 ────────────────────────────────────
        log("\n=== [2] 링크 생성 페이지 탐색 ===")
        page.goto("https://partners.coupang.com/link/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
        log(f"링크생성 URL: {page.url}")

        link_page_info = page.evaluate("""() => {
            return {
                title: document.title,
                inputs: [...document.querySelectorAll('input')].map(i => ({type: i.type, placeholder: i.placeholder, name: i.name, id: i.id})),
                buttons: [...document.querySelectorAll('button')].map(b => b.innerText.trim()).filter(t => t).slice(0,10),
                headings: [...document.querySelectorAll('h1,h2,h3')].map(h => h.innerText.trim()).filter(t => t).slice(0,5),
            };
        }""")
        log(f"링크 페이지 구조: {json.dumps(link_page_info, ensure_ascii=False, indent=2)}")

        # ── 3. 쿠팡 상품 페이지에서 파트너스 링크 직접 생성 시도 ──────────
        log("\n=== [3] 실제 상품에서 파트너스 링크 생성 테스트 ===")
        # 인기 카테고리 몇 개 시도
        test_products = [
            "https://www.coupang.com/vp/products/7891447044",  # 예시 상품
        ]

        # 파트너스 링크 생성 API 엔드포인트 탐색
        page.goto("https://partners.coupang.com/link/url", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
        log(f"URL 링크 생성 페이지: {page.url}")

        url_gen_info = page.evaluate("""() => {
            return {
                url: location.href,
                inputs: [...document.querySelectorAll('input')].map(i => ({type: i.type, placeholder: i.placeholder, name: i.name, id: i.id})).slice(0,5),
                buttons: [...document.querySelectorAll('button')].map(b => ({text: b.innerText.trim(), class: b.className})).filter(b => b.text).slice(0,8),
                forms: [...document.querySelectorAll('form')].map(f => ({id: f.id, action: f.action, class: f.className})),
            };
        }""")
        log(f"URL 생성 페이지: {json.dumps(url_gen_info, ensure_ascii=False, indent=2)}")

        # ── 4. 인기상품 / 배너 API 탐색 ──────────────────────────────────
        log("\n=== [4] 인기상품 배너 페이지 ===")
        page.goto("https://partners.coupang.com/banner/bestseller", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
        log(f"인기상품 URL: {page.url}")

        bestseller_info = page.evaluate("""() => {
            const products = [...document.querySelectorAll('[class*="product"], [class*="item"], li.unit')].slice(0,5);
            return {
                url: location.href,
                productCount: document.querySelectorAll('[class*="product-item"], [class*="productItem"], .unit').length,
                sampleProducts: products.map(p => ({
                    text: p.innerText.substring(0,100),
                    links: [...p.querySelectorAll('a')].map(a => a.href).slice(0,2),
                })),
                links: [...document.querySelectorAll('a[href*="coupang.com"], a[href*="link.coupang"]')].map(a => a.href).slice(0,10),
            };
        }""")
        log(f"베스트셀러 페이지: {json.dumps(bestseller_info, ensure_ascii=False, indent=2)}")

        # ── 5. API 호출 탐색 (네트워크 탭 없이 직접 확인) ─────────────────
        log("\n=== [5] 파트너스 링크 URL 패턴 분석 ===")
        # URL 링크 생성기에서 직접 입력 시도
        page.goto("https://partners.coupang.com/link/url", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        # 입력창에 상품 URL 입력 후 링크 생성
        test_url = "https://www.coupang.com/vp/products/7891447044"
        try:
            url_input = page.locator("input[type='text'], input[placeholder*='URL'], input[placeholder*='url'], input[name*='url']").first
            if url_input.count() > 0:
                url_input.fill(test_url)
                page.wait_for_timeout(1000)
                # 생성 버튼 클릭
                gen_btn = page.locator("button").filter(has_text="생성")
                if gen_btn.count() > 0:
                    gen_btn.first.click()
                    page.wait_for_timeout(3000)
                    # 결과 링크 추출
                    result = page.evaluate("""() => {
                        const resultEl = document.querySelector('input[readonly], textarea[readonly], .result-url, [class*="result"] input');
                        return resultEl ? resultEl.value : null;
                    }""")
                    log(f"생성된 파트너스 링크: {result}")
        except Exception as e:
            log(f"URL 입력 시도 실패: {e}")

        # ── 6. 최종 분석: 링크 구조 ────────────────────────────────────────
        log("\n=== [6] 현재 페이지 전체 링크 샘플 ===")
        all_links = page.evaluate("""() => {
            return [...document.querySelectorAll('a')].map(a => ({
                text: a.innerText.trim().substring(0,30),
                href: a.href,
            })).filter(a => a.href && a.href !== '#' && a.href !== location.href).slice(0,20);
        }""")
        for lnk in all_links:
            log(f"  {lnk['text'][:25]:25s} → {lnk['href']}")

    finally:
        page.close()
        try:
            pw.stop()
        except Exception:
            pass

    # 결과 저장
    result_path = Path("/tmp/coupang_partners_analysis.txt")
    result_path.write_text("\n".join(LOG), encoding="utf-8")
    log(f"\n결과 저장: {result_path}")

if __name__ == "__main__":
    run()
