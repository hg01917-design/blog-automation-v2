"""이슈봇 전용 PIL 인포그래픽 카드 생성기

PPT 슬라이드 스타일의 카드 이미지를 생성합니다.
Gemini/Bing API 없이 로컬에서 무제한 생성 가능.

카드 3종:
  1. 타이틀 카드  — 제목 + 핵심 키워드 (썸네일용)
  2. 정보 카드    — 소제목 + 핵심 요점 3~4개 (본문 중간)
  3. 정리 카드   — 핵심 요약 / 액션 포인트 (본문 끝)
"""
import re
import os
import hashlib
import textwrap
from pathlib import Path
from datetime import datetime

# 카드 크기
CARD_W = 1200
CARD_H = 750

# 폰트 경로 (AppleSDGothicNeo 우선, 없으면 Nanum/Arial)
_FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
_FONT_FALLBACKS = [
    "/Library/Fonts/NanumGothicBold.ttf",
    "/Library/Fonts/NanumGothic.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]

# 이슈봇 색상 팔레트 (카드별 다른 배경색)
_PALETTES = [
    # (bg_top, bg_bottom, accent, text_main, text_sub)
    ((15, 55, 120), (5, 30, 75), (255, 180, 0), (255, 255, 255), (200, 220, 255)),     # 딥 블루
    ((30, 100, 80), (10, 60, 50), (150, 255, 180), (255, 255, 255), (200, 255, 230)),   # 딥 그린
    ((100, 30, 80), (60, 15, 50), (255, 150, 200), (255, 255, 255), (255, 200, 230)),   # 딥 퍼플
    ((120, 60, 15), (70, 30, 5), (255, 210, 100), (255, 255, 255), (255, 235, 180)),    # 딥 오렌지
    ((25, 70, 110), (10, 40, 70), (100, 200, 255), (255, 255, 255), (180, 225, 255)),   # 스틸 블루
]

# 블로그별 고정 팔레트 (None이면 키워드 해시 자동 선택)
BLOG_PALETTE = {
    "baremi542": (20, 50, 100),   # 공식/정부 느낌 — 딥 네이비 계열 (팔레트 0 기반 커스텀)
    "issue01":   None,            # 자동
}

# baremi542 전용 팔레트 (정부/복지 공식 느낌)
_PALETTE_BAREMI542 = (
    (15, 40, 90),    # bg_top  — 딥 네이비
    (5, 20, 55),     # bg_bot
    (255, 200, 50),  # accent  — 골드
    (255, 255, 255), # text_main
    (200, 215, 255), # text_sub
)


def _get_font(size: int, bold: bool = True):
    from PIL import ImageFont
    idx = 6 if bold else 0
    try:
        return ImageFont.truetype(_FONT_PATH, size, index=idx)
    except Exception:
        pass
    for fp in _FONT_FALLBACKS:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_gradient_bg(draw, W: int, H: int, color_top: tuple, color_bottom: tuple):
    """세로 그라디언트 배경 그리기."""
    for y in range(H):
        t = y / H
        r = int(color_top[0] * (1 - t) + color_bottom[0] * t)
        g = int(color_top[1] * (1 - t) + color_bottom[1] * t)
        b = int(color_top[2] * (1 - t) + color_bottom[2] * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))


def _draw_text_shadow(draw, pos, text, font, fill=(255, 255, 255), shadow=(0, 0, 0, 140)):
    """그림자 있는 텍스트 그리기."""
    draw.text((pos[0] + 3, pos[1] + 3), text, font=font, fill=shadow)
    draw.text(pos, text, font=font, fill=fill)


def _multiline_center(draw, W: int, y: int, lines: list, font, fill, line_gap: int = 14) -> int:
    """여러 줄 텍스트 중앙 정렬. 다음 y 위치 반환."""
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font)
        lw = bb[2] - bb[0]
        lh = bb[3] - bb[1]
        _draw_text_shadow(draw, ((W - lw) // 2, y), line, font, fill=fill)
        y += lh + line_gap
    return y


def _extract_bullets(body: str, max_count: int = 4) -> list:
    """본문에서 핵심 요점 추출."""
    bullets = []

    # H2 소제목 추출
    h2s = re.findall(r'##H2:([^#]+)##', body)
    for h in h2s[:max_count]:
        clean = h.strip()
        if clean and len(clean) >= 4:
            bullets.append(clean)

    # 부족하면 문장에서 추출 (마침표로 끝나는 짧은 문장)
    if len(bullets) < max_count:
        sentences = re.split(r'[.。!?]\s+', re.sub(r'##[^#]+##|\{\{[^}]+\}\}', '', body))
        for s in sentences:
            s = s.strip()
            if 10 <= len(s) <= 40 and s not in bullets:
                bullets.append(s)
            if len(bullets) >= max_count:
                break

    return bullets[:max_count]


# ─── 카드 1: 타이틀 카드 ──────────────────────────────────────────────────────
def _card_title(title: str, keyword: str, palette: tuple, save_path: str) -> str:
    """타이틀 카드 — 제목 중앙 크게 + 키워드 배지 + 날짜."""
    from PIL import Image, ImageDraw
    import textwrap

    bg_top, bg_bot, accent, text_main, text_sub = palette

    img = Image.new("RGB", (CARD_W, CARD_H), bg_top)
    draw = ImageDraw.Draw(img)
    _draw_gradient_bg(draw, CARD_W, CARD_H, bg_top, bg_bot)

    # 좌우 장식 세로선
    for dx, alpha in [(0, 60), (1, 120), (2, 200), (3, 120), (4, 60)]:
        draw.line([(dx + 40, 60), (dx + 40, CARD_H - 60)], fill=(*accent, alpha))
        draw.line([(CARD_W - 40 - dx, 60), (CARD_W - 40 - dx, CARD_H - 60)], fill=(*accent, alpha))

    # 상단 키워드 배지
    badge_font = _get_font(32, bold=False)
    badge_text = f"  📌 {keyword}  "
    bb = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bb[2] - bb[0] + 20
    bh = bb[3] - bb[1] + 16
    bx = (CARD_W - bw) // 2
    by = 80
    draw.rounded_rectangle([(bx, by), (bx + bw, by + bh)], radius=bh // 2, fill=accent)
    draw.text((bx + 10, by + 8), badge_text.strip(), font=badge_font, fill=bg_top)

    # 제목 (중앙)
    title_font = _get_font(72, bold=True)
    wrapped = textwrap.wrap(title, width=16)[:3]
    lhs = [draw.textbbox((0, 0), l, font=title_font)[3] for l in wrapped]
    total_h = sum(lhs) + (len(wrapped) - 1) * 20
    y = (CARD_H - total_h) // 2 + 20
    _multiline_center(draw, CARD_W, y, wrapped, title_font, fill=text_main, line_gap=20)

    # 하단 날짜
    date_font = _get_font(30, bold=False)
    date_str = datetime.now().strftime("%Y.%m.%d")
    bb = draw.textbbox((0, 0), date_str, font=date_font)
    draw.text(
        ((CARD_W - (bb[2] - bb[0])) // 2, CARD_H - 70),
        date_str, font=date_font, fill=(*text_sub, 180)
    )

    # 하단 가로선
    for dy in range(3):
        draw.line([(80, CARD_H - 90 + dy), (CARD_W - 80, CARD_H - 90 + dy)],
                  fill=(*accent, 80 + dy * 40))

    img.save(save_path, "JPEG", quality=90)
    return save_path


# ─── 카드 2: 정보 카드 ──────────────────────────────────────────────────────
def _card_info(title: str, bullets: list, palette: tuple, save_path: str) -> str:
    """정보 카드 — 소제목 + 요점 3~4개 (체크리스트 스타일)."""
    from PIL import Image, ImageDraw
    import textwrap

    bg_top, bg_bot, accent, text_main, text_sub = palette

    img = Image.new("RGB", (CARD_W, CARD_H), (250, 252, 255))
    draw = ImageDraw.Draw(img)

    # 흰 배경 + 상단 컬러 헤더
    header_h = int(CARD_H * 0.22)
    _draw_gradient_bg(draw, CARD_W, header_h, bg_top, bg_bot)

    # 헤더 제목
    h_font = _get_font(52, bold=True)
    wrapped_h = textwrap.wrap(title, width=20)[:2]
    lhs = [draw.textbbox((0, 0), l, font=h_font)[3] for l in wrapped_h]
    total_h = sum(lhs) + (len(wrapped_h) - 1) * 12
    y = (header_h - total_h) // 2
    _multiline_center(draw, CARD_W, y, wrapped_h, h_font, fill=text_main, line_gap=12)

    # 좌측 악센트 세로선
    for dx in range(5):
        alpha = 60 + dx * 40
        draw.line([(50 + dx, header_h + 30), (50 + dx, CARD_H - 50)],
                  fill=(*bg_top, alpha))

    # 요점 목록
    item_font = _get_font(42, bold=True)
    sub_font = _get_font(34, bold=False)
    y = header_h + 50
    icons = ["①", "②", "③", "④"]
    for i, bullet in enumerate(bullets[:4]):
        icon = icons[i] if i < len(icons) else "•"
        # 아이콘 배지
        icon_font = _get_font(38, bold=True)
        bb = draw.textbbox((0, 0), icon, font=icon_font)
        iw = bb[2] - bb[0] + 16
        ih = bb[3] - bb[1] + 12
        draw.rounded_rectangle([(80, y + 4), (80 + iw, y + ih + 4)],
                                radius=ih // 2, fill=(*bg_top,))
        draw.text((88, y + 8), icon, font=icon_font, fill=(255, 255, 255))

        # 텍스트
        wrapped_b = textwrap.wrap(bullet, width=28)[:2]
        tx = 80 + iw + 20
        ty = y + 4
        for line in wrapped_b:
            draw.text((tx, ty), line, font=item_font, fill=(30, 40, 60))
            ty += draw.textbbox((0, 0), line, font=item_font)[3] + 6

        y = ty + 22

    img.save(save_path, "JPEG", quality=90)
    return save_path


# ─── 카드 3: 정리 카드 ──────────────────────────────────────────────────────
def _card_summary(title: str, keyword: str, palette: tuple, save_path: str) -> str:
    """정리 카드 — '이것만 기억하세요' 요약 스타일."""
    from PIL import Image, ImageDraw
    import textwrap

    bg_top, bg_bot, accent, text_main, text_sub = palette

    img = Image.new("RGB", (CARD_W, CARD_H), bg_top)
    draw = ImageDraw.Draw(img)
    _draw_gradient_bg(draw, CARD_W, CARD_H, bg_bot, bg_top)

    # 중앙 흰 카드
    cx, cy = CARD_W // 2, CARD_H // 2
    cw, ch = int(CARD_W * 0.78), int(CARD_H * 0.68)
    draw.rounded_rectangle(
        [(cx - cw // 2, cy - ch // 2), (cx + cw // 2, cy + ch // 2)],
        radius=24, fill=(255, 255, 255, 240)
    )

    # "이것만 기억하세요" 상단 배지
    badge_font = _get_font(30, bold=True)
    badge_text = "✅  이것만 기억하세요"
    bb = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bb[2] - bb[0] + 32
    bh = bb[3] - bb[1] + 16
    bx = cx - bw // 2
    by_badge = cy - ch // 2 + 30
    draw.rounded_rectangle([(bx, by_badge), (bx + bw, by_badge + bh)],
                            radius=bh // 2, fill=bg_top)
    draw.text((bx + 16, by_badge + 8), badge_text, font=badge_font, fill=(255, 255, 255))

    # 키워드 + 제목
    kw_font = _get_font(36, bold=False)
    title_font = _get_font(58, bold=True)
    y = by_badge + bh + 40

    kw_str = f"#{keyword}"
    bb = draw.textbbox((0, 0), kw_str, font=kw_font)
    draw.text(((CARD_W - (bb[2] - bb[0])) // 2, y), kw_str, font=kw_font, fill=(*bg_top,))
    y += bb[3] - bb[1] + 16

    wrapped = textwrap.wrap(title, width=16)[:2]
    for line in wrapped:
        bb = draw.textbbox((0, 0), line, font=title_font)
        lw = bb[2] - bb[0]
        lh = bb[3] - bb[1]
        draw.text(((CARD_W - lw) // 2, y), line, font=title_font, fill=(20, 30, 60))
        y += lh + 12

    # 하단 구분선 + 블로그 이름
    y += 20
    line_y = y
    draw.line([(cx - 180, line_y), (cx + 180, line_y)], fill=(*bg_top, 120), width=2)
    blog_font = _get_font(28, bold=False)
    blog_str = "이슈 정보 블로그"
    bb = draw.textbbox((0, 0), blog_str, font=blog_font)
    draw.text(((CARD_W - (bb[2] - bb[0])) // 2, line_y + 16), blog_str,
              font=blog_font, fill=(100, 110, 130))

    img.save(save_path, "JPEG", quality=90)
    return save_path


# ─── 공개 API ────────────────────────────────────────────────────────────────
def generate_issue_cards(
    title: str,
    keyword: str,
    body: str = "",
    output_dir: Path = None,
    count: int = 3,
    palette_idx: int = None,
    on_log=None,
    **kwargs,
) -> dict:
    """이슈봇용 인포그래픽 카드 3장 생성.

    Args:
        title: 블로그 제목
        keyword: 트렌드 키워드
        body: 본문 (요점 추출용)
        output_dir: 저장 디렉토리 (기본: images/)
        count: 생성할 카드 수 (기본 3)
        palette_idx: 색상 팔레트 인덱스 (None이면 자동)
        on_log: 로그 콜백

    Returns:
        {1: '/path/card1.jpg', 2: '/path/card2.jpg', 3: '/path/card3.jpg'}
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if output_dir is None:
        output_dir = Path(__file__).parent / "images"
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    # 팔레트 선택
    if palette_idx is None:
        # blog_id 파라미터가 있으면 전용 팔레트, 없으면 키워드 해시로 자동
        _blog_id = kwargs.get("blog_id", "")
        if _blog_id == "baremi542":
            palette = _PALETTE_BAREMI542
        else:
            palette_idx = int(hashlib.md5(keyword.encode()).hexdigest(), 16) % len(_PALETTES)
            palette = _PALETTES[palette_idx]
    else:
        palette = _PALETTES[palette_idx % len(_PALETTES)]

    bullets = _extract_bullets(body, max_count=4)
    if not bullets:
        bullets = [f"{keyword} 핵심 정보", "자세한 내용 확인", "생활 활용법", "정리 요약"]

    # 파일명 prefix (중복 방지)
    prefix = f"issue_{hashlib.md5((title + keyword).encode()).hexdigest()[:8]}"

    result = {}
    try:
        # 카드 1: 타이틀
        p1 = str(output_dir / f"{prefix}_card1.jpg")
        _card_title(title, keyword, palette, p1)
        result[1] = p1
        log(f"[카드] 타이틀 카드 생성: {p1}")

        # 카드 2: 정보
        if count >= 2:
            p2 = str(output_dir / f"{prefix}_card2.jpg")
            _card_info(f"{keyword} 핵심 정보", bullets, palette, p2)
            result[2] = p2
            log(f"[카드] 정보 카드 생성: {p2}")

        # 카드 3: 정리
        if count >= 3:
            p3 = str(output_dir / f"{prefix}_card3.jpg")
            _card_summary(title, keyword, palette, p3)
            result[3] = p3
            log(f"[카드] 정리 카드 생성: {p3}")

    except ImportError:
        log("[카드] ⚠ Pillow 미설치 — pip install Pillow")
        return {}
    except Exception as e:
        import traceback
        log(f"[카드] 생성 오류: {e}")
        log(traceback.format_exc())

    log(f"[카드] 총 {len(result)}장 생성 완료")
    return result


if __name__ == "__main__":
    # 테스트 실행
    out = Path(__file__).parent / "images" / "test_cards"
    r = generate_issue_cards(
        title="2026 전기요금 인상 이렇게 대처하세요",
        keyword="전기요금 인상",
        body="""##H2:인상 배경##
전기요금이 올해 두 차례 인상될 예정입니다. {{이미지1}}
##H2:절약 방법##
가전제품 대기전력 차단, 심야시간 세탁기 사용이 효과적입니다. {{이미지2}}
##H2:정부 지원##
에너지 바우처 신청으로 최대 17만원 지원 가능합니다. {{이미지3}}
##H2:체크리스트##
월별 사용량 확인 후 요금제 변경을 고려하세요.""",
        output_dir=out,
        on_log=print,
    )
    print(f"생성된 카드: {r}")
