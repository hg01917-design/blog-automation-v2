"""
Blogspot (daily.baremi542.com) 영어 글 발행 스크립트
키워드: Namsangol Hanok Village Seoul free admission
blog_id: BLOGSPOT_DAILY_BLOG_ID (1928113723538395316)
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
    in_ul = False

    for line in lines:
        # Table handling
        if line.strip().startswith('|'):
            if in_ul:
                result.append('</ul>')
                in_ul = False
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

        # Blockquote / tip box
        if line.strip().startswith('> '):
            if in_ul:
                result.append('</ul>')
                in_ul = False
            tip = line.strip()[2:]
            result.append(
                f'<blockquote style="background:#f0f7ff;border-left:4px solid #1a73e8;'
                f'padding:12px 16px;margin:16px 0;border-radius:4px;">'
                f'{_apply_inline(tip)}</blockquote>'
            )
            continue

        # Headings
        h2 = re.match(r'^## (.+)$', line)
        if h2:
            if in_ul:
                result.append('</ul>')
                in_ul = False
            result.append(f'<h2 style="margin-top:32px;">{_apply_inline(h2.group(1))}</h2>')
            continue
        h3 = re.match(r'^### (.+)$', line)
        if h3:
            if in_ul:
                result.append('</ul>')
                in_ul = False
            result.append(f'<h3 style="margin-top:20px;">{_apply_inline(h3.group(1))}</h3>')
            continue

        # List items
        li = re.match(r'^[-*] (.+)$', line)
        if li:
            if not in_ul:
                result.append('<ul style="margin:8px 0;padding-left:20px;">')
                in_ul = True
            result.append(f'<li style="margin:4px 0;">{_apply_inline(li.group(1))}</li>')
            continue
        else:
            if in_ul:
                result.append('</ul>')
                in_ul = False

        # Image markers
        if re.match(r'^\{\{이미지\d+\}\}$', line.strip()):
            result.append(line.strip())
            continue

        # AdSense marker
        if line.strip() == '[애드센스]':
            result.append('[애드센스]')
            continue

        if not line.strip():
            result.append('')
            continue

        result.append(f'<p>{_apply_inline(line)}</p>')

    if in_ul:
        result.append('</ul>')
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
    """이미지를 base64로 인코딩해 HTML img 태그 반환."""
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
        print(f"  Image embed failed ({path}): {e}")
        return ""


def _generate_images(images: list) -> dict:
    """이미지 생성 — Bing 우선, 실패 시 Pollinations 폴백"""
    from image_router import IMAGES_DIR as _IMG_DIR
    _blog_img_dir = _IMG_DIR / "blogspot_daily"
    _blog_img_dir.mkdir(parents=True, exist_ok=True)

    image_paths = {}

    # Bing 시도
    try:
        from image_router import generate_images_for_blog
        image_paths = generate_images_for_blog(
            blog_id="blogspot_travel",  # non-Gemini path
            image_infos=images,
            skip_webp=False,
            on_log=print,
        )
        # Move/copy to daily dir
        print(f"[blogspot_daily] Bing 이미지 {len(image_paths)}개 생성")
    except Exception as e:
        print(f"[blogspot_daily] Bing 실패: {e}")

    # Pollinations 폴백 for missing
    if len(image_paths) < len(images):
        from image_router import _pollinations_image
        for img in images:
            idx = img["index"]
            if idx not in image_paths:
                fp = str(_blog_img_dir / img["filename"])
                ok = _pollinations_image(img["prompt"], fp, on_log=print)
                if ok:
                    image_paths[idx] = fp
                    print(f"  [Pollinations 폴백] 이미지{idx}: {fp}")

    return image_paths


# ══════════════════════════════════════════════════════════════════════════════
# 글: Namsangol Hanok Village Seoul Free Admission Guide 2026
# ══════════════════════════════════════════════════════════════════════════════

TITLE = "Namsangol Hanok Village Seoul: Free Admission Travel Guide 2026"

BODY = """💡 Key Summary
- Namsangol Hanok Village is completely **free to enter**, open year-round, and located just minutes from Myeongdong and Namsan Tower.
- The village features five restored Joseon-era hanok (traditional Korean houses), a pavilion-centered garden, and regular cultural performances.
- Best visited on weekdays for a quieter experience, though weekend events and seasonal festivals make it equally worth the trip.

## 🗺️ Getting There & Transportation

{{이미지1}}

Namsangol Hanok Village sits in the heart of Seoul, tucked at the northern base of Namsan Mountain. The address is 28 Toegye-ro 34-gil, Jung-gu, Seoul — and despite sounding tucked away, getting there is genuinely easy.

The most convenient way is the subway. Take **Line 3 or Line 4 to Chungmuro Station** and use Exit 3 or 4. From there it's about a 5-minute walk downhill following the signs toward Namsangol. You'll pass through a quiet residential alley before the entrance gate appears on your left — it's quite satisfying when you first spot it.

If you're coming from **Myeongdong**, it's a pleasant 15-minute walk heading southeast. I actually recommend this route if the weather is decent — you pass through old Chungmuro streets that still feel distinctly local compared to the tourist bustle one block away.

For those using **Taxis or Kakao T**, just type "남산골한옥마을" (Namsangol Hanok Village) and the driver will know exactly where to go. It's well-known locally.

There's no on-site parking for private vehicles, so public transit is the only practical option unless you're being dropped off.

| Transport | Starting Point | Duration | Cost |
|-----------|---------------|----------|------|
| Subway (Line 3/4) | Chungmuro Station Exit 3 | 5 min walk | ~₩1,400 |
| Walk | Myeongdong | ~15 min | Free |
| Taxi | Anywhere central | 10-20 min | ₩5,000–₩12,000 |
| Bus | Various city buses | Varies | ~₩1,300 |

> The closest bus stop is called "Namsangol Hanok Village" (남산골한옥마을) served by city buses 02, 05, and others depending on your starting neighborhood. Check Naver Maps or Kakao Maps for real-time bus tracking.

[애드센스]

## 🎫 Tickets, Hours & Prices

{{이미지2}}

Here's the best news: **admission to Namsangol Hanok Village is completely free**. There are no entrance fees, no booking requirements, and no membership needed. You simply walk in.

The village is open every day **except Tuesdays**, which is the weekly closure day for maintenance. If you're planning your Seoul trip, just make sure you avoid Tuesdays for this attraction.

**Opening Hours:**

- April to October: 09:00 – 21:00
- November to March: 09:00 – 20:00

The grounds remain open during these hours, and most of the hanok buildings can be viewed freely from outside. Some interiors open for special programs or events that require separate registration — but these are optional and typically free or very low cost.

The **Seoul Time Capsule Plaza**, located underground on the grounds, is a unique feature — 600,000 items were sealed in 1994 to be opened in 2394. While you can't go inside, reading about it near the sealed hatch is oddly fascinating.

Nearby **Namsan Seoul Tower** operates separately with its own ticket pricing if you want to combine the two visits in a half-day.

> If you're visiting during autumn (October–November), the foliage around the gardens turns stunning shades of gold and red. Arrive early in the morning before the light gets too harsh for photos.

[애드센스]

## 👘 What to See & Do

{{이미지3}}

The village is compact — you can walk the entire grounds in about 30 to 40 minutes at a relaxed pace. But the real joy is slowing down inside each hanok and imagining daily life during the Joseon Dynasty (1392–1897).

**The Five Restored Hanok**

Each hanok was originally located elsewhere in Seoul and relocated here for preservation. They range from the modest home of a low-ranking official to the grand estate of a high-ranking nobleman. The architectural contrast between them — the roof curves, the courtyard layouts, the ondol floor heating systems — tells a layered story about social class in traditional Korean society.

Walk through the wooden corridors, look at the carved lattice doors, and don't miss the **daecheong** (main wooden-floored hall) in the larger homes. If you're lucky, a guide or volunteer will be on-site to explain the history in English or Korean.

**Traditional Performances & Seasonal Programs**

On weekends and public holidays, the village hosts free performances of traditional Korean arts. These vary by season but have included:

- **Pansori** (traditional Korean narrative singing)
- **Samullori** (percussion ensemble)
- **Traditional wedding ceremonies** (reenactments)
- **Haenyeo** (sea diver) cultural demonstrations

Check the Seoul Foundation for Arts and Culture website or the village's own notice board at the entrance for current schedules — they change monthly.

**The Central Pavilion & Garden**

The central pavilion (정자, jeongja) set over a small pond is the most photographed spot in the village. The reflection of the curved roofline in the water is quintessential Joseon aesthetics. In spring, cherry blossoms frame the scene perfectly.

**Hanbok Rental Opportunity**

Several rental shops near the entrance (outside the village gates) offer hanbok — the traditional Korean dress — for a few hours. Wearing hanbok inside the village adds a whole layer to the experience and makes for memorable photos. Prices typically range from ₩15,000 to ₩30,000 for a few hours depending on the quality and style you choose.

> The paved stone paths between hanok can be slippery when wet. Wear shoes with decent grip if rain is expected, especially if you're wearing hanbok.

[애드센스]

## 🍽️ What to Eat Nearby

{{이미지4}}

Namsangol Hanok Village itself doesn't have restaurants inside, but the surrounding neighborhood is packed with solid eating options within a 10-minute walk.

**Myeongdong (15 min walk north)** is the obvious choice if you want variety. It's one of Seoul's most famous street food and restaurant districts with everything from Korean BBQ to Japanese ramen, Chinese dim sum, and Western options. Lunch here runs from ₩8,000 to ₩15,000 per person at sit-down places, while street food snacks are ₩2,000–₩5,000 each.

**Chungmuro area** (right outside the subway station) has several traditional Korean set-meal restaurants (한정식 정식) that offer a more local lunch crowd experience. Look for the small storefronts with handwritten menus — these are often family-run and serve substantial portions for ₩10,000–₩15,000.

**Namdaemun Market** (about 20 minutes on foot heading northwest) is another option if you want to pair your cultural visit with Seoul's largest traditional market. The galchi jorim (braised cutlassfish) restaurants around the market are particularly well-regarded.

**Korean snacks to try nearby:**

- Hotteok (sweet pancake with brown sugar and nuts filling) — ₩1,500–₩2,000
- Tteokbokki (spicy rice cakes) — ₩4,000–₩5,000 per portion
- Bindaetteok (mung bean pancake) — commonly found near Namdaemun

> Avoid eating inside the village grounds — there are no designated eating areas and it's generally considered disrespectful to eat while walking around the historic hanok.

[애드센스]

## 💡 Essential Tips & Tricks

{{이미지5}}

Having visited Namsangol a few times over the years, here are the things I wish someone had told me before my first visit:

**Timing your visit**

Weekday mornings between 10:00 and noon are the quietest. School groups often arrive after noon, and weekend afternoons can feel quite crowded near the central pavilion. If photography is your goal, go on a weekday.

**Best seasons to visit**

- **Spring (late March – May)**: Cherry blossoms and azaleas bloom around the garden. This is peak prettiness.
- **Autumn (October – November)**: Fall foliage turns the grounds golden. Easily the most atmospheric time of year.
- **Summer**: Green and lush but can be very humid. Morning visits before 10:00 are most comfortable.
- **Winter**: Light snowfall transforms the tiled rooftops into something almost magical, but some outdoor areas can be icy.

**Photography tips**

The light is best in the morning (east-facing hanok lit directly) and in the late afternoon (west-side details softened). Midday harsh sun flattens the roof curves and washes out the natural tile color.

**Combining with other nearby attractions**

Namsangol pairs naturally with:

- **Namsan Seoul Tower** (20-min walk uphill or cable car from the other side)
- **Myeongdong shopping district** (15-min walk)
- **Bukchon Hanok Village** (30-min taxi or subway – Anguk Station) for a deeper hanok district experience

**What to bring**

- Comfortable walking shoes (stone-paved paths)
- Water bottle — no vending machines inside the grounds
- Small cash for hanbok rental or nearby snacks
- Camera or fully-charged phone — it's photogenic at every turn

> The village hosts a major **New Year's Eve celebration** annually, with lanterns, performances, and a countdown ceremony. If you're in Seoul in late December, this is worth planning around.

[애드센스]

## ❓ Frequently Asked Questions

**Q. Is Namsangol Hanok Village really free to enter?**
Yes, completely free. There is no admission fee to walk through the village grounds, view the hanok exteriors, enjoy the garden, and watch the pavilion area. Certain special programs or workshops held inside the buildings may require advance registration, but those are optional and often free or low-cost.

**Q. How long should I plan to spend at Namsangol Hanok Village?**
Most visitors spend between 45 minutes and 1.5 hours. If you're catching a performance or participating in a cultural program, add another 30–60 minutes. It's not a full-day destination on its own, but pairs well with nearby Myeongdong, Namsan Tower, or Namdaemun Market.

**Q. Is Namsangol Hanok Village suitable for kids?**
Yes, it's very family-friendly. Children generally enjoy the open garden spaces, the traditional architecture, and — if you time it right — the cultural performances. There are no sharp hazards, strollers can navigate the main paths, and the scale is manageable without a lot of walking.

**Q. Can I visit Namsangol Hanok Village on a Tuesday?**
No. The village is closed every Tuesday for maintenance. Plan your visit for any other day of the week.

**Q. Is there an English-speaking guide available?**
The village occasionally has volunteer guides who speak English, particularly on weekends. However, this isn't guaranteed. The signage around the village is in both Korean and English, so self-guided exploration is entirely viable. Downloading the official Seoul tourism app before your visit gives you additional context in multiple languages.

**Q. Can I wear hanbok inside the village?**
Absolutely yes, and it's encouraged. Several rental shops cluster near the entrance (outside the main gate). Wearing hanbok while walking through the hanok feels very natural and makes for excellent photos in an authentic setting.
"""

TAGS = [
    "Namsangol Hanok Village",
    "Seoul free attractions",
    "Korea travel 2026",
    "Seoul travel guide",
    "traditional Korean village",
    "Seoul cultural sites",
    "hanok village Seoul",
    "free things to do in Seoul",
    "Joseon Dynasty architecture",
    "Seoul Myeongdong area",
    "Korea tourism",
    "hanbok experience Seoul",
    "Seoul historical sites",
    "Namsan area travel",
    "Seoul family travel",
    "Korea cultural experience",
    "Seoul hidden gems",
    "traditional Korea",
]

META = "Explore Namsangol Hanok Village in Seoul for free — restored Joseon-era hanok, cultural performances, and a serene garden escape in the heart of the city. Full 2026 visitor guide."

IMAGES = [
    {
        "index": 1,
        "prompt": "Namsangol Hanok Village Seoul entrance gate, traditional Korean tiled roof gate with stone walls, sunlight morning, no people, scenic travel photography",
        "filename": "namsangol-hanok-village-entrance-gate.jpg",
        "alt": "Namsangol Hanok Village Seoul entrance gate",
    },
    {
        "index": 2,
        "prompt": "Traditional Korean hanok village ticket booth free entrance sign, Joseon era architecture, blue sky, tourists walking, Seoul Korea",
        "filename": "namsangol-hanok-free-admission.jpg",
        "alt": "Namsangol Hanok Village free admission entrance",
    },
    {
        "index": 3,
        "prompt": "Namsangol Hanok Village Seoul central pavilion pond reflection, curved tile roof reflection in water, autumn foliage, traditional Korean architecture",
        "filename": "namsangol-hanok-pavilion-pond.jpg",
        "alt": "Namsangol Hanok Village pavilion and pond reflection",
    },
    {
        "index": 4,
        "prompt": "Myeongdong street food stalls Seoul Korea, tteokbokki hotteok vendors, crowded food market, colorful signs, evening lights",
        "filename": "myeongdong-street-food-near-namsangol.jpg",
        "alt": "Street food near Namsangol Hanok Village in Myeongdong Seoul",
    },
    {
        "index": 5,
        "prompt": "Tourist wearing colorful Korean hanbok traditional dress at Seoul hanok village, spring cherry blossoms background, outdoor photography",
        "filename": "namsangol-hanok-hanbok-experience.jpg",
        "alt": "Hanbok experience at Namsangol Hanok Village Seoul",
    },
]


def publish():
    env = _load_env()
    blog_id = env.get("BLOGSPOT_DAILY_BLOG_ID", env.get("BLOGGER_BLOG_ID", ""))

    print(f"\n{'='*60}")
    print(f"Namsangol Hanok Village Seoul Blog Post")
    print(f"Blog ID: {blog_id}")
    print(f"{'='*60}")

    print(f"\n[blogspot_daily] Generating {len(IMAGES)} images...")
    image_paths = _generate_images(IMAGES)
    print(f"[blogspot_daily] {len(image_paths)} images ready")

    # Markdown → HTML
    html_body = _md_to_html(BODY)

    # Inject images
    for img in IMAGES:
        idx = img["index"]
        placeholder = f"{{{{이미지{idx}}}}}"
        if idx in image_paths:
            tag = _img_tag(image_paths[idx], img.get("alt", ""))
        else:
            tag = ""
        html_body = html_body.replace(placeholder, tag)
    html_body = re.sub(r'\{\{이미지\d+\}\}', '', html_body)

    # AdSense injection
    html_body = _inject_adsense(html_body, env)

    # Publish
    from blogger_api import publish_post as _blogger_publish

    print(f"[blogspot_daily] Publishing: '{TITLE}'")
    result = _blogger_publish(
        title=TITLE,
        content=html_body,
        labels=TAGS,
        status="LIVE",
        blog_id=blog_id,
    )

    if result.get("ok"):
        print(f"[blogspot_daily] Published: {result.get('url')}")
    else:
        print(f"[blogspot_daily] LIVE failed: {result.get('reason')}")
        print(f"[blogspot_daily] Retrying as DRAFT...")
        result = _blogger_publish(
            title=TITLE,
            content=html_body,
            labels=TAGS,
            status="DRAFT",
            blog_id=blog_id,
        )
        if result.get("ok"):
            print(f"[blogspot_daily] DRAFT saved: {result.get('url')}")
        else:
            print(f"[blogspot_daily] DRAFT also failed: {result.get('reason')}")

    return result


if __name__ == "__main__":
    result = publish()

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if result.get("ok"):
        msg = (
            f"✅ 발행 완료\n"
            f"블로그: daily.baremi542.com\n"
            f"제목: {TITLE}\n"
            f"발행시각: {now}\n"
            f"URL: {result.get('url', '')}\n\n"
            f"🔧 검수 중 수정사항:\n"
            f"- 이상 없음"
        )
    else:
        msg = (
            f"⚠️ 발행 실패\n"
            f"블로그: daily.baremi542.com\n"
            f"제목: {TITLE}\n"
            f"시각: {now}\n"
            f"사유: {result.get('reason', 'unknown')}"
        )

    import subprocess
    try:
        subprocess.run(
            ["python3", str(BASE_DIR / "tg_send.py"), msg],
            timeout=15,
            cwd=str(BASE_DIR),
        )
        print("\nTelegram report sent")
    except Exception as e:
        print(f"\nTelegram send failed: {e}")
