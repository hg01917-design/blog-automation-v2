"""사전 팩트 수집 — 글 생성 전 공식 사이트에서 최신 정보를 수집해 프롬프트에 주입"""
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from browser import connect_cdp, get_or_create_page

# 블로그별 직접 검색 URL (쿠팡 등 쇼핑 광고가 없는 공식 사이트 직접 검색)
# None이면 Naver 통합검색 사용
_DIRECT_SEARCH_URL = {
    "baremi542": "https://www.bokjiro.go.kr/ssis-tbu/twataa/wlfareInfo/moveTWAT52011M.do?searchWord={q}",
    "salim1su":  None,  # 키워드 기반 라우팅 (_resolve_salim1su_url 사용)
    "goodisak":  None,  # Naver 사용
    "nolja100":  None,  # Naver 사용
}

# salim1su 키워드 → 공식 사이트 라우팅 규칙
# (키워드, 검색 URL 템플릿) 순서대로 매칭
_SALIM1SU_ROUTES = [
    # 전기 관련
    (["전기", "kWh", "kwh", "한전", "전력", "누진"], "https://www.kepco.co.kr/search/index.do?searchWord={q}"),
    # 가스 관련
    (["가스", "도시가스", "난방", "보일러"], "https://www.kogas.or.kr/search/search.do?q={q}"),
    # 수도 관련
    (["수도", "상수도", "하수도", "물값"], None),  # 지자체별 → 네이버
    # 건강보험·의료비
    (["건강보험", "의료비", "병원비", "실비", "보험료"], "https://www.nhis.or.kr/search/search.do?q={q}"),
    # 식비·마트
    (["장보기", "식비", "마트", "식재료", "음식"], None),  # 네이버
]

# 검색에 추가할 블로그별 보조 쿼리 (Naver 사용 시)
_SEARCH_SUFFIX = {
    "salim1su": " 절약 방법",
    "goodisak": " 스펙 가격",
    "nolja100": " 여행정보 운영시간",
}

# Naver 사용 블로그에서 우선 찾을 도메인
_PRIORITY_DOMAINS = {
    "salim1su": [
        "kepco.co.kr", "kogas.or.kr", "nhis.or.kr",
        "energysaving.or.kr", "gov.kr",
    ],
    "goodisak": [
        "samsung.com", "lg.com", "apple.com", "microsoft.com",
        "danawa.com",
    ],
    "nolja100": [
        "visitkorea.or.kr", "knps.or.kr", "tour.go.kr",
        "korea.net", "jejutour.go.kr",
    ],
}


def _resolve_salim1su_url(keyword: str) -> str | None:
    """키워드를 보고 salim1su에 적합한 공식 검색 URL을 반환. 없으면 None(→ 네이버 사용)."""
    q = urllib.parse.quote(keyword)
    for triggers, url_tpl in _SALIM1SU_ROUTES:
        if any(t in keyword for t in triggers):
            if url_tpl:
                return url_tpl.format(q=q)
            return None  # 명시적으로 네이버 사용
    return None  # 기본값: 네이버

# 네이버 검색 결과에서 텍스트 추출 셀렉터 (UI 버전별 대응)
_NAVER_SNIPPET_SEL = [
    # 최신 버전
    "[class*='api_txt_lines']",
    "[class*='dsc_txt']",
    "[class*='total_dsc']",
    "[class*='news_dsc']",
    "[class*='slog_dsc']",
    "[class*='txt_inline']",
    # 구버전 폴백
    ".total_wrap .api_txt_lines",
    ".total_wrap .dsc_txt",
    ".sh_blog_passage",
    ".total_area .dsc_txt_lines",
    ".news_dsc",
    "._slog_dsc",
]


def _clean(text: str) -> str:
    """HTML 태그 및 중복 공백 제거"""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fetch_url_direct(page, url: str, on_log=None) -> str:
    """완성된 URL에 직접 접근해서 본문 텍스트 추출."""
    def log(msg):
        if on_log:
            on_log(msg)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)
    except Exception as e:
        log(f"[팩트수집] 직접 접근 실패: {e}")
        return ""

    for body_sel in ["main", "article", "#content", ".content", ".result", "body"]:
        try:
            el = page.locator(body_sel).first
            if el.count() > 0:
                body_text = _clean(el.inner_text(timeout=3000))
                if len(body_text) > 200:
                    log(f"[팩트수집] 텍스트 {len(body_text)}자 수집")
                    return body_text[:3000]
        except Exception:
            continue
    return ""


def _fetch_official_site(page, keyword: str, blog_id: str, on_log=None) -> str:
    """공식 사이트 직접 검색 (baremi542/salim1su 전용 — 쇼핑 광고 없는 정부 사이트)"""
    def log(msg):
        if on_log:
            on_log(msg)

    direct_url_tpl = _DIRECT_SEARCH_URL.get(blog_id)
    if not direct_url_tpl:
        return ""

    q = urllib.parse.quote(keyword)
    url = direct_url_tpl.format(q=q)

    log(f"[팩트수집] 공식 사이트 검색: {url[:80]}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)
    except Exception as e:
        log(f"[팩트수집] 공식 사이트 접근 실패: {e}")
        return ""

    body_text = ""
    for body_sel in ["main", "article", "#content", ".content", ".result", "body"]:
        try:
            el = page.locator(body_sel).first
            if el.count() > 0:
                body_text = _clean(el.inner_text(timeout=3000))
                if len(body_text) > 200:
                    break
        except Exception:
            continue

    if body_text:
        log(f"[팩트수집] 공식 사이트 텍스트 {len(body_text)}자 수집")
        return body_text[:3000]
    return ""


def _search_naver(page, keyword: str, blog_id: str, on_log=None) -> str:
    """네이버 통합검색에서 스니펫 텍스트 수집 (goodisak/nolja100 전용)"""
    def log(msg):
        if on_log:
            on_log(msg)

    suffix = _SEARCH_SUFFIX.get(blog_id, "")
    query = urllib.parse.quote(keyword + suffix)
    url = f"https://search.naver.com/search.naver?query={query}"

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
    except Exception as e:
        log(f"[팩트수집] 네이버 검색 실패: {e}")
        return ""

    snippets = []

    # 스니펫 텍스트 수집
    for sel in _NAVER_SNIPPET_SEL:
        try:
            els = page.locator(sel)
            count = min(els.count(), 5)
            for i in range(count):
                txt = _clean(els.nth(i).inner_text(timeout=2000))
                if txt and len(txt) > 30:
                    snippets.append(txt)
        except Exception:
            continue

    # 셀렉터 수집 실패 시 JS로 직접 텍스트 추출 (폴백)
    if not snippets:
        try:
            raw = page.evaluate("""() => {
                const blocks = document.querySelectorAll(
                    '[id*="sp_"] p, [class*="dsc"] p, [class*="desc"] p, ' +
                    '[class*="summary"], [class*="snippet"], [class*="txt"] p, ' +
                    '.news_area p, .blog_area p, .kin_area p'
                );
                return Array.from(blocks)
                    .map(el => el.innerText.trim())
                    .filter(t => t.length > 30)
                    .slice(0, 10)
                    .join('\\n\\n');
            }""")
            if raw and len(raw) > 50:
                snippets.append(raw)
                log(f"[팩트수집] JS 폴백으로 {len(raw)}자 수집")
        except Exception:
            pass

    # 우선 도메인 링크 발견 시 해당 페이지 접근
    priority_domains = _PRIORITY_DOMAINS.get(blog_id, [])
    if priority_domains and snippets:
        try:
            # 특정 도메인을 포함하는 링크만 직접 셀렉터로 찾기
            for domain in priority_domains:
                try:
                    link_el = page.locator(f'a[href*="{domain}"]').first
                    if link_el.count() > 0:
                        target_url = link_el.get_attribute("href")
                        if target_url:
                            log(f"[팩트수집] 공식 페이지: {target_url[:80]}")
                            page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                            page.wait_for_timeout(2000)
                            for body_sel in ["main", "article", "#content", "body"]:
                                try:
                                    el = page.locator(body_sel).first
                                    if el.count() > 0:
                                        body_text = _clean(el.inner_text(timeout=3000))
                                        if len(body_text) > 200:
                                            snippets.append(f"[공식 출처]\n{body_text[:2000]}")
                                            log(f"[팩트수집] 공식 페이지 {len(body_text)}자 수집")
                                            break
                                except Exception:
                                    continue
                            break
                except Exception:
                    continue
        except Exception as e:
            log(f"[팩트수집] 공식 페이지 접근 실패: {e}")

    return "\n\n".join(snippets)


def collect(keyword: str, blog_id: str, on_log=None) -> dict:
    """글 생성 전 키워드 관련 최신 정보를 수집한다.

    Args:
        keyword: 작성할 글의 메인 키워드
        blog_id: 블로그 ID

    Returns:
        {"context": str, "success": bool}
        context: 프롬프트에 주입할 참고 자료 텍스트
    """
    def log(msg):
        if on_log:
            on_log(msg)

    log(f"[팩트수집] '{keyword}' 사전 정보 수집 시작")

    try:
        pw, browser = connect_cdp(on_log)
    except Exception as e:
        log(f"[팩트수집] CDP 연결 실패: {e} — 건너뜀")
        return {"context": "", "success": False}

    try:
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        try:
            # salim1su: 키워드 기반으로 공식 사이트 URL 결정
            if blog_id == "salim1su":
                direct_url = _resolve_salim1su_url(keyword)
                if direct_url:
                    log(f"[팩트수집] 공식 사이트 라우팅: {direct_url[:60]}")
                    raw_text = _fetch_url_direct(page, direct_url, on_log)
                    # 결과 부족 시 네이버로 폴백
                    if not raw_text or len(raw_text) < 200:
                        log("[팩트수집] 공식 사이트 결과 부족 — 네이버 폴백")
                        raw_text = _search_naver(page, keyword, blog_id, on_log)
                else:
                    raw_text = _search_naver(page, keyword, blog_id, on_log)
            # baremi542: 고정 공식 사이트 직접 검색
            elif _DIRECT_SEARCH_URL.get(blog_id):
                raw_text = _fetch_official_site(page, keyword, blog_id, on_log)
            else:
                raw_text = _search_naver(page, keyword, blog_id, on_log)
        finally:
            try:
                page.close()
            except Exception:
                pass
    except Exception as e:
        log(f"[팩트수집] 수집 오류: {e}")
        raw_text = ""
    finally:
        try:
            pw.stop()
        except Exception:
            pass

    if not raw_text.strip():
        log("[팩트수집] 수집된 정보 없음 — 건너뜀")
        return {"context": "", "success": False}

    # 프롬프트 주입용 텍스트 조립
    context_text = (
        f"## 아래는 '{keyword}' 관련 최신 공식 정보입니다. "
        f"반드시 이 정보를 기반으로 정확한 수치(금액·날짜·조건)를 작성하세요. "
        f"이 정보와 다른 내용을 쓰지 마세요.\n\n"
        f"{raw_text[:3000]}"
    )

    log(f"[팩트수집] ✓ 참고 자료 {len(context_text)}자 수집 완료")
    return {"context": context_text, "success": True}
