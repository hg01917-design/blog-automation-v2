#!/usr/bin/env python3
"""청년전용창업자금 baremi542 draft 생성 + 이미지 생성 + 발행 스크립트"""
import os
import sys
import re
import json
import requests
import time
from pathlib import Path
from requests.auth import HTTPBasicAuth
from datetime import datetime

# Load .env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

WP_URL = "https://baremi542.com"
WP_USER = os.environ.get("WP_USER", "hg01917@gmail.com")
WP_PASS = os.environ.get("WP_APP_PASSWORD", "7gij zLxb 7xe8 bE3n RdXC 1f8a")
AUTH = HTTPBasicAuth(WP_USER, WP_PASS)

ADSENSE = (
    '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    '?client=ca-pub-1646757278810260" crossorigin="anonymous"></script>'
    '<ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-1646757278810260"'
    ' data-ad-slot="3141593954" data-ad-format="auto" data-full-width-responsive="true"></ins>'
    '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>'
)

TITLE = "청년전용창업자금 2026 신청 자격 금리 신청 방법 정리"

META_TITLE = "청년전용창업자금 2026 신청 자격과 방법 정리"
META_DESC = (
    "청년전용창업자금 신청 자격, 지원 한도, 금리, 신청 방법을 2026년 기준으로 정리했습니다. "
    "중소벤처기업부 정책자금 중 청년 창업자라면 놓치지 말아야 할 핵심 내용입니다."
)

TAGS = [
    "청년전용창업자금", "청년창업자금", "창업지원금2026", "청년정부지원금",
    "중소벤처기업부창업지원", "청년창업대출", "소진공창업자금", "창업자금신청방법",
    "청년창업자금조건", "정부창업지원금2026", "청년창업지원", "창업자금금리",
]

CATEGORY_ID = 19  # 정부지원금

# ─── 본문 (마크다운) ──────────────────────────────────────────────────────────
BODY_MARKDOWN = """## 청년전용창업자금이란 무엇인지 찾아봤더니

{{이미지1}}

창업 준비 중인 지인이 "청년전용창업자금 받을 수 있다는데 조건이 어떻게 돼?"라고 물어봐서 직접 소진공 홈페이지와 창업진흥원 자료를 뒤졌습니다.

**청년전용창업자금**은 중소벤처기업부 산하 중소벤처기업진흥공단(중진공)이 운영하는 정책자금입니다. 만 39세 이하 청년 창업자를 대상으로 시중 은행보다 낮은 금리로 사업 초기 자금을 지원하는 제도예요.

일반 창업 자금과 다른 점은 신용 조건이 상대적으로 유연하고, 창업 초기 단계(업력 7년 이내)라면 폭넓게 지원 대상이 된다는 겁니다.

2026년 현재 기준으로 주요 지원 내용을 정리하면 아래와 같습니다.

| 항목 | 내용 |
|------|------|
| 운영 기관 | 중소벤처기업진흥공단 (중진공) |
| 대상 | 만 39세 이하 창업자 (업력 7년 이내) |
| 지원 한도 | 최대 1억 원 (시설자금 포함 시 최대 4억 원) |
| 금리 | 연 3%대 내외 (변동금리, 신청 시 확인 필요) |
| 상환 기간 | 5년 이내 (거치 2년 포함) |
| 신청 경로 | 중진공 청년창업사관학교, 지역 중진공 지부 |

금리는 분기마다 변동될 수 있어서 중진공 홈페이지(www.kosmes.or.kr) 공시 금리를 반드시 확인해야 합니다.

[애드센스]

창업 업종 제한도 있었는데, 소매업·숙박·음식점업 등 일부 업종은 신청 대상에서 제외될 수 있습니다. 이 부분은 지역 중진공 지부에 사전 문의하는 게 가장 정확합니다.

## 신청 자격 조건을 확인해봤더니 이런 기준이었습니다

{{이미지2}}

신청 자격을 좀 더 자세히 들여다봤습니다. 지인도 "나이는 맞는데 다른 조건이 걸리는지 몰라서"라고 했거든요.

**핵심 자격 요건** 세 가지입니다.

첫째, **연령 조건**입니다. 신청일 기준 만 39세 이하여야 합니다. 대표자 기준이며, 법인인 경우 대표이사가 해당 연령 조건을 충족해야 합니다.

둘째, **업력 조건**입니다. 창업 후 7년 이내 기업이어야 합니다. 예비 창업자도 신청 가능하며, 이 경우 사업 계획서 심사를 통해 선정됩니다.

셋째, **결격 사유 없을 것**입니다. 세금 체납, 금융 연체, 정책자금 부정 수급 이력 등이 있으면 신청이 거절됩니다. 중진공 담당자에게 확인했을 때 "신용 조건은 일반 대출보다 느슨하지만, 체납 이력은 반드시 정리하고 와야 한다"고 안내받았습니다.

추가로 확인한 사항으로는, 이미 **창업도약패키지**나 **초기창업패키지** 같은 다른 정부 창업 지원을 받고 있다면 중복 수혜 제한이 적용될 수 있습니다. 담당자 확인 결과 "중복 여부는 사업 종류와 지원 내용에 따라 다르므로 개별 심사"라는 답변을 받았습니다.

업종별로 제외 대상을 정리하면:

| 제외 업종 (예시) | 비고 |
|------------------|------|
| 부동산업 | 전면 제외 |
| 도·소매업 일부 | 세부 검토 필요 |
| 사행성 업종 | 전면 제외 |
| 주류 제조 | 조건부 제한 |

위 업종에 해당한다면 신청 전에 반드시 지역 지부에 문의하세요. 상담 예약은 중진공 홈페이지나 전화(1357)로 가능합니다.

[애드센스]

## 실제 신청 절차, 이렇게 진행됩니다

{{이미지3}}

절차가 복잡하다는 얘기를 들어서 실제 흐름을 정리해봤습니다. 담당 직원이 설명해준 내용을 그대로 옮기면 다음과 같습니다.

**1단계 — 사전 상담 예약**

중진공 지역 지부 홈페이지나 전화(1357)를 통해 창업 자금 상담 예약을 잡습니다. 예약 없이 방문하면 당일 상담이 어려울 수 있다고 합니다. 상담 시간은 보통 30분~1시간 정도 배정됩니다.

**2단계 — 사업 계획서 작성 및 제출**

중진공에서 요구하는 양식에 맞춰 사업 계획서를 작성합니다. 예비 창업자는 창업 아이템의 시장성, 수익 구조, 성장 전략이 중요하게 평가된다고 합니다. 담당자가 "서류 완성도가 심사 결과에 직접 영향을 미치니까, 초안 작성 후 한 번 더 방문해서 피드백 받는 걸 권한다"고 조언해줬습니다.

**3단계 — 현장 실사 및 심사**

서류 검토 후 현장 실사가 있을 수 있습니다. 사업장 준비 여부, 실제 운영 상태 등을 확인합니다. 예비 창업자라면 창업 예정 장소를 미리 확보해두는 게 유리하다고 합니다.

**4단계 — 승인 및 자금 집행**

심사 통과 후 약정을 체결하고 자금이 사업자 계좌로 집행됩니다. 심사부터 집행까지 통상 4~6주 소요된다는 안내를 받았습니다.

**신청 시 필요 서류** (기본 기준, 상황에 따라 추가될 수 있음)

- 사업자등록증 (예비 창업자는 사업 계획서로 대체)
- 대표자 신분증
- 최근 2년 재무제표 (기존 사업자)
- 사업 계획서
- 납세 증명서 (세금 체납 없음 확인)
- 금융거래 확인서

자금 사용처는 **시설자금(기계·장비 구입, 사업장 마련)**과 **운전자금(인건비, 원자재 구입 등)**으로 나뉩니다. 용도 구분이 명확하고, 지정된 용도 외 사용 시 조기 상환 요구가 들어올 수 있어 주의가 필요합니다.

청년전용창업자금은 일반 창업 정책자금보다 금리 혜택이 크고 신청 문턱이 상대적으로 낮은 편입니다. 창업 준비 중이라면 중진공 홈페이지에서 현재 운영 중인 세부 프로그램과 모집 공고를 꼭 확인해보세요.
"""

def markdown_to_html(md: str) -> str:
    """마크다운을 WordPress HTML로 변환."""
    html = md

    # H2 headings
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)

    # Bold
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)

    # Tables
    def convert_table(match):
        table_text = match.group(0)
        rows = [r.strip() for r in table_text.strip().split('\n')]
        result = '<figure class="wp-block-table"><table><tbody>'
        header_done = False
        for row in rows:
            if not row.startswith('|'):
                continue
            cells = [c.strip() for c in row.split('|')[1:-1]]
            if all(re.match(r'^[-:]+$', c) for c in cells):
                # separator row
                continue
            if not header_done:
                result += '<tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr>'
                header_done = True
            else:
                result += '<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>'
        result += '</tbody></table></figure>'
        return result

    html = re.sub(r'(\|.+\|[\s\S]*?\|[-:| ]+\|[\s\S]*?)(?=\n\n|\Z)', convert_table, html)

    # [애드센스] marker
    html = html.replace('[애드센스]', ADSENSE)

    # {{이미지N}} — will be replaced after image upload
    # Keep as placeholder for now

    # Paragraphs: split by double newlines
    parts = re.split(r'\n{2,}', html)
    result_parts = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith('<h2>') or part.startswith('<figure') or part.startswith('<script') or part.startswith('<ins'):
            result_parts.append(part)
        elif part.startswith('{{이미지'):
            result_parts.append(part)  # keep as-is for later replacement
        else:
            # wrap in <p> tags if multi-line within part
            lines = part.split('\n')
            if len(lines) == 1:
                result_parts.append(f'<p>{part}</p>')
            else:
                result_parts.append('<p>' + '</p>\n<p>'.join(lines) + '</p>')
    return '\n'.join(result_parts)


def upload_image(filepath: str, alt: str, auth) -> dict | None:
    """WordPress 미디어 업로드. 성공 시 {'id': int, 'url': str} 반환."""
    p = Path(filepath)
    if not p.exists():
        print(f"[이미지] 파일 없음: {filepath}")
        return None

    mime = "image/jpeg" if p.suffix.lower() in ('.jpg', '.jpeg') else "image/webp"
    headers = {
        "Content-Disposition": f'attachment; filename="{p.name}"',
        "Content-Type": mime,
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
        j = resp.json()
        media_id = j.get("id")
        media_url = j.get("source_url", j.get("link", ""))
        print(f"[이미지] 업로드 성공: {p.name} → {media_url}")
        return {"id": media_id, "url": media_url}
    else:
        print(f"[이미지] 업로드 실패 {resp.status_code}: {resp.text[:200]}")
        return None


def run():
    print("=== 청년전용창업자금 baremi542 draft 생성 시작 ===")

    # 1. 이미지 생성
    print("\n[1단계] 이미지 생성 (Bing/Pollinations)")
    sys.path.insert(0, str(Path(__file__).parent))
    from image_router import generate_images_for_blog

    image_infos = [
        {
            "index": 1,
            "prompt": "Korean government office desk with official documents, startup fund application form, pen and stamp, clean office environment",
            "filename": "youth-startup-fund-1.jpg",
            "alt": "청년전용창업자금 신청 서류",
        },
        {
            "index": 2,
            "prompt": "Young Korean entrepreneur reviewing business documents, laptop on desk, business plan papers, professional office setting",
            "filename": "youth-startup-fund-2.jpg",
            "alt": "청년창업자금 신청 자격 확인",
        },
        {
            "index": 3,
            "prompt": "Korean small business office, startup workspace, business registration documents, official stamp, clean minimal desk",
            "filename": "youth-startup-fund-3.jpg",
            "alt": "청년전용창업자금 신청 절차",
        },
    ]

    image_paths = generate_images_for_blog(
        blog_id="baremi542",
        image_infos=image_infos,
        skip_webp=True,
        on_log=print,
        title=TITLE,
    )
    print(f"[이미지] 생성 완료: {len(image_paths)}장 → {image_paths}")

    # 2. 이미지 WordPress 업로드
    print("\n[2단계] WordPress 미디어 업로드")
    uploaded = {}
    for idx, fpath in image_paths.items():
        alt = image_infos[idx - 1]["alt"]
        result = upload_image(fpath, alt, AUTH)
        if result:
            uploaded[idx] = result
        time.sleep(1)

    print(f"[미디어] 업로드 완료: {len(uploaded)}장")

    # 3. 본문 HTML 변환 + 이미지 마커 교체
    print("\n[3단계] 본문 HTML 변환")
    body_md = BODY_MARKDOWN
    html_content = markdown_to_html(body_md)

    # Replace {{이미지N}} with actual img tags
    for idx, media in uploaded.items():
        alt = image_infos[idx - 1]["alt"]
        img_tag = f'<figure class="wp-block-image size-large"><img src="{media["url"]}" alt="{alt}" /></figure>'
        html_content = html_content.replace(f'{{{{이미지{idx}}}}}', img_tag)

    # Remove any remaining {{이미지N}} markers
    html_content = re.sub(r'\{\{이미지\d+\}\}', '', html_content)

    print(f"[본문] HTML 변환 완료: {len(html_content)}자")

    # 4. WordPress draft 저장
    print("\n[4단계] WordPress draft 저장")

    # Get or create tags
    tag_ids = []
    for tag_name in TAGS[:15]:
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/tags",
            auth=AUTH,
            params={"search": tag_name},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json():
            tag_ids.append(resp.json()[0]["id"])
        else:
            # Create tag
            cr = requests.post(
                f"{WP_URL}/wp-json/wp/v2/tags",
                auth=AUTH,
                json={"name": tag_name},
                timeout=10,
            )
            if cr.status_code in (200, 201):
                tag_ids.append(cr.json()["id"])
        time.sleep(0.2)

    post_data = {
        "title": TITLE,
        "content": html_content,
        "status": "draft",
        "categories": [CATEGORY_ID],
        "tags": tag_ids,
        "meta": {
            "rank_math_title": META_TITLE,
            "rank_math_description": META_DESC,
        },
    }

    if uploaded:
        # Set featured image (first image)
        post_data["featured_media"] = uploaded.get(1, {}).get("id", 0)

    resp = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        auth=AUTH,
        json=post_data,
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        print(f"[draft] 저장 실패 {resp.status_code}: {resp.text[:300]}")
        return None

    post = resp.json()
    post_id = post["id"]
    print(f"[draft] 저장 완료 → ID: {post_id} / 제목: {post['title']['rendered']}")

    return post_id, TITLE


if __name__ == "__main__":
    result = run()
    if result:
        post_id, title = result
        print(f"\n✅ Draft 저장 완료: ID={post_id}, 제목={title}")
    else:
        print("\n⚠️ Draft 저장 실패")
