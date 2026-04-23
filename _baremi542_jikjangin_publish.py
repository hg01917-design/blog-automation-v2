"""
baremi542 직장인국비지원 글 생성 + 이미지 생성 + WordPress 발행 원스텝 스크립트

흐름:
1. claude --print로 글 생성
2. ===섹션=== 파싱
3. Gemini Playwright로 이미지 생성 (3장)
4. WordPress REST API로 미디어 업로드 + 발행
5. 텔레그램 보고
"""
import sys
import os
import re
import json
import base64
import ssl
import time
import urllib.request
import urllib.error
import urllib.parse
import subprocess
import mimetypes
from pathlib import Path
from datetime import datetime

# ── 경로 설정 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# secrets 로드
_secrets_path = BASE_DIR / "remote_secrets.json"
if _secrets_path.exists():
    _s = json.loads(_secrets_path.read_text())
    for k, v in _s.items():
        os.environ.setdefault(k, v)

# ── WP 설정 ───────────────────────────────────────────────
WP_URL = "https://baremi542.com"
WP_USER = os.environ.get("WP_USER", "")
WP_PASS = os.environ.get("WP_APP_PASSWORD", "").replace(" ", "")
KEYWORD = "직장인국비지원"
BLOG_ID = "baremi542"
IMAGE_SAVE_DIR = Path("/tmp/baremi542_images")
IMAGE_SAVE_DIR.mkdir(parents=True, exist_ok=True)

CLAUDE_BIN = Path.home() / ".local" / "bin" / "claude"

_FIX_LOG = []


def log(msg: str):
    print(msg, flush=True)
    _FIX_LOG.append(msg)


# ── WP helpers ────────────────────────────────────────────
def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _auth_header() -> str:
    token = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
    return f"Basic {token}"


def wp_get(endpoint: str) -> dict:
    url = f"{WP_URL}/wp-json/wp/v2/{endpoint}"
    req = urllib.request.Request(url, headers={
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
    })
    resp = urllib.request.urlopen(req, timeout=20, context=_ssl_ctx())
    return json.loads(resp.read())


def wp_post(endpoint: str, data: dict, method: str = "POST") -> dict:
    url = f"{WP_URL}/wp-json/wp/v2/{endpoint}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
    }, method=method)
    resp = urllib.request.urlopen(req, timeout=30, context=_ssl_ctx())
    return json.loads(resp.read())


def wp_upload_media(image_path: str, filename: str, alt_text: str = "") -> int | None:
    """이미지를 WP 미디어 라이브러리에 업로드. media_id 반환."""
    url = f"{WP_URL}/wp-json/wp/v2/media"
    mime, _ = mimetypes.guess_type(filename)
    if not mime:
        ext = Path(filename).suffix.lower()
        mime = {"webp": "image/webp", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext.lstrip("."), "image/jpeg")
    data = Path(image_path).read_bytes()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": _auth_header(),
        "Content-Type": mime,
        "Content-Disposition": f'attachment; filename="{filename}"',
    }, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=60, context=_ssl_ctx())
        result = json.loads(resp.read())
        media_id = result.get("id")
        # alt text 설정
        if alt_text and media_id:
            try:
                wp_post(f"media/{media_id}", {"alt_text": alt_text}, method="POST")
            except Exception:
                pass
        return media_id
    except Exception as e:
        log(f"[미디어 업로드 실패] {filename}: {e}")
        return None


def get_or_create_tag_id(tag_name: str) -> int | None:
    try:
        res = wp_get(f"tags?search={urllib.parse.quote(tag_name)}")
        if res:
            return res[0]["id"]
        created = wp_post("tags", {"name": tag_name})
        return created["id"]
    except Exception:
        return None


def get_category_id(slug: str = "정부지원금") -> int:
    try:
        cats = wp_get("categories?per_page=50")
        for c in cats:
            if c.get("slug") == slug or c.get("name") == slug:
                return c["id"]
    except Exception:
        pass
    return 1


# ── 1. 글 생성 ───────────────────────────────────────────
def generate_content() -> str:
    """claude --print로 baremi542 직장인국비지원 글 생성."""
    instr_path = BASE_DIR / "project_instructions" / "baremi542.txt"
    instructions = instr_path.read_text(encoding="utf-8").strip() if instr_path.exists() else ""

    _SEO_TITLE_RULE = (
        "\n\n[구글 SEO 제목 규칙 — 필수 준수]\n"
        "① 제목 길이: 30~55자\n"
        "② 메인키워드 제목 맨 앞에\n"
        "③ 연도(2026), 숫자, '방법','비교' 중 하나 포함\n"
        "④ 구어체 금지 → 명사형 사용\n"
        "⑤ 완벽정리/총정리/N가지 나열형 금지\n"
    )
    _DEPTH_RULE = (
        "\n\n[깊이 있는 글쓰기 — 필수]\n"
        "단계별 구체적 방법, 실수하기 쉬운 것 포함, 구체적 수치 필수.\n"
        "글자수 3000자 이상 반드시 달성할 것.\n"
    )
    _BANNED = (
        "\n\n[절대 금지 표현]\n"
        "알아보겠습니다/살펴보겠습니다/소개하겠습니다/정리해드릴게요\n"
        "이번 포스팅에서는/오늘은 ~에 대해/함께 알아볼게요\n"
        "도움이 되셨으면 좋겠습니다 류\n"
        "구분선(---, ***, ___) 절대 금지\n"
    )
    _SECTION_FORMAT = (
        "\n\n아래 형식으로만 출력 (다른 형식 절대 금지):\n"
        "===제목===\n(SEO 최적화된 롱테일 제목)\n===제목끝===\n\n"
        "===본문===\n(블로그 본문 전체 — H2 소제목 3개 이상, 3000자 이상)\n===본문끝===\n\n"
        "===태그===\n태그1, 태그2, ... (10~20개)\n===태그끝===\n\n"
        "===메타===\n메타제목: (60자 이내)\n메타설명: (160자 이내)\n===메타끝===\n"
    )
    _IMAGE_RULE = (
        "\n\n[이미지 규칙 — 필수]\n"
        "본문 내 H2 소제목(##) 바로 아래에 {{이미지N}} 마커 삽입 (N=1부터 순서대로).\n"
        "본문 끝에 ===이미지=== 섹션으로 각 이미지 Gemini 생성 프롬프트 작성:\n"
        "===이미지===\n[이미지1]\n- Gemini프롬프트: (영어 프롬프트)\n- 파일명: (영문-소문자-하이픈.jpg)\n- alt: (키워드 포함 한국어)\n===이미지끝===\n"
    )

    prompt = (
        f"{instructions}\n\n[작성 키워드]\n{KEYWORD}"
        + _SEO_TITLE_RULE + _DEPTH_RULE + _BANNED + _SECTION_FORMAT + _IMAGE_RULE
    )

    log(f"[1단계] Claude 글 생성 시작 (키워드: {KEYWORD})")

    _REMOVE = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT",
               "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_IDE_PORT", "ANTHROPIC_API_KEY"}
    clean_env = {k: v for k, v in os.environ.items() if k not in _REMOVE}
    clean_env["HOME"] = str(Path.home())
    default_paths = [str(Path.home() / ".local/bin"), "/usr/local/bin", "/usr/bin", "/bin"]
    existing_paths = clean_env.get("PATH", "").split(":")
    combined = [p for p in default_paths if p not in existing_paths] + existing_paths
    clean_env["PATH"] = ":".join(p for p in combined if p)

    for attempt in range(1, 4):
        if attempt > 1:
            log(f"[1단계] 재시도 {attempt-1}/2")
        try:
            result = subprocess.run(
                [str(CLAUDE_BIN), "--dangerously-skip-permissions", "--print"],
                input=prompt,
                capture_output=True,
                text=True,
                cwd=str(BASE_DIR),
                timeout=300,
                env=clean_env,
                start_new_session=True,
            )
            raw = (result.stdout or "").strip()
            if result.returncode != 0:
                log(f"[1단계] 종료코드 {result.returncode}")
                continue
            if len(raw) < 500:
                log(f"[1단계] 응답 짧음 ({len(raw)}자) — 재시도")
                continue
            log(f"[1단계] ✅ 글 생성 완료 ({len(raw)}자)")
            return raw
        except subprocess.TimeoutExpired:
            log("[1단계] 타임아웃")
        except Exception as e:
            log(f"[1단계] 오류: {e}")

    return ""


# ── 2. 파싱 ──────────────────────────────────────────────
def parse_raw(raw: str) -> dict | None:
    title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
    body_m = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", raw, re.DOTALL)
    tag_m = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===", raw, re.DOTALL)
    meta_m = re.search(r"===메타===\s*\n(.*?)\n*===메타끝===", raw, re.DOTALL)
    img_m = re.search(r"===이미지===\s*\n(.*?)\n*===이미지끝===", raw, re.DOTALL)

    title = title_m.group(1).strip().split('\n')[0].strip() if title_m else KEYWORD
    body = body_m.group(1).strip() if body_m else raw

    # 태그
    tags = []
    if tag_m:
        tags = [t.strip() for line in tag_m.group(1).strip().split('\n') for t in line.split(',') if t.strip()]
    if not tags:
        tags = [KEYWORD, "국비지원", "직장인", "내일배움카드"]

    # 메타
    meta = {}
    if meta_m:
        for line in meta_m.group(1).strip().split('\n'):
            if ':' in line:
                k, v = line.split(':', 1)
                meta[k.strip()] = v.strip()

    # 이미지
    images = []
    if img_m:
        parts = re.split(r'\[이미지(\d+)\]', img_m.group(1))
        it = iter(parts[1:])
        for idx_str, block in zip(it, it):
            prompt_m = re.search(r'Gemini\s*프롬프트\s*[:：]\s*(.+)', block)
            fname_m = re.search(r'파일명\s*[:：]\s*(.+)', block)
            alt_m = re.search(r'\balt\s*[:：]\s*(.+)', block, re.IGNORECASE)
            if prompt_m and fname_m:
                images.append({
                    "index": int(idx_str),
                    "prompt": prompt_m.group(1).strip(),
                    "filename": fname_m.group(1).strip(),
                    "alt": alt_m.group(1).strip() if alt_m else f"{KEYWORD} 이미지 {idx_str}",
                })

    # 구분선 제거
    body = re.sub(r'(?m)^\s*[-*_]{3,}\s*$', '', body).strip()

    # 글자수 확인
    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
    char_count = len(re.sub(r"\s+", "", plain))
    log(f"[2단계] 제목: \"{title}\" | 본문: {char_count}자 | 이미지: {len(images)}개 | 태그: {len(tags)}개")

    if char_count < 1000:
        log(f"[2단계] ⚠ 본문 너무 짧음 ({char_count}자)")
        return None

    return {"title": title, "body": body, "tags": tags, "meta": meta, "images": images}


# ── 3. Gemini 이미지 생성 ─────────────────────────────────
def generate_images_gemini(images: list) -> dict:
    """image_router를 통해 이미지 생성."""
    if not images:
        log("[3단계] 이미지 정보 없음 — 기본 이미지 생성")
        # 기본 이미지 목록 생성
        images = [
            {
                "index": 1,
                "prompt": "Korean worker studying at a desk with a laptop, online training course, professional development, warm lighting, realistic photo style",
                "filename": "jikjangin-kukbi-1.jpg",
                "alt": "직장인 국비지원 온라인 훈련",
            },
            {
                "index": 2,
                "prompt": "Korean employment center office, people consulting with government officer, job training program documents on desk, realistic photo",
                "filename": "jikjangin-kukbi-2.jpg",
                "alt": "고용센터 직장인 훈련 상담",
            },
            {
                "index": 3,
                "prompt": "Korean adult learner with certificate of completion, government support program, career development training, bright office background",
                "filename": "jikjangin-kukbi-3.jpg",
                "alt": "직장인 국비지원 수료증",
            },
        ]

    log(f"[3단계] 이미지 {len(images)}개 생성 시작 (Gemini Playwright)")
    try:
        from gemini_image import generate_images
        result = generate_images(
            image_infos=images,
            on_log=log,
            skip_webp=False,
            output_dir=IMAGE_SAVE_DIR,
        )
        log(f"[3단계] 이미지 {len(result)}개 생성 완료")
        return result
    except Exception as e:
        log(f"[3단계] Gemini 이미지 생성 실패: {e}")
        log("[3단계] picsum.photos 폴백 시도")
        # picsum 폴백
        import io
        from PIL import Image as PILImage
        result = {}
        _ssl_ctx_local = ssl.create_default_context()
        _ssl_ctx_local.check_hostname = False
        _ssl_ctx_local.verify_mode = ssl.CERT_NONE
        for img_info in images:
            idx = img_info["index"]
            filename = img_info["filename"]
            filename = re.sub(r'[^\w\-.]', '-', filename)
            if not filename.endswith(".webp"):
                filename = filename.rsplit(".", 1)[0] + ".webp"
            seed = (idx * 137 + 42) % 1000
            url = f"https://picsum.photos/seed/{seed}/1024/768"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, timeout=30, context=_ssl_ctx_local)
                data = resp.read()
                img = PILImage.open(io.BytesIO(data))
                save_path = IMAGE_SAVE_DIR / filename
                img.convert("RGB").save(str(save_path), "WEBP", quality=85)
                result[idx] = str(save_path)
                log(f"[3단계] picsum 폴백 저장: {filename}")
            except Exception as e2:
                log(f"[3단계] picsum 폴백 실패 idx={idx}: {e2}")
        return result


# ── 4. 마크다운 → WordPress HTML 변환 ────────────────────
def md_to_html(body: str, image_paths: dict, images_meta: list) -> tuple[str, list]:
    """마크다운 본문 + {{이미지N}} 마커 → WordPress Gutenberg HTML.

    Returns: (html_content, fix_notes)
    """
    fix_notes = []

    # 이미지 index → {path, alt} 매핑
    img_map = {img["index"]: img for img in images_meta}

    # [애드센스] 마커 → 실제 애드센스 shortcode (WordPress용)
    # baremi542는 Rank Math + 애드센스 플러그인 사용
    # 실제 광고 코드 대신 <!-- adsense --> 주석으로 남김 (플러그인이 처리)
    ADSENSE_HTML = '\n<!-- wp:html -->\n<div class="adsense-container" style="text-align:center;margin:20px 0;">[adsense]</div>\n<!-- /wp:html -->\n'

    lines = body.split('\n')
    html_parts = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # {{이미지N}} 마커
        img_match = re.match(r'\{\{이미지(\d+)\}\}', line.strip())
        if img_match:
            idx = int(img_match.group(1))
            if idx in image_paths:
                # 미디어 업로드는 나중에 처리 — 여기선 플레이스홀더
                html_parts.append(f"__IMG_PLACEHOLDER_{idx}__")
            i += 1
            continue

        # [애드센스]
        if line.strip() == "[애드센스]":
            html_parts.append(ADSENSE_HTML)
            i += 1
            continue

        # ## H2 소제목
        h2_m = re.match(r'^##\s+(.+)', line)
        if h2_m:
            text = h2_m.group(1).strip()
            # 마크다운 볼드 제거
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            html_parts.append(f'\n<!-- wp:heading {{"level":2}} -->\n<h2 class="wp-block-heading">{text}</h2>\n<!-- /wp:heading -->\n')
            i += 1
            continue

        # ### H3 소제목
        h3_m = re.match(r'^###\s+(.+)', line)
        if h3_m:
            text = h3_m.group(1).strip()
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            html_parts.append(f'\n<!-- wp:heading {{"level":3}} -->\n<h3 class="wp-block-heading">{text}</h3>\n<!-- /wp:heading -->\n')
            i += 1
            continue

        # 표 (| 로 시작하는 라인들)
        if line.strip().startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            # 구분선 제거 (|---|---|)
            table_data = [l for l in table_lines if not re.match(r'^\s*\|[-|:\s]+\|\s*$', l)]
            if table_data:
                html_parts.append('\n<!-- wp:table -->\n<figure class="wp-block-table"><table>')
                for j, tline in enumerate(table_data):
                    cells = [c.strip() for c in tline.split('|')[1:-1]]
                    tag = 'th' if j == 0 else 'td'
                    row = ''.join(f'<{tag}>{_inline_md(c)}</{tag}>' for c in cells)
                    html_parts.append(f'<tr>{row}</tr>')
                html_parts.append('</table></figure>\n<!-- /wp:table -->\n')
            continue

        # 빈 줄
        if not line.strip():
            html_parts.append('')
            i += 1
            continue

        # 일반 단락
        text = _inline_md(line.strip())
        if text:
            html_parts.append(f'\n<!-- wp:paragraph -->\n<p>{text}</p>\n<!-- /wp:paragraph -->\n')
        i += 1

    # 연속된 빈 줄 정리
    html = '\n'.join(html_parts)
    html = re.sub(r'\n{3,}', '\n\n', html)

    return html, fix_notes


def _inline_md(text: str) -> str:
    """인라인 마크다운 → HTML 변환."""
    # **볼드**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # *이탤릭*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # [링크텍스트](URL)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text


# ── 5. 검수 ──────────────────────────────────────────────
def review_content(title: str, body: str, images_count: int) -> list:
    """검수 후 수정사항 목록 반환."""
    notes = []

    # 마크다운 잔재 확인 (소제목/볼드 잔재)
    if re.search(r'^##\s+', body, re.MULTILINE):
        notes.append("마크다운 소제목(##) 잔재 있음 → 변환 처리")
    if re.search(r'\*\*[^*]+\*\*', body):
        notes.append("마크다운 볼드(**) 잔재 있음 → 변환 처리")

    # 내부 마커 확인
    for marker in ["[검증 필요]", "[출처 필요]", "[TODO]", "[확인 필요]"]:
        if marker in body:
            notes.append(f"내부 마커 '{marker}' 발견 → 제거")

    # 구분선 확인
    if re.search(r'(?m)^\s*[-*_]{3,}\s*$', body):
        notes.append("구분선(---/***) 잔재 → 제거")

    # 글자수 확인
    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
    char_count = len(re.sub(r"\s+", "", plain))
    if char_count < 1700:
        notes.append(f"글자수 부족: {char_count}자 < 1700자")

    # 이미지 수 확인
    if images_count < 3:
        notes.append(f"이미지 {images_count}장 < 3장 필요")

    return notes


# ── 메인 ─────────────────────────────────────────────────
def main():
    start_time = datetime.now()
    log("=" * 60)
    log(f"[baremi542] 직장인국비지원 글 생성+발행 시작")
    log(f"시작시각: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    review_notes = []

    # ── 1. 글 생성 ──
    raw = generate_content()
    if not raw:
        msg = "글 생성 실패 — 종료"
        log(f"❌ {msg}")
        subprocess.run(
            ["python3", "tg_send.py",
             f"⚠️ 오류 발생\n작업: baremi542 직장인국비지원 글 생성/발행\n오류: {msg}\n조치: 종료"],
            cwd=str(BASE_DIR), timeout=30
        )
        return

    # ── 2. 파싱 ──
    log("[2단계] 파싱 시작")
    parsed = parse_raw(raw)
    if not parsed:
        msg = "파싱 실패 — raw 응답 이상"
        log(f"❌ {msg}")
        subprocess.run(
            ["python3", "tg_send.py",
             f"⚠️ 오류 발생\n작업: baremi542 직장인국비지원 글 생성/발행\n오류: {msg}\n조치: 종료"],
            cwd=str(BASE_DIR), timeout=30
        )
        return

    title = parsed["title"]
    body = parsed["body"]
    tags = parsed["tags"]
    images_info = parsed["images"]

    # ── 3. 이미지 생성 ──
    image_paths = generate_images_gemini(images_info)
    if len(image_paths) < 3:
        review_notes.append(f"이미지 {len(image_paths)}장만 생성됨 (3장 목표)")

    # ── 4. 검수 ──
    log("[4단계] 검수 시작")

    # 구분선 제거
    if re.search(r'(?m)^\s*[-*_]{3,}\s*$', body):
        body = re.sub(r'(?m)^\s*[-*_]{3,}\s*$', '', body).strip()
        review_notes.append("구분선(---) 제거")

    # 내부 마커 제거
    for marker in ["[검증 필요]", "[출처 필요]", "[TODO]"]:
        if marker in body:
            body = body.replace(marker, "")
            review_notes.append(f"내부 마커 '{marker}' 제거")

    r_notes = review_content(title, body, len(image_paths))
    if r_notes:
        log(f"[4단계] 검수 이슈: {r_notes}")
        review_notes.extend(r_notes)

    # ── 5. 미디어 업로드 + HTML 변환 ──
    log("[5단계] 미디어 업로드 + HTML 변환")

    # 이미지 업로드
    uploaded_ids = {}  # index → media_id
    for idx, img_path in image_paths.items():
        img_info = next((img for img in images_info if img["index"] == idx), None)
        alt_text = img_info["alt"] if img_info else f"{KEYWORD} 이미지 {idx}"
        filename = Path(img_path).name
        log(f"[5단계] 이미지 {idx} 업로드: {filename}")
        media_id = wp_upload_media(img_path, filename, alt_text)
        if media_id:
            uploaded_ids[idx] = media_id
            log(f"[5단계] ✅ 이미지 {idx} 업로드 완료 (media_id={media_id})")
        else:
            log(f"[5단계] ⚠ 이미지 {idx} 업로드 실패")
            review_notes.append(f"이미지 {idx} 업로드 실패")

    # HTML 변환
    html_content, conv_notes = md_to_html(body, image_paths, images_info)
    review_notes.extend(conv_notes)

    # 플레이스홀더 교체 (업로드된 이미지 URL로)
    for idx, media_id in uploaded_ids.items():
        img_info = next((img for img in images_info if img["index"] == idx), None)
        alt_text = img_info["alt"] if img_info else f"{KEYWORD} 이미지 {idx}"
        # WP 미디어 URL 조회
        try:
            media_data = wp_get(f"media/{media_id}")
            img_url = media_data.get("source_url", "")
            if img_url:
                img_html = (
                    f'\n<!-- wp:image {{"id":{media_id},"sizeSlug":"large","linkDestination":"none"}} -->\n'
                    f'<figure class="wp-block-image size-large">'
                    f'<img src="{img_url}" alt="{alt_text}" class="wp-image-{media_id}"/>'
                    f'</figure>\n<!-- /wp:image -->\n'
                )
                html_content = html_content.replace(f"__IMG_PLACEHOLDER_{idx}__", img_html)
                log(f"[5단계] 이미지 {idx} HTML 교체 완료")
        except Exception as e:
            log(f"[5단계] 이미지 {idx} URL 조회 실패: {e}")
            # 플레이스홀더 제거
            html_content = html_content.replace(f"__IMG_PLACEHOLDER_{idx}__", "")

    # 남은 플레이스홀더 정리
    html_content = re.sub(r'__IMG_PLACEHOLDER_\d+__\n?', '', html_content)

    # ── 6. 카테고리/태그 ID 조회 ──
    log("[6단계] 카테고리/태그 ID 조회")
    cat_id = get_category_id("정부지원금")
    tag_ids = []
    for tag in tags[:10]:
        tid = get_or_create_tag_id(tag)
        if tid:
            tag_ids.append(tid)

    # ── 7. WordPress 발행 ──
    log("[7단계] WordPress 발행")

    post_data = {
        "title": title,
        "content": html_content,
        "status": "publish",
        "categories": [cat_id] if cat_id else [],
        "tags": tag_ids,
    }

    # 썸네일(대표 이미지) 설정 — 첫 번째 이미지
    if 1 in uploaded_ids:
        post_data["featured_media"] = uploaded_ids[1]

    try:
        result = wp_post("posts", post_data)
        post_id = result.get("id")
        post_url = result.get("link", "")
        log(f"[7단계] ✅ 발행 완료!")
        log(f"  게시물 ID: {post_id}")
        log(f"  URL: {post_url}")
    except urllib.error.HTTPError as e:
        reason = e.read().decode(errors="replace")
        log(f"[7단계] ❌ HTTP 오류 {e.code}: {reason[:500]}")
        subprocess.run(
            ["python3", "tg_send.py",
             f"⚠️ 오류 발생\n작업: baremi542 직장인국비지원 발행\n오류: HTTP {e.code} {reason[:200]}\n조치: 확인 필요"],
            cwd=str(BASE_DIR), timeout=30
        )
        return
    except Exception as e:
        log(f"[7단계] ❌ 발행 오류: {e}")
        subprocess.run(
            ["python3", "tg_send.py",
             f"⚠️ 오류 발생\n작업: baremi542 직장인국비지원 발행\n오류: {e}\n조치: 확인 필요"],
            cwd=str(BASE_DIR), timeout=30
        )
        return

    # ── 8. 텔레그램 보고 ──
    end_time = datetime.now()
    fix_summary = "\n- ".join(review_notes) if review_notes else "이상 없음"
    tg_msg = (
        f"✅ 발행 완료\n"
        f"블로그: baremi542\n"
        f"제목: {title}\n"
        f"발행시각: {end_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"URL: {post_url}\n\n"
        f"🔧 검수 중 수정사항:\n- {fix_summary}"
    )
    log(f"\n[8단계] 텔레그램 보고")
    log(tg_msg)
    try:
        subprocess.run(
            ["python3", "tg_send.py", tg_msg],
            cwd=str(BASE_DIR), timeout=30
        )
    except Exception as e:
        log(f"[8단계] 텔레그램 전송 오류: {e}")

    log("\n" + "=" * 60)
    log("✅ 모든 작업 완료")
    log("=" * 60)


if __name__ == "__main__":
    main()
