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


# .env 로드 (.app 번들 실행 시 프로젝트 루트 우선)
import os as _os
_env_path = Path(_os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent))) / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).parent / ".env"
_adsense_pub = ""
_adsense_slot = ""
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line.startswith("ADSENSE_CODE="):
            _adsense_pub = _line.split("=", 1)[1].strip()
        if _line.startswith("ADSENSE_SLOT="):
            _adsense_slot = _line.split("=", 1)[1].strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            _os.environ.setdefault(_k.strip(), _v.strip())


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
    """실제 애드센스 HTML 반환 (두 줄 사이 불필요한 간격 없이)"""
    pub = _adsense_pub or "ca-pub-XXXXXXXX"
    slot = _adsense_slot or "XXXXXXXX"
    # script/ins 태그를 한 줄로 붙여서 TinyMCE가 사이에 <p> 삽입하지 않도록 함
    return (
        f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={pub}" crossorigin="anonymous"></script>'
        f'<ins class="adsbygoogle" style="display:block" data-ad-client="{pub}" data-ad-slot="{slot}" data-ad-format="auto" data-full-width-responsive="true"></ins>'
        '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>'
    )


# ─────────────────────────────────────────────
# 헬퍼: Tistory 이미지 파일 업로드 (파일 선택 창 방식)
# ─────────────────────────────────────────────
def _tistory_upload_image(page, filepath: str, alt: str = "", max_retries: int = 3,
                          on_log=None) -> bool:
    """Tistory 이미지 업로드.
    이미지버튼(mce-i-image) 클릭 → 사진 메뉴 → input#openFile set_input_files
    """
    def _log(msg):
        if on_log:
            on_log(msg)

    if not os.path.exists(filepath):
        _log(f"[이미지업로드] 파일 없음: {filepath}")
        return False

    for attempt in range(1, max_retries + 1):
        try:
            # 1. 이미지 버튼 클릭 — 보이는 버튼만 클릭 (숨겨진 attach-layer-btn 제외)
            page.evaluate("""() => {
                const icons = [...document.querySelectorAll('i.mce-ico.mce-i-image')];
                const visible = icons.find(ico => ico.getBoundingClientRect().width > 0);
                if (visible) visible.closest('button').click();
            }""")
            time.sleep(0.8)

            # 2. "사진" 서브메뉴 클릭
            page.evaluate("""() => {
                const items = [...document.querySelectorAll('.mce-tistory-attach-item')];
                const el = items.find(e => e.textContent.trim() === '사진');
                if (el) el.click();
            }""")
            time.sleep(0.5)

            # 3. input#openFile 에 파일 직접 설정 (Playwright는 hidden input도 처리)
            page.locator('#openFile').set_input_files(filepath)
            time.sleep(4)
            _log(f"[이미지업로드] 업로드 완료 (시도 {attempt})")
            return True

        except Exception as e:
            _log(f"[이미지업로드] 시도 {attempt} 실패: {e}")
            page.keyboard.press("Escape")
            time.sleep(1)

    return False


def _tistory_insert_adsense_format(page, log_fn=None) -> bool:
    """Tistory 에디터 애드센스 서식 삽입.
    점세개(#more-plugin-btn-open) → 서식(.mce-tistory-plugin-item) → 애드센스(.list_editor a.link_info)
    """
    def log(msg):
        if log_fn: log_fn(msg)

    try:
        # 1. 점세개 버튼 존재 확인 후 클릭
        btn_exists = page.evaluate("() => !!document.querySelector('#more-plugin-btn-open')")
        if not btn_exists:
            log("[포스팅] #more-plugin-btn-open 없음")
            return False

        page.click('#more-plugin-btn-open')
        time.sleep(1.0)

        # 2. "서식" 메뉴 항목 대기 후 클릭
        try:
            page.wait_for_selector('.mce-tistory-plugin-item', timeout=3000)
        except Exception:
            log("[포스팅] .mce-tistory-plugin-item 로드 실패")
            page.keyboard.press("Escape")
            return False

        clicked = page.evaluate("""() => {
            const items = [...document.querySelectorAll('.mce-tistory-plugin-item')];
            const el = items.find(e => e.textContent.trim() === '서식');
            if (el) { el.click(); return true; }
            return false;
        }""")

        if not clicked:
            log("[포스팅] 서식 메뉴 항목 없음")
            page.keyboard.press("Escape")
            return False

        time.sleep(1.5)
        log("[포스팅] 서식 메뉴 열림")

        # 3. 애드센스 항목 대기 후 클릭
        try:
            page.wait_for_selector('.list_editor a.link_info', timeout=3000)
        except Exception:
            log("[포스팅] .list_editor 로드 실패")
            page.keyboard.press("Escape")
            return False

        inserted = page.evaluate("""() => {
            const links = [...document.querySelectorAll('.list_editor a.link_info')];
            const el = links.find(e => e.textContent.includes('애드센스'));
            if (el) { el.click(); return el.textContent.trim(); }
            return null;
        }""")

        if inserted:
            time.sleep(1.0)
            log(f"[포스팅] 서식 애드센스 삽입 완료 ('{inserted}')")
            return True

        page.keyboard.press("Escape")
        log("[포스팅] 서식 목록에서 애드센스 항목 없음")
        return False

    except Exception as e:
        log(f"[포스팅] 서식 삽입 오류: {e}")
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return False


def _tistory_set_thumbnail(page, log_fn=None):
    """Tistory 에디터에서 첫 번째 이미지를 대표이미지(썸네일)로 설정한다."""
    def log(msg):
        if log_fn:
            log_fn(msg)
    try:
        # 대표이미지 설정 버튼 셀렉터
        thumb_sels = [
            'button[title="대표이미지 선택"]',
            'button[aria-label="대표이미지 선택"]',
            'button:has-text("대표이미지")',
            '.btn-cover-image',
            '[data-action="cover"]',
        ]
        for sel in thumb_sels:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible(timeout=2000):
                    btn.click(timeout=5000)
                    time.sleep(1)
                    # 첫 번째 이미지 클릭
                    first_img = page.locator('.cover-image-list img, .thumbnail-list img').first
                    if first_img.count() > 0:
                        first_img.click(timeout=3000)
                        time.sleep(1)
                    log("[포스팅] 대표이미지 설정 완료")
                    return True
            except Exception:
                pass
    except Exception as e:
        log(f"[포스팅] 대표이미지 설정 실패 (스킵): {e}")
    return False


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
                  image_paths=None, image_infos=None, keyword="", on_log=None):
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
        _TITLE_SELECTORS = [
            "#post-title-inp",
            ".tit_post input",
            "input[placeholder*='제목']",
            "input[name='title']",
            ".editor-title input",
            "[data-placeholder*='제목']",
        ]
        title_el = None
        for _sel in _TITLE_SELECTORS:
            try:
                page.wait_for_selector(_sel, timeout=10000)
                title_el = page.query_selector(_sel)
                if title_el:
                    log(f"[포스팅] 에디터 로드 완료 (셀렉터: {_sel})")
                    break
            except Exception:
                continue
        if not title_el:
            # 디버그: 현재 URL과 input 목록 출력
            log(f"[포스팅] 에디터 로드 실패 — 현재 URL: {page.url}")
            inputs_info = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('input')).map(e => ({
                    id: e.id, name: e.name, placeholder: e.placeholder, type: e.type
                })).slice(0, 10);
            }""")
            log(f"[포스팅] 입력 필드 목록: {inputs_info}")
            return False

        # ── 제목 입력 (keyboard.type) ──
        log(f"[포스팅] 제목 입력: {title[:30]}...")
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

            # ── ### H3 소소제목 ──
            h3_match = re.match(r'^###\s+(.+)$', stripped)
            if h3_match:
                heading = h3_match.group(1).strip()
                heading = re.sub(r'<[^>]+>', '', heading).strip()
                h3_html = f'<h3>{heading}</h3>'
                page.evaluate(
                    "(html) => { if(tinymce.activeEditor) tinymce.activeEditor.execCommand('mceInsertContent', false, html); }",
                    h3_html,
                )
                time.sleep(0.3)
                log(f"[포스팅] H3: {heading[:20]}...")
                i += 1
                continue

            # ── ## H2 소제목 ──
            h2_match = re.match(r'^##\s+(.+)$', stripped)
            if h2_match:
                heading = h2_match.group(1).strip()
                heading = re.sub(r'<[^>]+>', '', heading).strip()
                h2_html = f'<h2>{heading}</h2>'
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

            # ── {{이미지N}} → 이미지 파일 업로드 삽입 ──
            img_match = re.match(r'\{\{이미지(\d+)\}\}', stripped)
            if img_match:
                idx = int(img_match.group(1))
                if idx in image_paths:
                    alt = ""
                    for info in image_infos:
                        if info["index"] == idx:
                            alt = info.get("alt", "")
                            break
                    log(f"[포스팅] 이미지 {idx} 파일 업로드: {Path(image_paths[idx]).name}")
                    ok = _tistory_upload_image(page, image_paths[idx], alt, on_log=log)
                    if ok:
                        log(f"[포스팅] 이미지 {idx} 업로드 완료")
                        # 이미지 업로드 후 TinyMCE 포커스가 캡션으로 이동할 수 있음 → 본문으로 복구
                        page.evaluate("""() => {
                            const ed = tinymce && tinymce.activeEditor;
                            if (!ed) return;
                            const body = ed.getBody();
                            const doc = ed.getDoc();
                            // 본문 끝에 새 단락 추가 후 커서 이동
                            const p = doc.createElement('p');
                            p.setAttribute('data-ke-size', 'size16');
                            p.innerHTML = '<br data-mce-bogus="1">';
                            body.appendChild(p);
                            const range = doc.createRange();
                            range.setStart(p, 0);
                            range.collapse(true);
                            ed.selection.setRng(range);
                            ed.focus();
                        }""")
                        time.sleep(0.3)
                    else:
                        log(f"[포스팅] 이미지 {idx} 업로드 실패 — 스킵")
                else:
                    log(f"[포스팅] 이미지 {idx} 파일 없음 — 스킵")
                i += 1
                continue

            # ── [애드센스] → 서식 탭에서 삽입 (실패 시 스킵) ──
            if stripped == '[애드센스]' or stripped == '##AD##':
                # 새 단락에서 삽입 (이전 텍스트와 분리)
                frame.page.keyboard.press("Enter")
                time.sleep(0.1)
                ok = _tistory_insert_adsense_format(page, log)
                if ok:
                    time.sleep(0.5)
                    # TinyMCE 포커스 복구 + adsense 이후 새 빈 단락으로 커서 이동
                    page.evaluate("""() => {
                        const ed = tinymce && tinymce.activeEditor;
                        if (!ed) return;
                        const body = ed.getBody();
                        const doc = ed.getDoc();
                        const p = doc.createElement('p');
                        p.setAttribute('data-ke-size', 'size16');
                        p.innerHTML = '<br data-mce-bogus="1">';
                        body.appendChild(p);
                        const range = doc.createRange();
                        range.setStart(p, 0);
                        range.collapse(true);
                        ed.selection.setRng(range);
                        ed.focus();
                    }""")
                    time.sleep(0.1)
                else:
                    log("[포스팅] 애드센스 서식 삽입 실패 — 스킵 (HTML 직접 삽입 시 코드 깨짐)")
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
            _TAG_SELS = ['#tagText', '.tag_post input', 'input[placeholder*="태그"]', 'input[name="tag"]']
            tag_ok = 0
            for tag in tags:
                try:
                    # Locator 사용 (triple_click 지원)
                    tag_loc = None
                    for sel in _TAG_SELS:
                        loc = page.locator(sel).first
                        if loc.count() > 0 and loc.is_visible(timeout=1000):
                            tag_loc = loc
                            break
                    if not tag_loc:
                        break
                    tag_loc.click()
                    time.sleep(0.2)
                    tag_loc.fill(tag.strip())
                    page.keyboard.press("Enter")
                    time.sleep(random.uniform(0.5, 1.0))
                    tag_ok += 1
                except Exception as e:
                    log(f"[포스팅] 태그 '{tag}' 입력 오류: {e}")
            if tag_ok == 0:
                log("[포스팅] 태그 입력 실패 — 스킵")
            else:
                log(f"[포스팅] 태그 {tag_ok}개 입력 완료")

        # ── 카테고리 선택 (goodisak) ──
        blog_id_local = account.get("blog", "")
        if blog_id_local == "goodisak":
            cat_name = _get_goodisak_category(keyword or title)
            log(f"[포스팅] 카테고리 선택 (goodisak): {cat_name}")
            try:
                # TinyMCE 카테고리 드롭다운 열기
                cat_result = page.evaluate("""(catName) => {
                    const selectTxts = [...document.querySelectorAll('i.mce-txt')];
                    const catTxt = selectTxts.find(i => i.textContent.trim() === '카테고리');
                    if (catTxt) {
                        const btn = catTxt.closest('button');
                        if (btn) { btn.click(); return '__dropdown__'; }
                    }
                    return null;
                }""", cat_name)
                if cat_result == '__dropdown__':
                    import time as _t
                    _t.sleep(0.5)
                    selected = page.evaluate("""(catName) => {
                        const items = [...document.querySelectorAll('[role="menuitem"]')];
                        const item = items.find(el => el.textContent.trim() === catName);
                        if (item) { item.click(); return '카테고리:' + catName; }
                        return null;
                    }""", cat_name)
                    if selected:
                        log(f"[포스팅] 카테고리 선택 완료: {selected}")
                    else:
                        log(f"[포스팅] 카테고리 '{cat_name}' 항목 없음 — 스킵")
            except Exception as e:
                log(f"[포스팅] 카테고리 선택 오류: {e}")

        # ── 대표이미지 설정 (첫 번째 이미지) ──
        if image_paths:
            log("[포스팅] 대표이미지 설정 시도...")
            _tistory_set_thumbnail(page, log)

        # ── 임시저장 (검수 후 수동 발행) ──
        log("[포스팅] 임시저장 중...")
        saved = page.evaluate("""() => {
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
        _rand_delay(page, 2000, 3000)
        if saved:
            log(f"[포스팅] 임시저장 완료: {title[:30]}...")
            return True
        else:
            log("[포스팅] 임시저장 버튼 없음 — 실패")
            return False

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


def _naver_set_font_size(page, size: int = 19):
    """네이버 에디터 글자 크기를 설정한다."""
    try:
        # 글자 크기 입력 필드 찾기 (여러 selector 시도)
        selectors = [
            'input[data-name="fontSize"]',
            '.se-fontSize-input input',
            '.se-toolbar-item-fontSize input',
            'input[class*="fontSize"]',
            '.se-toolbar input[type="text"]',
            'input.se-input-text',
        ]
        size_input = None
        for sel in selectors:
            el = page.query_selector(sel)
            if el:
                try:
                    if el.is_visible(timeout=500):
                        size_input = el
                        break
                except Exception:
                    pass
        if size_input:
            size_input.triple_click()
            time.sleep(0.1)
            size_input.type(str(size), delay=50)
            page.keyboard.press("Enter")
            time.sleep(0.3)
    except Exception:
        pass


def _naver_restore_body_format(page):
    """서식을 본문(일반 텍스트)으로 복원하고 글자 크기를 19로 설정한다."""
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
                    _naver_set_font_size(page, 19)
                    return
            # 드롭다운 미열림 → Escape 후 재시도
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)


def _naver_type_line_with_bold(page, line: str, chunk_size: int = 50):
    """**bold** 마커가 포함된 줄을 네이버 에디터에 입력한다.

    **텍스트** 구간은 타이핑 후 Shift+Left×N으로 선택하고 Ctrl+B 적용.
    """
    import re as _re
    segments = _re.split(r'(\*\*[^*]+\*\*)', line)
    for seg in segments:
        if not seg:
            continue
        bold_m = _re.match(r'\*\*([^*]+)\*\*', seg)
        if bold_m:
            text = bold_m.group(1)
            # Ctrl+B 켜기 → 타이핑 → Ctrl+B 끄기 (선택 방식보다 안정적)
            page.keyboard.press("Control+b")
            time.sleep(0.1)
            _chunked_type(page, text, chunk_size=chunk_size)
            page.keyboard.press("Control+b")
            time.sleep(0.1)
        else:
            _chunked_type(page, seg, chunk_size=chunk_size)


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
    # 마크다운 bold → 마커 유지 (네이버 에디터에서 Ctrl+B로 처리)
    text = content
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
    """Claude 출력 이미지 위치를 그대로 유지한다 (기준 3: 이미지 지시 준수)."""
    return sections


# ─────────────────────────────────────────────
# goodisak 블로그 카테고리 판단
# ─────────────────────────────────────────────
_GOODISAK_FINANCE_KEYWORDS = [
    "카카오페이", "토스", "네이버페이", "삼성페이", "페이코",
    "이체", "송금", "수수료", "금융", "대출", "신용카드", "체크카드",
    "적금", "예금", "청약", "금리", "이자", "환율", "주식", "펀드",
    "연금", "보험", "세금", "절세", "소득공제", "환급", "환전",
    "포인트현금", "포인트전환", "마일리지",
]
_GOODISAK_IT_KEYWORDS = [
    "갤럭시", "아이폰", "아이패드", "애플", "삼성", "스마트폰",
    "노트북", "맥북", "윈도우", "맥os", "안드로이드", "ios",
    "유튜브", "넷플릭스", "디즈니플러스", "왓챠",
    "노션", "구글", "카카오", "네이버", "쿠팡", "배달의민족",
    "앱", "어플", "소프트웨어", "프로그램", "설정", "배터리",
    "저장공간", "화질", "광고차단", "vpn", "보안", "wifi",
    "블루투스", "이어폰", "에어팟", "애플워치", "갤럭시워치",
    "폴드", "플립", "태블릿", "pc", "컴퓨터",
]

def _get_goodisak_category(keyword: str) -> str:
    """키워드 기반 goodisak 블로그 카테고리 반환.
    금융 관련 → '금융', IT 관련 → 'IT 정보', 나머지 → 'IT 정보' (기본)
    """
    kw_flat = keyword.replace(" ", "").lower()
    for w in _GOODISAK_FINANCE_KEYWORDS:
        if w.replace(" ", "").lower() in kw_flat:
            return "금융"
    for w in _GOODISAK_IT_KEYWORDS:
        if w.replace(" ", "").lower() in kw_flat:
            return "IT 정보"
    return "IT 정보"  # 기본값


# 살림1수 블로그 카테고리 판단
# ─────────────────────────────────────────────
_SALIM_FIXED_COST_KEYWORDS = [
    "전기세", "전기요금", "전기비", "수도요금", "수도세", "수도비",
    "통신비", "인터넷요금", "인터넷비", "핸드폰요금", "휴대폰요금",
    "관리비", "도시가스", "가스요금", "가스비", "난방비",
]

def _get_salim_category(keyword: str) -> str:
    """키워드 기반 살림1수 블로그 카테고리 반환.
    고정비 관련 → '고정지출', 나머지 → '살림이야기'
    """
    kw_flat = keyword.replace(" ", "")
    for w in _SALIM_FIXED_COST_KEYWORDS:
        if w in kw_flat:
            return "고정지출"
    return "살림이야기"


# ─────────────────────────────────────────────
# 네이버 글 작성
# ─────────────────────────────────────────────
def _post_naver(account, title, content, tags=None,
                image_paths=None, image_infos=None, keyword="", on_log=None):
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

        # 본문 글자 크기 19 초기 설정
        _naver_set_font_size(page, 19)

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
                        # 리스트 마커(- ) 제거: 네이버 에디터 자동 리스트 변환 방지
                        if stripped.startswith('- '):
                            stripped = stripped[2:]
                        if not stripped:
                            continue
                        # | 마크다운 표 → 텍스트로 입력
                        if stripped.startswith("|") and "|" in stripped[1:]:
                            _chunked_type(page, stripped, chunk_size=50)
                            page.keyboard.press("Enter")
                            time.sleep(0.2)
                            continue
                        # **볼드** 처리 (Ctrl+B)
                        if '**' in stripped:
                            _naver_type_line_with_bold(page, stripped)
                        else:
                            _chunked_type(page, stripped, chunk_size=50)
                        if li < len(lines) - 1:
                            # 모바일 가독성: 줄 사이 Enter 두 번 (독립 문단으로 분리)
                            page.keyboard.press("Enter")
                            time.sleep(0.1)
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

        # ── 카테고리 선택 (salim1su) ──
        blog_id_for_cat = account.get("blog", "")
        if blog_id_for_cat == "salim1su" and keyword:
            cat_name = _get_salim_category(keyword)
            log(f"[포스팅] 카테고리 선택: {cat_name}")
            try:
                time.sleep(1.0)  # 팝업 완전 로드 대기
                selected = page.evaluate("""(catName) => {
                    // 1. 팝업 내 모든 클릭 가능 요소에서 텍스트 일치
                    const allEls = document.querySelectorAll(
                        'li, a, button, label, span, div[role="option"], div[role="listitem"]'
                    );
                    for (const el of allEls) {
                        const txt = el.textContent.trim();
                        if (txt === catName) {
                            el.click();
                            return 'clicked:' + txt;
                        }
                    }
                    // 2. 포함 매칭 (완전 일치 실패 시)
                    for (const el of allEls) {
                        const txt = el.textContent.trim();
                        if (txt.includes(catName)) {
                            el.click();
                            return 'partial:' + txt;
                        }
                    }
                    // 3. select 드롭다운
                    const sel = document.querySelector('select');
                    if (sel) {
                        for (const opt of sel.options) {
                            if (opt.text.trim() === catName || opt.text.includes(catName)) {
                                sel.value = opt.value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                return 'select:' + opt.text;
                            }
                        }
                    }
                    // 디버그: 팝업 내 텍스트 목록 반환
                    const popup = document.querySelector('[class*="layer_popup"][class*="is_show"], [class*="publish"]');
                    if (popup) {
                        const texts = Array.from(popup.querySelectorAll('li, button, a, label'))
                            .map(e => e.textContent.trim()).filter(t => t).slice(0, 20);
                        return 'debug:' + texts.join('|');
                    }
                    return false;
                }""", cat_name)
                if selected and selected is not False:
                    if str(selected).startswith('debug:'):
                        log(f"[포스팅] 카테고리 팝업 요소: {selected[6:]}")
                        log(f"[포스팅] 카테고리 '{cat_name}' 항목을 찾지 못함 — 스킵")
                    else:
                        time.sleep(0.5)
                        log(f"[포스팅] 카테고리 선택 완료: {selected}")
                else:
                    log(f"[포스팅] 카테고리 '{cat_name}' 항목을 찾지 못함 — 스킵")
            except Exception as e:
                log(f"[포스팅] 카테고리 선택 오류: {e}")

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

        # 발행 팝업 닫기 (Escape) → 임시저장
        log("[포스팅] 발행 팝업 닫기 (Escape) → 임시저장...")
        page.keyboard.press("Escape")
        _rand_delay(page, 1000, 1500)

        save_btn = None
        for sel in ['button[class*="save_btn"]', 'button[class*="saveDraft"]',
                    'button[data-action="save"]', 'button.se-save-draft-button']:
            save_btn = page.query_selector(sel)
            if save_btn:
                break
        # JavaScript 폴백: 텍스트로 버튼 찾기
        if not save_btn:
            saved = page.evaluate("""() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    if (btn.textContent.includes('임시저장')) {
                        btn.click(); return true;
                    }
                }
                return false;
            }""")
            if saved:
                _rand_delay(page, 2000, 3000)
                log(f"[포스팅] 네이버 임시저장 완료: {title[:30]}...")
                return True
            log("[포스팅] 임시저장 버튼을 찾을 수 없음")
            return False
        save_btn.click()
        _rand_delay(page, 2000, 3000)

        log(f"[포스팅] 네이버 임시저장 완료: {title[:30]}...")
        return True

    finally:
        pw.stop()


# ─────────────────────────────────────────────
# WordPress REST API 포스팅 (baremi542)
# ─────────────────────────────────────────────
import ssl as _ssl
_WP_SSL_CTX = _ssl.create_default_context()
_WP_SSL_CTX.check_hostname = False
_WP_SSL_CTX.verify_mode = _ssl.CERT_NONE


def _wp_urlopen(req, timeout=15):
    """SSL 인증서 검증 우회 urlopen (macOS Python 호환)"""
    import urllib.request
    return urllib.request.urlopen(req, timeout=timeout, context=_WP_SSL_CTX)


def _md_to_wp_html(content: str) -> str:
    """마크다운 본문을 WordPress HTML로 변환.

    처리 항목:
    - ## H2 / ### H3 → <h2> / <h3>
    - **bold** → <strong>
    - *italic* → <em>
    - | table | → <table>
    - [애드센스] → 제거
    - {{이미지N}} → 플레이스홀더 유지 (이미지 업로드 후 교체)
    - 일반 텍스트 → <p>
    """
    import re

    lines = content.split("\n")
    html_parts = []
    table_buf = []

    def flush_table():
        if not table_buf:
            return ""
        return _markdown_table_to_html(table_buf)

    h2_count = [0]  # H2 순번 (id="section-N" 용)

    def inline(text: str) -> str:
        # 외부 링크: [텍스트](https://...)
        text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
        # 앵커 링크: [텍스트](#section-N)
        text = re.sub(r"\[([^\]]+)\]\((#[^\)]+)\)", r'<a href="\2">\1</a>', text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        return text

    for line in lines:
        stripped = line.strip()

        # 표 줄
        if stripped.startswith("|"):
            table_buf.append(stripped)
            continue
        else:
            if table_buf:
                html_parts.append(flush_table())
                table_buf = []

        if not stripped:
            continue

        if stripped.startswith("### "):
            html_parts.append(f"<h3>{inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            h2_count[0] += 1
            html_parts.append(f'<h2 id="section-{h2_count[0]}">{inline(stripped[3:])}</h2>')
        elif stripped == "[애드센스]":
            html_parts.append(_get_adsense_html())
        elif re.match(r"^\{\{이미지\d+\}\}$", stripped):
            html_parts.append(stripped)  # 이미지 플레이스홀더 유지
        elif re.match(r"^<(p|div|ul|ol|li|blockquote|pre|figure|img|script|ins|br|hr|table)\b",
                      stripped, re.IGNORECASE):
            # 이미 HTML 블록 태그로 시작하는 줄 — 그대로 통과 (이중 래핑 방지)
            html_parts.append(stripped)
        else:
            # 일반 텍스트 — stray HTML 태그 제거 후 <p> 래핑
            clean = re.sub(r"<br\s*/?>", " ", stripped)
            clean = re.sub(r"<[^>]+>", "", clean).strip()
            if clean:
                html_parts.append(f"<p>{inline(clean)}</p>")

    if table_buf:
        html_parts.append(flush_table())

    return "\n".join(html_parts)


def _wp_upload_image(site_url: str, auth_header: str, filepath: str,
                     alt: str = "", on_log=None) -> str:
    """이미지를 WordPress 미디어 라이브러리에 업로드하고 URL을 반환한다."""
    import urllib.request
    import json
    import mimetypes
    import os

    def log(msg):
        if on_log:
            on_log(msg)

    if not os.path.exists(filepath):
        log(f"[WordPress] 이미지 파일 없음: {filepath}")
        return ""

    filename = os.path.basename(filepath)
    mime, _ = mimetypes.guess_type(filepath)
    mime = mime or "image/webp"

    with open(filepath, "rb") as f:
        data = f.read()

    upload_headers = {
        "Authorization": auth_header,
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": mime,
    }
    try:
        req = urllib.request.Request(
            f"{site_url}/wp-json/wp/v2/media",
            data=data,
            headers=upload_headers,
            method="POST",
        )
        resp = json.loads(_wp_urlopen(req, timeout=30).read())
        url = resp.get("source_url", "")
        media_id = resp.get("id", "")
        # alt 텍스트 업데이트
        if media_id and alt:
            patch_req = urllib.request.Request(
                f"{site_url}/wp-json/wp/v2/media/{media_id}",
                data=json.dumps({"alt_text": alt, "caption": alt}).encode(),
                headers={"Authorization": auth_header, "Content-Type": "application/json"},
                method="POST",
            )
            _wp_urlopen(patch_req, timeout=10)
        log(f"[WordPress] 이미지 업로드 완료: {filename} → {url}")
        return url
    except Exception as e:
        log(f"[WordPress] 이미지 업로드 실패 ({filename}): {e}")
        return ""


def _wp_upload_image_with_id(site_url: str, auth_header: str, filepath: str,
                              alt: str = "", on_log=None):
    """이미지 업로드 후 (url, media_id) 튜플 반환. 특성 이미지 설정에 사용."""
    import urllib.request
    import json
    import mimetypes

    def log(msg):
        if on_log:
            on_log(msg)

    if not os.path.exists(filepath):
        return "", None

    filename = os.path.basename(filepath)
    mime, _ = mimetypes.guess_type(filepath)
    mime = mime or "image/webp"

    with open(filepath, "rb") as f:
        data = f.read()

    upload_headers = {
        "Authorization": auth_header,
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": mime,
    }
    try:
        req = urllib.request.Request(
            f"{site_url}/wp-json/wp/v2/media",
            data=data,
            headers=upload_headers,
            method="POST",
        )
        resp = json.loads(_wp_urlopen(req, timeout=30).read())
        url      = resp.get("source_url", "")
        media_id = resp.get("id")
        if media_id and alt:
            patch_req = urllib.request.Request(
                f"{site_url}/wp-json/wp/v2/media/{media_id}",
                data=json.dumps({"alt_text": alt, "caption": alt}).encode(),
                headers={"Authorization": auth_header, "Content-Type": "application/json"},
                method="POST",
            )
            _wp_urlopen(patch_req, timeout=10)
        log(f"[WordPress] 이미지 업로드 완료: {filename} → {url}")
        return url, media_id
    except Exception as e:
        log(f"[WordPress] 이미지 업로드 실패 ({filename}): {e}")
        return "", None


def _post_wordpress(account, title, content, tags=None,
                    keyword: str = "", image_paths=None,
                    image_infos=None, on_log=None):
    """WordPress REST API로 글을 발행하고 Rank Math 메타를 설정한다.

    .env 필요:
      WP_USER=<워드프레스 사용자명>
      WP_APP_PASSWORD=<애플리케이션 비밀번호 (공백 제거)>
    """
    import json
    import base64
    import re
    import ssl
    import urllib.request
    import urllib.parse
    import os

    image_paths = image_paths or {}
    image_infos = image_infos or []

    # macOS Python SSL 인증서 문제 우회
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE

    def _urlopen(req, timeout=15):
        return urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx)

    def log(msg):
        if on_log:
            on_log(msg)

    site_url = account.get("editor_url", "").replace("/wp-admin/post-new.php", "")
    if not site_url:
        site_url = "https://baremi542.com"

    # 블로그별 전용 자격증명 우선, 없으면 공통 WP_USER/WP_APP_PASSWORD 사용
    user_env = account.get("wp_user_env", "WP_USER")
    pass_env = account.get("wp_pass_env", "WP_APP_PASSWORD")
    wp_user = os.environ.get(user_env) or os.environ.get("WP_USER", "")
    wp_pass = (os.environ.get(pass_env) or os.environ.get("WP_APP_PASSWORD", "")).replace(" ", "")

    if not wp_user or not wp_pass:
        log("[WordPress] ⚠ WP_USER / WP_APP_PASSWORD 환경변수 미설정 — 발행 스킵")
        return False

    token = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
    auth_header = f"Basic {token}"
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }

    # 1. [애드센스] 마커가 없으면 H2 기준 자동 삽입
    if "[애드센스]" not in content:
        md_lines = content.split("\n")
        h2_positions = [i for i, ln in enumerate(md_lines) if re.match(r'^##\s+', ln.strip())]
        pure_text = re.sub(r"\s+", "", re.sub(r"##.*|{{.*?}}|\|.*", "", content))
        char_count = len(pure_text)
        max_ads = 1 if char_count < 3000 else (2 if char_count < 5000 else 3)
        # 각 H2 바로 앞에 [애드센스] 삽입 (max_ads개까지)
        for pos in sorted(h2_positions[1:max_ads + 1], reverse=True):
            md_lines.insert(pos, "[애드센스]")
        content = "\n".join(md_lines)
        log(f"[WordPress] [애드센스] {min(max_ads, len(h2_positions[1:]))}개 자동 삽입")

    # 2. 마크다운 → HTML 변환
    html_content = _md_to_wp_html(content)

    # 2. 이미지 업로드 후 {{이미지N}} 플레이스홀더 교체
    info_map = {img["index"]: img for img in image_infos}
    _first_media_id = [None]  # 첫 번째 이미지 media_id (특성 이미지용)

    def _replace_image(m):
        idx = int(m.group(1))
        filepath = image_paths.get(idx, "")
        alt = info_map.get(idx, {}).get("alt", "")
        # 첫 번째 이미지 alt에 키워드 강제 포함 (Rank Math 이미지 alt 체크)
        if idx == 1 and keyword and keyword not in alt:
            alt = f"{keyword} {alt}".strip()
        if filepath:
            url, media_id = _wp_upload_image_with_id(
                site_url, auth_header, filepath, alt=alt, on_log=on_log)
            if url:
                if idx == 1 and media_id and _first_media_id[0] is None:
                    _first_media_id[0] = media_id
                return f'<figure class="wp-block-image"><img src="{url}" alt="{alt}"/></figure>'
        log(f"[WordPress] {{이미지{idx}}} — 파일 없음, 플레이스홀더 제거")
        return ""

    html_content = re.sub(r"\{\{이미지(\d+)\}\}", _replace_image, html_content)

    # 2-1. H2 소제목에 키워드 없는 경우 자동 보정 (Rank Math "keyword in subheading" 체크)
    if keyword:
        def fix_h2_keyword(m):
            inner = m.group(1)
            inner_text = re.sub(r"<[^>]+>", "", inner).strip()
            if keyword in inner_text or not inner_text:
                return m.group(0)
            return m.group(0).replace(inner, f"{keyword} {inner_text}", 1)
        html_content = re.sub(
            r"(<h2[^>]*>)(.*?)(</h2>)",
            lambda m: m.group(1) + (
                m.group(2) if keyword in re.sub(r"<[^>]+>", "", m.group(2))
                else f"{keyword} — {re.sub(r'<[^>]+>', '', m.group(2)).strip()}"
            ) + m.group(3),
            html_content, flags=re.DOTALL
        )

    # 3. 본문에서 실제 사용된 키워드 형태 감지 (띄어쓰기 변형 대응)
    plain = re.sub(r"<[^>]+>", "", html_content)
    plain = re.sub(r"\s+", " ", plain).strip()
    rm_keyword = keyword  # Rank Math에 전달할 키워드
    if keyword and keyword not in plain:
        # 공백 추가/제거 변형 탐색
        spaced = re.sub(r"(?<=\S)(?=\S)", " ", keyword)   # 각 글자 사이 공백 삽입 시도
        no_space = keyword.replace(" ", "")
        # 실제 본문에 있는 형태 우선 사용
        for variant in [no_space, spaced] + [keyword]:
            if variant and variant in plain:
                rm_keyword = variant
                break
        else:
            # 없으면 키워드를 본문 맨 앞에 삽입
            html_content = f"<p>{keyword}에 대해 정리했습니다.</p>\n" + html_content
            plain = keyword + " " + plain

    # 4. 메타 설명: 키워드로 시작하도록
    if not plain.startswith(rm_keyword):
        meta_desc = f"{rm_keyword} — {plain}"[:160]
    else:
        meta_desc = plain[:160]

    # 5. SEO 제목: 키워드 + 파워워드 + 감성어 포함 (Rank Math 체크 대응)
    _power_words = ["핵심", "완벽", "필수", "쉬운", "빠른", "정확한"]
    _sentiment_words = ["쉽게", "간단히", "완벽하게", "빠르게", "정확히"]
    base_seo = title if rm_keyword in title else f"{rm_keyword} | {title}"
    has_power = any(w in base_seo for w in _power_words)
    has_sentiment = any(w in base_seo for w in _sentiment_words)
    if not has_power and not has_sentiment:
        seo_title = f"{rm_keyword} 핵심 정리 | {title} 쉽게 확인"
    elif not has_power:
        seo_title = f"{rm_keyword} 핵심 정리 | {title}"
    elif not has_sentiment:
        seo_title = base_seo.rstrip() + " — 쉽게 확인"
    else:
        seo_title = base_seo
    seo_title = seo_title[:60]  # SEO 제목 60자 이내

    # 6. slug: rm_keyword 기반 (공백→하이픈)
    slug = urllib.parse.quote(rm_keyword.replace(" ", "-"), safe="")

    # 6. 태그 ID 조회 (없으면 생성)
    tag_ids = []
    if tags:
        for tag_name in tags[:10]:
            try:
                search_url = f"{site_url}/wp-json/wp/v2/tags?search={urllib.parse.quote(tag_name)}"
                req = urllib.request.Request(search_url, headers=headers)
                res = json.loads(_urlopen(req, timeout=8).read())
                if res:
                    tag_ids.append(res[0]["id"])
                else:
                    create_req = urllib.request.Request(
                        f"{site_url}/wp-json/wp/v2/tags",
                        data=json.dumps({"name": tag_name}).encode(),
                        headers=headers,
                        method="POST",
                    )
                    new_tag = json.loads(_urlopen(create_req, timeout=8).read())
                    tag_ids.append(new_tag["id"])
            except Exception:
                pass

    # 7. 카테고리 ID 조회 (없으면 생성)
    category_ids = []
    cat_name = account.get("category", "")
    if cat_name:
        try:
            cat_url = f"{site_url}/wp-json/wp/v2/categories?search={urllib.parse.quote(cat_name)}"
            req = urllib.request.Request(cat_url, headers=headers)
            cat_res = json.loads(_urlopen(req, timeout=8).read())
            if cat_res:
                category_ids = [cat_res[0]["id"]]
                log(f"[WordPress] 카테고리 '{cat_name}' ID: {category_ids[0]}")
            else:
                create_req = urllib.request.Request(
                    f"{site_url}/wp-json/wp/v2/categories",
                    data=json.dumps({"name": cat_name}).encode(),
                    headers=headers,
                    method="POST",
                )
                new_cat = json.loads(_urlopen(create_req, timeout=8).read())
                category_ids = [new_cat["id"]]
                log(f"[WordPress] 카테고리 '{cat_name}' 신규 생성: ID={category_ids[0]}")
        except Exception as e:
            log(f"[WordPress] 카테고리 설정 실패: {e}")

    # 8. 글 발행
    post_body = {
        "title": title,
        "content": html_content,
        "status": "publish",
        "slug": slug,
        "tags": tag_ids,
        "categories": category_ids,
        "meta": {
            "rank_math_focus_keyword": keyword,
            "rank_math_title": seo_title,
            "rank_math_description": meta_desc,
        },
    }
    # 특성 이미지(featured image) 설정 — 첫 번째 이미지 미디어 ID
    if _first_media_id[0]:
        post_body["featured_media"] = _first_media_id[0]
        log(f"[WordPress] 특성 이미지 설정: media_id={_first_media_id[0]}")

    log(f"[WordPress] REST API 발행 시작: \"{title}\"")
    log(f"[WordPress] Focus Keyword: {keyword} / SEO Title: {seo_title}")

    try:
        req = urllib.request.Request(
            f"{site_url}/wp-json/wp/v2/posts",
            data=json.dumps(post_body).encode(),
            headers=headers,
            method="POST",
        )
        resp = json.loads(_urlopen(req, timeout=30).read())
        post_id = resp.get("id")
        post_url = resp.get("link", "")
        log(f"[WordPress] ✓ 발행 완료: {post_url}")

        # Rank Math updateMeta — REST API meta 필드가 비활성화된 경우 전용 엔드포인트 사용
        if post_id and rm_keyword:
            try:
                rm_body = {
                    "objectID": post_id,
                    "objectType": "post",
                    "meta": {
                        "rank_math_focus_keyword": rm_keyword,
                        "rank_math_title": seo_title,
                        "rank_math_description": meta_desc,
                        "rank_math_rich_snippet": "article",
                        "rank_math_snippet_article_type": "BlogPosting",
                    },
                }
                rm_req = urllib.request.Request(
                    f"{site_url}/wp-json/rankmath/v1/updateMeta",
                    data=json.dumps(rm_body).encode(),
                    headers=headers,
                    method="POST",
                )
                _urlopen(rm_req, timeout=15)
                log(f"[WordPress] ✓ Rank Math 메타 설정 완료")
            except Exception as e:
                log(f"[WordPress] ⚠ Rank Math 메타 설정 실패 (스킵): {e}")

            # JSON-LD Article 스키마 직접 삽입 (Rank Math updateSchemas API 불안정 우회)
            try:
                import datetime
                now_iso = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00")
                schema_obj = {
                    "@context": "https://schema.org",
                    "@type": "BlogPosting",
                    "headline": seo_title,
                    "description": meta_desc,
                    "url": post_url,
                    "datePublished": now_iso,
                    "dateModified": now_iso,
                    "inLanguage": "ko-KR",
                    "author": {
                        "@type": "Person",
                        "name": wp_user,
                    },
                    "publisher": {
                        "@type": "Organization",
                        "name": site_url.replace("https://", "").replace("http://", "").split("/")[0],
                    },
                }
                jsonld_block = (
                    "\n<!-- wp:html -->\n"
                    '<script type="application/ld+json">\n'
                    + json.dumps(schema_obj, ensure_ascii=False, indent=2)
                    + "\n</script>\n"
                    "<!-- /wp:html -->\n"
                )
                updated_content = html_content + jsonld_block
                update_body = {"content": updated_content}
                upd_req = urllib.request.Request(
                    f"{site_url}/wp-json/wp/v2/posts/{post_id}",
                    data=json.dumps(update_body).encode(),
                    headers=headers,
                    method="POST",
                )
                _urlopen(upd_req, timeout=30)
                log(f"[WordPress] ✓ JSON-LD Article 스키마 삽입 완료")
            except Exception as e:
                log(f"[WordPress] ⚠ JSON-LD 스키마 삽입 실패 (스킵): {e}")

        return True
    except Exception as e:
        log(f"[WordPress] ⚠ 발행 실패: {e}")
        return False


# ─────────────────────────────────────────────
# 단일 계정 포스팅 (로그인 → 글쓰기 → 로그아웃)
# ─────────────────────────────────────────────
def post_single(blog_id: str, title: str, content: str,
                tags=None, image_paths=None, image_infos=None,
                keyword: str = "", on_log=None):
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

    # WordPress는 REST API 직접 호출 — 로그인/로그아웃 불필요
    if account["platform"] == "wordpress":
        log(f"[순환] {blog_id} WordPress REST API 발행...")
        ok = _post_wordpress(account, title, content, tags,
                             keyword=keyword, image_paths=image_paths,
                             image_infos=image_infos, on_log=on_log)
        status = "성공" if ok else "실패"
        log(f"[순환] {blog_id} 완료 ({status})")
        return ok

    # 1. 로그인 (Playwright 기반 플랫폼)
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
                           keyword=keyword, on_log=on_log)
    elif account["platform"] == "naver":
        ok = _post_naver(account, title, content, tags,
                         image_paths=image_paths, image_infos=image_infos,
                         keyword=keyword, on_log=on_log)
    else:
        log(f"[순환] 지원하지 않는 플랫폼: {account['platform']}")
        ok = False

    _pause(2, 4)

    # 3. 로그아웃 (임시 비활성화 — 발행 결과 확인용)
    # log(f"[순환] {blog_id} 로그아웃...")
    # logout_blog(blog_id, on_log)
    log(f"[순환] {blog_id} 로그아웃 스킵 (결과 확인 후 수동 로그아웃)")

    _pause(1, 2)

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
