"""통합 검수 에이전트 — 1단계: 규칙+품질 검수 / 2단계: 발행 후 실물 확인"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from agents import review_agent as _review
    from agents import final_review_agent as _final
    from agents import fix_agent as _fix
except ImportError:
    import review_agent as _review
    import final_review_agent as _final
    import fix_agent as _fix

# ── 블로그 플랫폼 설정 ─────────────────────────────────────────────────────
BLOG_POST_CONFIG = {
    "goodisak":  {"type": "tistory",   "domain": "goodisak.tistory.com",
                  "min_adsense": 3, "min_images": 2},
    "nolja100":  {"type": "tistory",   "domain": "nolja100.tistory.com",
                  "min_adsense": 3, "min_images": 2},
    "salim1su":  {"type": "naver",     "id": "salim1su",
                  "min_adsense": 0, "min_images": 1},
    "baremi542": {"type": "wordpress", "domain": "baremi542.com",
                  "min_adsense": 1, "min_images": 0},
}

NAVER_RESTRICTED = [
    "유발", "진단", "처방", "치료", "완치", "증상", "임상",
    "상담", "보장", "환급 확정", "수익 보장",
    "무조건", "반드시", "100%", "즉시 효과", "유일한",
]


# ══════════════════════════════════════════════════════════════════════════════
# 1단계: 포스팅 전 검수 (규칙 기반 + claude.ai 최종 검토)
# ══════════════════════════════════════════════════════════════════════════════

def run(result: dict, keyword: str, blog_id: str,
        on_log=None, on_status=None) -> dict:
    """규칙 기반 검수 → claude.ai 최종 검토 순차 실행.

    Returns:
        dict: {"passed": bool, "issues": list, "reason": str, "result": dict}
    """
    # 1단계-a: 규칙 기반 자동 검수
    review = _review.run(result, keyword, blog_id,
                         on_log=on_log, on_status=on_status)
    if not review["passed"]:
        return {
            "passed": False,
            "issues": review["issues"],
            "reason": f"자동 검수 불합격: {', '.join(review['issues'][:3])}",
            "result": review["result"],
        }

    # 1단계-b: 최종 검토 전 AI 패턴 사전 정제
    cleaned = _fix.pre_clean(review["result"], blog_id, on_log=on_log)

    # 1단계-c: claude.ai 최종 검토
    final = _final.run(cleaned, keyword, blog_id,
                       on_log=on_log, on_status=on_status)
    return {
        "passed": final["passed"],
        "issues": [],
        "reason": final["reason"],
        "result": final["result"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2단계: 포스팅 후 검수 (Playwright 실물 확인)
# ══════════════════════════════════════════════════════════════════════════════

def run_post(blog_id: str, title: str,
             on_log=None, on_status=None) -> dict:
    """포스팅 결과를 Playwright로 확인해 품질 체크.

    Returns:
        dict: {"passed": bool, "issues": list, "fixed": bool}
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if on_status:
        on_status("review", "working")

    log(f"[포스팅후검수] {blog_id} — '{title[:30]}' 검수 시작")

    cfg = BLOG_POST_CONFIG.get(blog_id)
    if not cfg:
        log(f"[포스팅후검수] '{blog_id}' 설정 없음 — 건너뜀")
        if on_status:
            on_status("review", "done")
        return {"passed": True, "issues": [], "fixed": False}

    pw = None
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from browser import connect_cdp
        pw, browser = connect_cdp(on_log)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()

        try:
            # 네이버는 현재 임시저장 워크플로우이므로 발행 URL 검수 스킵
            if cfg.get("type") == "naver":
                log("[포스팅후검수] 네이버 임시저장 모드 — 발행 URL 검수 건너뜀")
                if on_status:
                    on_status("review", "done")
                return {"passed": True, "issues": [], "fixed": False}

            # URL 탐색
            post_url = _find_post_url(blog_id, title, cfg, page, log)
            if not post_url:
                log("[포스팅후검수] 포스트 URL 찾기 실패 — 건너뜀")
                if on_status:
                    on_status("review", "done")
                return {"passed": True, "issues": ["URL 찾기 실패"], "fixed": False}

            log(f"[포스팅후검수] 발행 URL: {post_url}")

            # 1차 체크
            issues = _check_post(cfg, page, post_url, log)

            # 자동 수정
            fixed = False
            if issues:
                log(f"[포스팅후검수] {len(issues)}개 문제 — 자동 수정 시도")
                fixed = _autofix_post(blog_id, cfg, page, post_url, issues, log)

                if fixed:
                    # 재확인
                    page.wait_for_timeout(3000)
                    page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    issues = _check_post(cfg, page, post_url, log)

            passed = len(issues) == 0
            if passed:
                log("[포스팅후검수] ✓ 발행 글 검수 통과")
            else:
                for iss in issues:
                    log(f"[포스팅후검수] ⚠ {iss}")

            if on_status:
                on_status("review", "done" if passed else "failed")

            return {"passed": passed, "issues": issues, "fixed": fixed}

        finally:
            try:
                page.close()
            except Exception:
                pass

    except Exception as e:
        log(f"[포스팅후검수] 오류: {e} — 건너뜀")
        if on_status:
            on_status("review", "done")
        return {"passed": True, "issues": [str(e)], "fixed": False}

    finally:
        try:
            if pw:
                pw.stop()
        except Exception:
            pass


# ── URL 탐색 ──────────────────────────────────────────────────────────────

def _find_post_url(blog_id, title, cfg, page, log):
    """블로그 홈에서 최신 발행 글 URL 반환."""
    try:
        short_title = title[:12]

        if cfg["type"] == "tistory":
            domain = cfg["domain"]
            page.goto(f"https://{domain}", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            url = page.evaluate("""(shortTitle) => {
                const links = Array.from(document.querySelectorAll('a'));
                // 제목 매칭 우선
                for (const a of links) {
                    if (a.innerText && a.innerText.trim().includes(shortTitle))
                        return a.href;
                }
                // 숫자 경로 링크 (포스트 URL 패턴)
                const postLinks = links.filter(a =>
                    /\\/\\d+$/.test(a.href) &&
                    !a.href.includes('/manage') &&
                    !a.href.includes('/tag') &&
                    !a.href.includes('/category')
                );
                return postLinks.length ? postLinks[0].href : null;
            }""", short_title)
            return url

        elif cfg["type"] == "naver":
            nid = cfg["id"]
            page.goto(f"https://blog.naver.com/{nid}", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            # 네이버 블로그는 iframe 구조
            url = page.evaluate("""(nid, shortTitle) => {
                // iframe 내부 탐색
                const frames = document.querySelectorAll('iframe');
                for (const f of frames) {
                    try {
                        const links = Array.from(f.contentDocument.querySelectorAll('a'));
                        for (const a of links) {
                            if (a.innerText && a.innerText.trim().includes(shortTitle))
                                return a.href;
                        }
                    } catch(e) {}
                }
                // 직접 링크 탐색
                const links = Array.from(document.querySelectorAll('a'));
                for (const a of links) {
                    if (a.href && a.href.includes(nid) && /\\/\\d+$/.test(a.href))
                        return a.href;
                }
                return null;
            }""", nid, short_title)
            # 절대 URL 보정
            if url and not url.startswith("http"):
                url = f"https://blog.naver.com{url}"
            return url

        elif cfg["type"] == "wordpress":
            domain = cfg["domain"]
            page.goto(f"https://{domain}", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            url = page.evaluate("""(shortTitle) => {
                const selectors = ['h1 a', 'h2 a', '.entry-title a',
                                   'article a', '.post-title a'];
                for (const sel of selectors) {
                    const links = Array.from(document.querySelectorAll(sel));
                    for (const a of links) {
                        if (a.innerText && a.innerText.trim().includes(shortTitle))
                            return a.href;
                        if (links.length) return links[0].href;
                    }
                }
                return null;
            }""", short_title)
            return url

    except Exception as e:
        log(f"[포스팅후검수] URL 탐색 오류: {e}")
    return None


# ── 체크 ─────────────────────────────────────────────────────────────────

def _check_post(cfg, page, url, log):
    """발행 글 체크. 문제 목록 반환."""
    issues = []
    platform = cfg["type"]

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)

        if platform == "tistory":
            # 404 확인
            if page.evaluate("() => document.title.includes('404')"):
                return ["발행 글 없음 (404)"]

            # 애드센스 개수
            ad_count = page.evaluate(
                "() => document.querySelectorAll('ins.adsbygoogle').length"
            )
            min_ad = cfg.get("min_adsense", 3)
            if ad_count < min_ad:
                issues.append(f"애드센스 부족: {ad_count}개 < {min_ad}개")
                log(f"[포스팅후검수] 애드센스 {ad_count}개 (요구: {min_ad})")
            else:
                log(f"[포스팅후검수] ✓ 애드센스 {ad_count}개")

            # 이미지 개수
            img_count = page.evaluate(
                "() => document.querySelectorAll('.entry-content img,"
                " .contents_style img, article img').length"
            )
            min_img = cfg.get("min_images", 2)
            if img_count < min_img:
                issues.append(f"이미지 부족: {img_count}개 < {min_img}개")
                log(f"[포스팅후검수] 이미지 {img_count}개 (요구: {min_img})")
            else:
                log(f"[포스팅후검수] ✓ 이미지 {img_count}개")

            # 표 렌더링
            broken_tables = page.evaluate("""() => {
                const tables = document.querySelectorAll(
                    '.entry-content table, .contents_style table, article table');
                let broken = 0;
                for (const t of tables) {
                    if (!t.querySelector('td, th')) broken++;
                }
                return broken;
            }""")
            if broken_tables > 0:
                issues.append(f"표 렌더링 오류: {broken_tables}개")
                log(f"[포스팅후검수] ⚠ 표 렌더링 오류 {broken_tables}개")
            else:
                tbl_count = page.evaluate(
                    "() => document.querySelectorAll('table').length"
                )
                if tbl_count > 0:
                    log(f"[포스팅후검수] ✓ 표 {tbl_count}개 정상")

            # 빈 링크 확인 (쿠팡 제휴링크 등 나중에 확장)
            broken_links = page.evaluate("""() => {
                const links = document.querySelectorAll(
                    '.entry-content a, .contents_style a, article a');
                let broken = 0;
                for (const a of links) {
                    const h = a.getAttribute('href') || '';
                    if (!h || h === '#' || h === 'javascript:void(0)') broken++;
                }
                return broken;
            }""")
            if broken_links > 0:
                issues.append(f"빈 링크 {broken_links}개")
                log(f"[포스팅후검수] ⚠ 빈 링크 {broken_links}개")

        elif platform == "naver":
            # 발행 여부 (404)
            title_text = page.evaluate("() => document.title") or ""
            if "404" in title_text or "찾을 수 없" in title_text:
                return ["발행 글 없음 (404)"]

            # iframe 내 텍스트 추출
            body_text = page.evaluate("""() => {
                try {
                    const f = document.querySelector('iframe#mainFrame');
                    if (f) return f.contentDocument.body.innerText;
                } catch(e) {}
                return document.body.innerText;
            }""") or ""

            found = [w for w in NAVER_RESTRICTED if w in body_text]
            if found:
                issues.append(f"네이버 제한어 발견: {found}")
                log(f"[포스팅후검수] ⚠ 네이버 제한어: {found}")
            else:
                log("[포스팅후검수] ✓ 네이버 제한어 없음")

        elif platform == "wordpress":
            title_text = page.evaluate("() => document.title") or ""
            cur_url = page.url
            if ("404" in title_text or "찾을 수 없" in title_text
                    or "private" in cur_url):
                issues.append(f"WordPress 발행 상태 이상: {cur_url}")
                log(f"[포스팅후검수] ⚠ WordPress 이상: {cur_url}")
            else:
                log(f"[포스팅후검수] ✓ WordPress 발행 확인: {cur_url}")

    except Exception as e:
        log(f"[포스팅후검수] 체크 오류: {e}")
        issues.append(f"체크 오류: {e}")

    return issues


# ── 자동 수정 ────────────────────────────────────────────────────────────

def _autofix_post(blog_id, cfg, page, post_url, issues, log):
    """감지된 문제 자동 수정 시도. 수정 성공 시 True 반환."""
    fixed = False

    if cfg["type"] == "tistory":
        ad_issues = [i for i in issues if "애드센스 부족" in i]
        if ad_issues:
            fixed = _fix_tistory_adsense(cfg, page, post_url, log)

    return fixed


def _fix_tistory_adsense(cfg, page, post_url, log):
    """티스토리 편집 페이지에서 애드센스 마커 추가 후 임시저장."""
    try:
        m = re.search(r"/(\d+)$", post_url)
        if not m:
            log("[포스팅후검수] post_id 추출 실패 — 수정 건너뜀")
            return False

        post_id = m.group(1)
        domain = cfg["domain"]
        edit_url = f"https://{domain}/manage/newpost/{post_id}"

        log(f"[포스팅후검수] 편집 페이지: {edit_url}")
        page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

        # TinyMCE 에디터: 본문 1/3, 2/3 위치에 [애드센스] 삽입
        added = page.evaluate("""() => {
            if (!window.tinymce || !tinymce.activeEditor) return false;
            const ed = tinymce.activeEditor;
            const content = ed.getContent();
            const adTag = '<p>[애드센스]</p>';
            const parts = content.split('</p>');
            if (parts.length < 4) return false;
            const t1 = Math.floor(parts.length / 3);
            const t2 = Math.floor(parts.length * 2 / 3);
            parts.splice(t2, 0, adTag);
            parts.splice(t1, 0, adTag);
            ed.setContent(parts.join('</p>'));
            ed.fire('change');
            ed.save();
            return true;
        }""")

        if not added:
            log("[포스팅후검수] TinyMCE 편집 실패 — 수정 건너뜀")
            return False

        page.wait_for_timeout(1000)
        page.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if (b.textContent.trim().includes('임시저장')) {
                    b.click();
                    return;
                }
            }
        }""")
        page.wait_for_timeout(3000)
        log("[포스팅후검수] ✓ 애드센스 추가 임시저장 완료")
        return True

    except Exception as e:
        log(f"[포스팅후검수] 자동 수정 오류: {e}")
        return False
