"""
travel.baremi542.com (Blogspot) — 제주 우도 페리 자전거 렌트 당일치기 발행 스크립트
이미지: 사전 생성된 로컬 파일 사용, Picasa Web Albums로 업로드 후 URL 삽입
"""
import sys
import os
import re
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

BLOG_ID = "6036713839195958620"
KEYWORD = "제주 우도 페리 자전거 렌트 당일치기"

TITLE = "2026년 제주 우도 당일치기 — 페리 타고 자전거 렌트까지 한 번에 해결하는 법"

IMAGES_DIR = BASE_DIR / "images" / "blogspot_travel"

# 사전 생성된 이미지 파일
IMAGE_FILES = {
    1: str(IMAGES_DIR / "udo-ferry-1.jpg"),
    2: str(IMAGES_DIR / "udo-bicycle-2.jpg"),
    3: str(IMAGES_DIR / "udo-beach-3.jpg"),
    4: str(IMAGES_DIR / "udo-panorama-4.jpg"),
}

IMAGE_ALTS = {
    1: "성산항 페리 탑승 모습",
    2: "우도 자전거 렌트 매장",
    3: "우도 검멀레 해변 풍경",
    4: "우도 전경 파노라마",
}

TAGS = [
    "우도", "제주우도", "우도페리", "우도자전거", "우도당일치기",
    "성산항페리", "우도여행", "제주당일치기", "우도자전거렌트", "제주여행"
]

ADSENSE_PUB = "ca-pub-1646757278810260"
ADSENSE_SLOT = "3141593954"
ADSENSE_HTML = (
    f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_PUB}" crossorigin="anonymous"></script>'
    f'<ins class="adsbygoogle" style="display:block;text-align:center" data-ad-layout="in-article" data-ad-format="fluid" data-ad-client="{ADSENSE_PUB}" data-ad-slot="{ADSENSE_SLOT}"></ins>'
    '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>'
)

BODY_SECTIONS = [
    # (html_id, heading, body_text, after_adsense)
    {
        "img_idx": 1,
        "heading": "🚢 우도 가는 페리, 성산항에서 어떻게 타나요?",
        "content": """<p>우도로 들어가는 관문은 제주시 동쪽 끝에 위치한 성산항입니다. 제주 시내에서 버스를 이용하면 약 1시간, 렌터카로는 40분 정도 걸립니다.</p>

<p>성산항 매표소는 항구 입구 좌측에 있으며, 도착 후 현장에서 왕복 승선권을 구매하면 됩니다. 현지 검색 기준 2026년 현재 성인 왕복 요금은 약 8,000~10,000원대로 안내되고 있으나, 정확한 금액은 현장에서 확인하세요.</p>

<p>운항은 보통 하우목동항·천진항 두 곳을 기항하며, 성수기와 비수기에 따라 배 간격이 달라집니다. 성수기(7~8월)에는 15~30분 간격으로 자주 운항하므로 현장에서 대기 시간이 크게 길지 않습니다.</p>

<blockquote><p>💡 오전 첫 배(8시대)를 타면 사람이 가장 적고, 자전거 렌트 매장도 여유 있게 선택할 수 있습니다. 주말이라면 30분 전 도착을 권장합니다.</p></blockquote>""",
        "after_adsense": True,
    },
    {
        "img_idx": 2,
        "heading": "🚲 우도 자전거 렌트, 종류와 코스 선택법",
        "content": """<p>페리에서 내리면 항구 주변으로 자전거 대여점이 즐비합니다. 일반 자전거부터 전동 자전거(e-bike), 2인용 자전거까지 선택지가 다양합니다.</p>

<p>전동 자전거는 언덕이 있는 우도 서쪽 구간을 편하게 이동할 수 있어 가족 단위 방문객에게 인기입니다. 후기에 따르면 대여 요금은 1시간에 일반 자전거 5,000원, 전동 자전거 10,000~15,000원 선이 많으나 매장마다 차이가 있으니 현장에서 비교해 보세요.</p>

<p>우도 자전거 코스는 크게 두 가지로 나뉩니다. 해안 일주 코스(약 17km)는 섬 전체를 한 바퀴 돌며 우도봉, 검멀레 해변, 하고수동 해수욕장을 모두 담을 수 있는 루트입니다. 시간이 부족하다면 천진항~우도봉~하고수동 해수욕장을 연결하는 반일 코스(약 8km)도 충분히 만족스럽습니다.</p>

<blockquote><p>💡 자전거 반납 시간을 페리 출발 30분 전으로 맞추세요. 대여점이 항구 근처에 몰려 있어 반납 후 바로 탑승 줄에 합류할 수 있습니다.</p></blockquote>""",
        "after_adsense": False,
    },
    {
        "img_idx": 3,
        "heading": "🏖️ 우도에서 꼭 들르는 곳 — 검멀레 해변과 우도봉",
        "content": """<p>우도의 상징 중 하나는 검은 현무암 모래가 펼쳐진 검멀레 해변입니다. 일반 해수욕장과 달리 어두운 자갈 해변이 이국적인 분위기를 자아냅니다. 자전거로 접근이 가능하며, 해변 바로 옆에 주차 공간이 마련되어 있습니다.</p>

<p>우도봉(132m)은 섬에서 가장 높은 지점으로, 정상까지 걸어서 20분이면 오를 수 있습니다. 정상에 서면 제주 본섬 성산일출봉과 우도 해안선이 한눈에 내려다보입니다. 자전거는 아래 주차 공간에 세우고 도보로 오르는 방식이 일반적입니다.</p>

<p>우도 땅콩 아이스크림은 빠질 수 없는 간식입니다. 특산물인 땅콩으로 만든 소프트아이스크림이 현지에서 큰 인기를 얻고 있으며, 항구 주변 곳곳에서 구매할 수 있습니다. 후기에 따르면 한 개에 3,000~4,000원 선입니다.</p>

<blockquote><p>💡 검멀레 해변은 조류가 강한 날에는 입수가 제한되므로, 수영이 목적이라면 하고수동 해수욕장을 이용하세요.</p></blockquote>""",
        "after_adsense": False,
    },
    {
        "img_idx": 4,
        "heading": "🗓️ 우도 당일치기 추천 타임라인",
        "content": """<p>하루를 알차게 보내려면 이동 순서를 미리 정해두는 것이 핵심입니다. 아래는 현지 후기 기반 추천 동선입니다.</p>

<table border="1" style="border-collapse:collapse;width:100%;margin:16px 0">
<thead><tr>
<th style="padding:10px;background:#f0f4ff;text-align:left">시간</th>
<th style="padding:10px;background:#f0f4ff;text-align:left">행동</th>
</tr></thead>
<tbody>
<tr><td style="padding:10px">08:00</td><td style="padding:10px">성산항 도착, 왕복 승선권 구매</td></tr>
<tr><td style="padding:10px">08:30</td><td style="padding:10px">첫 배 탑승 (약 15분 소요)</td></tr>
<tr><td style="padding:10px">08:45</td><td style="padding:10px">천진항 도착, 자전거 렌트</td></tr>
<tr><td style="padding:10px">09:00~11:30</td><td style="padding:10px">해안 일주 코스 — 검멀레 해변, 우도봉</td></tr>
<tr><td style="padding:10px">11:30~13:00</td><td style="padding:10px">점심 (우도 땅콩 아이스크림 포함)</td></tr>
<tr><td style="padding:10px">13:00~14:00</td><td style="padding:10px">하고수동 해수욕장 또는 산호해수욕장 산책</td></tr>
<tr><td style="padding:10px">14:00</td><td style="padding:10px">자전거 반납</td></tr>
<tr><td style="padding:10px">14:30</td><td style="padding:10px">성산항 복귀 페리 탑승</td></tr>
</tbody>
</table>

<p>오후에 제주 본섬 성산일출봉(유네스코 세계자연유산)을 연계 관광하는 일정도 많이 선택합니다. 성산항에서 도보 10분 거리에 있어 당일치기 마무리로 안성맞춤입니다.</p>

<blockquote><p>💡 성수기 오후 배는 혼잡합니다. 14:00~15:00 사이 배표를 미리 확인하거나, 막배 시간을 사전에 체크해 두세요.</p></blockquote>""",
        "after_adsense": False,
    },
]

FAQ_HTML = """<h2>❓ 자주 묻는 질문</h2>

<p><strong>Q. 우도에 차를 가져갈 수 있나요?</strong><br>
우도는 환경보호 특별구역으로 외부 차량 반입이 제한됩니다. 현지 전기차·전동 카트 대여를 이용하거나 자전거로 이동하는 방식이 일반적입니다.</p>

<p><strong>Q. 우도 페리는 예약이 필요한가요?</strong><br>
현지 검색 기준 2026년 현재, 일반 탑승객(승선만 하는 경우)은 현장 구매가 가능합니다. 단, 성수기 주말에는 줄이 길어질 수 있으므로 30~60분 일찍 도착하길 권장합니다.</p>

<p><strong>Q. 겨울에도 우도 당일치기가 가능한가요?</strong><br>
겨울철에도 운항은 하지만 날씨와 파고에 따라 결항되는 날이 있습니다. 출발 전날 제주 우도 페리 운항 현황을 현지 해운사 공식 안내를 통해 반드시 확인하세요. 방한 준비도 필수입니다.</p>

<p><strong>Q. 자전거를 못 타도 우도 관광이 가능한가요?</strong><br>
가능합니다. 우도 내부에서는 전동 카트(버기카)나 소형 전기차를 대여할 수 있으며, 섬 내 순환 버스도 운행됩니다. 걷기를 좋아한다면 항구 주변과 해안도로도 도보 관광이 충분히 즐겁습니다.</p>"""


def image_to_base64_tag(img_path: str, alt: str, max_w: int = 640, quality: int = 65) -> str:
    """이미지를 base64 data URI로 변환 후 <img> 태그 반환."""
    from PIL import Image
    import io
    import base64

    img = Image.open(img_path)
    img.thumbnail((max_w, int(max_w * 0.75)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    return (
        f'<figure style="text-align:center;margin:16px 0">'
        f'<img src="data:image/jpeg;base64,{b64}" alt="{alt}" '
        f'style="max-width:100%;height:auto;border-radius:8px;" />'
        f'</figure>'
    )


def build_html(image_tags: dict) -> str:
    """섹션과 이미지 태그로 최종 HTML 조립."""
    parts = []

    # 핵심 요약
    parts.append("""<div style="background:#f8f9fa;border-left:4px solid #4a90d9;padding:16px;margin-bottom:24px;border-radius:4px">
<p><strong>💡 핵심 요약</strong></p>
<ul>
<li>우도는 제주 성산항에서 페리로 15분 거리, 당일치기로 충분히 즐길 수 있습니다.</li>
<li>자전거 렌트는 하우목동항·천진항 모두 가능하며, 현지 검색 기준 1~2시간 코스가 가장 인기입니다.</li>
<li>오전 8~9시 첫 배를 타면 여유롭게 한 바퀴를 돌고 오후에 복귀할 수 있습니다.</li>
</ul>
</div>""")

    for i, section in enumerate(BODY_SECTIONS):
        idx = section["img_idx"]
        parts.append(f'<h2>{section["heading"]}</h2>')

        # 이미지 (base64 태그)
        if idx in image_tags:
            parts.append(image_tags[idx])

        parts.append(section["content"])

        # 애드센스: 첫 번째 섹션 뒤에 삽입
        if section.get("after_adsense"):
            parts.append(ADSENSE_HTML)

    # FAQ
    parts.append(FAQ_HTML)

    return "\n".join(parts)


def main():
    print(f"[시작] travel.baremi542.com 발행: {TITLE}")

    # 1. 로컬 이미지 파일 확인
    missing = [idx for idx, fp in IMAGE_FILES.items() if not Path(fp).exists()]
    if missing:
        print(f"[오류] 이미지 파일 없음: {missing}")
        raise Exception(f"이미지 파일 없음: {missing}")
    print(f"[이미지] 로컬 파일 {len(IMAGE_FILES)}장 확인 완료")

    # 2. 썸네일에 제목 오버레이 적용
    try:
        from image_router import add_title_overlay
        add_title_overlay(IMAGE_FILES[1], TITLE, blog_id="triplog", on_log=print)
    except Exception as e:
        print(f"[썸네일] 오버레이 실패 (무시): {e}")

    # 3. 이미지를 base64 data URI로 변환
    print("[이미지] base64 변환 중...")
    image_tags = {}
    for idx, img_path in IMAGE_FILES.items():
        if Path(img_path).exists():
            alt = IMAGE_ALTS.get(idx, f"이미지{idx}")
            tag = image_to_base64_tag(img_path, alt, max_w=640, quality=65)
            image_tags[idx] = tag
            print(f"  [{idx}] 변환 완료")
        else:
            print(f"  [{idx}] 파일 없음: {img_path}")

    print(f"[이미지] 변환 완료: {len(image_tags)}장")

    if len(image_tags) < 3:
        print(f"[경고] 이미지 {len(image_tags)}장만 확보됨 (최소 3장 필요)")

    # 4. HTML 조립
    print("[변환] HTML 조립...")
    html_content = build_html(image_tags)

    # 6. 검수
    print("[검수] 시작...")
    errors = []

    # 마크다운 잔재
    md_residues = re.findall(r'(?:^#{1,6} |\*\*)', html_content, re.MULTILINE)
    if md_residues:
        errors.append(f"마크다운 잔재 의심: {md_residues[:3]}")

    # 내부 마커
    for marker in ['[검증 필요]', '[출처 필요]', '{{이미지']:
        if marker in html_content:
            errors.append(f"내부 마커: {marker}")

    # 글자수
    text_only = re.sub(r'<[^>]+>', '', html_content)
    char_count = len(text_only.replace(' ', '').replace('\n', ''))
    print(f"[검수] 글자수: {char_count}자")
    if char_count < 1700:
        errors.append(f"글자수 부족: {char_count}자")

    # 이미지 수
    img_count = html_content.count('data:image/')
    print(f"[검수] 이미지 수: {img_count}장")
    if img_count < 3:
        errors.append(f"이미지 부족: {img_count}장")

    if errors:
        print(f"[검수] 경고: {errors}")
    else:
        print("[검수] 통과!")

    # 치명적 오류만 중단
    fatal = [e for e in errors if '마커' in e]
    if fatal:
        raise Exception(f"치명적 검수 오류: {fatal}")

    # 7. 발행 (Draft → Publish 방식)
    print("[발행] Draft 생성 후 Publish...")
    import urllib.request as _ur
    import urllib.error as _ue

    from blogger_api import _inject_adsense, _load_env
    from gsc_indexing import _get_access_token
    _env = _load_env()
    html_content = _inject_adsense(html_content, _env)
    _token = _get_access_token()

    _body = {"title": TITLE, "content": html_content, "labels": TAGS}
    _draft_url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/?isDraft=true"
    _data = json.dumps(_body).encode("utf-8")
    post_id = None

    for attempt in range(1, 4):
        _req = _ur.Request(_draft_url, data=_data, headers={
            "Authorization": f"Bearer {_token}", "Content-Type": "application/json"
        }, method="POST")
        try:
            _resp = json.loads(_ur.urlopen(_req, timeout=60).read())
            post_id = _resp.get("id", "")
            print(f"[발행] Draft 생성 성공: {post_id}")
            break
        except _ue.HTTPError as e:
            print(f"[발행] Draft 실패 {e.code} (시도 {attempt}/3)")
            if attempt < 3:
                time.sleep(15)
        except Exception as e:
            print(f"[발행] Draft 오류: {e}")
            if attempt < 3:
                time.sleep(15)

    if not post_id:
        reason = "Draft 생성 3회 실패"
        tg_msg = (
            f"⚠️ 오류 발생\n"
            f"작업: travel.baremi542.com 발행\n"
            f"오류: {reason}\n조치: 스크립트 종료"
        )
        os.system(f'python3 /Users/hana/Downloads/blog-automation-v2/tg_send.py "{tg_msg}"')
        raise Exception(reason)

    _pub_api = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/{post_id}/publish"
    _pub_req = _ur.Request(_pub_api, data=b"", headers={
        "Authorization": f"Bearer {_token}", "Content-Length": "0"
    }, method="POST")
    try:
        _pub_resp = json.loads(_ur.urlopen(_pub_req, timeout=30).read())
        pub_url = _pub_resp.get("url", "")
        pub_time = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[완료] 발행 성공!")
        print(f"  URL: {pub_url}")
        print(f"  시각: {pub_time}")

        # 8. 텔레그램 보고
        correction_text = "\n- ".join(errors) if errors else "이상 없음"
        tg_msg = (
            f"✅ 발행 완료\n"
            f"블로그: travel.baremi542.com (Blogspot)\n"
            f"제목: {TITLE}\n"
            f"발행시각: {pub_time}\n\n"
            f"🔧 검수 중 수정사항:\n- {correction_text}"
        )
        os.system(f'python3 /Users/hana/Downloads/blog-automation-v2/tg_send.py "{tg_msg}"')
        print("[텔레그램] 보고 완료")
    except _ue.HTTPError as e:
        reason = f"Publish 실패 {e.code}"
        tg_msg = (
            f"⚠️ 오류 발생\n"
            f"작업: travel.baremi542.com 발행\n"
            f"오류: {reason}\n조치: Draft {post_id} 수동 발행 필요"
        )
        os.system(f'python3 /Users/hana/Downloads/blog-automation-v2/tg_send.py "{tg_msg}"')
        raise Exception(reason)


if __name__ == "__main__":
    main()
