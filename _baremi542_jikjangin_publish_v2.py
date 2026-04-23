"""
baremi542 직장인국비지원 — 이미지 생성 + WordPress 발행
(글 내용은 /tmp/baremi542_jikjangin_raw.txt 파일에서 읽음)
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

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# secrets 로드
_secrets_path = BASE_DIR / "remote_secrets.json"
if _secrets_path.exists():
    _s = json.loads(_secrets_path.read_text())
    for k, v in _s.items():
        os.environ.setdefault(k, v)

WP_URL = "https://baremi542.com"
WP_USER = os.environ.get("WP_USER", "")
WP_PASS = os.environ.get("WP_APP_PASSWORD", "").replace(" ", "")
KEYWORD = "직장인국비지원"
BLOG_ID = "baremi542"
IMAGE_SAVE_DIR = Path("/tmp/baremi542_images")
IMAGE_SAVE_DIR.mkdir(parents=True, exist_ok=True)
RAW_FILE = Path("/tmp/baremi542_jikjangin_raw.txt")

_FIX_LOG = []


def log(msg: str):
    print(msg, flush=True)
    _FIX_LOG.append(msg)


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


def parse_raw(raw: str) -> dict | None:
    title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
    body_m = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", raw, re.DOTALL)
    tag_m = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===", raw, re.DOTALL)
    meta_m = re.search(r"===메타===\s*\n(.*?)\n*===메타끝===", raw, re.DOTALL)
    img_m = re.search(r"===이미지===\s*\n(.*?)\n*===이미지끝===", raw, re.DOTALL)

    title = title_m.group(1).strip().split('\n')[0].strip() if title_m else KEYWORD
    body = body_m.group(1).strip() if body_m else raw

    tags = []
    if tag_m:
        tags = [t.strip() for line in tag_m.group(1).strip().split('\n') for t in line.split(',') if t.strip()]
    if not tags:
        tags = [KEYWORD, "국비지원", "직장인", "내일배움카드"]

    meta = {}
    if meta_m:
        for line in meta_m.group(1).strip().split('\n'):
            if ':' in line:
                k, v = line.split(':', 1)
                meta[k.strip()] = v.strip()

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

    body = re.sub(r'(?m)^\s*[-*_]{3,}\s*$', '', body).strip()

    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
    char_count = len(re.sub(r"\s+", "", plain))
    log(f"[파싱] 제목: \"{title}\" | 본문: {char_count}자 | 이미지: {len(images)}개 | 태그: {len(tags)}개")

    return {"title": title, "body": body, "tags": tags, "meta": meta, "images": images}


def generate_images_gemini(images: list) -> dict:
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
        import io
        from PIL import Image as PILImage
        result = {}
        _ctx = ssl.create_default_context()
        _ctx.check_hostname = False
        _ctx.verify_mode = ssl.CERT_NONE
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
                resp = urllib.request.urlopen(req, timeout=30, context=_ctx)
                data = resp.read()
                img = PILImage.open(io.BytesIO(data))
                save_path = IMAGE_SAVE_DIR / filename
                img.convert("RGB").save(str(save_path), "WEBP", quality=85)
                result[idx] = str(save_path)
                log(f"[3단계] picsum 저장: {filename}")
            except Exception as e2:
                log(f"[3단계] picsum 실패 idx={idx}: {e2}")
        return result


def _inline_md(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text


def md_to_html(body: str, image_paths: dict, images_meta: list) -> tuple[str, list]:
    fix_notes = []
    img_map = {img["index"]: img for img in images_meta}
    ADSENSE_HTML = '\n<!-- wp:html -->\n<div class="adsense-container" style="text-align:center;margin:20px 0;">[adsense]</div>\n<!-- /wp:html -->\n'

    lines = body.split('\n')
    html_parts = []
    i = 0

    while i < len(lines):
        line = lines[i]

        img_match = re.match(r'\{\{이미지(\d+)\}\}', line.strip())
        if img_match:
            idx = int(img_match.group(1))
            if idx in image_paths:
                html_parts.append(f"__IMG_PLACEHOLDER_{idx}__")
            i += 1
            continue

        if line.strip() == "[애드센스]":
            html_parts.append(ADSENSE_HTML)
            i += 1
            continue

        h2_m = re.match(r'^##\s+(.+)', line)
        if h2_m:
            text = h2_m.group(1).strip()
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            html_parts.append(f'\n<!-- wp:heading {{"level":2}} -->\n<h2 class="wp-block-heading">{text}</h2>\n<!-- /wp:heading -->\n')
            i += 1
            continue

        h3_m = re.match(r'^###\s+(.+)', line)
        if h3_m:
            text = h3_m.group(1).strip()
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            html_parts.append(f'\n<!-- wp:heading {{"level":3}} -->\n<h3 class="wp-block-heading">{text}</h3>\n<!-- /wp:heading -->\n')
            i += 1
            continue

        if line.strip().startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
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

        if not line.strip():
            i += 1
            continue

        text = _inline_md(line.strip())
        if text:
            html_parts.append(f'\n<!-- wp:paragraph -->\n<p>{text}</p>\n<!-- /wp:paragraph -->\n')
        i += 1

    html = '\n'.join(html_parts)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html, fix_notes


def main():
    start_time = datetime.now()
    log("=" * 60)
    log(f"[baremi542] 직장인국비지원 이미지+발행 시작")
    log(f"시작시각: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    review_notes = []

    # ── 1. raw 파일 읽기 ──
    if not RAW_FILE.exists():
        log(f"❌ raw 파일 없음: {RAW_FILE}")
        return
    raw = RAW_FILE.read_text(encoding="utf-8")
    log(f"[1단계] raw 파일 로드 완료 ({len(raw)}자)")

    # ── 2. 파싱 ──
    log("[2단계] 파싱 시작")
    parsed = parse_raw(raw)
    if not parsed:
        log("❌ 파싱 실패")
        return

    title = parsed["title"]
    body = parsed["body"]
    tags = parsed["tags"]
    images_info = parsed["images"]

    # 검수: 내부 마커 제거
    for marker in ["[검증 필요]", "[출처 필요]", "[TODO]"]:
        if marker in body:
            body = body.replace(marker, "")
            review_notes.append(f"내부 마커 '{marker}' 제거")

    # 글자수 확인
    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
    char_count = len(re.sub(r"\s+", "", plain))
    log(f"[검수] 글자수: {char_count}자")
    if char_count < 1700:
        log(f"⚠ 글자수 부족 ({char_count}자 < 1700자)")
        review_notes.append(f"글자수: {char_count}자")

    # ── 3. 이미지 생성 ──
    image_paths = generate_images_gemini(images_info)
    if len(image_paths) < 3:
        review_notes.append(f"이미지 {len(image_paths)}장만 생성됨")
        log(f"⚠ 이미지 {len(image_paths)}장 (3장 필요)")

    # ── 4. 미디어 업로드 ──
    log("[4단계] WP 미디어 업로드")
    uploaded_ids = {}
    for idx, img_path in image_paths.items():
        img_info = next((img for img in images_info if img["index"] == idx), None)
        alt_text = img_info["alt"] if img_info else f"{KEYWORD} 이미지 {idx}"
        filename = Path(img_path).name
        log(f"  이미지 {idx} 업로드: {filename}")
        media_id = wp_upload_media(img_path, filename, alt_text)
        if media_id:
            uploaded_ids[idx] = media_id
            log(f"  ✅ media_id={media_id}")
        else:
            log(f"  ⚠ 이미지 {idx} 업로드 실패")
            review_notes.append(f"이미지 {idx} 업로드 실패")

    # ── 5. HTML 변환 ──
    log("[5단계] HTML 변환")
    html_content, conv_notes = md_to_html(body, image_paths, images_info)
    review_notes.extend(conv_notes)

    # 이미지 플레이스홀더 → 실제 img 태그
    for idx, media_id in uploaded_ids.items():
        img_info = next((img for img in images_info if img["index"] == idx), None)
        alt_text = img_info["alt"] if img_info else f"{KEYWORD} 이미지 {idx}"
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
                log(f"  이미지 {idx} HTML 교체 완료: {img_url}")
        except Exception as e:
            log(f"  이미지 {idx} URL 조회 실패: {e}")
            html_content = html_content.replace(f"__IMG_PLACEHOLDER_{idx}__", "")

    html_content = re.sub(r'__IMG_PLACEHOLDER_\d+__\n?', '', html_content)

    # ── 6. 카테고리/태그 ──
    log("[6단계] 카테고리/태그")
    cat_id = get_category_id("정부지원금")
    log(f"  카테고리 ID: {cat_id}")
    tag_ids = []
    for tag in tags[:10]:
        tid = get_or_create_tag_id(tag)
        if tid:
            tag_ids.append(tid)
    log(f"  태그 {len(tag_ids)}개")

    # ── 7. 발행 ──
    log("[7단계] WordPress 발행")
    post_data = {
        "title": title,
        "content": html_content,
        "status": "publish",
        "categories": [cat_id] if cat_id else [],
        "tags": tag_ids,
    }
    if 1 in uploaded_ids:
        post_data["featured_media"] = uploaded_ids[1]

    try:
        result = wp_post("posts", post_data)
        post_id = result.get("id")
        post_url = result.get("link", "")
        log(f"✅ 발행 완료! ID={post_id}")
        log(f"   URL: {post_url}")
    except urllib.error.HTTPError as e:
        reason = e.read().decode(errors="replace")
        log(f"❌ HTTP 오류 {e.code}: {reason[:500]}")
        subprocess.run(
            ["python3", "tg_send.py",
             f"⚠️ 오류 발생\n작업: baremi542 직장인국비지원 발행\n오류: HTTP {e.code} {reason[:200]}\n조치: 확인 필요"],
            cwd=str(BASE_DIR), timeout=30
        )
        return
    except Exception as e:
        log(f"❌ 발행 오류: {e}")
        import traceback; traceback.print_exc()
        subprocess.run(
            ["python3", "tg_send.py",
             f"⚠️ 오류 발생\n작업: baremi542 직장인국비지원 발행\n오류: {e}\n조치: 확인 필요"],
            cwd=str(BASE_DIR), timeout=30
        )
        return

    # ── 8. 텔레그램 ──
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
    try:
        subprocess.run(["python3", "tg_send.py", tg_msg], cwd=str(BASE_DIR), timeout=30)
        log("텔레그램 전송 완료")
    except Exception as e:
        log(f"텔레그램 전송 오류: {e}")

    log("\n" + "=" * 60)
    log("✅ 모든 작업 완료")
    log("=" * 60)


if __name__ == "__main__":
    main()
