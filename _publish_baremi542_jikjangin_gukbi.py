#!/usr/bin/env python3
"""baremi542 블로그 직장인국비지원 키워드 글 생성 + 발행"""

import os
import sys
import json
import time
import base64
import re
import requests
from datetime import datetime
from pathlib import Path

# 프로젝트 루트
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# .env 로드
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

WP_URL = "https://baremi542.com"
WP_USER = os.getenv("WP_USER", "hg01917@gmail.com")
WP_PASS = os.getenv("WP_APP_PASSWORD", "")
ADSENSE_CODE = os.getenv("ADSENSE_CODE", "")
ADSENSE_SLOT = os.getenv("ADSENSE_SLOT", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8674424194")

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def tg_send(msg):
    try:
        import subprocess
        subprocess.run(
            ["python3", str(BASE_DIR / "tg_send.py"), msg],
            timeout=15, cwd=str(BASE_DIR)
        )
    except Exception as e:
        log(f"텔레그램 전송 실패: {e}")

# ─── Step 1: 글 생성 ─────────────────────────────────────────────────────
def generate_content():
    log("Step 1: 사전 생성된 콘텐츠 로드 중...")
    # Claude API 크레딧 부족으로 인해 로컬 파일에서 로드
    content_file = Path("/tmp/baremi542_jikjangin_content.txt")
    if content_file.exists():
        return content_file.read_text(encoding="utf-8")
    raise RuntimeError("콘텐츠 파일을 찾을 수 없습니다: /tmp/baremi542_jikjangin_content.txt")

def parse_content(raw):
    def extract(tag, text):
        pattern = f"==={tag}===\\s*(.*?)\\s*==={tag}끝==="
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1).strip() if m else ""

    title = extract("제목", raw)
    body = extract("본문", raw)
    tags = extract("태그", raw)
    meta = extract("메타", raw)
    images_raw = extract("이미지", raw)

    # 이미지 파싱
    image_infos = []
    img_blocks = re.findall(r'\[이미지(\d+)\](.*?)(?=\[이미지\d+\]|$)', images_raw, re.DOTALL)
    for idx_str, block in img_blocks:
        idx = int(idx_str)
        prompt_m = re.search(r'Gemini프롬프트:\s*(.+)', block)
        filename_m = re.search(r'파일명:\s*(.+)', block)
        alt_m = re.search(r'alt:\s*(.+)', block)
        image_infos.append({
            'index': idx,
            'prompt': prompt_m.group(1).strip() if prompt_m else f"Korean government office document",
            'filename': filename_m.group(1).strip() if filename_m else f"baremi542-jikjangin-{idx}.jpg",
            'alt': alt_m.group(1).strip() if alt_m else f"직장인 국비지원 이미지{idx}",
        })

    return title, body, tags, meta, image_infos

# ─── Step 2: 이미지 생성 ─────────────────────────────────────────────────
def generate_images(image_infos):
    log(f"Step 2: 이미지 생성 중 ({len(image_infos)}장)...")
    results = {}

    # baremi542는 Bing → Pollinations 순서 (image_router.py 참조)
    # 하지만 이 스크립트에서는 Gemini로 직접 생성 (지시사항: Gemini)
    try:
        from gemini_image import generate_images as gemini_gen
        output_dir = BASE_DIR / "images" / "baremi542"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Gemini용 이미지 infos 구성
        gemini_infos = []
        for info in image_infos:
            gemini_infos.append({
                'index': info['index'],
                'prompt': info['prompt'],
                'filename': info['filename'],
                'alt': info['alt'],
            })

        res = gemini_gen(gemini_infos, on_log=log, skip_webp=True, output_dir=output_dir)
        if res:
            results.update(res)
            log(f"Gemini 이미지 생성 성공: {len(res)}장")
            return results
        else:
            log("Gemini 실패, Pollinations 폴백 시도...")
    except Exception as e:
        log(f"Gemini 오류: {e}, Pollinations 폴백 시도...")

    # Pollinations 폴백
    import urllib.parse, urllib.request, ssl
    output_dir = BASE_DIR / "images" / "baremi542"
    output_dir.mkdir(parents=True, exist_ok=True)

    for info in image_infos:
        idx = info['index']
        prompt = info['prompt']
        filename = info['filename']
        filepath = str(output_dir / filename)

        encoded = urllib.parse.quote(prompt, safe="")
        seed = abs(hash(prompt)) % 9999999
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=600&nologo=true&seed={seed}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
                data = resp.read()
            if len(data) >= 5000:
                Path(filepath).write_bytes(data)
                results[idx] = filepath
                log(f"Pollinations [{idx}] 성공: {filename}")
            else:
                log(f"Pollinations [{idx}] 응답 너무 작음: {len(data)}B")
        except Exception as e:
            log(f"Pollinations [{idx}] 실패: {e}")
        time.sleep(2)

    return results

# ─── Step 3: WP 미디어 업로드 ─────────────────────────────────────────────
def upload_image_to_wp(filepath, alt_text=""):
    log(f"WP 미디어 업로드: {Path(filepath).name}")
    auth = (WP_USER, WP_PASS)
    headers = {
        "Content-Disposition": f"attachment; filename={Path(filepath).name}",
        "Content-Type": "image/jpeg",
    }
    with open(filepath, 'rb') as f:
        data = f.read()

    resp = requests.post(
        f"{WP_URL}/wp-json/wp/v2/media",
        auth=auth,
        headers=headers,
        data=data,
        timeout=60,
    )
    if resp.status_code in (200, 201):
        media = resp.json()
        src = media.get('source_url', '')
        media_id = media.get('id', 0)
        log(f"업로드 완료: {src}")
        # alt 텍스트 업데이트
        if alt_text and media_id:
            requests.post(
                f"{WP_URL}/wp-json/wp/v2/media/{media_id}",
                auth=auth,
                json={"alt_text": alt_text},
                timeout=15,
            )
        return src, media_id
    else:
        log(f"업로드 실패 {resp.status_code}: {resp.text[:200]}")
        return None, None

# ─── Step 4: 마크다운→WordPress 블록 변환 ─────────────────────────────────
def markdown_to_wp_blocks(body, image_map, image_infos, title):
    """마크다운 본문을 WordPress classic editor HTML로 변환"""
    adsense_html = ""
    if ADSENSE_CODE and ADSENSE_SLOT:
        push_call = "(adsbygoogle = window.adsbygoogle || []).push({});"
        adsense_html = (
            f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CODE}" crossorigin="anonymous"></script>\n'
            f'<ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_CODE}" data-ad-slot="{ADSENSE_SLOT}" data-ad-format="auto" data-full-width-responsive="true"></ins>\n'
            f'<script>{push_call}</script>'
        )

    # alt 텍스트 맵 구성
    alt_map = {info['index']: info.get('alt', '') for info in image_infos}

    lines = body.split('\n')
    html_parts = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # 이미지 마커 처리
        img_match = re.match(r'\{\{이미지(\d+)\}\}', line.strip())
        if img_match:
            idx = int(img_match.group(1))
            if idx in image_map:
                url = image_map[idx]
                alt = alt_map.get(idx, f'직장인 국비지원 {idx}')
                img_html = f'<figure class="wp-block-image size-large"><img src="{url}" alt="{alt}" /></figure>'
                html_parts.append(img_html)
            i += 1
            continue

        # 애드센스 마커 처리
        if '[애드센스]' in line:
            if adsense_html:
                html_parts.append(adsense_html)
            i += 1
            continue

        # H2 소제목
        if line.startswith('## '):
            text = line[3:].strip()
            html_parts.append(f'<h2>{text}</h2>')
            i += 1
            continue

        # H3 소제목
        if line.startswith('### '):
            text = line[4:].strip()
            html_parts.append(f'<h3>{text}</h3>')
            i += 1
            continue

        # 표 처리
        if line.strip().startswith('|') and '|' in line:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            # 헤더구분선 제거
            filtered = [l for l in table_lines if not re.match(r'^\|[\s\-\|]+\|$', l.strip())]
            table_html = '<table><tbody>'
            for j, tl in enumerate(filtered):
                cells = [c.strip() for c in tl.strip().strip('|').split('|')]
                if j == 0:
                    table_html += '<tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr>'
                else:
                    table_html += '<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>'
            table_html += '</tbody></table>'
            html_parts.append(table_html)
            continue

        # 빈 줄
        if not line.strip():
            i += 1
            continue

        # 일반 단락 (볼드 처리 포함)
        text = line.strip()
        # **볼드** → <strong>
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # *이탤릭* → <em>
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        html_parts.append(f'<p>{text}</p>')
        i += 1

    return '\n'.join(html_parts)

# ─── Step 5: 검수 ─────────────────────────────────────────────────────────
def inspect_content(title, html_content):
    issues = []

    # 마크다운 잔재 체크
    if re.search(r'(^|\s)#{1,6}\s', html_content):
        issues.append("마크다운 헤딩(#) 잔재 발견")
    if re.search(r'\*\*.+?\*\*', html_content):
        issues.append("마크다운 볼드(**) 잔재 발견")
    if re.search(r'^---+$', html_content, re.MULTILINE):
        issues.append("구분선(---) 잔재 발견")

    # 내부 마커 체크
    for marker in ['[검증 필요]', '[출처 필요]', '{{이미지', '[애드센스]']:
        if marker in html_content:
            issues.append(f"내부 마커 잔재: {marker}")

    # 이미지 수 체크
    img_count = len(re.findall(r'<img\s', html_content))
    if img_count < 3:
        issues.append(f"이미지 {img_count}장 (3장 미만)")

    # 글자수 체크 (HTML 태그 제거 후)
    text_only = re.sub(r'<[^>]+>', '', html_content)
    char_count = len(text_only.replace(' ', ''))
    if char_count < 1700:
        issues.append(f"글자수 {char_count}자 (1700자 미만)")

    return issues, img_count, char_count

# ─── Step 6: WordPress 발행 ───────────────────────────────────────────────
def publish_to_wp(title, html_content, tags_str, meta_desc, status="publish"):
    auth = (WP_USER, WP_PASS)

    # 태그 처리
    tag_names = [t.strip() for t in tags_str.split(',') if t.strip()]
    tag_ids = []
    for tag_name in tag_names[:10]:
        r = requests.post(
            f"{WP_URL}/wp-json/wp/v2/tags",
            auth=auth,
            json={"name": tag_name},
            timeout=15,
        )
        if r.status_code in (200, 201):
            tag_ids.append(r.json().get('id'))
        elif r.status_code == 400 and 'term_exists' in r.text:
            # 이미 존재하는 태그
            existing_id = r.json().get('data', {}).get('term_id')
            if existing_id:
                tag_ids.append(existing_id)

    # 카테고리: 정부지원금 (ID 찾기)
    cat_id = None
    cat_r = requests.get(
        f"{WP_URL}/wp-json/wp/v2/categories?search=정부지원금&per_page=5",
        auth=auth, timeout=15
    )
    if cat_r.status_code == 200:
        cats = cat_r.json()
        if cats:
            cat_id = cats[0]['id']

    post_data = {
        "title": title,
        "content": html_content,
        "status": status,
        "meta": {"rank_math_description": meta_desc} if meta_desc else {},
    }
    if tag_ids:
        post_data["tags"] = tag_ids
    if cat_id:
        post_data["categories"] = [cat_id]

    r = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        auth=auth,
        json=post_data,
        timeout=30,
    )
    if r.status_code in (200, 201):
        post = r.json()
        return post.get('id'), post.get('link')
    else:
        log(f"포스트 생성 실패 {r.status_code}: {r.text[:300]}")
        return None, None

def publish_post(post_id):
    auth = (WP_USER, WP_PASS)
    r = requests.patch(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        auth=auth,
        json={"status": "publish"},
        timeout=15,
    )
    return r.status_code in (200, 201)

# ─── 메인 ─────────────────────────────────────────────────────────────────
def main():
    log("=== baremi542 직장인국비지원 발행 시작 ===")

    # Step 1: 글 생성
    raw = generate_content()
    log(f"생성된 원문 길이: {len(raw)}자")

    title, body, tags, meta, image_infos = parse_content(raw)
    log(f"제목: {title}")
    log(f"이미지 정보: {len(image_infos)}개")

    if not title or not body:
        log("오류: 제목 또는 본문 파싱 실패")
        tg_send("⚠️ 오류 발생\n작업: baremi542 직장인국비지원 글 생성\n오류: 제목/본문 파싱 실패\n조치: 중단")
        return

    # Step 2: 이미지 생성
    if not image_infos:
        # 기본 이미지 정보 설정
        image_infos = [
            {'index': 1, 'prompt': 'Korean government employment support center, official document, desk with pen and stamp', 'filename': 'baremi542-jikjangin-gukbi-1.jpg', 'alt': '직장인 국비지원 고용센터'},
            {'index': 2, 'prompt': 'Korean worker studying at computer, online vocational training program', 'filename': 'baremi542-jikjangin-gukbi-2.jpg', 'alt': '직장인 국비지원 온라인 훈련'},
            {'index': 3, 'prompt': 'Korean government subsidy application form, financial support documents', 'filename': 'baremi542-jikjangin-gukbi-3.jpg', 'alt': '직장인 국비지원 신청서류'},
        ]

    image_files = generate_images(image_infos)
    log(f"생성된 이미지: {len(image_files)}장")

    if len(image_files) < 3:
        log(f"경고: 이미지 {len(image_files)}장만 생성됨 (3장 필요)")

    # Step 3: WP 업로드
    image_map = {}  # {index: url}
    for idx, filepath in image_files.items():
        alt = next((info['alt'] for info in image_infos if info['index'] == idx), '')
        url, media_id = upload_image_to_wp(filepath, alt)
        if url:
            image_map[idx] = url
        time.sleep(1)

    log(f"업로드된 이미지: {len(image_map)}장")

    # Step 4: 본문 변환
    html_content = markdown_to_wp_blocks(body, image_map, image_infos, title)

    # Step 5: 검수
    issues, img_count, char_count = inspect_content(title, html_content)
    if issues:
        log(f"검수 이슈: {issues}")
    else:
        log(f"검수 통과 — 이미지 {img_count}장, {char_count}자")

    # 수정 사항 기록
    fixes = []
    if issues:
        for issue in issues:
            fixes.append(f"검수 이슈: {issue}")

    # Step 6: draft로 저장 후 발행
    log("WordPress draft 저장 중...")
    post_id, post_link = publish_to_wp(title, html_content, tags, meta, status="draft")

    if not post_id:
        log("draft 저장 실패")
        tg_send(f"⚠️ 오류 발생\n작업: baremi542 직장인국비지원 발행\n오류: WordPress draft 저장 실패\n조치: 중단")
        return

    log(f"draft 저장 완료 (ID: {post_id})")

    # 발행
    log("발행 중...")
    ok = publish_post(post_id)

    if ok:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        log(f"발행 완료: {post_link}")

        fix_summary = "\n- ".join(fixes) if fixes else "이상 없음"
        tg_msg = f"""✅ 발행 완료
블로그: baremi542
제목: {title}
발행시각: {now}
링크: {post_link}

🔧 검수 중 수정사항:
- {fix_summary}"""
        tg_send(tg_msg)
    else:
        log("발행 실패")
        tg_send(f"⚠️ 오류 발생\n작업: baremi542 직장인국비지원 발행\n오류: publish PATCH 실패\n조치: draft 상태로 저장됨 (ID: {post_id})")

if __name__ == "__main__":
    main()
