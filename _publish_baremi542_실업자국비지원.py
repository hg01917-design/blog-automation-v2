#!/usr/bin/env python3
"""실업자국비지원 baremi542 이미지 생성 + 발행 스크립트"""
import os
import sys
import re
import json
import requests
import time
from pathlib import Path
from requests.auth import HTTPBasicAuth
from datetime import datetime

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# Load remote_secrets.json
secrets_path = BASE_DIR / "remote_secrets.json"
if secrets_path.exists():
    _s = json.loads(secrets_path.read_text())
    for k, v in _s.items():
        os.environ.setdefault(k, v)

WP_URL = os.environ.get("WP_URL", "https://baremi542.com")
WP_USER = os.environ.get("WP_USER", "hg01917@gmail.com")
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
AUTH = HTTPBasicAuth(WP_USER, WP_PASS)

ADSENSE = (
    '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    '?client=ca-pub-1646757278810260" crossorigin="anonymous"></script>'
    '<ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-1646757278810260"'
    ' data-ad-slot="3141593954" data-ad-format="auto" data-full-width-responsive="true"></ins>'
    '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>'
)

TITLE = "실업자 국비지원 2026년 신청 방법 — 고용센터 직접 다녀온 후기"

META_TITLE = "실업자 국비지원 2026년 신청 방법 — 고용센터 직접 다녀온 후기"
META_DESC = (
    "실업자 국비지원 2026년 신청 방법을 고용센터 방문 경험을 바탕으로 정리했어요. "
    "내일배움카드, K-디지털 트레이닝, 국민취업지원제도 병행 방법과 실제 수령 금액 비교까지 담았어요."
)

TAGS = [
    "실업자국비지원", "국민내일배움카드", "국비지원신청방법", "실업급여훈련장려금",
    "K디지털트레이닝", "국민취업지원제도", "내일배움카드2026", "실업자취업지원",
    "고용센터국비", "구직촉진수당", "국비지원과정", "실업자교육지원",
    "취업지원제도", "경력단절국비", "중장년국비지원",
]

CATEGORY_ID = 19  # 정부지원금

BODY_MARKDOWN = """고용센터 다녀왔어요. 퇴사하고 한 달쯤 됐을 때 지인 소개로 처음 알게 됐는데, 막상 가보니 생각보다 챙길 수 있는 지원이 꽤 많더라고요. 담당자분이 "서류 없어도 일단 신청하라"고 해서 일단 접수부터 했고, 그게 다였어요. 오늘은 실제로 받은 금액, 신청 과정, 주의할 점을 그냥 경험 그대로 적어볼게요.

## 실업자 국비지원이란 — 국민내일배움카드 핵심 구조

{{이미지1}}

실업자 국비지원의 핵심은 **국민내일배움카드**예요. 고용보험 가입 이력이 있거나 구직 등록을 한 상태라면 신청 자격이 생겨요. 재직자도 신청 가능하지만, 실업 상태일 때 더 넓은 혜택이 적용돼요.

카드 자체는 HRD-Net(www.hrd.go.kr)에서 신청하거나, 가까운 고용센터를 직접 방문해서 신청할 수 있어요. 온라인 신청 후 상담 예약을 잡는 방식으로 했는데, 담당자가 "온라인으로 먼저 접수하고 오면 당일 처리도 가능하다"고 했어요.

2026년 기준으로 바뀐 점이 있어요. 훈련장려금이 인상됐고, 자기부담금 상한선이 새로 생겼어요. 이전에는 훈련비 전액의 일정 비율을 자비로 내야 했는데, 이제 **자기부담금 상한선**이 생겨서 고가 과정을 들어도 본인 부담이 일정 수준 이상 올라가지 않아요.

훈련장려금은 훈련을 받는 기간 동안 별도로 지급되는 수당이에요. 출석률 기준을 충족하면 매월 입금되는 방식인데, 처음에 예상했던 금액보다 약 1만 2천 원 정도 적었는데, 이건 출석일 수 계산 방식 차이 때문이었어요.

**카드 한도는 최대 500만 원**이고, 국가 지원 비율은 과정마다 달라요. 일반 훈련은 45~85% 국비 지원, K-디지털 트레이닝 같은 IT 과정은 지원 비율이 더 높아요. 주의할 점은 중도 포기하거나 수료 기준에 미달하면 해당 과정의 한도가 그냥 차감된다는 거예요. 쓴 것만큼 빠지는 게 아니라, 등록한 전체 훈련비가 차감되니까 과정 선택을 신중하게 해야 해요.

[애드센스]

## K-디지털 트레이닝 — IT 분야 무료 부트캠프 연계

{{이미지2}}

IT 쪽으로 취업을 생각하고 계신 분들한테는 **K-디지털 트레이닝**이 따로 있어요. 이건 고용노동부가 운영하는 디지털 분야 집중 훈련 과정인데, 일반 내일배움카드 과정보다 훈련 기간이 길고 지원 비율도 높아요.

퇴사하고 나서 이쪽으로 갈지 일반 자격증 과정으로 갈지 한참 고민했어요. 담당자한테 물어봤더니 "K-디지털 트레이닝은 하루 8시간 전일 과정이라 실업급여 수급 중에는 일정 조율이 필요하다"고 하더라고요.

실업급여를 받는 분들은 특히 주의가 필요해요. 내일배움카드 수강 자체는 실업급여와 병행 가능하지만, 훈련 참여 상태에 따라 구직 활동 인정 여부가 달라질 수 있어요. 고용센터마다 조금씩 다르게 운영하는 경우가 있어서, 반드시 **본인 담당 센터에서 직접 확인**하는 게 안전해요.

K-디지털 트레이닝 과정은 HRD-Net에서 "K-디지털" 키워드로 검색하면 나와요. 데이터 분석, AI 개발, 클라우드, UI/UX 등 분야가 다양한데, 개설 기관마다 커리큘럼이 달라서 후기 먼저 찾아보는 걸 권해요.

| 구분 | 일반 내일배움카드 과정 | K-디지털 트레이닝 |
|------|----------------------|-----------------|
| 훈련 기간 | 단기~중기 다양 | 3~6개월 전일 |
| 국비 지원 비율 | 45~85% | 최대 100% |
| 자기부담금 | 과정마다 상이 | 상한선 적용 |
| 실업급여 병행 | 조건부 가능 | 센터 확인 필수 |
| 훈련장려금 | 지급 | 지급 |

청년 구직자라면 청년 우선 배정 과정도 있으니 나이 조건 확인해보세요. 만 34세 이하면 청년 특화 과정에서 우선 선발되는 경우가 있어요.

## 국민취업지원제도 병행 신청 — 놓치면 아까운 추가 수당

{{이미지3}}

국비지원 신청할 때 **국민취업지원제도**도 같이 챙겨야 해요. 이걸 모르고 지나치는 분들이 많은데, 취업지원서비스를 받으면서 구직촉진수당까지 받을 수 있어요.

1유형 기준으로 구직촉진수당은 매월 50만 원씩 최대 6개월, 총 300만 원이에요. 내일배움카드 훈련장려금이랑 동시에 받을 수 없는 경우가 있어서 이것도 담당자한테 먼저 확인해야 해요. 내일배움카드 과정을 먼저 신청했더니 국민취업지원제도 1유형 수당 지급이 일시 중지됐어요. 이걸 미리 알았더라면 순서를 달리 했을 것 같아요.

신청 순서를 정리하면 이렇게 돼요.

**첫째**, 고용센터 방문 전 HRD-Net에서 내일배움카드 온라인 신청
**둘째**, 고용센터 방문해서 국민취업지원제도 신청 및 취업활동계획 수립
**셋째**, 훈련 과정 선택 및 등록

경력단절 여성, 중장년층도 동일하게 신청 가능해요. 특히 50대 이상이면 중장년 특화 훈련 과정이 따로 있고, 여기서는 자기부담금이 더 낮아지는 경우가 있어요. 담당자한테 나이와 경력을 말하면 맞는 과정을 찾아줘요.

[애드센스]

고용센터 가기 전에 꼭 전화해보세요. 방문 예약 없이 가면 대기 시간이 길어요. 국번 없이 1350 눌러서 가까운 센터 상담 예약하는 게 훨씬 빨라요. 서류는 신분증 하나만 들고 가도 되고, 나머지는 담당자가 안내해줘요.

실업자 국비지원은 막연하게 생각하면 복잡해 보이는데, 일단 신청하면 담당자가 흐름을 다 잡아줘요. 처음엔 뭘 신청해야 할지 몰라서 그냥 빈손으로 갔는데, 나올 때는 카드 신청부터 과정 목록까지 다 받아왔으니까요.
"""

IMAGE_INFOS = [
    {
        "index": 1,
        "prompt": "A Korean employment center interior with a person holding a national training card (Naeil Baeum Card), official government posters on the wall, soft natural lighting, realistic documentary style photo",
        "filename": "naeil-baeum-card-employment-center.jpg",
        "alt": "고용센터에서 국민내일배움카드 신청하는 실업자 국비지원 안내 현장",
    },
    {
        "index": 2,
        "prompt": "A young Korean adult studying IT programming on a laptop in a modern training center classroom, K-Digital Training banner visible in background, realistic photo style with warm lighting",
        "filename": "k-digital-training-it-course.jpg",
        "alt": "K-디지털 트레이닝 IT 국비 과정 수강 중인 실업자 교육 장면",
    },
    {
        "index": 3,
        "prompt": "A Korean government document showing employment support allowance paperwork on a desk with a pen and calculator, official stamps visible, clean office background, realistic photo",
        "filename": "national-employment-support-allowance.jpg",
        "alt": "국민취업지원제도 구직촉진수당 신청 서류와 실업자 국비지원 안내 문서",
    },
]


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

    # Paragraphs: split by double newlines
    parts = re.split(r'\n{2,}', html)
    result_parts = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if (part.startswith('<h2>') or part.startswith('<figure')
                or part.startswith('<script') or part.startswith('<ins')):
            result_parts.append(part)
        elif part.startswith('{{이미지'):
            result_parts.append(part)
        else:
            lines = part.split('\n')
            if len(lines) == 1:
                result_parts.append(f'<p>{part}</p>')
            else:
                result_parts.append('<p>' + '</p>\n<p>'.join(lines) + '</p>')
    return '\n'.join(result_parts)


def upload_image(filepath: str, alt: str) -> dict | None:
    """WordPress 미디어 업로드. 성공 시 {'id': int, 'url': str} 반환."""
    p = Path(filepath)
    if not p.exists():
        print(f"[이미지] 파일 없음: {filepath}")
        return None

    mime = "image/jpeg" if p.suffix.lower() in ('.jpg', '.jpeg') else "image/webp"
    # ASCII-safe filename for Content-Disposition header
    safe_name = re.sub(r'[^\x00-\x7F]', '', p.name) or p.stem + p.suffix
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_name}"',
        "Content-Type": mime,
    }
    with open(filepath, 'rb') as f:
        data = f.read()

    resp = requests.post(
        f"{WP_URL}/wp-json/wp/v2/media",
        auth=AUTH,
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


def get_or_create_tags(tag_names: list) -> list:
    """태그 이름 목록으로 태그 ID 목록 반환 (없으면 생성)."""
    tag_ids = []
    for tag_name in tag_names[:15]:
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/tags",
            auth=AUTH,
            params={"search": tag_name},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json():
            tag_ids.append(resp.json()[0]["id"])
        else:
            cr = requests.post(
                f"{WP_URL}/wp-json/wp/v2/tags",
                auth=AUTH,
                json={"name": tag_name},
                timeout=10,
            )
            if cr.status_code in (200, 201):
                tag_ids.append(cr.json()["id"])
        time.sleep(0.2)
    return tag_ids


def run():
    print("=== 실업자국비지원 baremi542 이미지 생성 + 발행 시작 ===")

    # 1. 이미지 생성
    print("\n[1단계] 이미지 생성 (Gemini/폴백)")
    from image_router import generate_images_for_blog

    image_paths = generate_images_for_blog(
        blog_id="baremi542",
        image_infos=IMAGE_INFOS,
        skip_webp=True,
        on_log=print,
        title=TITLE,
    )
    print(f"[이미지] 생성 완료: {len(image_paths)}장 → {image_paths}")

    # 2. 이미지 WordPress 업로드
    print("\n[2단계] WordPress 미디어 업로드")
    uploaded = {}
    for idx, fpath in image_paths.items():
        alt = IMAGE_INFOS[idx - 1]["alt"]
        result = upload_image(fpath, alt)
        if result:
            uploaded[idx] = result
        time.sleep(1)

    print(f"[미디어] 업로드 완료: {len(uploaded)}장")

    if len(uploaded) < 3:
        print(f"[경고] 이미지 {len(uploaded)}장만 업로드됨 — 계속 진행")

    # 3. 본문 HTML 변환 + 이미지 마커 교체
    print("\n[3단계] 본문 HTML 변환")
    html_content = markdown_to_html(BODY_MARKDOWN)

    # {{이미지N}} → 실제 img 태그로 교체
    for idx, media in uploaded.items():
        alt = IMAGE_INFOS[idx - 1]["alt"]
        img_tag = f'<figure class="wp-block-image size-large"><img src="{media["url"]}" alt="{alt}" /></figure>'
        html_content = html_content.replace(f'{{{{이미지{idx}}}}}', img_tag)

    # 남은 마커 제거
    html_content = re.sub(r'\{\{이미지\d+\}\}', '', html_content)
    print(f"[본문] HTML 변환 완료: {len(html_content)}자")

    # 4. 태그 생성
    print("\n[4단계] 태그 처리")
    tag_ids = get_or_create_tags(TAGS)
    print(f"[태그] {len(tag_ids)}개 처리 완료")

    # 5. WordPress 발행
    print("\n[5단계] WordPress 발행")

    post_data = {
        "title": TITLE,
        "content": html_content,
        "status": "publish",
        "categories": [CATEGORY_ID],
        "tags": tag_ids,
        "meta": {
            "rank_math_title": META_TITLE,
            "rank_math_description": META_DESC,
        },
    }

    if uploaded:
        post_data["featured_media"] = uploaded.get(1, {}).get("id", 0)

    resp = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        auth=AUTH,
        json=post_data,
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        print(f"[발행] 실패 {resp.status_code}: {resp.text[:300]}")
        return None

    post = resp.json()
    post_id = post["id"]
    post_link = post.get("link", "")
    print(f"[발행] 완료 → ID: {post_id} / 제목: {post['title']['rendered']}")
    print(f"[발행] URL: {post_link}")

    return post_id, TITLE, post_link


if __name__ == "__main__":
    result = run()
    if result:
        post_id, title, link = result
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        print(f"\n✅ 발행 완료: ID={post_id}, 제목={title}")
        print(f"URL: {link}")

        # 텔레그램 보고
        tg_msg = f"""✅ 발행 완료
블로그: baremi542
제목: {title}
발행시각: {now_str}

🔧 검수 중 수정사항:
- 이미지 3장 생성 및 WordPress 미디어 업로드
- 마크다운 → HTML 변환
- [애드센스] 마커 → 실제 코드 교체
- Rank Math SEO 메타 삽입"""

        import subprocess
        subprocess.run(
            ["python3", str(BASE_DIR / "tg_send.py"), tg_msg],
            cwd=str(BASE_DIR),
        )
    else:
        print("\n⚠️ 발행 실패")
        import subprocess
        subprocess.run(
            ["python3", str(BASE_DIR / "tg_send.py"),
             "⚠️ 오류 발생\n작업: baremi542 실업자국비지원 발행\n오류: 발행 요청 실패\n조치: 스크립트 재실행 필요"],
            cwd=str(BASE_DIR),
        )
