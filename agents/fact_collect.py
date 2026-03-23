"""사전 팩트 수집 — 글 생성 전 공식 사이트에서 최신 정보를 수집해 프롬프트에 주입"""
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from browser import connect_cdp, get_or_create_page

# ── 블로그별 키워드 라우팅 규칙 ─────────────────────────────────────────────
# 각 항목: (트리거 단어 리스트, 검색 URL 템플릿 or None)
# None이면 네이버 통합검색 사용
# {q} 자리에 URL 인코딩된 키워드가 들어감
_ROUTES = {
    # ── 살림/절약 블로그 ──
    "salim1su": [
        (["전기", "kWh", "kwh", "한전", "전력", "누진"],
         "https://www.kepco.co.kr/search/index.do?searchWord={q}"),
        (["가스", "도시가스", "난방", "보일러"],
         "https://www.kogas.or.kr/search/search.do?q={q}"),
        (["건강보험", "의료비", "병원비", "보험료", "건보"],
         "https://www.nhis.or.kr/search/search.do?q={q}"),
        (["국민연금", "연금", "노령연금"],
         "https://www.nps.or.kr/jsppage/search/total_search.jsp?q={q}"),
        (["수도", "상수도", "하수도", "물값"], None),   # 지자체별 → 네이버
        (["식비", "마트", "장보기", "식재료"], None),   # 네이버
    ],

    # ── IT/가전 블로그 ──
    "goodisak": [
        (["갤럭시", "삼성", "Galaxy", "galaxy"],
         "https://www.samsung.com/kr/search/?searchvalue={q}"),
        (["LG", "lg", "엘지", "그램", "올레드", "oled", "OLED"],
         "https://www.lg.com/kr/search/?query={q}"),
        (["아이폰", "맥북", "아이패드", "애플", "Apple", "apple", "iPhone", "MacBook"],
         "https://www.apple.com/kr/search/{q}?src=serp"),
        (["다나와", "최저가", "가격비교"],
         "https://search.danawa.com/dsearch.php?query={q}"),
        (["인텔", "AMD", "엔비디아", "CPU", "GPU", "RAM"],
         None),  # 네이버
    ],

    # ── 여행 블로그 ──
    "nolja100": [
        (["국립공원", "설악산", "지리산", "한라산", "북한산", "소백산", "태백산",
          "오대산", "내장산", "계룡산", "덕유산", "가야산", "월악산", "속리산",
          "치악산", "주왕산", "월출산", "변산반도", "다도해", "한려수도", "태안"],
         "https://www.knps.or.kr/portal/search/search.do?searchWord={q}"),
        (["제주", "jeju"],
         "https://www.jejutour.go.kr/contents/search.do?keyword={q}"),
        (["관광", "여행", "입장료", "운영시간", "축제", "명소", "관광지"],
         "https://korean.visitkorea.or.kr/search/search_list.do?keyword={q}"),
    ],

    # ── 복지 블로그 ──
    "baremi542": [
        (["실업급여", "고용보험", "육아휴직", "출산휴가", "고용"],
         "https://www.ei.go.kr/ei/eih/cm/hm/main.do"),  # 고용보험 → 키워드 검색 없이 메인만
        (["연금", "국민연금", "노령연금", "장애연금"],
         "https://www.nps.or.kr/jsppage/search/total_search.jsp?q={q}"),
        (["장애인", "장애", "바우처"],
         "https://www.bokjiro.go.kr/ssis-tbu/twataa/wlfareInfo/moveTWAT52011M.do?searchWord={q}"),
        # 기본: 복지로 검색
        ([], "https://www.bokjiro.go.kr/ssis-tbu/twataa/wlfareInfo/moveTWAT52011M.do?searchWord={q}"),
    ],
}

# 네이버 사용 시 추가할 보조 쿼리
_SEARCH_SUFFIX = {
    "salim1su": " 절약 방법",
    "goodisak":  " 스펙 가격",
    "nolja100":  " 여행정보 운영시간 입장료",
    "baremi542": " 지원금 신청방법",
}

# 네이버 결과에서 우선 방문할 공식 도메인
_PRIORITY_DOMAINS = {
    "salim1su": ["kepco.co.kr", "kogas.or.kr", "nhis.or.kr", "nps.or.kr", "gov.kr"],
    "goodisak":  ["samsung.com", "lg.com", "apple.com", "microsoft.com", "danawa.com"],
    "nolja100":  ["visitkorea.or.kr", "knps.or.kr", "tour.go.kr", "jejutour.go.kr"],
    "baremi542": ["bokjiro.go.kr", "ei.go.kr", "nps.or.kr", "mohw.go.kr"],
}

# 네이버 검색 결과 스니펫 셀렉터 (UI 버전별 대응)
_NAVER_SNIPPET_SEL = [
    "[class*='api_txt_lines']",
    "[class*='dsc_txt']",
    "[class*='total_dsc']",
    "[class*='news_dsc']",
    "[class*='slog_dsc']",
    "[class*='txt_inline']",
    ".total_wrap .api_txt_lines",
    ".total_wrap .dsc_txt",
    ".sh_blog_passage",
    ".total_area .dsc_txt_lines",
    ".news_dsc",
    "._slog_dsc",
]


def _clean(text):
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _resolve_url(keyword, blog_id):
    """키워드와 블로그 ID로 공식 검색 URL 결정. None이면 네이버 사용."""
    routes = _ROUTES.get(blog_id, [])
    q = urllib.parse.quote(keyword)
    for triggers, url_tpl in routes:
        # 트리거 없으면 기본값 (무조건 매칭)
        if not triggers or any(t in keyword for t in triggers):
            if url_tpl:
                return url_tpl.format(q=q)
            return None  # 명시적으로 네이버
    return None


def _fetch_url_direct(page, url, on_log=None):
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

    for sel in ["main", "article", "#content", ".content", ".result", "body"]:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                text = _clean(el.inner_text(timeout=3000))
                if len(text) > 200:
                    log(f"[팩트수집] 공식 사이트 {len(text)}자 수집")
                    return text[:3000]
        except Exception:
            continue
    return ""


def _search_naver(page, keyword, blog_id, on_log=None):
    """네이버 통합검색 스니펫 수집 + 우선 도메인 직접 방문."""
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

    for sel in _NAVER_SNIPPET_SEL:
        try:
            els = page.locator(sel)
            for i in range(min(els.count(), 5)):
                txt = _clean(els.nth(i).inner_text(timeout=2000))
                if txt and len(txt) > 30:
                    snippets.append(txt)
        except Exception:
            continue

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

    # 우선 도메인 발견 시 직접 방문
    for domain in _PRIORITY_DOMAINS.get(blog_id, []):
        try:
            link_el = page.locator(f'a[href*="{domain}"]').first
            if link_el.count() > 0:
                target_url = link_el.get_attribute("href")
                if target_url:
                    log(f"[팩트수집] 공식 페이지 방문: {target_url[:80]}")
                    page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(2000)
                    for sel in ["main", "article", "#content", "body"]:
                        try:
                            el = page.locator(sel).first
                            if el.count() > 0:
                                text = _clean(el.inner_text(timeout=3000))
                                if len(text) > 200:
                                    snippets.append(f"[공식 출처]\n{text[:2000]}")
                                    log(f"[팩트수집] 공식 페이지 {len(text)}자 수집")
                                    break
                        except Exception:
                            continue
                    break
        except Exception:
            continue

    return "\n\n".join(snippets)


def collect(keyword, blog_id, on_log=None):
    """글 생성 전 키워드 관련 최신 정보를 수집한다.

    Returns:
        {"context": str, "success": bool}
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
            direct_url = _resolve_url(keyword, blog_id)
            if direct_url:
                log(f"[팩트수집] 공식 사이트 라우팅: {direct_url[:70]}")
                raw_text = _fetch_url_direct(page, direct_url, on_log)
                if not raw_text or len(raw_text) < 200:
                    log("[팩트수집] 공식 사이트 결과 부족 — 네이버 폴백")
                    raw_text = _search_naver(page, keyword, blog_id, on_log)
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

    context_text = (
        f"## 아래는 '{keyword}' 관련 최신 공식 정보입니다. "
        f"반드시 이 정보를 기반으로 정확한 수치(금액·날짜·조건)를 작성하세요. "
        f"이 정보와 다른 내용을 쓰지 마세요.\n\n"
        f"{raw_text[:3000]}"
    )

    log(f"[팩트수집] ✓ 참고 자료 {len(context_text)}자 수집 완료")
    return {"context": context_text, "success": True}
