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


def add_title_overlay(img_path: str, title: str, on_log=None) -> bool:
    """첫 번째 이미지(썸네일)에 제목 텍스트 오버레이 추가.
    이미지 하단에 반투명 바 + 흰 글씨로 제목 삽입.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    try:
        from PIL import Image, ImageDraw, ImageFont
        import textwrap

        FONT_CANDIDATES = [
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/Library/Fonts/NanumGothicBold.ttf",
            "/Library/Fonts/NanumGothic.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]

        img = Image.open(img_path).convert("RGBA")
        W, H = img.size

        # 폰트 크기: 이미지 너비 기준 자동 계산
        font_size = max(24, int(W * 0.045))
        font = None
        for fp in FONT_CANDIDATES:
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()

        # 제목 줄바꿈 (최대 2줄, 한 줄 20자 기준)
        wrapped = textwrap.wrap(title, width=20)[:2]

        # 텍스트 영역 높이 계산 (줄별 합산)
        dummy = ImageDraw.Draw(img)
        pad_v = int(H * 0.04)
        line_heights = [dummy.textbbox((0, 0), line, font=font)[3] for line in wrapped]
        total_text_h = sum(line_heights) + (len(wrapped) - 1) * 6
        bar_h = total_text_h + pad_v * 2

        # 반투명 어두운 바 (하단)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        bar = ImageDraw.Draw(overlay)
        bar.rectangle([(0, H - bar_h), (W, H)], fill=(0, 0, 0, 170))

        merged = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(merged)

        # 흰 글씨 (각 줄 개별 중앙 정렬)
        pad_v = int(H * 0.04)
        y = H - bar_h + pad_v
        for line in wrapped:
            bbox2 = draw.textbbox((0, 0), line, font=font)
            line_w = bbox2[2] - bbox2[0]
            line_h = bbox2[3] - bbox2[1]
            draw.text(((W - line_w) // 2, y), line, font=font, fill=(255, 255, 255, 255))
            y += line_h + 6

        # 원본 포맷 유지하여 저장
        p = Path(img_path)
        fmt = "JPEG" if p.suffix.lower() in (".jpg", ".jpeg") else \
              "WEBP" if p.suffix.lower() == ".webp" else "PNG"
        if fmt == "JPEG":
            merged.convert("RGB").save(img_path, "JPEG", quality=92)
        else:
            merged.save(img_path, fmt, quality=90)

        log(f"[썸네일] 텍스트 오버레이 완료: {p.name}")
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


def _enhance_prompt(blog_id: str, prompt: str, index: int = 1) -> str:
    """원본 프롬프트에 블로그별 스타일 + 구도 변형자를 합쳐 강화된 영문 프롬프트 반환."""
    style = _get_prompt_style(blog_id, prompt)
    # index 기반 구도 변형 (0-based 순환)
    composition = _COMPOSITION_VARIANTS[(index - 1) % len(_COMPOSITION_VARIANTS)]
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
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=600&nologo=true&seed={abs(hash(prompt)) % 99999}"

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=60, context=ctx)
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
    enhanced_infos = []
    for info in image_infos:
        enhanced = dict(info)
        enhanced['prompt'] = _enhance_prompt(blog_id, info['prompt'], index=info.get('index', 1))
        enhanced['filename'] = _clean_filename(info['filename'], skip_webp)
        enhanced_infos.append(enhanced)

    is_naver = blog_id in ("salim1su", "me1091")

    if is_naver:
        results = _generate_naver(enhanced_infos, skip_webp, log, reference_images=reference_images)
    else:
        results = _generate_other(enhanced_infos, skip_webp, log)

    # 첫 번째 이미지(썸네일)에 제목 텍스트 오버레이
    if title and results:
        first_key = min(results.keys())
        first_path = results[first_key]
        if first_path and Path(first_path).exists():
            add_title_overlay(first_path, title, on_log=log)

    return results


def _generate_naver(image_infos: list, skip_webp: bool, log, reference_images: list = None) -> dict:
    """Naver(salim1su/me1091): Gemini → Bing → Pollinations"""
    # 1단계: Gemini
    try:
        from gemini_image import generate_images, _quota_blocked_until
        blocked = _quota_blocked_until()
        if not blocked:
            log("[Router] Naver: Gemini 시도")
            results = generate_images(image_infos, on_log=log, skip_webp=skip_webp,
                                      reference_images=reference_images)
            if results:
                log(f"[Router] Gemini 성공: {len(results)}장")
                # 실패한 것만 폴백
                failed = [info for info in image_infos if info['index'] not in results]
                if not failed:
                    return results
                log(f"[Router] Gemini 실패 {len(failed)}장 → Bing 폴백")
                bing_res = _try_bing(failed, skip_webp, log)
                results.update(bing_res)
                # 여전히 실패한 것 → Pollinations
                still_failed = [info for info in failed if info['index'] not in bing_res]
                if still_failed:
                    poll_res = _try_pollinations(still_failed, log)
                    results.update(poll_res)
                return results
        else:
            log(f"[Router] Gemini 쿼터 차단({blocked.strftime('%m/%d %H:%M')}) → Bing 시도")
    except Exception as e:
        log(f"[Router] Gemini 오류: {e}")

    # 2단계: Bing(Copilot)
    bing_res = _try_bing(image_infos, skip_webp, log)
    if bing_res:
        failed = [info for info in image_infos if info['index'] not in bing_res]
        if not failed:
            return bing_res
        log(f"[Router] Bing 실패 {len(failed)}장 → Pollinations 폴백")
        poll_res = _try_pollinations(failed, log)
        bing_res.update(poll_res)
        return bing_res

    # 3단계: Pollinations
    log("[Router] Bing 전체 실패 → Pollinations 폴백")
    return _try_pollinations(image_infos, log)


def _generate_other(image_infos: list, skip_webp: bool, log) -> dict:
    """Tistory/WP: Bing → Pollinations (Gemini 사용 안 함)"""
    # 1단계: Bing(Copilot)
    bing_res = _try_bing(image_infos, skip_webp, log)
    if bing_res:
        failed = [info for info in image_infos if info['index'] not in bing_res]
        if not failed:
            return bing_res
        log(f"[Router] Bing 실패 {len(failed)}장 → Pollinations 폴백")
        poll_res = _try_pollinations(failed, log)
        bing_res.update(poll_res)
        return bing_res

    # 2단계: Pollinations
    log("[Router] Bing 전체 실패 → Pollinations 폴백")
    return _try_pollinations(image_infos, log)


def _try_bing(image_infos: list, skip_webp: bool, log) -> dict:
    """Bing Image Creator로 이미지 생성 시도."""
    try:
        from bing_image import generate_images_bing
        log(f"[Router] Bing Image Creator 시도: {len(image_infos)}장")
        results = generate_images_bing(image_infos, skip_webp=skip_webp, on_log=log)
        return results or {}
    except Exception as e:
        log(f"[Router] Bing 오류: {e}")
        return {}


def _try_pollinations(image_infos: list, log) -> dict:
    """Pollinations API로 이미지 생성 시도."""
    results = {}
    for info in image_infos:
        idx = info['index']
        prompt = info['prompt']
        filepath = str(IMAGES_DIR / info['filename'])
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
