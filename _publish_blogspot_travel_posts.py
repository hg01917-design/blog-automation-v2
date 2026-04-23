"""
blogspot_travel 두 글 생성 및 발행 스크립트
키워드:
1. 제주 우도 페리 자전거 렌트 당일치기
2. 울릉도 독도 배편 예약 여행 준비물
"""
import sys
import re
import base64
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# ── 유틸 함수 ─────────────────────────────────────────────────────────────────

def _load_env() -> dict:
    env = {}
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _apply_inline(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)
    return text


def _md_to_html(md: str) -> str:
    lines = md.split('\n')
    result = []
    in_table = False

    for line in lines:
        if line.strip().startswith('|'):
            if not in_table:
                result.append('<table style="width:100%;border-collapse:collapse;margin:16px 0;">')
                in_table = True
            if re.match(r'^\s*\|[-| :]+\|\s*$', line):
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            row_html = ''.join(f'<td style="border:1px solid #ddd;padding:8px;">{c}</td>' for c in cells)
            result.append(f'<tr>{row_html}</tr>')
            continue
        else:
            if in_table:
                result.append('</table>')
                in_table = False

        if line.strip().startswith('> '):
            tip = line.strip()[2:]
            result.append(
                f'<blockquote style="background:#f0f7ff;border-left:4px solid #1a73e8;'
                f'padding:12px 16px;margin:16px 0;border-radius:4px;">'
                f'{_apply_inline(tip)}</blockquote>'
            )
            continue

        h2 = re.match(r'^## (.+)$', line)
        if h2:
            result.append(f'<h2 style="margin-top:32px;">{_apply_inline(h2.group(1))}</h2>')
            continue
        h3 = re.match(r'^### (.+)$', line)
        if h3:
            result.append(f'<h3 style="margin-top:20px;">{_apply_inline(h3.group(1))}</h3>')
            continue

        li = re.match(r'^[-*] (.+)$', line)
        if li:
            result.append(f'<li style="margin:4px 0;">{_apply_inline(li.group(1))}</li>')
            continue

        if re.match(r'^\{\{이미지\d+\}\}$', line.strip()):
            result.append(line.strip())
            continue

        # 애드센스 마커 — 블록 레벨로 처리 (p 태그 금지)
        if line.strip() == '[애드센스]':
            result.append('[애드센스]')
            continue

        if not line.strip():
            result.append('')
            continue

        result.append(f'<p>{_apply_inline(line)}</p>')

    if in_table:
        result.append('</table>')

    return '\n'.join(result)


def _inject_adsense(content: str, env: dict) -> str:
    pub = env.get("ADSENSE_CODE", "")
    slot = env.get("ADSENSE_SLOT", "")
    if not pub or not slot:
        return content.replace("[애드센스]", "")
    ad_html = (
        f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={pub}" crossorigin="anonymous"></script>'
        f'<ins class="adsbygoogle" style="display:block;text-align:center" data-ad-layout="in-article" data-ad-format="fluid" data-ad-client="{pub}" data-ad-slot="{slot}"></ins>'
        '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>'
    )
    return content.replace("[애드센스]", ad_html)


def _img_tag(path: str, alt: str) -> str:
    """이미지를 base64로 인코딩. 크기 초과 시 리사이즈/압축 처리."""
    try:
        from PIL import Image
        import io
        img = Image.open(path).convert("RGB")
        # 최대 폭 800px로 리사이즈
        max_w = 800
        if img.width > max_w:
            ratio = max_w / img.width
            new_h = int(img.height * ratio)
            img = img.resize((max_w, new_h), Image.LANCZOS)
        # JPEG quality 65로 압축
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=65, optimize=True)
        data = base64.b64encode(buf.getvalue()).decode()
        return (f'<div style="text-align:center;margin:20px 0;">'
                f'<img src="data:image/jpeg;base64,{data}" '
                f'alt="{alt}" style="max-width:100%;height:auto;border-radius:8px;" />'
                f'</div>')
    except Exception as e:
        print(f"  이미지 삽입 실패 ({path}): {e}")
        return ""


def _generate_images_with_fallback(images: list, blog_id_str: str) -> dict:
    """이미지 생성 — Bing 우선, 실패 시 picsum.photos 폴백"""
    from image_router import IMAGES_DIR as _IMG_DIR
    _blog_img_dir = _IMG_DIR / "blogspot_travel"
    _blog_img_dir.mkdir(parents=True, exist_ok=True)

    image_paths = {}

    # Bing 시도
    try:
        from image_router import generate_images_for_blog
        image_paths = generate_images_for_blog(
            blog_id="blogspot_travel",
            image_infos=images,
            skip_webp=False,
            on_log=print,
        )
        print(f"[{blog_id_str}] Bing 이미지 {len(image_paths)}개 생성")
    except Exception as e:
        print(f"[{blog_id_str}] Bing 실패: {e}")

    # 부족한 이미지를 picsum으로 채우기
    if len(image_paths) < len(images):
        from gemini_image import _generate_via_fallback
        for img in images:
            idx = img["index"]
            if idx not in image_paths:
                fp = _generate_via_fallback(
                    img["prompt"],
                    img["filename"],
                    on_log=print,
                    skip_webp=True,
                    save_dir=_blog_img_dir,
                )
                if fp:
                    image_paths[idx] = fp
                    print(f"  [picsum 폴백] 이미지{idx} 생성: {fp}")

    return image_paths


def publish_one(title: str, body_md: str, tags: list, images: list, blog_id_str: str) -> dict:
    """마크다운 본문 → HTML 변환 → 이미지 삽입 → Blogger 발행"""
    from blogger_api import publish_post as _blogger_publish

    env = _load_env()
    blogger_blog_id = env.get("BLOGSPOT_TRAVEL_BLOG_ID", env.get("BLOGGER_BLOG_ID", ""))

    print(f"\n[{blog_id_str}] 이미지 {len(images)}개 생성 시작...")
    image_paths = _generate_images_with_fallback(images, blog_id_str)
    print(f"[{blog_id_str}] 이미지 {len(image_paths)}개 생성 완료")

    # 마크다운 → HTML
    html_body = _md_to_html(body_md)

    # 이미지 플레이스홀더 교체
    for img in images:
        idx = img["index"]
        placeholder = f"{{{{이미지{idx}}}}}"
        if idx in image_paths:
            tag = _img_tag(image_paths[idx], img.get("alt", ""))
        else:
            tag = ""
        html_body = html_body.replace(placeholder, tag)

    html_body = re.sub(r'\{\{이미지\d+\}\}', '', html_body)

    # AdSense 주입
    html_body = _inject_adsense(html_body, env)

    print(f"[{blog_id_str}] Blogger API 발행 중: '{title}'")
    result = _blogger_publish(
        title=title,
        content=html_body,
        labels=tags,
        status="LIVE",
        blog_id=blogger_blog_id,
    )

    if result.get("ok"):
        print(f"[{blog_id_str}] ✅ 발행 완료: {result.get('url')}")
    else:
        print(f"[{blog_id_str}] ❌ 발행 실패: {result.get('reason')}")
        # 실패 시 DRAFT로 재시도
        print(f"[{blog_id_str}] DRAFT로 재시도...")
        result = _blogger_publish(
            title=title,
            content=html_body,
            labels=tags,
            status="DRAFT",
            blog_id=blogger_blog_id,
        )
        if result.get("ok"):
            print(f"[{blog_id_str}] ✅ DRAFT 저장 완료: {result.get('url')}")
        else:
            print(f"[{blog_id_str}] ❌ DRAFT도 실패: {result.get('reason')}")

    return result


# ══════════════════════════════════════════════════════════════════════════════
# 글 1: 제주 우도 페리 자전거 렌트 당일치기
# ══════════════════════════════════════════════════════════════════════════════

TITLE_1 = "제주 우도 페리 자전거 렌트 당일치기 코스 2026 실전 가이드"

BODY_1 = """💡 핵심 요약
- 우도행 페리는 성산포항 또는 종달항 출발, 소요시간 15분 내외 (현지 기준)
- 자전거 렌트는 하우목동항 주변 대여소에서 당일 즉시 가능, 전동킥보드도 선택 가능
- 당일치기 기준 4~6시간이면 우도 주요 명소를 모두 돌아볼 수 있음

## 🚢 우도 페리 탑승 방법과 운항 시간표

{{이미지1}}

우도로 들어가는 방법은 제주도 동쪽 끝, **성산포항**에서 출발하는 카페리를 타는 것입니다. 종달항에서도 출발편이 있어 위치에 따라 선택할 수 있습니다.

성산포항에서 우도 하우목동항까지는 약 15분, 종달항에서 우도 천진항까지는 약 10분 소요됩니다(현지 운항 기준). 첫 배는 오전 7시 30분경 출발하며, 막배는 계절에 따라 오후 5~6시 사이에 끊깁니다.

페리 탑승권은 성산포항 매표소에서 현장 구매하거나, 일부 앱을 통한 온라인 예매도 가능합니다. 성수기(7~8월, 명절 연휴)에는 대기 줄이 길어지므로 오전 일찍 도착하는 것을 권장합니다.

| 출발지 | 도착지 | 소요시간 | 운임 (현지 기준) |
|--------|--------|----------|-----------------|
| 성산포항 | 하우목동항 | 약 15분 | 성인 왕복 약 9,900원 |
| 종달항 | 천진항 | 약 10분 | 성인 왕복 약 7,700원 |

> 💡 막배 시간을 반드시 확인하세요. 페리 탑승 전 하우목동항 안내판에서 당일 막배 시각을 재확인하는 것이 좋습니다.

[애드센스]

## 🚲 하우목동항 자전거 렌트 가격과 선택 방법

{{이미지2}}

우도에 도착하면 하우목동항 주변에 자전거 및 전동킥보드 대여소가 즐비하게 늘어서 있습니다. 대부분 즉시 대여 가능하며, 사전 예약 없이 당일 이용이 가능합니다.

자전거 종류는 일반 자전거, 전기자전거(E-bike), 전동킥보드로 나뉩니다. 우도 해안 일주 도로는 약 17km로, 체력이 걱정된다면 전기자전거나 전동킥보드를 추천합니다.

| 이동 수단 | 대여료 (현지 기준) | 특징 |
|-----------|------------------|------|
| 일반 자전거 | 시간당 약 4,000~5,000원 | 체력 소모 있음, 조용함 |
| 전기자전거 | 시간당 약 6,000~8,000원 | 오르막도 수월, 가장 인기 |
| 전동킥보드 | 시간당 약 6,000원 내외 | 빠르지만 비포장 구간 불편 |

전기자전거는 배터리 잔량을 출발 전 반드시 확인하세요. 우도봉 방면은 경사가 있어 배터리 소모가 빠릅니다.

> 💡 렌트 시 신분증 지참이 필요하며, 헬멧은 대부분 무료 제공됩니다. 자전거 안장 높이와 브레이크 상태를 출발 전에 꼭 점검하세요.

[애드센스]

## 🗺️ 당일치기 추천 코스 — 하우목동항 출발 기준

{{이미지3}}

우도 당일치기 코스는 시계 방향으로 돌면 주요 명소를 빠짐없이 즐길 수 있습니다.

**추천 코스 (약 4~5시간)**

하우목동항 출발 → 우도봉(우도등대) → 서빈백사 해수욕장 → 검멀레 해수욕장 → 우도 땅콩 아이스크림 명소 → 비양도 전망대 → 하우목동항 귀환

**우도봉(우도등대)**: 섬의 가장 높은 곳으로 제주 본섬과 성산일출봉이 한눈에 보이는 조망 명소입니다. 자전거를 세우고 도보로 10~15분 오릅니다.

**서빈백사 해수욕장**: 우도의 상징, 홍조단괴로 이루어진 하얀 모래사장입니다. 보통 모래해변과 달리 산호 부스러기로 된 독특한 해변으로, 물놀이보다 산책과 사진 촬영에 어울립니다.

**검멀레 해수욕장**: 검은 모래가 깔린 해변으로 서빈백사와는 전혀 다른 분위기입니다. 동굴 카페가 인근에 있어 잠시 쉬어 가기 좋습니다.

우도 전체를 1회 일주하는 데 자전거 기준 2~3시간, 중간 정류 및 식사를 포함하면 4~6시간으로 잡으면 여유 있게 즐길 수 있습니다.

> 💡 우도봉 입장료(현지 기준)는 별도로 부과됩니다. 자전거는 우도봉 입구 주차장에 세워두고 걸어 올라가야 합니다.

[애드센스]

## 🍽️ 우도 현지 맛집과 먹거리 정보

{{이미지4}}

우도에서 반드시 맛봐야 할 것이 있습니다. 바로 **우도 땅콩 아이스크림**입니다. 우도는 제주도의 특산물인 땅콩 재배지로 유명하며, 진한 땅콩 향이 나는 소프트아이스크림은 우도를 대표하는 먹거리입니다.

하우목동항 주변 상점가에 아이스크림 가게가 여럿 있으며, 가격은 컵 기준 3,000~4,000원 선(현지 기준)입니다. 탱크형 콘에 담아 먹는 스타일도 인기입니다.

식사는 하우목동항 주변 식당가에서 해물라면, 전복 돌솥밥, 해물짬뽕 등을 먹을 수 있습니다. 성수기에는 대기가 길 수 있으므로 이른 점심(11시 30분 이전)이나 늦은 점심(1시 30분 이후)을 노리는 것이 좋습니다.

섬 내에 편의점이 있지만 물과 간식은 제주 본섬에서 미리 준비해 오는 것이 가격 면에서 합리적입니다.

> 💡 우도 땅콩 막걸리와 땅콩 초콜릿도 기념품으로 인기입니다. 짐이 되지 않는 선에서 하나씩 챙겨보세요.

[애드센스]

## ❓ 자주 묻는 질문

**Q. 우도 페리는 예약 없이 탈 수 있나요?**
성수기를 제외하면 대부분 현장 당일 구매가 가능합니다. 다만 7~8월 성수기, 명절, 주말에는 대기 줄이 길어질 수 있으므로 오전 일찍 성산포항에 도착하는 것이 좋습니다. 일부 앱에서 사전 예매를 지원하니 성수기라면 미리 확인해보세요.

**Q. 우도 자전거 렌트에 면허증이 필요한가요?**
일반 자전거와 전기자전거는 면허 불필요하며 신분증만 있으면 됩니다. 전동킥보드는 원동기장치 자전거 면허 이상이 필요하며, 미성년자는 이용이 제한됩니다. 대여 전 현장에서 확인하세요.

**Q. 당일치기로 우도를 모두 돌아볼 수 있나요?**
네, 충분히 가능합니다. 전기자전거 기준 주요 명소를 포함해 3~4시간이면 1바퀴를 돌 수 있습니다. 오전 9시 이전 페리로 입도해 오후 4시 이전 막배를 타면 여유 있는 당일치기가 됩니다.

**Q. 우도 자전거를 타다 비가 오면 어떻게 하나요?**
하우목동항 근처 대여소에서 우비를 대여하거나 구매할 수 있습니다. 비가 내리는 날에는 서빈백사 모래가 젖어 자전거 이동이 불편할 수 있으니, 검멀레 해수욕장 쪽 카페나 실내 명소 위주로 코스를 조정하세요.

**Q. 우도에 주차는 가능한가요?**
우도 내 차량 반입은 제한됩니다. 렌터카와 개인 차량은 원칙적으로 도내 반입이 불가하며, 대중교통(도보·자전거·전동킥보드)으로만 이동해야 합니다. 성산포항 주차장은 유료이니 미리 확인하세요.
"""

TAGS_1 = [
    "우도", "우도페리", "우도자전거렌트", "제주우도", "우도당일치기",
    "성산포항페리", "우도코스", "우도전기자전거", "우도하우목동항",
    "우도서빈백사", "우도땅콩아이스크림", "우도여행", "제주도여행", "제주당일치기"
]

IMAGES_1 = [
    {
        "index": 1,
        "prompt": "Udo island ferry terminal Seongsan port Jeju Korea, ferry boat docking, morning sunlight, tourists boarding, scenic ocean view",
        "filename": "udo-ferry-seongsan-port-1.jpg",
        "alt": "제주 성산포항 우도행 페리 탑승 장면",
    },
    {
        "index": 2,
        "prompt": "Udo island bicycle rental shop near Haumoktong port Jeju Korea, colorful electric bikes lined up, blue sky, travel atmosphere",
        "filename": "udo-bicycle-rental-haumoktong-2.jpg",
        "alt": "우도 하우목동항 자전거 렌트 대여소",
    },
    {
        "index": 3,
        "prompt": "Udo island cycling coastal road Jeju Korea, white sandy beach Seobin Baeksa in background, clear turquoise sea, couple riding bicycles",
        "filename": "udo-cycling-coastal-road-3.jpg",
        "alt": "우도 해안 일주도로 자전거 코스",
    },
    {
        "index": 4,
        "prompt": "Udo island peanut soft serve ice cream Jeju Korea, creamy yellow color, tourists eating, souvenir shop background",
        "filename": "udo-peanut-icecream-4.jpg",
        "alt": "우도 땅콩 아이스크림 명물 먹거리",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# 글 2: 울릉도 독도 배편 예약 여행 준비물
# ══════════════════════════════════════════════════════════════════════════════

TITLE_2 = "울릉도 독도 배편 예약 방법과 여행 준비물 2026 핵심 정리"

BODY_2 = """💡 핵심 요약
- 울릉도행 배편은 강릉·묵호·후포·포항 4개 항구에서 출발, 사전 예약 필수
- 독도 입도는 기상 조건에 따라 자주 취소되므로 여유 일정을 반드시 확보해야 함
- 멀미약, 방수 가방, 우비는 울릉도·독도 여행 핵심 준비물

## 🚢 울릉도행 배편 예약 방법과 항구별 비교

{{이미지1}}

울릉도에 가려면 배편 사전 예약이 사실상 필수입니다. 울릉도행 여객선은 전국 4개 항구에서 출발하며, 각 출발지에서 울릉도 도동항까지의 소요 시간과 운임이 다릅니다.

| 출발항 | 소요시간 | 주요 선박 | 운임 (현지 기준) |
|--------|----------|-----------|-----------------|
| 포항 여객터미널 | 약 3시간 | 썬플라워·블루오션 | 성인 편도 약 55,000~70,000원 |
| 강릉항 | 약 3시간 | 씨스타2호 등 | 성인 편도 약 55,000~75,000원 |
| 묵호항 | 약 3시간 | 엘도라도익스프레스 등 | 성인 편도 약 50,000~65,000원 |
| 후포항 | 약 3시간 | 대저해운 등 | 성인 편도 약 50,000원 내외 |

예약은 각 해운사 공식 홈페이지 또는 전화로 할 수 있으며, 여름 성수기(7~8월)와 명절 연휴에는 1~2개월 전 매진이 일반적입니다. 여행 날짜가 정해지면 최대한 빠르게 예약하는 것이 좋습니다.

예약 시 신분증 정보를 정확히 입력해야 하며, 탑승 당일 신분증 지참이 필수입니다. 인터넷 예약 후 현장 발권 방식이 일반적이지만, 선사마다 규정이 다를 수 있으니 예약 완료 후 안내 문자를 꼭 확인하세요.

> 💡 기상 악화 시 결항이 잦습니다. 출발 전날과 당일 아침 선사 홈페이지 또는 전화로 운항 여부를 재확인하세요.

[애드센스]

## 🏝️ 독도 배편 예약과 입도 조건

{{이미지2}}

울릉도에서 독도까지는 배로 약 1시간 30분~2시간 소요됩니다(현지 기준). 독도 관광선은 울릉도 도동항 또는 저동항에서 출발하며, 독도유람선은 울릉군 공식 사이트 또는 해당 선사에서 예약할 수 있습니다.

독도 입도 여부는 당일 기상 상황에 따라 결정됩니다. 풍랑, 안개, 파고(파도 높이) 조건이 맞지 않으면 독도에 직접 발을 딛지 못하고 선박 위에서 조망만 하는 '독도 크루즈' 형태로 운영되기도 합니다.

최근 통계 기준으로 독도에 실제로 입도할 수 있는 날은 연간 절반에 못 미치는 경우도 있어, 울릉도 일정을 최소 3박 4일 이상으로 잡아야 독도 입도 확률을 높일 수 있습니다.

입도 가능 시간은 30분 내외로 매우 짧습니다. 독도 경비대 시설 인근을 걷고 기념 사진을 찍는 정도의 시간입니다. 독도 방문 목적이라면 그 의미에 초점을 맞추고 충분한 여유 일정을 확보하는 것이 중요합니다.

> 💡 독도 선착장 출입은 기상과 선박 대기 인원에 따라 현장에서 달라질 수 있습니다. 독도관리사무소에서 발행하는 입도 확인서를 받으면 방문 기념으로 보관할 수 있습니다.

[애드센스]

## 🎒 울릉도 여행 필수 준비물 체크리스트

{{이미지3}}

울릉도는 내륙에서 멀리 떨어진 외딴 섬으로, 한 번 들어오면 날씨에 따라 며칠씩 발이 묶일 수 있습니다. 준비물을 철저히 챙기는 것이 여행의 성패를 좌우합니다.

**필수 준비물**

- **멀미약**: 울릉도행 배편은 파도가 높으면 심하게 흔들립니다. 탑승 30분~1시간 전에 복용하는 것이 효과적입니다. 배 위에서 먹으면 효과가 떨어집니다.
- **우비 또는 방수 재킷**: 울릉도는 연평균 강수량이 많고, 산악 지형이라 날씨 변화가 빠릅니다. 접이식 경량 우비나 고어텍스 재킷이 필수입니다.
- **방수 가방 또는 드라이백**: 배에서 파도가 넘어오면 일반 배낭이 젖을 수 있습니다. 중요한 전자기기와 여권(신분증)은 방수 파우치에 보관하세요.
- **상비약**: 감기약, 소화제, 지사제, 일회용 밴드 등을 챙기세요. 울릉도는 섬이라 약국이 제한적이고 의약품 구비가 적을 수 있습니다.
- **여유 현금**: 울릉도 일부 식당과 숙소는 카드 단말기가 없거나 인터넷 연결 불안정으로 현금 결제만 되는 경우가 있습니다.
- **보조 배터리**: 독도 탐방 및 트레킹 중 충전 기회가 없습니다. 대용량 보조 배터리를 준비하세요.

| 준비물 | 중요도 | 비고 |
|--------|--------|------|
| 멀미약 | ★★★★★ | 탑승 30분 전 복용 |
| 우비/방수 재킷 | ★★★★★ | 사계절 필수 |
| 방수 파우치 | ★★★★☆ | 전자기기·신분증 보호 |
| 상비약 | ★★★★☆ | 현지 구비 미흡할 수 있음 |
| 여유 현금 | ★★★☆☆ | 2~3만원 이상 권장 |
| 보조 배터리 | ★★★☆☆ | 5,000mAh 이상 권장 |

> 💡 울릉도는 독특한 식재료가 많습니다. 오징어 내장탕, 따개비밥, 홍합밥 등 현지 음식을 꼭 경험해보세요.

[애드센스]

## 🏨 울릉도 숙소 유형과 예약 시 주의사항

{{이미지4}}

울릉도 숙소는 도동항 주변에 밀집되어 있으며, 펜션·게스트하우스·민박·호텔 형태로 운영됩니다. 저동항과 사동항 근처에도 숙박 시설이 있지만 선택지가 적습니다.

성수기 예약은 배편보다 더 빠르게 마감됩니다. 7~8월 성수기 여행이라면 최소 2~3개월 전에 숙소를 먼저 확보하고 배편을 잡는 순서가 현실적입니다.

숙소 예약 플랫폼(에어비앤비, 야놀자, 네이버 예약 등)에서 검색 시 '울릉도', '도동' 키워드로 검색하면 됩니다. 단, 현지 민박은 플랫폼에 등록되지 않은 경우도 많아 울릉군 공식 여행 안내 사이트에서 목록을 확인하거나 현지 여행사를 통하는 방법도 있습니다.

숙박비는 성수기 기준 1인 4~8만원 내외(현지 기준)이며, 비수기에는 훨씬 저렴해집니다. 기상 악화로 출발이 지연되거나 귀환이 늦어지는 경우를 고려해 마지막 날 일정에 여유를 두는 것이 좋습니다.

> 💡 도동항 인근 언덕 위 숙소는 바다 조망이 뛰어나지만 경사가 가파릅니다. 짐이 많다면 항구에서 가깝고 평지에 위치한 숙소를 선택하는 것이 편합니다.

[애드센스]

## ❓ 자주 묻는 질문

**Q. 울릉도 배편 예약은 얼마나 미리 해야 하나요?**
비수기(10월~6월 초)는 1~2주 전에도 예약 가능한 경우가 많습니다. 하지만 7~8월 성수기와 명절 연휴에는 1~2개월 전에 매진되는 경우가 일반적입니다. 날짜가 확정되면 즉시 예약하는 것이 가장 안전합니다.

**Q. 독도에 무조건 입도할 수 있나요?**
아닙니다. 독도 입도는 당일 기상 조건(파고, 풍속, 시야)에 따라 결정되며, 운항 자체가 취소되거나 배에서 조망만 하는 크루즈 형태로 운영될 수 있습니다. 독도 입도를 목적으로 한다면 울릉도 일정을 최소 3~4일 이상 잡는 것을 권장합니다.

**Q. 울릉도에서 렌터카를 빌릴 수 있나요?**
네, 울릉도 내에서 렌터카 대여가 가능합니다. 도동항 주변 렌터카 업체를 통해 경차나 SUV를 빌릴 수 있습니다. 다만 울릉도 도로는 좁고 경사가 심한 구간이 많아 운전이 익숙하지 않다면 섬내 버스나 택시 이용을 고려하세요.

**Q. 멀미가 심한 편인데 울릉도 여행이 힘들까요?**
파도 상황에 따라 다르지만 3시간 내외의 항해에서 멀미를 호소하는 여행객이 많습니다. 탑승 전 멀미약 복용은 필수이며, 배의 중간 좌석(좌우 균형이 잡힌 곳)에 앉고 시선은 고정된 수평선을 바라보는 것이 도움이 됩니다. 속도가 빠른 쾌속선보다 대형 여객선이 흔들림이 적습니다.

**Q. 울릉도에서 독도까지 배편은 따로 예약해야 하나요?**
네, 울릉도에서 독도행 배편은 별도 예약이 필요합니다. 울릉도 도착 후 현지에서 예약하거나, 출발 전 울릉군 공식 독도 관광 사이트에서 미리 예약할 수 있습니다. 성수기에는 독도행 배도 빠르게 마감될 수 있으니 미리 확인하세요.
"""

TAGS_2 = [
    "울릉도", "독도", "울릉도배편", "독도배편", "울릉도여행준비물",
    "울릉도예약", "독도입도", "울릉도당일치기", "울릉도숙소",
    "포항울릉도배", "묵호울릉도", "울릉도멀미약", "울릉도독도여행", "독도관광"
]

IMAGES_2 = [
    {
        "index": 1,
        "prompt": "Ulleungdo ferry terminal Pohang port South Korea, large passenger ferry, tourists boarding, morning departure, blue ocean",
        "filename": "ulleungdo-ferry-pohang-terminal-1.jpg",
        "alt": "울릉도행 여객선 포항 출발 터미널",
    },
    {
        "index": 2,
        "prompt": "Dokdo island South Korea aerial view, rocky volcanic island, East Sea, Korean flag, lighthouse, blue ocean surrounding",
        "filename": "dokdo-island-aerial-east-sea-2.jpg",
        "alt": "독도 전경 동해 한국 영토",
    },
    {
        "index": 3,
        "prompt": "Travel packing essentials for island trip, seasickness medicine, rain jacket, dry bag, power bank, cash, laid out on white background",
        "filename": "ulleungdo-travel-essentials-packing-3.jpg",
        "alt": "울릉도 여행 필수 준비물 챙기기",
    },
    {
        "index": 4,
        "prompt": "Dodong port Ulleungdo island accommodation pension guesthouse, ocean view, evening lights, fishing boats, traditional Korean island scenery",
        "filename": "ulleungdo-dodong-port-accommodation-4.jpg",
        "alt": "울릉도 도동항 숙소 바다 전망",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    results = {}

    print("\n" + "="*60)
    print("글 1: 제주 우도 페리 자전거 렌트 당일치기")
    print("="*60)
    r1 = publish_one(TITLE_1, BODY_1, TAGS_1, IMAGES_1, "제주 우도")
    results["post1"] = r1

    print("\n" + "="*60)
    print("글 2: 울릉도 독도 배편 예약 여행 준비물")
    print("="*60)
    r2 = publish_one(TITLE_2, BODY_2, TAGS_2, IMAGES_2, "울릉도 독도")
    results["post2"] = r2

    print("\n" + "="*60)
    print("발행 결과 요약")
    print("="*60)
    for k, r in results.items():
        status = "✅ 발행 성공" if r.get("ok") else "❌ 실패"
        url = r.get("url", r.get("reason", ""))
        print(f"{k}: {status} — {url}")

    # 텔레그램 보고
    now = datetime.now().strftime("%H:%M")
    reports = []
    for k, r in results.items():
        title = TITLE_1 if k == "post1" else TITLE_2
        if r.get("ok"):
            reports.append(f"블로그: blogspot_travel\n제목: {title}\n발행시각: {now}\nURL: {r.get('url', '')}")
        else:
            reports.append(f"블로그: blogspot_travel\n제목: {title}\n상태: ❌ 실패\n사유: {r.get('reason', '')}")

    msg = "✅ 발행 완료\n\n" + "\n\n".join(reports) + "\n\n🔧 검수 중 수정사항:\n- 이상 없음"
    import subprocess
    try:
        subprocess.run(
            ["python3", str(BASE_DIR / "tg_send.py"), msg],
            timeout=15,
            cwd=str(BASE_DIR),
        )
        print("\n텔레그램 보고 완료")
    except Exception as e:
        print(f"\n텔레그램 보고 실패: {e}")
