"""
publish_drafts.py
각 블로그의 임시저장 글 1개씩 → 이미지/애드센스 확인·보완 → 공개 발행

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

# .env 로드
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

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

# 블로그별 실제 도메인 (GSC 색인 요청용)
BLOG_DOMAIN = {
    "goodisak": "welfare.baremi542.com",
    "nolja100": "issue.baremi542.com",
    "baremi542": "baremi542.com",
    "woll100":  "info.baremi542.com",
    "phn0502":  "film.baremi542.com",
}

# ─── DB 상태 업데이트 ──────────────────────────
def _mark_keyword_published(blog_id: str, title: str):
    """발행 성공 후 keyword_blog_status 테이블을 draft_saved → published 로 업데이트.

    매칭 우선순위:
    1. DB에 저장된 title과 발행 제목이 정확히 일치하는 키워드
    2. DB title이 발행 제목에 포함되거나 발행 제목이 DB title에 포함
    3. 키워드 자체가 발행 제목에 포함
    4. 가장 최근 draft_saved 키워드 (최후 폴백)
    """
    try:
        from keyword_engine.db_handler import _conn, set_keyword_status
        with _conn() as db:
            rows = db.execute(
                "SELECT keyword, title FROM keyword_blog_status "
                "WHERE blog_id=? AND status='draft_saved' ORDER BY updated_at DESC",
                (blog_id,)
            ).fetchall()
        if not rows:
            return
        matched = None
        # 1순위: DB 저장 title과 발행 제목 정확히 일치
        for kw, saved_title in rows:
            if saved_title and saved_title.strip() == title.strip():
                matched = kw
                break
        # 2순위: 부분 포함
        if not matched:
            for kw, saved_title in rows:
                if saved_title and (saved_title in title or title in saved_title):
                    matched = kw
                    break
        # 3순위: 키워드가 제목에 포함
        if not matched:
            for kw, _ in rows:
                if kw and kw in title:
                    matched = kw
                    break
        # 최후 폴백: 가장 최근 draft_saved
        if not matched:
            matched = rows[0][0]
        set_keyword_status(matched, "published", blog_id)
        _log(f"[{blog_id}] DB 업데이트: '{matched}' → published")
    except Exception as e:
        _log(f"[{blog_id}] DB 업데이트 실패: {e}")


# ─── 로그 ───────────────────────────────────────
def _log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ─── 이미지 생성 (image_router: Bing → Pollinations) ──────────────────
def _make_image(prompt: str, filename: str, blog_id: str = "", title: str = "") -> str | None:
    """image_router로 이미지 생성 (Bing → Pollinations). 썸네일은 title 오버레이 적용."""
    try:
        from image_router import generate_images_for_blog
        index = 0  # 썸네일(첫 번째 이미지)로 사용될 경우 오버레이 적용
        results = generate_images_for_blog(
            blog_id=blog_id or "goodisak",
            image_infos=[{"index": index, "prompt": prompt, "filename": filename}],
            skip_webp=False,
            on_log=_log,
            title=title if title else None,
        )
        if results and index in results:
            _log(f"[이미지] 생성 완료 → {Path(results[index]).name}")
            return results[index]
    except Exception as e:
        _log(f"[이미지] image_router 실패: {e}")
    return None


# ══════════════════════════════════════════════
# WordPress (baremi542)
# ══════════════════════════════════════════════
TRIPLOG_URL = "https://app.baremi542.com"


def _wp_auth(user_env="WP_USER", pass_env="WP_APP_PASSWORD"):
    wp_user = os.environ.get(user_env, "") or os.environ.get("WP_USER", "")
    wp_pass = (os.environ.get(pass_env, "") or os.environ.get("WP_APP_PASSWORD", "")).replace(" ", "")
    if not wp_user or not wp_pass:
        raise RuntimeError(f"{user_env} / {pass_env} 환경변수 미설정")
    token = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
    return f"Basic {token}"


def _wp_api(path: str, method="GET", data=None, auth=None, site_url=None):
    """WordPress REST API 요청."""
    url = site_url or SITE_URL
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    req = urllib.request.Request(
        f"{url}/wp-json/wp/v2/{path}",
        data=json.dumps(data).encode() if data else None,
        headers=headers,
        method=method,
    )
    return json.loads(_wp_urlopen(req, timeout=20).read())


def _wp_health_check(url=None) -> bool:
    """WordPress 사이트 살아있는지 확인"""
    check_url = url or SITE_URL
    try:
        req = urllib.request.Request(
            f"{check_url}/wp-json/",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        resp = urllib.request.urlopen(req, timeout=8, context=ctx)
        return resp.status == 200
    except Exception as e:
        _log(f"[WP] 헬스체크 실패 ({check_url}): {e}")
        return False


def publish_wp_draft():
    _log("── baremi542 (WordPress) 드래프트 처리 시작 ──")

    # 사이트 헬스체크 먼저
    if not _wp_health_check():
        _log("[WP] baremi542.com 응답 없음 (사이트 다운) — 스킵. 호스팅 상태 확인 필요.")
        return False

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

    # ── 품질 검수 + 자동/Claude 수정 ──
    wp_issues = _content_quality_gate(content_html, title, "baremi542")
    if wp_issues:
        fixed_html, remaining = _auto_repair_content(content_html, wp_issues)
        if fixed_html != content_html:
            _log("[WP] 자동 수정 적용")
            content_html = fixed_html
        if remaining:
            repaired = _claude_repair_draft(content_html, title, remaining, "baremi542")
            if repaired:
                content_html = repaired
                re_issues = _content_quality_gate(content_html, title, "baremi542")
                if re_issues:
                    _notify_issue("baremi542", title, re_issues)
                    return False
            else:
                _notify_issue("baremi542", title, remaining)
                return False

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
            fp = _make_image(title, f"{slug}-img{i}.jpg", blog_id="baremi542", title=title if i == 1 else "")
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

    # 공개 발행
    patch_data = {
        "status": "publish",
        "content": updated_content,
    }
    result = _wp_api(f"posts/{post_id}", method="POST", data=patch_data, auth=auth)
    new_status = result.get("status", "?")
    new_link = result.get("link", "")
    _log(f"[WP] 발행 완료 → status={new_status}, link={new_link}")
    if new_status == "publish":
        _mark_keyword_published("baremi542", title)
    if new_link:
        from gsc_indexing import request_indexing
        request_indexing(new_link)
    return new_status == "publish"


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
# 콘텐츠 품질 검수 게이트 (모든 블로그 공통)
# ══════════════════════════════════════════════
def _content_quality_gate(content: str, title: str, blog_id: str) -> list:
    """발행 전 콘텐츠 품질 검수. 문제 목록 반환 (빈 리스트 = 통과).

    검사 항목:
    1. 템플릿 마커 잔재 (===본문===, Gemini프롬프트: 등)
    2. 본문 길이 너무 짧음 (2000자 미만)
    3. 제목이 키워드 수준으로 짧음 (10자 미만)
    4. 동일 이미지 중복 삽입
    """
    issues = []

    # 1. 템플릿 마커 잔재 체크
    BAD_MARKERS = [
        '===본문===', '===이미지===', '===태그===', '===태그끝===',
        '===이미지끝===', 'Gemini프롬프트:', '- 파일명:', '- alt:',
        '===본문끝===', '===제목끝===', '{{이미지1}}', '{{이미지2}}', '{{이미지3}}',
        '[검증 필요]', '[출처 필요]', '[애드센스]', '[TODO]', '[FIXME]',
    ]
    for marker in BAD_MARKERS:
        if marker in content:
            issues.append(f"템플릿 마커 노출: '{marker}'")
            break  # 첫 번째만 보고해도 충분
    # 동적 이미지 마커 잔재: {{이미지N}} (숫자 무관)
    if re.search(r'\{\{이미지\d+\}\}', content):
        issues.append("이미지 마커 미교체: '{{이미지N}}' 잔재 발견")

    # 2. 본문 길이 체크 (HTML 태그 제거 후 순수 텍스트)
    plain = re.sub(r'<[^>]+>', ' ', content)
    plain = re.sub(r'\s+', ' ', plain).strip()
    if len(plain) < 2000:
        issues.append(f"본문 너무 짧음 ({len(plain)}자 < 2000자) — 내용 보완 필요")

    # 3. 제목 길이 체크
    if len(title.strip()) < 10:
        issues.append(f"제목 너무 짧음 ({len(title.strip())}자): '{title}'")

    # 4. 키워드 밀도 체크
    main_keyword = title.strip().split()[0] if title.strip() else ""
    if len(main_keyword) >= 3:
        words = plain.split()
        if len(words) >= 100:
            count = sum(1 for w in words if main_keyword in w)
            density = (count / len(words)) * 100
            if density < 0.5:
                issues.append(f"키워드 밀도 너무 낮음 ({density:.1f}%) — 메인키워드 의도적으로 배치 필요")
            elif density > 4.0:
                issues.append(f"키워드 과최적화 ({density:.1f}%) — 스팸 패널티 위험")

    # 5. 중복 이미지 체크
    img_srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE)
    if len(img_srcs) > 1:
        seen = set()
        for src in img_srcs:
            base = src.split('?')[0]  # 쿼리스트링 제거 후 비교
            if base in seen:
                issues.append(f"중복 이미지 발견: {base[-40:]}")
                break
            seen.add(base)

    if issues:
        _log(f"[{blog_id}] ❌ 품질 검수 실패:")
        for issue in issues:
            _log(f"[{blog_id}]   - {issue}")
    else:
        _log(f"[{blog_id}] ✅ 품질 검수 통과")
    return issues


def _notify_issue(blog_id: str, title: str, issues: list):
    """수동 확인 필요 시 텔레그램으로 알림."""
    msg = (
        f"⚠️ 검수 실패 — 수동 확인 필요\n"
        f"블로그: {blog_id}\n"
        f"제목: {title}\n"
        f"이슈:\n" + "\n".join(f"  - {i}" for i in issues)
    )
    _log(f"[알림] {msg}")
    try:
        import urllib.request as _ur, urllib.parse as _up, json as _json, ssl as _ssl
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            return
        chat_id = "8674424194"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = _json.dumps({"chat_id": chat_id, "text": msg}).encode()
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        req = _ur.Request(url, data=data, headers={"Content-Type": "application/json"})
        _ur.urlopen(req, timeout=10, context=ctx)
    except Exception as e:
        _log(f"[알림] 텔레그램 전송 실패: {e}")


def _auto_repair_content(content: str, issues: list) -> tuple[str, list]:
    """자동 수정 가능한 이슈를 처리하고 (수정된 콘텐츠, 남은 이슈) 반환.

    자동 수정:
    - 마커 잔재 제거 (===본문===, Gemini프롬프트: 등)
    - 중복 이미지 제거

    자동 수정 불가:
    - 본문 너무 짧음 → Claude 수정 필요
    - 제목 너무 짧음 → 수동 확인 필요
    """
    fixed = content
    remaining = []

    for issue in issues:
        if "템플릿 마커 노출" in issue:
            # 마커 패턴 제거
            marker_patterns = [
                r'===제목===.*?===제목끝===\s*',
                r'===본문===\s*', r'===본문끝===\s*',
                r'===이미지===.*?===이미지끝===\s*',
                r'===태그===.*?===태그끝===\s*',
                r'\[이미지\d+\]\s*\n?- Gemini프롬프트:.*?\n.*?\n.*?\n',
                r'- Gemini프롬프트:.*?\n',
                r'- 파일명:.*?\n',
                r'- alt:.*?\n',
                r'\[이미지\d+\]\s*',
                r'\{\{이미지\d+\}\}',
                r'===제목===\s*', r'===이미지===\s*', r'===태그===\s*',
                r'\[검증 필요\]', r'\[출처 필요\]', r'\[애드센스\]',
                r'\[TODO\]', r'\[FIXME\]',
            ]
            before = fixed
            for pattern in marker_patterns:
                fixed = re.sub(pattern, '', fixed, flags=re.DOTALL)
            if fixed != before:
                _log(f"  → 마커 자동 제거 완료")
            else:
                remaining.append(issue)

        elif "이미지 마커 미교체" in issue:
            # {{이미지N}} 잔재 제거 (이미지 삽입 실패 시 마커만 남은 경우)
            before = fixed
            fixed = re.sub(r'\{\{이미지\d+\}\}', '', fixed)
            if fixed != before:
                _log(f"  → 이미지 마커 자동 제거 완료")
            else:
                remaining.append(issue)

        elif "중복 이미지" in issue:
            # 두 번째 이상 같은 src 이미지 태그 제거
            seen_srcs = set()
            def _dedup_img(m):
                src = re.search(r'src=["\']([^"\']+)["\']', m.group(0))
                if not src:
                    return m.group(0)
                base = src.group(1).split('?')[0]
                if base in seen_srcs:
                    return ''  # 중복 제거
                seen_srcs.add(base)
                return m.group(0)
            fixed = re.sub(r'<img[^>]+>', _dedup_img, fixed)
            _log(f"  → 중복 이미지 자동 제거 완료")

        else:
            # 자동 수정 불가 이슈
            remaining.append(issue)

    return fixed, remaining


def _claude_repair_draft(content: str, title: str, issues: list, blog_id: str) -> str | None:
    """Claude를 사용해 글 내용을 수정. 수정된 HTML 반환 (실패 시 None).

    본문이 너무 짧거나 내용 문제가 있을 때 호출.
    subprocess로 분리 실행 — sync_playwright 중복 인스턴스 충돌 방지.
    """
    import subprocess, sys, json as _json, tempfile, os
    _log(f"[{blog_id}] Claude 수정 요청 중...")
    try:
        # HTML → plain text 변환
        plain = re.sub(r'<[^>]+>', '', content)
        plain = re.sub(r'\s+', ' ', plain).strip()
        wrapped = f"===제목===\n{title}\n===제목끝===\n\n===본문===\n{plain}\n===본문끝==="

        # 임시 파일로 입력/출력 교환 (subprocess에서 Playwright 사용)
        in_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8')
        _json.dump({'text': wrapped, 'issues': issues}, in_file, ensure_ascii=False)
        in_file.close()
        out_file = in_file.name + '_out.json'

        repair_script = f"""
import sys, json
data = json.load(open({repr(in_file.name)}, encoding='utf-8'))
sys.path.insert(0, {repr(str(Path(__file__).parent))})
from claude_playwright import repair_text
result = repair_text(data['text'], data['issues'])
json.dump({{'result': result}}, open({repr(out_file)}, 'w', encoding='utf-8'), ensure_ascii=False)
"""
        proc = subprocess.run(
            [sys.executable, '-c', repair_script],
            timeout=120, capture_output=True, text=True
        )
        if proc.returncode != 0:
            _log(f"[{blog_id}] Claude 수정 subprocess 실패: {proc.stderr[:200]}")
            return None

        result_data = _json.loads(open(out_file, encoding='utf-8').read())
        repaired_raw = result_data.get('result')
        if not repaired_raw:
            return None

        # 수정된 raw에서 본문 추출 후 HTML 변환 (단락 → <p>)
        body_m = re.search(r'===본문===\s*\n(.*?)\n*===본문끝===', repaired_raw, re.DOTALL)
        if not body_m:
            return None
        body_text = body_m.group(1).strip()
        paragraphs = [p.strip() for p in re.split(r'\n{2,}', body_text) if p.strip()]
        repaired_html = '\n'.join(f'<p>{p}</p>' for p in paragraphs)
        _log(f"[{blog_id}] Claude 수정 완료 ({len(repaired_html)}자)")
        return repaired_html
    except Exception as e:
        _log(f"[{blog_id}] Claude 수정 실패: {e}")
        return None
    finally:
        for f in [in_file.name, out_file]:
            try:
                os.unlink(f)
            except Exception:
                pass


# ══════════════════════════════════════════════
# Tistory (goodisak / nolja100)
# ══════════════════════════════════════════════
def _tistory_ensure_login(page, blog_id: str) -> bool:
    """기존 page에서 티스토리 로그인 상태 확인·로그인. 탭을 새로 열지 않음."""
    import random as _rnd
    config = ACCOUNT_MAP.get(blog_id, {})
    kakao_id = config.get("kakao_id", "")
    blog_url = f"https://{blog_id}.tistory.com/manage"
    TISTORY_LOGIN_URL = "https://www.tistory.com/auth/login"

    try:
        page.evaluate("window.onbeforeunload = null")
    except Exception:
        pass

    page.goto(blog_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(_rnd.randint(2000, 3000))

    # 이미 manage 접근 성공
    if "/manage" in page.url and "tistory.com" in page.url:
        _log(f"[{blog_id}] 로그인 상태 확인됨")
        return True

    # 다른 계정 세션 → 로그아웃 후 재시도
    if "tistory.com" in page.url and "auth/login" not in page.url:
        page.goto("https://www.tistory.com/auth/logout", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2000)

    # 로그인 페이지로 이동
    page.goto(TISTORY_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(_rnd.randint(2000, 3000))

    if "auth/login" in page.url:
        try:
            kakao_btn = page.locator('a.btn_login.link_kakao_id, a[class*="kakao"]').first
            kakao_btn.click(timeout=10000)
            page.wait_for_timeout(_rnd.randint(3000, 5000))
        except Exception as e:
            _log(f"[{blog_id}] 카카오 버튼 클릭 실패: {e}")
            return False

    # 카카오 계정 선택
    if kakao_id:
        try:
            acc = page.locator(f'a.wrap_profile:has-text("{kakao_id}")').first
            acc.wait_for(state="visible", timeout=8000)
            acc.click()
            page.wait_for_timeout(_rnd.randint(3000, 5000))
        except Exception:
            pass

    # 동의 화면
    try:
        agree = page.locator('button:has-text("동의하고 계속하기"), button:has-text("확인")').first
        if agree.is_visible(timeout=3000):
            agree.click()
            page.wait_for_timeout(2000)
    except Exception:
        pass

    # 로그인 완료 대기
    for _ in range(30):
        url = page.url
        if "tistory.com" in url and "auth/login" not in url and "kakao" not in url:
            _log(f"[{blog_id}] 티스토리 로그인 성공")
            page.goto(blog_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            return "/manage" in page.url
        page.wait_for_timeout(_rnd.randint(800, 1200))

    _log(f"[{blog_id}] 로그인 실패 — URL: {page.url}")
    return False


def _tistory_get_draft_id(page, blog_id: str) -> str | None:
    """에디터 임시저장 목록에서 첫 번째 유효한 드래프트를 에디터에 로드.
    성공 시 'loaded' 반환 (이후 page.goto 불필요).
    """
    editor_url = f"https://{blog_id}.tistory.com/manage/newpost/"
    _log(f"[{blog_id}] 에디터 이동: {editor_url}")
    # beforeunload 다이얼로그 방지 (Node.js24 unhandled rejection 크래시 방지)
    try:
        page.evaluate("window.onbeforeunload = null")
    except Exception:
        pass
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

    # 유사 중복 감지용 — 핵심 단어 집합으로 변환
    def _title_core_words(t):
        import re as _re
        _STOP = {'방법', '하는', '하기', '위한', '이란', '이다', '그리고', '직접', '써보고', '써봤다',
                 '느낀', '차이', '비교', '알아보자', '총정리', '정리', '추천', '꿀팁', '후기',
                 '완벽', '완전', '정말', '진짜', '무엇인지', '알아보기', '한다면'}
        words = _re.findall(r'[가-힣a-zA-Z0-9]+', t)
        return {w for w in words if len(w) >= 2 and w not in _STOP}

    published_core_sets = [_title_core_words(t) for t in published_titles]

    def _is_similar_to_published(title):
        """발행된 글과 핵심어 55% 이상 겹치면 중복으로 판단"""
        core = _title_core_words(title)
        if not core:
            return False
        for pub_core in published_core_sets:
            overlap = core & pub_core
            if len(overlap) >= max(3, len(core) * 0.55):
                return True
        return False

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
                            del_btn.click()
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
        # 제목 품질 검수: 너무 짧으면 키워드만 들어간 불완전 글 → 스킵
        if len(title) < 8:
            _log(f"[{blog_id}] 제목 너무 짧음({len(title)}자) — 스킵: '{title}'")
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
        # 유사 중복 체크 (핵심어 기반)
        if _is_similar_to_published(title):
            _log(f"[{blog_id}] 유사 중복 감지 — 스킵: '{title}'")
            continue

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

    # ── 품질 검수 + 자동/Claude 수정 ──
    issues = _content_quality_gate(content, title, blog_id)
    if issues:
        # 1단계: 자동 수정 시도 (마커 제거, 중복 이미지)
        fixed_content, remaining = _auto_repair_content(content, issues)
        if fixed_content != content:
            _log(f"[{blog_id}] 자동 수정 적용 — 에디터 업데이트")
            page.evaluate("(c) => tinymce.activeEditor.setContent(c)", fixed_content)
            content = fixed_content

        if remaining:
            # 2단계: 자동 수정 후에도 남은 이슈 → Claude 수정 시도
            _log(f"[{blog_id}] 남은 이슈 {len(remaining)}개 — Claude 수정 시도")
            repaired = _claude_repair_draft(content, title, remaining, blog_id)
            if repaired:
                page.evaluate("(c) => tinymce.activeEditor.setContent(c)", repaired)
                content = repaired
                # 재검수
                re_issues = _content_quality_gate(content, title, blog_id)
                if re_issues:
                    _log(f"[{blog_id}] ⛔ 수정 후에도 검수 실패 — 텔레그램 알림 후 스킵")
                    _notify_issue(blog_id, title, re_issues)
                    return False
            else:
                _log(f"[{blog_id}] ⛔ Claude 수정 실패 — 텔레그램 알림 후 스킵")
                _notify_issue(blog_id, title, remaining)
                return False

    # 이미지 체크 (Tistory [##_Image 형식 포함)
    has_images = '<img' in content or '[##_Image' in content
    _log(f"[{blog_id}] 이미지 있음: {has_images}")

    # 애드센스 체크 (Tistory 서식 삽입 시 나타나는 class/data 속성)
    has_adsense = bool(
        re.search(r'adsbygoogle|tistory-ad|data-ad|애드센스', content, re.IGNORECASE)
    )
    _log(f"[{blog_id}] 애드센스 있음: {has_adsense}")

    # 이미지 보완 — 없으면 picsum으로 3개 생성 후 업로드
    if not has_images:
        _log(f"[{blog_id}] 이미지 없음 → 생성·업로드 중...")
        slug = re.sub(r'[^\w가-힣]', '-', title.strip()).strip('-')[:30]
        uploaded = 0
        for i in range(1, 4):
            fp = _make_image(title, f"{blog_id}-{slug}-{i}.jpg", blog_id=blog_id, title=title if i == 1 else "")
            if fp:
                if i == 1:
                    page.evaluate("""() => {
                        const ed = tinymce.activeEditor;
                        ed.selection.select(ed.getBody(), true);
                        ed.selection.collapse(true);  // 맨 앞
                    }""")
                ok = _tistory_upload_image(page, fp, alt=title, on_log=_log)
                if ok:
                    uploaded += 1
                    _log(f"[{blog_id}] 이미지 {i} 업로드 성공")
                    time.sleep(2)
        if uploaded == 0:
            _log(f"[{blog_id}] ❌ 이미지 생성/업로드 모두 실패 → 발행 중단")
            return False

    # 애드센스 보완
    if not has_adsense:
        _log(f"[{blog_id}] 애드센스 없음 → 서식 삽입 중...")
        # 에디터 중간 위치로 커서 이동 후 삽입
        # 이미지 직후 빈 p 제외, 텍스트가 있는 단락 기준으로 중간 선택
        page.evaluate("""() => {
            const ed = tinymce.activeEditor;
            const body = ed.getBody();
            const allParas = [...body.querySelectorAll('p, h2, h3')];
            // 텍스트가 있고, 바로 앞 형제가 figure/이미지가 아닌 단락만 추출
            const textParas = allParas.filter(el => {
                const txt = el.innerText.trim();
                if (txt.length < 10) return false;  // 빈 단락 제외
                const prev = el.previousElementSibling;
                if (prev && (prev.tagName === 'FIGURE' || prev.querySelector('img'))) return false;  // 이미지 직후 제외
                return true;
            });
            const paras = textParas.length >= 3 ? textParas : allParas;
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

    # 1-1. 썸네일(대표이미지) 설정 — 발행 패널에서 첫 번째 이미지 선택
    thumb_result = page.evaluate("""() => {
        // 발행 패널에서 이미지 목록 찾기 (썸네일 선택 UI)
        const selectors = [
            '.cover-image-list img',
            '.thumbnail-list img',
            '[class*="cover"] img',
            '[class*="thumb"] img',
            '.attach-image-wrap img',
            '[class*="imageSelect"] img',
            '[class*="representative"] img',
        ];
        for (const sel of selectors) {
            const imgs = document.querySelectorAll(sel);
            if (imgs.length > 0) {
                imgs[0].click();
                return 'set:' + sel;
            }
        }
        return null;
    }""")
    if thumb_result:
        _log(f"[{blog_id}] 썸네일 설정 완료 ({thumb_result})")
        time.sleep(0.5)
    else:
        _log(f"[{blog_id}] 썸네일 UI 없음 — 기본값 유지")

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

    # 2-1. 댓글 비허용 설정
    comment_result = page.evaluate("""() => {
        // 방법A: Tistory TinyMCE 에디터 — "댓글 허용" select-menu 드롭다운 클릭 후 "댓글 비허용" 선택
        const selectTxts = [...document.querySelectorAll('i.mce-txt')];
        const commentSelectTxt = selectTxts.find(i => i.textContent === '댓글 허용');
        if (commentSelectTxt) {
            const btn = commentSelectTxt.closest('button');
            if (btn) {
                btn.click(); // 드롭다운 열기
                return '__need_dropdown__';
            }
        }
        // 방법B: 이미 드롭다운이 열려있다면 "댓글 비허용" 클릭
        const menuItems = [...document.querySelectorAll('[role="menuitem"]')];
        const noCommentItem = menuItems.find(el => el.textContent.trim() === '댓글 비허용');
        if (noCommentItem) { noCommentItem.click(); return 'mce-dropdown-비허용'; }
        // 방법C: name 속성
        const byName = document.querySelector(
            'input[name="commentAccepting"], input[name="comment_accepting"], ' +
            'input[name="commentStatus"], input[name="comment-allow"]'
        );
        if (byName && byName.type === 'checkbox' && byName.checked) { byName.click(); return 'checkbox-name'; }
        // 방법D: 체크박스
        const checkboxes = [...document.querySelectorAll('input[type=checkbox]')];
        for (const cb of checkboxes) {
            const lbl = cb.closest('label') || document.querySelector(`label[for="${cb.id}"]`);
            if (lbl && lbl.textContent.includes('댓글') && cb.checked) {
                cb.click(); return 'checkbox-댓글';
            }
        }
        return null;
    }""")
    time.sleep(0.5)
    # 드롭다운이 열렸으면 "댓글 비허용" 클릭
    if comment_result == '__need_dropdown__':
        time.sleep(0.5)
        comment_result = page.evaluate("""() => {
            const menuItems = [...document.querySelectorAll('[role="menuitem"]')];
            const noCommentItem = menuItems.find(el => el.textContent.trim() === '댓글 비허용');
            if (noCommentItem) { noCommentItem.click(); return 'mce-dropdown-비허용'; }
            return null;
        }""")
    time.sleep(0.5)
    if comment_result:
        _log(f"[{blog_id}] 댓글 비허용 설정 완료 ({comment_result})")
    else:
        _log(f"[{blog_id}] ⚠️ 댓글 비허용 요소 못 찾음 — 기본값 유지")

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

    # 4. 성공 확인 — 신버전 에디터는 publish 후에도 manage/newpost/#에 머뭄
    time.sleep(2)
    cur_url = page.url
    _log(f"[{blog_id}] 최종 URL: {cur_url}")
    # URL이 변경됐으면 확실히 성공, 아니면 버튼 클릭 자체를 성공으로 간주
    return True


def publish_triplog_draft() -> bool:
    """app.baremi542.com (트립로그) 드래프트 발행"""
    _log("── triplog (WordPress) 드래프트 처리 시작 ──")

    if not _wp_health_check(TRIPLOG_URL):
        _log("[triplog] 사이트 응답 없음 — 스킵")
        return False

    try:
        auth = _wp_auth("TRIPLOG_WP_USER", "TRIPLOG_WP_APP_PASSWORD")
    except RuntimeError as e:
        _log(f"[triplog] {e} — 스킵")
        return False

    drafts = _wp_api("posts?status=draft&per_page=10&orderby=modified&order=desc", auth=auth, site_url=TRIPLOG_URL)
    if not drafts:
        _log("[triplog] 드래프트 없음 — 스킵")
        return False

    def _score(p):
        return len(re.sub(r'<[^>]+>', '', p.get("content", {}).get("rendered", "")))
    post = max(drafts, key=_score)
    post_id = post["id"]
    title = post["title"]["rendered"]
    content_html = post["content"]["rendered"]
    _log(f"[triplog] 선택된 드래프트: [{post_id}] {title} ({len(content_html)}자)")

    has_images = bool(re.search(r'<img\s', content_html))
    updated_content = content_html

    if not has_images:
        _log("[triplog] 이미지 없음 → loremflickr 생성 중...")
        slug = re.sub(r'[^\w가-힣]', '-', title.strip()).strip('-')[:40]
        for i in range(1, 3):
            fp = _make_image(title, f"{slug}-img{i}.jpg", blog_id="triplog", title=title if i == 1 else "")
            if fp:
                img_url, _ = _wp_upload_image_with_id(TRIPLOG_URL, auth, fp, alt=title, on_log=_log)
                if img_url:
                    fig = f'<figure class="wp-block-image"><img src="{img_url}" alt="{title}"/></figure>\n'
                    if i == 1:
                        updated_content = re.sub(r'(</p>)', r'\1' + fig, updated_content, count=1)
                    else:
                        mid = len(updated_content) // 2
                        ins = updated_content.find('</p>', mid)
                        if ins > 0:
                            updated_content = updated_content[:ins + 4] + fig + updated_content[ins + 4:]

    result = _wp_api(f"posts/{post_id}", method="POST",
                     data={"status": "publish", "content": updated_content},
                     auth=auth, site_url=TRIPLOG_URL)
    new_status = result.get("status", "")
    new_link = result.get("link", "")
    _log(f"[triplog] 발행 결과: {new_status} — {title}")
    if new_status == "publish":
        _mark_keyword_published("triplog", title)
    if new_link and new_status == "publish":
        from gsc_indexing import request_indexing
        request_indexing(new_link)
    return new_status == "publish"


def publish_tistory_draft(blog_id: str) -> bool:
    _log(f"── {blog_id} (Tistory) 드래프트 처리 시작 ──")
    account = ACCOUNT_MAP.get(blog_id)
    if not account:
        _log(f"[{blog_id}] ACCOUNT_MAP에 없음")
        return False

    # 단일 세션: 로그인 + 발행을 같은 탭에서 처리
    pw, browser = connect_cdp(on_log=_log)
    try:
        page = get_or_create_page(browser)

        # 로그인 확인 & 처리 (새 탭 열지 않음)
        if not _tistory_ensure_login(page, blog_id):
            _log(f"[{blog_id}] 로그인 실패 — 중단")
            return False

        # 임시저장 게시물 로드 (에디터 드래프트 목록에서 직접 로드)
        draft_id = _tistory_get_draft_id(page, blog_id)
        if not draft_id:
            _log(f"[{blog_id}] 임시저장 글 없음 — 스킵")
            return False

        # 로그인 상태 재확인
        if "accounts.kakao.com" in page.url or "auth/login" in page.url:
            _log(f"[{blog_id}] 로그인 세션 만료 — 중단")
            return False

        # TinyMCE 로드 대기
        time.sleep(2)

        # 이미지/애드센스 체크 및 보완
        if not _tistory_check_and_fix(page, blog_id, draft_id):
            return False

        # 제목 읽기 (DB 업데이트용)
        _draft_title = ""
        for _sel in ['#post-title-inp', '#title', 'input[name="title"]', '.title-input']:
            _el = page.query_selector(_sel)
            if _el:
                _draft_title = (_el.input_value() or "").strip()
                if _draft_title:
                    break

        # nolja100: 여행 주제 아닌 글은 발행 금지
        if blog_id == "nolja100":
            # 여러 셀렉터 시도
            title_val = ""
            for sel in ['#post-title-inp', '#title', 'input[name="title"]', '.title-input']:
                el = page.query_selector(sel)
                if el:
                    title_val = (el.input_value() or "").strip()
                    if title_val:
                        break
            # 셀렉터 실패 시 페이지 제목에서 추출
            if not title_val:
                title_val = page.evaluate("() => document.title || ''")
            TRAVEL_KW = ["여행", "관광", "숙소", "호텔", "펜션", "맛집", "카페", "코스",
                         "드라이브", "당일치기", "뚜벅", "트레킹", "둘레길", "섬", "해변",
                         "온천", "리조트", "캠핑", "글램핑", "국내", "해외", "항공", "투어",
                         "페리", "지하철", "자갈치", "제주", "강릉", "부산", "경주", "강원",
                         "서울", "인천", "대전", "광주", "전주", "수원", "춘천", "속초",
                         "벚꽃", "단풍", "여의도", "한강", "공원", "축제", "주차", "명소",
                         "나들이", "피크닉", "산책", "데이트", "야경", "뷰", "포토스팟",
                         "진해", "군항제", "창원", "하동", "광양", "왕십리", "경주", "안양",
                         "봄나들이", "봄여행", "꽃구경", "명소", "주차장", "셔틀", "입장료",
                         "통영", "여수", "거제", "남해", "순천", "전주", "군산", "목포"]
            is_travel = any(kw in title_val for kw in TRAVEL_KW)
            if not is_travel:
                if not title_val:
                    # 제목을 못 읽은 경우 — 삭제 대신 스킵 (nolja100 봇은 여행만 씀)
                    _log(f"[nolja100] ⚠ 제목 읽기 실패 — 여행 글로 간주하고 발행 진행")
                else:
                    _log(f"[nolja100] ⛔ 여행 주제 아님 (제목: {title_val[:40]}) → 발행 중단 (임시저장 삭제)")
                    page.evaluate("""() => {
                        const btns = [...document.querySelectorAll('button')];
                        const del = btns.find(b => b.textContent.includes('삭제'));
                        if (del) del.click();
                    }""")
                    return False
            _log(f"[nolja100] ✅ 여행 주제 확인: {title_val[:40]}")

        # woll100: 교통 주제 아닌 글은 발행 금지
        if blog_id == "woll100":
            title_val = ""
            for sel in ['#post-title-inp', '#title', 'input[name="title"]']:
                el = page.query_selector(sel)
                if el:
                    title_val = (el.input_value() or "").strip()
                    if title_val:
                        break
            TRAFFIC_KW = ["공항", "버스", "리무진", "시외버스", "KTX", "기차", "지하철",
                          "교통", "시간표", "요금", "노선", "정류장", "예매", "소요시간",
                          "출발", "도착", "인천공항", "김포공항", "김해공항", "제주공항",
                          "대구공항", "청주공항", "무안공항", "공항철도", "셔틀버스"]
            is_traffic = any(kw in title_val for kw in TRAFFIC_KW)
            if title_val and not is_traffic:
                _log(f"[woll100] ⛔ 교통 주제 아님 (제목: {title_val[:40]}) → 스킵 (임시저장 삭제)")
                try:
                    del_links = page.query_selector_all('a.link_del, button.btn_del, [data-action="delete"]')
                    if del_links:
                        del_links[0].click()
                        time.sleep(1)
                except Exception:
                    pass
                return False
            if title_val:
                _log(f"[woll100] ✅ 교통 주제 확인: {title_val[:40]}")

        # phn0502: 영화/OTT 주제 아닌 글은 발행 금지
        if blog_id == "phn0502":
            title_val = ""
            for sel in ['#post-title-inp', '#title', 'input[name="title"]']:
                el = page.query_selector(sel)
                if el:
                    title_val = (el.input_value() or "").strip()
                    if title_val:
                        break
            MOVIE_KW = ["영화", "넷플릭스", "왓챠", "웨이브", "티빙", "OTT", "결말", "줄거리",
                        "해석", "쿠키", "배우", "출연", "드라마", "시리즈", "애니", "액션",
                        "로맨스", "스릴러", "공포", "신작", "장르", "추천", "평점", "명작"]
            is_movie = any(kw in title_val for kw in MOVIE_KW)
            if title_val and not is_movie:
                _log(f"[phn0502] ⛔ 영화 주제 아님 (제목: {title_val[:40]}) → 스킵 (임시저장 삭제)")
                try:
                    del_links = page.query_selector_all('a.link_del, button.btn_del, [data-action="delete"]')
                    if del_links:
                        del_links[0].click()
                        time.sleep(1)
                except Exception:
                    pass
                return False
            if title_val:
                _log(f"[phn0502] ✅ 영화 주제 확인: {title_val[:40]}")

        # goodisak: IT+금융 주제 아닌 글은 발행 금지
        if blog_id == "goodisak":
            title_val = ""
            for sel in ['#post-title-inp', '#title', 'input[name="title"]', '.title-input']:
                el = page.query_selector(sel)
                if el:
                    title_val = (el.input_value() or "").strip()
                    if title_val:
                        break
            BLOCK_KW = ["여행", "관광", "숙소", "호텔", "펜션", "맛집", "카페", "코스",
                        "드라이브", "당일치기", "트레킹", "둘레길", "해변", "온천", "리조트",
                        "캠핑", "글램핑", "항공", "축제", "벚꽃", "단풍", "나들이", "피크닉",
                        "산책", "데이트", "야경", "포토스팟", "제주", "강릉", "경주", "강원",
                        "주차장", "셔틀", "입장료", "DMZ", "평화생명", "군항제", "살림",
                        "세탁", "청소", "요리", "냄새", "수납", "세제", "주방"]
            if title_val and any(kw in title_val for kw in BLOCK_KW):
                _log(f"[goodisak] ⛔ IT+금융 주제 아님 (제목: {title_val[:40]}) → 스킵 (임시저장 삭제)")
                try:
                    page.evaluate("""() => {
                        const btns = [...document.querySelectorAll('button')];
                        const del = btns.find(b => b.textContent.includes('삭제'));
                        if (del) del.click();
                    }""")
                except Exception:
                    pass
                return False
            if title_val:
                _log(f"[goodisak] ✅ IT+금융 주제 확인: {title_val[:40]}")

        # 공개 발행
        ok = _tistory_publish_private(page, blog_id)
        if ok:
            _log(f"[{blog_id}] ✓ 공개 발행 완료")
            _mark_keyword_published(blog_id, _draft_title)
            # 색인 요청: 최신 발행글 URL 가져오기
            try:
                time.sleep(3)
                custom_domain = BLOG_DOMAIN.get(blog_id)
                page.goto(f"https://{blog_id}.tistory.com/manage/posts/", wait_until="domcontentloaded", timeout=20000)
                time.sleep(2)
                latest_url = page.evaluate("""() => {
                    const links = document.querySelectorAll('a[href]');
                    for (const a of links) {
                        if (/tistory\\.com\\/\\d+/.test(a.href)) return a.href;
                    }
                    return null;
                }""")
                if latest_url and custom_domain:
                    # tistory.com URL → 커스텀 도메인 URL로 변환
                    import re as _re
                    m = _re.search(r'/(\d+)$', latest_url.rstrip('/'))
                    if m:
                        latest_url = f"https://{custom_domain}/{m.group(1)}"
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

    # 임시저장 개수 버튼 클릭 (다양한 셀렉터 시도)
    opened = page.evaluate("""() => {
        const selectors = [
            '.save_count_btn__ZTLNa',
            '[class*="save_count_btn"]',
            '[class*="draftCount"]',
            '[class*="draft_count"]',
            '[class*="saveDraftCount"]',
            'button[aria-label*="임시저장"]',
            'a[aria-label*="임시저장"]',
        ];
        for (const sel of selectors) {
            const btn = document.querySelector(sel);
            if (btn) {
                const n = parseInt(btn.textContent.trim().replace(/[^0-9]/g,''));
                if (n > 0) { btn.click(); return n; }
            }
        }
        // 텍스트 "임시저장"이 포함된 버튼 중 숫자가 있는 것
        const allBtns = [...document.querySelectorAll('button, a')];
        for (const btn of allBtns) {
            const txt = btn.textContent.trim();
            if (txt.includes('임시저장')) {
                const n = parseInt(txt.replace(/[^0-9]/g,''));
                if (n > 0) { btn.click(); return n; }
            }
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
    loaded = page.evaluate("""([skipSet, publishedSet]) => {
        var lis = document.querySelectorAll('li');
        for (var i = 0; i < lis.length; i++) {
            var titleEl = lis[i].querySelector('[class*="title__"]');
            if (!titleEl) continue;
            var title = titleEl.textContent.trim();
            if (!title || skipSet.includes(title) || publishedSet.includes(title)) continue;
            if (title.length < 10) continue;  // 제목 너무 짧으면 스킵
            var clickable = lis[i].querySelector('[class*="article_button"]') || lis[i];
            clickable.click();
            return title;
        }
        return null;
    }""", [list(SKIP), list(published_titles)])

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


def _naver_delete_all_images(page) -> int:
    """Naver SE3 에디터에서 이미지 컴포넌트 전체 삭제. 삭제된 개수 반환.

    SE3 이미지 블록은 .se-module-image (컴포넌트 래퍼).
    JS로 클릭 → 삭제 버튼(.se-btn-remove) 클릭 방식으로 제거.
    클릭 방식 실패 시 DOM 직접 제거 폴백.
    """
    deleted = page.evaluate("""() => {
        let count = 0;
        // SE3 이미지 모듈 전체 선택
        const modules = document.querySelectorAll(
            '.se-module-image, [class*="se-module"][class*="image"], .se-component-image'
        );
        modules.forEach(mod => {
            try {
                // 삭제 버튼 클릭 시도 (SE3 컴포넌트 내 remove 버튼)
                const removeBtn = mod.querySelector(
                    '.se-btn-remove, [class*="btn_remove"], [class*="delete"], button[title*="삭제"]'
                );
                if (removeBtn) {
                    removeBtn.click();
                    count++;
                    return;
                }
                // 삭제 버튼 없으면 컴포넌트 자체 제거
                const component = mod.closest('.se-component') || mod;
                component.remove();
                count++;
            } catch(e) {}
        });
        return count;
    }""")
    _log(f"[Naver] 기존 이미지 {deleted}개 삭제")
    if deleted > 0:
        import time as _t; _t.sleep(1)
    return deleted


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


def _naver_publish_public(page, category: str = None) -> bool:
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

    # 공개 옵션 선택 — 반드시 전체공개 (이웃공개 아님)
    page.evaluate("""() => {
        // 1순위: 라벨 텍스트로 정확히 "전체공개" 찾기
        const allEls = [...document.querySelectorAll('label, span, li, a, button')];
        const pubLabel = allEls.find(el => el.textContent.trim() === '전체공개');
        if (pubLabel) { pubLabel.click(); return; }

        // 2순위: radio value/id에서 public/0/open 포함 (all/1 제외 — 이웃공개일 수 있음)
        const inputs = [...document.querySelectorAll('input[type="radio"]')];
        const pub = inputs.find(r => {
            const v = (r.value || r.id || '').toLowerCase();
            // 'all'/'1' 은 이웃공개일 수 있으므로 제외
            return v === 'public' || v === 'open' || v === '0' || v === 'everyone';
        });
        if (pub) { pub.click(); return; }

        // 3순위: label[for] 연결된 radio 중 전체공개 텍스트
        for (const label of document.querySelectorAll('label')) {
            if (label.textContent.trim() === '전체공개') {
                const radio = document.getElementById(label.getAttribute('for'));
                if (radio) radio.click();
                else label.click();
                return;
            }
        }
    }""")
    time.sleep(1)

    # 카테고리 선택 (me1091: 리뷰 등)
    if category:
        cat_set = page.evaluate("""(catName) => {
            const allEls = [...document.querySelectorAll(
                '[class*="layer_publish"] li, [class*="isShow__"] li, [class*="is_show__"] li, ' +
                '[class*="layer_publish"] a, [class*="isShow__"] a, ' +
                '[class*="layer_publish"] button, [class*="isShow__"] button'
            )];
            for (const el of allEls) {
                if (el.textContent.trim() === catName) {
                    el.click();
                    return 'clicked:' + catName;
                }
            }
            // select 드롭다운 시도
            const sel = document.querySelector('[class*="layer_publish"] select, [class*="isShow__"] select');
            if (sel) {
                for (const opt of sel.options) {
                    if (opt.text.trim() === catName || opt.text.includes(catName)) {
                        sel.value = opt.value;
                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                        return 'select:' + opt.text;
                    }
                }
            }
            return null;
        }""", category)
        if cat_set:
            _log(f"[Naver] 카테고리 설정: {cat_set}")
            time.sleep(0.5)
        else:
            _log(f"[Naver] 카테고리 '{category}' 항목 없음 — 스킵")

    # 발행 확인 버튼 (confirm_btn__* 우선, 메인 publish_btn 제외)
    confirmed = page.evaluate("""() => {
        const mainPublishBtn = document.querySelector('button[class*="publish_btn__"]');
        // 1순위: confirm_btn 클래스 버튼
        const confirmBtn = document.querySelector('[class*="confirm_btn__"]');
        if (confirmBtn && !confirmBtn.disabled) { confirmBtn.click(); return '발행(confirm)'; }
        // 2순위: 팝업 레이어 내 발행/확인 버튼 (메인 버튼 제외)
        const labels = ['발행', '확인', '게시', '등록'];
        const btns = [...document.querySelectorAll(
            '[class*="layer_publish"] button, [class*="is_show__"] button, [class*="isShow__"] button'
        )].filter(b => b !== mainPublishBtn);
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
        naver_title = info.get('title', '')
        _log(f"[{blog_id}] 제목: {naver_title}")
        _log(f"[{blog_id}] 이미지: {info.get('hasImages')}, 글자수: {info.get('length','?')}")

        # 에디터 텍스트에서도 품질 검수 (마커 잔재 등)
        naver_text = page.evaluate("() => document.body.innerText || ''")
        issues = _content_quality_gate(naver_text, naver_title, blog_id)
        if issues:
            # Naver SE3 에디터는 setContent가 어려우므로 자동 수정만 시도
            fixed_text, remaining = _auto_repair_content(naver_text, issues)
            if remaining:
                # 자동 수정 불가 → 텔레그램 알림 후 스킵 (Naver는 에디터 직접 수정 어려움)
                _log(f"[{blog_id}] ⛔ 품질 검수 실패 — 텔레그램 알림 후 스킵")
                _notify_issue(blog_id, naver_title, remaining)
                return False

        # 글자수 체크
        if info.get('length', 0) < 1700:
            _log(f"[{blog_id}] 글자수 부족({info.get('length')}자) — 스킵")
            return False

        # 공개 발행 (me1091은 리뷰 카테고리)
        cat = "리뷰" if blog_id == "me1091" else None
        ok = _naver_publish_public(page, category=cat)
        if ok:
            _log(f"[{blog_id}] ✓ 공개 발행 완료")
            _mark_keyword_published(blog_id, naver_title)
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
# 3라운드 완료 후 분석 & 보고
# ══════════════════════════════════════════════
def _fetch_rss_titles(url: str, limit: int = 10) -> list:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10, context=ctx).read().decode()
        items = re.findall(r'<item>(.*?)</item>', resp, re.DOTALL)
        result = []
        for item in items[:limit]:
            t = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item)
            d = re.search(r'<pubDate>(.*?)</pubDate>', item)
            if t:
                result.append({"title": t.group(1).strip(), "date": (d.group(1)[:16] if d else "")})
        return result
    except Exception:
        return []


def _analyze_and_report(all_results: list):
    """3라운드 전체 결과 분석 → Telegram 보고 + Notion 기록."""
    import datetime, sqlite3

    today = datetime.date.today().isoformat()
    _log("[분석] 3라운드 완료 — 블로그 집계 시작")

    # ── 오늘 발행 집계 ──────────────────────────
    rss_map = {
        "goodisak":  "https://welfare.baremi542.com/rss",
        "nolja100":  "https://issue.baremi542.com/rss",
        "salim1su":  "https://rss.blog.naver.com/salim1su.xml",
        "baremi542": "https://baremi542.com/feed",
    }
    today_posts = {}
    for blog, rss in rss_map.items():
        posts = _fetch_rss_titles(rss, limit=20)
        today_count = sum(1 for p in posts if today[:7] in p["date"])  # 이번 달
        today_exact = sum(1 for p in posts if today in p["date"])
        today_posts[blog] = {"total_recent": len(posts), "this_month": today_count, "today": today_exact}

    # ── 라운드별 발행 집계 ──────────────────────
    round_summary = []
    blog_total = {"goodisak": 0, "nolja100": 0, "salim1su": 0, "baremi542": 0}
    for rnum, results in all_results:
        ok_blogs = [b for b, v in results.items() if v is True]
        skip_blogs = [b for b, v in results.items() if v is None]
        fail_blogs = [b for b, v in results.items() if v is False]
        for b in ok_blogs:
            blog_total[b] = blog_total.get(b, 0) + 1
        round_summary.append(f"R{rnum}: ✅{','.join(ok_blogs) or '없음'} | ⏭{','.join(skip_blogs) or '없음'} | ⚠{','.join(fail_blogs) or '없음'}")

    # ── 키워드 잔량 ──────────────────────────────
    kw_remain = {}
    try:
        import sqlite3 as _sqlite3
        _db_path2 = Path(__file__).parent / "keyword_engine" / "engine.db"
        db = _sqlite3.connect(str(_db_path2))
        rows = db.execute(
            "SELECT category, COUNT(*) FROM keywords WHERE status NOT IN ('published','failed') GROUP BY category"
        ).fetchall()
        for cat, cnt in rows:
            kw_remain[cat] = cnt
        db.close()
    except Exception:
        pass

    # ── 부진 원인 분석 ──────────────────────────
    issues = []
    blog_theme = {"goodisak": "IT", "nolja100": "여행", "salim1su": "살림", "baremi542": "정부지원금"}
    for blog, totals in blog_total.items():
        if totals == 0:
            theme = blog_theme.get(blog, "")
            kw_cat = "정부지원" if blog == "baremi542" else theme
            remain = kw_remain.get(kw_cat, 0) + kw_remain.get("정부지원금", 0) if blog == "baremi542" else kw_remain.get(theme, 0)
            if remain == 0:
                issues.append(f"{blog}: 키워드 고갈 → 키워드 엔진 재실행 필요")
            else:
                issues.append(f"{blog}: 임시저장 없음 (overnight bot 확인 필요)")

    if "salim1su" in blog_total and blog_total["salim1su"] < 2:
        issues.append("salim1su: 네이버 애드포스트 미신청 → 수익 불가 (신청 필요)")

    # ── Telegram 보고 ────────────────────────────
    kw_str = " | ".join(f"{k} {v}개" for k, v in kw_remain.items())
    msg_lines = [
        f"📊 [3라운드 완료 보고] {today}",
        "",
        "📝 블로그별 오늘 발행:",
    ]
    for blog, cnt in blog_total.items():
        icon = "✅" if cnt > 0 else "⚠"
        msg_lines.append(f"  {icon} {blog}: {cnt}건")
    msg_lines += ["", "🔄 라운드 상세:"] + [f"  {s}" for s in round_summary]
    msg_lines += ["", f"📦 키워드 잔량: {kw_str}"]
    if issues:
        msg_lines += ["", "⚠ 보완 필요:"] + [f"  • {i}" for i in issues]

    telegram_msg = "\n".join(msg_lines)

    # Telegram 전송
    try:
        env = Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent))) / ".env"
        bot_token, chat_id = "", ""
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    bot_token = line.split("=", 1)[1].strip()
                elif line.startswith("TELEGRAM_CHAT_ID="):
                    chat_id = line.split("=", 1)[1].strip()
        if bot_token and chat_id:
            payload = json.dumps({"chat_id": chat_id, "text": telegram_msg}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
            _log("[분석] Telegram 보고 전송 완료")
    except Exception as e:
        _log(f"[분석] Telegram 전송 실패: {e}")

    # Notion 기록 (notion_report.json에 저장 — 다음 CCR 세션이 읽어서 업로드)
    try:
        report = {
            "date": today,
            "round_summary": round_summary,
            "blog_total": blog_total,
            "kw_remain": kw_remain,
            "issues": issues,
        }
        Path("/tmp/daily_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        _log("[분석] /tmp/daily_report.json 저장 완료")
    except Exception as e:
        _log(f"[분석] 보고서 저장 실패: {e}")

    print(telegram_msg)


# ══════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════
if __name__ == "__main__":
    import random
    import json as _json
    import fcntl

    # ── 중복 실행 방지 락 ──
    _LOCK_FILE = Path("/tmp/publish_drafts.lock")
    _lock_fd = open(_LOCK_FILE, "w")
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        _log("⚠ 이미 publish_drafts.py 실행 중 — 중복 실행 방지로 종료")
        sys.exit(0)

    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    ROUNDS = 3
    ROUND_GAP_MIN = 12600   # 3.5시간
    ROUND_GAP_MAX = 14400   # 4시간
    MIN_BLOG_GAP  = 12600   # 같은 블로그 재발행 최소 간격 (3.5시간)

    # 마지막 발행 시간 파일 (세션 간 유지)
    TIMES_FILE = Path(__file__).parent / "logs" / "blog_publish_times.json"
    last_published: dict = {}
    if TIMES_FILE.exists():
        try:
            last_published = _json.loads(TIMES_FILE.read_text())
        except Exception:
            pass

    all_results = []

    for round_num in range(1, ROUNDS + 1):
        blog_order = ["baremi542", "goodisak", "nolja100", "salim1su", "me1091", "triplog", "woll100", "phn0502"]
        random.shuffle(blog_order)
        _log(f"[라운드 {round_num}] 순서: {blog_order}")
        round_results = {}

        for blog_id in blog_order:
            if target not in ("all", blog_id):
                continue

            # 같은 블로그 재발행 간격 체크
            # nolja100/triplog는 여행 블로그 그룹 — 하나가 발행되면 둘 다 3.5h 대기
            TRAVEL_GROUP = {"nolja100", "triplog"}
            now = time.time()
            if blog_id in TRAVEL_GROUP:
                last = max(last_published.get(b, 0) for b in TRAVEL_GROUP)
            else:
                last = last_published.get(blog_id, 0)
            elapsed = now - last
            if elapsed < MIN_BLOG_GAP:
                remain = int(MIN_BLOG_GAP - elapsed)
                _log(f"[{blog_id}] 간격 미충족 — {remain//3600}시간 {(remain%3600)//60}분 후 재시도 가능, 스킵")
                round_results[blog_id] = None
                continue

            if blog_id == "baremi542":
                ok = publish_wp_draft()
            elif blog_id == "triplog":
                ok = publish_triplog_draft()
            elif blog_id == "goodisak":
                ok = publish_tistory_draft("goodisak")
            elif blog_id == "nolja100":
                ok = publish_tistory_draft("nolja100")
            elif blog_id == "salim1su":
                ok = publish_naver_draft("salim1su")
            elif blog_id == "me1091":
                ok = publish_naver_draft("me1091")
            elif blog_id == "woll100":
                ok = publish_tistory_draft("woll100")
            elif blog_id == "phn0502":
                ok = publish_tistory_draft("phn0502")
            else:
                ok = False

            round_results[blog_id] = ok
            if ok:
                last_published[blog_id] = time.time()
                TIMES_FILE.write_text(_json.dumps(last_published))

        all_results.append((round_num, round_results))

        # 라운드 완료 후 소셜 포스팅 (RSS 반영 5분 대기 후)
        if any(v for v in round_results.values()):
            _log(f"[소셜] 5분 후 RSS→Facebook/Threads 포스팅 예정...")
            time.sleep(300)
            try:
                import social_post
                social_post.run(on_log=_log)
            except Exception as e:
                _log(f"[소셜] 오류: {e}")

        # 네이버 이웃봇 (salim1su 또는 me1091 발행 성공 시)
        naver_published = any(round_results.get(b) for b in ("salim1su", "me1091"))
        if naver_published:
            _log("[이웃봇] 네이버 발행 완료 → run_neighbor.sh 백그라운드 실행")
            import subprocess as _sp
            _sp.Popen(
                ["bash", str(Path(__file__).parent / "run_neighbor.sh")],
                stdout=open(str(Path(__file__).parent / "logs" / "neighbor.log"), "a"),
                stderr=_sp.STDOUT,
            )

        # 라운드 간 대기 (마지막 라운드 제외)
        if round_num < ROUNDS:
            gap = random.randint(ROUND_GAP_MIN, ROUND_GAP_MAX)
            _log(f"[라운드 {round_num} 완료] {gap//3600}시간 {(gap%3600)//60}분 후 라운드 {round_num+1} 시작")
            time.sleep(gap - 300 if gap > 300 else gap)

    print("\n" + "=" * 50)
    print("[전체 결과]")
    for rnum, results in all_results:
        print(f"  라운드 {rnum}:")
        for blog, ok in results.items():
            if ok is None:
                status = "⏭ 간격 미충족 (스킵)"
            elif ok:
                status = "✅ 공개 발행 완료"
            else:
                status = "⚠ 처리 불완전"
            print(f"    {blog}: {status}")
    print("=" * 50)

    # 3라운드 완료 후 분석 & 보고
    if target == "all":
        _analyze_and_report(all_results)
