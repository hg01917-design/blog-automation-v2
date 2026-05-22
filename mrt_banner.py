"""마이리얼트립 제휴 쿠폰 배너 — 여행 블로그 본문 중간 삽입

흐름:
  키워드 → MRT 검색 URL 구성 → create_affiliate_link API → 배너 HTML 블록 → 본문 중간 삽입

지원 블로그: nolja100, triplog, blogspot_travel
"""
import re
import urllib.parse
import urllib.request
import hashlib
from pathlib import Path

from PIL import Image, ImageOps


# 공정위 고지 문구
_DISCLOSURE = "이 글에는 마이리얼트립 파트너스 제휴 링크가 포함되어 있으며, 예약 시 소정의 수수료를 받을 수 있습니다."

# 플랫폼별 배너 CTA 문구
_CTA = {
    "nolja100":       "👉 마이리얼트립에서 할인 확인하기",
    "triplog":        "👉 마이리얼트립 최저가 예약",
    "blogspot_travel":"👉 마이리얼트립 예약 바로가기",
}

_FIXED_AFFILIATE_URL = "https://myrealt.rip/ZYUtd2"
_MRT_IMG_DIR = Path(__file__).parent / "images" / "mrt"


def _build_banner_html(affiliate_url: str, keyword: str, blog_id: str) -> str:
    """플랫폼 공통 HTML 배너 블록 반환 (Tistory/WP/Blogspot 모두 호환)."""
    cta = _CTA.get(blog_id, "👉 마이리얼트립에서 예약하기")
    return (
        f'\n<div style="border:2px solid #FF4B4B;border-radius:12px;padding:20px;'
        f'text-align:center;background:#FFF8F8;margin:24px 0;">\n'
        f'<p style="font-size:12px;color:#999;margin:0 0 6px;">{_DISCLOSURE}</p>\n'
        f'<p style="font-weight:bold;font-size:17px;margin:0 0 14px;">'
        f'🎫 {keyword} 여행 — 마이리얼트립 최저가</p>\n'
        f'<a href="{affiliate_url}" target="_blank" rel="noopener sponsored" '
        f'style="display:inline-block;background:#FF4B4B;color:#fff;'
        f'padding:12px 28px;border-radius:8px;font-weight:bold;'
        f'font-size:15px;text-decoration:none;">{cta}</a>\n'
        f'</div>\n'
    )


def _extract_mrt_image_urls(body: str) -> list[str]:
    return re.findall(r'https?://[^\s"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^\s"\']*)?', body or "", flags=re.IGNORECASE)


def _download_and_convert_webp(img_url: str, seed: str, idx: int, on_log=None) -> str:
    def log(msg):
        if on_log:
            on_log(msg)
    _MRT_IMG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=20).read()
        digest = hashlib.sha1((seed + img_url + str(len(raw))).encode()).hexdigest()[:12]
        out_name = f"mrt_{idx:02d}_{digest}.webp"
        out_path = _MRT_IMG_DIR / out_name
    except Exception as e:
        log(f"[MRT배너] 이미지 다운로드 실패: {e}")
        return ""

    try:
        tmp_path = _MRT_IMG_DIR / f"_tmp_{idx}.bin"
        tmp_path.write_bytes(raw)
        with Image.open(tmp_path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            w, h = im.size
            if w > 1600:
                nh = int(h * (1600 / w))
                im = im.resize((1600, nh), Image.LANCZOS)
            im.save(out_path, format="WEBP", quality=84, method=6)
        tmp_path.unlink(missing_ok=True)
        log(f"[MRT배너] 이미지 저장(webp): {out_path}")
        return str(out_path)
    except Exception as e:
        log(f"[MRT배너] 이미지 변환 실패: {e}")
        return ""


def _build_review_block(keyword: str, affiliate_url: str) -> str:
    return (
        "\n<div style=\"border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin:18px 0;background:#f8fbff;\">\n"
        f"<p style=\"margin:0 0 8px;font-weight:700;\">{keyword} 상품 정보·리뷰 요약</p>\n"
        "<ul style=\"margin:0;padding-left:18px;line-height:1.75;\">\n"
        "<li>상품 안내에 나온 핵심 포함사항/이용 조건을 먼저 확인하세요.</li>\n"
        "<li>리뷰에서는 대기 시간, 동선, 예약 타이밍 관련 포인트가 자주 언급됩니다.</li>\n"
        "<li>후기를 종합하면 피크 시간대 회피와 사전 예약이 만족도에 큰 영향을 줍니다.</li>\n"
        "</ul>\n"
        f"<p style=\"margin:10px 0 0;\"><a href=\"{affiliate_url}\" target=\"_blank\" rel=\"noopener sponsored\" style=\"font-weight:700;color:#0b63ce;\">👉 할인/예약 링크 바로가기</a></p>\n"
        "</div>\n"
    )


def _find_insert_point(body: str) -> int:
    """본문 중간 삽입 위치(줄 인덱스) 반환.

    우선순위:
      1. 전체 H2 목록 중 두 번째 H2 바로 뒤
      2. 없으면 전체 줄 수 절반 지점
    """
    lines = body.split('\n')
    h2_indices = [i for i, l in enumerate(lines) if re.match(r'^##\s', l)]
    if len(h2_indices) >= 2:
        return h2_indices[1] + 1  # 두 번째 H2 직후
    if len(h2_indices) == 1:
        return h2_indices[0] + 1
    return len(lines) // 2


def insert_mrt_banner(body: str, keyword: str, blog_id: str = "", on_log=None) -> str:
    """여행 글 본문 중간에 마이리얼트립 제휴 쿠폰 배너를 삽입한다.

    Args:
        body:     원본 본문 (마크다운/혼합)
        keyword:  글 키워드 또는 제목 (검색어로 사용)
        blog_id:  "nolja100" | "triplog" | "blogspot_travel"
        on_log:   로그 콜백

    Returns:
        배너가 삽입된 본문 문자열
    """
    def log(msg):
        if on_log:
            on_log(msg)
        else:
            print(msg, flush=True)

    # 검색 키워드: 첫 단어(지명) 추출
    search_kw = re.split(r'[\s,]+', keyword.strip())[0] if keyword.strip() else keyword
    search_url = f"https://www.myrealtrip.com/offers?q={urllib.parse.quote(search_kw)}"

    # 제휴 링크 고정
    affiliate_url = _FIXED_AFFILIATE_URL
    log(f"[MRT배너] 고정 제휴 링크 사용: {affiliate_url}")

    # 본문 내 이미지 URL이 있으면 전부 webp 저장 시도
    image_urls = _extract_mrt_image_urls(body)
    if image_urls:
        log(f"[MRT배너] 원본 이미지 URL 감지: {len(image_urls)}개")
    saved = 0
    for i, u in enumerate(image_urls, start=1):
        if _download_and_convert_webp(u, seed=search_kw or "mrt", idx=i, on_log=log):
            saved += 1
    if image_urls:
        log(f"[MRT배너] webp 저장 완료: {saved}/{len(image_urls)}")

    banner_html = _build_banner_html(affiliate_url, search_kw, blog_id)
    review_html = _build_review_block(search_kw, affiliate_url)

    lines = body.split('\n')
    insert_at = _find_insert_point(body)
    lines.insert(insert_at, banner_html)
    lines.insert(insert_at + 1, review_html)
    log(f"[MRT배너] ✅ 배너 삽입 완료 (줄 {insert_at})")
    return '\n'.join(lines)
