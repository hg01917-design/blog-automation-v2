"""
사업자정책지원금 키워드로 baremi542 WordPress 블로그에 포스팅 생성 및 발행
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
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# .env 로드
def _load_env():
    env = {}
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

ENV = _load_env()
for k, v in ENV.items():
    os.environ.setdefault(k, v)

KEYWORD = "사업자정책지원금"
BLOG_ID = "baremi542"
WP_URL = "https://baremi542.com"

# ─── 1단계: Claude API로 글 생성 ───────────────────────────
def generate_content():
    import anthropic

    client = anthropic.Anthropic(api_key=ENV.get("ANTHROPIC_API_KEY", ""))

    prompt = f"""아래 키워드로 정부지원금 정보 포스팅을 작성해주세요.
키워드: {KEYWORD}

작성 규칙:
- 3000자 이상
- 반드시 마크다운 형식 (## 소제목, **볼드**)
- H2 소제목 3개 이상 (## 소제목 형식으로)
- 구분선(---, ***, ___) 절대 사용 금지
- 구글 SEO 롱테일 키워드 집중
- 문체: 반드시 존댓말 (~습니다, ~세요, ~해요)
- 모바일 2~3문장 단락
- 경험 표현: 정보 탐색자 관점 ("찾아봤더니", "확인해봤더니" 등)
- 20대/50대/특정 조건 지원금을 "내가 받았어요" 식으로 쓰지 말 것

참고 자료 (이 수치만 사용):
2026년 스마트상점 기술보급사업: 중소벤처기업부/소상공인시장진흥공단 주관.
- 서빙 로봇, 키오스크, 경영 지원 소프트웨어 등 디지털 기술 도입 지원
- 지원 방식: 구입형, 렌탈형, 소프트웨어 구독형
- 지원 비율: 최대 70%~100% 차등 적용
- 공식 홈페이지 신청 → 서류 검토 → 서면 평가 → 최종 선정
- 불법 브로커 개입 등 부정행위 방지 유의사항 존재
- 의무 사용 기간 준수 등 사후 관리

제목 규칙:
- 메인키워드({KEYWORD})는 반드시 제목 맨 앞에 위치
- 메인키워드 뒤에 타겟 대상 + 세부 키워드 조합
- 예시: '사업자정책지원금 소상공인 디지털전환 신청방법과 지원비율 확인' 처럼 구체적으로
- 30~55자 범위

제목 금지 패턴:
- 완벽정리 / 총정리 / 완방정리
- N가지 / N종류 / N개 나열형
- 확인되지 않은 수치/날짜 단정 금지
- '알아보겠습니다', '살펴보겠습니다', '소개하겠습니다'
- '이번 포스팅에서는', '오늘은 ~에 대해'
- '도움이 되셨으면 좋겠습니다' 류 마무리

애드센스 삽입 규칙:
- 3000자 이상이므로 [애드센스] 마커 2개 삽입
- 삽입 위치: 본문 텍스트 → [애드센스] → 본문 텍스트 구조
- 이미지·버튼 바로 위 또는 아래 삽입 절대 금지
- 본문 맨 마지막 삽입 금지

이미지 마커:
- 각 H2 소제목 바로 아래에 {{이미지N}} 마커 삽입 (N은 1부터 순서대로)

출력 형식 (반드시 이 형식으로):

===제목===
(제목)
===제목끝===

===본문===
## 소제목1
{{이미지1}}
본문 내용...

[애드센스]

본문 내용 이어서...

## 소제목2
{{이미지2}}
본문 내용...

[애드센스]

본문 내용 이어서...

## 소제목3
{{이미지3}}
본문 내용...
===본문끝===

===태그===
태그1, 태그2, 태그3, 태그4, 태그5, 태그6, 태그7, 태그8, 태그9, 태그10
===태그끝===

===메타===
(80~120자 메타 디스크립션)
===메타끝===

===이미지===
[이미지1]
- Gemini프롬프트: (영어로, 구체적 장면 묘사)
- 파일명: (영문-소문자-하이픈.jpg)
- alt: (한국어)
[이미지2]
- Gemini프롬프트: (영어로)
- 파일명: (영문-소문자-하이픈.jpg)
- alt: (한국어)
[이미지3]
- Gemini프롬프트: (영어로)
- 파일명: (영문-소문자-하이픈.jpg)
- alt: (한국어)
===이미지끝===
"""

    print("[글 생성] Claude API 호출 중...")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text
    print(f"[글 생성] 완료 ({len(raw)}자)")
    return raw


# ─── 2단계: 파싱 ───────────────────────────
def parse_content(raw):
    title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
    body_m = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", raw, re.DOTALL)
    tag_m = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===", raw, re.DOTALL)
    img_m = re.search(r"===이미지===\s*\n(.*?)\n*===이미지끝===", raw, re.DOTALL)
    meta_m = re.search(r"===메타===\s*\n(.*?)\n*===메타끝===", raw, re.DOTALL)

    title = title_m.group(1).strip().split('\n')[0].strip() if title_m else KEYWORD
    body = body_m.group(1).strip() if body_m else raw
    meta = meta_m.group(1).strip() if meta_m else ""

    if tag_m:
        tag_raw = tag_m.group(1).strip()
        tags = [t.strip() for line in tag_raw.split('\n') for t in line.split(',') if t.strip()]
    else:
        tags = [KEYWORD]

    images = []
    if img_m:
        img_block = img_m.group(1)
        parts = re.split(r'\[이미지(\d+)\]', img_block)
        it = iter(parts[1:])
        for idx_str, block in zip(it, it):
            prompt = re.search(r'Gemini\s*프롬프트\s*[:：]\s*(.+)', block)
            fname = re.search(r'파일명\s*[:：]\s*(.+)', block)
            alt_m2 = re.search(r'\balt\s*[:：]\s*(.+)', block, re.IGNORECASE)
            if prompt and fname:
                images.append({
                    "index": int(idx_str),
                    "prompt": prompt.group(1).strip(),
                    "filename": fname.group(1).strip(),
                    "alt": alt_m2.group(1).strip() if alt_m2 else "",
                })

    print(f"[파싱] 제목: {title}")
    print(f"[파싱] 본문: {len(body)}자 / 태그: {len(tags)}개 / 이미지: {len(images)}개")
    return {"title": title, "body": body, "tags": tags, "images": images, "meta": meta}


# ─── 3단계: 이미지 생성 ───────────────────────────
def generate_images(images):
    """Gemini API로 이미지 생성"""
    import google.generativeai as genai

    gemini_key = ENV.get("GEMINI_API_KEY", "")
    if not gemini_key:
        print("[이미지] GEMINI_API_KEY 없음 — Pollinations 폴백 사용")
        return generate_images_pollinations(images)

    genai.configure(api_key=gemini_key)

    img_dir = ROOT / "images" / "baremi542"
    img_dir.mkdir(parents=True, exist_ok=True)

    image_paths = {}

    for img_info in images:
        idx = img_info["index"]
        prompt = img_info["prompt"]
        filename = img_info["filename"]

        out_path = img_dir / f"baremi542-사업자정책지원금-{idx}.jpg"

        try:
            print(f"[이미지{idx}] Gemini 생성 중: {prompt[:50]}...")
            from image_router import generate_images_for_blog
            result = generate_images_for_blog(
                BLOG_ID,
                [img_info],
                skip_webp=False,
                on_log=print,
                title=filename
            )
            if result.get(idx):
                image_paths[idx] = result[idx]
                print(f"[이미지{idx}] 생성 완료: {result[idx]}")
            else:
                print(f"[이미지{idx}] 생성 실패 — Pollinations 폴백")
                p = generate_single_pollinations(idx, prompt, out_path)
                if p:
                    image_paths[idx] = p
        except Exception as e:
            print(f"[이미지{idx}] 오류: {e} — Pollinations 폴백")
            p = generate_single_pollinations(idx, prompt, out_path)
            if p:
                image_paths[idx] = p

    return image_paths


def generate_images_pollinations(images):
    """Pollinations API로 이미지 생성"""
    img_dir = ROOT / "images" / "baremi542"
    img_dir.mkdir(parents=True, exist_ok=True)

    image_paths = {}
    for img_info in images:
        idx = img_info["index"]
        prompt = img_info["prompt"]
        out_path = img_dir / f"baremi542-사업자정책지원금-{idx}.jpg"
        p = generate_single_pollinations(idx, prompt, out_path)
        if p:
            image_paths[idx] = p
    return image_paths


def generate_single_pollinations(idx, prompt, out_path):
    """Pollinations.ai로 단일 이미지 생성"""
    try:
        encoded = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=768&seed={idx * 42}&nologo=true"

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        print(f"[이미지{idx}] Pollinations 다운로드 중...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            data = resp.read()

        out_path.write_bytes(data)
        print(f"[이미지{idx}] 저장: {out_path}")
        return str(out_path)
    except Exception as e:
        print(f"[이미지{idx}] Pollinations 실패: {e}")
        return None


# ─── 4단계: WordPress 미디어 업로드 ───────────────────────────
def wp_auth_header():
    user = ENV.get("WP_USER", "")
    pw = ENV.get("WP_APP_PASSWORD", "").replace(" ", "")
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return f"Basic {token}"


def upload_image_to_wp(img_path, filename, alt_text=""):
    """WordPress 미디어 라이브러리에 이미지 업로드"""
    auth = wp_auth_header()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    img_data = Path(img_path).read_bytes()

    # Content-Type 결정
    ext = Path(img_path).suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    mime = mime_map.get(ext, "image/jpeg")

    upload_url = f"{WP_URL}/wp-json/wp/v2/media"

    req = urllib.request.Request(
        upload_url,
        data=img_data,
        headers={
            "Authorization": auth,
            "Content-Type": mime,
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
        method="POST"
    )

    print(f"[업로드] {filename} → WordPress 미디어...")
    resp = urllib.request.urlopen(req, timeout=60, context=ctx)
    result = json.loads(resp.read())

    media_id = result["id"]
    media_url = result.get("source_url", "")
    print(f"[업로드] 완료: ID={media_id}, URL={media_url}")

    # alt 텍스트 업데이트
    if alt_text:
        try:
            body = json.dumps({"alt_text": alt_text}).encode()
            req2 = urllib.request.Request(
                f"{WP_URL}/wp-json/wp/v2/media/{media_id}",
                data=body,
                headers={"Authorization": auth, "Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req2, timeout=10, context=ctx)
        except Exception as e:
            print(f"[업로드] alt 업데이트 실패 (무시): {e}")

    return media_id, media_url


# ─── 5단계: 마크다운 → WordPress HTML 변환 ───────────────────────────
def md_to_wp_html(body, image_paths, image_infos, title):
    """마크다운 본문을 WordPress HTML로 변환하고 이미지 마커 교체"""

    # 이미지 정보 인덱스
    img_info_map = {info["index"]: info for info in image_infos}

    # 이미지 업로드 및 URL 수집
    image_urls = {}
    for idx, img_path in image_paths.items():
        info = img_info_map.get(idx, {})
        filename = info.get("filename", f"img{idx}.jpg")
        alt = info.get("alt", "")

        try:
            media_id, media_url = upload_image_to_wp(img_path, filename, alt)
            image_urls[idx] = {"url": media_url, "id": media_id, "alt": alt}
        except Exception as e:
            print(f"[이미지{idx}] WordPress 업로드 실패: {e}")

    # {{이미지N}} 마커를 실제 이미지 HTML로 교체
    def replace_image_marker(m):
        idx = int(m.group(1))
        if idx in image_urls:
            info = image_urls[idx]
            return f'<figure class="wp-block-image size-large"><img src="{info["url"]}" alt="{info["alt"]}" class="wp-image-{info["id"]}"/></figure>'
        return ""

    body = re.sub(r'\{\{이미지(\d+)\}\}', replace_image_marker, body)

    # [애드센스] 마커를 실제 애드센스 코드로 변환
    pub = ENV.get("ADSENSE_CODE", "")
    slot = ENV.get("ADSENSE_SLOT", "")
    if pub and slot:
        ad_html = (
            f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={pub}" crossorigin="anonymous"></script>'
            f'<ins class="adsbygoogle" style="display:block;text-align:center" data-ad-layout="in-article" data-ad-format="fluid" data-ad-client="{pub}" data-ad-slot="{slot}"></ins>'
            '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>'
        )
        body = body.replace("[애드센스]", ad_html)
    else:
        body = body.replace("[애드센스]", "")

    # 마크다운 → HTML 변환
    lines = body.split('\n')
    html_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # H2 소제목
        if line.startswith('## '):
            heading = line[3:].strip()
            html_lines.append(f'<h2>{heading}</h2>')
        # H3 소제목
        elif line.startswith('### '):
            heading = line[4:].strip()
            html_lines.append(f'<h3>{heading}</h3>')
        # 빈 줄
        elif line.strip() == '':
            html_lines.append('')
        # 이미 HTML인 경우 (figure 태그, script 태그 등)
        elif line.strip().startswith('<'):
            html_lines.append(line)
        # 일반 텍스트 단락
        else:
            # 볼드 처리
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            # 이탤릭 처리
            line = re.sub(r'\*(.+?)\*', r'<em>\1</em>', line)
            html_lines.append(f'<p>{line}</p>')

        i += 1

    html = '\n'.join(html_lines)

    # 빈 <p></p> 제거
    html = re.sub(r'<p>\s*</p>', '', html)
    # 연속 빈 줄 정리
    html = re.sub(r'\n{3,}', '\n\n', html)

    return html


# ─── 검수 체크리스트 ───────────────────────────
def review_content(title, html, image_count):
    issues = []

    # 1. 마크다운 잔재 확인
    if re.search(r'(?m)^#{1,6}\s', html):
        issues.append("마크다운 heading 잔재 발견 (## 형식)")
    if re.search(r'\*\*.+?\*\*', html):
        issues.append("마크다운 볼드(**) 잔재 발견")

    # 2. 이미지 수 확인
    img_count_in_html = len(re.findall(r'<img\s', html))
    if img_count_in_html < 3:
        issues.append(f"이미지 {img_count_in_html}장 (3장 미만)")

    # 3. 내부 마커 확인
    bad_markers = ['[검증 필요]', '[출처 필요]', '{{이미지', '[TODO]']
    for marker in bad_markers:
        if marker in html:
            issues.append(f"내부 마커 발견: {marker}")

    # 4. 글자수 확인
    plain = re.sub(r'<[^>]+>', '', html)
    char_count = len(re.sub(r'\s+', '', plain))
    if char_count < 1700:
        issues.append(f"글자수 {char_count}자 (1700자 미만)")

    # 5. 구분선 확인
    if re.search(r'(?m)^\s*[-*_]{3,}\s*$', html):
        issues.append("구분선(---) 발견")

    print(f"\n[검수] 이미지: {img_count_in_html}장 / 본문: {char_count}자")

    if issues:
        print(f"[검수] 문제 발견: {issues}")
    else:
        print("[검수] 통과 ✓")

    return issues, img_count_in_html, char_count


# ─── 6단계: WordPress 발행 ───────────────────────────
def get_category_id(slug):
    auth = wp_auth_header()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(
            f"{WP_URL}/wp-json/wp/v2/categories?per_page=50",
            headers={"Authorization": auth}
        )
        cats = json.loads(urllib.request.urlopen(req, timeout=20, context=ctx).read())
        for c in cats:
            if c.get("slug") == slug or c.get("name") == slug:
                return c["id"]
    except Exception as e:
        print(f"[카테고리] 조회 실패: {e}")
    return 1


def get_or_create_tag(tag_name):
    auth = wp_auth_header()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        encoded = urllib.parse.quote(tag_name)
        req = urllib.request.Request(
            f"{WP_URL}/wp-json/wp/v2/tags?search={encoded}",
            headers={"Authorization": auth}
        )
        res = json.loads(urllib.request.urlopen(req, timeout=10, context=ctx).read())
        if res:
            return res[0]["id"]
        # 없으면 생성
        body = json.dumps({"name": tag_name}).encode()
        req2 = urllib.request.Request(
            f"{WP_URL}/wp-json/wp/v2/tags",
            data=body,
            headers={"Authorization": auth, "Content-Type": "application/json"},
            method="POST"
        )
        created = json.loads(urllib.request.urlopen(req2, timeout=10, context=ctx).read())
        return created["id"]
    except Exception as e:
        print(f"[태그] {tag_name} 처리 실패: {e}")
        return None


def publish_to_wordpress(title, html, tags, meta):
    auth = wp_auth_header()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # 카테고리 ID
    cat_id = get_category_id("정부지원금")
    categories = [cat_id]

    # 태그 ID 목록
    tag_ids = []
    for tag in tags[:15]:
        tid = get_or_create_tag(tag)
        if tid:
            tag_ids.append(tid)
        time.sleep(0.2)

    post_body = {
        "title": title,
        "content": html,
        "status": "publish",
        "categories": categories,
        "tags": tag_ids,
    }

    if meta:
        post_body["excerpt"] = meta

    body_bytes = json.dumps(post_body, ensure_ascii=False).encode()
    req = urllib.request.Request(
        f"{WP_URL}/wp-json/wp/v2/posts",
        data=body_bytes,
        headers={"Authorization": auth, "Content-Type": "application/json"},
        method="POST"
    )

    print(f"\n[발행] WordPress 발행 중...")
    resp = urllib.request.urlopen(req, timeout=60, context=ctx)
    result = json.loads(resp.read())

    post_id = result.get("id")
    post_url = result.get("link", "")
    print(f"[발행] 완료! ID={post_id}")
    print(f"[발행] URL: {post_url}")

    return post_id, post_url


# ─── 7단계: 텔레그램 보고 ───────────────────────────
def send_telegram(msg):
    try:
        import subprocess
        result = subprocess.run(
            ["python3", str(ROOT / "tg_send.py"), msg],
            capture_output=True, text=True, timeout=30
        )
        print(f"[텔레그램] {result.stdout.strip()}")
    except Exception as e:
        print(f"[텔레그램] 전송 실패: {e}")


# ─── 메인 실행 ───────────────────────────
def main():
    print("=" * 60)
    print(f"baremi542 포스팅 생성 시작: {KEYWORD}")
    print("=" * 60)

    fixes = []

    # 1. 글 생성
    try:
        raw = generate_content()
    except Exception as e:
        msg = f"⚠️ 오류 발생\n작업: 글 생성 (Claude API)\n오류: {e}\n조치: 중단"
        print(msg)
        send_telegram(msg)
        return

    # 2. 파싱
    parsed = parse_content(raw)
    title = parsed["title"]
    body = parsed["body"]
    tags = parsed["tags"]
    images = parsed["images"]
    meta = parsed["meta"]

    # 3. 이미지 생성
    image_paths = {}
    if images:
        try:
            image_paths = generate_images(images)
        except Exception as e:
            print(f"[이미지] 생성 오류: {e}")

    if len(image_paths) < 3:
        print(f"[이미지] {len(image_paths)}장만 생성됨, 추가 생성 시도...")
        # 부족한 이미지 추가 생성
        existing_indices = set(image_paths.keys())
        for img_info in images:
            if img_info["index"] not in existing_indices and len(image_paths) < 3:
                idx = img_info["index"]
                out_path = ROOT / "images" / "baremi542" / f"baremi542-사업자정책지원금-{idx}-retry.jpg"
                p = generate_single_pollinations(idx, img_info["prompt"], out_path)
                if p:
                    image_paths[idx] = p

    # 4. HTML 변환 + 이미지 업로드
    try:
        html = md_to_wp_html(body, image_paths, images, title)
    except Exception as e:
        msg = f"⚠️ 오류 발생\n작업: HTML 변환 / 이미지 업로드\n오류: {e}\n조치: 중단"
        print(msg)
        send_telegram(msg)
        return

    # 구분선 제거 (혹시 남아있으면)
    html = re.sub(r'(?m)^\s*[-*_]{3,}\s*$', '', html).strip()

    # 5. 검수
    issues, img_count, char_count = review_content(title, html, len(image_paths))

    for issue in issues:
        fixes.append(issue)

    # 심각한 문제가 있으면 경고만 하고 계속 진행 (이미지 부족 제외)
    if img_count < 3:
        print(f"[경고] 이미지 {img_count}장으로 발행 진행 (3장 미달)")
        fixes.append(f"이미지 {img_count}장으로 발행 (부족)")

    # 6. WordPress 발행
    try:
        post_id, post_url = publish_to_wordpress(title, html, tags, meta)
    except Exception as e:
        msg = f"⚠️ 오류 발생\n작업: WordPress 발행\n오류: {str(e)[:200]}\n조치: 중단"
        print(msg)
        send_telegram(msg)
        return

    # 7. 텔레그램 보고
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    fixes_text = "\n- ".join(fixes) if fixes else "이상 없음"
    if fixes:
        fixes_text = "- " + fixes_text

    report = f"""✅ 발행 완료
블로그: baremi542
제목: {title}
발행시각: {now}

🔧 검수 중 수정사항:
{fixes_text}

🔗 URL: {post_url}"""

    print("\n" + report)
    send_telegram(report)

    print("\n[완료] 작업 종료")


if __name__ == "__main__":
    main()
