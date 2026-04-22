"""마이리얼트립 제휴 쿠폰 배너 — 여행 블로그 본문 중간 삽입

흐름:
  키워드 → MRT 검색 URL 구성 → create_affiliate_link API → 배너 HTML 블록 → 본문 중간 삽입

지원 블로그: nolja100, triplog, blogspot_travel
"""
import re
import urllib.parse
from pathlib import Path


# 공정위 고지 문구
_DISCLOSURE = "이 글에는 마이리얼트립 파트너스 제휴 링크가 포함되어 있으며, 예약 시 소정의 수수료를 받을 수 있습니다."

# 플랫폼별 배너 CTA 문구
_CTA = {
    "nolja100":       "👉 마이리얼트립에서 할인 확인하기",
    "triplog":        "👉 마이리얼트립 최저가 예약",
    "blogspot_travel":"👉 마이리얼트립 예약 바로가기",
}


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

    try:
        from mrt_affiliate import create_affiliate_link
    except Exception as e:
        log(f"[MRT배너] import 오류: {e} — 스킵")
        return body

    # 검색 키워드: 첫 단어(지명) 추출
    search_kw = re.split(r'[\s,]+', keyword.strip())[0] if keyword.strip() else keyword
    search_url = f"https://www.myrealtrip.com/offers?q={urllib.parse.quote(search_kw)}"

    log(f"[MRT배너] 제휴 링크 생성: '{search_kw}' → {search_url}")
    affiliate_url = create_affiliate_link(search_url, on_log=log)

    if not affiliate_url:
        log("[MRT배너] 제휴 링크 생성 실패 — 원본 URL 사용")
        affiliate_url = search_url

    banner_html = _build_banner_html(affiliate_url, search_kw, blog_id)

    lines = body.split('\n')
    insert_at = _find_insert_point(body)
    lines.insert(insert_at, banner_html)
    log(f"[MRT배너] ✅ 배너 삽입 완료 (줄 {insert_at})")
    return '\n'.join(lines)
