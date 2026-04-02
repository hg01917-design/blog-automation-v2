"""
publish_drafts.py
각 블로그의 임시저장 글 1개씩 → 이미지/애드센스 확인·보완 → 비공개 발행

사용법:
    python publish_drafts.py                    # 4개 블로그 모두
    python publish_drafts.py goodisak           # 특정 블로그만
"""
import sys
import re
import time
import json
import base64
import os
import ssl
import urllib.request
import urllib.parse
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from browser import connect_cdp, get_or_create_page
from gsc_indexing import request_indexing
from config import ACCOUNTS, ACCOUNT_MAP
from login_playwright import login_blog
from poster import (
    _tistory_upload_image,
    _tistory_insert_adsense_format,
    _wp_urlopen,
    _wp_upload_image_with_id,
)

IMAGES_DIR = Path(__file__).parent / "images"
SITE_URL = "https://baremi542.com"

# ─── 로그 ───────────────────────────────────────
def _log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ─── 이미지 생성 (loremflickr) ──────────────────
def _make_image(prompt: str, filename: str) -> str | None:
    """loremflickr 스톡 이미지 다운로드 → images/ 에 저장. 경로 반환."""
    import re as _re
    STOP = {
        'with', 'from', 'that', 'this', 'photo', 'image', 'realistic',
        'style', 'clean', 'bright', 'light', 'scene', 'interior', 'modern',
        'korean', 'ratio', 'text', 'people', 'watermark', 'icon', 'flat',
        'white', 'background', 'type', 'natural', 'infographic',
    }
    words = _re.findall(r'[A-Za-z]{4,}', prompt)
    kws = [w.lower() for w in words if w.lower() not in STOP][:3]
    kw_str = ','.join(kws) if kws else 'lifestyle'
    url = f"https://loremflickr.com/1024/768/{urllib.parse.quote(kw_str)}"

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        data = resp.read()
        ext = ".jpg"
        if not filename.endswith(ext):
            filename = Path(filename).stem + ext
        out = IMAGES_DIR / filename
        out.write_bytes(data)
        _log(f"[이미지] loremflickr → {filename}")
        return str(out)
    except Exception as e:
        _log(f"[이미지] 다운로드 실패: {e}")
        return None


# ══════════════════════════════════════════════
# WordPress (baremi542)
# ══════════════════════════════════════════════
def _wp_auth():
    wp_user = os.environ.get("WP_USER", "")
    wp_pass = os.environ.get("WP_APP_PASSWORD", "").replace(" ", "")
    if not wp_user or not wp_pass:
        raise RuntimeError("WP_USER / WP_APP_PASSWORD 환경변수 미설정")
    token = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
    return f"Basic {token}"


def _wp_api(path: str, method="GET", data=None, auth=None):
    """WordPress REST API 요청."""
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    req = urllib.request.Request(
        f"{SITE_URL}/wp-json/wp/v2/{path}",
        data=json.dumps(data).encode() if data else None,
        headers=headers,
        method=method,
    )
    return json.loads(_wp_urlopen(req, timeout=20).read())


def publish_wp_draft():
    _log("── baremi542 (WordPress) 드래프트 처리 시작 ──")
    try:
        auth = _wp_auth()
    except RuntimeError as e:
        _log(f"[WP] {e} — 스킵")
        return False

    # 드래프트 목록
    drafts = _wp_api("posts?status=draft&per_page=10&orderby=modified&order=desc", auth=auth)
    if not drafts:
        _log("[WP] 드래프트 없음 — 스킵")
        return False

    # 가장 적합한 드래프트: 글자 수가 많은 것
    def _score(p):
        return len(re.sub(r'<[^>]+>', '', p.get("content", {}).get("rendered", "")))
    post = max(drafts, key=_score)
    post_id = post["id"]
    title = post["title"]["rendered"]
    content_html = post["content"]["rendered"]
    _log(f"[WP] 선택된 드래프트: [{post_id}] {title}")
    _log(f"[WP] 콘텐츠 길이: {len(content_html)}자")

    # 이미지 체크
    has_images = bool(re.search(r'<img\s', content_html))
    _log(f"[WP] 이미지 있음: {has_images}")

    # 애드센스 체크 (AdSense 스크립트 또는 <!-- adsense --> 스타일)
    has_adsense = bool(
        re.search(r'adsbygoogle|data-ad-client|<!-- adsense', content_html, re.IGNORECASE)
    )
    _log(f"[WP] 애드센스 있음: {has_adsense}")

    updated_content = content_html

    # 이미지 보완 — 없으면 2개 생성 후 상단에 삽입
    if not has_images:
        _log("[WP] 이미지 없음 → 생성 중...")
        slug = re.sub(r'[^\w가-힣]', '-', title.strip()).strip('-')[:40]
        for i in range(1, 3):
            fp = _make_image(title, f"{slug}-img{i}.jpg")
            if fp:
                img_url, media_id = _wp_upload_image_with_id(
                    SITE_URL, auth, fp, alt=title, on_log=_log
                )
                if img_url:
                    fig = f'<figure class="wp-block-image"><img src="{img_url}" alt="{title}"/></figure>\n'
                    # 첫 번째 </p> 뒤에 삽입
                    if i == 1:
                        updated_content = re.sub(r'(</p>)', r'\1' + fig, updated_content, count=1)
                    else:
                        # 중간쯤 삽입
                        mid = len(updated_content) // 2
                        insert_pos = updated_content.find('</p>', mid)
                        if insert_pos > 0:
                            updated_content = (
                                updated_content[:insert_pos + 4]
                                + fig
                                + updated_content[insert_pos + 4:]
                            )

    # 애드센스 보완
    if not has_adsense:
        _log("[WP] 애드센스 없음 → 삽입 중...")
        # </p> 기준 1/3, 2/3 위치에 애드센스 HTML 삽입
        adsense_html = (
            '\n<!-- adsense -->\n'
            '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"></script>\n'
            '<ins class="adsbygoogle" style="display:block;text-align:center" '
            'data-ad-layout="in-article" data-ad-format="fluid" '
            'data-ad-client="ca-pub-XXXXXXXXXXXXXXXX" data-ad-slot="XXXXXXXXXX"></ins>\n'
            '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>\n'
        )
        parts = updated_content.split('</p>')
        n = len(parts)
        if n >= 4:
            t1, t2 = n // 3, n * 2 // 3
            parts.insert(t2, adsense_html)
            parts.insert(t1, adsense_html)
        elif n >= 2:
            parts.insert(n // 2, adsense_html)
        updated_content = '</p>'.join(parts)

    # 비공개 발행
    patch_data = {
        "status": "private",
        "content": updated_content,
    }
    result = _wp_api(f"posts/{post_id}", method="POST", data=patch_data, auth=auth)
    new_status = result.get("status", "?")
    new_link = result.get("link", "")
    _log(f"[WP] 발행 완료 → status={new_status}, link={new_link}")
    return new_status == "private"


# ══════════════════════════════════════════════
# 중복 체크 (발행 전 RSS 비교)
# ══════════════════════════════════════════════
def _get_published_titles(blog_id: str, blog_type: str = 'tistory') -> set:
    """RSS에서 이미 발행된 글 제목 목록을 가져온다."""
    import re as _re
    try:
        if blog_type == 'naver':
            url = f"https://rss.blog.naver.com/{blog_id}.xml"
        else:
            url = f"https://{blog_id}.tistory.com/rss"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=10, context=ctx).read().decode('utf-8', errors='ignore')
        titles = _re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>', data)
        result = {(t[0] or t[1]).strip() for t in titles if (t[0] or t[1]).strip()}
        _log(f"[{blog_id}] 발행된 글 {len(result)}개 확인")
        return result
    except Exception as e:
        _log(f"[{blog_id}] RSS 조회 실패: {e}")
        return set()


# ══════════════════════════════════════════════
# Tistory (goodisak / nolja100)
# ══════════════════════════════════════════════
def _tistory_get_draft_id(page, blog_id: str) -> str | None:
    """에디터 임시저장 목록에서 첫 번째 유효한 드래프트를 에디터에 로드.
    성공 시 'loaded' 반환 (이후 page.goto 불필요).
    """
    editor_url = f"https://{blog_id}.tistory.com/manage/newpost/"
    _log(f"[{blog_id}] 에디터 이동: {editor_url}")
    try:
        page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass
    time.sleep(4)

    # 임시저장 개수 버튼 클릭
    count_btn = page.query_selector('a.count[aria-label*="임시저장"]')
    if not count_btn:
        _log(f"[{blog_id}] 임시저장 버튼 없음 — 임시저장 글 없음")
        return None
    count_btn.click()
    time.sleep(2)

    # 스킵 목록
    SKIP_TITLES = {'제목 없음', '토스 행운퀴즈'}
    SKIP_KEYWORDS = ['규칙 확인', '[내용 없음]']

    # 이미 발행된 글 목록 (중복 방지)
    published_titles = _get_published_titles(blog_id, 'tistory')

    # --- 1단계: 중복 드래프트 삭제 ---
    if published_titles:
        # dialog 자동 수락 핸들러 등록
        def _accept(d): d.accept()
        page.on("dialog", _accept)
        try:
            links_all = page.query_selector_all('a.link_info')
            for link in links_all:
                try:
                    title = (link.text_content() or '').strip()
                    if title in published_titles:
                        del_btn = link.evaluate_handle(
                            "el => el.parentElement.querySelector('button.ico_trash')"
                        ).as_element()
                        if del_btn:
                            _log(f"[{blog_id}] 중복 삭제: '{title}'")
                            del_btn.evaluate("el => el.click()")
                            time.sleep(1.5)
                except Exception:
                    pass
        finally:
            page.remove_listener("dialog", _accept)

    # --- 2단계: 첫 번째 유효 드래프트 로드 ---
    links = page.query_selector_all('a.link_info')
    for link in links:
        try:
            title = (link.text_content() or '').strip()
        except Exception:
            continue
        if title in SKIP_TITLES:
            continue
        if any(kw in title for kw in SKIP_KEYWORDS):
            continue
        # 내용 미리보기도 확인
        preview_el = link.evaluate_handle(
            "el => el.closest('.info_editor')?.querySelector('.inner_layer')"
        )
        try:
            preview = preview_el.as_element().text_content() if preview_el else ''
        except Exception:
            preview = ''
        if '[내용 없음]' == (preview or '').strip():
            continue
        if title in published_titles:
            continue  # 방금 삭제 못 한 경우 스킵

        _log(f"[{blog_id}] 드래프트 로드: {title}")
        link.click()
        time.sleep(5)
        return 'loaded'

    _log(f"[{blog_id}] 유효한 임시저장 글 없음")
    return None


def _tistory_wait_editor(page):
    """TinyMCE 에디터 로드 대기."""
    for _ in range(20):
        ready = page.evaluate("""() =>
            !!(window.tinymce && tinymce.activeEditor &&
               tinymce.activeEditor.getContent)
        """)
        if ready:
            return True
        time.sleep(1)
    return False


def _tistory_check_and_fix(page, blog_id: str, post_id: str):
    """TinyMCE 에디터에서 이미지/애드센스 체크 후 보완."""
    # 에디터 로드 대기
    if not _tistory_wait_editor(page):
        _log(f"[{blog_id}] TinyMCE 로드 실패")
        return False

    content = page.evaluate("() => tinymce.activeEditor.getContent()")
    title_el = page.query_selector('#post-title-inp') or page.query_selector('#title')
    title = title_el.input_value() if title_el else f"post-{post_id}"
    _log(f"[{blog_id}] 제목: {title}")
    _log(f"[{blog_id}] 콘텐츠 길이: {len(content)}자")

    # 이미지 체크 (Tistory [##_Image 형식 포함)
    has_images = '<img' in content or '[##_Image' in content
    _log(f"[{blog_id}] 이미지 있음: {has_images}")

    # 애드센스 체크 (Tistory 서식 삽입 시 나타나는 class/data 속성)
    has_adsense = bool(
        re.search(r'adsbygoogle|tistory-ad|data-ad|애드센스', content, re.IGNORECASE)
    )
    _log(f"[{blog_id}] 애드센스 있음: {has_adsense}")

    # 이미지 보완 — 없으면 loremflickr로 2개 생성 후 업로드
    if not has_images:
        _log(f"[{blog_id}] 이미지 없음 → 생성·업로드 중...")
        slug = re.sub(r'[^\w가-힣]', '-', title.strip()).strip('-')[:30]
        for i in range(1, 3):
            fp = _make_image(title, f"{blog_id}-{slug}-{i}.jpg")
            if fp:
                # 에디터 커서를 콘텐츠 앞/뒤로 이동 후 이미지 삽입
                if i == 1:
                    page.evaluate("""() => {
                        const ed = tinymce.activeEditor;
                        ed.selection.select(ed.getBody(), true);
                        ed.selection.collapse(true);  // 맨 앞
                    }""")
                ok = _tistory_upload_image(page, fp, alt=title, on_log=_log)
                if ok:
                    _log(f"[{blog_id}] 이미지 {i} 업로드 성공")
                    time.sleep(2)

    # 애드센스 보완
    if not has_adsense:
        _log(f"[{blog_id}] 애드센스 없음 → 서식 삽입 중...")
        # 에디터 중간 위치로 커서 이동 후 삽입
        page.evaluate("""() => {
            const ed = tinymce.activeEditor;
            const body = ed.getBody();
            const paras = body.querySelectorAll('p, h2, h3');
            if (paras.length > 2) {
                const mid = Math.floor(paras.length / 2);
                ed.selection.select(paras[mid], true);
                ed.selection.collapse(true);
            }
        }""")
        ok = _tistory_insert_adsense_format(page, _log)
        if ok:
            _log(f"[{blog_id}] 애드센스 삽입 성공")
            time.sleep(1)

    # 태그 추가 (비어있으면 제목 키워드로 자동 추가)
    current_tags = page.evaluate("() => document.getElementById('tagText')?.value || ''")
    if not current_tags.strip():
        words = re.findall(r'[가-힣]{2,6}', title)
        auto_tags = list(dict.fromkeys(words))[:7]  # 중복제거, 최대 7개
        _log(f"[{blog_id}] 태그 자동 추가: {auto_tags}")
        page.evaluate("""(tags) => {
            const el = document.getElementById('tagText');
            if (!el) return;
            tags.forEach(kw => {
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(el, kw);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', keyCode: 13, bubbles: true}));
                el.dispatchEvent(new KeyboardEvent('keypress', {key: 'Enter', keyCode: 13, bubbles: true}));
                el.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', keyCode: 13, bubbles: true}));
            });
        }""", auto_tags)
        time.sleep(1)

    return True


def _tistory_publish_private(page, blog_id: str) -> bool:
    """Tistory 에디터에서 공개 발행."""
    _log(f"[{blog_id}] 공개 발행 시작...")

    # 1. 완료 버튼 클릭 (발행 다이얼로그 열기)
    clicked = page.evaluate("""() => {
        const candidates = [
            document.querySelector('#publish-layer-btn'),
            document.querySelector('#btn-submit'),
            document.querySelector('#publish-btn'),
            document.querySelector('.btn_publish'),
            ...[...document.querySelectorAll('button, a')]
                .filter(el => ['완료', '발행', '게시'].includes(el.textContent.trim()))
        ];
        for (const el of candidates) {
            if (el) { el.click(); return el.textContent.trim(); }
        }
        return null;
    }""")
    if not clicked:
        _log(f"[{blog_id}] 발행/완료 버튼 없음")
        return False
    _log(f"[{blog_id}] '{clicked}' 버튼 클릭")
    time.sleep(2)

    # 2. 공개 라디오 선택 (open20 = 공개)
    page.evaluate("""() => {
        const r = document.getElementById('open20');
        if (r) { r.click(); r.checked = true; return; }
        // 폴백: 라벨 텍스트로 찾기
        const labels = [...document.querySelectorAll('label')];
        const pub = labels.find(l => l.textContent.trim() === '공개');
        if (pub) pub.click();
    }""")
    time.sleep(1)

    # 3. 공개 발행 버튼 클릭
    confirmed = page.evaluate("""() => {
        const labels = ['공개 발행', '발행하기', '발행', '확인', '게시'];
        const btns = [...document.querySelectorAll('button')];
        for (const lbl of labels) {
            const btn = btns.find(b => b.textContent.trim() === lbl && !b.disabled);
            if (btn) { btn.click(); return lbl; }
        }
        return null;
    }""")
    if confirmed:
        _log(f"[{blog_id}] 발행 버튼: '{confirmed}'")
        time.sleep(3)
    else:
        _log(f"[{blog_id}] 발행 버튼 없음 — 임시저장으로 저장됨")
        page.evaluate("""() => {
            const btn = [...document.querySelectorAll('button')]
                .find(b => b.textContent.includes('임시저장'));
            if (btn) btn.click();
        }""")
        time.sleep(2)
        return False

    # 4. 성공 확인 (URL 변경 또는 알림)
    time.sleep(2)
    cur_url = page.url
    _log(f"[{blog_id}] 최종 URL: {cur_url}")
    return "manage/newpost" not in cur_url or "?post=" in cur_url


def publish_tistory_draft(blog_id: str) -> bool:
    _log(f"── {blog_id} (Tistory) 드래프트 처리 시작 ──")
    account = ACCOUNT_MAP.get(blog_id)
    if not account:
        _log(f"[{blog_id}] ACCOUNT_MAP에 없음")
        return False

    # 로그인
    ok = login_blog(blog_id, on_log=_log)
    if not ok:
        _log(f"[{blog_id}] 로그인 실패")
        return False
    time.sleep(2)

    pw, browser = connect_cdp(on_log=_log)
    try:
        page = get_or_create_page(browser)

        # 임시저장 게시물 로드 (에디터 드래프트 목록에서 직접 로드)
        draft_id = _tistory_get_draft_id(page, blog_id)
        if not draft_id:
            _log(f"[{blog_id}] 임시저장 글 없음 — 스킵")
            return False

        # 로그인 상태 확인
        if "accounts.kakao.com" in page.url or "auth/login" in page.url:
            _log(f"[{blog_id}] 로그인 필요 — 중단")
            return False

        # TinyMCE 로드 대기
        time.sleep(2)

        # 이미지/애드센스 체크 및 보완
        if not _tistory_check_and_fix(page, blog_id, draft_id):
            return False

        # 공개 발행
        ok = _tistory_publish_private(page, blog_id)
        if ok:
            _log(f"[{blog_id}] ✓ 공개 발행 완료")
            # 색인 요청: 최신 발행글 URL 가져오기
            try:
                time.sleep(3)
                page.goto(f"https://{blog_id}.tistory.com/manage/posts/", wait_until="domcontentloaded", timeout=20000)
                time.sleep(2)
                latest_url = page.evaluate("""() => {
                    const a = document.querySelector('table a[href*="/' + location.hostname.split('.')[0] + '"]') ||
                              document.querySelector('.list_post a[href]') ||
                              document.querySelector('td a[href*="tistory.com"]');
                    return a ? a.href : null;
                }""")
                if not latest_url:
                    # Fallback: check links with numeric path
                    latest_url = page.evaluate("""() => {
                        const links = document.querySelectorAll('a[href]');
                        for (const a of links) {
                            if (/tistory\\.com\\/\\d+/.test(a.href)) return a.href;
                        }
                        return null;
                    }""")
                if latest_url:
                    request_indexing(latest_url)
            except Exception as e:
                _log(f"[{blog_id}] 색인 요청 실패: {e}")
        else:
            _log(f"[{blog_id}] 발행 불확실 — manage/posts 확인 필요")
        return ok

    finally:
        pw.stop()


# ══════════════════════════════════════════════
# Naver (salim1su)
# ══════════════════════════════════════════════
def _naver_get_draft(page, blog_id: str) -> bool:
    """Naver 에디터를 열고, 임시저장 팝업에서 첫 번째 유효한 드래프트를 로드.
    성공 시 True 반환 (이미 에디터에 로드됨). 없으면 False."""
    from config import ACCOUNT_MAP
    editor_url = ACCOUNT_MAP.get(blog_id, {}).get("editor_url",
                                                   f"https://blog.naver.com/{blog_id}/postwrite")
    _log(f"[{blog_id}] 에디터 이동: {editor_url}")
    page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)

    if "nidlogin" in page.url or "nid.naver.com" in page.url:
        _log(f"[{blog_id}] 로그인 필요 — 중단")
        return False

    # 임시저장 개수 버튼 클릭
    opened = page.evaluate("""() => {
        const btn = document.querySelector('.save_count_btn__ZTLNa, [class*="save_count_btn"]');
        if (btn && parseInt(btn.textContent.trim()) > 0) {
            btn.click();
            return parseInt(btn.textContent.trim());
        }
        return 0;
    }""")
    if not opened:
        _log(f"[{blog_id}] 임시저장 글 없음 (버튼 0 또는 없음)")
        return False

    _log(f"[{blog_id}] 임시저장 {opened}개 — 팝업 오픈")
    time.sleep(2)

    # 이미 발행된 글 목록 (중복 방지)
    published_titles = _get_published_titles(blog_id, 'naver')

    SKIP = {'제목 없음', ''}

    # --- 1단계: 중복 드래프트 삭제 ---
    if published_titles:
        def _accept_naver(d): d.accept()
        page.on("dialog", _accept_naver)
        try:
            duplicates = page.evaluate("""(publishedSet) => {
                var lis = document.querySelectorAll('li');
                var found = [];
                for (var i = 0; i < lis.length; i++) {
                    var titleEl = lis[i].querySelector('[class*="title__"]');
                    var delBtn = lis[i].querySelector('[class*="delete_button"], [title="삭제"]');
                    if (titleEl && delBtn) {
                        var t = titleEl.textContent.trim();
                        if (publishedSet.includes(t)) found.push(t);
                    }
                }
                return found;
            }""", list(published_titles))
            for dup_title in duplicates:
                _log(f"[{blog_id}] 중복 삭제: '{dup_title}'")
                page.evaluate("""(dupTitle) => {
                    var lis = document.querySelectorAll('li');
                    for (var i = 0; i < lis.length; i++) {
                        var titleEl = lis[i].querySelector('[class*="title__"]');
                        if (titleEl && titleEl.textContent.trim() === dupTitle) {
                            var delBtn = lis[i].querySelector('[class*="delete_button"], [title="삭제"]');
                            if (delBtn) { delBtn.click(); return true; }
                        }
                    }
                    return false;
                }""", dup_title)
                time.sleep(1.5)
        finally:
            page.remove_listener("dialog", _accept_naver)

    # --- 2단계: 첫 번째 유효 드래프트 로드 ---
    loaded = page.evaluate("""(skipSet, publishedSet) => {
        var lis = document.querySelectorAll('li');
        for (var i = 0; i < lis.length; i++) {
            var titleEl = lis[i].querySelector('[class*="title__"]');
            if (!titleEl) continue;
            var title = titleEl.textContent.trim();
            if (!title || skipSet.includes(title) || publishedSet.includes(title)) continue;
            var clickable = lis[i].querySelector('[class*="article_button"]') || lis[i];
            clickable.click();
            return title;
        }
        return null;
    }""", list(SKIP), list(published_titles))

    if not loaded:
        _log(f"[{blog_id}] 유효한 임시저장 글 없음 (모두 발행됨이거나 비어있음)")
        return False

    _log(f"[{blog_id}] 드래프트 로드: {loaded}")
    time.sleep(4)
    return True


def _naver_open_draft_in_editor(page, blog_id: str, draft_url: str) -> bool:
    """임시저장 글을 Naver Smart Editor로 열기."""
    # postview → edit URL로 변환 시도
    # https://blog.naver.com/{blogId}/{logNo} → postwrite URL
    m = re.search(r'logNo=(\d+)|/(\d{5,})', draft_url)
    if m:
        log_no = m.group(1) or m.group(2)
        edit_url = (
            f"https://blog.naver.com/{blog_id}/postwrite?logNo={log_no}"
        )
        _log(f"[{blog_id}] 편집 URL: {edit_url}")
        page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
    else:
        _log(f"[{blog_id}] 편집 URL 변환 실패, 원본 URL 사용: {draft_url}")
        page.goto(draft_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)
    return True


def _naver_check_editor_content(page) -> dict:
    """Naver Smart Editor 콘텐츠 확인."""
    result = page.evaluate("""() => {
        const content = document.body.innerText || '';
        const hasImages = !!document.querySelector(
            '.se-image-resource, .se-module-image, img[src*="blogfiles"], img[src*="postfiles"]'
        );
        const hasAdsense = content.includes('애드센스') || content.includes('adsbygoogle');
        const titleEl = document.querySelector('.se-documentTitle .se-text-paragraph, #title');
        const title = titleEl ? titleEl.innerText : '';
        return { hasImages, hasAdsense, title, length: content.length };
    }""")
    return result or {}


def _naver_publish_public(page) -> bool:
    """Naver Smart Editor에서 공개 발행."""
    # 발행 버튼 클릭
    clicked = page.evaluate("""() => {
        const btn = document.querySelector('button[class*="publish_btn"]')
                 || [...document.querySelectorAll('button')].find(b => b.textContent.trim() === '발행');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    if not clicked:
        _log("[Naver] 발행 버튼 없음")
        return False
    time.sleep(2)

    # 발행 팝업 대기
    try:
        page.wait_for_selector('[class*="layer_popup"][class*="isShow"], [class*="isShow__"]', timeout=5000)
    except Exception:
        pass

    # 공개 옵션 선택 (공개 라디오 버튼)
    page.evaluate("""() => {
        const inputs = [...document.querySelectorAll('input[type="radio"]')];
        const pub = inputs.find(r => {
            const v = (r.value || r.id || '').toLowerCase();
            return v.includes('public') || v.includes('all') || v === '1' || v === 'open';
        });
        if (pub) { pub.click(); return; }
        // 텍스트로 "전체공개" 또는 "공개" 찾기
        const labels = [...document.querySelectorAll('label, span, li, a')];
        const pubLabel = labels.find(el => {
            const t = el.textContent.trim();
            return t === '전체공개' || t === '공개' || t === '전체 공개';
        });
        if (pubLabel) pubLabel.click();
    }""")
    time.sleep(1)

    # 발행 확인 버튼
    confirmed = page.evaluate("""() => {
        const labels = ['발행', '확인', '게시', '등록'];
        const btns = [...document.querySelectorAll(
            '[class*="isShow__"] button, [class*="layer_popup"] button, button'
        )];
        for (const lbl of labels) {
            const btn = btns.find(b => b.textContent.trim() === lbl && !b.disabled);
            if (btn) { btn.click(); return lbl; }
        }
        return null;
    }""")
    if confirmed:
        _log(f"[Naver] 발행 확인: '{confirmed}'")
        time.sleep(3)
        return True
    _log("[Naver] 발행 확인 버튼 없음")
    return False


def publish_naver_draft(blog_id="salim1su") -> bool:
    _log(f"── {blog_id} (Naver) 드래프트 처리 시작 ──")

    ok = login_blog(blog_id, on_log=_log)
    if not ok:
        _log(f"[{blog_id}] 로그인 실패")
        return False
    time.sleep(2)

    pw, browser = connect_cdp(on_log=_log)
    try:
        page = get_or_create_page(browser)

        # 임시저장 드래프트 로드 (에디터 내 save_count_btn 방식)
        loaded = _naver_get_draft(page, blog_id)
        if not loaded:
            _log(f"[{blog_id}] 임시저장 글 없음 — 스킵")
            return False

        if "nidlogin" in page.url or "nid.naver.com" in page.url:
            _log(f"[{blog_id}] 로그인 만료 — 중단")
            return False

        # 에디터 로드 대기
        try:
            page.wait_for_selector(".se-content, .se-editor", timeout=20000)
        except Exception:
            _log(f"[{blog_id}] Naver 에디터 로드 실패")
            return False
        time.sleep(3)

        # 콘텐츠 확인
        info = _naver_check_editor_content(page)
        _log(f"[{blog_id}] 제목: {info.get('title','?')}")
        _log(f"[{blog_id}] 이미지: {info.get('hasImages')}, 글자수: {info.get('length','?')}")

        # 글자수 체크
        if info.get('length', 0) < 1700:
            _log(f"[{blog_id}] 글자수 부족({info.get('length')}자) — 스킵")
            return False

        # 공개 발행
        ok = _naver_publish_public(page)
        if ok:
            _log(f"[{blog_id}] ✓ 공개 발행 완료")
            # 색인 요청: 발행 후 URL 캡처
            try:
                time.sleep(3)
                post_url = page.url
                if "PostView" in post_url or f"blog.naver.com/{blog_id}" in post_url:
                    request_indexing(post_url)
            except Exception as e:
                _log(f"[{blog_id}] 색인 요청 실패: {e}")
        else:
            _log(f"[{blog_id}] 발행 불확실 — 확인 필요")
        return ok

    finally:
        pw.stop()


# ══════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════
if __name__ == "__main__":
    import random
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    results = {}

    # 블로그 순서 랜덤화 (봇 티 방지)
    blog_order = ["baremi542", "goodisak", "nolja100", "salim1su"]
    random.shuffle(blog_order)
    _log(f"발행 순서: {blog_order}")

    for blog_id in blog_order:
        if target not in ("all", blog_id):
            continue

        if blog_id == "baremi542":
            results["baremi542"] = publish_wp_draft()
        elif blog_id == "goodisak":
            results["goodisak"] = publish_tistory_draft("goodisak")
        elif blog_id == "nolja100":
            results["nolja100"] = publish_tistory_draft("nolja100")
        elif blog_id == "salim1su":
            results["salim1su"] = publish_naver_draft("salim1su")

        # 발행 간격: 12600~14400초 사이 랜덤 (3.5~4시간)
        if blog_id != blog_order[-1] and target == "all":
            gap = random.randint(12600, 14400)
            _log(f"다음 발행까지 대기: {gap//3600}시간 {(gap%3600)//60}분")
            time.sleep(gap)

    print("\n" + "=" * 50)
    print("[최종 결과]")
    for blog, ok in results.items():
        status = "✅ 비공개 발행 완료" if ok else "⚠ 처리 불완전 (확인 필요)"
        print(f"  {blog}: {status}")
    print("=" * 50)
