"""
다온나상점(hg0191) 가격 경쟁력 분석 및 최적화
- CDP 포트 9223 전용
- 셀러센터 상품 목록 수집 → 네이버쇼핑 최저가 비교 → 가격 조정/판매중지
- Telegram 중간 보고 (30개마다) + 최종 보고
"""
import re
import json
import time
import random
import urllib.request
from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9223"
TELEGRAM_TOKEN_FILE = "/Users/hana/.claude/projects/-Users-hana-Downloads-blog-automation-v2/memory/reference_telegram.md"
TELEGRAM_CHAT_ID = "8674424194"
HanaAutobot = None  # 아래에서 로드

NAVER_ID = "hg0191"

# ── 판단 기준 ────────────────────────────────────────────────
# 경쟁 셀러 50명 이상 + 내가격 > 시장평균 → 판매중지
# 경쟁 셀러 10명 미만 → 가격 여유
# 시장최저가 대비 2배 이상 + 셀러 많음 → 판매중지
# 가격인하: 시장최저가 + 200~500원
# 가격인상: 내가 최저가 → 시장평균 - 100원
# 최소 마진: 15% (위탁판매 특성상 도매가+배송비 이하 금지 → 판매가 * 0.85 이하 내리지 않음)

def _rand_delay(page, min_ms=800, max_ms=2000):
    page.wait_for_timeout(random.randint(min_ms, max_ms))

def _wait_nav(page, timeout=12000):
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    _rand_delay(page, 800, 1500)

def log(msg):
    print(msg, flush=True)

def send_telegram(text):
    """텔레그램 메시지 전송"""
    if not HanaAutobot:
        log(f"[텔레그램] 토큰 없음, 로컬 출력: {text}")
        return
    try:
        url = f"https://api.telegram.org/bot{HanaAutobot}/sendMessage"
        data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        log(f"[텔레그램] 전송 완료")
    except Exception as e:
        log(f"[텔레그램] 전송 실패: {e}")

def load_telegram_token():
    """메모리 파일에서 봇 토큰 로드 시도"""
    global HanaAutobot
    # 봇 토큰은 별도 파일에서 로드
    token_paths = [
        "/Users/hana/.claude/projects/-Users-hana-Downloads-blog-automation-v2/memory/telegram_token.txt",
        "/Users/hana/Downloads/blog-automation-v2/.telegram_token",
    ]
    for p in token_paths:
        try:
            with open(p) as f:
                tok = f.read().strip()
                if tok:
                    HanaAutobot = tok
                    log(f"[텔레그램] 토큰 로드 성공")
                    return
        except Exception:
            pass
    log("[텔레그램] 토큰 파일 없음 — 로컬 로그만 출력")


# ── 상품 목록 수집 ─────────────────────────────────────────
def get_all_products(page):
    """셀러센터 상품관리 > 상품 조회/수정에서 전체 상품 수집
    Returns: list of {name, price, product_no, status}
    """
    log("[수집] 상품관리 → 상품 조회/수정 이동...")

    # LNB 상품관리 섹션 펼치기
    page.evaluate("""() => {
        const lnb = document.getElementById('seller-lnb');
        if (!lnb) return;
        const el = Array.from(lnb.querySelectorAll('span, a'))
            .find(e => e.textContent.trim() === '상품관리' && !e.getAttribute('href'));
        if (el) el.click();
    }""")
    _rand_delay(page, 400, 700)

    # 상품 조회/수정 링크 클릭
    try:
        link = page.locator('#seller-lnb a[href="#/products/origin-list"]').first
        link.wait_for(state="visible", timeout=8000)
        link.scroll_into_view_if_needed()
        _rand_delay(page, 300, 500)
        link.click()
        _wait_nav(page)
        log(f"[수집] 이동 완료: {page.url}")
    except Exception as e:
        log(f"[수집] LNB 클릭 실패, URL 직접 이동: {e}")
        page.goto("https://sell.smartstore.naver.com/#/products/origin-list",
                  wait_until="domcontentloaded", timeout=30000)
        _wait_nav(page)

    # 페이지당 100개 설정 시도
    _set_page_size(page, 100)

    products = []
    page_num = 1

    while True:
        log(f"[수집] 페이지 {page_num} 파싱 중...")
        _rand_delay(page, 1000, 1800)

        new_products = _parse_product_list(page)
        if not new_products:
            log(f"[수집] 페이지 {page_num} 상품 없음 — 수집 종료")
            break

        products.extend(new_products)
        log(f"[수집] 페이지 {page_num}: {len(new_products)}개 수집 (누적 {len(products)}개)")

        # 다음 페이지 버튼 확인
        has_next = _go_next_page(page)
        if not has_next:
            log(f"[수집] 마지막 페이지 도달")
            break
        page_num += 1
        if page_num > 20:  # 안전장치: 최대 20페이지(= 2000개)
            log("[수집] 최대 페이지(20) 도달 — 중단")
            break

    log(f"[수집] 총 {len(products)}개 상품 수집 완료")
    return products


def _set_page_size(page, size=100):
    """페이지당 표시 개수 설정 (100개)"""
    try:
        # 페이지당 개수 셀렉트박스 찾기
        selects = page.locator('select').all()
        for sel in selects:
            options = sel.evaluate("el => Array.from(el.options).map(o => o.value)")
            if str(size) in [str(o) for o in options]:
                sel.select_option(str(size))
                _rand_delay(page, 1000, 1500)
                log(f"[수집] 페이지당 {size}개 설정 완료")
                return
    except Exception as e:
        log(f"[수집] 페이지 크기 설정 실패: {e}")


def _parse_product_list(page):
    """현재 페이지의 상품 목록 파싱
    Returns: list of {name, price, product_no, status, url}
    """
    products = []

    # Angular ui-view에서 상품 테이블 파싱
    try:
        # 상품 행 찾기 — 다양한 셀렉터 시도
        rows_data = page.evaluate("""() => {
            const results = [];

            // 방법 1: 테이블 행에서 상품명 + 가격 추출
            const rows = document.querySelectorAll('tr[ng-repeat], tr[data-ng-repeat], .product-row, tbody tr');
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length < 3) return;

                // 상품명 찾기
                const nameEl = row.querySelector('a[href*="product"], .product-name, td:nth-child(2) a, .name');
                const name = nameEl ? nameEl.textContent.trim() : '';
                if (!name || name.length < 2) return;

                // href에서 상품번호 추출
                const href = nameEl ? (nameEl.getAttribute('href') || '') : '';
                const noMatch = href.match(/\/(\d+)/) || href.match(/productNo=(\d+)/);
                const productNo = noMatch ? noMatch[1] : '';

                // 판매가 찾기 (숫자+원 패턴)
                let price = 0;
                cells.forEach(td => {
                    const txt = td.textContent.trim();
                    const m = txt.match(/^([\d,]+)원?$/) || txt.match(/^([\d,]+)$/);
                    if (m) {
                        const v = parseInt(m[1].replace(/,/g, ''));
                        if (v >= 100 && v <= 10000000) {
                            price = v;
                        }
                    }
                });

                // 배송비 파싱 (무료배송 여부)
                const rowTxt = row.innerText || '';
                let myShipping = 0;
                if (rowTxt.includes('무료배송') || rowTxt.includes('무료 배송')) {
                    myShipping = 0;
                } else {
                    const shipMatch = rowTxt.match(/배송비\\s*([\\d,]+)원/) ||
                                      rowTxt.match(/배송\\s*([\\d,]+)원/);
                    if (shipMatch) {
                        const fee = parseInt(shipMatch[1].replace(/,/g, ''));
                        myShipping = (!isNaN(fee) && fee <= 50000) ? fee : 0;
                    }
                }

                // 판매상태 찾기
                const statusEl = row.querySelector('.status, [class*=status], td:last-child');
                const status = statusEl ? statusEl.textContent.trim() : '';

                if (name && price > 0) {
                    results.push({name, price, productNo, status, href, myShipping});
                }
            });

            return results;
        }""")

        if rows_data:
            products.extend(rows_data)
            return products

    except Exception as e:
        log(f"[파싱] 테이블 방법 1 실패: {e}")

    # 방법 2: 페이지 텍스트 기반 파싱
    try:
        body_text = page.evaluate("""() => {
            const uiview = document.querySelector('[ui-view]');
            return uiview ? uiview.innerText : document.body.innerText;
        }""")

        lines = [l.strip() for l in body_text.split('\n') if l.strip()]
        i = 0
        while i < len(lines):
            line = lines[i]
            # 가격 패턴: "12,000원" 또는 "12000"
            price_match = re.match(r'^([\d,]+)원?$', line)
            if price_match:
                price = int(price_match.group(1).replace(',', ''))
                if 100 <= price <= 10000000:
                    # 앞 줄에서 상품명 찾기
                    name = lines[i-1] if i > 0 else ''
                    if name and len(name) > 2 and not re.match(r'^[\d,]+', name):
                        products.append({
                            'name': name,
                            'price': price,
                            'productNo': '',
                            'status': '',
                            'href': ''
                        })
            i += 1

    except Exception as e:
        log(f"[파싱] 방법 2 실패: {e}")

    return products


def _go_next_page(page):
    """다음 페이지 버튼 클릭. 없으면 False 반환"""
    try:
        # 다음 페이지 버튼 셀렉터들
        next_selectors = [
            'a[ng-click*="next"], button[ng-click*="next"]',
            '.pagination .next:not(.disabled)',
            'a.next-page:not(.disabled)',
            'button.btn-next:not(:disabled)',
            '[aria-label="다음 페이지"]',
            '.paging button:last-child:not(:disabled)',
        ]
        for sel in next_selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000) and btn.is_enabled():
                    btn.click()
                    _wait_nav(page, timeout=8000)
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False


# ── 네이버쇼핑 최저가 조사 ─────────────────────────────────
def _detect_captcha(page):
    """캡챠 또는 봇 감지 페이지 여부 확인"""
    try:
        url = page.url
        if "captcha" in url or "challenge" in url or "robot" in url:
            return True
        title = page.title()
        if "캡챠" in title or "captcha" in title.lower() or "보안" in title:
            return True
        # 페이지 내 캡챠 요소 탐지
        has_captcha = page.evaluate("""() => {
            const txt = document.body ? document.body.innerText : '';
            return txt.includes('자동입력 방지') ||
                   txt.includes('보안문자') ||
                   txt.includes('로봇이 아닙니다') ||
                   document.querySelector('iframe[src*="recaptcha"]') !== null ||
                   document.querySelector('.g-recaptcha') !== null;
        }""")
        return bool(has_captcha)
    except Exception:
        return False


def search_naver_shopping(page, query, shopping_tab_page=None):
    """네이버쇼핑에서 상품 검색 → {min_price, avg_price, seller_count, found}
    기존 쇼핑 탭을 재사용 (탭 생성 최소화)

    - 배송비 포함 실제 구매가 기준으로 비교
      * 무료배송: 표시 가격 그대로 사용
      * 배송비 별도: 표시 가격 + 배송비 합산
    - 캡챠 감지 시 즉시 작업 중단 + Telegram 알림
    """
    search_page = shopping_tab_page or page

    try:
        encoded = urllib.parse.quote(query)
        url = f"https://search.shopping.naver.com/search/all?query={encoded}&sort=price_asc"

        search_page.goto(url, wait_until="domcontentloaded", timeout=25000)
        _rand_delay(search_page, 1500, 2500)

        # 캡챠 감지
        if _detect_captcha(search_page):
            msg = "🚨 캡챠 발생 - 수동 처리 필요합니다"
            log(f"[캡챠] {msg}")
            send_telegram(msg)
            raise RuntimeError("캡챠 감지 — 작업 중단")

        # 검색 결과 파싱 (배송비 포함 실제 구매가 계산)
        result = search_page.evaluate("""() => {
            const items = [];

            // 상품 카드 단위로 순회 (가격 + 배송비 함께 파싱)
            const cards = document.querySelectorAll(
                '.basicList_item__,  [class*=basicList_item], ' +
                '.product_item__, [class*=product_item]'
            );

            cards.forEach(card => {
                // 상품 가격
                const priceEl = card.querySelector(
                    '.price_num, [class*=price_num], .price strong, [class*=productPrice]'
                );
                if (!priceEl) return;
                const priceTxt = priceEl.textContent.replace(/[,원\\s]/g, '');
                const basePrice = parseInt(priceTxt);
                if (isNaN(basePrice) || basePrice < 100 || basePrice > 10000000) return;

                // 배송비 확인
                const cardTxt = card.innerText || '';
                let shippingFee = 0;
                if (cardTxt.includes('무료배송') || cardTxt.includes('무료 배송')) {
                    shippingFee = 0;  // 무료배송
                } else {
                    // 배송비 패턴: "배송비 3,000원" / "+3,000원" 등
                    const shipMatch = cardTxt.match(/배송비\\s*([\\d,]+)원/) ||
                                      cardTxt.match(/\\+([\\d,]+)원/) ;
                    if (shipMatch) {
                        shippingFee = parseInt(shipMatch[1].replace(/,/g, ''));
                        if (isNaN(shippingFee) || shippingFee > 50000) shippingFee = 0;
                    } else {
                        // 배송비 정보 없음 → 0원으로 처리 (보수적)
                        shippingFee = 0;
                    }
                }

                // 실제 구매가 = 상품가 + 배송비
                items.push(basePrice + shippingFee);
            });

            // 카드 파싱 실패 시 폴백: 가격 요소만 수집 (배송비 미반영)
            if (items.length === 0) {
                const priceEls = document.querySelectorAll(
                    '.price_num, [class*=price_num], .price strong, ' +
                    '[class*=productPrice], .basicList_price__'
                );
                priceEls.forEach(el => {
                    const txt = el.textContent.replace(/[,원\\s]/g, '');
                    const n = parseInt(txt);
                    if (!isNaN(n) && n >= 100 && n <= 10000000) {
                        items.push(n);
                    }
                });
            }

            // 셀러 수 (더보기 / 총 N개)
            const countEl = document.querySelector(
                '.subFilter_num__m7TIw, [class*=subFilter_num], ' +
                '.totalCount, [class*=count_num]'
            );
            const countTxt = countEl ? countEl.textContent : '';
            const countMatch = countTxt.match(/([\\d,]+)/);
            const sellerCount = countMatch ? parseInt(countMatch[1].replace(/,/g, '')) : 0;

            if (items.length === 0) return {found: false};

            items.sort((a, b) => a - b);
            const minPrice = items[0];
            const avgPrice = Math.round(items.reduce((a, b) => a + b, 0) / items.length);

            return {found: true, minPrice, avgPrice, sellerCount, sampleCount: items.length};
        }""")

        if result and result.get('found'):
            return result
        else:
            return {'found': False, 'minPrice': 0, 'avgPrice': 0, 'sellerCount': 0}

    except RuntimeError:
        raise  # 캡챠 예외는 그대로 전파
    except Exception as e:
        log(f"[쇼핑검색] '{query}' 오류: {e}")
        return {'found': False, 'minPrice': 0, 'avgPrice': 0, 'sellerCount': 0}

import urllib.parse


# ── 가격 조정 결정 로직 ───────────────────────────────────────
def decide_action(product, market):
    """
    product: {name, price, productNo, myShipping(optional)}
    market: {found, minPrice, avgPrice, sellerCount}
             ※ minPrice/avgPrice는 이미 배송비 포함 실제 구매가

    Returns: (action, new_price, reason)
    action: 'stop' | 'lower' | 'raise' | 'keep'

    비교 기준: 배송비 포함 실제 구매가로 동일 기준 비교
    - 내 실제 구매가 = 내 판매가(price) + 내 배송비(myShipping)
    - 시장 가격(minPrice/avgPrice)은 search_naver_shopping에서 이미 배송비 합산됨
    """
    my_price = product['price']
    my_shipping = product.get('myShipping', 0) or 0
    # 내 실제 구매가 (배송비 포함)
    my_total = my_price + my_shipping

    if not market.get('found') or market['minPrice'] == 0:
        return 'keep', my_price, '시장 데이터 없음'

    min_p = market['minPrice']   # 시장 최저 실제 구매가 (배송비 포함)
    avg_p = market['avgPrice']   # 시장 평균 실제 구매가 (배송비 포함)
    sellers = market.get('sellerCount', 0)

    # 최소 가격 (마진 15% 보장) — 판매가 기준
    min_allowed = int(my_price * 0.85)

    # 판매중지: 시장최저가(실구매가) 대비 내 실구매가 2배 이상 + 경쟁자 많음
    if my_total >= min_p * 2 and sellers >= 50:
        return 'stop', 0, f'시장최저(배송포함) {min_p:,}원의 {my_total/min_p:.1f}배, 경쟁{sellers}명'

    # 가격인하: 시장평균(실구매가)보다 비쌈 + 경쟁자 20명 이상
    if my_total > avg_p * 1.2 and sellers >= 20:
        # 목표: 시장최저(실구매가)보다 200~500원 비싼 수준으로 내 판매가 조정
        new_price = (min_p - my_shipping) + random.randint(200, 500)
        new_price = max(new_price, min_p + random.randint(200, 500) - my_shipping)
        # 마진 최소 보장
        if new_price < min_allowed:
            new_price = min_allowed
        if new_price < my_price:
            return 'lower', new_price, f'시장평균(배송포함) {avg_p:,}원보다 비쌈(내실구매가:{my_total:,}원), 경쟁{sellers}명'

    # 가격인상: 내 실구매가가 시장최저(배송포함) 이하 + 경쟁자 적음
    if my_total <= min_p and sellers < 30:
        # 목표 판매가: 시장평균(실구매가) - 배송비 - 100원
        new_price = max(my_price, avg_p - my_shipping - 100)
        if new_price > my_price * 1.5:
            new_price = int(my_price * 1.3)  # 30% 이상 올리지 않음
        if new_price > my_price:
            return 'raise', new_price, f'내 실구매가({my_total:,}원) ≤ 시장최저(배송포함) {min_p:,}원, 경쟁{sellers}명'

    # 가격인상 2: 내 실구매가가 시장평균의 80% 미만 + 경쟁자 10명 미만 → 여유 있음
    if my_total < avg_p * 0.8 and sellers < 10:
        new_price = int(avg_p * 0.9) - my_shipping
        if new_price > my_price * 1.5:
            new_price = int(my_price * 1.3)
        if new_price > my_price:
            return 'raise', new_price, f'틈새상품, 시장평균(배송포함) {avg_p:,}원, 경쟁{sellers}명'

    return 'keep', my_price, f'적정가격 (시장최저(배송포함) {min_p:,}원, 평균 {avg_p:,}원)'


# ── 셀러센터 가격 변경 ─────────────────────────────────────
def update_product_price(page, product_no, new_price):
    """셀러센터에서 특정 상품 가격 변경
    Returns: True/False
    """
    if not product_no:
        return False

    try:
        # 상품 수정 페이지로 이동
        edit_url = f"https://sell.smartstore.naver.com/#/products/real/{product_no}"
        page.goto(edit_url, wait_until="domcontentloaded", timeout=25000)
        _wait_nav(page, timeout=10000)

        # 판매가 입력 필드 찾기
        price_input = page.locator(
            'input[name="salePrice"], input[placeholder*="판매가"], '
            'input[ng-model*="price"], .price-input input'
        ).first

        price_input.wait_for(state="visible", timeout=8000)
        price_input.triple_click()
        _rand_delay(page, 300, 500)
        price_input.fill(str(new_price))
        _rand_delay(page, 500, 800)

        # 저장 버튼
        save_btn = page.locator(
            'button[ng-click*="save"], button.btn-primary, '
            'button:has-text("저장"), button:has-text("수정완료")'
        ).first
        save_btn.wait_for(state="visible", timeout=5000)
        save_btn.click()
        _wait_nav(page, timeout=10000)

        # 성공 확인
        success = page.evaluate("""() => {
            const msg = document.querySelector('.alert-success, .toast-success, [class*=success]');
            return msg ? msg.textContent.trim() : null;
        }""")
        log(f"[가격변경] {product_no} → {new_price:,}원 성공: {success}")
        return True

    except Exception as e:
        log(f"[가격변경] {product_no} 실패: {e}")
        return False


def stop_product_sale(page, product_no, product_name):
    """셀러센터에서 특정 상품 판매중지
    Returns: True/False
    """
    if not product_no:
        log(f"[판매중지] {product_name} — 상품번호 없음, 건너뜀")
        return False

    try:
        # 상품 목록으로 돌아가서 해당 상품 체크 후 판매중지
        edit_url = f"https://sell.smartstore.naver.com/#/products/real/{product_no}"
        page.goto(edit_url, wait_until="domcontentloaded", timeout=25000)
        _wait_nav(page, timeout=10000)

        # 판매상태 변경 버튼/드롭다운
        stop_btn = page.locator(
            'button:has-text("판매중지"), select[ng-model*="status"], '
            'a:has-text("판매중지"), button[ng-click*="suspend"]'
        ).first

        if stop_btn.is_visible(timeout=5000):
            stop_btn.click()
            _rand_delay(page, 500, 800)

            # 확인 팝업
            confirm_btn = page.locator(
                'button:has-text("확인"), button:has-text("예"), button.btn-ok'
            ).first
            if confirm_btn.is_visible(timeout=3000):
                confirm_btn.click()
                _wait_nav(page, timeout=8000)
            log(f"[판매중지] {product_name} 성공")
            return True

        # select 드롭다운 방법
        status_sel = page.locator('select[ng-model*="status"], select[name*="status"]').first
        if status_sel.is_visible(timeout=3000):
            status_sel.select_option(value="SUSPENSION")
            _rand_delay(page, 500, 800)
            save_btn = page.locator('button:has-text("저장"), button:has-text("수정완료")').first
            if save_btn.is_visible(timeout=3000):
                save_btn.click()
                _wait_nav(page, timeout=8000)
            log(f"[판매중지] {product_name} (select) 성공")
            return True

        log(f"[판매중지] {product_name} — 버튼 없음")
        return False

    except Exception as e:
        log(f"[판매중지] {product_name} 실패: {e}")
        return False


# ── 메인 ──────────────────────────────────────────────────
def run():
    load_telegram_token()

    send_telegram("🔧 다온나상점 가격 최적화 시작\nCDP 9223 연결 중...")

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        log(f"[연결] CDP 9223 연결 성공")
    except Exception as e:
        log(f"[연결] CDP 9223 연결 실패: {e}")
        pw.stop()
        send_telegram(f"❌ CDP 9223 연결 실패: {e}")
        return

    try:
        context = browser.contexts[0] if browser.contexts else browser.new_context()

        # 셀러센터 탭 재사용
        seller_page = None
        for p in context.pages:
            if "sell.smartstore.naver.com" in p.url:
                seller_page = p
                break
        if seller_page is None:
            seller_page = context.pages[0] if context.pages else context.new_page()
            seller_page.goto("https://sell.smartstore.naver.com/#/home/dashboard",
                            wait_until="domcontentloaded", timeout=30000)
            _wait_nav(seller_page)

        log(f"[셀러센터] 현재 URL: {seller_page.url}")

        # 로그인 확인
        if "nidlogin" in seller_page.url or "login" in seller_page.url.lower():
            send_telegram("❌ 셀러센터 로그인 필요 — 수동 로그인 후 재실행하세요")
            return

        # ── 1. 전체 상품 수집 ──
        log("=" * 50)
        log("[1단계] 전체 상품 수집 시작")
        send_telegram("📦 상품 목록 수집 중...\n(전체 상품 페이지 순회)")

        products = get_all_products(seller_page)

        if not products:
            send_telegram("❌ 상품 수집 실패 — 상품 없음 또는 파싱 오류")
            log("[오류] 상품 수집 실패")
            return

        send_telegram(f"✅ 상품 수집 완료: {len(products)}개\n\n가격 분석 시작...")

        # ── 2. 네이버쇼핑 최저가 비교 ──
        log("=" * 50)
        log(f"[2단계] 네이버쇼핑 최저가 비교 ({len(products)}개)")

        # 쇼핑 탭: 기존 탭에서 검색 (같은 탭 재사용)
        # 셀러센터 탭을 보존하고, 쇼핑 검색은 다른 기존 탭 사용
        shopping_page = None
        for p in context.pages:
            if "shopping.naver.com" in p.url or "naver.com/nidlogin" in p.url:
                shopping_page = p
                break
        if shopping_page is None:
            # 기존 탭 중 셀러센터 아닌 것 재사용
            for p in context.pages:
                if "sell.smartstore.naver.com" not in p.url:
                    shopping_page = p
                    break
        if shopping_page is None:
            shopping_page = context.new_page()

        results = []
        stopped = []
        lowered = []
        raised = []
        kept = []

        for i, product in enumerate(products):
            name = product.get('name', '')
            my_price = product.get('price', 0)
            product_no = product.get('productNo', '')

            if not name or my_price <= 0:
                continue

            # 네이버쇼핑 검색 (30자 초과는 앞부분만)
            search_query = name[:30] if len(name) > 30 else name
            try:
                market = search_naver_shopping(shopping_page, search_query)
            except RuntimeError:
                # 캡챠 감지 — Telegram 알림은 search_naver_shopping 내에서 이미 전송됨
                log("[캡챠] 작업 중단")
                return

            action, new_price, reason = decide_action(product, market)

            result = {
                'name': name,
                'my_price': my_price,
                'market': market,
                'action': action,
                'new_price': new_price,
                'reason': reason,
                'product_no': product_no,
            }
            results.append(result)

            my_shipping_fee = product.get('myShipping', 0) or 0
            my_total_price = my_price + my_shipping_fee
            shipping_label = f"(배송비:{my_shipping_fee:,}원포함={my_total_price:,})" if my_shipping_fee > 0 else "(무료배송)"
            log(f"[{i+1}/{len(products)}] {name[:25]} | 내가격:{my_price:,}{shipping_label} | "
                f"시장최저(배송포함):{market.get('minPrice',0):,} | 결정:{action} | {reason}")

            # ── 실제 조치 실행 ──
            if action == 'stop':
                ok = stop_product_sale(seller_page, product_no, name)
                if ok:
                    stopped.append(result)
                    # 셀러센터 나온 후 현재 URL 복구
                    _rand_delay(seller_page, 1000, 1500)
            elif action == 'lower':
                ok = update_product_price(seller_page, product_no, new_price)
                if ok:
                    lowered.append(result)
                    _rand_delay(seller_page, 800, 1200)
            elif action == 'raise':
                ok = update_product_price(seller_page, product_no, new_price)
                if ok:
                    raised.append(result)
                    _rand_delay(seller_page, 800, 1200)
            else:
                kept.append(result)

            # 셀러센터 탭이 이동했으면 상품 목록으로 복귀 (다음 조치 전)
            if action in ('stop', 'lower', 'raise'):
                _rand_delay(seller_page, 1200, 2000)

            # 30개마다 중간 보고
            if (i + 1) % 30 == 0:
                msg = (
                    f"🔧 가격 최적화 진행 중\n"
                    f"- 분석: {i+1}/{len(products)}개\n"
                    f"- 판매중지: {len(stopped)}개\n"
                    f"- 가격인하: {len(lowered)}개\n"
                    f"- 가격인상: {len(raised)}개\n"
                    f"- 현상유지: {len(kept)}개"
                )
                send_telegram(msg)
                log(msg)

            # 인간적인 딜레이 (쇼핑 검색 간)
            _rand_delay(shopping_page, 1000, 2500)

        # ── 최종 보고 ──
        log("=" * 50)
        log("[완료] 가격 최적화 완료")

        stop_lines = '\n'.join(
            f"- {r['name'][:20]} (내:{r['my_price']:,}원 / 최저:{r['market'].get('minPrice',0):,}원)"
            for r in stopped[:10]
        ) or '없음'

        lower_lines = '\n'.join(
            f"- {r['name'][:20]}: {r['my_price']:,}→{r['new_price']:,}원"
            for r in lowered[:10]
        ) or '없음'

        raise_lines = '\n'.join(
            f"- {r['name'][:20]}: {r['my_price']:,}→{r['new_price']:,}원"
            for r in raised[:10]
        ) or '없음'

        final_msg = (
            f"✅ 가격 최적화 완료\n\n"
            f"[판매중지] {len(stopped)}개\n{stop_lines}\n\n"
            f"[가격인하] {len(lowered)}개\n{lower_lines}\n\n"
            f"[가격인상] {len(raised)}개\n{raise_lines}\n\n"
            f"[현상유지] {len(kept)}개\n"
            f"(총 분석 {len(results)}개)"
        )
        send_telegram(final_msg)
        log(final_msg)

        # 결과 JSON 저장
        with open('/Users/hana/Downloads/blog-automation-v2/price_optimization_result.json', 'w', encoding='utf-8') as f:
            json.dump({
                'total': len(results),
                'stopped': stopped,
                'lowered': lowered,
                'raised': raised,
                'kept_count': len(kept),
            }, f, ensure_ascii=False, indent=2)
        log("[저장] price_optimization_result.json 저장 완료")

    finally:
        pw.stop()


if __name__ == "__main__":
    run()
