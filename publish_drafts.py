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
# Tistory (goodisak / nolja100)
# ══════════════════════════════════════════════
def _tistory_get_draft_id(page, blog_id: str) -> str | None:
    """Tistory 관리 포스트 목록에서 가장 최근 임시저장 게시물 ID 반환."""
    manage_url = f"https://{blog_id}.tistory.com/manage/posts"
    _log(f"[{blog_id}] 포스트 목록 이동: {manage_url}")
    page.goto(manage_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    # JavaScript로 임시저장 글 링크 추출
    draft_id = page.evaluate("""() => {
        // 임시저장 뱃지/상태 텍스트를 찾아 해당 행의 편집 링크에서 ID 추출
        const rows = document.querySelectorAll('tr, li, .item, [class*="post"]');
        for (const row of rows) {
            const text = row.textContent || '';
            if (text.includes('임시저장') || text.includes('draft')) {
                // /manage/newpost/{id} 패턴 링크 찾기
                const link = row.querySelector('a[href*="/manage/newpost/"]');
                if (link) {
                    const m = link.href.match(/newpost\\/(\d+)/);
                    if (m) return m[1];
                }
            }
        }
        // 폴백: 페이지 전체에서 임시저장 관련 edit 링크 탐색
        const allLinks = document.querySelectorAll('a[href*="/manage/newpost/"]');
        for (const a of allLinks) {
            const row = a.closest('tr, li, .item') || a.parentElement;
            if (row && (row.textContent.includes('임시저장') || row.textContent.includes('draft'))) {
                const m = a.href.match(/newpost\\/(\d+)/);
                if (m) return m[1];
            }
        }
        return null;
    }""")

    if draft_id:
        _log(f"[{blog_id}] 임시저장 ID: {draft_id}")
        return draft_id

    # 폴백: URL 파라미터로 임시저장 필터
    draft_url = f"https://{blog_id}.tistory.com/manage/posts?type=1"
    _log(f"[{blog_id}] 폴백 URL 시도: {draft_url}")
    page.goto(draft_url, wait_until="domcontentloaded", timeout=20000)
    time.sleep(2)
    draft_id = page.evaluate("""() => {
        const links = document.querySelectorAll('a[href*="/manage/newpost/"]');
        if (links.length > 0) {
            const m = links[0].href.match(/newpost\\/(\d+)/);
            return m ? m[1] : null;
        }
        return null;
    }""")
    if draft_id:
        _log(f"[{blog_id}] 폴백으로 임시저장 ID: {draft_id}")
    return draft_id


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
    title_el = page.query_selector('#title')
    title = title_el.input_value() if title_el else f"post-{post_id}"
    _log(f"[{blog_id}] 제목: {title}")
    _log(f"[{blog_id}] 콘텐츠 길이: {len(content)}자")

    # 이미지 체크
    has_images = '<img' in content
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

    return True


def _tistory_publish_private(page, blog_id: str) -> bool:
    """Tistory 에디터에서 비공개 발행."""
    _log(f"[{blog_id}] 비공개 발행 시작...")

    # 1. 완료/발행 버튼 클릭 — 여러 셀렉터 시도
    clicked = page.evaluate("""() => {
        const candidates = [
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

    # 2. 비공개 옵션 선택
    set_private = page.evaluate("""() => {
        // 라디오 버튼 또는 라벨로 비공개 설정
        const selectors = [
            'input[value="private"]',
            'input[id*="private"]',
            'input[id*="비공개"]',
            'label[for*="private"]',
        ];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) { el.click(); return 'selector:' + sel; }
        }
        // 텍스트로 찾기
        const labels = [...document.querySelectorAll('label, span, button, li, a')];
        const priv = labels.find(el => {
            const t = el.textContent.trim();
            return t === '비공개' || t === '나만보기' || t === '비공개 글';
        });
        if (priv) { priv.click(); return 'text:' + priv.textContent.trim(); }
        return null;
    }""")
    if set_private:
        _log(f"[{blog_id}] 비공개 선택: {set_private}")
        time.sleep(1)
    else:
        _log(f"[{blog_id}] 비공개 옵션 못 찾음 — 그대로 진행")

    # 3. 최종 발행 버튼
    confirmed = page.evaluate("""() => {
        const labels = [
            '발행하기', '발행', '확인', '게시', '저장 후 발행',
            '공개', '비공개 발행', '완료',
        ];
        const btns = [...document.querySelectorAll(
            '.layer-publish button, .publish-layer button, dialog button, ' +
            '.modal button, .popup button, button'
        )];
        for (const lbl of labels) {
            const btn = btns.find(b => b.textContent.trim() === lbl && !b.disabled);
            if (btn) { btn.click(); return lbl; }
        }
        return null;
    }""")
    if confirmed:
        _log(f"[{blog_id}] 발행 확인 버튼: '{confirmed}'")
        time.sleep(3)
    else:
        _log(f"[{blog_id}] 발행 확인 버튼 없음 — 임시저장으로 저장됨")
        # 폴백: 임시저장
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

        # 임시저장 게시물 ID 조회
        draft_id = _tistory_get_draft_id(page, blog_id)
        if not draft_id:
            _log(f"[{blog_id}] 임시저장 글 없음 — 스킵")
            return False

        # 편집 페이지 이동
        edit_url = f"https://{blog_id}.tistory.com/manage/newpost/{draft_id}"
        _log(f"[{blog_id}] 편집 페이지: {edit_url}")
        page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)

        # 로그인 상태 확인
        if "accounts.kakao.com" in page.url or "auth/login" in page.url:
            _log(f"[{blog_id}] 로그인 필요 — 중단")
            return False

        # iframe 로드 대기
        try:
            page.wait_for_selector("#editor-tistory_ifr", timeout=15000)
        except Exception:
            _log(f"[{blog_id}] 에디터 iframe 로드 실패")
            return False
        time.sleep(3)

        # 이미지/애드센스 체크 및 보완
        if not _tistory_check_and_fix(page, blog_id, draft_id):
            return False

        # 비공개 발행
        ok = _tistory_publish_private(page, blog_id)
        if ok:
            _log(f"[{blog_id}] ✓ 비공개 발행 완료")
        else:
            _log(f"[{blog_id}] 비공개 발행 불확실 — 임시저장 상태")
        return ok

    finally:
        pw.stop()


# ══════════════════════════════════════════════
# Naver (salim1su)
# ══════════════════════════════════════════════
def _naver_get_draft(page, blog_id: str) -> str | None:
    """Naver 블로그 임시저장 글 편집 URL 반환."""
    # 네이버 임시저장 목록
    for draft_url in [
        f"https://blog.naver.com/{blog_id}?redirect=DraftBox",
        f"https://blog.naver.com/PostTempList.nhn?blogId={blog_id}",
        f"https://blog.naver.com/{blog_id}/manage/posts/temporary",
    ]:
        _log(f"[{blog_id}] 임시저장 목록 시도: {draft_url}")
        try:
            page.goto(draft_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)
            if "nidlogin" in page.url or "nid.naver.com" in page.url:
                _log(f"[{blog_id}] 로그인 필요 — 중단")
                return None

            # postwrite/{id} 링크 탐색
            post_url = page.evaluate("""() => {
                const links = [...document.querySelectorAll('a[href*="postview"],'
                    + 'a[href*="EditPost"],'
                    + 'a[href*="postwrite"]')];
                if (links.length > 0) return links[0].href;
                // iframe 내부도 탐색
                try {
                    const f = document.querySelector('iframe#mainFrame');
                    if (f) {
                        const inner = [...f.contentDocument.querySelectorAll(
                            'a[href*="postview"], a[href*="EditPost"], a[href*="postwrite"]')];
                        if (inner.length > 0) return inner[0].href;
                    }
                } catch(e) {}
                return null;
            }""")
            if post_url:
                _log(f"[{blog_id}] 임시저장 글 URL: {post_url}")
                return post_url
        except Exception as e:
            _log(f"[{blog_id}] {draft_url} 접근 실패: {e}")
    return None


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


def _naver_publish_private(page) -> bool:
    """Naver Smart Editor에서 비공개 발행."""
    # 발행 버튼 클릭
    pub_btn = page.query_selector('button[class*="publish_btn"]')
    if not pub_btn:
        pub_btn_js = page.evaluate("""() => {
            const btns = [...document.querySelectorAll('button')];
            const btn = btns.find(b => b.textContent.includes('발행'));
            if (btn) { btn.click(); return true; }
            return false;
        }""")
        if not pub_btn_js:
            _log("[Naver] 발행 버튼 없음")
            return False
    else:
        pub_btn.click()
    time.sleep(2)

    # 발행 팝업에서 비공개 선택
    set_private = page.evaluate("""() => {
        // 비공개/나만보기 옵션 클릭
        const options = [...document.querySelectorAll('label, span, button, li, a, input')];
        const priv = options.find(el => {
            const t = el.textContent.trim();
            return t === '비공개' || t === '나만보기' || el.value === 'only_me';
        });
        if (priv) { priv.click(); return 'found:' + (priv.textContent.trim() || priv.value); }
        // input[type=radio] 중 value/id가 private 관련인 것
        const radios = [...document.querySelectorAll('input[type="radio"]')];
        const privRadio = radios.find(r =>
            ['private', 'only_me', '비공개', 'onlyMe'].includes(r.value || r.id || '')
        );
        if (privRadio) { privRadio.click(); return 'radio:' + privRadio.value; }
        return null;
    }""")
    if set_private:
        _log(f"[Naver] 비공개 선택: {set_private}")
        time.sleep(1)
    else:
        _log("[Naver] 비공개 옵션 못 찾음 — 기본 설정으로 진행")

    # 발행 확인 버튼
    confirmed = page.evaluate("""() => {
        const labels = ['발행', '확인', '저장', '등록', '게시'];
        const btns = [...document.querySelectorAll(
            '[class*="layer_popup"] button, [class*="popup"] button, ' +
            '[class*="modal"] button, button'
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
        draft_url = _naver_get_draft(page, blog_id)
        if not draft_url:
            _log(f"[{blog_id}] 임시저장 글 없음 — 스킵")
            return False

        # 에디터로 열기
        _naver_open_draft_in_editor(page, blog_id, draft_url)

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
        _log(f"[{blog_id}] 이미지: {info.get('hasImages')}, 애드센스: {info.get('hasAdsense')}")

        # 비공개 발행
        ok = _naver_publish_private(page)
        if ok:
            _log(f"[{blog_id}] ✓ 비공개 발행 완료")
        else:
            _log(f"[{blog_id}] 발행 불확실 — 임시저장 상태 유지")
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
