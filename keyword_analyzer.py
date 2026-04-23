"""Naver 블로그 키워드 분석 — 경쟁도 / 연관키워드 / SEO 제목 생성

사용:
    from keyword_analyzer import analyze_keyword, generate_titles
    result = analyze_keyword("인천공항 주차장 요금")
    titles = generate_titles("인천공항 주차장 할인", "woll100")
"""
import os
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

# .env 로드 (PyInstaller 번들 대응: BLOG_AUTO_PROJECT_ROOT 우선)
_env = Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent))) / ".env"
if not _env.exists():
    _env = Path.home() / "Downloads" / "blog-automation-v2" / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

_CLIENT_ID = os.environ.get("NAVER_SEARCH_CLIENT_ID", "")
_CLIENT_SECRET = os.environ.get("NAVER_SEARCH_CLIENT_SECRET", "")

_NAVER_BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"
_NAVER_AC_URL   = "https://ac.search.naver.com/nx/ac"


def _naver_headers() -> dict:
    return {
        "X-Naver-Client-Id": _CLIENT_ID,
        "X-Naver-Client-Secret": _CLIENT_SECRET,
        "User-Agent": "Mozilla/5.0",
    }


def get_blog_count(keyword: str) -> int:
    """네이버 블로그 검색 결과 수 (경쟁도 지표)."""
    if not _CLIENT_ID:
        return -1
    try:
        url = f"{_NAVER_BLOG_URL}?query={urllib.parse.quote(keyword)}&display=1"
        req = urllib.request.Request(url, headers=_naver_headers())
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        return data.get("total", 0)
    except Exception:
        return -1


def difficulty_label(total: int) -> str:
    """발행량 → 난이도 텍스트."""
    if total < 0:
        return "확인불가"
    if total < 3000:
        return "매우 낮음 ✅✅"
    if total < 10000:
        return "낮음 ✅"
    if total < 50000:
        return "보통 ⚠️"
    return "높음 ❌"


def get_autocomplete(keyword: str) -> list[str]:
    """네이버 자동완성으로 연관 키워드 수집."""
    try:
        url = f"{_NAVER_AC_URL}?query={urllib.parse.quote(keyword)}&con=1&frm=nv&ans=2&type=people"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        results = []
        for group in data.get("items", []):
            for item in group:
                if isinstance(item, list) and item:
                    results.append(item[0])
        return list(dict.fromkeys(results))[:15]  # 중복 제거, 최대 15개
    except Exception:
        return []


def get_related_from_search(keyword: str) -> list[str]:
    """자동완성 실패 시 네이버 블로그 검색 제목에서 연관 키워드 추출."""
    if not _CLIENT_ID:
        return []
    try:
        url = f"{_NAVER_BLOG_URL}?query={urllib.parse.quote(keyword)}&display=10&sort=sim"
        req = urllib.request.Request(url, headers=_naver_headers())
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        import re
        titles = [item.get("title", "") for item in data.get("items", [])]
        # HTML 태그 제거 후 단어 추출
        words = []
        for t in titles:
            clean = re.sub(r"<[^>]+>", "", t)
            parts = re.findall(r"[가-힣]{2,6}", clean)
            words.extend(parts)
        # keyword 토큰 제거 후 빈도순 정렬
        kw_tokens = set(keyword.split())
        freq: dict[str, int] = {}
        for w in words:
            if w not in kw_tokens and w != keyword:
                freq[w] = freq.get(w, 0) + 1
        sorted_words = sorted(freq, key=lambda x: -freq[x])
        # keyword + 자주 나온 단어 조합으로 후보 키워드 생성
        candidates = []
        for w in sorted_words[:8]:
            candidates.append(f"{keyword} {w}")
        return candidates[:10]
    except Exception:
        return []


def analyze_keyword(keyword: str, on_log=None) -> dict:
    """키워드 전체 분석: 경쟁도 + 연관키워드 각각 경쟁도 체크.

    Returns:
        {
            "keyword": str,
            "total": int,
            "level": str,
            "related": [{"keyword": str, "total": int, "level": str}, ...],
        }
    """
    def log(msg):
        if on_log:
            on_log(msg)

    log(f"[분석] '{keyword}' 경쟁도 조회 중...")
    main_total = get_blog_count(keyword)
    log(f"[분석] 발행량: {main_total:,}개 → {difficulty_label(main_total)}")

    log(f"[분석] 연관 키워드 수집 중...")
    related_kws = get_autocomplete(keyword)
    if not related_kws:
        log(f"[분석] 자동완성 결과 없음 → 블로그 검색 결과로 대체 수집 중...")
        related_kws = get_related_from_search(keyword)
    log(f"[분석] 연관 키워드 {len(related_kws)}개 발견")

    related = []
    for kw in related_kws:
        if kw == keyword:
            continue
        total = get_blog_count(kw)
        related.append({
            "keyword": kw,
            "total": total,
            "level": difficulty_label(total),
        })
        time.sleep(0.1)  # API 부하 방지

    # 발행량 오름차순 정렬 (경쟁 낮은 게 위로)
    related.sort(key=lambda x: x["total"] if x["total"] >= 0 else 999999)

    return {
        "keyword": keyword,
        "total": main_total,
        "level": difficulty_label(main_total),
        "related": related,
    }


# ── 블로그별 타겟 난이도 기준 ──────────────────────────────────────────────
_BLOG_TARGET = {
    "nolja100":   {"max_total": 30000, "label": "여행 블로그 (nolja100) — 3만 이하 권장"},
    "triplog":    {"max_total": 30000, "label": "여행 블로그 (triplog) — 3만 이하 권장"},
    "salim1su":   {"max_total": 50000, "label": "살림 블로그 (salim1su) — 5만 이하 권장"},
    "goodisak":   {"max_total": 20000, "label": "IT 블로그 (goodisak) — 2만 이하 권장"},
    "woll100":    {"max_total": 15000, "label": "교통 블로그 (woll100) — 1.5만 이하 권장"},
    "baremi542":  {"max_total": 50000, "label": "정부지원 블로그 — 5만 이하 권장"},
    "phn0502":    {"max_total": 10000, "label": "영화 블로그 (phn0502) — 1만 이하 권장"},
    "me1091":     {"max_total": 20000, "label": "쿠팡리뷰 블로그 (me1091) — 2만 이하 권장"},
}

_BLOG_THEME = {
    "nolja100":  "국내외 여행지·숙소·관광지",
    "triplog":   "해외여행 숙소·투어·맛집",
    "salim1su":  "살림·절약·가사·주방",
    "goodisak":  "IT·전자기기·금융·앱",
    "woll100":   "교통·버스·KTX·공항·요금",
    "baremi542": "정부지원금·복지·혜택",
    "phn0502":   "영화·OTT·드라마 리뷰",
    "me1091":    "쿠팡 상품 리뷰·추천",
}


def filter_by_blog(related: list[dict], blog_id: str) -> list[dict]:
    """블로그 수준에 맞는 키워드만 필터링."""
    cfg = _BLOG_TARGET.get(blog_id)
    if not cfg:
        return related
    return [r for r in related if 0 <= r["total"] <= cfg["max_total"]]


def generate_titles(keyword: str, blog_id: str, on_log=None) -> list[str]:
    """Claude Haiku로 SEO 제목 5개 생성.

    Returns:
        list[str]: 제목 후보 최대 5개
    """
    def log(msg):
        if on_log:
            on_log(msg)

    theme = _BLOG_THEME.get(blog_id, "블로그")
    is_naver = blog_id in ("salim1su", "me1091")
    title_len = "20~35자" if is_naver else "30~55자"

    prompt = (
        f"[출력 규칙] 아래 요청에 대해 제목 후보 5개만 출력. 번호 없이 한 줄에 하나씩. 설명 금지.\n\n"
        f"블로그 주제: {theme}\n"
        f"타겟 키워드: {keyword}\n"
        f"제목 조건:\n"
        f"- 길이: {title_len}\n"
        f"- 키워드를 제목 앞쪽에 정확히 포함\n"
        f"- 구체적 수치·연도(2026)·'방법','가격','후기','비교' 중 하나 포함\n"
        f"- AI 클리셰('완벽정리','한눈에','꼼꼼히') 절대 금지\n"
        f"- 검색자가 실제로 검색할 법한 자연스러운 표현\n\n"
        f"제목 5개:"
    )

    try:
        from claude_direct import _run_claude, _FORMAT_ENFORCE_PREFIX
        raw = _run_claude(prompt, on_log=on_log, timeout=60)
        lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
        # 번호/기호 제거
        import re
        titles = []
        for line in lines:
            line = re.sub(r'^[\d\.\-\*\#\s]+', '', line).strip()
            if 5 < len(line) < 80:
                titles.append(line)
        log(f"[분석] 제목 {len(titles)}개 생성 완료")
        return titles[:5]
    except Exception as e:
        log(f"[분석] 제목 생성 실패: {e}")
        return []
