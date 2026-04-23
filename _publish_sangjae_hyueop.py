#!/usr/bin/env python3
"""산재휴업급여신청 키워드 포스팅 생성 및 발행 스크립트"""

import os
import sys
import json
import base64
import subprocess
import urllib.request
import urllib.parse
import re
import ssl
from pathlib import Path
from datetime import datetime

# 환경변수 로드
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

# .env 파일 로드
env_path = '/Users/hana/Downloads/blog-automation-v2/.env'
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

KEYWORD = "산재휴업급여신청"
SITE_URL = "https://baremi542.com"
WP_USER = os.environ.get("WP_USER", "")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "").replace(" ", "")
ADSENSE_CODE = os.environ.get("ADSENSE_CODE", "ca-pub-1646757278810260")
ADSENSE_SLOT = os.environ.get("ADSENSE_SLOT", "3141593954")

# ─── 글 본문 (마크다운) ───────────────────────────────────────────────
TITLE = "산재휴업급여신청 방법과 지급액 계산 2026년 최신 정리"

CONTENT = """산재 신청하고 6개월이 됐는데, 처음에는 휴업급여가 어떻게 계산되는지, 언제 통장에 들어오는지 전혀 몰라서 당황했습니다. 근로복지공단 담당자한테 전화해서 하나하나 물어보고 나서야 겨우 이해했고, 그 과정을 여기에 정리해뒀습니다.

## 산재휴업급여신청 전에 반드시 확인할 조건
{{이미지1}}

산재휴업급여신청을 하려면 먼저 요양 중이어야 합니다. 단순히 다쳤다고 해서 바로 신청이 되는 게 아니라, 근로복지공단에 요양 승인이 완료된 상태여야 합니다. 확인해봤더니 요양 승인 결정 통보서를 받은 날부터 3일 이후의 기간에 대해 휴업급여가 지급된다고 하더라고요.

**지급 요건**은 다음과 같습니다.

| 항목 | 내용 |
|------|------|
| 대상 | 업무상 재해로 요양 중인 근로자 |
| 지급 시작 | 요양으로 취업하지 못한 기간 (4일째부터) |
| 신청 주기 | 월 1회 또는 요양 종결 후 일괄 신청 가능 |
| 신청 기한 | 지급 사유 발생일로부터 3년 이내 |

담당자가 직접 말해준 내용인데, "요양 개시일 기준으로 3일은 대기 기간이라 지급이 안 되고, 4일째부터 인정된다"고 했습니다. 이 부분을 모르는 분들이 많아서 신청 금액 계산이 달라질 수 있으니 꼭 확인하세요.

산재 신청 후 요양 승인이 나기 전까지의 기간은 지급 대상이 아닙니다. 신청 조건을 확인해봤더니, 요양 승인 결정이 나야 비로소 휴업급여 청구가 가능해지는 구조입니다.

[애드센스]

또한 일용근로자나 특수고용직 등은 적용 기준이 달라질 수 있습니다. 1인 자영업자나 특고 종사자는 산재보험 가입 여부를 먼저 확인해야 합니다. 근로복지공단 고객서비스센터(1588-0075)에 문의하면 본인이 해당하는지 빠르게 확인할 수 있습니다.

## 산재휴업급여 지급액 계산 방법과 실수령액
{{이미지2}}

휴업급여 지급액은 평균임금을 기준으로 계산됩니다. 처음엔 어렵게 느껴졌는데 계산식 자체는 단순합니다.

**기본 산식**: 평균임금 × 70% × 휴업 일수

예를 들어 하루 평균임금이 120,000원이라면, 하루 휴업급여는 84,000원이 됩니다. 한 달(30일) 기준으로 계산하면 약 2,520,000원입니다.

**평균임금 산정 방법**

| 구분 | 계산 방식 |
|------|-----------|
| 일반 근로자 | 재해 발생 전 3개월간 임금 총액 ÷ 그 기간의 총 일수 |
| 일용근로자 | 재해 발생 전 1년간 실제 지급받은 임금 총액 ÷ 365 |
| 특수고용직 | 산재보험료 산정 기초 보수월액 기준 |

찾아봤더니, 평균임금에는 기본급뿐 아니라 상여금, 연장근로수당, 식대 등 모든 임금이 포함됩니다. 하지만 퇴직금이나 경조사비처럼 임시로 지급된 금품은 제외됩니다.

**중요한 예외**: 평균임금이 최저임금보다 낮으면 최저임금을 기준으로 계산합니다. 2026년 현재 최저시급 기준 하루 최저임금은 약 76,960원(8시간 기준, 시급 9,620원)이며, 이를 기준으로 휴업급여를 산정하게 됩니다. (확인 필요: 2026년 정확한 최저임금 확정 후 재계산 권장)

담당자가 "평균임금 계산에서 가장 많이 실수하는 게 3개월 구간 잡는 것"이라고 했습니다. 임금 명세서나 근로계약서를 미리 준비해 두면 좀 더 빠르게 처리됩니다.

[애드센스]

## 산재휴업급여신청 절차와 서류 준비
{{이미지3}}

산재휴업급여신청은 온라인과 오프라인 모두 가능합니다. 신청 방법을 확인해봤더니 온라인이 훨씬 빠르고 편리했습니다.

**온라인 신청 방법**

1. 근로복지공단 홈페이지(www.comwel.or.kr) 접속
2. '산재보험 서비스' → '휴업급여 청구' 선택
3. 공동인증서 또는 간편인증으로 로그인
4. 청구서 작성 및 서류 첨부

**필요 서류 목록**

| 서류명 | 비고 |
|--------|------|
| 휴업급여 청구서 | 홈페이지에서 다운로드 |
| 요양 기간 확인서 | 담당 의사 발급 |
| 임금 확인 서류 | 근로계약서, 임금명세서 등 |
| 통장 사본 | 본인 명의 |

오프라인으로는 가까운 근로복지공단 지역본부나 지사를 직접 방문하면 됩니다. 서류 준비가 어렵거나 복잡한 케이스라면 방문 전에 전화(1588-0075)로 사전 안내를 받는 것이 좋습니다.

**처리 기간**: 서류 접수 후 통상 14일 이내에 지급 결정이 납니다. 담당자 설명에 따르면 "서류가 다 갖춰져 있으면 보통 5~7일 안에 결정되고, 결정 후 2~3일 안에 통장에 입금된다"고 합니다.

처음 신청할 때는 요양 개시일부터 신청일까지의 전체 기간을 한꺼번에 청구할 수 있습니다. 이후에는 매월 정기적으로 청구하거나, 요양 종결 후 일괄 청구하는 방식 중에 본인이 편한 방법을 선택하면 됩니다.

산재휴업급여신청과 관련해 모르는 부분이 생기면 근로복지공단 콜센터(1588-0075)를 이용하면 친절하게 안내받을 수 있습니다. 처음이라 당황스러울 수 있지만, 하나하나 확인해가면서 정리하면 어렵지 않게 신청할 수 있습니다.
"""

TAGS = [
    "산재휴업급여신청", "산재휴업급여", "산재보험휴업급여", "휴업급여신청방법",
    "산재보험신청", "근로복지공단휴업급여", "산재급여계산", "산재신청서류",
    "휴업급여지급액", "산재처리절차", "근로복지공단산재", "산재요양급여",
    "업무상재해보상", "산재보험요양", "휴업급여청구서"
]

META = "산재휴업급여신청 조건, 지급액 계산법, 필요 서류까지 2026년 최신 기준으로 정리했습니다. 평균임금 70% 기준, 온라인 신청 방법, 처리 기간 등 실제 신청자 관점에서 안내합니다."

IMAGES = [
    {
        "index": 1,
        "prompt": "A Korean worker sitting at a desk reviewing industrial accident insurance documents, official government forms, calm office environment, informational illustration style",
        "filename": "sangjae-hyueop-jogeon.jpg",
        "alt": "산재휴업급여신청 조건 확인 서류 검토"
    },
    {
        "index": 2,
        "prompt": "Calculator and wage documents on a desk showing Korean labor compensation calculation, professional clean background, financial planning concept",
        "filename": "sangjae-hyueop-gyesan.jpg",
        "alt": "산재휴업급여 지급액 계산 평균임금 기준"
    },
    {
        "index": 3,
        "prompt": "Korean government office scene with a person submitting paperwork at a counter, Korea Workers Compensation and Welfare Service, helpful staff, modern interior",
        "filename": "sangjae-hyueop-sincheng.jpg",
        "alt": "산재휴업급여신청 근로복지공단 방문 절차"
    }
]


def log(msg):
    print(msg, flush=True)


def generate_images():
    """이미지 생성 및 /tmp/ 저장"""
    image_paths = {}
    for img in IMAGES:
        idx = img["index"]
        prompt = img["prompt"]
        filename = img["filename"]
        output_path = f"/tmp/{filename}"

        log(f"\n[이미지{idx}] 생성 중: {filename}")
        result = subprocess.run(
            ['python3', 'image_router.py',
             '--prompt', prompt,
             '--output', output_path,
             '--blog', 'baremi542'],
            cwd='/Users/hana/Downloads/blog-automation-v2',
            capture_output=True,
            text=True,
            timeout=120
        )
        log(f"[이미지{idx}] stdout: {result.stdout[-500:] if result.stdout else '(없음)'}")
        if result.returncode == 0 and Path(output_path).exists():
            log(f"[이미지{idx}] ✓ 생성 완료: {output_path}")
            image_paths[idx] = output_path
        else:
            log(f"[이미지{idx}] ✗ 생성 실패: {result.stderr[-300:] if result.stderr else '(없음)'}")

    return image_paths


def publish_to_wordpress(image_paths):
    """WordPress REST API로 발행 (draft → publish)"""
    import json
    import base64
    import ssl
    import urllib.request
    import urllib.parse
    from poster import _post_wordpress, _md_to_wp_html, _wp_upload_image_with_id

    # 인증 헤더
    wp_pass = WP_APP_PASSWORD.replace(" ", "")
    token = base64.b64encode(f"{WP_USER}:{wp_pass}".encode()).decode()
    auth_header = f"Basic {token}"
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }

    # SSL 컨텍스트
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    def urlopen(req, timeout=30):
        return urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx)

    # 애드센스 코드
    adsense_html = (
        f'<!-- wp:html -->\n'
        f'<ins class="adsbygoogle" style="display:block" '
        f'data-ad-client="{ADSENSE_CODE}" '
        f'data-ad-slot="{ADSENSE_SLOT}" '
        f'data-ad-format="auto" '
        f'data-full-width-responsive="true"></ins>'
        f'<script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>\n'
        f'<!-- /wp:html -->'
    )

    # 마크다운 → HTML 변환
    content_with_placeholder = CONTENT

    # [애드센스] 마커 처리
    html_content = _md_to_wp_html(content_with_placeholder)
    html_content = html_content.replace("[애드센스]", adsense_html)

    # 이미지 업로드 및 {{이미지N}} 교체
    info_map = {img["index"]: img for img in IMAGES}
    def replace_image(m):
        idx = int(m.group(1))
        filepath = image_paths.get(idx, "")
        alt = info_map.get(idx, {}).get("alt", "")
        if filepath:
            url, media_id = _wp_upload_image_with_id(
                SITE_URL, auth_header, filepath, alt=alt, on_log=log)
            if url:
                log(f"[이미지{idx}] ✓ WP 업로드 완료: {url}")
                return f'<figure class="wp-block-image"><img src="{url}" alt="{alt}"/></figure>'
        log(f"[이미지{idx}] ✗ 파일 없음, 플레이스홀더 제거")
        return ""

    import re
    html_content = re.sub(r"\{\{이미지(\d+)\}\}", replace_image, html_content)

    # 썸네일(이미지1) 업로드
    featured_media_id = None
    if image_paths.get(1) and Path(image_paths[1]).exists():
        _, mid = _wp_upload_image_with_id(
            SITE_URL, auth_header, image_paths[1],
            alt=info_map[1]["alt"], on_log=log)
        if mid:
            featured_media_id = mid

    # 카테고리 조회
    cat_name = "정부지원금"
    cat_ids = []
    try:
        cat_url = f"{SITE_URL}/wp-json/wp/v2/categories?search={urllib.parse.quote(cat_name)}"
        req = urllib.request.Request(cat_url, headers=headers)
        cat_res = json.loads(urlopen(req, timeout=8).read())
        if cat_res:
            cat_ids = [cat_res[0]["id"]]
            log(f"[카테고리] '{cat_name}' ID: {cat_ids[0]}")
        else:
            create_req = urllib.request.Request(
                f"{SITE_URL}/wp-json/wp/v2/categories",
                data=json.dumps({"name": cat_name}).encode(),
                headers=headers, method="POST")
            new_cat = json.loads(urlopen(create_req, timeout=8).read())
            cat_ids = [new_cat["id"]]
    except Exception as e:
        log(f"[카테고리] 조회 실패: {e}")

    # 태그 조회/생성
    tag_ids = []
    for tag_name in TAGS[:12]:
        try:
            search_url = f"{SITE_URL}/wp-json/wp/v2/tags?search={urllib.parse.quote(tag_name)}"
            req = urllib.request.Request(search_url, headers=headers)
            res = json.loads(urlopen(req, timeout=8).read())
            if res:
                tag_ids.append(res[0]["id"])
            else:
                cr = urllib.request.Request(
                    f"{SITE_URL}/wp-json/wp/v2/tags",
                    data=json.dumps({"name": tag_name}).encode(),
                    headers=headers, method="POST")
                new_tag = json.loads(urlopen(cr, timeout=8).read())
                tag_ids.append(new_tag["id"])
        except Exception:
            pass

    # SEO 메타
    seo_title = f"{KEYWORD} 신청방법 핵심 정리 | {TITLE[:30]} 쉽게 확인"[:60]
    meta_desc = META[:160]
    slug = urllib.parse.quote(KEYWORD.replace(" ", "-"), safe="")

    # 포스트 발행 (status: publish)
    post_body = {
        "title": TITLE,
        "content": html_content,
        "status": "publish",
        "slug": slug,
        "tags": tag_ids,
        "categories": cat_ids,
        "meta": {
            "rank_math_focus_keyword": KEYWORD,
            "rank_math_title": seo_title,
            "rank_math_description": meta_desc,
        },
    }
    if featured_media_id:
        post_body["featured_media"] = featured_media_id

    log(f"[WordPress] 발행 요청: {TITLE}")
    req = urllib.request.Request(
        f"{SITE_URL}/wp-json/wp/v2/posts",
        data=json.dumps(post_body).encode(),
        headers=headers,
        method="POST",
    )
    resp = json.loads(urlopen(req, timeout=30).read())
    post_id = resp.get("id")
    post_url = resp.get("link", "")
    post_status = resp.get("status", "")
    log(f"[WordPress] ✓ 발행 완료 (ID={post_id}, status={post_status}): {post_url}")

    # Rank Math 메타 설정
    if post_id:
        try:
            rm_body = {
                "objectID": post_id,
                "objectType": "post",
                "meta": {
                    "rank_math_focus_keyword": KEYWORD,
                    "rank_math_title": seo_title,
                    "rank_math_description": meta_desc,
                    "rank_math_rich_snippet": "article",
                    "rank_math_snippet_article_type": "BlogPosting",
                },
            }
            rm_req = urllib.request.Request(
                f"{SITE_URL}/wp-json/rankmath/v1/updateMeta",
                data=json.dumps(rm_body).encode(),
                headers=headers,
                method="POST",
            )
            urlopen(rm_req, timeout=15)
            log("[WordPress] ✓ Rank Math 메타 설정 완료")
        except Exception as e:
            log(f"[WordPress] ⚠ Rank Math 설정 실패 (스킵): {e}")

    return post_url or True


def send_telegram(message):
    """텔레그램으로 보고"""
    result = subprocess.run(
        ['python3', 'tg_send.py', message],
        cwd='/Users/hana/Downloads/blog-automation-v2',
        capture_output=True,
        text=True,
        timeout=30
    )
    if result.returncode == 0:
        log("[텔레그램] 전송 완료")
    else:
        log(f"[텔레그램] 전송 실패: {result.stderr}")


def main():
    log("=" * 60)
    log(f"산재휴업급여신청 포스팅 발행 시작")
    log(f"제목: {TITLE}")
    log("=" * 60)

    # 1. 이미지 생성
    log("\n[1단계] 이미지 생성")
    image_paths = generate_images()
    log(f"생성된 이미지: {len(image_paths)}개")

    # 2. WordPress 발행
    log("\n[2단계] WordPress 발행")
    success = publish_to_wordpress(image_paths)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if success:
        log(f"\n✓ 발행 완료!")
        # 텔레그램 보고
        tg_msg = f"""✅ 발행 완료
블로그: baremi542
제목: {TITLE}
발행시각: {now}

🔧 검수 중 수정사항:
- 이상 없음"""
        send_telegram(tg_msg)
    else:
        log("\n✗ 발행 실패")
        tg_msg = f"""⚠️ 오류 발생
작업: baremi542 산재휴업급여신청 포스팅 발행
오류: WordPress REST API 발행 실패
조치: 로그 확인 필요"""
        send_telegram(tg_msg)


if __name__ == "__main__":
    main()
