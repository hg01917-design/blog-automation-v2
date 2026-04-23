"""
datalab_trend.py — 네이버 DataLab 트렌드 점수
rising trend → score 최대 1.5배
falling trend → score 최소 0.7배
"""
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

_root = Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent.parent)))
_env = _root / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

CLIENT_ID = os.environ.get("NAVER_DATALAB_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("NAVER_DATALAB_CLIENT_SECRET", "")

def get_trend_multiplier(keyword: str) -> float:
    """DataLab 트렌드로 점수 배수 반환. API 실패 시 1.0 반환."""
    if not CLIENT_ID or not CLIENT_SECRET:
        return 1.0

    # 최근 3개월 vs 이전 3개월 비교
    today = datetime.now()
    end_date = today.strftime("%Y-%m-%d")
    start_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")

    body = json.dumps({
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "month",
        "keywordGroups": [{"groupName": "keyword", "keywords": [keyword[:20]]}]
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "https://openapi.naver.com/v1/datalab/search",
            data=body,
            headers={
                "X-Naver-Client-Id": CLIENT_ID,
                "X-Naver-Client-Secret": CLIENT_SECRET,
                "Content-Type": "application/json",
            }
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
        results = resp.get("results", [])
        if not results:
            return 1.0

        data = results[0].get("data", [])
        if len(data) < 2:
            return 1.0

        # 최근 달 vs 첫 달 비교
        recent = data[-1].get("ratio", 50)
        oldest = data[0].get("ratio", 50)

        if oldest == 0:
            return 1.0

        trend_ratio = recent / oldest

        # 배수 계산
        if trend_ratio >= 1.5:
            return 1.5   # 급상승
        elif trend_ratio >= 1.2:
            return 1.3   # 상승
        elif trend_ratio >= 0.9:
            return 1.0   # 안정
        elif trend_ratio >= 0.6:
            return 0.85  # 하락
        else:
            return 0.7   # 급하락

    except Exception:
        return 1.0  # API 실패 시 중립
