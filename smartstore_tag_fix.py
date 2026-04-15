"""스마트스토어 판매자 태그 일괄 등록 + 상품명 부적합 수정
- CDP 포트 9223 연결
- 로그인 ID: hg0191
- 방법 A: 상품 목록 API → 태그 업데이트 API
- 방법 B (폴백): UI 자동화
"""
import json
import re
import time
import random
import sys
import traceback
from pathlib import Path
from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9223"
SMARTSTORE_URL = "https://sell.smartstore.naver.com"
NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"
NAVER_ID = "hg0191"
NAVER_PW = "qazq0691+@"

start_time = time.time()

def log(msg):
    elapsed = int(time.time() - start_time)
    print(f"[{elapsed:03d}s] {msg}", flush=True)

def rand_delay(page, mn=500, mx=1500):
    page.wait_for_timeout(random.randint(mn, mx))

def wait_nav(page, timeout=12000):
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    rand_delay(page, 800, 1500)


# ─── 태그 생성 규칙 ─────────────────────────────────────────
def generate_tags(product_name: str) -> list[str]:
    """상품명에서 최대 10개 태그 추출 (공백 없는 단어 형태)"""
    name = product_name.strip()
    # 특수문자 제거 후 단어 분리
    clean = re.sub(r'[^\w\s가-힣a-zA-Z0-9]', ' ', name)
    words = [w.strip() for w in clean.split() if len(w.strip()) >= 2]

    # 핵심 키워드 사전
    category_map = {
        '가디건': ['가디건', '니트가디건', '여성가디건'],
        '원피스': ['원피스', '여성원피스', '데일리원피스'],
        '티셔츠': ['티셔츠', '반팔티', '여성티셔츠'],
        '블라우스': ['블라우스', '여성블라우스', '셔츠블라우스'],
        '바지': ['바지', '여성바지', '슬랙스'],
        '청바지': ['청바지', '데님팬츠', '진'],
        '스커트': ['스커트', '미니스커트', '롱스커트'],
        '코트': ['코트', '여성코트', '롱코트'],
        '패딩': ['패딩', '겨울패딩', '다운패딩'],
        '자켓': ['자켓', '여성자켓', '아우터'],
        '니트': ['니트', '니트탑', '여성니트'],
        '후드': ['후드티', '후드집업', '캐주얼'],
        '맨투맨': ['맨투맨', '스웨트셔츠', '캐주얼티'],
        '레깅스': ['레깅스', '스판레깅스', '운동레깅스'],
        '수영복': ['수영복', '비키니', '래쉬가드'],
        '잠옷': ['잠옷', '파자마', '홈웨어'],
        '속옷': ['속옷', '언더웨어', '브라'],
        '반팔': ['반팔', '반팔티', '여름티'],
        '긴팔': ['긴팔', '긴팔티', '가을티'],
        '민소매': ['민소매', '나시', '탑'],
        '봄': ['봄옷', '봄신상', '봄코디'],
        '여름': ['여름옷', '여름신상', '여름코디'],
        '가을': ['가을옷', '가을신상', '가을코디'],
        '겨울': ['겨울옷', '겨울신상', '겨울코디'],
        '오버핏': ['오버핏', '루즈핏', '빅사이즈'],
        '슬림': ['슬림핏', '슬림', '타이트'],
        '세트': ['세트', '투피스세트', '코디세트'],
        '데님': ['데님', '청바지', '데님팬츠'],
        '린넨': ['린넨', '린넨셔츠', '여름린넨'],
        '면': ['면티', '순면', '면소재'],
        '실크': ['실크', '새틴', '광택'],
    }

    tags = set()

    # 상품명 자체를 공백 제거해서 태그로
    no_space = re.sub(r'\s+', '', name)
    if len(no_space) <= 20:
        tags.add(no_space)

    # 카테고리 매핑
    for keyword, tag_list in category_map.items():
        if keyword in name:
            for t in tag_list:
                tags.add(t)
            break  # 첫 번째 매핑만

    # 개별 단어 조합 태그
    key_modifiers = ['여성', '남성', '봄', '여름', '가을', '겨울', '오버핏', '슬림', '루즈', '스트라이프', '플로럴', '체크']
    for word in words:
        if word in key_modifiers:
            continue
        if len(word) >= 2:
            tags.add(word)

    # 수식어 + 상품종류 조합
    for mod in key_modifiers:
        if mod in name:
            for word in words:
                if word not in key_modifiers and len(word) >= 2:
                    combined = mod + word
                    if len(combined) <= 15:
                        tags.add(combined)
                    break

    # 최대 10개, 짧은 것 우선
    tag_list = sorted(tags, key=lambda x: len(x))[:10]
    return tag_list


# ─── 로그인 ─────────────────────────────────────────────────
def naver_login(page):
    log("로그인 페이지 이동...")
    page.goto(NAVER_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    wait_nav(page, 8000)

    try:
        id_input = page.locator("#id")
        id_input.wait_for(state="visible", timeout=10000)
        id_input.click()
        rand_delay(page, 500, 1000)
        id_input.triple_click()
        id_input.type(NAVER_ID, delay=80)
        rand_delay(page, 400, 800)

        pw_input = page.locator("#pw")
        pw_input.click()
        rand_delay(page, 400, 800)
        pw_input.type(NAVER_PW, delay=80)
        rand_delay(page, 600, 1000)

        login_btn = page.locator('#log\\.login, button.btn_login, button[type="submit"]').first
        login_btn.click(timeout=5000)
        rand_delay(page, 3000, 5000)

        for _ in range(20):
            cur = page.url
            if "nidlogin" not in cur and ("naver.com" in cur or "smartstore" in cur):
                log(f"로그인 성공: {cur}")
                return True
            rand_delay(page, 800, 1200)

        log(f"로그인 실패 — URL: {page.url}")
        return False
    except Exception as e:
        log(f"로그인 오류: {e}")
        return False


def ensure_logged_in(page):
    page.goto(SMARTSTORE_URL, wait_until="domcontentloaded", timeout=30000)
    wait_nav(page, 10000)
    cur = page.url
    log(f"현재 URL: {cur}")
    if "nidlogin" in cur or "login" in cur:
        ok = naver_login(page)
        if not ok:
            raise RuntimeError("로그인 실패")
        page.goto(SMARTSTORE_URL, wait_until="domcontentloaded", timeout=30000)
        wait_nav(page)
    log("셀러센터 진입 완료")


# ─── API 방식 ────────────────────────────────────────────────
def get_api_base_and_channel(page) -> tuple[str, str]:
    """현재 셀러센터에서 channelNo 추출"""
    cur = page.url
    # URL 패턴: sell.smartstore.naver.com/#/... 또는 채널 정보를 JS 변수에서 추출
    channel_no = None

    # JS에서 채널 정보 추출 시도
    try:
        channel_no = page.evaluate("""() => {
            // 전역 변수 탐색
            if (window.__CHANNEL_NO__) return window.__CHANNEL_NO__;
            if (window.channelNo) return window.channelNo;
            // Angular 앱 탐색
            const el = document.querySelector('[ng-app], [data-ng-app]');
            if (el && el.__ngContext__) return null;
            return null;
        }""")
    except Exception:
        pass

    if not channel_no:
        # 쿠키에서 채널번호 추출 시도
        try:
            cookies = page.context.cookies()
            for c in cookies:
                if 'channel' in c['name'].lower():
                    channel_no = c['value']
                    break
        except Exception:
            pass

    # URL 해시에서 추출 시도
    if not channel_no:
        m = re.search(r'/channels/(\d+)', cur)
        if m:
            channel_no = m.group(1)

    return channel_no


def fetch_products_via_api(page, channel_no: str) -> list[dict]:
    """상품 목록 API 호출"""
    all_products = []
    page_num = 1
    page_size = 100

    while True:
        api_url = f"https://sell.smartstore.naver.com/v2/products?page={page_num}&pageSize={page_size}&statusTypes=SALE,SUSPEND"
        log(f"API 호출: {api_url}")

        try:
            resp = page.request.get(api_url, timeout=15000)
            if resp.status != 200:
                log(f"API 응답 {resp.status} — API 방식 포기")
                return []
            data = resp.json()
            items = data.get('contents', data.get('items', data.get('data', [])))
            if not items:
                break
            all_products.extend(items)
            log(f"페이지 {page_num}: {len(items)}개 (누적 {len(all_products)}개)")
            if len(items) < page_size:
                break
            page_num += 1
            time.sleep(random.uniform(0.8, 1.5))
        except Exception as e:
            log(f"API 오류: {e}")
            return []

    return all_products


def update_product_tags_api(page, product_id: str, tags: list[str]) -> bool:
    """단일 상품 태그 업데이트 (API)"""
    try:
        api_url = f"https://sell.smartstore.naver.com/v2/products/{product_id}"
        # 먼저 현재 상품 데이터 조회
        resp = page.request.get(api_url, timeout=10000)
        if resp.status != 200:
            return False
        product_data = resp.json()

        # 태그 업데이트
        product_data['sellerTags'] = [{'text': t} for t in tags]

        # PUT 요청
        put_resp = page.request.put(
            api_url,
            data=json.dumps(product_data),
            headers={'Content-Type': 'application/json'},
            timeout=15000
        )
        return put_resp.status in (200, 201, 204)
    except Exception as e:
        log(f"태그 업데이트 오류 (ID={product_id}): {e}")
        return False


# ─── UI 방식 폴백 ─────────────────────────────────────────────
def go_to_product_list(page):
    """상품관리 → 상품 목록으로 이동"""
    page.goto(f"{SMARTSTORE_URL}/#/products/origin-list", wait_until="domcontentloaded", timeout=30000)
    wait_nav(page)
    log(f"상품 목록 URL: {page.url}")


def get_products_from_ui(page) -> list[dict]:
    """UI에서 상품 목록 파싱"""
    products = []
    go_to_product_list(page)
    rand_delay(page, 2000, 3000)

    # 전체 상품 수 확인
    try:
        total_text = page.evaluate("""() => {
            const t = document.querySelector('[ui-view]') || document.body;
            return t.innerText;
        }""")
        m = re.search(r'총\s*([\d,]+)\s*개', total_text)
        if m:
            total = int(m.group(1).replace(',', ''))
            log(f"총 상품 수: {total}개")
    except Exception:
        pass

    # 상품 행 파싱 (Angular 테이블)
    try:
        rows = page.evaluate("""() => {
            const rows = [];
            // 테이블 행 탐색
            document.querySelectorAll('tr, [class*=product-row], [class*=list-item]').forEach(row => {
                const nameEl = row.querySelector('[class*=product-name], [class*=name], td:nth-child(3)');
                const idEl = row.querySelector('[class*=product-id], [data-product-id]');
                const linkEl = row.querySelector('a[href*=products]');
                if (nameEl && nameEl.innerText.trim()) {
                    const name = nameEl.innerText.trim();
                    const id = idEl ? idEl.innerText.trim() : (linkEl ? linkEl.href.match(/\\/([0-9]+)(?:\\/|$)/)?.[1] : null);
                    if (name && id) rows.push({name, id});
                }
            });
            return rows;
        }""")
        products.extend(rows)
        log(f"UI 파싱: {len(rows)}개 행 발견")
    except Exception as e:
        log(f"UI 파싱 오류: {e}")

    return products


def update_tag_via_ui(page, product_url_or_id: str, tags: list[str]) -> bool:
    """UI로 개별 상품 태그 입력"""
    try:
        if product_url_or_id.startswith('http'):
            page.goto(product_url_or_id, wait_until="domcontentloaded", timeout=30000)
        else:
            page.goto(f"{SMARTSTORE_URL}/#/products/real/{product_url_or_id}/edit", wait_until="domcontentloaded", timeout=30000)
        wait_nav(page)
        rand_delay(page, 1500, 2500)

        # 판매자태그 입력 필드 찾기
        tag_input = page.locator('input[placeholder*="태그"], input[class*="tag"], [class*="seller-tag"] input').first
        tag_input.wait_for(state="visible", timeout=8000)

        for tag in tags:
            tag_input.click()
            rand_delay(page, 200, 400)
            tag_input.type(tag, delay=50)
            rand_delay(page, 300, 500)
            tag_input.press("Enter")
            rand_delay(page, 200, 400)

        # 저장 버튼 클릭
        save_btn = page.locator('button:has-text("저장"), button:has-text("완료"), button[class*="save"]').first
        save_btn.click(timeout=5000)
        wait_nav(page, 8000)
        return True
    except Exception as e:
        log(f"UI 태그 입력 실패: {e}")
        return False


# ─── 상품 진단 페이지 접근 ───────────────────────────────────
def get_problematic_products(page) -> list[dict]:
    """상품 진단에서 상품명 문제 상품 목록 추출"""
    # 상품 진단 페이지 접근 시도
    diag_urls = [
        f"{SMARTSTORE_URL}/#/products/diagnosis",
        f"{SMARTSTORE_URL}/#/products/smart-diagnosis",
        f"{SMARTSTORE_URL}/#/products/product-diagnosis",
    ]

    for url in diag_urls:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            wait_nav(page, 8000)
            cur = page.url
            log(f"진단 URL 시도: {url} → {cur}")

            # 페이지에 진단 관련 내용 있는지 확인
            body = page.evaluate("() => document.body.innerText")
            if '진단' in body or '상품명' in body:
                log("진단 페이지 진입 성공")
                return _parse_diagnosis_page(page)
        except Exception as e:
            log(f"진단 URL 실패 ({url}): {e}")

    # LNB 탐색
    try:
        page.goto(SMARTSTORE_URL, wait_until="domcontentloaded", timeout=30000)
        wait_nav(page)
        # 상품관리 섹션에서 진단 메뉴 찾기
        page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('#seller-lnb a'));
            const diag = links.find(a => a.textContent.includes('진단'));
            if (diag) diag.click();
        }""")
        wait_nav(page)
        body = page.evaluate("() => document.body.innerText")
        if '진단' in body:
            return _parse_diagnosis_page(page)
    except Exception as e:
        log(f"LNB 진단 탐색 실패: {e}")

    return []


def _parse_diagnosis_page(page) -> list[dict]:
    """진단 페이지에서 상품명 문제 상품 추출"""
    problems = []
    try:
        # "상품명 문제" 항목 클릭
        page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('*'));
            const el = els.find(e => e.textContent.trim() === '상품명' || e.textContent.includes('상품명 문제'));
            if (el) el.click();
        }""")
        rand_delay(page, 1000, 2000)

        body_text = page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in body_text.split('\n') if l.strip()]

        # 상품 ID와 이름 파싱
        for line in lines:
            if re.search(r'\d{10,}', line):  # 상품 ID 패턴
                m = re.search(r'(\d{10,})', line)
                if m:
                    problems.append({'id': m.group(1), 'name': line})

        log(f"진단 페이지: {len(problems)}개 상품 발견")
    except Exception as e:
        log(f"진단 페이지 파싱 오류: {e}")

    return problems


def fix_product_name(original_name: str) -> str:
    """상품명 수정 규칙 적용"""
    name = original_name

    # 1. 특수문자 제거 (!, ★, ◆, ■, ▶ 등)
    name = re.sub(r'[!！★◆■▶●◀▲▼◇☆♥♦♠♣]', '', name)

    # 2. 금지어 제거 (과장 표현)
    banned = [
        '최저가', '최저', '1위', '인증', '공식', '정품인증', '인증서',
        '보장', '100%', '무조건', '절대', '완전', '초특가', '대박',
        '폭탄', '땡처리', '최고', '최상', '프리미엄급', 'NO.1', 'no.1',
    ]
    for b in banned:
        name = name.replace(b, '')

    # 3. 연속 공백 정리
    name = re.sub(r'\s+', ' ', name).strip()

    # 4. 길이 조정 (25~50자)
    if len(name) > 50:
        # 50자에서 자연스럽게 자르기 (단어 경계에서)
        name = name[:50].rsplit(' ', 1)[0] if ' ' in name[:50] else name[:50]

    return name


# ─── 메인 실행 ────────────────────────────────────────────────
def main():
    result = {
        "tag_success": 0,
        "tag_fail": 0,
        "tag_fail_reasons": [],
        "tag_examples": [],
        "name_fixed": [],
        "name_fail": [],
        "errors": [],
    }

    with sync_playwright() as p:
        log("CDP 연결 중...")
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            log(f"CDP 연결 실패: {e}")
            return result

        context = browser.contexts[0] if browser.contexts else browser.new_context()

        # 기존 스마트스토어 탭 재사용
        page = None
        for pg in context.pages:
            if "smartstore" in pg.url or "naver" in pg.url:
                page = pg
                log(f"기존 탭 재사용: {pg.url}")
                break
        if page is None:
            page = context.new_page()
            log("새 탭 생성")

        try:
            # ── 1. 로그인 확인 ──
            log("=" * 50)
            log("STEP 1: 로그인 확인")
            ensure_logged_in(page)

            # ── 2. 상품 목록 수집 (API 방식 먼저) ──
            log("=" * 50)
            log("STEP 2: 상품 목록 수집")

            products = []

            # API 방식 시도: 채널번호 없이 직접 호출
            log("API 방식 시도...")
            api_url = "https://sell.smartstore.naver.com/v2/products?page=1&pageSize=100&statusTypes=SALE"
            try:
                resp = page.request.get(api_url, timeout=15000)
                log(f"API 응답 상태: {resp.status}")
                if resp.status == 200:
                    data = resp.json()
                    log(f"API 응답 키: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                    # 다양한 키 탐색
                    for key in ['contents', 'items', 'data', 'products', 'list']:
                        if key in data:
                            items = data[key]
                            if items:
                                products.extend(items)
                                log(f"API 방식 성공: {len(items)}개 (키={key})")
                                break
                    if not products and isinstance(data, list):
                        products = data
                        log(f"API 방식 성공 (직접 리스트): {len(products)}개")
                else:
                    log(f"API 방식 실패 (상태 {resp.status}), UI 방식으로 전환")
            except Exception as e:
                log(f"API 방식 오류: {e}, UI 방식으로 전환")

            # API 실패 시 다른 엔드포인트 시도
            if not products:
                alt_urls = [
                    "https://sell.smartstore.naver.com/v1/products?page=1&pageSize=100",
                    "https://sell.smartstore.naver.com/api/v1/products?page=1&size=100",
                ]
                for alt_url in alt_urls:
                    try:
                        resp = page.request.get(alt_url, timeout=10000)
                        log(f"대안 API {alt_url}: 상태 {resp.status}")
                        if resp.status == 200:
                            data = resp.json()
                            log(f"대안 API 응답: {str(data)[:200]}")
                            break
                    except Exception as e:
                        log(f"대안 API 오류: {e}")

            # ── 3. 상품명 진단 페이지 ──
            log("=" * 50)
            log("STEP 3: 상품 진단 페이지 접근")

            # 상품 목록 UI 진입 (진단 경로 포함)
            page.goto(f"{SMARTSTORE_URL}/#/products/origin-list", wait_until="domcontentloaded", timeout=30000)
            wait_nav(page)
            rand_delay(page, 2000, 3000)

            log(f"상품 목록 페이지 URL: {page.url}")

            # 현재 페이지 텍스트 확인
            body_text = page.evaluate("""() => {
                const t = document.querySelector('[ui-view]') || document.body;
                return t.innerText.substring(0, 2000);
            }""")
            log(f"페이지 내용 (앞 500자): {body_text[:500]}")

            # 상품 목록에서 ID와 이름 파싱 시도
            if not products:
                log("UI에서 상품 정보 파싱 시도...")
                products_from_ui = page.evaluate("""() => {
                    const result = [];
                    // 다양한 선택자로 상품 행 탐색
                    const selectors = [
                        'tr[class*="product"]',
                        '[class*="product-item"]',
                        '[class*="list-row"]',
                        'tbody tr',
                    ];
                    for (const sel of selectors) {
                        const rows = document.querySelectorAll(sel);
                        if (rows.length > 0) {
                            rows.forEach(row => {
                                const text = row.innerText.trim();
                                const link = row.querySelector('a[href*="product"]');
                                const name = row.querySelector('[class*="name"], td:nth-child(3), td:nth-child(2)');
                                if (text && link) {
                                    const m = link.href.match(/\\/([0-9]{8,})/);
                                    result.push({
                                        id: m ? m[1] : null,
                                        name: name ? name.innerText.trim() : text.split('\\n')[0],
                                        href: link.href
                                    });
                                }
                            });
                            if (result.length > 0) break;
                        }
                    }
                    return result;
                }""")
                log(f"UI 파싱 결과: {len(products_from_ui)}개")
                if products_from_ui:
                    products = products_from_ui

            # ── 4. 실제 상품 목록 페이지에서 데이터 수집 ──
            log("=" * 50)
            log("STEP 4: 상품 데이터 수집 (페이지 스크롤 방식)")

            all_product_data = []  # {id, name, tags} 형태

            # 스크롤하며 모든 상품 수집
            rand_delay(page, 1000, 2000)

            # 페이지네이션으로 전체 수집
            page_idx = 1
            while True:
                log(f"페이지 {page_idx} 수집...")
                rand_delay(page, 1500, 2500)

                page_products = page.evaluate("""() => {
                    const result = [];
                    // Angular 렌더링된 상품 행
                    const rows = document.querySelectorAll('[ui-view] tr, [ng-repeat], [class*="product-row"]');
                    rows.forEach(row => {
                        const links = row.querySelectorAll('a');
                        let productId = null, productName = null;
                        links.forEach(a => {
                            const m = a.href.match(/\\/([0-9]{8,})(?:\\/|$)/);
                            if (m) {
                                productId = m[1];
                                productName = a.innerText.trim() || a.title || null;
                            }
                        });
                        if (productId && productName) {
                            result.push({id: productId, name: productName});
                        }
                    });
                    return result;
                }""")

                if page_products:
                    log(f"페이지 {page_idx}: {len(page_products)}개 상품")
                    all_product_data.extend(page_products)
                else:
                    log(f"페이지 {page_idx}: 상품 없음 — 중단")
                    break

                # 다음 페이지 버튼 찾기
                next_btn = page.locator('button[class*="next"], a[class*="next"], [aria-label="다음"]').first
                if next_btn.is_visible(timeout=2000):
                    next_btn.click()
                    wait_nav(page, 8000)
                    page_idx += 1
                else:
                    log("다음 페이지 없음")
                    break

                if page_idx > 20:  # 안전장치
                    break

            log(f"총 수집 상품: {len(all_product_data)}개")

            # API로 수집된 상품과 합치기
            if products and not all_product_data:
                # API 데이터를 표준 형태로 변환
                for p in products:
                    pid = p.get('productNo') or p.get('id') or p.get('productId')
                    pname = p.get('name') or p.get('productName') or p.get('originProductName', '')
                    if pid and pname:
                        all_product_data.append({'id': str(pid), 'name': pname})
                log(f"API 데이터 변환: {len(all_product_data)}개")

            if not all_product_data:
                log("상품 목록 수집 실패 — 현재 페이지 HTML 구조 확인")
                html_sample = page.evaluate("() => document.body.innerHTML.substring(0, 3000)")
                log(f"HTML 샘플: {html_sample[:1000]}")
                result["errors"].append("상품 목록 수집 실패")

            # ── 5. 태그 없는 상품 필터링 ──
            log("=" * 50)
            log("STEP 5: 태그 없는 상품에 태그 등록")

            # API로 태그 현황 확인
            products_without_tags = []
            for prod in all_product_data:
                pid = prod.get('id')
                pname = prod.get('name', '')
                existing_tags = prod.get('sellerTags', prod.get('tags', []))
                if not existing_tags:
                    products_without_tags.append({'id': pid, 'name': pname})

            if not products_without_tags:
                # 모든 상품이 태그 없다고 가정 (API 데이터 없는 경우)
                products_without_tags = all_product_data
                log(f"태그 현황 불명 — 전체 {len(all_product_data)}개 처리 대상으로 설정")
            else:
                log(f"태그 없는 상품: {len(products_without_tags)}개")

            # 배치 처리 (10개씩)
            batch_size = 10
            for batch_start in range(0, len(products_without_tags), batch_size):
                batch = products_without_tags[batch_start:batch_start + batch_size]
                log(f"배치 {batch_start//batch_size + 1}: {len(batch)}개 처리")

                for prod in batch:
                    pid = prod.get('id')
                    pname = prod.get('name', '')
                    if not pid or not pname:
                        result["tag_fail"] += 1
                        result["tag_fail_reasons"].append(f"ID 또는 이름 없음: {prod}")
                        continue

                    tags = generate_tags(pname)
                    log(f"  상품 {pid} '{pname[:30]}' → 태그: {tags}")

                    # API 업데이트 시도
                    success = False
                    try:
                        api_url = f"https://sell.smartstore.naver.com/v2/products/{pid}"
                        resp = page.request.get(api_url, timeout=10000)
                        if resp.status == 200:
                            prod_data = resp.json()
                            prod_data['sellerTags'] = [{'text': t} for t in tags]
                            put_resp = page.request.put(
                                api_url,
                                data=json.dumps(prod_data),
                                headers={'Content-Type': 'application/json'},
                                timeout=15000
                            )
                            if put_resp.status in (200, 201, 204):
                                success = True
                                log(f"    API 태그 등록 성공")
                            else:
                                log(f"    API PUT 실패: {put_resp.status}")
                        else:
                            log(f"    API GET 실패: {resp.status}")
                    except Exception as e:
                        log(f"    API 오류: {e}")

                    if success:
                        result["tag_success"] += 1
                        if len(result["tag_examples"]) < 5:
                            result["tag_examples"].append({"name": pname, "tags": tags})
                    else:
                        result["tag_fail"] += 1
                        result["tag_fail_reasons"].append(f"{pname[:20]}: API 실패")

                    rand_delay(page, 500, 1200)

                # 배치 간 휴식
                if batch_start + batch_size < len(products_without_tags):
                    sleep_sec = random.uniform(2, 3)
                    log(f"배치 완료, {sleep_sec:.1f}초 대기...")
                    time.sleep(sleep_sec)

            # ── 6. 상품 진단 → 상품명 수정 ──
            log("=" * 50)
            log("STEP 6: 상품 진단 → 상품명 부적합 수정")

            # 진단 페이지 접근
            diag_page_urls = [
                f"{SMARTSTORE_URL}/#/products/diagnosis",
                f"{SMARTSTORE_URL}/#/products/smart-diagnosis",
            ]

            diag_found = False
            for durl in diag_page_urls:
                try:
                    page.goto(durl, wait_until="domcontentloaded", timeout=20000)
                    wait_nav(page, 8000)
                    rand_delay(page, 2000, 3000)
                    body = page.evaluate("() => document.body.innerText")
                    if '진단' in body or '상품명' in body:
                        log(f"진단 페이지 발견: {durl}")
                        diag_found = True
                        break
                except Exception as e:
                    log(f"진단 URL {durl} 실패: {e}")

            if not diag_found:
                # LNB에서 진단 메뉴 찾기
                page.goto(SMARTSTORE_URL, wait_until="domcontentloaded", timeout=30000)
                wait_nav(page)
                rand_delay(page, 1500, 2500)
                lnb_text = page.evaluate("() => document.getElementById('seller-lnb') ? document.getElementById('seller-lnb').innerText : ''")
                log(f"LNB 텍스트: {lnb_text[:500]}")

                # 진단 링크 찾기
                diag_link = page.evaluate("""() => {
                    const lnb = document.getElementById('seller-lnb');
                    if (!lnb) return null;
                    const a = Array.from(lnb.querySelectorAll('a')).find(a => a.textContent.includes('진단'));
                    return a ? a.href : null;
                }""")
                if diag_link:
                    log(f"LNB 진단 링크: {diag_link}")
                    page.goto(diag_link, wait_until="domcontentloaded", timeout=20000)
                    wait_nav(page)
                    diag_found = True
                else:
                    log("진단 페이지를 찾을 수 없음 — 스킵")

            if diag_found:
                rand_delay(page, 2000, 3000)
                diag_body = page.evaluate("() => document.body.innerText")
                log(f"진단 페이지 내용 (앞 1000자): {diag_body[:1000]}")

                # 상품명 문제 항목 클릭
                page.evaluate("""() => {
                    const all = Array.from(document.querySelectorAll('*'));
                    const el = all.find(e =>
                        (e.textContent.trim() === '상품명' || e.textContent.includes('상품명 문제'))
                        && e.children.length < 3
                    );
                    if (el) el.click();
                }""")
                rand_delay(page, 2000, 3000)

                # 문제 상품 목록 파싱
                problem_products = page.evaluate("""() => {
                    const result = [];
                    document.querySelectorAll('tr, [class*="product-row"], [class*="list-item"]').forEach(row => {
                        const nameEl = row.querySelector('[class*="product-name"], [class*="name"] a, td a');
                        const linkEl = row.querySelector('a[href*="product"]');
                        if (nameEl && linkEl) {
                            const m = linkEl.href.match(/\\/([0-9]{8,})/);
                            result.push({
                                id: m ? m[1] : null,
                                name: nameEl.innerText.trim(),
                                href: linkEl.href
                            });
                        }
                    });
                    return result;
                }""")

                log(f"상품명 문제 상품: {len(problem_products)}개")

                for prod in problem_products[:10]:  # 최대 10개만 처리
                    pid = prod.get('id')
                    orig_name = prod.get('name', '')
                    if not pid or not orig_name:
                        continue

                    new_name = fix_product_name(orig_name)
                    if new_name == orig_name:
                        log(f"  수정 불필요: '{orig_name}'")
                        continue

                    log(f"  수정: '{orig_name}' → '{new_name}'")

                    # UI로 상품명 수정
                    try:
                        edit_url = f"{SMARTSTORE_URL}/#/products/real/{pid}/edit"
                        page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
                        wait_nav(page)
                        rand_delay(page, 2000, 3000)

                        # 상품명 입력 필드 찾기
                        name_input = page.locator('input[name*="productName"], input[placeholder*="상품명"], #productName').first
                        name_input.wait_for(state="visible", timeout=8000)
                        name_input.triple_click()
                        rand_delay(page, 300, 500)
                        name_input.type(new_name, delay=60)
                        rand_delay(page, 500, 1000)

                        # 저장
                        save_btn = page.locator('button:has-text("저장"), button:has-text("수정완료")').first
                        save_btn.click(timeout=5000)
                        wait_nav(page, 10000)

                        result["name_fixed"].append({"before": orig_name, "after": new_name})
                        log(f"    저장 완료")
                    except Exception as e:
                        log(f"    상품명 수정 실패: {e}")
                        result["name_fail"].append({"name": orig_name, "reason": str(e)})

                    rand_delay(page, 1000, 2000)
            else:
                log("진단 페이지 접근 불가 — 상품명 수정 스킵")

        except Exception as e:
            log(f"전체 오류: {e}")
            traceback.print_exc()
            result["errors"].append(str(e))
        finally:
            log("작업 완료 (탭 유지)")
            # page.close() 호출 안 함

    return result


if __name__ == "__main__":
    r = main()
    elapsed = int(time.time() - start_time)

    print("\n" + "=" * 60)
    print("[태그/상품명 수정 결과]")
    print()
    print("## 태그 등록")
    print(f"- 처리 완료: {r['tag_success']}개")
    print(f"- 실패: {r['tag_fail']}개")
    if r['tag_fail_reasons']:
        for reason in r['tag_fail_reasons'][:5]:
            print(f"  - {reason}")
    if r['tag_examples']:
        print("- 태그 예시:")
        for ex in r['tag_examples']:
            print(f"  - \"{ex['name']}\" → {ex['tags']}")
    print()
    print("## 상품명 수정")
    print(f"- 수정 완료: {len(r['name_fixed'])}개")
    for i, fix in enumerate(r['name_fixed'], 1):
        print(f"  {i}. 전: \"{fix['before']}\" / 후: \"{fix['after']}\"")
    print()
    print("## 실패/오류")
    for err in r['errors']:
        print(f"- {err}")
    for fail in r['name_fail']:
        print(f"- 상품명 수정 실패: {fail['name'][:30]} ({fail['reason'][:50]})")
    print()
    print(f"## 소요 시간")
    print(f"- 총 {elapsed // 60}분 {elapsed % 60}초")
    print("=" * 60)
