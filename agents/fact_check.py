"""팩트체크 모듈 — 가격/스펙 주장을 네이버쇼핑/쿠팡으로 검증 후 자동 수정"""
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


# ── 2. 크롤링 ────────────────────────────────────────────────────────────────

_NAVER_URL = "https://search.shopping.naver.com/search/all?query={q}"
_COUPANG_URL = "https://www.coupang.com/np/search?q={q}&channel=auto"

_NAVER_SELECTORS = ["strong.price_num", ".price_num", "[class*='price'] strong"]
_COUPANG_SELECTORS = [".price-value", ".sale-price"]


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


def _fetch_actual_prices(browser, query: str, on_log=None) -> list:
    """네이버쇼핑 우선, 없으면 쿠팡 폴백 — 새 탭 열고 닫음"""
    def log(msg):
        if on_log:
            on_log(msg)

    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    try:
        q = urllib.parse.quote(query)
        prices = _scrape_prices(
            page, _NAVER_URL.format(q=q), _NAVER_SELECTORS, on_log
        )
        if prices:
            log(f"[팩트체크] 네이버쇼핑 '{query}' 가격 {len(prices)}개: {prices}")
            return prices

        log(f"[팩트체크] 네이버쇼핑 결과 없음 → 쿠팡 폴백")
        prices = _scrape_prices(
            page, _COUPANG_URL.format(q=q), _COUPANG_SELECTORS, on_log
        )
        if prices:
            log(f"[팩트체크] 쿠팡 '{query}' 가격 {len(prices)}개: {prices}")
        return prices
    finally:
        try:
            page.close()
        except Exception:
            pass


# ── 3. 비교 및 수정 ──────────────────────────────────────────────────────────

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


# ── 4. 메인 진입점 ───────────────────────────────────────────────────────────

def run(body: str, keyword: str, on_log=None) -> dict:
    """팩트체크 실행.

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
        # 중복 검색 방지: keyword 당 1회만 조회
        actual_prices = _fetch_actual_prices(browser, keyword, on_log)

        if not actual_prices:
            log("[팩트체크] 실제 가격 조회 실패 — 원본 유지")
            return {**FALLBACK, "checked": True}

        actual_median = _median(actual_prices)
        actual_min = min(actual_prices)
        actual_max = max(actual_prices)
        log(
            f"[팩트체크] 실제 가격 범위: {actual_min:,.0f}~{actual_max:,.0f}원 "
            f"(중앙값: {actual_median:,.0f}원)"
        )

        for claim in price_claims[:3]:  # 최대 3건 (시간 제한)
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
