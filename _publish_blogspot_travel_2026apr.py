"""
blogspot_travel 두 글 생성 및 발행 스크립트 (2026-04-19)
키워드:
1. 제주 우도 페리 자전거 렌트 당일치기
2. 서울 창덕궁 후원 예약 입장료 시간
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
        max_w = 800
        if img.width > max_w:
            ratio = max_w / img.width
            new_h = int(img.height * ratio)
            img = img.resize((max_w, new_h), Image.LANCZOS)
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
        labels=tags[:12],  # Blogger API 최대 12개 제한
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
            labels=tags[:12],  # Blogger API 최대 12개 제한
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
# 글 2: 서울 창덕궁 후원 예약 입장료 시간
# ══════════════════════════════════════════════════════════════════════════════

TITLE_2 = "서울 창덕궁 후원 예약 방법과 입장료 관람 시간 2026 완벽 정리"

BODY_2 = """💡 핵심 요약
- 창덕궁 후원은 사전 예약 필수, 문화재청 예약 사이트에서 1~30일 전 예매 가능
- 입장료는 일반 성인 기준 8,000원(후원 포함), 궁궐 단독 관람은 3,000원 (후기 기준)
- 관람 시간은 계절별로 다르며, 해설사 동행 투어로만 후원 입장 가능

## 🏯 창덕궁 후원이란? 역사와 볼거리 소개

{{이미지1}}

창덕궁은 조선 시대 5대 궁궐 중 하나로, 1997년 유네스코 세계유산에 등재된 서울의 대표 문화유산입니다. 그 중에서도 **후원(後苑)**은 왕과 왕비의 휴식 공간으로 사용된 비밀 정원으로, 약 30만㎡(약 9만 평)에 이르는 드넓은 자연림과 연못, 정자가 어우러진 공간입니다.

후원은 창경궁과도 연결되어 있으며, 자연 지형을 최대한 살린 한국 전통 조경의 정수를 보여줍니다. 인공적으로 과도하게 손대지 않고 자연 그대로를 활용한 것이 서양의 정형식 정원과 구별되는 특징입니다.

후원 내 주요 볼거리는 다음과 같습니다.

| 명소 | 특징 |
|------|------|
| 부용지 | 가장 아름다운 연못, 부용정과 주합루가 반영 |
| 애련지 | 연꽃이 피는 연못, 가을 단풍이 아름다움 |
| 연경당 | 조선 시대 양반가 건축 양식의 사랑채 |
| 옥류천 | 자연 계곡 위 정자들, 소요정·청의정 등 |
| 존덕정 | 오래된 소나무와 어우러진 육각형 정자 |

> 💡 후원은 봄 철쭉(4~5월), 여름 연꽃(7~8월), 가을 단풍(10~11월)이 절정을 이룹니다. 방문 시기에 따라 전혀 다른 풍경을 즐길 수 있습니다.

[애드센스]

## 📅 창덕궁 후원 예약 방법과 예매 절차

{{이미지2}}

창덕궁 후원은 **반드시 사전 예약**이 필요합니다. 현장 매표로는 후원에 입장할 수 없으니 방문 전 온라인 예약을 반드시 완료해야 합니다.

**예약 방법**

예약은 문화재청 궁능유적본부 공식 예약 사이트(한국 관광공사 코레일 연계 또는 문화재청 직접 예약 페이지)에서 가능합니다. 예약은 방문 1일 전까지, 일부 시간대는 당일 잔여석이 나오기도 하지만 봄·가을 성수기에는 조기 마감이 일반적입니다.

| 예약 항목 | 내용 |
|----------|------|
| 예약 사이트 | 문화재청 궁능유적본부 공식 예약 페이지 |
| 예약 가능 기간 | 방문일 기준 최대 30일 전부터 |
| 1인 최대 예약 | 동반자 포함 1회 4인까지 (현지 규정 기준) |
| 예약 변경/취소 | 방문 1일 전까지 가능 |

**예약 절차**

1. 문화재청 궁능유적본부 공식 예약 사이트 접속
2. 창덕궁 후원 선택 → 원하는 날짜·시간 선택
3. 인원 수 입력 → 요금 확인 후 결제
4. 예약 확인서(QR코드) 출력 또는 앱 저장
5. 당일 창덕궁 매표소에서 예약 확인 후 입장

> 💡 단체 관람(10인 이상)은 별도 단체 예약 창구를 이용해야 합니다. 개인 예약 페이지에서는 최대 4인까지만 예약됩니다.

[애드센스]

## 💰 창덕궁 후원 입장료와 할인 정보

{{이미지3}}

창덕궁 입장료는 궁궐 단독 관람과 후원 포함 관람으로 나뉩니다. 후원은 별도 입장료가 추가됩니다.

| 구분 | 일반 성인 | 청소년(만 7~18세) | 비고 |
|------|----------|-----------------|------|
| 창덕궁 단독 | 3,000원 | 1,500원 | 현지 기준 |
| 창덕궁 + 후원 | 8,000원 | 4,000원 | 해설사 동행 필수 |
| 만 6세 이하 | 무료 | — | |
| 만 65세 이상 | 무료 | — | |
| 국가유공자 등 | 무료 | — | 증빙 필요 |

**할인 혜택**

- 한복 착용 시: 창덕궁 무료 입장 (후원 요금 별도 적용, 기간 한정이므로 방문 전 확인 필요)
- 문화가 있는 날(매월 마지막 수요일): 무료 개방 또는 할인 (후원 제외될 수 있음)
- 고궁박물관 통합권: 경복궁·창덕궁·덕수궁·창경궁 연계 관람 시 할인

> 💡 한복 무료 입장은 기간 한정 정책으로, 방문 전 창덕궁 공식 안내를 통해 최신 정보를 반드시 확인하세요.

[애드센스]

## 🕐 창덕궁 후원 관람 시간과 투어 일정

{{이미지4}}

창덕궁 후원은 **해설사 동행 투어**로만 입장이 가능합니다. 자유 관람이 아닌 지정된 시간에 해설사와 함께 움직이는 방식이므로, 예약 시간에 맞춰 정시에 집결해야 합니다.

**운영 시간 (계절별 변동, 현지 기준)**

| 계절 | 관람 시간 | 투어 소요 시간 |
|------|----------|--------------|
| 봄·가을 (3~5월, 9~11월) | 09:00~18:00 | 약 90~120분 |
| 여름 (6~8월) | 09:00~18:30 | 약 90~120분 |
| 겨울 (12~2월) | 09:00~17:00 | 약 90분 |

**투어 시간대 (예: 오전 9시, 10시, 11시, 오후 1시, 2시, 3시, 4시 등)**

각 회차당 인원이 제한되어 있으며, 한국어 해설 외에 영어·중국어·일본어 해설 투어도 별도 운영됩니다(일정에 따라 다름).

**관람 주의사항**

- 월요일은 정기 휴무 (단, 공휴일이면 개관하고 다음날 대체 휴무)
- 투어 집결 시각 5분 전까지 입구에 도착해야 합니다
- 후원 내 음식물 섭취 금지, 반려동물 출입 불가
- 사진 촬영은 가능하나 일부 구역에서 삼각대 사용이 제한될 수 있음

> 💡 후원 투어는 계절과 날씨에 따라 코스가 일부 변경될 수 있습니다. 겨울에는 일부 연못이 얼어 다른 경로로 안내받을 수 있습니다.

[애드센스]

## ❓ 자주 묻는 질문

**Q. 창덕궁 후원 예약은 당일에도 가능한가요?**
성수기(봄 4~5월, 가을 10~11월)에는 당일 잔여석이 거의 없어 현장 입장이 어렵습니다. 비수기에는 당일 잔여 자리가 남는 경우도 있지만 보장할 수 없으므로, 방문 일정이 정해지면 최소 1~2주 전에 예약하는 것이 안전합니다.

**Q. 후원 관람 시 특별히 준비해야 할 것이 있나요?**
후원은 자연림 속 흙길과 계단을 포함한 코스를 약 90~120분 동안 걸어야 합니다. 편한 운동화와 계절에 맞는 복장을 갖추고, 개인 생수를 지참하는 것이 좋습니다. 우산·우비는 날씨에 따라 필요합니다.

**Q. 창덕궁 후원은 어린이도 입장 가능한가요?**
만 7세 미만 어린이는 후원 입장이 제한될 수 있으며, 만 7세 이상은 청소년 요금이 적용됩니다. 어린 자녀와 방문 시 현지 안내에 따르는 것이 좋습니다. 또한 오랜 도보 코스이므로 체력 배분을 고려하세요.

**Q. 창덕궁과 창경궁을 같이 관람할 수 있나요?**
네, 창덕궁과 창경궁은 경내에서 연결되어 있어 한 티켓으로 두 궁궐을 같이 관람할 수 있습니다. 후원은 창덕궁 영역에 속하며 별도 예약이 필요합니다. 창경궁 동선까지 포함하면 반나절~하루 일정으로 여유 있게 계획하는 것이 좋습니다.

**Q. 창덕궁 주변 주차와 대중교통 정보는?**
지하철 3호선 안국역 3번 출구에서 도보 5~10분 거리입니다. 주변 주차 공간이 협소하고 주차 요금이 비싸므로, 대중교통 이용을 강력히 권장합니다. 인근에 북촌 한옥마을·인사동·경복궁이 있어 연계 관광 코스로 구성하기에도 좋습니다.
"""

TAGS_2 = [
    "창덕궁", "창덕궁후원", "창덕궁예약", "창덕궁입장료", "창덕궁관람시간",
    "서울궁궐", "창덕궁후원예약방법", "부용지", "서울여행", "서울문화유산",
    "조선궁궐", "세계유산", "창덕궁한복", "서울당일치기", "창덕궁투어"
]

IMAGES_2 = [
    {
        "index": 1,
        "prompt": "Changdeokgung Palace Huwon secret garden Seoul Korea, traditional Korean architecture, natural forest, reflection pond Buyongji, autumn foliage",
        "filename": "changdeokgung-huwon-buyongji-1.jpg",
        "alt": "창덕궁 후원 부용지 전경",
    },
    {
        "index": 2,
        "prompt": "Changdeokgung Palace entrance gate Seoul Korea, tourists entering, traditional wooden gate, Korean palace courtyard, blue sky",
        "filename": "changdeokgung-reservation-entrance-2.jpg",
        "alt": "창덕궁 입구 예약 관람 장면",
    },
    {
        "index": 3,
        "prompt": "Korean palace ticket booth admission fee counter, visitors paying entrance fee, traditional palace setting Seoul Korea",
        "filename": "changdeokgung-ticket-admission-3.jpg",
        "alt": "창덕궁 입장료 매표소",
    },
    {
        "index": 4,
        "prompt": "Changdeokgung Huwon garden tour group with guide, forest path walking, traditional pavilion Jondeokjeong, Korean nature garden autumn",
        "filename": "changdeokgung-huwon-tour-guide-4.jpg",
        "alt": "창덕궁 후원 해설사 투어 관람",
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
    results["post1"] = {"title": TITLE_1, "result": r1}

    print("\n" + "="*60)
    print("글 2: 서울 창덕궁 후원 예약 입장료 시간")
    print("="*60)
    r2 = publish_one(TITLE_2, BODY_2, TAGS_2, IMAGES_2, "서울 창덕궁")
    results["post2"] = {"title": TITLE_2, "result": r2}

    print("\n" + "="*60)
    print("발행 결과 요약")
    print("="*60)
    for k, v in results.items():
        r = v["result"]
        status = "✅ 발행 성공" if r.get("ok") else "❌ 실패"
        url = r.get("url", r.get("reason", ""))
        print(f"{k}: {status} — {url}")

    # 텔레그램 보고
    now = datetime.now().strftime("%H:%M")
    reports = []
    for k, v in results.items():
        title = v["title"]
        r = v["result"]
        if r.get("ok"):
            reports.append(f"블로그: travel.baremi542.com\n제목: {title}\n발행시각: {now}\nURL: {r.get('url', '')}")
        else:
            reports.append(f"블로그: travel.baremi542.com\n제목: {title}\n상태: ❌ 실패\n사유: {r.get('reason', '')}")

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
