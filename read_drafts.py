"""
read_drafts.py
각 블로그의 임시저장 글 내용을 읽어서 출력 (발행 X)
"""
import sys
import time
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp, get_or_create_page
from login_playwright import login_blog
from config import ACCOUNT_MAP

def _log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

SKIP_TITLES = {'제목 없음', '토스 행운퀴즈', '[내용 없음]'}


def read_tistory_drafts(blog_id: str, max_drafts: int = 3):
    """Tistory 블로그 임시저장 글 내용 읽기"""
    _log(f"=== {blog_id} 임시저장 글 확인 ===")

    # 로그인
    ok = login_blog(blog_id, on_log=_log)
    if not ok:
        _log(f"[{blog_id}] 로그인 실패")
        return []
    time.sleep(2)

    pw, browser = connect_cdp(on_log=_log)
    try:
        page = get_or_create_page(browser)

        editor_url = f"https://{blog_id}.tistory.com/manage/newpost/"
        page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # 임시저장 버튼 클릭
        count_btn = page.query_selector('a.count[aria-label*="임시저장"]')
        if not count_btn:
            _log(f"[{blog_id}] 임시저장 버튼 없음")
            return []

        count_text = count_btn.text_content() or ''
        _log(f"[{blog_id}] 임시저장: {count_text.strip()}")
        count_btn.click()
        time.sleep(2)

        # 드래프트 목록
        links = page.query_selector_all('a.link_info')
        _log(f"[{blog_id}] 드래프트 {len(links)}개 발견")

        # 드래프트 목록에서 유효한 제목들 수집 (element handle 저장 X)
        draft_titles = []
        for link in links:
            try:
                t = (link.text_content() or '').strip()
                if t and t not in SKIP_TITLES and '규칙 확인' not in t and '[내용 없음]' not in t:
                    draft_titles.append(t)
            except Exception:
                pass

        _log(f"[{blog_id}] 유효 드래프트 제목 {len(draft_titles)}개: {draft_titles[:5]}")

        drafts = []

        for idx, target_title in enumerate(draft_titles[:max_drafts]):
            # 매번 에디터 페이지로 돌아가서 드래프트 목록 재오픈
            page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            count_btn2 = page.query_selector('a.count[aria-label*="임시저장"]')
            if not count_btn2:
                break
            count_btn2.click()
            time.sleep(2)

            # 제목으로 해당 링크 찾기
            fresh_links = page.query_selector_all('a.link_info')
            clicked = False
            for link in fresh_links:
                try:
                    t = (link.text_content() or '').strip()
                    if t == target_title:
                        _log(f"  드래프트 [{idx+1}] 로드: '{target_title}'")
                        link.click()
                        time.sleep(5)
                        clicked = True
                        break
                except Exception:
                    pass

            if not clicked:
                _log(f"  드래프트 [{idx+1}] '{target_title}' 못 찾음 — 첫 번째 항목 클릭")
                fresh_links2 = page.query_selector_all('a.link_info')
                for link in fresh_links2:
                    try:
                        t = (link.text_content() or '').strip()
                        if t and t not in SKIP_TITLES:
                            link.click()
                            time.sleep(5)
                            break
                    except Exception:
                        pass

            # 내용 읽기
            try:
                content = page.evaluate("() => tinymce.activeEditor ? tinymce.activeEditor.getContent() : ''")
            except Exception:
                content = ""

            # 제목
            try:
                title_el = page.query_selector('#post-title-inp') or page.query_selector('#title')
                actual_title = title_el.input_value() if title_el else target_title
            except Exception:
                actual_title = target_title

            # 태그
            try:
                tag_val = page.evaluate("() => document.getElementById('tagText')?.value || ''")
            except Exception:
                tag_val = ""

            # 분석
            clean_text = re.sub(r'<[^>]+>', '', content)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            char_count = len(clean_text)
            img_count = content.count('[##_Image') + len(re.findall(r'<img\s', content))

            # 품질 평가
            quality = "✓"
            issues = []
            if char_count < 1700:
                issues.append(f"글자수 부족({char_count}자)")
                quality = "✗"
            if img_count < 3:
                issues.append(f"이미지 부족({img_count}개)")
                quality = "⚠" if quality == "✓" else quality
            if not tag_val.strip():
                issues.append("태그 없음")
                quality = "⚠" if quality == "✓" else quality

            draft_info = {
                'index': idx,
                'title': actual_title,
                'char_count': char_count,
                'img_count': img_count,
                'tags': tag_val,
                'quality': quality,
                'issues': issues,
                'content_html': content,       # 전체 HTML (Claude Code 검수용)
                'content_text': clean_text,    # 전체 텍스트
                'preview': clean_text[:800],
            }
            drafts.append(draft_info)

            _log(f"    {quality} 제목: {actual_title}")
            _log(f"    글자수: {char_count}자 | 이미지: {img_count}개 | 태그: {tag_val[:60] or '(없음)'}")
            if issues:
                _log(f"    문제: {', '.join(issues)}")
            _log(f"    내용 미리보기: {clean_text[:300]}")
            _log("")

        return drafts

    finally:
        pw.stop()


def read_wp_drafts(blog_id: str):
    """WordPress(baremi542, triplog) REST API로 draft 읽기"""
    import urllib.request, ssl, base64
    from dotenv import load_dotenv
    import os
    load_dotenv(Path(__file__).parent / ".env")

    site_map = {
        "baremi542": ("https://baremi542.com", "WP_USER", "WP_APP_PASSWORD"),
        "triplog":   ("https://app.baremi542.com", "TRIPLOG_WP_USER", "TRIPLOG_WP_APP_PASSWORD"),
    }
    site_url, user_env, pass_env = site_map[blog_id]
    user = os.getenv(user_env, "")
    pw   = os.getenv(pass_env, "")
    if not user or not pw:
        _log(f"[{blog_id}] WP 인증 정보 없음")
        return []

    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(
            f"{site_url}/wp-json/wp/v2/posts?status=draft&per_page=5&orderby=modified&order=desc",
            headers={"Authorization": f"Basic {token}", "User-Agent": "Mozilla/5.0"}
        )
        data = json.loads(urllib.request.urlopen(req, timeout=15, context=ctx).read())
    except Exception as e:
        _log(f"[{blog_id}] WP API 오류: {e}")
        return []

    drafts = []
    for post in data:
        content_html = post.get("content", {}).get("rendered", "")
        clean_text = re.sub(r'<[^>]+>', '', content_html)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        char_count  = len(clean_text)
        img_count   = len(re.findall(r'<img\s', content_html))
        title       = post.get("title", {}).get("rendered", "")

        issues = []
        quality = "✓"
        if char_count < 1700:
            issues.append(f"글자수 부족({char_count}자)"); quality = "✗"
        if img_count < 3:
            issues.append(f"이미지 부족({img_count}개)"); quality = "⚠" if quality == "✓" else quality
        md_markers = re.findall(r'\*\*[^*]+\*\*|^#{1,3} ', content_html, re.MULTILINE)
        if md_markers:
            issues.append(f"마크다운 잔재({len(md_markers)}개)"); quality = "⚠" if quality == "✓" else quality
        for marker in ["[검증 필요]", "[출처 필요]", "[사실 확인]", "{{", "===이미지==="]:
            if marker in content_html:
                issues.append(f"내부마커({marker})"); quality = "✗"; break

        draft = {
            "post_id":     post["id"],
            "title":       title,
            "char_count":  char_count,
            "img_count":   img_count,
            "quality":     quality,
            "issues":      issues,
            "content_html": content_html,
            "content_text": clean_text,
            "preview":     clean_text[:800],
        }
        drafts.append(draft)
        _log(f"  {quality} [{post['id']}] {title} ({char_count}자, 이미지{img_count}개)")
        if issues:
            _log(f"     → {', '.join(issues)}")
        _log(f"     미리보기: {clean_text[:200]}")
    return drafts


def read_naver_drafts(blog_id: str):
    """네이버 블로그 draft 상태를 DB에서 확인 (Playwright 없이)"""
    try:
        from keyword_engine.db_handler import _conn
        with _conn() as db:
            rows = db.execute(
                "SELECT keyword, title, updated_at FROM keyword_blog_status "
                "WHERE blog_id=? AND status='draft_saved' ORDER BY updated_at DESC LIMIT 5",
                (blog_id,)
            ).fetchall()
        if not rows:
            _log(f"[{blog_id}] draft_saved 없음")
            return []
        drafts = []
        for kw, saved_title, updated_at in rows:
            display = f"'{saved_title}'" if saved_title else f"키워드: '{kw}'"
            _log(f"  [{blog_id}] draft_saved: {display} ({updated_at})")
            drafts.append({"keyword": kw, "title": saved_title or "", "updated_at": updated_at,
                           "note": "네이버는 publish_drafts.py로 직접 검수 필요"})
        return drafts
    except Exception as e:
        _log(f"[{blog_id}] DB 조회 오류: {e}")
        return []


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else 'all'
    results = {}

    TISTORY_BLOGS = ["goodisak", "nolja100", "woll100", "phn0502"]
    WP_BLOGS      = ["baremi542", "triplog"]
    NAVER_BLOGS   = ["salim1su", "me1091"]

    for blog_id in TISTORY_BLOGS:
        if target in ('all', blog_id):
            _log(f"\n=== {blog_id} (Tistory) ===")
            results[blog_id] = read_tistory_drafts(blog_id, max_drafts=3)

    for blog_id in WP_BLOGS:
        if target in ('all', blog_id):
            _log(f"\n=== {blog_id} (WordPress) ===")
            results[blog_id] = read_wp_drafts(blog_id)

    for blog_id in NAVER_BLOGS:
        if target in ('all', blog_id):
            _log(f"\n=== {blog_id} (Naver) ===")
            results[blog_id] = read_naver_drafts(blog_id)

    # 요약 출력
    _log("\n========== 임시저장 글 요약 ==========")
    total = 0
    for blog_id, drafts in results.items():
        if drafts:
            total += len(drafts)
            _log(f"\n[{blog_id}] {len(drafts)}개")
            for d in drafts:
                title = d.get('title') or d.get('keyword', '?')
                q = d.get('quality', '-')
                cc = d.get('char_count', '-')
                ic = d.get('img_count', '-')
                _log(f"  {q} {title} ({cc}자, 이미지{ic}개)")
                if d.get('issues'):
                    _log(f"     → {', '.join(d['issues'])}")
    _log(f"\n총 {total}개 임시저장 글 발견")

    # JSON 저장 (Claude Code가 읽어서 검수에 활용)
    out = Path("draft_review.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"결과 저장: {out} (Claude Code 검수용)")
