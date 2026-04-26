"""팩트체크 모듈 — 가격/스펙 주장을 블로그별 지정 사이트로 검증 후 자동 수정"""
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from browser import connect_cdp


# ── 1. 클레임 추출 ──────────────────────────────────────────────────────────

# 가격 정규식 (원화 표기 3종)
_PRICE_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})+원)"           # 1,234,000원
    r"|(\d+(?:\.\d+)?만\s*원)"           # 15만원 / 15.5만원
    r"|(\d+(?:\.\d+)?천\s*원)",          # 5천원
    re.UNICODE,
)

# 스펙 정규식
_SPEC_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mAh|GB|TB|Hz|MP|인치|kg|mm|cm|W)(?!\w)",
    re.UNICODE | re.IGNORECASE,
)


def _parse_won(text: str) -> float:
    """'1,234,000원' / '15만원' / '5천원' → float (원 단위)"""
    t = text.replace(" ", "").replace(",", "")
    if "만원" in t:
        return float(re.sub(r"만원$", "", t)) * 10_000
    if "천원" in t:
        return float(re.sub(r"천원$", "", t)) * 1_000
    return float(re.sub(r"원$", "", t))


def extract_price_claims(body: str) -> list:
    """본문에서 가격 클레임 추출 → [{"match", "value", "start", "end"}]"""
    claims = []
    for m in _PRICE_RE.finditer(body):
        raw = m.group(0).strip()
        try:
            value = _parse_won(raw)
        except (ValueError, AttributeError):
            continue
        if value <= 0:
            continue
        claims.append({
            "match": raw, "value": value,
            "start": m.start(), "end": m.end(), "type": "price",
        })
    return claims


def extract_spec_claims(body: str) -> list:
    """본문에서 스펙 클레임 추출 → [{"match", "value", "unit", "start", "end"}]"""
    claims = []
    for m in _SPEC_RE.finditer(body):
        try:
            value = float(m.group(1))
        except ValueError:
            continue
        claims.append({
            "match": m.group(0).strip(), "value": value, "unit": m.group(2),
            "start": m.start(), "end": m.end(), "type": "spec",
        })
    return claims


# ── 2. 키워드 기반 팩트체크 사이트 결정 ─────────────────────────────────────

# (트리거 단어 리스트, 사이트 목록)
_FACT_CHECK_ROUTES = [
    # OTT / 스트리밍
    (["넷플릭스", "Netflix", "netflix"], [
        {"url": "https://www.netflix.com/kr/search?q={q}",
         "selectors": [".price", "[class*='price']", "[class*='plan']"], "label": "넷플릭스"},
    ]),
    (["티빙", "tving", "TVING"], [
        {"url": "https://www.tving.com/search?keyword={q}",
         "selectors": [".price", "[class*='price']"], "label": "티빙"},
    ]),
    (["웨이브", "wavve", "Wavve"], [
        {"url": "https://www.wavve.com/search?keyword={q}",
         "selectors": [".price", "[class*='price']"], "label": "웨이브"},
    ]),
    (["쿠팡플레이", "CoupangPlay"], [
        {"url": "https://www.coupangplay.com/search?keyword={q}",
         "selectors": [".price", "[class*='price']"], "label": "쿠팡플레이"},
    ]),
    (["왓챠", "watcha"], [
        {"url": "https://watcha.com/search?query={q}",
         "selectors": [".price", "[class*='price']"], "label": "왓챠"},
    ]),
    (["디즈니플러스", "Disney+", "disney+"], [
        {"url": "https://www.disneyplus.com/ko-kr/search?q={q}",
         "selectors": [".price", "[class*='price']"], "label": "디즈니+"},
    ]),
    # OTT 묶음 (요금제 비교)
    (["OTT", "ott", "스트리밍 요금", "구독 요금"], [
        {"url": "https://search.naver.com/search.naver?query={q}+요금제",
         "selectors": ["[class*='dsc_txt']", "[class*='api_txt_lines']"], "label": "네이버검색(OTT)"},
    ]),

    # 전기
    (["전기요금", "전기세", "kWh", "kwh", "누진세", "전력요금"], [
        {"url": "https://www.kepco.co.kr/search/index.do?searchWord={q}",
         "selectors": [".price", "[class*='price']", ".cost"], "label": "한전"},
    ]),

    # 가스
    (["가스요금", "도시가스요금", "가스비", "도시가스비"], [
        {"url": "https://www.kogas.or.kr/search/search.do?q={q}",
         "selectors": [".price", "[class*='price']", ".cost"], "label": "한국가스공사"},
    ]),

    # 건강보험
    (["건강보험료", "건보료", "보험료 계산"], [
        {"url": "https://www.nhis.or.kr/search/search.do?q={q}",
         "selectors": [".price", "[class*='amount']"], "label": "건보공단"},
    ]),

    # 국민연금
    (["국민연금", "노령연금", "연금 수령"], [
        {"url": "https://www.nps.or.kr/jsppage/search/total_search.jsp?q={q}",
         "selectors": [".price", "[class*='amount']"], "label": "국민연금공단"},
    ]),

    # 복지·지원금
    (["지원금", "보조금", "복지급여", "기초생활", "실업급여", "고용보험"], [
        {"url": "https://www.bokjiro.go.kr/ssis-tbu/twataa/wlfareInfo/moveTWAT52011M.do?searchWord={q}",
         "selectors": [".price", "[class*='amount']"], "label": "복지로"},
        {"url": "https://www.gov.kr/search?srchWord={q}",
         "selectors": [".price", "[class*='amount']"], "label": "정부24"},
    ]),

    # IT 제품 — 삼성
    (["갤럭시", "삼성 갤럭시", "Galaxy", "삼성 TV", "삼성 냉장고"], [
        {"url": "https://www.samsung.com/kr/search/?searchvalue={q}",
         "selectors": [".price", "[class*='price']"], "label": "삼성공식"},
        {"url": "https://search.shopping.naver.com/search/all?query={q}",
         "selectors": ["strong.price_num", ".price_num"], "label": "네이버쇼핑"},
    ]),

    # IT 제품 — 애플
    (["아이폰", "맥북", "아이패드", "iPhone", "MacBook", "iPad"], [
        {"url": "https://www.apple.com/kr/search/{q}?src=serp",
         "selectors": [".price", "[class*='price']"], "label": "애플공식"},
        {"url": "https://search.shopping.naver.com/search/all?query={q}",
         "selectors": ["strong.price_num", ".price_num"], "label": "네이버쇼핑"},
    ]),

    # 여행 — 입장료/운영
    (["입장료", "관람료", "국립공원", "설악산", "지리산", "한라산"], [
        {"url": "https://search.naver.com/search.naver?query={q}+입장료",
         "selectors": ["[class*='dsc_txt']", "[class*='api_txt_lines']"],
         "label": "네이버검색(입장료)", "max_price": 29999},
        {"url": "https://www.knps.or.kr/portal/search/search.do?searchWord={q}",
         "selectors": [".price", "[class*='fee']"], "label": "국립공원공단",
         "max_price": 29999},
    ]),

    # 여행 — 숙박
    (["호텔", "리조트", "펜션", "숙박"], [
        {"url": "https://hotel.naver.com/hotels/search?query={q}",
         "selectors": [".price", "[class*='price']"], "label": "네이버호텔",
         "min_price": 30000},
        {"url": "https://www.yanolja.com/search?keyword={q}",
         "selectors": [".price", "[class*='price']"], "label": "야놀자",
         "min_price": 30000},
    ]),
]

# 블로그별 기본 사이트 (키워드 매칭 안 될 때 폴백)
_DEFAULT_SITES = {
    "goodisak": [
        {"url": "https://search.shopping.naver.com/search/all?query={q}",
         "selectors": ["strong.price_num", ".price_num"], "label": "네이버쇼핑"},
        {"url": "https://search.danawa.com/dsearch.php?query={q}",
         "selectors": [".price_sect strong", ".low_price strong"], "label": "다나와"},
    ],
    "nolja100": [
        {"url": "https://search.naver.com/search.naver?query={q}+입장료",
         "selectors": ["[class*='dsc_txt']", "[class*='api_txt_lines']"],
         "label": "네이버검색", "max_price": 29999},
        {"url": "https://hotel.naver.com/hotels/search?query={q}",
         "selectors": [".price", "[class*='price']"], "label": "네이버호텔",
         "min_price": 30000},
    ],
    "salim1su": [
        {"url": "https://search.naver.com/search.naver?query={q}",
         "selectors": ["[class*='dsc_txt']", "[class*='api_txt_lines']"], "label": "네이버검색"},
    ],
    "baremi542": [
        {"url": "https://www.bokjiro.go.kr/ssis-tbu/twataa/wlfareInfo/moveTWAT52011M.do?searchWord={q}",
         "selectors": [".price", "[class*='amount']"], "label": "복지로"},
        {"url": "https://www.gov.kr/search?srchWord={q}",
         "selectors": [".price", "[class*='amount']"], "label": "정부24"},
    ],
}


def get_fact_check_sites(blog_name, keyword=""):
    """키워드 우선, 없으면 블로그 기본 사이트 반환.

    Returns:
        [{"url": str, "selectors": list, "label": str}, ...]
    """
    kw = keyword or ""
    for triggers, sites in _FACT_CHECK_ROUTES:
        if triggers and any(t in kw for t in triggers):
            return sites

    # 키워드 매칭 없음 → 블로그 기본값
    blog = (blog_name or "").lower().strip()
    for key in _DEFAULT_SITES:
        if key in blog:
            return _DEFAULT_SITES[key]

    # 최종 폴백
    return [
        {"url": "https://search.shopping.naver.com/search/all?query={q}",
         "selectors": ["strong.price_num", ".price_num"], "label": "네이버쇼핑"},
    ]


# ── 3. 크롤링 ────────────────────────────────────────────────────────────────

def _clean_price(raw: str):
    cleaned = re.sub(r"[^\d]", "", raw)
    return float(cleaned) if cleaned else None


def _scrape_prices(page, url: str, selectors: list, on_log=None) -> list:
    """지정 URL에서 가격 목록 스크랩"""
    def log(msg):
        if on_log:
            on_log(msg)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)
    except Exception as e:
        log(f"[팩트체크] 페이지 로드 실패: {e}")
        return []

    for sel in selectors:
        try:
            els = page.locator(sel)
            if els.count() == 0:
                continue
            prices = []
            for i in range(min(5, els.count())):
                raw = els.nth(i).inner_text(timeout=2000).strip()
                p = _clean_price(raw)
                if p and p > 0:
                    prices.append(p)
            if prices:
                return prices
        except Exception:
            continue
    return []


def _fetch_actual_prices(browser, query, blog_name="", keyword="", on_log=None, claim_value=0):
    """키워드 기반 팩트체크 사이트에서 가격 조회 — 첫 번째 결과 반환 후 폴백"""
    def log(msg):
        if on_log:
            on_log(msg)

    sites = get_fact_check_sites(blog_name, keyword)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    try:
        q = urllib.parse.quote(query)
        for site in sites:
            # 가격 범위에 맞는 사이트만 사용
            min_price = site.get("min_price", 0)
            max_price = site.get("max_price", 0)
            if claim_value > 0:
                if min_price > 0 and claim_value < min_price:
                    log(f"[팩트체크] {site['label']} 스킵 — {claim_value:,.0f}원 < 최소 {min_price:,}원")
                    continue
                if max_price > 0 and claim_value > max_price:
                    log(f"[팩트체크] {site['label']} 스킵 — {claim_value:,.0f}원 > 최대 {max_price:,}원")
                    continue
            url = site["url"].format(q=q)
            label = site["label"]
            prices = _scrape_prices(page, url, site["selectors"], on_log)
            if prices:
                log(f"[팩트체크] {label} '{query}' 가격 {len(prices)}개: {prices}")
                return prices
            log(f"[팩트체크] {label} 결과 없음 → 다음 사이트 폴백")
        return []
    finally:
        try:
            page.close()
        except Exception:
            pass


# ── 4. 비교 및 수정 ──────────────────────────────────────────────────────────

MISMATCH_THRESHOLD = 0.25  # 25% 이상 차이 시 자동 수정


def _median(values: list) -> float:
    s = sorted(values)
    n = len(s)
    return (s[n // 2 - 1] + s[n // 2]) / 2 if n % 2 == 0 else s[n // 2]


def _format_price_korean(value: float) -> str:
    """float → 한국어 가격 표기"""
    v = int(round(value, -2))  # 100원 단위 반올림
    if v >= 10_000 and v % 10_000 == 0:
        return f"{v // 10_000}만원"
    if v >= 10_000:
        man = v // 10_000
        rem = v % 10_000
        if rem % 1_000 == 0:
            return f"{man}만 {rem // 1_000}천원"
        return f"{v:,}원"
    if v >= 1_000 and v % 1_000 == 0:
        return f"{v // 1_000}천원"
    return f"{v:,}원"


def _apply_corrections(body: str, corrections: list) -> str:
    """역순 오프셋으로 치환 (앞쪽 오프셋 보존)"""
    for c in sorted(corrections, key=lambda x: x["start"], reverse=True):
        body = body[: c["start"]] + c["new_text"] + body[c["end"]:]
    return body


# ── 5. 메인 진입점 ───────────────────────────────────────────────────────────

def run(body: str, keyword: str, blog_name: str = "", on_log=None) -> dict:
    """팩트체크 실행.

    Args:
        body: 검증할 블로그 본문
        keyword: 검색 키워드
        blog_name: 블로그 식별자 (goodisak / nolja100 / salim1su / baremi542)
        on_log: 로그 콜백

    Returns:
        {"body": str, "corrections": list, "checked": bool}
    """
    def log(msg):
        if on_log:
            on_log(msg)

    FALLBACK = {"body": body, "corrections": [], "checked": False}

    price_claims = extract_price_claims(body)
    spec_claims = extract_spec_claims(body)

    if not price_claims:
        log(f"[팩트체크] 가격 클레임 없음 (스펙 {len(spec_claims)}건은 크롤링 없이 통과)")
        return FALLBACK

    log(f"[팩트체크] 가격 {len(price_claims)}건, 스펙 {len(spec_claims)}건 발견")

    # CDP 연결
    try:
        pw, browser = connect_cdp(on_log)
    except Exception as e:
        log(f"[팩트체크] CDP 연결 실패: {e} — 건너뜀")
        return FALLBACK

    corrections = []
    try:
        for claim in price_claims[:3]:  # 최대 3건 (시간 제한)
            # 가격 앞 80자 컨텍스트에서 제품명 추출
            ctx_start = max(0, claim["start"] - 80)
            ctx_text = body[ctx_start:claim["start"]].strip()
            # 마지막 문장 단위로 자르기 (쉼표/마침표/줄바꿈 기준)
            product_query = re.split(r"[,\.。\n]", ctx_text)[-1].strip()
            # 한국어 문법 조사·어미 제거 (예: "렌탈은 월", "가격이", "비용은")
            product_query = re.sub(
                r'\s+\S*(은|는|이|가|을|를|의|에서|에|로|렌탈은?|월|가격은?|비용은?|요금은?|구입은?)\s*$',
                '', product_query
            ).strip()
            # 제품명으로 너무 짧거나 오염된 경우 keyword 사용
            search_query = product_query if len(product_query) > 3 else keyword
            log(f"[팩트체크] 검색어: '{search_query}' (원문: '{ctx_text[-20:]}')")

            actual_prices = _fetch_actual_prices(browser, search_query, blog_name, keyword, on_log, claim_value=claim["value"])

            if not actual_prices:
                log(f"[팩트체크] '{search_query}' 가격 조회 실패 — 건너뜀")
                continue

            actual_median = _median(actual_prices)
            actual_min = min(actual_prices)
            actual_max = max(actual_prices)
            stated = claim["value"]
            ratio = abs(stated - actual_median) / actual_median if actual_median else 0

            # 실제 범위 내에 있으면 정상
            if actual_min * 0.9 <= stated <= actual_max * 1.1:
                log(f"[팩트체크] ✓ {claim['match']} — 범위 내 정상")
                continue

            if ratio > MISMATCH_THRESHOLD:
                new_text = _format_price_korean(actual_median)
                log(
                    f"[팩트체크] ✗ {claim['match']} → {new_text} "
                    f"(오차 {ratio:.0%})"
                )
                corrections.append({
                    "start": claim["start"], "end": claim["end"],
                    "old_text": claim["match"], "new_text": new_text,
                    "stated": stated, "actual": actual_median,
                    "ratio": ratio, "type": "price",
                })
            else:
                log(f"[팩트체크] △ {claim['match']} — 허용 범위 내 (오차 {ratio:.0%})")

    except Exception as e:
        log(f"[팩트체크] 검증 오류: {e} — 원본 반환")
        return FALLBACK
    finally:
        try:
            pw.stop()
        except Exception:
            pass

    corrected_body = _apply_corrections(body, corrections) if corrections else body
    if corrections:
        log(f"[팩트체크] {len(corrections)}건 수정 완료")
    else:
        log("[팩트체크] ✓ 모든 가격 정상")

    return {"body": corrected_body, "corrections": corrections, "checked": True}
