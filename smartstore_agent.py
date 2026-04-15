"""스마트스토어 셀러센터 데이터 수집 에이전트
- 탭 1개만 사용, 로그인 후 LNB 메뉴 클릭으로만 이동
- 봇 감지 방지: 랜덤 딜레이, page.click(), 자연스러운 스크롤
- 작업 완료 후 탭 유지 (page.close() 호출 안 함)

실제 구조:
- LNB: #seller-lnb, 섹션 헤더 클릭으로 하위 메뉴 펼침
- 판매관리/통계 콘텐츠: 페이지 내 iframe (sell.smartstore.naver.com/o/v3/iframe/*, biz_iframe/*)
- 상품관리: Angular ui-view 직접 렌더링
- 광고관리: mg/insight/* iframe
"""
import re
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp

SMARTSTORE_URL = "https://sell.smartstore.naver.com"
NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"
NAVER_ID = "hg0191"


# ─── 유틸리티 ───────────────────────────────────────────────

def _rand_delay(page, min_ms=800, max_ms=2000):
    """사람처럼 랜덤 딜레이"""
    page.wait_for_timeout(random.randint(min_ms, max_ms))


def _natural_scroll(page, distance=300, steps=4):
    """자연스러운 마우스 스크롤"""
    step = max(1, distance // steps)
    for _ in range(steps):
        page.mouse.wheel(0, step)
        page.wait_for_timeout(random.randint(80, 180))


def _wait_nav(page, timeout=10000):
    """페이지 이동 후 안정화 대기"""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    _rand_delay(page, 1000, 1800)


def _get_main_iframe_text(page, timeout=8000):
    """페이지 내 메인 콘텐츠 iframe 텍스트 추출
    sell.smartstore.naver.com/o/v3/iframe/* 또는 biz_iframe/* 또는 mg/insight/* 형태
    """
    try:
        for f in page.frames:
            url = f.url
            if (
                "sell.smartstore.naver.com/o/" in url
                or "sell.smartstore.naver.com/biz_iframe/" in url
                or "sell.smartstore.naver.com/mg/" in url
            ) and url != page.url:
                try:
                    f.wait_for_load_state("domcontentloaded", timeout=timeout)
                    return f.evaluate("() => document.body.innerText")
                except Exception:
                    try:
                        return f.evaluate("() => document.body.innerText")
                    except Exception:
                        pass
    except Exception:
        pass
    return None


def _expand_lnb_section(page, section_name: str):
    """LNB 섹션 헤더 클릭해서 하위 메뉴 펼치기"""
    page.evaluate(f"""() => {{
        const lnb = document.getElementById('seller-lnb');
        if (!lnb) return;
        const el = Array.from(lnb.querySelectorAll('span, a'))
            .find(e => e.textContent.trim() === '{section_name}' && !e.getAttribute('href'));
        if (el) el.click();
    }}""")
    _rand_delay(page, 350, 600)


def _click_lnb_link(page, log, section: str, href: str) -> bool:
    """LNB 섹션 펼치고 해당 href 링크 클릭"""
    _expand_lnb_section(page, section)

    try:
        link = page.locator(f'#seller-lnb a[href="{href}"]').first
        link.wait_for(state="visible", timeout=6000)
        link.scroll_into_view_if_needed()
        _rand_delay(page, 200, 400)
        link.click()
        _wait_nav(page)
        log(f"[이동] {section} → {href} | URL: {page.url}")
        return True
    except Exception as e:
        log(f"[이동 실패] {section}/{href}: {e}")
        return False


# ─── 메인 진입점 ────────────────────────────────────────────

def run(on_log=None):
    """스마트스토어 셀러센터 데이터 수집

    Returns:
        dict: {
            "account": str,          # 계정명 (ID / 스토어명)
            "product_count": str,    # 상품 수
            "order_status": dict,    # 주문 현황
            "stats": dict,           # 노출/클릭/전환 등 통계
            "ad_status": str,        # 광고 집행 여부
        }
    """

    def log(msg):
        if on_log:
            on_log(msg)
        else:
            print(msg)

    result = {
        "account": None,
        "product_count": None,
        "order_status": {},
        "stats": {},
        "ad_status": None,
    }

    pw, browser = connect_cdp(on_log)

    try:
        context = browser.contexts[0] if browser.contexts else browser.new_context()

        # 기존 smartstore 탭 재사용 (새 탭 금지 원칙)
        page = None
        for p in context.pages:
            if "sell.smartstore.naver.com" in p.url:
                page = p
                break
        if page is None:
            # 기존 탭이 없을 때만 새 탭 허용
            page = context.new_page() if not context.pages else context.pages[0]

        # ── 1. sell.smartstore.naver.com 접속 (goto 1회) ──
        log("[1/6] 스마트스토어 셀러센터 접속...")
        page.goto(SMARTSTORE_URL, wait_until="domcontentloaded", timeout=30000)
        _wait_nav(page)
        log(f"[1/6] URL: {page.url}")

        # ── 2. 로그인 확인 ──
        if "nidlogin" in page.url or "naver.com/login" in page.url:
            log("[2/6] 로그인 페이지 감지 — 로그인 시작...")
            _naver_login(page, log)
        elif "sell.smartstore.naver.com" not in page.url:
            log(f"[2/6] 예상치 못한 URL({page.url}) — 로그인 시도...")
            _naver_login(page, log)
        else:
            log("[2/6] 로그인 상태 확인")

        # 계정 정보 추출
        account_info = page.evaluate("""() => {
            const id = document.querySelector('.login-id, [class*=login-id]');
            const store = document.querySelector('.shop, [class*=shop]');
            return {
                id: id ? id.innerText.trim() : null,
                store: store ? store.innerText.trim() : null
            };
        }""")
        result["account"] = f"{account_info.get('id', '?')} / {account_info.get('store', '?')}"
        log(f"[2/6] 계정: {result['account']}")

        # ── 잘못된 스토어 즉시 중단 ──
        current_id = (account_info.get("id") or "").strip().lower()
        if current_id and current_id != NAVER_ID.lower():
            log(f"[오류] 현재 로그인 계정({current_id})이 hg0191(다온나상점)이 아닙니다. 즉시 중단합니다.")
            result["error"] = f"잘못된 계정: {current_id} (hg0191이어야 함)"
            return result

        # ── 3. 상품관리 → 상품 조회/수정 ──
        log("[3/6] 상품관리 → 상품 조회/수정...")
        result["product_count"] = _get_product_count(page, log)

        # ── 4. 판매관리 → 주문 현황 ──
        log("[4/6] 판매관리 → 주문 현황...")
        result["order_status"] = _get_order_status(page, log)

        # ── 5. 데이터분석 → 요약 (노출/클릭/전환) ──
        log("[5/6] 데이터분석 → 요약...")
        result["stats"] = _get_stats(page, log)

        # ── 6. 광고관리 → 광고 집행 여부 ──
        log("[6/6] 광고관리 → 광고 집행 확인...")
        result["ad_status"] = _get_ad_status(page, log)

        # 최종 보고 (탭 그대로 유지)
        log("=" * 50)
        log(f"[완료] 계정: {result['account']}")
        log(f"[완료] 상품 수: {result['product_count']}")
        log(f"[완료] 주문 현황: {result['order_status']}")
        log(f"[완료] 통계: {result['stats']}")
        log(f"[완료] 광고: {result['ad_status']}")
        log("탭 유지됨.")
        log("=" * 50)

        return result

    finally:
        # page.close() 호출 없이 pw만 중지
        pw.stop()


# ─── 로그인 ─────────────────────────────────────────────────

def _naver_login(page, log):
    """네이버 로그인 (현재 탭에서, goto 추가 없이)"""
    if "nidlogin" not in page.url:
        page.goto(NAVER_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        _wait_nav(page)

    try:
        id_input = page.locator("#id")
        id_input.wait_for(state="visible", timeout=10000)
        id_input.click()
        _rand_delay(page, 800, 1500)
        current_id = id_input.input_value()
        log(f"[로그인] 자동완성 계정: {current_id or '(없음)'}")

        if current_id != NAVER_ID:
            id_input.click(click_count=3)
            id_input.fill(NAVER_ID)
            _rand_delay(page, 500, 1000)

        pw_input = page.locator("#pw")
        if pw_input.is_visible(timeout=3000):
            pw_input.click()
            _rand_delay(page, 800, 1200)

        login_btn = page.locator('#log\\.login, button.btn_login, button[type="submit"]').first
        login_btn.click(timeout=5000)
        _rand_delay(page, 3000, 5000)

        for _ in range(20):
            if "nidlogin" not in page.url and "naver.com" in page.url:
                log(f"[로그인] 성공 ({page.url})")
                page.goto(SMARTSTORE_URL, wait_until="domcontentloaded", timeout=30000)
                _wait_nav(page)
                return True
            _rand_delay(page, 800, 1200)

        log(f"[로그인] 실패 — URL: {page.url}")
        return False

    except Exception as e:
        log(f"[로그인] 오류: {e}")
        return False


# ─── 각 섹션 데이터 수집 ─────────────────────────────────────

def _get_product_count(page, log) -> str:
    """상품관리 → 상품 조회/수정 → 총 상품 수"""
    ok = _click_lnb_link(page, log, "상품관리", "#/products/origin-list")
    if not ok:
        return "이동 실패"

    _natural_scroll(page, 200, 3)
    _rand_delay(page, 1000, 1500)

    # 상품관리는 iframe 없이 Angular 직접 렌더링
    # ui-view 내 "목록 (총 N개)" 패턴 찾기
    body_text = page.evaluate("""() => {
        const uiview = document.querySelector('[ui-view]');
        return uiview ? uiview.innerText : document.body.innerText;
    }""")

    # 다양한 수량 패턴 시도
    patterns = [
        r'목록\s*[\(（]\s*총\s*([\d,]+)\s*개[\)）]',
        r'총\s*([\d,]+)\s*개',
        r'전체\s*([\d,]+)\s*건',
        r'([\d,]+)\s*개의\s*상품',
    ]
    for pat in patterns:
        m = re.search(pat, body_text)
        if m:
            count = m.group(0)
            log(f"[상품관리] 상품 수: {count}")
            return count

    # 패턴 매치 실패 시 관련 줄만 반환
    lines = [l.strip() for l in body_text.split('\n') if l.strip()]
    kw_lines = [l for l in lines if any(k in l for k in ['총', '개', '건', '목록', '상품'])][:5]
    result = ' | '.join(kw_lines) if kw_lines else "파싱 실패"
    log(f"[상품관리] 상품 수: {result}")
    return result


def _get_order_status(page, log) -> dict:
    """판매관리 → 발주확인/발송관리 → 주문 현황 (iframe)"""
    ok = _click_lnb_link(page, log, "판매관리", "#/naverpay/sale/delivery")
    if not ok:
        # 폴백: 미결제 확인
        ok = _click_lnb_link(page, log, "판매관리", "#/naverpay/sale/unpayment")
        if not ok:
            return {"error": "이동 실패"}

    _natural_scroll(page, 300, 4)
    _rand_delay(page, 1000, 1500)

    iframe_text = _get_main_iframe_text(page)
    if not iframe_text:
        log("[판매관리] iframe 없음")
        return {"error": "iframe 없음"}

    lines = [l.strip() for l in iframe_text.split('\n') if l.strip()]

    # "빠르게 확인해주세요!" 섹션 찾기
    status = {}
    try:
        idx = next(i for i, l in enumerate(lines) if '빠르게 확인' in l)
        section = lines[idx:idx + 25]
        # "키워드\n도움말\nN건" 패턴 파싱
        i = 0
        while i < len(section) - 1:
            line = section[i]
            # "N건" 패턴 찾기
            m = re.search(r'([\d,]+)건', section[i + 1] if i + 1 < len(section) else "")
            if m and len(line) < 30 and not re.search(r'\d', line):
                status[line] = m.group(0)
            i += 1
        log(f"[판매관리] 빠른 확인: {status}")
    except StopIteration:
        pass

    # "목록 (총 N개)" 파싱
    total_m = re.search(r'목록\s*[\(（]\s*총\s*([\d,]+)\s*개[\)）]', iframe_text)
    if total_m:
        status["총 주문"] = total_m.group(0)

    # 전체 줄에서 "X건" 포함 줄 추출
    if not status:
        order_lines = [l for l in lines if re.search(r'\d+건', l) and len(l) < 60]
        for ol in order_lines[:8]:
            status[ol] = ol
        if not status:
            status["요약"] = ' | '.join(lines[:10])

    log(f"[판매관리] 주문 현황: {status}")
    return status


def _get_stats(page, log) -> dict:
    """데이터분석 → 요약 (biz_iframe) → 어제 성과 지표"""
    ok = _click_lnb_link(page, log, "데이터분석", "#/bizadvisor/summary/ecommerce")
    if not ok:
        return {"error": "이동 실패"}

    # 차트 로딩 충분히 대기
    _rand_delay(page, 3000, 4500)
    _natural_scroll(page, 400, 5)
    _rand_delay(page, 1000, 1500)

    iframe_text = _get_main_iframe_text(page, timeout=12000)
    if not iframe_text:
        log("[통계] iframe 없음")
        return {"error": "iframe 없음"}

    lines = [l.strip() for l in iframe_text.split('\n') if l.strip()]
    stats = {}

    # "어제 X\nY값\n지난주 대비Z%" 패턴 파싱
    stat_keys = [
        "어제 결제 금액", "어제 결제건수", "어제 결제 상품수량",
        "어제 유입수", "어제 유입당 결제율", "어제 환불 금액",
        "어제 최고 결제 금액 카테고리", "어제 최고 유입 채널",
    ]
    for i, line in enumerate(lines):
        for key in stat_keys:
            if line == key and i + 1 < len(lines):
                stats[key] = lines[i + 1]
                break

    # 기간 정보
    for line in lines:
        if re.search(r'\d{4}\.\s*\d{2}\.\s*\d{2}', line):
            stats["조회기간"] = line
            break

    if not stats:
        # 관련 줄만 추출
        num_lines = [l for l in lines if re.search(r'[\d,]+[원%]?', l) and len(l) < 50]
        stats["수치"] = num_lines[:10]

    log(f"[통계] {stats}")
    return stats


def _get_ad_status(page, log) -> str:
    """광고관리 → 광고 관리 → 집행 여부 확인"""
    ok = _click_lnb_link(page, log, "광고관리", "#/smart-ads/manage")
    if not ok:
        return "이동 실패"

    _rand_delay(page, 2000, 3000)
    _natural_scroll(page, 200, 3)
    _rand_delay(page, 1000, 1500)

    iframe_text = _get_main_iframe_text(page)
    search_text = iframe_text or ""

    # iframe 없으면 페이지 본문 사용
    if not search_text:
        search_text = page.evaluate("() => document.body.innerText")

    # 집행 중 여부 판단
    on_keywords = ["집행중", "운영중", "활성", "진행중", "광고 관리\n캠페인"]
    off_keywords = ["중지", "일시정지", "종료", "등록된 광고가 없"]
    intro_keywords = ["광고 시작하기", "광고 관리 기능으로 쉽게", "소개"]  # 소개 페이지 = 미등록

    for kw in intro_keywords:
        if kw in search_text:
            ad_status = "광고 미등록 (소개 페이지)"
            log(f"[광고관리] {ad_status}")
            return ad_status

    for kw in on_keywords:
        if kw in search_text:
            ad_status = f"광고 집행 중 ({kw})"
            log(f"[광고관리] {ad_status}")
            return ad_status

    for kw in off_keywords:
        if kw in search_text:
            ad_status = f"광고 집행 안 함 ({kw})"
            log(f"[광고관리] {ad_status}")
            return ad_status

    ad_status = "확인불가 (데이터 없음)"
    log(f"[광고관리] {ad_status}")
    return ad_status


if __name__ == "__main__":
    run()
