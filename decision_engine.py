"""
decision_engine.py
판단 엔진 — GSC 패턴 분석 + 키워드 확장 + CTR 낮은 글 제목 수정 + 발행량 조정
overnight_run.py에서 라운드 시작 전 호출
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
KST = timezone(timedelta(hours=9))


def _log(msg: str, on_log=None):
    if on_log:
        on_log(msg)
    else:
        print(msg, flush=True)


# ── 1. 잘 되는 글 패턴 → 유사 키워드 확장 ─────────────────────────────────

def expand_from_rising_pages(on_log=None) -> int:
    """급상승 페이지 감지 → 유사 키워드 DB 추가"""
    try:
        from keyword_engine.gsc_connector import generate_keywords_from_gsc
        added = generate_keywords_from_gsc(on_log=on_log)
        if added:
            _log(f"[판단엔진] 급상승 패턴에서 키워드 {added}개 추가", on_log)
        return added
    except Exception as e:
        _log(f"[판단엔진] 키워드 확장 오류: {e}", on_log)
        return 0


# ── 2. CTR 낮은 글 제목 수정 ─────────────────────────────────────────────

def _fetch_html_title(url: str) -> str:
    """URL 페이지에서 <title> 태그 파싱"""
    import ssl, urllib.request, re as _re
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=10, context=ctx).read().decode("utf-8", errors="ignore")
        m = _re.search(r'<title[^>]*>([^<]+)</title>', html, _re.IGNORECASE)
        if m:
            title = m.group(1).strip()
            # 사이트명 suffix 제거 (| 또는 – 뒤)
            title = _re.split(r'\s*[|–—]\s*', title)[0].strip()
            return title
    except Exception:
        pass
    return ""


def _generate_ctr_title(current_title: str, blog_id: str, slug: str = "") -> str:
    """Claude로 CTR 개선 제목 생성"""
    import subprocess, os
    from pathlib import Path

    CLAUDE_BIN = Path.home() / ".local" / "bin" / "claude"
    BASE_DIR = Path(__file__).parent

    prompt = (
        f"아래 블로그 글 제목의 검색 노출 대비 클릭률(CTR)이 낮습니다. "
        f"SEO 최적화와 클릭률을 높이도록 제목을 개선해주세요.\n\n"
        f"블로그: {blog_id}\n"
        f"현재 제목: {current_title}\n"
        f"URL 키워드: {slug}\n\n"
        f"규칙:\n"
        f"- 핵심 키워드를 제목 맨 앞에 배치\n"
        f"- 30~55자 이내\n"
        f"- 숫자·연도(2026)·구체적 정보 포함\n"
        f"- 구어체 금지, 명사형 마무리\n"
        f"- '방법', '총정리', '비교', '완벽정리', '가이드' 중 하나 포함\n"
        f"- 현재 제목보다 클릭하고 싶어지는 제목으로\n\n"
        f"개선된 제목만 한 줄로 출력 (설명 없이):"
    )
    try:
        result = subprocess.run(
            [str(CLAUDE_BIN), "--dangerously-skip-permissions", "--print", prompt],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "HOME": str(Path.home())},
            cwd=str(BASE_DIR),
        )
        new_title = (result.stdout or "").strip().split('\n')[0].strip().strip('"\'')
        if len(new_title) > 10 and new_title != current_title:
            return new_title
    except Exception as e:
        _log(f"[CTR] Claude 제목 생성 오류: {e}")
    return ""


def _update_wp_post_title(blog_id: str, page_url: str, new_title: str) -> bool:
    """WordPress REST API로 포스트 제목 수정"""
    import ssl, urllib.request, urllib.parse, json, base64, re as _re, os
    if blog_id == "baremi542":
        site_url = "https://baremi542.com"
        wp_user = os.environ.get("WP_USER", "")
        wp_pass = os.environ.get("WP_APP_PASSWORD", "").replace(" ", "")
    else:  # triplog
        site_url = "https://app.baremi542.com"
        wp_user = os.environ.get("TRIPLOG_WP_USER", "")
        wp_pass = os.environ.get("TRIPLOG_WP_APP_PASSWORD", "").replace(" ", "")
    if not wp_user or not wp_pass:
        _log(f"[CTR] {blog_id} WP 인증 정보 없음")
        return False
    slug = page_url.rstrip("/").split("/")[-1]
    auth = "Basic " + base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        search_url = f"{site_url}/wp-json/wp/v2/posts?slug={urllib.parse.quote(slug)}"
        req = urllib.request.Request(search_url, headers={"Authorization": auth, "User-Agent": "Mozilla/5.0"})
        posts = json.loads(urllib.request.urlopen(req, timeout=10, context=ctx).read())
        if not posts:
            _log(f"[CTR] {blog_id} 포스트 없음: {slug}")
            return False
        post_id = posts[0]["id"]
        update_url = f"{site_url}/wp-json/wp/v2/posts/{post_id}"
        data = json.dumps({"title": new_title}).encode()
        req = urllib.request.Request(
            update_url, data=data, method="POST",
            headers={"Authorization": auth, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        result = json.loads(urllib.request.urlopen(req, timeout=10, context=ctx).read())
        return bool(result.get("title", {}).get("rendered"))
    except Exception as e:
        _log(f"[CTR] WP 제목 수정 오류: {e}")
        return False


def _update_tistory_post_title(blog_id: str, page_url: str, new_title: str) -> bool:
    """Playwright(Chrome 9222)로 Tistory 포스트 제목 수정"""
    import re as _re, time as _time
    m = _re.search(r'/(\d+)/?$', page_url)
    if not m:
        _log(f"[CTR] post_id 추출 실패: {page_url}")
        return False
    post_id = m.group(1)
    edit_url = f"https://{blog_id}.tistory.com/manage/newpost/{post_id}"
    try:
        from browser import connect_cdp, get_or_create_page
        pw, browser = connect_cdp(on_log=_log)
        page = get_or_create_page(browser)
        page.goto(edit_url, wait_until="networkidle", timeout=30000)
        _time.sleep(2)
        # 제목 입력창 선택
        title_sel = "#post-title-inp"
        page.wait_for_selector(title_sel, timeout=10000)
        title_el = page.query_selector(title_sel)
        title_el.click(click_count=3)
        page.fill(title_sel, new_title)
        # 임시저장 (Ctrl+S)
        page.keyboard.press("Meta+s")
        _time.sleep(3)
        _log(f"[CTR] Tistory 제목 수정 완료: {new_title}")
        return True
    except Exception as e:
        _log(f"[CTR] Tistory 제목 수정 오류: {e}")
        return False


def fix_low_ctr_titles(on_log=None) -> int:
    """CTR 1% 미만 + 노출 50회↑ 글 → Claude로 제목 개선 → Tistory/WP 자동 수정"""
    import os
    # .env 로드
    from pathlib import Path
    _env = Path(__file__).parent / ".env"
    if _env.exists():
        for line in _env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    try:
        from keyword_engine.gsc_connector import get_low_ctr_pages_with_titles
        pages = get_low_ctr_pages_with_titles(threshold=0.01, min_impressions=50)
        if not pages:
            _log("[CTR] 수정 대상 없음", on_log)
            return 0
        _log(f"[CTR] {len(pages)}개 저CTR 페이지 감지", on_log)

        fixed = 0
        for p in pages[:3]:  # 한 번에 최대 3개 처리
            blog_id = p.get("blog_id", "")
            page_url = p.get("page_url", "")
            slug = p.get("slug", "")
            avg_ctr = p.get("avg_ctr", 0)
            impressions = p.get("total_impressions", 0)

            # 현재 제목 가져오기
            current_title = _fetch_html_title(page_url) or slug
            _log(f"  └ {blog_id}: '{current_title[:40]}' (노출 {impressions}, CTR {avg_ctr:.1%})", on_log)

            # Claude로 개선 제목 생성
            new_title = _generate_ctr_title(current_title, blog_id, slug)
            if not new_title:
                _log(f"  └ 제목 개선안 생성 실패 — 스킵", on_log)
                continue

            _log(f"  └ 개선안: '{new_title[:50]}'", on_log)

            # 플랫폼별 업데이트
            if blog_id in ("baremi542", "triplog"):
                ok = _update_wp_post_title(blog_id, page_url, new_title)
            else:
                ok = _update_tistory_post_title(blog_id, page_url, new_title)

            if ok:
                _log(f"  ✅ {blog_id} 제목 수정 완료", on_log)
                fixed += 1

        return fixed
    except Exception as e:
        _log(f"[판단엔진] CTR 분석 오류: {e}", on_log)
        return 0


# ── 3. 시즌/트렌드 키워드 우선순위 상향 ────────────────────────────────────

_SEASON_KEYWORDS = {
    # 월 → (시즌 키워드 패턴, 점수 보정)
    3:  (["벚꽃", "봄나들이", "입학", "이사", "봄옷"], 20),
    4:  (["벚꽃", "어버이날", "봄여행", "축제"], 20),
    5:  (["어린이날", "어버이날", "가정의달", "황금연휴"], 25),
    6:  (["장마", "에어컨", "여름준비", "여행"], 15),
    7:  (["휴가", "여름여행", "제주도", "해수욕장"], 25),
    8:  (["휴가", "여름여행", "말복", "개학준비"], 20),
    9:  (["추석", "단풍", "가을여행", "국감"], 20),
    10: (["단풍", "핼러윈", "국감", "가을낚시"], 20),
    11: (["수능", "김장", "연말", "겨울준비"], 20),
    12: (["크리스마스", "연말정산", "송년", "겨울여행"], 25),
    1:  (["새해", "연말정산", "신년", "겨울"], 15),
    2:  (["설날", "밸런타인", "졸업", "입학준비"], 20),
}


def boost_seasonal_keywords(on_log=None) -> int:
    """현재 달 시즌 키워드 점수 상향"""
    from keyword_engine.db_handler import _conn
    month = datetime.now(KST).month
    season_data = _SEASON_KEYWORDS.get(month, ([], 0))
    patterns, boost = season_data
    if not patterns:
        return 0

    boosted = 0
    with _conn() as db:
        for pattern in patterns:
            result = db.execute(
                """UPDATE keywords SET score = MIN(score + ?, 100)
                   WHERE keyword LIKE ? AND score < 80""",
                (boost, f"%{pattern}%"),
            )
            boosted += result.rowcount
    if boosted:
        _log(f"[판단엔진] 시즌 키워드 {boosted}개 점수 +{boost}", on_log)
    return boosted


# ── 4. 발행량 조정 권고 ────────────────────────────────────────────────────

def get_publish_count_recommendation(on_log=None) -> dict:
    """블로그별 오늘 권장 발행량 반환 {blog_id: count}"""
    try:
        from adsense_tracker import get_recommended_publish_count
        count = get_recommended_publish_count()
        blogs = ["goodisak", "nolja100", "salim1su", "baremi542",
                 "triplog", "woll100", "phn0502"]
        rec = {b: count for b in blogs}
        if count > 1:
            _log(f"[판단엔진] 수익 pace 저조 → 발행량 {count}개/블로그 권고", on_log)
        return rec
    except Exception:
        return {}


# ── 메인: overnight_run.py에서 라운드 시작 전 호출 ─────────────────────────

def run_daily_analysis(on_log=None) -> dict:
    """
    매일 1회 실행 (overnight_run.py 첫 라운드 전).
    - GSC 데이터 수집
    - 급상승 키워드 추가
    - 시즌 키워드 점수 상향
    - CTR 낮은 글 감지
    반환: {"keywords_added": N, "season_boosted": N, "low_ctr": N}
    """
    _log("[판단엔진] 일간 분석 시작", on_log)
    results = {}

    # GSC 어제 데이터 수집
    try:
        from keyword_engine.gsc_connector import collect_daily
        gsc_result = collect_daily()
        _log(f"[판단엔진] GSC 수집 완료: {list(gsc_result.keys())}", on_log)
    except Exception as e:
        _log(f"[판단엔진] GSC 수집 생략 ({e})", on_log)

    # AdSense 어제 수익 수집
    try:
        from adsense_tracker import collect_earnings
        earned = collect_earnings()
        if earned is not None:
            _log(f"[판단엔진] AdSense 어제 수익: ₩{earned:,.0f}", on_log)
    except Exception as e:
        _log(f"[판단엔진] AdSense 수집 생략 ({e})", on_log)

    # 급상승 키워드 추가
    results["keywords_added"] = expand_from_rising_pages(on_log=on_log)

    # 시즌 키워드 점수 상향
    results["season_boosted"] = boost_seasonal_keywords(on_log=on_log)

    # CTR 낮은 글 감지 (로그만)
    results["low_ctr"] = fix_low_ctr_titles(on_log=on_log)

    _log(f"[판단엔진] 완료 — 키워드+{results['keywords_added']}, 시즌+{results['season_boosted']}", on_log)
    return results


if __name__ == "__main__":
    run_daily_analysis()
