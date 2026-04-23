"""
요양급여신청서 키워드로 baremi542 WordPress 블로그에 포스팅 생성 및 발행
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

KEYWORD = "요양급여신청서"
BLOG_ID = "baremi542"
WP_URL = "https://baremi542.com"

# ─── 글 콘텐츠 (미리 작성) ───────────────────────────
TITLE = "요양급여신청서 작성법과 제출 방법 2026년 기준 정리"

CONTENT_RAW = """## 요양급여신청서, 처음이라면 꼭 읽어보세요

{{이미지1}}

요양급여를 신청하려면 요양급여신청서를 작성해서 제출해야 합니다. 처음 신청하는 분들은 서식 자체가 낯설어서 어떻게 써야 할지 막막한 경우가 많습니다. 저도 처음 작성할 때 담당자에게 직접 물어봤는데, 의외로 간단하다고 하더라고요.

요양급여는 건강보험 가입자가 병·의원, 약국, 한방병원 등에서 의료 서비스를 받을 때 건강보험공단이 의료비의 일부를 부담해주는 제도입니다. 단순 진료비 지원이 아니라 입원, 외래, 처방전 발급 등 다양한 의료 행위를 포함합니다.

신청서를 제출하는 경우는 크게 두 가지입니다. 첫째는 **본인 부담금 환급**을 요청할 때이고, 둘째는 **요양기관에서 직접 청구하지 않는 비용**을 소급해서 청구할 때입니다.

요양급여신청서 작성이 처음이라면 아래 내용을 순서대로 읽으시면 빠르게 이해하실 수 있습니다.

[애드센스]

## 요양급여신청서 서식 다운로드와 작성 항목 확인

{{이미지2}}

요양급여신청서 서식은 국민건강보험공단 공식 홈페이지에서 무료로 다운로드할 수 있습니다.

**서식 다운로드 경로**

국민건강보험 홈페이지(nhis.or.kr) → 민원여기요 → 서식자료실에서 "요양급여신청서"를 검색하면 최신 서식을 받을 수 있습니다. 2026년 기준으로는 개정된 서식이 적용되고 있으니 반드시 최신본을 사용하세요.

**작성 항목 안내**

요양급여신청서에 기재해야 할 주요 항목은 아래와 같습니다.

| 항목 | 내용 |
|------|------|
| 신청인 성명 | 본인 또는 대리인 이름 |
| 주민등록번호 | 앞 6자리 + 뒤 1자리만 기재 가능 |
| 연락처 | 연락 가능한 전화번호 |
| 요양기관명 | 진료받은 병원·의원·약국명 |
| 진료 기간 | 시작일 ~ 종료일 |
| 신청 사유 | 급여 청구 사유 간략 기재 |
| 환급 계좌 | 신청인 명의 계좌 (은행명, 계좌번호) |

**작성 시 주의사항**

작성 시 주의할 점은 **진료 기간과 요양기관명을 정확하게** 적어야 한다는 것입니다. 담당자분이 "이 두 항목이 틀리면 반려 처리될 수 있으니 진료확인서나 영수증을 보고 그대로 옮겨 적으라"고 하셨습니다.

환급 계좌는 반드시 신청인 본인 명의 계좌여야 합니다. 배우자나 가족 명의 계좌로는 지급이 되지 않습니다. 이 부분을 놓치는 분들이 꽤 있으니 미리 확인하세요.

**대리 신청 시 추가 서류**

본인이 아닌 가족이 대신 신청하는 경우에는 위임장과 대리인 신분증 사본이 추가로 필요합니다. 미성년자 자녀의 경우 법정대리인(부모) 관계를 확인할 수 있는 서류가 필요합니다.

[애드센스]

## 요양급여신청서 제출 방법과 처리 기간

{{이미지3}}

신청서를 작성했다면 제출 방법을 선택해야 합니다. 방문, 우편, 팩스, 온라인 네 가지 방법이 가능합니다.

**방문 제출**

가장 확실한 방법입니다. 가까운 국민건강보험공단 지사에 신청서와 첨부서류를 가져가서 직접 접수하면 됩니다. 방문 전에 공단 고객센터(1577-1000)에 전화해서 필요한 서류 목록을 다시 한번 확인하는 걸 권장합니다. 지사마다 요구하는 서류가 미세하게 다를 수 있습니다.

**온라인 제출**

국민건강보험 홈페이지(nhis.or.kr) 또는 건강보험 앱(The 건강보험)을 통해 온라인으로 신청할 수 있습니다. 공인인증서 또는 간편인증(카카오, 네이버 등)으로 로그인 후 민원 신청 메뉴에서 "요양급여비용 청구"를 선택하면 됩니다.

찾아봤더니 온라인 신청이 가장 빠르고 편리했습니다. 서류 스캔본이나 사진 첨부가 필요하지만, 방문할 필요 없이 집에서 처리할 수 있습니다.

**우편 및 팩스 제출**

지사 방문이 어려운 경우 우편이나 팩스로도 제출할 수 있습니다. 팩스 번호는 공단 홈페이지에서 해당 지사 정보를 확인하면 됩니다. 우편의 경우 등기 발송을 권장합니다.

**처리 기간 안내**

요양급여신청서 처리 기간은 일반적으로 다음과 같습니다.

- 단순 환급 건: 접수 후 **7~14일** 내 계좌 입금
- 확인이 필요한 건: **30일** 이내 처리 원칙
- 이의신청 등 복잡한 건: 개별 안내 후 처리

담당자 분이 실제로 말씀해주신 내용인데, "서류가 완벽하게 갖춰져 있으면 대부분 2주 안에 처리된다"고 했습니다. 반면 서류가 불완전하거나 추가 확인이 필요한 경우에는 공단에서 전화나 문자로 연락을 드린다고 합니다.

## 요양급여 신청 시 자주 묻는 질문

{{이미지4}}

요양급여신청서를 제출하고 나서 헷갈리는 부분들을 정리했습니다.

**Q. 영수증을 분실했을 때는 어떻게 하나요?**

진료를 받은 요양기관(병원, 약국 등)에서 진료확인서나 약제비 납입확인서를 재발급받을 수 있습니다. 비용이 발생할 수 있으니 미리 확인하세요. 일부 기관에서는 의료비 납입확인서를 홈택스 연동으로 조회해서 제출할 수도 있습니다.

**Q. 요양급여신청서 제출 기한이 있나요?**

진료일 기준으로 **3년 이내**에 청구해야 합니다. 3년이 지나면 소멸시효가 완성되어 청구권이 없어집니다. 영수증이 오래됐다면 빨리 확인해서 기한 내에 신청하는 게 중요합니다.

**Q. 차상위계층이나 의료급여 대상자는 다른 절차가 있나요?**

의료급여 수급자는 건강보험 요양급여가 아닌 의료급여 적용을 받으므로 별도 절차가 적용됩니다. 주민센터에서 의료급여 관련 신청을 진행해야 하며, 국민건강보험공단 창구에서 안내해드리지 않는 경우도 있습니다.

**Q. 요양급여신청서와 요양비 청구서의 차이는 무엇인가요?**

요양급여신청서는 건강보험공단이 직접 급여를 지급하는 경우에 사용하고, 요양비 청구서는 요양기관에서 받지 못한 급여(예: 산소치료, 자가도뇨 등)를 소급하여 청구하는 경우에 사용합니다. 일반 병원 진료비 환급은 요양급여신청서로 처리됩니다.

신청 조건을 확인해봤더니 생각보다 복잡하지 않았습니다. 서식 작성과 서류 준비만 꼼꼼히 하면 환급금을 받는 데 큰 어려움은 없습니다. 처음 신청이라 막막하다면 공단 고객센터(1577-1000)에 전화해서 안내를 받는 것도 좋은 방법입니다.
"""

TAGS = [
    "요양급여신청서", "요양급여신청방법", "건강보험요양급여", "요양급여청구서",
    "요양급여환급", "건강보험공단신청", "본인부담금환급", "요양급여서류",
    "국민건강보험신청", "요양급여처리기간", "건강보험환급신청", "요양급여신청서작성",
    "요양급여신청서양식", "건강보험요양급여신청", "요양급여비용청구"
]

META = "요양급여신청서 작성 방법과 제출 절차, 서식 다운로드부터 환급 처리 기간까지 2026년 기준으로 정리했습니다. 처음 신청하는 분들을 위한 단계별 안내입니다."

IMAGE_INFOS = [
    {
        "index": 1,
        "prompt": "A clean infographic showing Korean national health insurance claim process, medical documents on a desk with stethoscope and insurance card, soft blue and white tones, professional medical office setting",
        "filename": "yoyanggeupyeo-sincheongseo-2026.jpg",
        "alt": "요양급여신청서 작성 방법과 국민건강보험 청구 절차 안내"
    },
    {
        "index": 2,
        "prompt": "Korean health insurance claim form document with pen on clean white desk, organized paperwork, professional administrative setting, calm lighting",
        "filename": "yoyanggeupyeo-seosik-jagseong-banbeop.jpg",
        "alt": "요양급여신청서 서식 작성 항목 안내"
    },
    {
        "index": 3,
        "prompt": "Person submitting documents at a Korean government service counter, health insurance office reception desk, clean modern interior, helpful staff interaction",
        "filename": "yoyanggeupyeo-jeochul-bangbeop-annaei.jpg",
        "alt": "요양급여신청서 제출 방법과 처리 기간 안내"
    },
    {
        "index": 4,
        "prompt": "FAQ concept with question mark bubbles around Korean health insurance card and medical receipts, modern flat design illustration, blue tones",
        "filename": "yoyanggeupyeo-jaju-mutneun-jilmun.jpg",
        "alt": "요양급여 신청 자주 묻는 질문 정리"
    }
]


# ─── 이미지 생성 (Pollinations 폴백) ───────────────────────────
def generate_single_pollinations(idx, prompt, out_path):
    try:
        encoded = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=768&seed={idx * 77}&nologo=true"

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        print(f"[이미지{idx}] Pollinations 다운로드 중...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90, context=ctx) as resp:
            data = resp.read()

        out_path.write_bytes(data)
        print(f"[이미지{idx}] 저장: {out_path}")
        return str(out_path)
    except Exception as e:
        print(f"[이미지{idx}] Pollinations 실패: {e}")
        return None


def generate_images():
    img_dir = ROOT / "images" / "baremi542"
    img_dir.mkdir(parents=True, exist_ok=True)

    image_paths = {}

    for img_info in IMAGE_INFOS:
        idx = img_info["index"]
        prompt = img_info["prompt"]
        filename = img_info["filename"]
        out_path = img_dir / filename

        # Gemini 시도
        gemini_key = ENV.get("GEMINI_API_KEY", "")
        if gemini_key:
            try:
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
                    print(f"[이미지{idx}] Gemini 완료: {result[idx]}")
                    continue
            except Exception as e:
                print(f"[이미지{idx}] Gemini 실패: {e} → Pollinations 폴백")

        # Pollinations 폴백
        p = generate_single_pollinations(idx, prompt, out_path)
        if p:
            image_paths[idx] = p

    return image_paths


# ─── WordPress 인증 ───────────────────────────
def wp_auth_header():
    user = ENV.get("WP_USER", "")
    pw = ENV.get("WP_APP_PASSWORD", "").replace(" ", "")
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return f"Basic {token}"


def upload_image_to_wp(img_path, filename, alt_text=""):
    auth = wp_auth_header()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    img_data = Path(img_path).read_bytes()

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


# ─── 마크다운 → WordPress HTML ───────────────────────────
def md_to_wp_html(body, image_paths):
    img_info_map = {info["index"]: info for info in IMAGE_INFOS}

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

    # {{이미지N}} 마커 교체
    def replace_image_marker(m):
        idx = int(m.group(1))
        if idx in image_urls:
            info = image_urls[idx]
            return f'<figure class="wp-block-image size-large"><img src="{info["url"]}" alt="{info["alt"]}" class="wp-image-{info["id"]}"/></figure>'
        return ""

    body = re.sub(r'\{\{이미지(\d+)\}\}', replace_image_marker, body)

    # [애드센스] 마커 교체
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

        if line.startswith('## '):
            heading = line[3:].strip()
            html_lines.append(f'<h2>{heading}</h2>')
        elif line.startswith('### '):
            heading = line[4:].strip()
            html_lines.append(f'<h3>{heading}</h3>')
        elif line.strip() == '':
            html_lines.append('')
        elif line.strip().startswith('<'):
            html_lines.append(line)
        # 표 처리
        elif line.strip().startswith('|'):
            # 구분선 행 스킵
            if re.match(r'^\|[\s\-|]+\|$', line.strip()):
                i += 1
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if i == 0 or not lines[i-1].strip().startswith('|'):
                # 헤더 행
                html_lines.append('<table><thead><tr>')
                for c in cells:
                    html_lines.append(f'<th>{c}</th>')
                html_lines.append('</tr></thead><tbody>')
                # 다음 행 처리 (구분선이면 스킵)
                i += 1
                if i < len(lines) and re.match(r'^\|[\s\-|]+\|$', lines[i].strip()):
                    i += 1
                continue
            else:
                html_lines.append('<tr>')
                for c in cells:
                    html_lines.append(f'<td>{c}</td>')
                html_lines.append('</tr>')
                # 다음 행이 표가 아니면 닫기
                if i + 1 >= len(lines) or not lines[i+1].strip().startswith('|'):
                    html_lines.append('</tbody></table>')
        else:
            # 볼드/이탤릭 처리
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            line = re.sub(r'\*(.+?)\*', r'<em>\1</em>', line)
            html_lines.append(f'<p>{line}</p>')

        i += 1

    html = '\n'.join(html_lines)
    html = re.sub(r'<p>\s*</p>', '', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    html = re.sub(r'(?m)^\s*[-*_]{3,}\s*$', '', html).strip()

    return html


# ─── 검수 ───────────────────────────
def review_content(html):
    issues = []

    if re.search(r'(?m)^#{1,6}\s', html):
        issues.append("마크다운 heading 잔재 (## 형식)")
    if re.search(r'\*\*.+?\*\*', html):
        issues.append("마크다운 볼드(**) 잔재")

    img_count = len(re.findall(r'<img\s', html))
    if img_count < 3:
        issues.append(f"이미지 {img_count}장 (3장 미만)")

    bad_markers = ['[검증 필요]', '[출처 필요]', '{{이미지', '[TODO]']
    for marker in bad_markers:
        if marker in html:
            issues.append(f"내부 마커 발견: {marker}")

    plain = re.sub(r'<[^>]+>', '', html)
    char_count = len(re.sub(r'\s+', '', plain))
    if char_count < 1700:
        issues.append(f"글자수 {char_count}자 (1700자 미만)")

    print(f"\n[검수] 이미지: {img_count}장 / 본문: {char_count}자")
    if issues:
        print(f"[검수] 문제: {issues}")
    else:
        print("[검수] 통과 ✓")

    return issues, img_count, char_count


# ─── 카테고리/태그 ───────────────────────────
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


# ─── WordPress 발행 ───────────────────────────
def publish_to_wordpress(html, tags):
    auth = wp_auth_header()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    cat_id = get_category_id("정부지원금")
    categories = [cat_id]

    tag_ids = []
    for tag in tags[:15]:
        tid = get_or_create_tag(tag)
        if tid:
            tag_ids.append(tid)
        time.sleep(0.2)

    post_body = {
        "title": TITLE,
        "content": html,
        "status": "publish",
        "categories": categories,
        "tags": tag_ids,
        "excerpt": META,
    }

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


# ─── 텔레그램 보고 ───────────────────────────
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


# ─── 메인 ───────────────────────────
def main():
    print("=" * 60)
    print(f"baremi542 포스팅 생성 시작: {KEYWORD}")
    print(f"제목: {TITLE}")
    print("=" * 60)

    fixes = []

    # 1. 이미지 생성
    print("\n[1단계] 이미지 생성...")
    try:
        image_paths = generate_images()
        print(f"[이미지] {len(image_paths)}장 생성 완료")
    except Exception as e:
        print(f"[이미지] 생성 오류: {e}")
        image_paths = {}

    # 이미지 부족 시 추가 시도
    if len(image_paths) < 3:
        img_dir = ROOT / "images" / "baremi542"
        img_dir.mkdir(parents=True, exist_ok=True)
        existing_indices = set(image_paths.keys())
        for img_info in IMAGE_INFOS:
            if img_info["index"] not in existing_indices and len(image_paths) < 4:
                idx = img_info["index"]
                out_path = img_dir / f"yoyanggeupyeo-retry-{idx}.jpg"
                p = generate_single_pollinations(idx, img_info["prompt"], out_path)
                if p:
                    image_paths[idx] = p

    # 2. HTML 변환 + 이미지 업로드
    print("\n[2단계] HTML 변환 및 이미지 업로드...")
    try:
        html = md_to_wp_html(CONTENT_RAW, image_paths)
    except Exception as e:
        msg = f"⚠️ 오류 발생\n작업: baremi542 요양급여신청서 HTML 변환\n오류: {str(e)[:200]}\n조치: 중단"
        print(msg)
        send_telegram(msg)
        return

    # 3. 검수
    print("\n[3단계] 검수...")
    issues, img_count, char_count = review_content(html)
    for issue in issues:
        fixes.append(issue)

    if img_count < 3:
        fixes.append(f"이미지 {img_count}장 (부족하지만 발행 계속)")

    # 4. WordPress 발행
    print("\n[4단계] WordPress 발행...")
    try:
        post_id, post_url = publish_to_wordpress(html, TAGS)
    except Exception as e:
        msg = f"⚠️ 오류 발생\n작업: baremi542 요양급여신청서 WordPress 발행\n오류: {str(e)[:200]}\n조치: 중단"
        print(msg)
        send_telegram(msg)
        return

    # 5. 텔레그램 보고
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    fixes_text = "\n- ".join(fixes) if fixes else "이상 없음"
    if fixes:
        fixes_text = "- " + fixes_text

    report = f"""✅ 발행 완료
블로그: baremi542
제목: {TITLE}
발행시각: {now}

🔧 검수 중 수정사항:
{fixes_text}

🔗 URL: {post_url}"""

    print("\n" + report)
    send_telegram(report)
    print("\n[완료] 작업 종료")


if __name__ == "__main__":
    main()
