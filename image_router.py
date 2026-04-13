"""블로그별 이미지 생성 라우터

블로그 타입에 따라 이미지 생성 소스를 분기합니다.

  salim1su (Naver):  Gemini → Bing(Copilot) → Pollinations
  그 외 블로그:      Bing(Copilot) → Pollinations  (Gemini 사용 안 함)

사용법:
    from image_router import generate_images_for_blog
    result = generate_images_for_blog(
        blog_id="salim1su",
        image_infos=[{'index': 1, 'prompt': '이불 세탁', 'filename': 'img1.jpg'}],
        skip_webp=True,
        on_log=print,
    )
    # → {1: '/path/to/img1.jpg'}
"""
import re
import ssl
import time
import urllib.request
import urllib.parse
from pathlib import Path


def add_title_overlay(img_path: str, title: str, blog_id: str = "", on_log=None) -> bool:
    """썸네일에 블로그별 특색 텍스트 오버레이 추가."""
    def log(msg):
        if on_log:
            on_log(msg)

    try:
        from PIL import Image, ImageDraw, ImageFont
        import textwrap

        _FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
        _FONT_FALLBACKS = [
            "/Library/Fonts/NanumGothicBold.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]

        def _font(size, bold=True):
            idx = 6 if bold else 0
            try:
                return ImageFont.truetype(_FONT_PATH, size, index=idx)
            except Exception:
                for fp in _FONT_FALLBACKS:
                    try:
                        return ImageFont.truetype(fp, size)
                    except Exception:
                        continue
            return ImageFont.load_default()

        def _extract_core(t, max_len=18):
            core = re.split(r'[—·｜]', t)[0].strip()
            if len(core) <= max_len:
                return core
            words = core.split()
            r = ""
            for w in words:
                if len(r) + len(w) + 1 <= max_len:
                    r = (r + " " + w).strip()
                else:
                    break
            return r or core[:max_len]

        def _shadow(draw, pos, text, font, fill=(255,255,255,255), shadow=(0,0,0,160)):
            draw.text((pos[0]+2, pos[1]+2), text, font=font, fill=shadow)
            draw.text(pos, text, font=font, fill=fill)

        def _draw_lines(draw, wrapped, font, W, y_start, gap=12, fill=(255,255,255,255)):
            y = y_start
            for line in wrapped:
                bb = draw.textbbox((0, 0), line, font=font)
                lw = bb[2] - bb[0]; lh = bb[3] - bb[1]
                _shadow(draw, ((W - lw) // 2, y), line, font, fill=fill)
                y += lh + gap

        img = Image.open(img_path).convert("RGBA")
        W, H = img.size
        core = _extract_core(title)

        # ── 블로그별 스타일 ──────────────────────────────────────────
        if blog_id == "baremi542":
            # 하단 그라디언트 + 왼쪽 정렬 (뉴스/정보)
            font = _font(max(52, int(W * .082)))
            ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            for i in range(H // 2):
                d.line([(0, H//2+i),(W, H//2+i)], fill=(10,10,30,int(210*(i/(H//2))**1.4)))
            merged = Image.alpha_composite(img, ov)
            draw = ImageDraw.Draw(merged)
            wrapped = textwrap.wrap(core, width=13)[:2]
            pad = int(W * .07); y = H - pad
            for line in reversed(wrapped):
                bb = draw.textbbox((0,0), line, font=font); lh = bb[3]-bb[1]; y -= lh+10
                _shadow(draw, (pad, y), line, font)

        elif blog_id == "triplog":
            # 상단 그린 배너 + ✈ 태그 (여행 워드프레스)
            font = _font(max(62, int(W * .098))); tf = _font(max(26, int(W * .036)), bold=False)
            wrapped = textwrap.wrap(core, width=10)[:2]
            pv = int(H * .055)
            d0 = ImageDraw.Draw(img)
            lhs = [d0.textbbox((0,0),l,font=font)[3] for l in wrapped]
            total_h = sum(lhs) + (len(wrapped)-1)*12 + pv*2 + 38
            ov = Image.new("RGBA", img.size, (0,0,0,0))
            ImageDraw.Draw(ov).rectangle([(0,0),(W,total_h)], fill=(0,100,80,185))
            merged = Image.alpha_composite(img, ov)
            draw = ImageDraw.Draw(merged)
            draw.text((int(W*.06), int(pv*.5)), "✈  여행 코스", font=tf, fill=(200,255,230,240))
            y = pv + 34
            for line in wrapped:
                bb = draw.textbbox((0,0),line,font=font); lw=bb[2]-bb[0]; lh=bb[3]-bb[1]
                _shadow(draw, ((W-lw)//2, y), line, font); y += lh+12

        elif blog_id == "goodisak":
            # 우측 네이비 세로 배너 (IT/금융)
            font = _font(max(46, int(W * .072)))
            bw = int(W * .40)
            ov = Image.new("RGBA", img.size, (0,0,0,0))
            ImageDraw.Draw(ov).rectangle([(W-bw,0),(W,H)], fill=(20,25,55,210))
            merged = Image.alpha_composite(img, ov)
            draw = ImageDraw.Draw(merged)
            wrapped = textwrap.wrap(_extract_core(title, 14), width=6)[:3]
            lhs = [draw.textbbox((0,0),l,font=font)[3] for l in wrapped]
            total_h = sum(lhs)+(len(wrapped)-1)*12; y=(H-total_h)//2
            for line in wrapped:
                bb=draw.textbbox((0,0),line,font=font); lw=bb[2]-bb[0]; lh=bb[3]-bb[1]
                _shadow(draw, (W-bw+(bw-lw)//2, y), line, font, fill=(180,210,255,255)); y+=lh+12

        elif blog_id == "me1091":
            # 중앙 레드 원형 배지 (리뷰)
            font = _font(max(48, int(W * .074))); sf = _font(max(24, int(W * .034)))
            ov = Image.new("RGBA", img.size, (0,0,0,80))
            merged = Image.alpha_composite(img, ov)
            r = int(W * .31); cx, cy = W//2, H//2
            badge = Image.new("RGBA", img.size, (0,0,0,0))
            ImageDraw.Draw(badge).ellipse([(cx-r,cy-r),(cx+r,cy+r)], fill=(200,40,20,225))
            merged = Image.alpha_composite(merged, badge)
            draw = ImageDraw.Draw(merged)
            wrapped = textwrap.wrap(_extract_core(title, 14), width=7)[:2]
            lhs = [draw.textbbox((0,0),l,font=font)[3] for l in wrapped]
            total_h = sum(lhs)+(len(wrapped)-1)*10; y=cy-total_h//2
            for line in wrapped:
                bb=draw.textbbox((0,0),line,font=font); lw=bb[2]-bb[0]; lh=bb[3]-bb[1]
                _shadow(draw, ((W-lw)//2, y), line, font); y+=lh+10
            draw.text((W//2, cy+r-int(r*.28)), "리뷰", font=sf, fill=(255,220,200,210), anchor="mm")

        elif blog_id == "nolja100":
            # 하단 퍼플 그라디언트 + #여행일기 태그
            font = _font(max(52, int(W * .082))); sf = _font(max(24, int(W * .032)), bold=False)
            ov = Image.new("RGBA", img.size, (0,0,0,0)); d = ImageDraw.Draw(ov)
            for i in range(H//2):
                d.line([(0,H//2+i),(W,H//2+i)], fill=(30,20,60,int(200*(i/(H//2))**1.5)))
            merged = Image.alpha_composite(img, ov)
            draw = ImageDraw.Draw(merged)
            draw.text((W//2, H-int(H*.20)), "# 여행일기", font=sf, fill=(180,200,255,210), anchor="mm")
            wrapped = textwrap.wrap(core, width=12)[:2]
            lhs = [draw.textbbox((0,0),l,font=font)[3] for l in wrapped]
            total_h = sum(lhs)+(len(wrapped)-1)*10; y=H-int(H*.16)-total_h
            _draw_lines(draw, wrapped, font, W, y, gap=10)

        elif blog_id == "salim1su":
            # 상단 핑크 리본 + ✨살림정보 태그
            font = _font(max(52, int(W * .082))); tf = _font(max(24, int(W * .032)))
            ov = Image.new("RGBA", img.size, (0,0,0,0))
            rh = int(H * .09)
            ImageDraw.Draw(ov).rectangle([(0,0),(W,rh)], fill=(220,100,110,225))
            for i in range(H//3):
                ImageDraw.Draw(ov).line([(0,H-H//3+i),(W,H-H//3+i)], fill=(120,40,50,int(170*(i/(H//3))**1.2)))
            merged = Image.alpha_composite(img, ov)
            draw = ImageDraw.Draw(merged)
            draw.text((W//2, rh//2), "✨ 살림정보", font=tf, fill=(255,240,240,255), anchor="mm")
            wrapped = textwrap.wrap(core, width=12)[:2]
            lhs = [draw.textbbox((0,0),l,font=font)[3] for l in wrapped]
            total_h = sum(lhs)+(len(wrapped)-1)*10; y=H-int(H*.07)-total_h
            _draw_lines(draw, wrapped, font, W, y, gap=10)

        elif blog_id == "woll100":
            # 도로 표지판 스타일 (교통정보)
            font = _font(max(50, int(W * .078))); sf = _font(max(22, int(W * .030)))
            ov = Image.new("RGBA", img.size, (0,0,0,80))
            merged = Image.alpha_composite(img, ov)
            draw = ImageDraw.Draw(merged)
            wrapped = textwrap.wrap(_extract_core(title, 14), width=10)[:2]
            lhs = [draw.textbbox((0,0),l,font=font)[3] for l in wrapped]
            total_h = sum(lhs)+(len(wrapped)-1)*12
            sw=int(W*.84); sh=total_h+int(H*.14); sx=(W-sw)//2; sy=(H-sh)//2
            draw.rectangle([(sx-5,sy-5),(sx+sw+5,sy+sh+5)], fill=(255,255,255,255))
            draw.rectangle([(sx,sy),(sx+sw,sy+sh)], fill=(30,110,50,240))
            y = sy+(sh-total_h)//2
            for line in wrapped:
                bb=draw.textbbox((0,0),line,font=font); lw=bb[2]-bb[0]; lh=bb[3]-bb[1]
                _shadow(draw, ((W-lw)//2, y), line, font, shadow=(0,60,20,160)); y+=lh+12
            draw.text((W//2, sy+sh-int(sh*.18)), "교통정보", font=sf, fill=(180,230,180,210), anchor="mm")

        elif blog_id == "phn0502":
            # 영화 포스터 — 클래퍼보드 + 황금 글씨
            font = _font(max(60, int(W * .092))); sf = _font(max(26, int(W * .034)))
            ov = Image.new("RGBA", img.size, (5,5,15,165))
            merged = Image.alpha_composite(img, ov)
            draw = ImageDraw.Draw(merged)
            sh = int(H * .055)
            for i in range(9):
                draw.rectangle([(i*sh,0),((i+1)*sh,sh)], fill=(0,0,0,235) if i%2==0 else (255,255,255,235))
            wrapped = textwrap.wrap(_extract_core(title, 16), width=10)[:2]
            lhs = [draw.textbbox((0,0),l,font=font)[3] for l in wrapped]
            total_h = sum(lhs)+(len(wrapped)-1)*14; y=(H-total_h)//2+int(H*.04)
            for line in wrapped:
                bb=draw.textbbox((0,0),line,font=font); lw=bb[2]-bb[0]; lh=bb[3]-bb[1]
                _shadow(draw, ((W-lw)//2, y), line, font, fill=(255,210,50,255)); y+=lh+14
            draw.text((W//2, H-int(H*.07)), "★ 영화리뷰", font=sf, fill=(200,170,50,215), anchor="mm")

        else:
            # 기본: 하단 반투명 바 + 흰 글씨
            font = _font(max(44, int(W * .068)))
            wrapped = textwrap.wrap(core, width=14)[:2]
            pv = int(H * .05)
            d0 = ImageDraw.Draw(img)
            lhs = [d0.textbbox((0,0),l,font=font)[3] for l in wrapped]
            total_h = sum(lhs)+(len(wrapped)-1)*10; bar_h=total_h+pv*2
            ov = Image.new("RGBA", img.size, (0,0,0,0))
            ImageDraw.Draw(ov).rectangle([(0,H-bar_h),(W,H)], fill=(0,0,0,185))
            merged = Image.alpha_composite(img, ov)
            draw = ImageDraw.Draw(merged)
            _draw_lines(draw, wrapped, font, W, H-bar_h+pv, gap=10)

        # 저장
        p = Path(img_path)
        fmt = "JPEG" if p.suffix.lower() in (".jpg", ".jpeg") else \
              "WEBP" if p.suffix.lower() == ".webp" else "PNG"
        if fmt == "JPEG":
            merged.convert("RGB").save(img_path, "JPEG", quality=92)
        else:
            merged.save(img_path, fmt, quality=90)

        log(f"[썸네일] {blog_id} 오버레이 완료: {p.name}")
        return True

    except Exception as e:
        log(f"[썸네일] 텍스트 오버레이 실패: {e}")
        return False

IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)

# ─── 블로그별 프롬프트 스타일 가이드 ────────────────────────────────────
# DALL-E 3(Bing) 최적화: 주제 맥락 + 품질 지시어 + 분위기
_PROMPT_STYLE = {
    "salim1su": (
        "photorealistic product/lifestyle photography, Korean home setting, "
        "soft natural window light, shallow depth of field, clean minimal background, "
        "sharp focus on subject, no text, no people, no faces, 4K quality"
    ),
    "nolja100": (
        "photorealistic travel photography, South Korea scenic location, "
        "golden hour lighting, wide landscape or architectural shot, "
        "vibrant colors, professional DSLR look, no people, no faces, no text, 4K quality"
    ),
    "goodisak_IT": (
        "photorealistic tech product photography, modern workspace, "
        "device screen with soft glow, dark or light minimal desk setup, "
        "professional studio lighting, no text overlay, no people, 4K quality"
    ),
    "goodisak_finance": (
        "photorealistic financial concept photography, Korean currency or credit card, "
        "clean white or navy background, top-down flat lay composition, "
        "professional studio lighting, no text, no people, 4K quality"
    ),
    "baremi542": (
        "photorealistic documentary-style photography, Korean government or administrative setting, "
        "official document on desk, pen and stamp, soft office lighting, "
        "clean organized composition, no people, no faces, 4K quality"
    ),
    "me1091": (
        "photorealistic lifestyle product photography, Korean home or daily life setting, "
        "natural indoor lighting, clean minimal background, product in actual use context, "
        "warm and inviting atmosphere, no text overlay, no people, no faces, 4K quality"
    ),
    "triplog": (
        "photorealistic travel photography, South Korea tourist destination or pension or resort, "
        "blue sky or sunset backdrop, wide establishing shot, "
        "vibrant natural colors, professional travel magazine style, no people, no faces, 4K quality"
    ),
    "issue01": (
        "photorealistic editorial photography, Korean daily life or social scene, "
        "clean bright natural lighting, journalistic composition, "
        "neutral background, no text overlay, no people faces, 4K quality"
    ),
}

# 구도 변형자 — 같은 글 내 이미지 중복 방지 (index 기반 순환)
_COMPOSITION_VARIANTS = [
    "wide establishing shot, centered composition",
    "close-up detail shot, macro perspective",
    "overhead flat lay, top-down angle",
    "side angle, rule of thirds composition",
    "slightly low angle, looking up perspective",
]

# IT/금융 키워드 분류 (goodisak용)
_GOODISAK_FINANCE_KW = {
    "포인트", "페이", "카드", "통장", "환급", "지원금", "대출", "금융",
    "현금", "계좌", "적금", "수익", "주식", "펀드", "보험", "세금",
    "신용", "체크카드", "캐시백", "환전",
}


def _get_prompt_style(blog_id: str, prompt: str) -> str:
    """블로그 + 프롬프트 내용에 따라 이미지 스타일 반환."""
    if blog_id == "goodisak":
        if any(kw in prompt for kw in _GOODISAK_FINANCE_KW):
            return _PROMPT_STYLE["goodisak_finance"]
        return _PROMPT_STYLE["goodisak_IT"]
    return _PROMPT_STYLE.get(blog_id, "photorealistic photography, high quality, 4K")


_GEMINI_PERSON_TRIGGERS = [
    "공연", "탈춤", "퍼포먼스", "performance", "dancer", "dancers", "people", "person",
    "crowd", "audience", "festival performance", "무용", "무희", "인물", "사람",
    "행사", "parade", "마당놀이",
]

def _sanitize_prompt_for_gemini(prompt: str) -> str:
    """Gemini 이미지 생성 시 사람/공연 관련 단어 감지 → 장소/풍경 위주로 변환.

    콘텐츠 필터 트리거 방지: Gemini는 공연/사람 묘사 프롬프트에 텍스트로 응답하는 경우가 있음.
    """
    p_lower = prompt.lower()
    triggered = any(kw in p_lower or kw in prompt for kw in _GEMINI_PERSON_TRIGGERS)
    if not triggered:
        return prompt
    # 트리거 단어 제거 + "traditional venue, scenic landscape, no people" 추가
    cleaned = prompt
    for kw in _GEMINI_PERSON_TRIGGERS:
        cleaned = re.sub(re.escape(kw), "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip().strip(",").strip()
    return f"{cleaned}, scenic landscape, traditional venue exterior, no people, wide shot"


def _enhance_prompt(blog_id: str, prompt: str, index: int = 1) -> str:
    """원본 프롬프트에 블로그별 스타일 + 구도 변형자를 합쳐 강화된 영문 프롬프트 반환."""
    style = _get_prompt_style(blog_id, prompt)
    # index 기반 구도 변형 (0-based 순환)
    composition = _COMPOSITION_VARIANTS[(index - 1) % len(_COMPOSITION_VARIANTS)]
    # Gemini 전용 블로그: 사람/공연 트리거 제거
    if blog_id in ("salim1su", "me1091"):
        prompt = _sanitize_prompt_for_gemini(prompt)
    return f"{prompt}, {composition}, {style}"


# ─── Pollinations API ────────────────────────────────────────────────────
def _pollinations_image(prompt: str, filepath: str, on_log=None) -> bool:
    """Pollinations.ai API로 이미지 1장 생성 후 저장.

    URL: https://image.pollinations.ai/prompt/{encoded}?width=800&height=600&nologo=true
    """
    def log(msg):
        if on_log:
            on_log(msg)

    encoded = urllib.parse.quote(prompt, safe="")
    import time as _t
    _seed = abs(hash(prompt + str(int(_t.time() / 3600)))) % 9999999  # 시간 포함 → 블로그 간 중복 방지
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=600&nologo=true&seed={_seed}"

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            data = resp.read()
        if len(data) < 5000:
            log(f"[Pollinations] 응답 너무 작음: {len(data)}B")
            return False
        Path(filepath).write_bytes(data)
        log(f"[Pollinations] 저장 완료: {Path(filepath).name} ({len(data)//1024}KB)")
        return True
    except Exception as e:
        log(f"[Pollinations] 실패: {e}")
        return False


# ─── 공통 파일명 정리 ────────────────────────────────────────────────────
def _clean_filename(filename: str, skip_webp: bool) -> str:
    filename = re.sub(r'[^\w\-.]', '-', filename)
    filename = re.sub(r'-+', '-', filename).strip('-')
    if skip_webp:
        if not filename.endswith(('.jpg', '.jpeg', '.png')):
            filename = Path(filename).stem + '.jpg'
    else:
        if not filename.endswith('.webp'):
            filename = Path(filename).stem + '.webp'
    return filename


# ─── 메인 라우터 ─────────────────────────────────────────────────────────
def generate_images_for_blog(
    blog_id: str,
    image_infos: list,
    skip_webp: bool = False,
    on_log=None,
    reference_images: list = None,
    title: str = "",
) -> dict:
    """블로그 타입에 따라 이미지 생성 소스를 분기해 이미지 생성.

    Args:
        blog_id:     "salim1su" | "nolja100" | "goodisak" | "baremi542" | "triplog"
        image_infos: [{'index': int, 'prompt': str, 'filename': str}, ...]
        skip_webp:   True면 .jpg 저장 (Naver용)
        on_log:      로그 콜백
        title:       글 제목 — 첫 번째 이미지(썸네일)에 텍스트 오버레이로 삽입

    Returns:
        {index: filepath} 딕셔너리 (성공한 것만)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if not image_infos:
        return {}

    # 프롬프트에 블로그별 스타일 + 구도 변형 적용
    # 파일명은 SEO 최적화: {blog_id}-{keyword_slug}-{index}.{ext}
    def _seo_filename(info: dict, kw_slug: str, skip_webp: bool) -> str:
        idx = info.get('index', 1)
        ext = 'jpg' if skip_webp else 'webp'
        return f"{blog_id}-{kw_slug}-{idx}.{ext}"

    # keyword_slug: 이미지 infos의 alt 또는 prompt 첫 단어로 슬러그 생성
    first_alt = image_infos[0].get('alt', '') or image_infos[0].get('prompt', '')
    kw_slug = re.sub(r'[^\w\s-]', '', first_alt.lower()).strip()
    kw_slug = re.sub(r'[\s_]+', '-', kw_slug)[:30].strip('-') or blog_id

    enhanced_infos = []
    for info in image_infos:
        enhanced = dict(info)
        enhanced['prompt'] = _enhance_prompt(blog_id, info['prompt'], index=info.get('index', 1))
        enhanced['filename'] = _seo_filename(info, kw_slug, skip_webp)
        enhanced_infos.append(enhanced)

    # 블로그별 이미지 저장 폴더
    output_dir = IMAGES_DIR / blog_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Gemini 전용: Naver 블로그만 (salim1su, me1091)
    # Tistory(nolja100, goodisak) / WP(baremi542, triplog) → Bing 4장 모드
    is_gemini_only = blog_id in ("salim1su", "me1091")

    if is_gemini_only:
        results = _generate_naver(enhanced_infos, skip_webp, log, reference_images=reference_images, output_dir=output_dir)
    else:
        results = _generate_other(enhanced_infos, skip_webp, log, output_dir=output_dir)

    return results


def generate_thumbnail(blog_id: str, keyword: str, title: str, on_log=None) -> str | None:
    """썸네일 1장 별도 생성 + 제목 오버레이 적용. 성공 시 파일 경로 반환."""
    def log(msg):
        if on_log:
            on_log(msg)

    style = _get_prompt_style(blog_id, keyword)
    composition = _COMPOSITION_VARIANTS[0]  # 썸네일은 wide shot 고정
    thumb_prompt = f"{keyword} representative thumbnail image, {composition}, {style}"

    output_dir = IMAGES_DIR / blog_id
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_kw = re.sub(r'[^\w\s-]', '', keyword).replace(' ', '-').lower()[:30]
    thumb_filename = f"thumb-{safe_kw}-{int(time.time()) % 100000}.jpg"
    thumb_path = str(output_dir / thumb_filename)

    is_gemini_only = blog_id in ("salim1su", "me1091")
    success = False

    if is_gemini_only:
        try:
            from gemini_image import generate_images as _gemini_gen
            thumb_infos = [{"index": 1, "prompt": thumb_prompt, "filename": thumb_filename, "alt": keyword}]
            res = _gemini_gen(thumb_infos, on_log=log, skip_webp=True, output_dir=output_dir)
            if res and 1 in res:
                thumb_path = res[1]
                success = True
                log(f"[썸네일] Gemini 생성 완료")
        except Exception as e:
            log(f"[썸네일] Gemini 실패: {e}")

    if not success:
        try:
            from bing_image import generate_images_bing as _bing_gen
            thumb_infos = [{"index": 1, "prompt": thumb_prompt, "filename": thumb_filename, "alt": keyword}]
            res = _bing_gen(thumb_infos, on_log=log, output_dir=output_dir)
            if res and 1 in res:
                thumb_path = res[1]
                success = True
                log(f"[썸네일] Bing 생성 완료")
        except Exception as e:
            log(f"[썸네일] Bing 실패: {e}")

    if not success:
        success = _pollinations_image(thumb_prompt, thumb_path, on_log=log)
        if success:
            log(f"[썸네일] Pollinations 생성 완료")

    if success and Path(thumb_path).exists():
        add_title_overlay(thumb_path, title, blog_id=blog_id, on_log=log)
        log(f"[썸네일] 오버레이 적용 완료: {thumb_filename}")
        return thumb_path

    log(f"[썸네일] 생성 실패")
    return None


def _generate_naver(image_infos: list, skip_webp: bool, log, reference_images: list = None, output_dir=None) -> dict:
    """Naver(salim1su/me1091): Gemini만 사용. 실패 시 최대 3회 재시도."""
    import time as _t
    try:
        from gemini_image import generate_images, _quota_blocked_until
    except Exception as e:
        log(f"[Router] Gemini import 오류: {e}")
        return {}

    for attempt in range(1, 4):
        try:
            blocked = _quota_blocked_until()
            if blocked:
                wait_sec = (blocked - __import__('datetime').datetime.now()).total_seconds()
                if wait_sec > 0:
                    log(f"[Router] Gemini 쿼터 차단 — {blocked.strftime('%H:%M')} 해제 예정, {int(wait_sec)}초 대기 후 재시도")
                    _t.sleep(min(wait_sec + 5, 300))  # 최대 5분만 대기
                    continue

            log(f"[Router] Naver: Gemini 시도 ({attempt}/3)")
            results = generate_images(image_infos, on_log=log, skip_webp=skip_webp,
                                      reference_images=reference_images, output_dir=output_dir)
            if results:
                log(f"[Router] Gemini 성공: {len(results)}장")
                return results

            log(f"[Router] Gemini {attempt}회 실패" + (" — 재시도" if attempt < 3 else " — 포기"))
            if attempt < 3:
                _t.sleep(30)

        except Exception as e:
            log(f"[Router] Gemini 오류 ({attempt}/3): {e}")
            if attempt < 3:
                _t.sleep(30)

    log("[Router] Naver: Gemini 3회 모두 실패 — 이미지 없이 진행 불가")
    return {}


def _loremflickr_image(prompt: str, filepath: str, on_log=None) -> bool:
    """loremflickr.com 스톡 이미지 다운로드 (Tistory/WP 전용 최후 폴백)."""
    import urllib.request, urllib.parse
    keyword = urllib.parse.quote(prompt.split(',')[0].replace(' ', ',')[:50])
    url = f"https://loremflickr.com/1024/768/{keyword}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if len(data) < 5000:
            return False
        with open(filepath, 'wb') as f:
            f.write(data)
        if on_log:
            on_log(f"[Router] loremflickr 성공: {filepath}")
        return True
    except Exception as e:
        if on_log:
            on_log(f"[Router] loremflickr 실패: {e}")
        return False


def _try_loremflickr(image_infos: list, log, output_dir=None) -> dict:
    save_dir = Path(output_dir) if output_dir else IMAGES_DIR
    save_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for info in image_infos:
        idx = info['index']
        filepath = str(save_dir / info['filename'])
        log(f"[Router] loremflickr [{idx}]: {info['prompt'][:50]}")
        if _loremflickr_image(info['prompt'], filepath, on_log=log):
            results[idx] = filepath
        time.sleep(1)
    return results


def _generate_other(image_infos: list, skip_webp: bool, log, output_dir=None) -> dict:
    """Tistory/WP: Bing만 사용. 실패 시 스킵 (Pollinations/loremflickr 금지 — 엉뚱한 이미지 방지)"""
    bing_res = _try_bing(image_infos, skip_webp, log, output_dir=output_dir)
    if bing_res:
        failed = [info for info in image_infos if info['index'] not in bing_res]
        if failed:
            log(f"[Router] Bing 실패 {len(failed)}장 → 스킵 (폴백 없음)")
        return bing_res

    log("[Router] Bing 전체 실패 → 스킵 (폴백 없음)")
    return {}


def _try_bing(image_infos: list, skip_webp: bool, log, output_dir=None) -> dict:
    """Bing Image Creator로 이미지 생성 시도."""
    try:
        from bing_image import generate_images_bing
        log(f"[Router] Bing Image Creator 시도: {len(image_infos)}장")
        results = generate_images_bing(image_infos, skip_webp=skip_webp, on_log=log, output_dir=output_dir)
        return results or {}
    except Exception as e:
        log(f"[Router] Bing 오류: {e}")
        return {}


def _try_pollinations(image_infos: list, log, output_dir=None) -> dict:
    """Pollinations API로 이미지 생성 시도."""
    save_dir = Path(output_dir) if output_dir else IMAGES_DIR
    save_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for info in image_infos:
        idx = info['index']
        prompt = info['prompt']
        filepath = str(save_dir / info['filename'])
        log(f"[Router] Pollinations [{idx}]: {prompt[:60]}")
        ok = _pollinations_image(prompt, filepath, on_log=log)
        if ok:
            results[idx] = filepath
        else:
            log(f"[Router] Pollinations [{idx}] 실패")
        time.sleep(1)
    return results


if __name__ == '__main__':
    # 테스트
    result = generate_images_for_blog(
        blog_id="goodisak",
        image_infos=[
            {'index': 1, 'prompt': '노트북 화면에 코딩 화면', 'filename': 'test_goodisak1.jpg'},
        ],
        skip_webp=True,
        on_log=print,
    )
    print('결과:', result)
