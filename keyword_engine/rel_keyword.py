"""네이버 검색광고 API — keywordstool (relKeyword) 연동

엔드포인트: GET https://api.naver.com/keywordstool
인증: X-Timestamp / X-API-KEY / X-Customer / X-Signature (HMAC-SHA256)
"""
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

_root = Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent.parent)))
_env = _root / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

_API_KEY = os.environ.get("NAVER_API_KEY", "")
_SECRET_KEY = os.environ.get("NAVER_SECRET_KEY", "")  # base64 인코딩된 값
_CUSTOMER_ID = os.environ.get("NAVER_CUSTOMER_ID", "")
_BASE_URL = "https://api.searchad.naver.com"
_URI = "/keywordstool"

# SECRET_KEY는 raw 문자열을 UTF-8 바이트로 사용 (keyword_scorer.py 방식과 동일)
_SECRET_BYTES = _SECRET_KEY.encode("utf-8") if _SECRET_KEY else b""


def _parse_vol(val) -> int:
    """'< 10' 같은 문자열 응답도 정수로 변환"""
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip().replace(",", "")
    if s.startswith("<"):
        return 5  # "< 10" → 5로 처리
    try:
        return int(s)
    except Exception:
        return 0


def _sign(timestamp: str) -> str:
    """HMAC-SHA256 서명 생성"""
    message = f"{timestamp}.GET.{_URI}"
    sig = hmac.new(_SECRET_BYTES, message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(sig).decode("utf-8")


def get_rel_keywords(
    seeds: list,
    min_vol: int = 100,
    max_vol: int = 3000,
    on_log=None,
) -> list:
    """
    네이버 검색광고 keywordstool API로 연관키워드 조회.

    Args:
        seeds: 힌트 키워드 목록 (최대 5개 사용)
        min_vol: 최소 월간 검색량 (PC+모바일 합산)
        max_vol: 최대 월간 검색량
        on_log: 로그 콜백

    Returns:
        [{"keyword": str, "total_vol": int, "pc_vol": int, "mobile_vol": int}, ...]
        min_vol ≤ total_vol ≤ max_vol 범위만 포함, total_vol 내림차순 정렬
    """
    if not (_API_KEY and _SECRET_BYTES and _CUSTOMER_ID):
        if on_log:
            on_log("[relKeyword] API 키 미설정 — 자동완성 폴백 사용")
        return []

    # 키워드 내 공백 제거 후 쉼표로 합치기 (keyword_scorer.py 방식과 동일)
    hint = ",".join(s.replace(" ", "") for s in seeds[:5])
    timestamp = str(int(time.time() * 1000))
    params = urllib.parse.urlencode({"hintKeywords": hint, "showDetail": "1"})
    headers = {
        "X-Timestamp": timestamp,
        "X-API-KEY": _API_KEY,
        "X-Customer": _CUSTOMER_ID,
        "X-Signature": _sign(timestamp),
    }

    try:
        req = urllib.request.Request(
            f"{_BASE_URL}{_URI}?{params}",
            headers=headers,
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        if on_log:
            on_log(f"[relKeyword] API 오류: {e}")
        return []

    results = []
    for item in data.get("keywordList", []):
        kw = item.get("relKeyword", "").strip()
        if not kw:
            continue
        pc = _parse_vol(item.get("monthlyPcQcCnt", 0))
        mobile = _parse_vol(item.get("monthlyMobileQcCnt", 0))
        total = pc + mobile
        if min_vol <= total <= max_vol:
            results.append({
                "keyword": kw,
                "total_vol": total,
                "pc_vol": pc,
                "mobile_vol": mobile,
            })

    # 검색량 내림차순 정렬
    results.sort(key=lambda x: x["total_vol"], reverse=True)

    if on_log:
        on_log(f"[relKeyword] seeds={seeds[:3]} → {len(results)}개 ({min_vol}~{max_vol})")
    return results
