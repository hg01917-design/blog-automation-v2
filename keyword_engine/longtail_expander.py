"""롱테일 키워드 확장기
경쟁사 제목에서 뽑은 기본 키워드 → 네이버 자동완성 + 연관검색어 → 롱테일 저장

흐름:
  base_keyword (예: "속초여행")
      ↓ 네이버 자동완성 API (HTTP)
      ["속초여행 코스", "속초여행 1박2일 추천", ...]
      ↓ 네이버 검색 연관검색어 (Playwright)
      ["속초여행지 추천 코스", "속초 뚜벅이 당일치기", ...]
      ↓ 롱테일 필터 (공백 포함 2어절 이상 + 기본 키워드보다 길게)
      ↓ DB 저장 (upsert_keyword)
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
import os
import sys

# 프로젝트 루트 기준 .env 로드
_root = Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent.parent)))
_env = _root / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


# ── 네이버 자동완성 API (HTTP, Playwright 불필요) ──────────────────────
def _naver_autocomplete(keyword: str) -> list[str]:
    """네이버 자동완성 API로 제안 키워드 수집"""
    q = urllib.parse.quote(keyword)
    url = (
        f"https://ac.search.naver.com/nx/ac"
        f"?q={q}&q_enc=UTF-8&st=100&frm=nv"
        f"&r_format=json&r_enc=UTF-8&r_unicode=0&t_koreng=1&ans=2&run=2&rev=4"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = json.loads(urllib.request.urlopen(req, timeout=8).read())
        results = []
        for group in data.get("items", []):
            for item in group:
                if isinstance(item, list) and item:
                    results.append(str(item[0]).strip())
                elif isinstance(item, str):
                    results.append(item.strip())
        return [r for r in results if r]
    except Exception:
        return []


# ── 네이버 연관검색어 (Playwright) ──────────────────────────────────────
def _naver_related_search(keyword: str, on_log=None) -> list[str]:
    """네이버 검색결과 페이지에서 연관검색어 수집 (Playwright CDP)"""
    try:
        sys.path.insert(0, str(_root))
        from poster import connect_cdp
    except ImportError:
        return []

    results = []
    pw, browser = connect_cdp(on_log=on_log)
    try:
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        q = urllib.parse.quote(keyword)
        page.goto(
            f"https://search.naver.com/search.naver?where=nexearch&query={q}",
            wait_until="domcontentloaded",
            timeout=20000,
        )
        time.sleep(2)

        # 연관검색어 셀렉터 (네이버 UI 버전별 대응)
        raw = page.evaluate("""() => {
            const selectors = [
                '.related_srch .keyword',
                '.lst_related_srch .item_keyword',
                'a.relate_kwd',
                '.related_keywords a',
                '[class*=related] a',
            ];
            for (const sel of selectors) {
                const items = [...document.querySelectorAll(sel)];
                if (items.length > 0) {
                    return items.map(el => el.innerText.trim()).filter(t => t);
                }
            }
            return [];
        }""")
        results = raw if raw else []
        page.close()
    except Exception as e:
        if on_log:
            on_log(f"[롱테일] 연관검색어 수집 오류: {e}")
    finally:
        pw.stop()

    return results


# ── 롱테일 필터 ──────────────────────────────────────────────────────────
def _is_longtail(keyword: str, base: str) -> bool:
    """롱테일 여부 판단: 기본 키워드보다 길고, 공백 포함 2어절 이상"""
    kw = keyword.strip()
    if len(kw) <= len(base):
        return False
    words = kw.split()
    if len(words) < 2:
        return False
    # 광고성/무관 패턴 제외
    _SKIP = re.compile(r"(쇼핑|광고|구매|구입|가격비교|사이트|앱다운|공식)")
    if _SKIP.search(kw):
        return False
    return True


# ── 메인 함수 ─────────────────────────────────────────────────────────────
def expand_longtail(
    base_keywords: list[str],
    category: str = "",
    blog_id: str = None,
    top_n: int = 5,
    on_log=None,
) -> int:
    """
    base_keywords를 네이버 자동완성 + 연관검색어로 확장해 DB에 저장.

    Args:
        base_keywords: 기본 키워드 목록
        category: DB 카테고리 ('여행', '살림', '정부지원금', 'IT' 등)
        blog_id: 포화 체크용 (선택)
        top_n: 기본 키워드 중 상위 N개만 처리 (Playwright 부하 제한)
        on_log: 로그 콜백

    Returns:
        새로 저장된 롱테일 키워드 수
    """
    from keyword_engine.db_handler import upsert_keyword, keyword_exists

    def log(msg):
        if on_log:
            on_log(msg)

    saved = 0
    processed_bases = set()

    for base in base_keywords[:top_n]:
        base = base.strip()
        if not base or base in processed_bases:
            continue
        processed_bases.add(base)

        log(f"[롱테일] '{base}' 확장 시작")

        candidates = []

        # 1. 자동완성 (HTTP — 빠름)
        ac = _naver_autocomplete(base)
        candidates.extend(ac)
        log(f"[롱테일] 자동완성 {len(ac)}개: {ac[:5]}")
        time.sleep(0.5)

        # 2. 연관검색어 (Playwright — 한 번만 실행, 부하 큰 키워드에만)
        if len(base.split()) <= 1:  # 단어 1개짜리 기본 키워드만
            related = _naver_related_search(base, on_log=on_log)
            candidates.extend(related)
            log(f"[롱테일] 연관검색어 {len(related)}개: {related[:5]}")

        # 3. 롱테일 필터 + 중복 제거
        longtails = []
        seen = set()
        for kw in candidates:
            kw = kw.strip()
            if kw and kw not in seen and _is_longtail(kw, base):
                seen.add(kw)
                longtails.append(kw)

        log(f"[롱테일] '{base}' → 롱테일 {len(longtails)}개 추출")

        # 4. DB 저장 (기존 키워드 덮어쓰기 X, 신규만)
        for kw in longtails:
            if not keyword_exists(kw):
                upsert_keyword(
                    keyword=kw,
                    score=50.0,       # 기본 점수 (경쟁사 제목 키워드와 동일 수준)
                    volume=0,
                    pub_count=1,
                    category=category,
                    blog_id=blog_id,
                )
                saved += 1

        time.sleep(1)

    log(f"[롱테일] 총 {saved}개 신규 롱테일 키워드 저장 완료")
    return saved
