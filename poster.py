"""멀티 계정 순환 포스팅 — 로그인 → 글 작성 → 임시저장 → 로그아웃"""
import time
import re
import random
import base64
import os
from pathlib import Path
from browser import connect_cdp, get_or_create_page
from config import ACCOUNTS, ACCOUNT_MAP
from login_playwright import login_blog, logout_blog
from content_builder import insert_adsense_markers


def _rand_delay(page, min_ms=500, max_ms=1500):
    page.wait_for_timeout(random.randint(min_ms, max_ms))


def _chunked_type(page, text, chunk_size=50, delay_per_char=None):
    """긴 텍스트를 chunk_size 글자씩 나눠서 keyboard.type() 한다.

    네이버 에디터에서 긴 텍스트를 한번에 type()하면
    포커스를 잃거나 중간에 누락되는 문제를 방지.
    - 50자씩 분할
    - 청크 사이 0.3초 대기
    - 매 5청크마다 본문 영역 클릭으로 포커스 유지
    """
    if delay_per_char is None:
        delay_per_char = random.randint(10, 30)

    chunk_count = 0
    for i in range(0, len(text), chunk_size):
        # 매 5청크마다 포커스 재확인
        if chunk_count > 0 and chunk_count % 5 == 0:
            try:
                body_p = page.query_selector(
                    '.se-component.se-text .se-text-paragraph'
                )
                if body_p:
                    # 네이버 에디터 본문 영역 클릭으로 포커스 복구
                    body_p.click()
                    time.sleep(0.2)
            except Exception:
                pass

        chunk = text[i:i + chunk_size]
        page.keyboard.type(chunk, delay=delay_per_char)
        chunk_count += 1
        time.sleep(0.3)  # 청크 사이 0.3초 대기


# .env에서 애드센스 코드 읽기
_env_path = Path(__file__).parent / ".env"
_adsense_pub = ""
_adsense_slot = ""
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("ADSENSE_CODE="):
            _adsense_pub = line.split("=", 1)[1].strip()
        if line.startswith("ADSENSE_SLOT="):
            _adsense_slot = line.split("=", 1)[1].strip()


# ─────────────────────────────────────────────
# 헬퍼: HTML → 마커 변환
# ─────────────────────────────────────────────
def _html_to_markers(body_html: str) -> str:
    """HTML 본문을 ##H2:##, ##H3:##, ##AD##, ##TABLE:N## 마커로 변환"""
    text = body_html

    # H2/H3 → 마커
    text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'##H2:\1##', text, flags=re.DOTALL)
    text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'##H3:\1##', text, flags=re.DOTALL)

    # 애드센스 블록 → ##AD##
    text = re.sub(
        r'<!--\s*AdSense.*?-->.*?(?=<h2|<p|$)',
        '##AD##\n', text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(
        r'<ins\s+class="adsbygoogle"[^>]*>.*?</ins>',
        '##AD##', text, flags=re.DOTALL
    )

    # 테이블 보존
    _table_store = []

    def _preserve_table(m):
        _table_store.append(m.group(0))
        return f'##TABLE:{len(_table_store) - 1}##'

    text = re.sub(r'<table[^>]*>.*?</table>', _preserve_table, text, flags=re.DOTALL)

    # bold/italic → 마크다운
    text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<b>(.*?)</b>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<em>(.*?)</em>', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'<i>(.*?)</i>', r'*\1*', text, flags=re.DOTALL)

    # 줄바꿈 변환
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</(?:p|div|li|tr)>', '\n', text)

    # 나머지 HTML 태그 제거
    text = re.sub(r'<[^>]+>', '', text)

    # 마크다운 제목 변환
    text = re.sub(r'^###\s+(.+)$', r'##H3:\1##', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+(.+)$', r'##H2:\1##', text, flags=re.MULTILINE)

    # 연속 빈줄 정리
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip(), _table_store


def _get_adsense_html():
    """실제 애드센스 HTML 반환"""
    pub = _adsense_pub or "ca-pub-XXXXXXXX"
    slot = _adsense_slot or "XXXXXXXX"
    return (
        '<div class="ad-container" style="margin:1.5em 0;text-align:center;">'
        f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={pub}" crossorigin="anonymous"></script>'
        f'<ins class="adsbygoogle" style="display:block;text-align:center;" '
        f'data-ad-layout="in-article" data-ad-format="fluid" '
        f'data-ad-client="{pub}" data-ad-slot="{slot}"></ins>'
        '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>'
        '</div><p>&nbsp;</p>'
    )


# ─────────────────────────────────────────────
# 헬퍼: 이미지를 base64로 TinyMCE에 삽입
# ─────────────────────────────────────────────
def _insert_image_into_tinymce(page, filepath: str, alt: str = ""):
    """이미지 파일을 base64로 인코딩하여 TinyMCE insertContent로 삽입"""
    if not os.path.exists(filepath):
        return False

    with open(filepath, "rb") as f:
        data = base64.b64encode(f.read()).decode()

    ext = Path(filepath).suffix.lstrip(".")
    mime = {"webp": "image/webp", "png": "image/png", "jpg": "image/jpeg",
            "jpeg": "image/jpeg"}.get(ext, "image/webp")

    img_html = (
        f'<p><img src="data:{mime};base64,{data}" '
        f'alt="{alt}" style="max-width:100%;height:auto;" /></p>'
        '<p>&nbsp;</p>'
    )
    page.evaluate(
        "(html) => { if(tinymce.activeEditor) tinymce.activeEditor.insertContent(html); }",
        img_html,
    )
    time.sleep(0.5)
    return True


# ─────────────────────────────────────────────
# 마크다운 표 → HTML 변환
# ─────────────────────────────────────────────
def _markdown_table_to_html(lines: list) -> str:
    """마크다운 표를 HTML <table>로 변환"""
    if len(lines) < 2:
        return ""
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    # 구분선(---|---) 제거
    rows = [r for r in rows if not all(set(c.strip()) <= {'-', ':'} for c in r)]
    if not rows:
        return ""

    html = '<table style="border-collapse:collapse;width:100%;margin:1em 0;" border="1" cellpadding="8" cellspacing="0">'
    # 첫 줄 = 헤더
    html += '<thead><tr>'
    for cell in rows[0]:
        html += f'<th style="background:#f5f5f5;padding:8px;border:1px solid #ddd;">{cell}</th>'
    html += '</tr></thead><tbody>'
    for row in rows[1:]:
        html += '<tr>'
        for cell in row:
            html += f'<td style="padding:8px;border:1px solid #ddd;">{cell}</td>'
        html += '</tr>'
    html += '</tbody></table><p>&nbsp;</p>'
    return html


# ─────────────────────────────────────────────
# 티스토리 글 작성 (TinyMCE 기반)
# ─────────────────────────────────────────────
def _post_tistory(account, title, body_html, tags=None,
                  image_paths=None, image_infos=None, on_log=None):
    """티스토리 에디터에서 글 작성 + 임시저장

    Args:
        title: 글 제목
        body_html: HTML 본문
        tags: 태그 리스트
        image_paths: {index: filepath} 이미지 경로
        image_infos: [{"index":1, "section":"...", "alt":"..."}, ...] 이미지 정보
    """
    def log(msg):
        if on_log:
            on_log(msg)

    image_paths = image_paths or {}
    image_infos = image_infos or []

    pw, browser = connect_cdp(on_log)
    try:
        editor_url = account["editor_url"]
        log(f"[포스팅] 에디터 이동: {editor_url}")
        page = get_or_create_page(browser, navigate_to=editor_url)
        _rand_delay(page, 3000, 5000)

        # 로그인 확인
        if "accounts.kakao.com" in page.url or "auth/login" in page.url:
            log("[포스팅] 로그인 안 됨 — 중단")
            return False

        # 글 복원 팝업 닫기
        try:
            page.evaluate("""() => {
                const buttons = document.querySelectorAll('button, a');
                for (const btn of buttons) {
                    const text = btn.textContent.trim();
                    if (text.includes('새 글 작성') || text.includes('취소') || text.includes('아니오')) {
                        btn.click();
                        return text;
                    }
                }
                return null;
            }""")
            _rand_delay(page, 1000, 2000)
        except Exception:
            pass

        # ── 에디터 로드 대기 ──
        page.wait_for_selector("#post-title-inp, .tit_post input", timeout=15000)
        log("[포스팅] 에디터 로드 완료")

        # ── 제목 입력 (keyboard.type) ──
        log(f"[포스팅] 제목 입력: {title[:30]}...")
        title_el = page.query_selector("#post-title-inp") or page.query_selector(".tit_post input")
        title_el.click()
        _rand_delay(page, 300, 600)
        title_el.type(title, delay=random.randint(40, 120))
        _rand_delay(page, 500, 1000)

        # ── TinyMCE iframe 진입 ──
        log("[포스팅] 본문 입력 중...")
        page.wait_for_selector("#editor-tistory_ifr", timeout=15000)
        iframe_el = page.query_selector("#editor-tistory_ifr")
        frame = iframe_el.content_frame()
        body_el = frame.query_selector("body")
        body_el.click()
        _rand_delay(page, 300, 600)

        # 본문을 줄 단위로 처리
        # Claude 응답 형식: ## H2, {{이미지N}}, [애드센스], | 표 |, 일반 텍스트
        blog_id = account.get("blog", "")

        # 애드센스 자동 삽입 (content_builder 규칙 적용)
        body_text = insert_adsense_markers(body_html, blog_id)

        lines = body_text.split('\n')
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if not stripped:
                frame.page.keyboard.press("Enter")
                time.sleep(0.05)
                i += 1
                continue

            # ── ## H2 소제목 ──
            h2_match = re.match(r'^##\s+(.+)$', stripped)
            if h2_match:
                heading = h2_match.group(1).strip()
                heading = re.sub(r'<[^>]+>', '', heading).strip()
                h2_html = f'<h2>{heading}</h2><p>&nbsp;</p>'
                page.evaluate(
                    "(html) => { if(tinymce.activeEditor) tinymce.activeEditor.execCommand('mceInsertContent', false, html); }",
                    h2_html,
                )
                time.sleep(0.5)
                log(f"[포스팅] H2: {heading[:20]}...")
                i += 1
                continue

            # ── | 마크다운 표 ──
            if stripped.startswith("|") and "|" in stripped[1:]:
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                if len(table_lines) >= 2:
                    table_html = _markdown_table_to_html(table_lines)
                    if table_html:
                        page.evaluate(
                            "(html) => { if(tinymce.activeEditor) tinymce.activeEditor.insertContent(html); }",
                            table_html,
                        )
                        time.sleep(0.5)
                        log("[포스팅] 표 삽입 완료")
                        continue
                # 표 변환 실패 시 텍스트로 입력
                for tl in table_lines:
                    _chunked_type(frame.page, tl.strip(), chunk_size=100)
                    frame.page.keyboard.press("Enter")
                    time.sleep(0.1)
                continue

            # ── {{이미지N}} → 이미지 삽입 ──
            img_match = re.match(r'\{\{이미지(\d+)\}\}', stripped)
            if img_match:
                idx = int(img_match.group(1))
                if idx in image_paths:
                    # image_infos에서 alt 찾기
                    alt = ""
                    for info in image_infos:
                        if info["index"] == idx:
                            alt = info.get("alt", "")
                            break
                    ok = _insert_image_into_tinymce(page, image_paths[idx], alt)
                    if ok:
                        log(f"[포스팅] 이미지 {idx} 삽입 완료")
                else:
                    log(f"[포스팅] 이미지 {idx} 파일 없음 — 스킵")
                i += 1
                continue

            # ── [애드센스] → 애드센스 ins 태그 삽입 ──
            if stripped == '[애드센스]' or stripped == '##AD##':
                try:
                    ad_html = _get_adsense_html()
                    page.evaluate(
                        "(html) => { if(tinymce.activeEditor) tinymce.activeEditor.insertContent(html); }",
                        ad_html,
                    )
                    time.sleep(0.5)
                    log("[포스팅] 애드센스 삽입")
                except Exception:
                    pass
                i += 1
                continue

            # ── **볼드**, *이탤릭* → insertContent ──
            if '**' in stripped or re.search(r'(?<!\*)\*(?!\*)', stripped):
                html_line = stripped
                html_line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_line)
                html_line = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', html_line)
                html_line = f'<p>{html_line}</p>'
                page.evaluate(
                    "(html) => { if(tinymce.activeEditor) tinymce.activeEditor.insertContent(html); }",
                    html_line,
                )
                time.sleep(0.2)
                i += 1
                continue

            # ── 일반 텍스트 → keyboard.type (100자씩 분할) ──
            _chunked_type(frame.page, stripped, chunk_size=100)
            frame.page.keyboard.press("Enter")
            time.sleep(random.uniform(0.1, 0.3))
            i += 1

        # TinyMCE 변경 반영
        page.evaluate("""() => {
            if (window.tinymce && tinymce.activeEditor) {
                tinymce.activeEditor.fire('change');
                tinymce.activeEditor.save();
            }
        }""")
        _rand_delay(page, 1000, 2000)
        log("[포스팅] 본문 입력 완료")

        # ── 태그 입력 ──
        if tags:
            log(f"[포스팅] 태그 입력: {tags}")
            try:
                tag_input = page.query_selector("#tagText") or page.query_selector(".tag_post input")
                if tag_input:
                    tag_input.click()
                    time.sleep(0.3)
                    for tag in tags:
                        tag_input.fill("")
                        tag_input.type(tag.strip(), delay=random.randint(40, 100))
                        page.keyboard.press("Enter")
                        time.sleep(random.uniform(0.5, 1.0))
            except Exception:
                log("[포스팅] 태그 입력 실패 — 스킵")

        # ── 임시저장 ──
        log("[포스팅] 임시저장...")
        page.evaluate("""() => {
            const buttons = document.querySelectorAll('button, a, input[type="button"]');
            for (const btn of buttons) {
                const text = btn.textContent.trim();
                if (text === '임시저장' || text.includes('임시저장')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        _rand_delay(page, 3000, 5000)

        log(f"[포스팅] 임시저장 완료: {title[:30]}...")
        return True

    finally:
        pw.stop()


# ─────────────────────────────────────────────
# 네이버 에디터 헬퍼 함수들
# (blog-tool/naver_playwright.py 참고)
# ─────────────────────────────────────────────
def _naver_dismiss_overlays(page):
    """도움말, 팝업 등 오버레이 요소를 닫는다."""
    try:
        page.evaluate("""() => {
            const help = document.querySelector('[class*="container__"]');
            if (help && help.querySelector('.se-help-title')) help.remove();
            document.querySelectorAll('.se-popup-dim').forEach(el => el.remove());
            const closeBtn = document.querySelector(
                '[class*="close_btn"], .se-popup-close-button'
            );
            if (closeBtn) closeBtn.click();
        }""")
        time.sleep(0.5)
    except Exception:
        pass


def _naver_wait_for_image_load(page, max_retries=3):
    """업로드된 이미지가 정상 로드됐는지 확인한다."""
    for attempt in range(max_retries):
        try:
            loaded = page.evaluate("""() => {
                const imgs = document.querySelectorAll(
                    '.se-component.se-image img.se-image-resource'
                );
                if (!imgs.length) return false;
                const last = imgs[imgs.length - 1];
                return last.complete && last.naturalWidth > 0 && last.naturalHeight > 0;
            }""")
            if loaded:
                return True
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return False


def _naver_remove_image_placeholders(page):
    """이미지 업로드 후 자동 삽입되는 캡션을 제거한다."""
    try:
        captions = page.query_selector_all(
            '.se-component.se-image .se-caption .se-text-paragraph'
        )
        for cap in captions:
            cap_text = cap.text_content().strip()
            if not cap_text or cap_text == '사진 설명을 입력하세요.' or \
               'AI 활용' in cap_text or '설명을 입력' in cap_text:
                try:
                    cap.click(timeout=3000)
                    time.sleep(0.2)
                    page.keyboard.press("Meta+a")
                    time.sleep(0.1)
                    page.keyboard.press("Delete")
                    time.sleep(0.1)
                    page.keyboard.press("Escape")
                    time.sleep(0.2)
                except Exception:
                    pass
        page.evaluate("""() => {
            document.querySelectorAll('.se-component.se-image .se-caption')
                .forEach(el => { el.style.display = 'none'; });
        }""")
    except Exception:
        pass


def _naver_upload_image(page, filepath, log_fn=None):
    """네이버 에디터에 이미지 1장을 업로드한다.

    expect_file_chooser 방식:
    1. 사진 버튼 클릭
    2. file chooser 이벤트 감지 → set_files()로 파일 지정
    3. 창 자동 닫힘 + 이미지 업로드
    """
    if not os.path.exists(filepath):
        if log_fn:
            log_fn(f"[포스팅] 이미지 파일 없음: {filepath}")
        return False

    _naver_dismiss_overlays(page)

    # 사진 버튼 찾기
    photo_btn = page.query_selector('.se-image-toolbar-button')
    if not photo_btn:
        photo_btn = page.query_selector('button[data-name="image"]')
    if not photo_btn:
        if log_fn:
            log_fn("[포스팅] 사진 버튼을 찾을 수 없음")
        return False

    try:
        # file chooser 이벤트 감지 + 사진 버튼 클릭
        with page.expect_file_chooser(timeout=10000) as fc_info:
            photo_btn.click(timeout=5000)
        file_chooser = fc_info.value
        file_chooser.set_files(filepath)
        time.sleep(4)

        # 이미지 로드 확인
        _naver_wait_for_image_load(page)
        _naver_remove_image_placeholders(page)

        # 이미지 뒤 본문 영역으로 커서 복귀
        body_ps = page.query_selector_all(
            ".se-component.se-text .se-text-paragraph"
        )
        if body_ps:
            body_ps[-1].click()
            time.sleep(0.3)

        return True

    except Exception as e:
        if log_fn:
            log_fn(f"[포스팅] 이미지 업로드 실패: {e}")
        # fallback: Escape로 다이얼로그 닫기 시도
        try:
            page.keyboard.press("Escape")
            time.sleep(1)
        except Exception:
            pass
        return False


def _naver_apply_subtitle_format(page):
    """현재 줄에 소제목 서식을 적용한다."""
    _naver_dismiss_overlays(page)
    fmt_btn = page.query_selector('.se-text-format-toolbar-button')
    if not fmt_btn:
        fmt_btn = page.query_selector('button[data-name="text-format"]')
    if not fmt_btn:
        return False

    for attempt in range(3):
        try:
            fmt_btn.click()
            time.sleep(0.5)  # 드롭다운 열림 대기 (기존 0.2 → 0.5)
            # 소제목 버튼 폴링 (최대 3초)
            for _ in range(15):
                time.sleep(0.2)
                sub_btn = page.query_selector(
                    'button.se-toolbar-option-text-format-sectionTitle-button'
                )
                if sub_btn and sub_btn.is_visible():
                    sub_btn.click()
                    time.sleep(0.4)
                    return True
            # 드롭다운 미열림 → Escape 후 재시도
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)
    return False


def _naver_restore_body_format(page):
    """서식을 본문(일반 텍스트)으로 복원한다."""
    fmt_btn = page.query_selector('.se-text-format-toolbar-button')
    if not fmt_btn:
        fmt_btn = page.query_selector('button[data-name="text-format"]')
    if not fmt_btn:
        return

    for attempt in range(3):
        try:
            fmt_btn.click()
            time.sleep(0.5)  # 드롭다운 열림 대기 (기존 0.2 → 0.5)
            for _ in range(15):
                time.sleep(0.2)
                text_btn = page.query_selector(
                    'button.se-toolbar-option-text-format-text-button'
                )
                if text_btn and text_btn.is_visible():
                    text_btn.click()
                    time.sleep(0.4)
                    return
            # 드롭다운 미열림 → Escape 후 재시도
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)


def _parse_naver_sections(content):
    """본문을 섹션 단위로 파싱한다.

    Returns: [
        {"type": "intro", "body": "도입부 텍스트"},
        {"type": "heading", "text": "소제목"},
        {"type": "image", "index": 1},
        {"type": "text", "body": "본문 문단"},
        ...
    ]

    ## 소제목 → heading
    {{이미지N}} → image
    [애드센스] / ##AD## → skip
    나머지 → text (문단 단위로 묶음)
    """
    # 마크다운 bold → 제거 (네이버는 plain text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)
    # HTML 태그 제거
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</(?:p|div|h[1-6]|li|tr)>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    # HTML 주석 제거
    text = re.sub(r'<!--.*?-->', '', text)
    # 연속 빈 줄 정리
    text = re.sub(r'\n{3,}', '\n\n', text)

    sections = []
    current_text_lines = []

    def flush_text():
        if current_text_lines:
            body = '\n'.join(current_text_lines).strip()
            if body:
                sections.append({"type": "text", "body": body})
            current_text_lines.clear()

    for line in text.split('\n'):
        stripped = line.strip()

        # 빈 줄 → 문단 구분
        if not stripped:
            current_text_lines.append('')
            continue

        # ## 소제목
        h_match = re.match(r'^#{1,3}\s+(.+)$', stripped)
        if h_match:
            flush_text()
            heading = h_match.group(1).strip()
            heading = re.sub(r'<[^>]+>', '', heading).strip()
            sections.append({"type": "heading", "text": heading})
            continue

        # {{이미지N}}
        img_match = re.match(r'\{\{이미지(\d+)\}\}', stripped)
        if img_match:
            flush_text()
            sections.append({"type": "image", "index": int(img_match.group(1))})
            continue

        # [애드센스] / ##AD## → 네이버는 스킵
        if stripped in ('[애드센스]', '##AD##'):
            continue

        # 일반 텍스트
        current_text_lines.append(stripped)

    flush_text()
    return sections


def _redistribute_images_if_top(sections):
    """이미지가 모두 상단에 몰려 있으면 소제목 사이사이로 균등 분산시킨다."""
    images = [s for s in sections if s["type"] == "image"]
    if not images:
        return sections

    # 마지막 이미지 위치가 전체 섹션 30% 이내이면 분산 필요
    last_img_pos = max(i for i, s in enumerate(sections) if s["type"] == "image")
    if last_img_pos >= len(sections) * 0.3:
        return sections  # 이미 충분히 분산됨

    # 이미지 제외한 기본 섹션
    base = [s for s in sections if s["type"] != "image"]
    if len(base) < 2:
        return sections

    n = len(images)
    total = len(base)

    # 이미지를 base 섹션에 균등 분산 (n+1 등분 지점에 삽입)
    # 예: base 10개, 이미지 3개 → 위치 2, 5, 7
    insert_positions = []
    for j in range(1, n + 1):
        pos = int(j * total / (n + 1))
        pos = max(1, min(pos, total - 1))
        insert_positions.append(pos)

    # 뒤에서 앞으로 삽입 (인덱스 이동 방지)
    result = list(base)
    for j in range(n - 1, -1, -1):
        result.insert(insert_positions[j], images[j])

    return result


# ─────────────────────────────────────────────
# 네이버 글 작성
# ─────────────────────────────────────────────
def _post_naver(account, title, content, tags=None,
                image_paths=None, image_infos=None, on_log=None):
    """네이버 블로그 에디터에서 글 작성 + 발행

    blog-tool/naver_playwright.py 참고:
    - 섹션 단위 파싱 (heading/image/text)
    - 소제목: 서식 변경 → 타이핑 → Enter → 서식 복원
    - 이미지: 사진 버튼 → #hidden-file.set_input_files → 로드 대기
    - 본문: 문단 단위 keyboard.type()
    """
    def log(msg):
        if on_log:
            on_log(msg)

    image_paths = image_paths or {}
    image_infos = image_infos or []
    images_dir = Path(__file__).parent / "images"

    # 애드센스 마커 삽입
    blog_id = account.get("blog", "")
    body_text = insert_adsense_markers(content, blog_id)

    # 본문을 섹션으로 파싱 + 이미지 상단 몰림 방지
    sections = _parse_naver_sections(body_text)
    sections = _redistribute_images_if_top(sections)

    pw, browser = connect_cdp(on_log)
    try:
        editor_url = account["editor_url"]
        log(f"[포스팅] 네이버 에디터 이동: {editor_url}")
        page = get_or_create_page(browser, navigate_to=editor_url)
        _rand_delay(page, 3000, 5000)

        if "nidlogin" in page.url or "nid.naver.com" in page.url:
            log("[포스팅] 로그인 안 됨 — 중단")
            return False

        # 에디터 로드 대기
        page.wait_for_selector(".se-content", timeout=60000)

        # 팝업/도움말 닫기
        time.sleep(1)
        alert_popup = page.query_selector('.se-popup-alert-confirm')
        if alert_popup:
            dismiss_btn = alert_popup.query_selector(
                'button.se-popup-button-cancel, button:last-child'
            )
            if dismiss_btn:
                dismiss_btn.click()
                time.sleep(1)
        help_close = page.query_selector('button.se-help-panel-close-button')
        if help_close:
            help_close.click()
            time.sleep(1)

        # ── 제목 입력 (제목만, 도입부 절대 불포함) ──
        # 제목에서 줄바꿈 제거 + 첫 줄만 사용
        clean_title = title.split('\n')[0].strip()
        log(f"[포스팅] 제목 입력 중: \"{clean_title}\" ({len(clean_title)}자)")
        title_sel = ".se-documentTitle .se-text-paragraph"
        page.wait_for_selector(title_sel, timeout=10000)
        title_el = page.query_selector(title_sel)
        title_el.click()
        time.sleep(0.5)

        # 제목 필드가 비어있는지 확인
        existing = (title_el.text_content() or "").strip()
        if existing:
            log(f"[포스팅] 제목 필드에 기존 텍스트 있음: \"{existing[:30]}\" — 지우고 다시 입력")
            page.keyboard.press("Meta+a")
            time.sleep(0.1)
            page.keyboard.press("Delete")
            time.sleep(0.3)

        _chunked_type(page, clean_title, chunk_size=100)
        time.sleep(0.5)

        # 제목 필드에 입력된 내용 검증
        typed = (title_el.text_content() or "").strip()
        log(f"[포스팅] 제목 입력 확인: \"{typed[:40]}\"")
        time.sleep(random.uniform(0.5, 1.0))

        # ── 본문 영역으로 이동 (Tab이 아닌 직접 클릭) ──
        log("[포스팅] 본문 영역 클릭...")
        body_p = page.query_selector(
            '.se-component.se-text .se-text-paragraph'
        )
        if body_p:
            body_p.click()
        else:
            # fallback: 본문 placeholder 클릭
            page.click('.se-component.se-text')
        time.sleep(random.uniform(0.5, 1.0))

        # 본문 포커스 확인
        in_body = page.evaluate("""() => {
            const sel = window.getSelection();
            const node = sel && sel.focusNode ? sel.focusNode.parentElement : null;
            return node ? !node.closest('.se-documentTitle') : false;
        }""")
        if not in_body:
            log("[포스팅] ⚠ 본문 포커스 실패 — Enter로 이동 시도")
            page.keyboard.press("Escape")
            time.sleep(0.3)
            if body_p:
                body_p.click()
            time.sleep(0.5)

        # ── 섹션별 입력 ──
        for si, section in enumerate(sections):
            stype = section["type"]

            if stype == "heading":
                heading = section["text"]
                log(f"[포스팅] 소제목: {heading[:30]}...")

                # 소제목 앞 빈 줄 (첫 섹션 제외)
                if si > 0:
                    page.keyboard.press("Enter")
                    time.sleep(0.05)
                    page.keyboard.press("Enter")
                    time.sleep(0.05)

                # 소제목 서식 적용 → 타이핑 → Enter → 본문 서식 복원
                _naver_apply_subtitle_format(page)
                _chunked_type(page, heading, chunk_size=50)
                page.keyboard.press("Enter")
                time.sleep(0.5)
                _naver_restore_body_format(page)
                time.sleep(0.3)

                # 소제목 후 본문 영역 재클릭으로 포커스 확보
                body_p = page.query_selector(
                    '.se-component.se-text .se-text-paragraph'
                )
                if body_p:
                    body_ps = page.query_selector_all(
                        '.se-component.se-text .se-text-paragraph'
                    )
                    if body_ps:
                        body_ps[-1].click()
                        time.sleep(0.3)
                page.keyboard.press("Enter")
                time.sleep(0.3)

            elif stype == "image":
                idx = section["index"]
                filepath = image_paths.get(idx)

                # image_paths에 없으면 images 폴더에서 검색
                if not filepath:
                    for info in image_infos:
                        if info["index"] == idx:
                            candidate = images_dir / info.get("filename", "")
                            if candidate.exists():
                                filepath = str(candidate)
                            break

                if filepath and os.path.exists(filepath):
                    log(f"[포스팅] 이미지 {idx} 업로드: {Path(filepath).name}")
                    ok = _naver_upload_image(page, filepath, log)
                    if ok:
                        log(f"[포스팅] 이미지 {idx} 완료")
                    else:
                        log(f"[포스팅] 이미지 {idx} 업로드 실패")
                else:
                    log(f"[포스팅] 이미지 {idx} 파일 없음 — 스킵")

            elif stype == "text":
                body = section["body"]
                # 빈 줄 기준으로 문단 분리
                paragraphs = re.split(r'\n\s*\n', body)
                for pi, para in enumerate(paragraphs):
                    lines = [l for l in para.split('\n') if l.strip()]
                    for li, line in enumerate(lines):
                        stripped = line.strip()
                        # | 마크다운 표 → 텍스트로 입력
                        if stripped.startswith("|") and "|" in stripped[1:]:
                            _chunked_type(page, stripped, chunk_size=50)
                            page.keyboard.press("Enter")
                            time.sleep(0.2)
                            continue
                        _chunked_type(page, stripped, chunk_size=50)
                        if li < len(lines) - 1:
                            page.keyboard.press("Enter")
                            time.sleep(0.1)
                    # 문단 사이 Enter 두 번
                    if pi < len(paragraphs) - 1:
                        page.keyboard.press("Enter")
                        time.sleep(0.1)
                        page.keyboard.press("Enter")
                        time.sleep(0.1)
                # 섹션 끝 Enter
                page.keyboard.press("Enter")
                time.sleep(0.5)

        _rand_delay(page, 1000, 2000)

        # ── 입력 완료 후 에디터 글자수 확인 ──
        try:
            editor_text_len = page.evaluate("""() => {
                const els = document.querySelectorAll('.se-component.se-text .se-text-paragraph');
                let total = 0;
                for (const el of els) {
                    total += (el.textContent || '').length;
                }
                return total;
            }""")
            log(f"[포스팅] 에디터 실제 입력 글자수: {editor_text_len}자")
        except Exception:
            log("[포스팅] 에디터 글자수 확인 실패")
        log("[포스팅] 본문 입력 완료")

        # ── 발행 ──
        log("[포스팅] 발행 버튼 클릭...")
        _naver_dismiss_overlays(page)
        publish_btn = page.query_selector('button[class*="publish_btn"]')
        if not publish_btn:
            log("[포스팅] 발행 버튼을 찾을 수 없음")
            return False
        publish_btn.click()
        _rand_delay(page, 2000, 3000)

        page.wait_for_selector(
            '[class*="layer_popup"][class*="is_show"]', timeout=10000
        )

        if tags:
            log(f"[포스팅] 태그 입력 중: {tags}")
            try:
                tag_input = page.query_selector('#tag-input')
                if tag_input:
                    tag_input.click()
                    time.sleep(0.3)
                    for tag in tags:
                        tag_input.fill("")
                        tag_input.type(tag.strip(), delay=random.randint(40, 100))
                        page.keyboard.press("Enter")
                        time.sleep(random.uniform(0.5, 1.0))
            except Exception:
                log("[포스팅] 태그 입력 실패 — 스킵")

        log("[포스팅] 저장 중...")
        save_btn = page.query_selector('button[class*="save_btn"]')
        if not save_btn:
            log("[포스팅] 저장 버튼을 찾을 수 없음")
            return False
        save_btn.click()
        _rand_delay(page, 3000, 5000)

        log(f"[포스팅] 네이버 포스팅 완료: {title[:30]}...")
        return True

    finally:
        pw.stop()


# ─────────────────────────────────────────────
# 단일 계정 포스팅 (로그인 → 글쓰기 → 로그아웃)
# ─────────────────────────────────────────────
def post_single(blog_id: str, title: str, content: str,
                tags=None, image_paths=None, image_infos=None,
                on_log=None):
    """한 계정에 대해 로그인 → 포스팅 → 로그아웃 전체 수행"""
    def log(msg):
        if on_log:
            on_log(msg)

    account = ACCOUNT_MAP.get(blog_id)
    if not account:
        raise ValueError(f"알 수 없는 블로그: {blog_id}")

    log(f"\n{'='*50}")
    log(f"[순환] {blog_id} ({account['platform']}) 시작")
    log(f"{'='*50}")

    # 1. 로그인
    log(f"[순환] {blog_id} 로그인...")
    ok = login_blog(blog_id, on_log)
    if not ok:
        log(f"[순환] {blog_id} 로그인 실패 — 스킵")
        return False

    _pause(3, 5)

    # 2. 포스팅
    log(f"[순환] {blog_id} 글 작성 시작...")
    if account["platform"] == "tistory":
        ok = _post_tistory(account, title, content, tags,
                           image_paths=image_paths, image_infos=image_infos,
                           on_log=on_log)
    elif account["platform"] == "naver":
        ok = _post_naver(account, title, content, tags,
                         image_paths=image_paths, image_infos=image_infos,
                         on_log=on_log)
    else:
        log(f"[순환] 지원하지 않는 플랫폼: {account['platform']}")
        ok = False

    _pause(2, 4)

    # 3. 로그아웃
    log(f"[순환] {blog_id} 로그아웃...")
    logout_blog(blog_id, on_log)

    _pause(3, 6)

    status = "성공" if ok else "실패"
    log(f"[순환] {blog_id} 완료 ({status})")
    return ok


# ─────────────────────────────────────────────
# 멀티 계정 순환 포스팅
# ─────────────────────────────────────────────
def post_all(keyword: str, contents: dict, tags_map: dict = None,
             on_log=None):
    """모든 계정을 순환하며 포스팅."""
    def log(msg):
        if on_log:
            on_log(msg)

    tags_map = tags_map or {}
    results = {}

    log(f"\n{'#'*50}")
    log(f"# 멀티 계정 순환 포스팅 시작")
    log(f"# 키워드: {keyword}")
    log(f"# 대상: {[a['blog'] for a in ACCOUNTS]}")
    log(f"{'#'*50}")

    for account in ACCOUNTS:
        blog_id = account["blog"]

        if blog_id not in contents:
            log(f"[순환] {blog_id} — 콘텐츠 없음, 스킵")
            results[blog_id] = False
            continue

        data = contents[blog_id]
        tags = tags_map.get(blog_id, [])

        ok = post_single(
            blog_id=blog_id,
            title=data["title"],
            content=data["content"],
            tags=tags,
            on_log=on_log,
        )
        results[blog_id] = ok

        if account != ACCOUNTS[-1]:
            cooldown = random.randint(10, 20)
            log(f"[순환] 계정 전환 대기 {cooldown}초...")
            time.sleep(cooldown)

    log(f"\n{'='*50}")
    log("[결과 요약]")
    for blog_id, ok in results.items():
        status = "O 성공" if ok else "X 실패"
        log(f"  {blog_id}: {status}")
    log(f"{'='*50}")

    return results


def _pause(min_s, max_s):
    """계정 간 랜덤 대기 (초 단위)"""
    time.sleep(random.uniform(min_s, max_s))
