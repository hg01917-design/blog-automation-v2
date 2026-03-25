"""키워드 점수 계산 — 기회점수 = 검색량² / (발행량 + 검색량)"""
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

# .env 로드
_env = Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent.parent))) / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

AD_API_KEY = os.environ.get("NAVER_API_KEY", "")
AD_SECRET_KEY = os.environ.get("NAVER_SECRET_KEY", "")
AD_CUSTOMER_ID = os.environ.get("NAVER_CUSTOMER_ID", "")


def _signature(timestamp: str, method: str, uri: str) -> str:
    msg = f"{timestamp}.{method}.{uri}"
    sig = hmac.new(
        AD_SECRET_KEY.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(sig).decode()


def _resolve_keys():
    """숫자=Customer ID, 긴 문자열=API Key 자동 판별"""
    api, cid = AD_API_KEY, AD_CUSTOMER_ID
    if AD_API_KEY.isdigit() and not AD_CUSTOMER_ID.isdigit():
        api, cid = AD_CUSTOMER_ID, AD_API_KEY
    return api, cid


def get_search_volume(keyword: str) -> int:
    """네이버 검색광고 API로 월간 검색량 조회 (PC + 모바일)"""
    if not AD_API_KEY or not AD_SECRET_KEY or not AD_CUSTOMER_ID:
        return 0

    api_key, cid = _resolve_keys()
    ts = str(int(time.time() * 1000))
    uri = "/keywordstool"
    hint = keyword.replace(" ", "")
    params = urllib.parse.urlencode({"hintKeywords": hint, "showDetail": "1"})

    req = urllib.request.Request(
        f"https://api.searchad.naver.com{uri}?{params}",
        headers={
            "X-Timestamp": ts,
            "X-API-KEY": api_key,
            "X-Customer": cid,
            "X-Signature": _signature(ts, "GET", uri),
        },
    )
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        for item in data.get("keywordList", []):
            if item.get("relKeyword", "").replace(" ", "") == hint:
                pc = int(item.get("monthlyPcQcCnt", 0) or 0)
                mob = int(item.get("monthlyMobileQcCnt", 0) or 0)
                return pc + mob
        # 정확한 매칭 없으면 첫 번째 결과 사용
        first = (data.get("keywordList") or [{}])[0]
        if first:
            pc = int(first.get("monthlyPcQcCnt", 0) or 0)
            mob = int(first.get("monthlyMobileQcCnt", 0) or 0)
            return pc + mob
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return 0
    except Exception:
        pass
    return 0


def opportunity_score(volume: int, pub_count: int) -> float:
    """기회점수 = 검색량² / (발행량 + 검색량)"""
    denom = pub_count + volume
    return (volume ** 2) / denom if denom > 0 else 0


def score_keywords(keywords: list, get_pub_count_fn, on_log=None) -> list:
    """
    키워드 리스트 점수 계산

    Returns:
        [{"keyword", "score", "volume", "pub_count"}, ...] 점수 내림차순
    """
    results = []
    for kw in keywords:
        volume = get_search_volume(kw)
        time.sleep(0.3)
        pub_count = get_pub_count_fn(kw)
        score = opportunity_score(volume, pub_count)
        results.append({
            "keyword": kw,
            "score": score,
            "volume": volume,
            "pub_count": pub_count,
        })
        if on_log:
            on_log(
                f"[scorer] {kw}: 검색량={volume:,}  발행량={pub_count:,}  점수={score:,.0f}"
            )
    return sorted(results, key=lambda x: x["score"], reverse=True)
