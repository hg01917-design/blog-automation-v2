"""직장인국비지원 글 생성 + 이미지 생성 + WordPress Draft 저장"""
import os
import sys
import json
import base64
import urllib.request
import urllib.parse
import time
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# .env 로드
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

WP_URL = "https://baremi542.com"
WP_USER = os.getenv("WP_USER", "hg01917@gmail.com")
WP_PASS = os.getenv("WP_APP_PASSWORD", "")

TITLE = "직장인국비지원 신청 방법과 지원 가능 교육과정 2026 비교 가이드"

BODY_MARKDOWN = """## 직장인도 국비지원 받을 수 있나요?

{{이미지1}}

직장을 다니면서도 정부의 국비 지원을 받아 자격증을 취득하거나 직무 역량을 키울 수 있다는 사실, 알고 계셨나요? 많은 분들이 국비지원은 구직자나 실업자만 받을 수 있다고 오해하지만, 실제로는 재직 중인 직장인도 다양한 경로로 교육비 지원을 받을 수 있습니다.

대표적인 제도가 **국민내일배움카드(재직자 계좌제)**입니다. 이 제도는 고용보험에 가입된 근로자라면 누구나 신청할 수 있으며, 1인당 300만 원에서 최대 500만 원까지 훈련비를 지원받을 수 있습니다.

실제로 국비지원 교육을 이용한 분들의 후기를 살펴보면, 직장을 다니면서 야간이나 주말 과정을 이수해 자격증을 취득하거나, 온라인 강의로 업무에 필요한 기술을 익히는 사례가 많습니다. 2026년에도 이 제도는 그대로 운영되고 있으며, 지원 범위는 오히려 더 넓어졌습니다.

[애드센스]

## 직장인 국비지원 신청 방법 단계별 안내

{{이미지2}}

직장인 국민내일배움카드 신청 절차는 크게 세 단계로 나뉩니다. 어렵지 않으니 차근차근 따라오세요.

**1단계 — HRD-Net 회원 가입 및 카드 신청**

국민내일배움카드는 고용노동부 HRD-Net(www.hrd.go.kr) 또는 고용24(www.work.go.kr) 홈페이지에서 신청합니다.

- HRD-Net 접속 → 로그인(공동인증서 또는 간편인증)
- [국민내일배움카드] 메뉴 → 신청서 작성
- 재직자의 경우 재직 확인 서류(재직증명서 또는 건강보험 가입 확인서) 업로드
- 카드 수령(약 2~3주 소요)

**2단계 — 훈련 과정 선택 및 수강 신청**

카드가 발급되면 HRD-Net에서 원하는 교육 과정을 검색해 수강 신청합니다.

- 직종, 지역, 온/오프라인 여부 필터 적용
- 과정별 지원 금액, 자부담 비율 확인 (일반적으로 자부담 15~55%)
- 수강 신청 완료 후 훈련기관에 등록

**3단계 — 수강 및 출석 인증**

오프라인 과정이라면 매 수업마다 출석 인증(지문/QR 스캔)이 필요합니다. 온라인 과정도 학습 진도율 80% 이상을 충족해야 수료 처리되며, 수료 후 남은 잔액은 다음 과정에 재사용할 수 있습니다.

| 구분 | 내용 |
|------|------|
| 지원 대상 | 고용보험 가입 재직자, 특고·프리랜서, 자영업자(매출 1.5억 이하) |
| 지원 금액 | 300만 원(기본) ~ 500만 원(취약계층 우대) |
| 자부담 비율 | 15% ~ 55% (소득·취약 여부에 따라 차등) |
| 카드 유효기간 | 5년 |
| 신청 방법 | HRD-Net, 고용24, 고용센터 방문 |

[애드센스]

## 직장인이 신청 가능한 주요 국비지원 교육과정 2026

{{이미지3}}

재직자가 특히 관심 갖는 교육 분야는 IT, 데이터 분석, 회계·세무, 어학, 자격증 취득 등입니다. 2026년 기준 인기 있는 국비지원 과정을 정리했습니다.

**IT·개발 계열**

파이썬, 데이터 분석, AI·머신러닝, 웹개발, 클라우드(AWS·Azure) 관련 과정이 가장 활성화되어 있습니다. 삼성SDS 멀티캠퍼스, 이스트소프트, KG아이티뱅크 등 대형 훈련기관이 재직자 야간·주말반을 운영합니다.

**자격증 취득 과정**

산업기사·기사 시험 대비 과정, 전산세무·회계, 사회복지사, 직업상담사 등의 자격증 취득 과정이 국비지원 대상에 포함됩니다. 자격증 취득 후 장려금을 받을 수 있는 과정도 있습니다.

**어학·비즈니스 영어**

직무 관련 비즈니스 영어, TOEIC, OPIc 준비 과정도 지원 대상입니다. 단, 일반 회화 목적의 강의는 지원되지 않을 수 있으므로 HRD-Net에서 국비 지원 여부를 반드시 확인하세요.

**회계·세무·HR 계열**

재경관리사, ERP 정보관리사, 세무사 시험 대비, 노무·인사 실무 과정도 직장인 수요가 높습니다. 특히 재직자 대상으로 야간·주말반이 열려 있는 경우가 많습니다.

## 직장인 재직자훈련 추가 지원제도

국민내일배움카드 외에도 직장인이 활용할 수 있는 국비지원 제도가 더 있습니다.

**사업주 직업훈련 지원**

회사가 직원을 대상으로 집합교육 또는 사내 훈련을 실시하면 고용보험 환급을 받을 수 있습니다. 직원 입장에서는 회사가 지원하는 교육을 무료로 수강하는 방식이지만, 간접적으로 국비 혜택을 누리는 것입니다. 회사 인사팀에 사업주 훈련 지원 여부를 확인해보는 것이 좋습니다.

**구직자 내일배움카드 vs 재직자 국민내일배움카드**

| 구분 | 구직자 내일배움카드 | 재직자 국민내일배움카드 |
|------|-------------------|---------------------|
| 대상 | 실업자, 구직자 | 고용보험 가입 재직자 |
| 지원 한도 | 200만 원 | 300~500만 원 |
| 자부담 | 없음(일부 과정) | 15~55% |
| 사용 기간 | 1~2년 | 5년 |

재직자는 구직자보다 자부담이 생기지만 지원 한도가 훨씬 높고 유효기간도 길어서 장기적으로 여러 과정을 수강하기에 유리합니다.

## 직장인 국비지원 신청 시 자주 하는 실수

국비지원을 신청하면서 많은 분들이 혼동하거나 놓치는 부분들이 있습니다.

**자부담 비율 미확인**

과정마다 자부담 비율이 다릅니다. 훈련비가 100만 원인 과정에서 자부담 55%라면 실제 본인이 낼 금액은 55만 원입니다. HRD-Net에서 과정 선택 전에 자부담 금액을 반드시 확인하세요.

**출석 기준 미충족으로 수료 실패**

온라인 과정은 진도율 80% 이상, 오프라인 과정은 출석률 80% 이상을 충족해야 수료됩니다. 수료 실패 시 지원금 환수와 함께 다음 훈련 신청에 제한이 생길 수 있습니다.

**훈련기관 인지도만 보고 선택**

인기 훈련기관이라도 본인의 학습 목표, 스케줄, 이동 거리 등을 종합적으로 고려해야 합니다. HRD-Net에서 훈련기관 평가 등급(A~E)과 수료율을 함께 확인하는 것을 권장합니다.

직장인 국비지원은 알고 활용하면 연간 수백만 원의 자기계발 비용을 절약할 수 있는 훌륭한 제도입니다. HRD-Net에 가입해 본인에게 맞는 과정을 검색해보시기 바랍니다.
"""

TAGS = [
    "직장인국비지원", "재직자국비지원", "국민내일배움카드", "직장인교육비지원",
    "HRDNet", "재직자훈련", "직장인자격증국비", "국비지원교육과정",
    "직장인IT국비지원", "재직자계좌제", "직장인자기계발지원", "국비지원신청방법",
    "직장인데이터분석국비", "고용보험환급", "재직자훈련지원"
]

META_TITLE = "직장인국비지원 신청 방법과 교육과정 2026 비교 가이드"
META_DESC = "직장인도 국민내일배움카드로 최대 500만 원 국비지원을 받을 수 있습니다. 재직자 신청 방법, 자부담 비율, 인기 교육과정을 2026년 기준으로 안내합니다."

IMAGE_INFOS = [
    {
        "index": 1,
        "prompt": "Korean government office desk with training application documents, national voucher card, pen and official stamp, clean organized workspace, soft natural office lighting",
        "filename": "jikjangin-gukbi-1.jpg",
        "alt": "직장인 국비지원 신청 서류와 국민내일배움카드"
    },
    {
        "index": 2,
        "prompt": "HRD training course website on laptop screen, Korean adult learner studying online course, modern home office setup, warm desk lamp lighting",
        "filename": "jikjangin-gukbi-2.jpg",
        "alt": "HRD-Net 국비지원 교육과정 신청 화면"
    },
    {
        "index": 3,
        "prompt": "Korean professional development classroom setting, IT coding education, students at computers, modern educational facility, bright indoor lighting",
        "filename": "jikjangin-gukbi-3.jpg",
        "alt": "직장인 국비지원 IT 교육과정 수업 현장"
    },
]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def markdown_to_html(md_text: str, adsense_code: str, adsense_slot: str) -> str:
    """간단한 마크다운 → HTML 변환 (표, 볼드, 헤딩, 이미지 마커 포함)"""
    import re

    lines = md_text.split('\n')
    html_lines = []
    in_table = False
    table_lines = []

    def flush_table():
        nonlocal table_lines, in_table
        if not table_lines:
            return
        # 첫 줄: 헤더, 둘째 줄: 구분선, 나머지: 데이터
        rows = []
        for i, tl in enumerate(table_lines):
            if i == 1:  # 구분선 skip
                continue
            cells = [c.strip() for c in tl.strip().strip('|').split('|')]
            if i == 0:
                rows.append('<thead><tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr></thead>')
            else:
                rows.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
        html_lines.append('<table class="wp-block-table"><tbody>' + ''.join(rows) + '</tbody></table>')
        table_lines = []
        in_table = False

    adsense_html = f'''<!-- Adsense -->
<div class="adsense-wrap" style="margin:24px 0;">
<ins class="adsbygoogle" style="display:block" data-ad-client="{adsense_code}" data-ad-slot="{adsense_slot}" data-ad-format="auto" data-full-width-responsive="true"></ins>
<script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
</div>'''

    for line in lines:
        stripped = line.strip()

        # 표 처리
        if stripped.startswith('|'):
            if not in_table:
                in_table = True
            table_lines.append(stripped)
            continue
        elif in_table:
            flush_table()

        # 이미지 마커 (나중에 실제 이미지 src로 교체됨)
        img_match = re.match(r'\{\{이미지(\d+)\}\}', stripped)
        if img_match:
            n = img_match.group(1)
            html_lines.append(f'{{{{이미지{n}}}}}')
            continue

        # 애드센스
        if stripped == '[애드센스]':
            html_lines.append(adsense_html)
            continue

        # H2
        if stripped.startswith('## '):
            html_lines.append(f'<h2>{stripped[3:]}</h2>')
            continue

        # H3
        if stripped.startswith('### '):
            html_lines.append(f'<h3>{stripped[4:]}</h3>')
            continue

        # 순서 있는 목록
        ol_match = re.match(r'^\d+\.\s+(.*)', stripped)
        if ol_match:
            html_lines.append(f'<li>{ol_match.group(1)}</li>')
            continue

        # 순서 없는 목록
        if stripped.startswith('- '):
            html_lines.append(f'<li>{stripped[2:]}</li>')
            continue

        # 빈 줄
        if not stripped:
            html_lines.append('')
            continue

        # 일반 문단
        html_lines.append(f'<p>{stripped}</p>')

    if in_table:
        flush_table()

    result = '\n'.join(html_lines)

    # 볼드 처리
    result = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', result)

    return result


def upload_image_to_wp(filepath: str, alt: str) -> dict | None:
    """WordPress REST API로 이미지 업로드"""
    wp_api = f"{WP_URL}/wp-json/wp/v2/media"
    auth = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()

    p = Path(filepath)
    mime = "image/jpeg" if p.suffix.lower() in ('.jpg', '.jpeg') else "image/webp"

    with open(filepath, 'rb') as f:
        data = f.read()

    req = urllib.request.Request(
        wp_api,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Disposition": f'attachment; filename="{p.name}"',
            "Content-Type": mime,
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            return {
                "id": result.get("id"),
                "url": result.get("source_url"),
                "alt": alt,
            }
    except Exception as e:
        log(f"[WP 업로드 오류] {e}")
        return None


def save_wp_draft(title: str, content_html: str, tags: list, meta_title: str, meta_desc: str, featured_media_id: int = None) -> dict | None:
    """WordPress REST API로 draft 저장"""
    import json as _json

    wp_api = f"{WP_URL}/wp-json/wp/v2/posts"
    auth = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()

    payload = {
        "title": title,
        "content": content_html,
        "status": "draft",
        "tags": [],  # 태그 ID가 필요하므로 일단 빈 배열, 아래에서 생성
        "meta": {
            "rank_math_title": meta_title,
            "rank_math_description": meta_desc,
            "rank_math_focus_keyword": "직장인국비지원",
        }
    }

    if featured_media_id:
        payload["featured_media"] = featured_media_id

    # 태그 생성/조회
    tag_ids = []
    for tag_name in tags:
        tag_id = get_or_create_tag(tag_name, auth)
        if tag_id:
            tag_ids.append(tag_id)
    if tag_ids:
        payload["tags"] = tag_ids

    data = _json.dumps(payload).encode()
    req = urllib.request.Request(
        wp_api,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = _json.loads(resp.read().decode())
            return {
                "id": result.get("id"),
                "link": result.get("link"),
                "status": result.get("status"),
            }
    except Exception as e:
        log(f"[WP Draft 저장 오류] {e}")
        try:
            import traceback
            traceback.print_exc()
        except:
            pass
        return None


def get_or_create_tag(tag_name: str, auth: str) -> int | None:
    """태그 검색 후 없으면 생성, ID 반환"""
    import json as _json

    # 태그 검색
    search_url = f"{WP_URL}/wp-json/wp/v2/tags?search={urllib.parse.quote(tag_name)}&per_page=5"
    req = urllib.request.Request(search_url, headers={"Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            tags = _json.loads(resp.read().decode())
            for t in tags:
                if t.get("name") == tag_name:
                    return t["id"]
    except:
        pass

    # 태그 생성
    data = _json.dumps({"name": tag_name}).encode()
    req = urllib.request.Request(
        f"{WP_URL}/wp-json/wp/v2/tags",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            t = _json.loads(resp.read().decode())
            return t.get("id")
    except Exception as e:
        log(f"[태그 생성 오류] {tag_name}: {e}")
        return None


def main():
    log("=== 직장인국비지원 글 생성 시작 ===")

    # 1. 이미지 생성
    log("1단계: 이미지 생성 (Bing → Pollinations)")
    from image_router import generate_images_for_blog
    img_results = generate_images_for_blog(
        blog_id="baremi542",
        image_infos=IMAGE_INFOS,
        skip_webp=True,
        on_log=log,
        title=TITLE,
    )
    log(f"이미지 생성 결과: {len(img_results)}장 성공 — {list(img_results.keys())}")

    # 이미지를 WP에 업로드
    log("2단계: 이미지 WordPress 업로드")
    uploaded = {}  # index -> {id, url, alt}
    featured_media_id = None

    for info in IMAGE_INFOS:
        idx = info["index"]
        if idx not in img_results:
            log(f"  [이미지{idx}] 생성 실패 → 스킵")
            continue
        filepath = img_results[idx]
        log(f"  [이미지{idx}] 업로드 중: {filepath}")
        result = upload_image_to_wp(filepath, info["alt"])
        if result:
            uploaded[idx] = result
            log(f"  [이미지{idx}] 업로드 완료: {result['url']}")
            if idx == 1:
                featured_media_id = result["id"]
        else:
            log(f"  [이미지{idx}] 업로드 실패")
        time.sleep(1)

    # 3. 본문 HTML 변환
    log("3단계: 마크다운 → HTML 변환")
    adsense_code = os.getenv("ADSENSE_CODE", "ca-pub-1646757278810260")
    adsense_slot = os.getenv("ADSENSE_SLOT", "3141593954")
    content_html = markdown_to_html(BODY_MARKDOWN, adsense_code, adsense_slot)

    # 이미지 마커 교체
    import re
    for idx, img_data in uploaded.items():
        img_html = f'<figure class="wp-block-image"><img src="{img_data["url"]}" alt="{img_data["alt"]}" /></figure>'
        content_html = content_html.replace(f'{{{{이미지{idx}}}}}', img_html)

    # 남은 마커 제거
    content_html = re.sub(r'\{\{이미지\d+\}\}', '', content_html)

    # 4. WordPress Draft 저장
    log("4단계: WordPress Draft 저장")
    result = save_wp_draft(
        title=TITLE,
        content_html=content_html,
        tags=TAGS,
        meta_title=META_TITLE,
        meta_desc=META_DESC,
        featured_media_id=featured_media_id,
    )

    if result:
        log(f"=== Draft 저장 완료 ===")
        log(f"  ID: {result['id']}")
        log(f"  Status: {result['status']}")
        log(f"  Link: {result['link']}")

        # 결과 저장
        draft_data = {
            "blog_id": "baremi542",
            "keyword": "직장인국비지원",
            "title": TITLE,
            "status": "draft",
            "post_id": result["id"],
            "post_url": result["link"],
            "images_uploaded": len(uploaded),
            "created_at": datetime.now().isoformat(),
        }
        out_path = BASE_DIR / "drafts" / "baremi542_jikjangin_gukbi.json"
        out_path.write_text(json.dumps(draft_data, ensure_ascii=False, indent=2))
        log(f"  결과 저장: {out_path}")
    else:
        log("=== Draft 저장 실패 ===")

    # 본문 글자수 출력
    char_count = len(BODY_MARKDOWN.replace(' ', '').replace('\n', ''))
    log(f"본문 글자수(공백·줄바꿈 제외): {char_count}자")
    log(f"본문 총 글자수: {len(BODY_MARKDOWN)}자")

    return result


if __name__ == "__main__":
    main()
