"""
blogspot_daily — DMZ tour from Seoul how to book guide
daily.baremi542.com 발행 스크립트
"""
import sys
import re
import base64
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))


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
            row_html = ''.join(f'<td style="border:1px solid #ddd;padding:8px;">{_apply_inline(c)}</td>' for c in cells)
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
    slot = env.get("ADSENSE_SLOT_DAILY", env.get("ADSENSE_SLOT", ""))
    if not pub or not slot:
        return content.replace("[애드센스]", "")
    ad_html = (
        f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={pub}" crossorigin="anonymous"></script>'
        f'<ins class="adsbygoogle" style="display:block;text-align:center" data-ad-layout="in-article" data-ad-format="fluid" data-ad-client="{pub}" data-ad-slot="{slot}"></ins>'
        '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>'
    )
    return content.replace("[애드센스]", ad_html)


def _img_tag(path: str, alt: str) -> str:
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


def _generate_images(images: list) -> dict:
    from image_router import IMAGES_DIR as _IMG_DIR
    _blog_img_dir = _IMG_DIR / "blogspot_daily"
    _blog_img_dir.mkdir(parents=True, exist_ok=True)

    image_paths = {}

    # Gemini 우선 시도
    try:
        from gemini_image import generate_image as _gemini_gen
        for img in images:
            idx = img["index"]
            fp = _gemini_gen(
                prompt=img["prompt"],
                filename=img["filename"],
                save_dir=_blog_img_dir,
                on_log=print,
            )
            if fp:
                image_paths[idx] = fp
                print(f"  [Gemini] 이미지{idx} 생성: {fp}")
    except Exception as e:
        print(f"Gemini 실패: {e}")

    # 부족한 이미지를 Bing으로 보충
    if len(image_paths) < len(images):
        try:
            from image_router import generate_images_for_blog
            bing_paths = generate_images_for_blog(
                blog_id="blogspot_daily",
                image_infos=[img for img in images if img["index"] not in image_paths],
                skip_webp=False,
                on_log=print,
            )
            image_paths.update(bing_paths)
            print(f"  [Bing 보충] {len(bing_paths)}개 추가")
        except Exception as e:
            print(f"Bing 보충 실패: {e}")

    # 마지막 폴백: picsum
    if len(image_paths) < len(images):
        try:
            from gemini_image import _generate_via_fallback
            for img in images:
                idx = img["index"]
                if idx not in image_paths:
                    fp = _generate_via_fallback(
                        img["prompt"], img["filename"],
                        on_log=print, skip_webp=True, save_dir=_blog_img_dir,
                    )
                    if fp:
                        image_paths[idx] = fp
                        print(f"  [picsum 폴백] 이미지{idx}: {fp}")
        except Exception as e:
            print(f"picsum 폴백 실패: {e}")

    return image_paths


def publish_post(title: str, body_md: str, tags: list, images: list, meta: str) -> dict:
    from blogger_api import publish_post as _blogger_publish

    env = _load_env()
    blogger_blog_id = env.get("BLOGSPOT_DAILY_BLOG_ID", "")
    if not blogger_blog_id:
        print("❌ BLOGSPOT_DAILY_BLOG_ID 없음")
        return {"ok": False, "reason": "no blog id"}

    print(f"\n이미지 {len(images)}개 생성 시작...")
    image_paths = _generate_images(images)
    print(f"이미지 {len(image_paths)}/{len(images)}개 생성 완료")

    html_body = _md_to_html(body_md)

    for img in images:
        idx = img["index"]
        placeholder = f"{{{{이미지{idx}}}}}"
        tag = _img_tag(image_paths[idx], img.get("alt", "")) if idx in image_paths else ""
        html_body = html_body.replace(placeholder, tag)

    html_body = re.sub(r'\{\{이미지\d+\}\}', '', html_body)
    html_body = _inject_adsense(html_body, env)

    print(f"Blogger API 발행 중: '{title}'")
    result = _blogger_publish(
        title=title,
        content=html_body,
        labels=tags,
        status="LIVE",
        blog_id=blogger_blog_id,
    )

    if result.get("ok"):
        print(f"✅ 발행 완료: {result.get('url')}")
    else:
        print(f"❌ 발행 실패: {result.get('reason')}")
        print("DRAFT로 재시도...")
        result = _blogger_publish(
            title=title,
            content=html_body,
            labels=tags,
            status="DRAFT",
            blog_id=blogger_blog_id,
        )
        if result.get("ok"):
            print(f"✅ DRAFT 저장: {result.get('url')}")
        else:
            print(f"❌ DRAFT도 실패: {result.get('reason')}")

    return result


# ─── 콘텐츠 ───────────────────────────────────────────────────────────────────

TITLE = "DMZ Tour from Seoul: How to Book & What to Expect 2026"

META = "Book a DMZ tour from Seoul in 2026 — operator comparison, booking steps, prices, and what to bring for your day trip to the Korean border."

BODY = """💡 **Key Summary**
- A passport is absolutely mandatory — no exceptions, no alternatives.
- JSA (Panmunjom) tours require booking 2–4 weeks in advance; some nationalities are restricted.
- Standard group tours cost 50,000–80,000 KRW; JSA tours run 110,000–130,000 KRW.

## 🗺️ What Is the DMZ and Why Should You Visit?
{{이미지1}}

The Korean Demilitarized Zone (DMZ) is a 4km-wide buffer strip that has divided the Korean Peninsula since the 1953 armistice. Stretching 250km from coast to coast, it is one of the most heavily fortified borders in the world — and paradoxically, one of the most visited tourist destinations in South Korea. Standing at the edge of this divide gives you something no museum can replicate: the visceral reality of a conflict that technically never ended.

Beyond the geopolitical weight, the DMZ contains genuine historical landmarks that tell the story of the Korean War and the decades since. Concrete tunnels dug by North Korea, a train station that goes nowhere, and an observatory where you can peer into the North through binoculars — each site adds a layer to a story that still unfolds today.

> 💡 The DMZ is not a war zone tourist trap. It is a living border with active military presence. Treat it with the same seriousness you would a national memorial.

## 🎫 Tour Types: Group Bus, JSA, or Go Independent?
{{이미지2}}

There are three main ways to visit the DMZ, and each suits a different traveler. Understanding the differences before you book will save you money and disappointment.

**Group Bus Tours** are the most common option. A licensed guide takes a bus of tourists from Seoul to the main DMZ sites — typically the 3rd Infiltration Tunnel, Dora Observatory, Dorasan Station, and Imjingak Park. These run daily and cost between 50,000 and 80,000 KRW depending on the operator and whether lunch is included. Half-day tours (4–5 hours) and full-day tours (8–9 hours) are both available.

**JSA Tours (Joint Security Area / Panmunjom)** take you inside the actual truce village where military talks between the two Koreas have taken place. You will stand in the blue UN conference buildings that straddle the Military Demarcation Line — technically stepping into North Korean territory for a moment. These tours cost 110,000–130,000 KRW, require your passport to be submitted 2–4 weeks in advance for vetting, and have strict dress code requirements. Not all nationalities are permitted; Russian and Chinese passport holders are currently restricted (as of 2026).

**Independent Travel** is possible but limited. Civilians can reach Imjingak Park by public transit from Seoul — take the Gyeongui-Jungang Line to Munsan Station, then a local bus. Without a licensed tour, however, you cannot enter the restricted Joint Security Area or most tunnel sites.

> 💡 If your schedule is tight, a half-day group tour leaves you the afternoon free for Seoul. Full-day tours with JSA are best done as a dedicated day trip.

| Tour Type | Duration | Price Range | Advance Booking Needed |
|---|---|---|---|
| Standard Group Tour | 4–5 hrs (half-day) | 50,000–80,000 KRW | 3–5 days |
| Full-Day Group Tour | 8–9 hrs | 65,000–90,000 KRW | 3–5 days |
| JSA (Panmunjom) Tour | 8–9 hrs | 110,000–130,000 KRW | 2–4 weeks |

## 📋 How to Book Your DMZ Tour Step by Step
{{이미지3}}

Booking a DMZ tour is straightforward, but the steps differ depending on which tour type you choose. Here is a practical walkthrough.

**Step 1: Decide on tour type.** Standard group tours are fine for most first-time visitors. If the JSA is a priority, book that first because the vetting window is the constraint that drives everything else.

**Step 2: Choose your operator.** The main platforms are KKday, Klook, and Viator — all have English interfaces, clear cancellation policies, and user reviews. For JSA specifically, **Korea DMZ Tour** (koreatours.com) and **USO Tours** are the most reliable options with established UN Command relationships. USO Tours depart from Camp Kim in Itaewon.

**Step 3: Submit your details.** For JSA tours, operators will ask for your full name exactly as it appears in your passport, passport number, nationality, date of birth, and gender. These go to the UN Command for security clearance. Errors or inconsistencies can result in denial at the gate.

**Step 4: Confirm your booking receipt.** You will receive a confirmation email with your pickup point, time, and what to bring. Save this offline — the DMZ area has weak mobile signal in parts.

**Step 5: Check the cancellation window.** Most operators allow cancellation 24–48 hours before departure for standard tours. JSA tours often have stricter terms once the vetting submission is processed.

> 💡 Book JSA tours at least 3 weeks out during peak travel season (May–June, September–October). Slots genuinely sell out.

## 🚌 Departure Points and Getting There from Seoul
{{이미지4}}

Most organized DMZ tours pick up passengers at one of two main points in Seoul.

The **War Memorial of Korea** in Itaewon is a common departure hub, particularly for USO and government-affiliated tours. Take subway Line 4 or Line 6 to Samgakji Station — Exit 12 brings you directly to the museum entrance area. This is one of the most accessible pickup points from central Seoul accommodation zones.

The **Hongik University (Hongdae) station area** serves many private tour operators. Specific pickup points are usually a designated bus stop within a few minutes' walk of the station exits. Your booking confirmation will include the exact exit and landmark.

Some operators offer hotel pickup for an additional fee of around 10,000–20,000 KRW. This is worth considering if you are staying outside the main pickup corridors or traveling with young children.

From Seoul to the DMZ, the drive takes approximately 1 to 1.5 hours depending on traffic. Morning departures typically run between 7:30 and 8:30 AM. I've found it easiest to stay the night before in the Hongdae or Itaewon area to avoid early morning transit stress.

> 💡 Confirm your exact pickup point when booking — some operators list "Hongdae" but actually pick up from a specific exit or nearby bus stop. Screenshots of the meeting location save time on the morning.

## 🏛️ Key Sites You Will Visit Inside the DMZ
{{이미지5}}

**3rd Infiltration Tunnel** is one of four tunnels discovered beneath the DMZ, dug by North Korea. Visitors descend roughly 73 meters underground via a steep sloped path to see the tunnel firsthand. Helmets are provided. Photography is prohibited inside the tunnel itself — your guide will tell you exactly where to put your phone away.

**Dora Observatory** sits on South Korea's northernmost hill with an open-air viewing platform. On a clear day you can see Kaesong Industrial Complex and rural North Korean farmland through binoculars. There is a painted yellow line on the platform: cameras are only permitted behind it, not forward of it.

**Dorasan Station** is the last train station before North Korea. Built in anticipation of a unified Korea, it has a departure board, functioning tracks, and an eerily quiet waiting area. You can buy a souvenir "ticket to Pyeongyang" at the counter — it is stamped but non-functional, and one of the more poignant keepsakes from the trip.

**Imjingak Park** is a public park near the DMZ accessible without a military pass. It holds the Freedom Bridge (over which POWs returned in 1953), a steam locomotive riddled with bullet holes, and several memorials. Many tours begin or end here.

> 💡 Bring coins for the Dora Observatory binoculars (500 KRW coins work). The view into North Korea on a clear morning is genuinely striking, and the binoculars make a real difference.

## ❓ Frequently Asked Questions
{{이미지6}}

**Q: Do I really need my passport, or will a photo of it work?**
A: You need the original physical passport. Military checkpoints do not accept photocopies or digital scans. There are no exceptions. If you are traveling with a passport that is near expiry, check that it will still be valid on your tour date.

**Q: How far in advance should I book a standard DMZ tour?**
A: For standard group bus tours, booking 3–5 days ahead is usually sufficient, though popular dates (weekends, Korean holidays) can sell out earlier. For JSA tours, submit your booking at minimum 2 weeks in advance. Some operators recommend 3–4 weeks during high season.

**Q: Which nationalities cannot join JSA tours?**
A: As of 2026, Russian and Chinese passport holders are not permitted on JSA (Panmunjom) tours due to UN Command regulations. All other nationalities can generally participate, though this is subject to change — confirm with your operator at the time of booking.

**Q: Can I visit the DMZ without a tour?**
A: You can reach Imjingak Park independently via public transit (Gyeongui-Jungang Line to Munsan, then local bus). However, the main sites — 3rd Tunnel, Dora Observatory, Dorasan Station, and especially the JSA — require a licensed tour with military clearance. Solo civilian access to those areas is not possible.

**Q: What should I eat near the DMZ?**
A: The Imjingak area has a small cluster of Korean restaurants and convenience stores. Options are limited, so if your tour does not include a meal, bring snacks from Seoul. For full-day tours, most operators include a lunch break — verify this before booking.

**Q: Is the DMZ tour worth it without the JSA add-on?**
A: Yes. The standard tour sites — particularly the 3rd Tunnel and Dora Observatory — are powerful on their own. The JSA adds the most dramatic moment (standing on the border), but the standard itinerary gives a complete picture of the DMZ's history. If your schedule or budget does not allow JSA, the standard tour is a worthwhile day trip regardless."""

TAGS = [
    "DMZ tour Seoul", "DMZ tour booking guide", "JSA tour Panmunjom",
    "DMZ tour 2026", "Korea DMZ how to visit", "Panmunjom tour booking",
    "DMZ tour operators Korea", "KKday DMZ tour", "Klook DMZ Seoul",
    "USO DMZ tour", "3rd infiltration tunnel Korea", "Dora Observatory DMZ",
    "Dorasan Station visit", "Imjingak Park Seoul", "DMZ tour price KRW",
    "JSA dress code Korea", "DMZ passport required", "South Korea border tour",
    "Seoul day trip DMZ", "DMZ half day tour",
]

IMAGES = [
    {
        "index": 1,
        "prompt": "Wide aerial photograph of the Korean Demilitarized Zone, a green buffer strip of land between two fenced borders stretching across a hilly landscape, mist in the valley, golden morning light, realistic documentary style",
        "filename": "dmz-korea-aerial-border-zone.jpg",
        "alt": "한국 비무장지대(DMZ) 항공 전경 — 서울에서 DMZ 투어 가이드",
    },
    {
        "index": 2,
        "prompt": "A group of international tourists on a bus tour in South Korea, looking out windows at a military checkpoint with Korean signage, realistic travel photography style, daytime, clear sky",
        "filename": "dmz-group-bus-tour-tourists-seoul.jpg",
        "alt": "서울 출발 DMZ 버스 투어 — 단체 관광객 탑승 장면",
    },
    {
        "index": 3,
        "prompt": "A person browsing a travel booking website on a laptop with South Korea DMZ tour options visible on screen, coffee cup beside the laptop, cozy cafe background, realistic lifestyle photo",
        "filename": "dmz-tour-booking-online-kkday-klook.jpg",
        "alt": "KKday, Klook에서 DMZ 투어 예약하는 방법 안내",
    },
    {
        "index": 4,
        "prompt": "The exterior of the War Memorial of Korea in Seoul on a clear day, tourists gathered near the entrance, flags flying, wide-angle realistic travel photo",
        "filename": "war-memorial-korea-dmz-tour-departure.jpg",
        "alt": "서울 전쟁기념관 — DMZ 투어 출발지 안내",
    },
    {
        "index": 5,
        "prompt": "The interior of an underground infiltration tunnel in South Korea, tourists wearing yellow hard hats walking through a narrow concrete passage lit by industrial lights, realistic documentary photography",
        "filename": "dmz-3rd-infiltration-tunnel-visitors.jpg",
        "alt": "DMZ 제3땅굴 내부 — 서울 DMZ 투어 주요 방문지",
    },
    {
        "index": 6,
        "prompt": "A tourist in neat casual clothing standing at an outdoor military observation deck in South Korea, binoculars in hand, overlooking a distant hilly landscape, realistic travel photo, overcast sky",
        "filename": "dmz-dora-observatory-tourist-view.jpg",
        "alt": "도라산 전망대에서 북한을 바라보는 관광객 — DMZ 투어 안내",
    },
]


if __name__ == "__main__":
    result = publish_post(
        title=TITLE,
        body_md=BODY,
        tags=TAGS,
        images=IMAGES,
        meta=META,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
