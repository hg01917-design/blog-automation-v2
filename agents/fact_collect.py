"""사전 팩트 수집 — 글 생성 전 공식 사이트에서 최신 정보를 수집해 프롬프트에 주입"""
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from browser import connect_cdp, get_or_create_page

# 블로그별 우선 검색 도메인 (검색 결과에서 이 도메인 링크 우선 추출)
_PRIORITY_DOMAINS = {
    "baremi542": [
        "bokjiro.go.kr", "gov.kr", "korea.kr", "moel.go.kr",
        "nts.go.kr", "hometax.go.kr", "molit.go.kr", "mohw.go.kr",
    ],
    "salim1su": [
        "bokjiro.go.kr", "gov.kr", "kepco.co.kr", "kogas.or.kr",
        "korea.kr", "mohw.go.kr",
    ],
    "goodisak": [
        "samsung.com", "lg.com", "apple.com", "microsoft.com",
        "naver.com", "danawa.com",
    ],
    "nolja100": [
        "visitkorea.or.kr", "knps.or.kr", "tour.go.kr",
        "korea.net", "jejutour.go.kr",
    ],
}

# 검색에 추가할 블로그별 보조 쿼리
_SEARCH_SUFFIX = {
    "baremi542": " 신청방법 지원금액",
    "salim1su": " 신청방법 혜택",
    "goodisak": " 스펙 가격",
    "nolja100": " 여행정보 운영시간",
}

# 네이버 검색 결과에서 텍스트 추출 셀렉터
_NAVER_SNIPPET_SEL = [
    ".total_wrap .api_txt_lines",   # 통합검색 본문 발췌
    ".total_wrap .dsc_txt",
    ".sh_blog_passage",             # 블로그 발췌
    ".total_area .dsc_txt_lines",
    ".news_dsc",                    # 뉴스 요약
    "._slog_dsc",
]


def _clean(text: str) -> str:
    """HTML 태그 및 중복 공백 제거"""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _search_naver(page, keyword: str, blog_id: str, on_log=None) -> str:
    """네이버 통합검색에서 스니펫 텍스트 수집"""
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

    # 1. 스니펫 텍스트 수집
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

    # 2. 우선 도메인 링크 발견 시 해당 페이지 접근해서 본문 추출
    priority_domains = _PRIORITY_DOMAINS.get(blog_id, [])
    if priority_domains:
        try:
            links = page.locator("a[href]").all()
            target_url = None
            for link in links[:30]:
                try:
                    href = link.get_attribute("href") or ""
                    if any(d in href for d in priority_domains):
                        target_url = href
                        break
                except Exception:
                    continue

            if target_url:
                log(f"[팩트수집] 공식 페이지 접근: {target_url[:80]}")
                page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)

                # 본문 텍스트 추출 (최대 2000자)
                body_text = ""
                for body_sel in ["main", "article", "#content", ".content", "body"]:
                    try:
                        el = page.locator(body_sel).first
                        if el.count() > 0:
                            body_text = _clean(el.inner_text(timeout=3000))
                            if len(body_text) > 200:
                                break
                    except Exception:
                        continue

                if body_text:
                    snippets.append(f"[공식 출처 발췌]\n{body_text[:2000]}")
                    log(f"[팩트수집] 공식 페이지 텍스트 {len(body_text)}자 수집")
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
