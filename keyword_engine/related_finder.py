"""pub코드로 연관 도메인 확장 — Naver 검색으로 같은 pub코드 사용 사이트 발견"""
import json
import os
import re
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

CLIENT_ID = os.environ.get("NAVER_SEARCH_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("NAVER_SEARCH_CLIENT_SECRET", "")

_TISTORY_ROOT = re.compile(r"(https?://[^/]+\.tistory\.com)")


def find_sites_by_pub_code(pub_code: str, on_log=None) -> set:
    """
    pub코드로 Naver 검색 → 같은 pub코드 사용하는 Tistory 사이트 추가 발굴

    pub_code: "ca-pub-1234567890123456"
    Returns: tistory 루트 URL set
    """
    match = re.search(r"(\d{14,})", pub_code)
    if not match or not CLIENT_ID:
        return set()

    number = match.group(1)
    query = f"ca-pub-{number}"
    found = set()

    for endpoint in ("webkr.json", "blog.json"):
        try:
            params = urllib.parse.urlencode({"query": query, "display": 100})
            req = urllib.request.Request(
                f"https://openapi.naver.com/v1/search/{endpoint}?{params}",
                headers={
                    "X-Naver-Client-Id": CLIENT_ID,
                    "X-Naver-Client-Secret": CLIENT_SECRET,
                },
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            for item in data.get("items", []):
                m = _TISTORY_ROOT.match(item.get("link", ""))
                if m:
                    found.add(m.group(1))
        except Exception as e:
            if on_log:
                on_log(f"[related_finder] {endpoint} 오류: {e}")
        time.sleep(0.2)

    if on_log and found:
        on_log(f"[related_finder] {pub_code} → 연관 {len(found)}개 사이트 발견")
    return found


def expand_by_pub_codes(pub_groups: dict, on_log=None) -> set:
    """
    pub코드 그룹에서 각 pub코드로 추가 사이트 검색 후 합집합 반환

    pub_groups: {pub_code: [url1, url2, ...]}
    Returns: 신규 발견된 tistory URL set
    """
    new_urls = set()
    # 2개 이상 사이트를 가진 pub코드 우선, 최대 5개 pub코드만 검색
    sorted_pubs = sorted(pub_groups.items(), key=lambda x: len(x[1]), reverse=True)
    for pub_code, sites in sorted_pubs[:5]:
        extra = find_sites_by_pub_code(pub_code, on_log=on_log)
        existing = set(sites)
        added = extra - existing
        if added:
            new_urls |= added
            if on_log:
                on_log(f"[related_finder] {pub_code}: 기존 {len(existing)}개 → +{len(added)}개 확장")
    return new_urls
