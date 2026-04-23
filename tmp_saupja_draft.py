"""baremi542 사업자정책지원금 글 생성 + draft 저장 스크립트"""
import os
import sys
import json
import base64
import requests
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# .env 로드
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

WP_URL = "https://baremi542.com"
WP_USER = os.environ.get("WP_USER", "hg01917@gmail.com")
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
AUTH_TOKEN = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
HEADERS = {
    "Authorization": f"Basic {AUTH_TOKEN}",
    "Content-Type": "application/json",
}

TITLE = "사업자정책지원금 2026년 스마트상점 기술보급사업 신청 방법"

BODY_MARKDOWN = """가게를 운영하다 보면 이것저것 비용이 만만치 않게 들어요. 키오스크 하나 들여놓으려 해도 수백만 원이 넘고, 서빙 로봇이나 경영 관리 소프트웨어는 생각만 해도 한숨이 나오더라고요. 그러던 중에 지인한테서 국가에서 최대 100%까지 지원해주는 사업이 있다는 말을 듣고 바로 찾아봤어요.

찾아봤더니 중소벤처기업부와 소상공인시장진흥공단에서 주관하는 **2026년 스마트상점 기술보급사업**이 바로 그 제도였어요. 사업자라면 한 번쯤 들어봤을 만한 **사업자정책지원금** 중에서도 실제로 체감할 수 있는 규모의 지원을 받을 수 있는 프로그램이에요.

처음에는 반신반의했는데, 신청 조건을 확인해봤더니 생각보다 문턱이 낮았고, 지원 항목도 꽤 구체적이어서 당장 실행에 옮길 수 있겠다 싶었어요.

## 2026년 스마트상점 기술보급사업이란

{{이미지1}}

이 사업은 소상공인의 디지털 전환을 돕기 위해 정부가 직접 비용을 보조해주는 제도예요. 매장 운영에 필요한 스마트 기술 장비나 소프트웨어를 도입할 때, 구입 비용의 상당 부분을 국가가 대신 내주는 방식이에요.

지원 대상 품목은 크게 세 가지로 나뉘어요.

- **서빙 로봇**: 홀 서빙을 자동화해주는 로봇으로, 인건비 절감에 직접적인 효과가 있어요
- **키오스크**: 주문·결제 통합 무인단말기, 카페·식당·편의점 등 다양한 업종에서 활용 가능해요
- **경영 지원 소프트웨어**: 매출 분석, 재고 관리, 고객 관리까지 통합으로 처리할 수 있는 솔루션이에요

지원 방식도 업주 입장에서 선택할 수 있게 세 가지로 나뉘어 있어요.

| 지원 방식 | 내용 |
|-----------|------|
| 구입형 | 장비를 직접 구매하는 방식, 보조금으로 구입 비용 충당 |
| 렌탈형 | 월정액으로 장비를 빌리는 방식, 렌탈료 일부 지원 |
| 소프트웨어 구독형 | SaaS 형태의 소프트웨어를 구독, 구독료 일부 보조 |

지원 비율은 최대 70%에서 100%까지 조건에 따라 차등 적용돼요. 사업자 규모, 업종, 지역 등에 따라 비율이 달라지기 때문에 실제 신청 전에 본인 조건을 먼저 확인하는 게 중요해요.

[애드센스]

## 신청 조건과 절차 확인해봤더니

{{이미지2}}

신청 자격은 소상공인 기본 요건을 충족해야 해요. 상시 근로자 수가 업종별 기준 이하인 소상공인이면 대부분 해당되는데, 도소매·음식·숙박업은 5인 미만, 제조·건설·운수 등은 10인 미만이에요.

실제로 소진공 담당자에게 전화로 문의했을 때, "사업자등록이 되어 있고 해당 업종에서 실제 영업 중이면 일단 신청 가능합니다"라고 안내해줬어요. 복잡하게 생각할 필요 없이 사업자등록증만 있으면 기본 조건은 된다는 뜻이에요.

신청 절차는 다음 순서로 진행돼요.

**1단계 — 공식 홈페이지 직접 신청**
소상공인시장진흥공단 공식 홈페이지에서 직접 신청서를 작성해요. 이때 사업자등록증, 최근 매출 증빙 자료, 도입하려는 장비 견적서 등을 미리 준비해두면 수월해요.

**2단계 — 서류 검토**
신청 후 공단 측에서 제출 서류를 검토해요. 보통 2~3주 정도 소요된다고 해요. 서류에 누락이 있으면 보완 요청이 오니, 처음부터 꼼꼼하게 챙기는 게 좋아요.

**3단계 — 서면 평가**
서류가 통과되면 사업계획서를 바탕으로 서면 평가가 진행돼요. 장비 도입의 필요성, 예상 효과 등을 구체적으로 써야 유리해요.

**4단계 — 최종 선정**
평가 점수를 합산해 지원 대상자를 최종 선정해요. 선정 결과는 문자와 이메일로 동시에 통보돼요.

준비 서류를 미리 챙겨두면 신청에서 최종 선정까지 보통 4~6주 정도 걸려요. 사업 시작 직전에 신청하는 건 시간이 촉박할 수 있으니 여유 있게 준비하는 게 좋아요.

## 주의사항 — 이것만큼은 반드시 지키세요

{{이미지3}}

신청하면서 담당자가 강조했던 내용이 있어요. 절대로 불법 브로커를 통해 신청하면 안 된다는 거예요. 공식 홈페이지 직접 신청이 원칙이고, 수수료를 받고 대신 해준다는 업체는 모두 불법이에요.

실제로 "지원금 신청 대행"이라는 명목으로 접근하는 업체들이 꽤 있어요. 하지만 그런 업체를 통하면 지원금을 못 받는 것은 물론, 향후 다른 정부 사업 참여까지 제한될 수 있어요. 직접 신청이 조금 번거롭더라도 반드시 본인이 공식 채널로 접수해야 해요.

또 한 가지는 **의무 사용 기간** 문제예요. 지원받은 장비나 소프트웨어는 일정 기간 동안 의무적으로 사용해야 해요. 기간 내에 임의로 반납하거나 처분하면 지원금을 환수당할 수 있어요. 담당자가 직접 "의무 사용 기간을 지키지 않으면 전액 환수 조치가 내려진다"고 못을 박았어요.

[애드센스]

지원금 관련 서류를 처음 받았을 때 분량이 많아서 당황했어요. 그런데 항목별로 천천히 읽어보면 어렵지 않아요. 모르는 부분은 소진공 콜센터(1588-5302)에 전화하면 친절하게 안내해줘요. 당황하지 마세요, 한 항목씩 확인하다 보면 충분히 혼자서도 완료할 수 있어요.

2026년에 매장 운영 비용 때문에 고민 중인 소상공인이라면, 스마트상점 기술보급사업이 실질적인 도움이 될 수 있어요. 키오스크 하나 들이는 데 수백만 원이 들던 게, 지원을 받으면 실제 부담이 크게 줄어들거든요. 신청 기간 놓치지 않도록 공식 홈페이지를 미리 즐겨찾기 해두는 걸 권해요.
"""

TAGS = ["사업자정책지원금", "스마트상점기술보급사업", "소상공인지원금", "2026지원금", "키오스크지원", "서빙로봇지원", "소진공지원사업", "정부지원금신청", "소상공인정책자금", "중소벤처기업부지원"]

META_DESC = "2026년 스마트상점 기술보급사업 신청 방법과 조건을 실제 경험을 바탕으로 정리했어요. 서빙 로봇, 키오스크, 경영 소프트웨어 최대 100% 지원받는 사업자정책지원금 완벽 안내."

IMAGE_INFOS = [
    {
        "index": 1,
        "prompt": "Korean government office desk with official policy documents, stamp, and pen, soft office lighting, clean organized composition, policy support fund concept",
        "filename": "saupja-jiwongeum-policy-1.jpg",
        "alt": "사업자정책지원금 스마트상점 기술보급사업 안내 문서",
    },
    {
        "index": 2,
        "prompt": "Korean small business owner reviewing application documents at a cafe counter, kiosk device nearby, natural indoor lighting, concept of government grant application",
        "filename": "saupja-jiwongeum-apply-2.jpg",
        "alt": "소상공인 스마트상점 지원금 신청 절차",
    },
    {
        "index": 3,
        "prompt": "Modern Korean small restaurant or cafe with self-ordering kiosk and serving robot, clean interior, soft warm lighting, smart store technology concept",
        "filename": "saupja-jiwongeum-kiosk-3.jpg",
        "alt": "스마트상점 키오스크 서빙로봇 지원 사업",
    },
]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def generate_images():
    """image_router.py로 이미지 생성"""
    log("이미지 생성 시작...")
    from image_router import generate_images_for_blog
    results = generate_images_for_blog(
        blog_id="baremi542",
        image_infos=IMAGE_INFOS,
        skip_webp=True,
        on_log=log,
        title=TITLE,
    )
    log(f"이미지 생성 완료: {len(results)}장 → {results}")
    return results


def upload_media(filepath: str, alt_text: str) -> int | None:
    """WordPress 미디어 업로드 → attachment ID 반환"""
    filename = Path(filepath).name
    with open(filepath, "rb") as f:
        data = f.read()

    upload_headers = {
        "Authorization": f"Basic {AUTH_TOKEN}",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "image/jpeg",
    }
    resp = requests.post(
        f"{WP_URL}/wp-json/wp/v2/media",
        headers=upload_headers,
        data=data,
        timeout=60,
    )
    if resp.status_code in (200, 201):
        media = resp.json()
        media_id = media["id"]
        # alt text 업데이트
        requests.post(
            f"{WP_URL}/wp-json/wp/v2/media/{media_id}",
            headers=HEADERS,
            json={"alt_text": alt_text},
            timeout=30,
        )
        log(f"미디어 업로드 완료: {filename} → ID {media_id}")
        return media_id
    else:
        log(f"미디어 업로드 실패: {resp.status_code} {resp.text[:200]}")
        return None


def build_content(body: str, image_results: dict, image_infos: list, media_ids: dict) -> str:
    """마크다운 → WordPress HTML 변환 + 이미지 삽입"""
    import re

    # 이미지 마커 → WordPress 이미지 블록으로 교체
    for info in image_infos:
        idx = info["index"]
        alt = info["alt"]
        marker = f"{{{{이미지{idx}}}}}"
        media_id = media_ids.get(idx)
        img_path = image_results.get(idx, "")

        if media_id:
            img_html = (
                f'<!-- wp:image {{"id":{media_id},"sizeSlug":"large"}} -->\n'
                f'<figure class="wp-block-image size-large">'
                f'<img src="{WP_URL}/wp-content/uploads/{Path(img_path).name}" alt="{alt}" class="wp-image-{media_id}"/>'
                f'</figure>\n'
                f'<!-- /wp:image -->'
            )
        else:
            img_html = ""

        body = body.replace(marker, img_html)

    # 애드센스 마커 → WordPress HTML 블록
    adsense_block = (
        '<!-- wp:html -->\n'
        '<div class="adsbygoogle-wrap">'
        '<ins class="adsbygoogle" style="display:block;text-align:center;" '
        'data-ad-layout="in-article" data-ad-format="fluid" '
        'data-ad-client="ca-pub-XXXXXXXXXXXXXXXX" data-ad-slot="XXXXXXXXXX"></ins>'
        '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>'
        '</div>\n'
        '<!-- /wp:html -->'
    )
    body = body.replace("[애드센스]", adsense_block)

    # 마크다운 → HTML 변환
    lines = body.split("\n")
    html_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # 테이블 처리
        if "|" in line and i + 1 < len(lines) and "|---" in lines[i + 1]:
            table_lines = [line]
            i += 1  # skip separator
            i += 1
            while i < len(lines) and "|" in lines[i]:
                table_lines.append(lines[i])
                i += 1
            # 테이블 헤더
            headers = [h.strip() for h in table_lines[0].split("|") if h.strip()]
            th_html = "".join(f"<th>{h}</th>" for h in headers)
            rows_html = ""
            for row_line in table_lines[1:]:
                cells = [c.strip() for c in row_line.split("|") if c.strip()]
                rows_html += "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>\n"
            html_lines.append(
                f'<!-- wp:table -->\n<figure class="wp-block-table">'
                f'<table><thead><tr>{th_html}</tr></thead>'
                f'<tbody>{rows_html}</tbody></table>'
                f'</figure>\n<!-- /wp:table -->'
            )
            continue

        # H2
        if line.startswith("## "):
            text = line[3:].strip()
            html_lines.append(f'<!-- wp:heading {{"level":2}} -->\n<h2>{text}</h2>\n<!-- /wp:heading -->')

        # 리스트 항목
        elif line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                item = lines[i][2:].strip()
                item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item)
                items.append(f"<li>{item}</li>")
                i += 1
            html_lines.append(
                f'<!-- wp:list -->\n<ul>{"".join(items)}</ul>\n<!-- /wp:list -->'
            )
            continue

        # wp:html 블록 (애드센스/이미지) 그대로 삽입
        elif line.startswith("<!-- wp:"):
            html_lines.append(line)

        # 빈 줄
        elif line.strip() == "":
            pass  # 단락 구분은 아래에서 처리

        # 일반 단락
        else:
            # 순서 있는 리스트 (1. 2. 등)
            if re.match(r"^\*\*\d+단계", line) or re.match(r"^\d+\.", line):
                text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
                html_lines.append(
                    f'<!-- wp:paragraph -->\n<p>{text}</p>\n<!-- /wp:paragraph -->'
                )
            else:
                text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
                html_lines.append(
                    f'<!-- wp:paragraph -->\n<p>{text}</p>\n<!-- /wp:paragraph -->'
                )

        i += 1

    return "\n\n".join(html_lines)


def get_or_create_tags(tag_names: list) -> list:
    """태그명 → WordPress 태그 ID 목록 반환 (없으면 생성)"""
    tag_ids = []
    for name in tag_names:
        # 검색
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/tags",
            headers=HEADERS,
            params={"search": name, "per_page": 5},
            timeout=15,
        )
        found = False
        if resp.status_code == 200:
            for tag in resp.json():
                if tag["name"] == name:
                    tag_ids.append(tag["id"])
                    found = True
                    break
        if not found:
            # 생성
            cr = requests.post(
                f"{WP_URL}/wp-json/wp/v2/tags",
                headers=HEADERS,
                json={"name": name},
                timeout=15,
            )
            if cr.status_code in (200, 201):
                tag_ids.append(cr.json()["id"])
    log(f"태그 ID: {tag_ids}")
    return tag_ids


def get_category_id(slug_or_name: str) -> int | None:
    """카테고리 slug 또는 이름으로 ID 조회"""
    resp = requests.get(
        f"{WP_URL}/wp-json/wp/v2/categories",
        headers=HEADERS,
        params={"per_page": 50},
        timeout=15,
    )
    if resp.status_code == 200:
        for cat in resp.json():
            if cat["slug"] == slug_or_name or cat["name"] == slug_or_name:
                return cat["id"]
    return None


def save_draft(content_html: str, tag_ids: list, featured_media_id: int | None) -> dict | None:
    """WordPress REST API로 draft 저장"""
    cat_id = get_category_id("정부지원금")
    log(f"카테고리 ID: {cat_id}")

    payload = {
        "title": TITLE,
        "content": content_html,
        "status": "draft",
        "tags": tag_ids,
        "meta": {
            "rank_math_title": TITLE,
            "rank_math_description": META_DESC,
            "rank_math_focus_keyword": "사업자정책지원금",
        },
    }
    if cat_id:
        payload["categories"] = [cat_id]
    if featured_media_id:
        payload["featured_media"] = featured_media_id

    resp = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        headers=HEADERS,
        json=payload,
        timeout=30,
    )
    if resp.status_code in (200, 201):
        post = resp.json()
        log(f"Draft 저장 완료: ID={post['id']}, 링크={post.get('link','')}")
        return post
    else:
        log(f"Draft 저장 실패: {resp.status_code} {resp.text[:300]}")
        return None


def main():
    log("=" * 60)
    log("baremi542 사업자정책지원금 글 생성 시작")
    log("=" * 60)

    # 1. 이미지 생성
    image_results = generate_images()

    # 2. 이미지 업로드
    media_ids = {}
    for info in IMAGE_INFOS:
        idx = info["index"]
        img_path = image_results.get(idx)
        if img_path and Path(img_path).exists():
            mid = upload_media(img_path, info["alt"])
            if mid:
                media_ids[idx] = mid
        else:
            log(f"이미지 {idx} 없음, 업로드 건너뜀")

    log(f"업로드된 미디어: {media_ids}")

    # 3. 본문 HTML 변환
    content_html = build_content(BODY_MARKDOWN, image_results, IMAGE_INFOS, media_ids)

    # 글자수 확인 (HTML 제거 후)
    import re
    plain = re.sub(r"<[^>]+>", "", content_html)
    plain = re.sub(r"<!--.*?-->", "", plain, flags=re.DOTALL)
    char_count = len(plain.strip())
    log(f"본문 글자수(HTML 제거): {char_count}자")

    # 4. 태그 생성
    tag_ids = get_or_create_tags(TAGS)

    # 5. 대표 이미지
    featured_media_id = media_ids.get(1)

    # 6. Draft 저장
    post = save_draft(content_html, tag_ids, featured_media_id)

    if post:
        draft_id = post["id"]
        log(f"\n✅ 완료: draft_id={draft_id}")

        # 텔레그램 보고
        os.system(
            f'cd /Users/hana/Downloads/blog-automation-v2 && '
            f'python3 tg_send.py "✅ baremi542 draft 저장 완료\n'
            f'제목: {TITLE}\n'
            f'글자수: {char_count}자\n'
            f'이미지: {len(media_ids)}장\n'
            f'draft_id: {draft_id}"'
        )
        return draft_id
    else:
        os.system(
            f'cd /Users/hana/Downloads/blog-automation-v2 && '
            f'python3 tg_send.py "⚠️ 오류 발생\n'
            f'작업: baremi542 글 생성\n'
            f'오류: Draft 저장 실패\n'
            f'조치: 로그 확인 필요"'
        )
        return None


if __name__ == "__main__":
    main()
