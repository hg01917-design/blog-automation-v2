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
    """텍스트를 클립보드 붙여넣기 방식으로 입력한다.

    keyboard.type()은 한글 IME 조합 중 글자가 뒤섞이는 문제가 있어
    클립보드 → Cmd+V 방식으로 교체. 텍스트가 정확하게 입력됨.
    """
    import subprocess as _sp
    try:
        _sp.run(['pbcopy'], input=text.encode('utf-8'), check=True)
        page.keyboard.press('Meta+v')
        time.sleep(random.uniform(0.6, 1.5))
    except Exception:
        # pbcopy 실패 시 기존 방식으로 폴백
        if delay_per_char is None:
            delay_per_char = random.randint(10, 30)
        chunk_count = 0
        for i in range(0, len(text), chunk_size):
            if chunk_count > 0 and chunk_count % 5 == 0:
                try:
                    body_p = page.query_selector('.se-component.se-text .se-text-paragraph')
                    if body_p:
                        body_p.click()
                        time.sleep(0.2)
                except Exception:
                    pass
            page.keyboard.type(text[i:i + chunk_size], delay=delay_per_char)
            chunk_count += 1
            time.sleep(0.3)


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
def _select_file_in_finder(filepath: str) -> bool:
    """macOS 파일 피커 다이얼로그에서 파일 선택 (사람처럼).

    Finder가 열린 상태에서 Cmd+Shift+G → 전체 경로 입력 → Enter → Enter
    다이얼로그가 자연스럽게 닫히며 파일 선택 완료.
    """
    import subprocess as _sp
    # 파일 경로에서 특수문자 이스케이프
    safe_path = filepath.replace('"', '\\"')
    script = f'''
tell application "System Events"
    delay 0.8
    keystroke "g" using {{command down, shift down}}
    delay 0.5
    keystroke "{safe_path}"
    delay 0.3
    key code 36
    delay 0.5
    key code 36
end tell
'''
    try:
        result = _sp.run(["osascript", "-e", script], capture_output=True, timeout=8)
        return result.returncode == 0
    except Exception:
        return False


def _tistory_upload_image(page, filepath: str, alt: str = "", max_retries: int = 3,
                          on_log=None) -> bool:
    """Tistory 이미지 업로드.
    이미지버튼(mce-i-image) 클릭 → 사진 메뉴 → file_chooser로 파일 선택 (AppleScript 불필요)
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

            # 2. "사진" 서브메뉴 클릭 + file_chooser 인터셉트
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.evaluate("""() => {
                    const items = [...document.querySelectorAll('.mce-tistory-attach-item')];
                    const el = items.find(e => e.textContent.trim() === '사진');
                    if (el) el.click();
                }""")
            fc_info.value.set_files(filepath)
            time.sleep(4)

            # 3. 업로드된 마지막 img에 alt 설정 (TinyMCE)
            if alt:
                try:
                    page.evaluate("""(altText) => {
                        const ed = window.tinymce && (tinymce.get('content') || tinymce.activeEditor);
                        if (!ed) return;
                        const imgs = ed.getBody().querySelectorAll('img');
                        if (imgs.length > 0) imgs[imgs.length - 1].setAttribute('alt', altText);
                    }""", alt)
                except Exception:
                    pass
            _log(f"[이미지업로드] 업로드 완료 (시도 {attempt})")
            # 업로드 성공 후 로컬 파일 삭제
            try:
                os.remove(filepath)
                _log(f"[이미지업로드] 로컬 파일 삭제: {filepath}")
            except Exception:
                pass
            return True

        except Exception as e:
            _log(f"[이미지업로드] 시도 {attempt} 실패: {e}")
            page.keyboard.press("Escape")
            time.sleep(1)

    return False


def _body_to_tinymce_html(body_text: str, blog_id: str) -> str:
    """본문 마커를 TinyMCE HTML로 변환. 이미지/애드센스는 placeholder로 처리."""
    # [이미지N]...[/이미지N] → {{이미지N}}
    body = re.sub(
        r'\[이미지\s*(\d+)\][\s\S]*?\[/이미지\s*\1\]',
        lambda m: f'\n{{{{이미지{m.group(1)}}}}}\n',
        body_text
    )
    body = re.sub(r'\[/?이미지\s*\d+\]', '', body)
    body = re.sub(r'(?m)^\s*(프롬프트|alt|Gemini프롬프트):.*$', '', body)
    body = insert_adsense_markers(body, blog_id)

    SP = '<p data-ke-size="size19">&nbsp;</p>'

    def _needs_spacing(html_tag: str) -> bool:
        """H2/H3/이미지/애드센스/버튼 블록 여부"""
        return (
            html_tag.startswith('<h2') or
            html_tag.startswith('<h3') or
            'data-img-slot' in html_tag or
            'data-adsense' in html_tag or
            ('<a href=' in html_tag and 'display:inline-block' in html_tag)
        )

    parts = []
    for line in body.split('\n'):
        s = line.strip()
        if not s:
            # 빈 줄 → 일반 텍스트 단락 사이에만 간격 삽입 (H2/이미지/애드센스 인접 제외)
            if parts and parts[-1].startswith('<p data-ke-size="size19">') and not parts[-1] == SP:
                parts.append(SP)
            continue
        # H3
        h3 = re.match(r'^###\s+(.+)$', s) or re.match(r'^\[H3\](.+?)\[/H3\]$', s, re.IGNORECASE)
        if h3:
            parts.append(f'<h3 data-ke-size="size23">{re.sub(r"<[^>]+>","",h3.group(1)).strip()}</h3>')
            continue
        # H2
        h2 = re.match(r'^##\s+(.+)$', s) or re.match(r'^\[H2\](.+?)\[/H2\]$', s, re.IGNORECASE)
        if h2:
            parts.append(f'<h2 data-ke-size="size26">{re.sub(r"<[^>]+>","",h2.group(1)).strip()}</h2>')
            continue
        # 이미지 placeholder
        img = re.match(r'\{\{이미지(\d+)\}\}', s)
        if img:
            parts.append(f'<p data-ke-size="size19" data-img-slot="{img.group(1)}">&nbsp;</p>')
            continue
        # 애드센스 placeholder
        if s in ('[애드센스]', '##AD##'):
            parts.append('<p data-ke-size="size19" data-adsense="1">&nbsp;</p>')
            continue
        # 꿀팁 박스 / 인용 (> 로 시작)
        if s.startswith('> '):
            tip = s[2:]
            tip = re.sub(r'\[BOLD\](.+?)\[/BOLD\]', r'<strong>\1</strong>', tip, flags=re.IGNORECASE)
            tip = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', tip)
            parts.append(
                f'<blockquote style="background:#f0f7ff;border-left:4px solid #1a73e8;'
                f'padding:12px 16px;margin:16px 0;border-radius:4px;">{tip}</blockquote>'
            )
            continue
        # 마크다운 표 (줄 단위 처리 불가 — 스킵)
        if s.startswith('|') and s.endswith('|'):
            continue
        # Bold / Italic / 링크
        text = s
        text = re.sub(r'\[BOLD\](.+?)\[/BOLD\]', r'<strong>\1</strong>', text, flags=re.IGNORECASE)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
        parts.append(f'<p data-ke-size="size19">{text}</p>')

    # 도입부 없음 보호: 첫 의미있는 요소가 H2/H3이면 p로 강제 변환
    first_idx = next((i for i, t in enumerate(parts) if t != SP), None)
    if first_idx is not None and (
        parts[first_idx].startswith('<h2') or parts[first_idx].startswith('<h3')
    ):
        txt = re.sub(r'<[^>]+>', '', parts[first_idx]).strip()
        parts[first_idx] = f'<p data-ke-size="size19">{txt}</p>'

    # H2/H3/이미지/애드센스/버튼 블록 앞뒤에 빈 줄 1칸 삽입
    spaced = []
    for i, tag in enumerate(parts):
        nxt = parts[i + 1] if i < len(parts) - 1 else None
        cur_needs = _needs_spacing(tag)
        if cur_needs and spaced and not spaced[-1].startswith(SP):
            spaced += [SP]
        spaced.append(tag)
        if cur_needs and nxt and not nxt.startswith(SP):
            spaced += [SP]

    return '\n'.join(spaced)


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
# 내부링크 삽입 (Tistory용 — TinyMCE insertContent)
# ─────────────────────────────────────────────
_TISTORY_BLOG_RSS = {
    "nolja100": "https://issue.baremi542.com/rss",
    "goodisak": "https://welfare.baremi542.com/rss",
    "woll100":  "https://info.baremi542.com/rss",
    "phn0502":  "https://film.baremi542.com/rss",
}

def _tistory_inject_internal_links(page, blog_id: str, log_fn=None):
    """본문 끝에 같은 블로그 최근 글 3개 내부링크 섹션을 TinyMCE로 삽입."""
    log = log_fn or (lambda x: None)
    if blog_id not in _TISTORY_BLOG_RSS:
        return
    import urllib.request as _ur
    import ssl as _ssl
    rss_url = _TISTORY_BLOG_RSS[blog_id]
    try:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        req = _ur.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
        with _ur.urlopen(req, timeout=8, context=ctx) as _r:
            rss = _r.read().decode("utf-8", errors="ignore")
        items = re.findall(
            r'<item>.*?<title><!\[CDATA\[(.*?)\]\]></title>.*?<link>(.*?)</link>.*?</item>',
            rss, re.DOTALL
        )
        if not items:
            titles = re.findall(r'<title>(.*?)</title>', rss)[1:4]
            links  = re.findall(r'<link>(.*?)</link>', rss)[1:4]
            items = list(zip(titles, links))
        import html as _html
        items = [(_html.unescape(t.strip()), l.strip()) for t, l in items[:3] if t.strip() and l.strip()]
        if not items:
            log(f"[내부링크] {blog_id}: RSS 항목 없음")
            return
        li_html = ''.join(
            f'<li><a href="{url}" target="_blank" style="color:#4285f4;text-decoration:none">{title}</a></li>'
            for title, url in items
        )
        section_html = (
            '<div style="margin-top:30px;padding:16px;background:#f8f9fa;'
            'border-left:4px solid #4285f4;border-radius:4px">'
            '<strong>📌 함께 읽으면 좋은 글</strong>'
            f'<ul style="margin:8px 0 0 0;padding-left:20px">{li_html}</ul>'
            '</div>'
        )
        page.evaluate(
            "(html) => { if(tinymce.activeEditor) { const ed = tinymce.activeEditor; ed.setContent(ed.getContent() + html); } }",
            section_html,
        )
        log(f"[내부링크] {blog_id}: {len(items)}개 삽입 완료")
    except Exception as e:
        log(f"[내부링크] {blog_id} 실패 (무시): {e}")


def _tistory_ensure_meta_description(page, keyword: str, log_fn=None):
    """첫 <p> 단락에 keyword가 없으면 앞에 키워드 포함 단락을 삽입한다.
    Tistory는 본문 첫 문단이 메타디스크립션으로 사용되므로 SEO를 위해 필요."""
    log = log_fn or (lambda x: None)
    if not keyword:
        return
    try:
        inserted = page.evaluate("""(kw) => {
            const ed = tinymce.activeEditor;
            if (!ed) return false;
            const body = ed.getBody();
            const firstP = body.querySelector('p');
            if (!firstP) return false;
            const text = firstP.textContent || '';
            if (text.includes(kw)) return false;
            const newP = ed.getDoc().createElement('p');
            newP.setAttribute('data-ke-size', 'size19');
            const preview = text.substring(0, 80).trim();
            newP.textContent = kw + ' \u2014 ' + (preview ? preview + '...' : '\uc774\uc5d0 \ub300\ud574 \uc790\uc138\ud788 \uc54c\uc544\ubcf4\uc138\uc694.');
            body.insertBefore(newP, firstP);
            ed.fire('change');
            ed.save();
            return true;
        }""", keyword)
        if inserted:
            log(f"[메타디스크립션] 키워드 '{keyword}' 첫 단락 삽입 완료")
        else:
            log(f"[메타디스크립션] 키워드 '{keyword}' 이미 첫 단락에 포함됨 (패스)")
    except Exception as e:
        log(f"[메타디스크립션] 삽입 실패 (무시): {e}")


# ─────────────────────────────────────────────
# 티스토리 글 작성 (TinyMCE 기반)
# ─────────────────────────────────────────────
def _post_tistory(account, title, body_html, tags=None,
                  image_paths=None, image_infos=None, keyword="",
                  thumbnail_path=None, on_log=None):
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

        blog_id = account.get("blog", "")

        # ── 본문 HTML 변환 후 setContent() 한 번에 삽입 ──
        log("[포스팅] 본문 HTML 변환 중...")
        full_html = _body_to_tinymce_html(body_html, blog_id)
        page.evaluate("""(html) => {
            const ed = tinymce.activeEditor;
            if (!ed) return;
            ed.setContent(html);
            ed.fire('change');
            ed.save();
        }""", full_html)
        _rand_delay(page, 1000, 1500)
        log("[포스팅] 본문 setContent 완료")

        # ── 이미지 placeholder 위치에 업로드 ──
        _diag_path = "/tmp/blogauto_img_diag.log"
        def _diag(msg):
            log(msg)
            try:
                from datetime import datetime as _dt
                with open(_diag_path, "a") as _f:
                    _f.write(f"[{_dt.now().strftime('%H:%M:%S')}] {msg}\n")
            except Exception:
                pass

        _diag(f"[포스팅] image_paths {len(image_paths)}개: keys={sorted(image_paths.keys())}")
        _slot_debug = page.evaluate("""() => {
            const ed = window.tinymce && tinymce.activeEditor;
            if (!ed) return 'editor_not_found';
            const slots = ed.getBody().querySelectorAll('[data-img-slot]');
            return [...slots].map(s => s.getAttribute('data-img-slot')).join(',') || 'no_slots';
        }""")
        _diag(f"[포스팅] TinyMCE data-img-slot 현황: {_slot_debug}")

        _thumb_uploaded = False
        for idx in sorted(image_paths.keys()):
            img_path = image_paths[idx]
            alt = next((info.get("alt", "") for info in image_infos if info["index"] == idx), "")
            # placeholder 단락으로 커서 이동 후 삭제
            placed = page.evaluate(f"""() => {{
                const ed = tinymce.activeEditor;
                const body = ed.getBody();
                const allSlots = [...body.querySelectorAll('[data-img-slot]')].map(s=>s.getAttribute('data-img-slot')).join(',');
                const p = body.querySelector('[data-img-slot="{idx}"]');
                if (!p) return 'missing:slots=[' + allSlots + ']';
                const range = ed.getDoc().createRange();
                range.selectNode(p);
                ed.selection.setRng(range);
                ed.focus();
                p.parentNode.removeChild(p);
                ed.fire('change');
                return true;
            }}""")
            if placed is True or placed == True:
                _diag(f"[포스팅] 이미지 {idx} 업로드: {Path(img_path).name}")
                ok = _tistory_upload_image(page, img_path, alt, on_log=log)
                if ok:
                    _diag(f"[포스팅] 이미지 {idx} 업로드 완료")
                    if idx == 0:
                        _thumb_uploaded = True
                    # 커서를 본문 끝으로 복구
                    page.evaluate("""() => {
                        const ed = tinymce.activeEditor;
                        if (!ed) return;
                        const body = ed.getBody();
                        const p = ed.getDoc().createElement('p');
                        p.setAttribute('data-ke-size', 'size19');
                        p.innerHTML = '<br data-mce-bogus="1">';
                        body.appendChild(p);
                        const range = ed.getDoc().createRange();
                        range.setStart(p, 0);
                        range.collapse(true);
                        ed.selection.setRng(range);
                        ed.focus();
                    }""")
                    time.sleep(0.3)
                else:
                    _diag(f"[포스팅] 이미지 {idx} 업로드 실패 — 스킵")
            else:
                _diag(f"[포스팅] 이미지 {idx} placeholder 없음 — {placed}")
                # 썸네일(0번)은 placeholder 없어도 본문 맨 앞에 강제 삽입
                if idx == 0:
                    _diag("[포스팅] 썸네일 slot 0 미탐지 — 본문 첫 번째 단락 앞에 강제 삽입")
                    page.evaluate("""() => {
                        const ed = tinymce.activeEditor;
                        const body = ed.getBody();
                        const first = body.firstElementChild;
                        if (!first) return;
                        const range = ed.getDoc().createRange();
                        range.setStart(first, 0);
                        range.collapse(true);
                        ed.selection.setRng(range);
                        ed.focus();
                    }""")
                    ok = _tistory_upload_image(page, img_path, alt, on_log=log)
                    if ok:
                        _diag("[포스팅] 썸네일 강제 삽입 완료")
                        _thumb_uploaded = True

        # ── 채워지지 않은 이미지 placeholder 제거 ──
        page.evaluate("""() => {
            const ed = tinymce.activeEditor;
            if (!ed) return;
            const body = ed.getBody();
            body.querySelectorAll('[data-img-slot]').forEach(p => p.parentNode.removeChild(p));
            ed.fire('change');
        }""")

        # ── 썸네일(index 0) 대표이미지 설정 ──
        # 업로드 성공 시 파일이 삭제되므로 exists() 체크 대신 업로드 성공 플래그 사용
        if _thumb_uploaded:
            _diag("[포스팅] 썸네일 대표이미지 설정 시작")
            time.sleep(1)
            _tistory_set_thumbnail(page, log_fn=log)

        # ── 애드센스 placeholder 위치에 서식 삽입 (전체 루프) ──
        adsense_count = page.evaluate("""() => {
            const ed = window.tinymce && tinymce.activeEditor;
            if (!ed) return 0;
            return ed.getBody().querySelectorAll('[data-adsense]').length;
        }""")
        for _ad_i in range(adsense_count):
            has_adsense = page.evaluate("""() => {
                const ed = tinymce.activeEditor;
                const body = ed.getBody();
                const p = body.querySelector('[data-adsense]');
                if (!p) return false;
                const range = ed.getDoc().createRange();
                range.selectNode(p);
                ed.selection.setRng(range);
                ed.focus();
                p.parentNode.removeChild(p);
                ed.fire('change');
                return true;
            }""")
            if has_adsense:
                ok = _tistory_insert_adsense_format(page, log)
                if ok:
                    page.evaluate("""() => {
                        const ed = tinymce.activeEditor;
                        if (!ed) return;
                        const body = ed.getBody();
                        const p = ed.getDoc().createElement('p');
                        p.setAttribute('data-ke-size', 'size19');
                        p.innerHTML = '<br data-mce-bogus="1">';
                        body.appendChild(p);
                        const range = ed.getDoc().createRange();
                        range.setStart(p, 0);
                        range.collapse(true);
                        ed.selection.setRng(range);
                        ed.focus();
                    }""")
                    time.sleep(0.5)
                else:
                    log(f"[포스팅] 애드센스 서식 삽입 실패 ({_ad_i+1}번째) — 스킵")

        # size19 일괄 적용 + 저장
        page.evaluate("""() => {
            const ed = window.tinymce && tinymce.activeEditor;
            if (!ed) return;
            const body = ed.getBody();
            body.querySelectorAll('p:not([data-ke-size])').forEach(p => {
                p.setAttribute('data-ke-size', 'size19');
            });
            ed.fire('change');
            ed.save();
        }""")

        # ── 스크롤 (봇 감지 방지) ──
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight / 2)")
        time.sleep(random.uniform(1.0, 2.0))
        page.evaluate("() => window.scrollTo(0, 0)")
        time.sleep(random.uniform(0.5, 1.0))
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(random.uniform(1.0, 2.0))
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

        # ── 카테고리 선택 (tistory 블로그) ──
        blog_id_local = account.get("blog", "")
        _TISTORY_CAT = {
            "nolja100": "여행",
            "woll100":  "교통정보",
            "phn0502":  "영화",
            "goodisak": None,  # 동적 결정 (IT/금융)
        }
        if blog_id_local in _TISTORY_CAT:
            if blog_id_local == "goodisak":
                cat_name = _get_goodisak_category(keyword or title) or "IT정보"
            else:
                cat_name = _TISTORY_CAT[blog_id_local]
            if not cat_name:
                log(f"[포스팅] 카테고리 없음 — 스킵 ({blog_id_local})")
            else:
                log(f"[포스팅] 카테고리 선택 ({blog_id_local}): {cat_name}")
                try:
                    # TinyMCE 카테고리 드롭다운 열기
                    cat_result = page.evaluate("""() => {
                        const selectTxts = [...document.querySelectorAll('i.mce-txt')];
                        const catTxt = selectTxts.find(i => i.textContent.trim() === '카테고리');
                        if (catTxt) {
                            const btn = catTxt.closest('button');
                            if (btn) { btn.click(); return '__dropdown__'; }
                        }
                        return null;
                    }""")
                    if cat_result == '__dropdown__':
                        import time as _t
                        _t.sleep(1.0)
                        # mce-floatpanel > mce-menu-item 클릭 (span.mce-text 부모)
                        selected = page.evaluate("""(catName) => {
                            const panel = document.querySelector('.mce-floatpanel.mce-menu');
                            if (panel) {
                                const items = [...panel.querySelectorAll('.mce-menu-item')];
                                const item = items.find(el => el.textContent.trim().includes(catName));
                                if (item) {
                                    item.click();
                                    return '카테고리:' + item.textContent.trim();
                                }
                                return '없음:' + items.map(el => el.textContent.trim()).join('|');
                            }
                            // fallback: span.mce-text 부모 클릭
                            const spans = [...document.querySelectorAll('span.mce-text')];
                            const span = spans.find(el => el.textContent.trim().includes(catName));
                            if (span) {
                                const parent = span.closest('.mce-menu-item') || span.parentElement;
                                parent.click();
                                return '카테고리:' + span.textContent.trim();
                            }
                            return '없음:' + spans.map(el => el.textContent.trim()).join('|');
                        }""", cat_name)
                        if selected and selected.startswith('카테고리:'):
                            log(f"[포스팅] 카테고리 선택 완료: {selected}")
                        else:
                            log(f"[포스팅] 카테고리 '{cat_name}' 항목 없음. 실제 목록: {selected}")
                except Exception as e:
                    log(f"[포스팅] 카테고리 선택 오류: {e}")

        # ── 내부링크 삽입 (Tistory: TinyMCE insertContent) ──
        _tistory_inject_internal_links(page, blog_id_local, log)


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


def _naver_close_upload_panel(page):
    """이미지 업로드 후 남아있는 라이브러리/파일선택 패널을 닫는다."""
    try:
        closed = page.evaluate("""() => {
            // 라이브러리 패널 닫기 버튼들 시도
            const closeSelectors = [
                'button[aria-label="라이브러리 닫기"]',
                'button[aria-label="닫기"]',
                '.se-library-close-button',
                '[class*="library"] button[class*="close"]',
                '[class*="library"] button[aria-label*="닫"]',
                '.se-dialog-close-button',
                '[class*="close_btn__"]',
            ];
            for (const sel of closeSelectors) {
                const btn = document.querySelector(sel);
                if (btn && btn.offsetParent !== null) {
                    btn.click();
                    return sel;
                }
            }
            return null;
        }""")
        if closed:
            time.sleep(0.5)
            return
        # 버튼 못찾으면 Escape 1회로 닫기
        page.keyboard.press("Escape")
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


def _naver_upload_image(page, filepath, log_fn=None, alt: str = ""):
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
        # 업로드 전 이미지 컴포넌트 수 기록 (중복 삽입 방지)
        img_count_before = page.evaluate(
            "() => document.querySelectorAll('.se-component.se-image').length"
        )

        # 사진 버튼 클릭 + file_chooser 인터셉트
        # 주의: set_files 전에 input[type=file] value를 초기화해야 같은 파일 재선택 시 change 이벤트 발생
        with page.expect_file_chooser(timeout=8000) as fc_info:
            photo_btn.click(timeout=5000)
        chooser = fc_info.value
        # 파일 선택기 초기화 후 재설정 (브라우저 캐싱으로 동일 파일 무시 방지)
        try:
            chooser.page.evaluate("() => { document.querySelectorAll('input[type=file]').forEach(el => { el.value = ''; }); }")
        except Exception:
            pass
        chooser.set_files(filepath)
        time.sleep(4)

        # 이미지 로드 확인
        _naver_wait_for_image_load(page)
        _naver_remove_image_placeholders(page)

        # 업로드 후 이미지 수 확인 — 이미 삽입된 경우 패널 닫기 생략 (중복 방지)
        img_count_after = page.evaluate(
            "() => document.querySelectorAll('.se-component.se-image').length"
        )
        if img_count_after > img_count_before:
            # set_files()로 이미 삽입됨 → 패널만 조용히 닫기 (Escape 1회)
            try:
                page.keyboard.press("Escape")
                time.sleep(0.3)
            except Exception:
                pass
        else:
            # 아직 삽입 안 됨 → 패널 확인 버튼/닫기 버튼으로 삽입 트리거
            _naver_close_upload_panel(page)

        # alt/caption 설정: 마지막 이미지의 캡션 placeholder 클릭 후 입력
        if alt:
            try:
                set_ok = page.evaluate("""(altText) => {
                    // SE3 이미지 컴포넌트의 마지막 img에 alt 직접 설정
                    const imgs = document.querySelectorAll(
                        '.se-image-resource, .se-module-image img, .se-component-image img'
                    );
                    if (imgs.length > 0) imgs[imgs.length - 1].setAttribute('alt', altText);
                    return imgs.length;
                }""", alt)
                if log_fn:
                    log_fn(f"[포스팅] 이미지 alt 설정: {alt[:30]} (img 수: {set_ok})")
            except Exception as _ae:
                if log_fn:
                    log_fn(f"[포스팅] alt 설정 실패: {_ae}")

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

    # 서식 버튼 찾기 (여러 셀렉터 시도)
    fmt_btn = None
    for sel in [
        '.se-text-format-toolbar-button',
        'button[data-name="text-format"]',
        'button[class*="text-format"]',
        '.se-toolbar-item-textformat button',
    ]:
        el = page.query_selector(sel)
        if el and el.is_visible():
            fmt_btn = el
            break

    if not fmt_btn:
        return False

    for attempt in range(3):
        try:
            fmt_btn.click()
            time.sleep(0.7)  # 드롭다운 열림 대기

            # 소제목 버튼 폴링 (최대 4초) — 여러 셀렉터 시도
            for _ in range(20):
                time.sleep(0.2)
                for sub_sel in [
                    'button.se-toolbar-option-text-format-sectionTitle-button',
                    'button[data-type="sectionTitle"]',
                    'button[class*="sectionTitle"]',
                    'li[data-type="sectionTitle"] button',
                ]:
                    sub_btn = page.query_selector(sub_sel)
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


def _naver_set_font_color_black(page):
    """네이버 스마트에디터 글자 색상을 검정(#000000)으로 설정한다."""
    try:
        # 전체 선택 후 색상 적용
        page.keyboard.press("Control+a")
        time.sleep(0.3)
        # 글자색 버튼 클릭
        color_selectors = [
            'button[data-name="fontColor"]',
            '.se-toolbar-item-fontColor button',
            'button[title*="글자색"]',
            'button[aria-label*="글자색"]',
        ]
        color_btn = None
        for sel in color_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    color_btn = el
                    break
            except Exception:
                pass
        if not color_btn:
            return
        color_btn.click()
        time.sleep(0.5)
        # 직접 입력 필드에 #000000 입력
        hex_input_sels = [
            'input[placeholder*="#"]',
            'input[placeholder*="hex"]',
            '.se-color-input input',
            'input[maxlength="6"]',
            'input[maxlength="7"]',
        ]
        hex_input = None
        for sel in hex_input_sels:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    hex_input = el
                    break
            except Exception:
                pass
        if hex_input:
            hex_input.click(click_count=3)
            time.sleep(0.1)
            hex_input.fill("000000")
            page.keyboard.press("Enter")
            time.sleep(0.3)
        else:
            # 폴백: 검정 색상 셀 직접 클릭
            black_sels = [
                '[data-color="#000000"]',
                '[title="검정"]',
                '[aria-label="검정"]',
            ]
            for sel in black_sels:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click()
                        time.sleep(0.3)
                        break
                except Exception:
                    pass
        # 팝업 닫기
        page.keyboard.press("Escape")
        time.sleep(0.2)
    except Exception:
        pass


def _naver_set_font_size(page, size: int = 19):
    """네이버 SE2 에디터 전체 본문 글자 크기를 설정한다.
    1차: Ctrl+A → 툴바 드롭다운 클릭 → 숫자 선택
    2차: JS DOM으로 se-fsN 클래스 직접 교체 (폴백)
    """
    try:
        # 1차: 전체 선택 후 툴바 드롭다운으로 변경
        page.keyboard.press("Meta+a")
        time.sleep(0.3)
        fs_btn = page.query_selector('.se-font-size-code-toolbar-button')
        if fs_btn:
            fs_btn.click()
            time.sleep(0.4)
            # 드롭다운 옵션에서 size 값 선택
            clicked = page.evaluate(f"""(targetSize) => {{
                const allEls = document.querySelectorAll(
                    '[class*="option"] *, [class*="dropdown"] *, [class*="layer"] *'
                );
                let found = false;
                allEls.forEach(el => {{
                    if (el.textContent.trim() === String(targetSize) && el.offsetParent !== null) {{
                        el.click();
                        found = true;
                    }}
                }});
                return found;
            }}""", size)
            time.sleep(0.3)
            if clicked:
                return
        # 2차 폴백: JS DOM 클래스 교체
        page.evaluate(f"""(targetSize) => {{
            const spans = document.querySelectorAll('span[class*="se-fs"]');
            spans.forEach(sp => {{
                const toRemove = [...sp.classList].filter(c => /^se-fs\\d+$/.test(c));
                toRemove.forEach(c => sp.classList.remove(c));
                sp.classList.add('se-fs' + targetSize);
            }});
        }}""", size)
        time.sleep(0.2)
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


def _naver_type_line_with_links(page, line: str, chunk_size: int = 50):
    """[텍스트](URL) 마크다운 링크가 포함된 줄을 네이버 에디터에 입력한다.

    링크 텍스트는 볼드로 입력 후 Enter → raw URL 붙여넣기 → Enter.
    SE2는 URL 단독 줄 입력 시 OGP 미리보기 카드로 자동 변환한다.
    """
    import re as _re
    import subprocess as _sp
    segments = _re.split(r'(\[[^\]]+\]\(https?://[^\)]+\))', line)
    for seg in segments:
        if not seg:
            continue
        link_m = _re.match(r'\[([^\]]+)\]\((https?://[^\)]+)\)', seg)
        if link_m:
            text = link_m.group(1)
            url = link_m.group(2)
            # 1) 링크 텍스트를 볼드로 입력
            page.keyboard.press("Meta+b")
            time.sleep(0.15)
            _chunked_type(page, text, chunk_size=chunk_size)
            time.sleep(0.2)
            page.keyboard.press("Meta+b")  # 볼드 해제
            time.sleep(0.15)
            # 2) Enter 후 raw URL 붙여넣기 → SE2가 OGP 미리보기로 자동 변환
            page.keyboard.press("Enter")
            time.sleep(0.2)
            try:
                _sp.run(['pbcopy'], input=url.encode('utf-8'), check=True)
                page.keyboard.press("Meta+v")
                time.sleep(0.3)
            except Exception:
                _chunked_type(page, url, chunk_size=chunk_size)
            # 3) Enter 한 번 더 → OGP 카드 변환 트리거
            page.keyboard.press("Enter")
            time.sleep(3)  # OGP 로딩 대기
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

        # ## 소제목 또는 [H2]...[/H2] 마커
        h_match = re.match(r'^#{1,3}\s+(.+)$', stripped) or re.match(r'^\s*\[H2\](.+?)\[/H2\]\s*$', stripped, re.IGNORECASE)
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

        # 마크다운 구분선 (---) → Naver SE3에서 <hr>로 렌더됨, 제거
        if re.match(r'^-{3,}$', stripped):
            continue

        # 일반 텍스트
        current_text_lines.append(stripped)

    flush_text()

    # 도입부 규칙: 첫 번째 요소가 소제목이면 일반 텍스트로 강제 변환
    # HTML div(핵심요약 등)가 첫 번째면 그 뒤 첫 소제목도 확인해서 도입부 없으면 빈 도입부 추가는 안 함
    # (프롬프트로 도입부를 요청하는 것이 근본 해결책)
    if sections and sections[0]["type"] == "heading":
        sections[0] = {"type": "text", "body": sections[0]["text"]}
    # HTML 블록(핵심요약 박스 등)이 첫 번째이고, 그 다음이 바로 소제목인 경우도 처리
    elif sections and sections[0]["type"] == "html":
        if len(sections) >= 2 and sections[1]["type"] == "heading":
            # 소제목을 텍스트로 변환 (도입부 역할)
            sections[1] = {"type": "text", "body": sections[1]["text"]}

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
    금융 관련 → '금융', IT 관련 → '' (카테고리 없음, 실제 IT 카테고리명 미확인)
    """
    kw_flat = keyword.replace(" ", "").lower()
    for w in _GOODISAK_FINANCE_KEYWORDS:
        if w.replace(" ", "").lower() in kw_flat:
            return "금융"
    # IT 카테고리: 실제 Tistory 카테고리명 확인 필요 → 현재 빈 값 반환 (카테고리 없음으로 처리)
    return ""


# 살림1수 블로그 카테고리 판단
# ─────────────────────────────────────────────
_SALIM_FIXED_COST_KEYWORDS = [
    "전기세", "전기요금", "전기비", "수도요금", "수도세", "수도비",
    "통신비", "인터넷요금", "인터넷비", "핸드폰요금", "휴대폰요금",
    "관리비", "도시가스", "가스요금", "가스비", "난방비",
]

def _get_salim_category(keyword: str) -> str:
    """키워드 기반 살림1수 블로그 카테고리 반환.
    고정비 관련 → '고정비줄이기', 나머지 → '살림이야기'
    """
    kw_flat = keyword.replace(" ", "")
    for w in _SALIM_FIXED_COST_KEYWORDS:
        if w in kw_flat:
            return "고정비줄이기"
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
    blog_id = account.get("blog", "")
    images_dir = Path(__file__).parent / "images" / blog_id

    # 애드센스 마커 삽입
    body_text = insert_adsense_markers(content, blog_id)

    # [이미지N]...[/이미지N] → {{이미지N}} 변환 (프롬프트/alt 줄 제거)
    body_text = re.sub(
        r'\[이미지\s*(\d+)\][\s\S]*?\[/이미지\s*\1\]',
        lambda m: f'\n{{{{이미지{m.group(1)}}}}}\n',
        body_text
    )
    # 혹시 남은 단독 [이미지N] 태그와 프롬프트/alt 줄 제거
    body_text = re.sub(r'\[/?이미지\s*\d+\]', '', body_text)
    body_text = re.sub(r'(?m)^\s*(프롬프트|alt|Gemini프롬프트):.*$', '', body_text)

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

        # 본문 글자 크기 19 + 색상 검정 초기 설정
        _naver_set_font_size(page, 19)
        _naver_set_font_color_black(page)

        # 기존 본문 내용 감지 → 전체 삭제 (이전 세션 자동복원으로 잘못된 이미지 재사용 방지)
        body_comp_count = page.evaluate("""() => {
            return document.querySelectorAll('.se-component').length;
        }""")
        if body_comp_count > 1:
            log(f"[포스팅] 기존 본문 컴포넌트 {body_comp_count}개 감지 — 전체 삭제 후 새로 작성")
            page.keyboard.press("Meta+a")
            time.sleep(0.3)
            page.keyboard.press("Delete")
            time.sleep(0.8)
            # 삭제 후 본문 재클릭
            body_p2 = page.query_selector('.se-component.se-text .se-text-paragraph')
            if body_p2:
                body_p2.click()
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
                    time.sleep(random.uniform(0.3, 0.7))
                    page.keyboard.press("Enter")
                    time.sleep(random.uniform(0.3, 0.7))

                # 텍스트 먼저 입력 → ElementHandle.click()으로 포커스 이동 → 서식 적용
                _chunked_type(page, heading, chunk_size=50)
                time.sleep(random.uniform(0.5, 1.0))

                # 방금 입력한 소제목 텍스트 paragraph를 ElementHandle.click()으로 클릭
                # (JS click은 SE3 포커스 이동 안 됨 → ElementHandle 필수)
                para_els = page.query_selector_all('.se-text-paragraph')
                for el in para_els:
                    try:
                        if el.text_content().strip() == heading:
                            el.scroll_into_view_if_needed()
                            el.click()
                            time.sleep(random.uniform(0.3, 0.6))
                            break
                    except Exception:
                        pass

                fmt_ok = _naver_apply_subtitle_format(page)
                if not fmt_ok:
                    log(f"[포스팅] ⚠ 소제목 서식 적용 실패 — 일반 텍스트로 진행: {heading[:20]}")
                else:
                    log(f"[포스팅] ✅ 소제목 서식 적용 완료")
                page.keyboard.press("End")
                page.keyboard.press("Enter")
                time.sleep(random.uniform(0.8, 1.5))

                # 소제목 후 마지막 본문 paragraph 클릭으로 포커스 확보
                body_ps = page.query_selector_all('.se-component.se-text .se-text-paragraph')
                if body_ps:
                    body_ps[-1].click()
                    time.sleep(random.uniform(0.4, 0.8))
                page.keyboard.press("Enter")
                time.sleep(random.uniform(0.4, 0.8))

            elif stype == "image":
                idx = section["index"]
                filepath = image_paths.get(idx)
                img_alt = next((i.get("alt", "") for i in image_infos if i["index"] == idx), "")
                if not img_alt:
                    img_alt = keyword or title or ""

                # image_paths에 없으면 images 폴더에서 검색
                if not filepath:
                    for info in image_infos:
                        if info["index"] == idx:
                            fname = info.get("filename", "")
                            if fname:
                                candidate = images_dir / fname
                                if candidate.is_file():
                                    filepath = str(candidate)
                            break

                if filepath and os.path.isfile(filepath):
                    log(f"[포스팅] 이미지 {idx} 업로드: {Path(filepath).name}")
                    ok = _naver_upload_image(page, filepath, log, alt=img_alt)
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
                        # [텍스트](URL) 마크다운 링크 → 하이퍼링크 삽입
                        # [BOLD]...[/BOLD] → **...** 변환
                        stripped = re.sub(r'\[BOLD\](.*?)\[/BOLD\]', r'**\1**', stripped, flags=re.IGNORECASE)
                        if re.search(r'\[.+?\]\(https?://[^\)]+\)', stripped):
                            _naver_type_line_with_links(page, stripped)
                        # **볼드** 처리 (Ctrl+B)
                        elif '**' in stripped:
                            _naver_type_line_with_bold(page, stripped)
                        else:
                            _chunked_type(page, stripped, chunk_size=50)
                        if li < len(lines) - 1:
                            # 모바일 가독성: 줄 사이 Enter 두 번 (독립 문단으로 분리)
                            page.keyboard.press("Enter")
                            time.sleep(random.uniform(0.2, 0.5))
                            page.keyboard.press("Enter")
                            time.sleep(random.uniform(0.2, 0.5))
                    # 문단 사이 Enter 두 번
                    if pi < len(paragraphs) - 1:
                        page.keyboard.press("Enter")
                        time.sleep(random.uniform(0.3, 0.6))
                        page.keyboard.press("Enter")
                        time.sleep(random.uniform(0.3, 0.6))
                # 섹션 끝 Enter
                page.keyboard.press("Enter")
                time.sleep(random.uniform(0.8, 1.5))

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

        # ── 발행 패널 열기 → 카테고리 + 태그 설정 ──
        try:
            _naver_dismiss_overlays(page)
            pub_panel_btn = page.locator('.publish_btn__m9KHH')
            if pub_panel_btn.is_visible(timeout=3000):
                pub_panel_btn.click()
                time.sleep(random.uniform(1.5, 2.5))
                log("[포스팅] 발행 패널 열림")

                # 카테고리 선택
                category = account.get("category", "")
                if category:
                    try:
                        cat_btn = page.locator('.selectbox_button__jb1Dt')
                        if cat_btn.is_visible(timeout=3000):
                            cat_btn.click()
                            time.sleep(random.uniform(0.8, 1.5))
                            items = page.locator('.item__sAGX9')
                            count = items.count()
                            for i in range(count):
                                item = items.nth(i)
                                item_text = (item.text_content() or "").strip()
                                if category in item_text:
                                    item.click()
                                    time.sleep(random.uniform(0.5, 1.0))
                                    log(f"[포스팅] 카테고리 '{item_text}' 선택 완료")
                                    break
                    except Exception as _ce:
                        log(f"[포스팅] 카테고리 선택 오류: {_ce}")

                # 태그 입력
                if tags:
                    try:
                        tag_input = page.locator('#tag-input')
                        if tag_input.is_visible(timeout=3000):
                            tag_ok = 0
                            for tag in tags[:10]:
                                try:
                                    tag_input.click()
                                    time.sleep(random.uniform(0.2, 0.5))
                                    tag_input.fill(tag.strip())
                                    page.keyboard.press("Enter")
                                    time.sleep(random.uniform(0.5, 1.0))
                                    tag_ok += 1
                                except Exception as _te:
                                    log(f"[포스팅] 태그 '{tag}' 입력 오류: {_te}")
                            log(f"[포스팅] 태그 {tag_ok}개 입력 완료")
                        else:
                            log("[포스팅] 태그 입력창 미발견 — 건너뜀")
                    except Exception as _tage:
                        log(f"[포스팅] 태그 입력 실패: {_tage}")

                # 발행 패널 닫기 — 패널이 완전히 닫혀야 임시저장 버튼이 노출됨
                # 패널 바깥 헤더 영역 클릭 → Escape → 제목 입력창 클릭 순으로 시도
                try:
                    closed = False
                    # 1순위: 헤더 영역 클릭 (패널 바깥)
                    header = page.locator('.se-header')
                    if header.is_visible(timeout=1500):
                        header.click(position={"x": 300, "y": 20})
                        time.sleep(0.8)
                        closed = True
                    if not closed:
                        page.keyboard.press("Escape")
                        time.sleep(0.8)
                    # 패널이 사라졌는지 확인
                    panel_still_open = page.locator('.publish_btn__m9KHH').is_visible(timeout=1000)
                    if panel_still_open:
                        page.keyboard.press("Escape")
                        time.sleep(0.5)
                        # 제목 입력창 클릭으로 포커스 이동
                        title_input = page.locator('.se-title-input')
                        if title_input.is_visible(timeout=1000):
                            title_input.click()
                        time.sleep(0.8)
                    log("[포스팅] 발행 패널 닫힘")
                except Exception:
                    page.keyboard.press("Escape")
                    time.sleep(1.0)
            else:
                log("[포스팅] 발행 패널 버튼 미발견 — 태그/카테고리 건너뜀")
        except Exception as _panel_e:
            log(f"[포스팅] 발행 패널 처리 오류: {_panel_e}")

        # ── 임시저장 — 발행 패널이 닫힌 상태에서만 클릭 ──
        log("[포스팅] 임시저장 중...")
        _naver_dismiss_overlays(page)
        time.sleep(random.uniform(1.0, 1.5))
        saved = False
        try:
            # 저장 버튼 찾기 — "발행" 텍스트 버튼은 절대 클릭 금지
            saved = page.evaluate("""() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const text = btn.textContent.trim();
                    if (text === '발행' || text === '공개발행' || text === '발행하기') continue;
                    if (text === '임시저장' || text === '저장' || text.includes('임시저장') || text.includes('저장')) {
                        btn.click(); return text;
                    }
                }
                return false;
            }""")
            if saved:
                log(f"[포스팅] 저장 버튼 클릭: '{saved}'")
                saved = True
        except Exception:
            pass
        if not saved:
            # 폴백: 클래스명으로 찾기
            try:
                save_btn = page.locator('.save_btn__bzc5B')
                if save_btn.is_visible(timeout=2000):
                    save_btn.click()
                    saved = True
            except Exception:
                pass
        if not saved:
            page.keyboard.press("Meta+s")
        _rand_delay(page, 2000, 3000)
        log(f"[포스팅] 임시저장 {'완료' if saved else '(Meta+S 시도)'}: {title[:30]}...")
        return True

        # ── 아래는 사용 안 함 (임시저장 후 return) — 발행 폴백용 보존 ──
        saved = page.evaluate("""() => {
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {
                if (btn.textContent.includes('임시저장')) {
                    btn.click(); return true;
                }
            }
            return false;
        }""")
        _rand_delay(page, 2000, 3000)
        if saved:
            log(f"[포스팅] 네이버 임시저장 완료(폴백): {title[:30]}...")
            return True
        log("[포스팅] 발행/임시저장 버튼 모두 없음 — 실패")
        return False

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
            # 빈 줄 → 단락 사이 시각적 간격 추가 (<p>&nbsp;</p>)
            if html_parts and html_parts[-1] not in ('<p>&nbsp;</p>', '') and not html_parts[-1].startswith('<h'):
                html_parts.append('<p>&nbsp;</p>')
            continue

        if stripped.startswith("### "):
            html_parts.append(f"<h3>{inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            h2_count[0] += 1
            html_parts.append(f'<h2 id="section-{h2_count[0]}">{inline(stripped[3:])}</h2>')
        elif stripped == "[애드센스]":
            pass  # Ad Inserter 플러그인이 처리 — 코드 삽입 불필요
        elif re.match(r"^\{\{이미지\d+\}\}$", stripped):
            html_parts.append(stripped)  # 이미지 플레이스홀더 유지
        elif re.match(r"^<h[2-6]\b", stripped, re.IGNORECASE):
            # <h2>/<h3> 등 HTML 헤딩 태그 — 그대로 통과 (마크다운 ## 대신 HTML 생성 시)
            html_parts.append(stripped)
        elif re.match(r"^<(p|div|ul|ol|li|blockquote|pre|figure|img|script|ins|br|hr|table|strong|em)\b",
                      stripped, re.IGNORECASE):
            # 이미 HTML 블록 태그로 시작하는 줄 — 그대로 통과 (이중 래핑 방지)
            html_parts.append(stripped)
        else:
            # 일반 텍스트 — stray HTML 태그 제거 후 <p> 래핑 (inline 변환으로 **bold** 처리)
            clean = re.sub(r"<br\s*/?>", " ", stripped)
            clean = re.sub(r"<[^>]+>", "", clean).strip()
            if clean:
                html_parts.append(f"<p>{inline(clean)}</p>")

    if table_buf:
        html_parts.append(flush_table())

    # H2/H3/이미지/애드센스 앞뒤 강제 빈 줄 2칸 삽입 (Tistory와 동일 규칙)
    WP_SP = '<p>&nbsp;</p>'

    def _wp_needs_spacing(tag: str) -> bool:
        return (
            tag.startswith('<h2') or
            tag.startswith('<h3') or
            bool(re.match(r'^\{\{이미지\d+\}\}$', tag)) or
            'adsbygoogle' in tag or
            tag.startswith('<script') and 'pagead' in tag
        )

    spaced = []
    for i, tag in enumerate(html_parts):
        nxt = html_parts[i + 1] if i < len(html_parts) - 1 else None
        if _wp_needs_spacing(tag):
            if spaced and spaced[-1] != WP_SP:
                spaced += [WP_SP, WP_SP]
            spaced.append(tag)
            if nxt and nxt != WP_SP:
                spaced += [WP_SP, WP_SP]
        else:
            spaced.append(tag)

    return "\n".join(spaced)


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

    import re as _re
    ext = os.path.splitext(filename)[1] or ".jpg"
    ascii_filename = _re.sub(r'[^\x20-\x7e]', '', filename).strip() or f"image{ext}"
    upload_headers = {
        "Authorization": auth_header,
        "Content-Disposition": f'attachment; filename="{ascii_filename}"',
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

    import re as _re
    ext = os.path.splitext(filename)[1] or ".jpg"
    ascii_filename = _re.sub(r'[^\x20-\x7e]', '', filename).strip() or f"image{ext}"
    upload_headers = {
        "Authorization": auth_header,
        "Content-Disposition": f'attachment; filename="{ascii_filename}"',
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
                    image_infos=None, thumbnail_path=None, on_log=None):
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

    # 0. 제목/본문 정리 — Claude 생성물에 포함된 내부 마커/프롬프트 제거
    title = re.sub(r'^\*\*', '', title).strip()  # 제목 앞 ** 제거
    title = re.sub(r'\*\*$', '', title).strip()  # 제목 뒤 ** 제거
    # ===이미지=== ... ===이미지끝=== 섹션 (Gemini 프롬프트 포함) 제거
    content = re.sub(r'===이미지===.*?===이미지끝===', '', content, flags=re.DOTALL)
    # ═══...═══ 품질 체크 블록 제거
    content = re.sub(r'═{3,}.*?═{3,}', '', content, flags=re.DOTALL)
    # {{마이리얼트립링크}} 등 미치환 플레이스홀더 제거 ({{이미지N}}은 나중에 처리하므로 제외)
    content = re.sub(r'\{\{(?!이미지\d+\}\})[^}]+\}\}', '', content)
    # [이미지N] / [/이미지N] 잔재 제거 ({{이미지N}} 플레이스홀더로 치환되지 못한 경우)
    content = re.sub(r'\[/?이미지\s*\d+\]', '', content)

    # [애드센스] 마커 제거 — Ad Inserter 플러그인이 자동 삽입하므로 코드 삽입 불필요
    content = re.sub(r'\[애드센스\]', '', content)

    # 2. 마크다운 → HTML 변환
    html_content = _md_to_wp_html(content)

    # 2. 썸네일(특성 이미지) 업로드 — 본문과 별개
    _featured_media_id = None
    _thumb_src = thumbnail_path or (image_paths.get(0) if image_paths else None)
    if _thumb_src and Path(_thumb_src).exists():
        _thumb_url, _thumb_mid = _wp_upload_image_with_id(
            site_url, auth_header, _thumb_src, alt=f"{keyword} 대표이미지", on_log=on_log)
        if _thumb_mid:
            _featured_media_id = _thumb_mid
            log(f"[WordPress] 썸네일 업로드 완료: media_id={_thumb_mid}")

    # 2-1. 이미지 업로드 후 {{이미지N}} 플레이스홀더 교체 (index 1부터, 본문 전용)
    info_map = {img["index"]: img for img in image_infos}

    def _replace_image(m):
        idx = int(m.group(1))
        filepath = image_paths.get(idx, "")
        alt = info_map.get(idx, {}).get("alt", "")
        if idx == 1 and keyword and keyword not in alt:
            alt = f"{keyword} {alt}".strip()
        if filepath:
            url, media_id = _wp_upload_image_with_id(
                site_url, auth_header, filepath, alt=alt, on_log=on_log)
            if url:
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

    # 8. 글 임시저장 (발행은 Claude Code 검수 후 별도 수행)
    post_body = {
        "title": title,
        "content": html_content,
        "status": "draft",
        "slug": slug,
        "tags": tag_ids,
        "categories": category_ids,
        "meta": {
            "rank_math_focus_keyword": keyword,
            "rank_math_title": seo_title,
            "rank_math_description": meta_desc,
        },
    }
    # 특성 이미지(featured image) 설정 — 별도 생성한 썸네일
    if _featured_media_id:
        post_body["featured_media"] = _featured_media_id
        log(f"[WordPress] 특성 이미지 설정: media_id={_featured_media_id}")

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
        log(f"[WordPress] ✓ 임시저장 완료: {post_url}")

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
                keyword: str = "", thumbnail_path: str = None, on_log=None):
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
                             image_infos=image_infos, thumbnail_path=thumbnail_path,
                             on_log=on_log)
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
                           keyword=keyword, thumbnail_path=thumbnail_path, on_log=on_log)
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
