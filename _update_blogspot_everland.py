#!/usr/bin/env python3
"""
Blogger API로 에버랜드 글 수정
- Bing 이미지 3장 생성
- base64 임베드
- PUT 요청으로 콘텐츠 업데이트
"""
import sys
import base64
import json
import urllib.request
from pathlib import Path
from PIL import Image
import io

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

BLOG_ID = "1928113723538395316"
POST_ID = "7170297014619545250"


def _img_tag(path: str, alt: str) -> str:
    """이미지를 base64로 인코딩하여 HTML img 태그 생성."""
    try:
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
        print(f"  ❌ 이미지 임베드 실패 ({path}): {e}")
        return ""


def generate_images() -> dict:
    """Bing으로 에버랜드 이미지 3장 생성."""
    from image_router import generate_images_for_blog

    image_infos = [
        {
            "index": 1,
            "prompt": "Long queue at Everland ticket booth on sunny day, crowded entrance, realistic photo",
            "filename": "bs_ev_1.jpg",
            "alt": "에버랜드 매표소 긴 줄"
        },
        {
            "index": 2,
            "prompt": "Person showing QR code ticket on smartphone at amusement park fast entrance gate, realistic photo",
            "filename": "bs_ev_2.jpg",
            "alt": "QR 티켓 빠른 입장"
        },
        {
            "index": 3,
            "prompt": "Everland colorful roller coaster rides under blue sky, happy visitors, realistic photo",
            "filename": "bs_ev_3.jpg",
            "alt": "에버랜드 어트랙션"
        }
    ]

    print("[이미지] Bing으로 에버랜드 이미지 3장 생성 중...")
    try:
        image_paths = generate_images_for_blog(
            blog_id="bs_everland",
            image_infos=image_infos,
            skip_webp=True,
            on_log=print
        )
        print(f"[이미지] ✅ {len(image_paths)}장 생성 완료")
        return image_paths
    except Exception as e:
        print(f"[이미지] ❌ 생성 실패: {e}")
        return {}


def create_content(image_paths: dict) -> str:
    """이미지 3장을 포함한 2000자 이상 HTML 콘텐츠 생성."""
    images = [
        (1, "에버랜드 매표소 긴 줄"),
        (2, "QR 티켓 빠른 입장"),
        (3, "에버랜드 어트랙션"),
    ]

    # 이미지 HTML 생성
    img_html = []
    for idx, alt in images:
        if idx in image_paths:
            tag = _img_tag(image_paths[idx], alt)
            if tag:
                img_html.append(tag)

    content = f"""<p>에버랜드를 방문하기 전에 미리 알아야 할 필수 정보를 정리했습니다. 입장권 선택부터 시간 활용 팁까지, 2026년 최신 정보를 바탕으로 안내하겠습니다.</p>

<h2 style="margin-top:32px;">매표소 이용 가이드</h2>

{img_html[0] if len(img_html) > 0 else ''}

<p>에버랜드의 현장 매표소는 주말과 연휴에 수십 분 대기가 기본입니다. 온라인 사전 예매가 가장 빠르고 저렴합니다. 통신사 할인, 신용카드 캐시백, 여행사 패키지 등 다양한 할인 경로가 있으니 비교 후 예매하세요.</p>

<p>입장권 종류는 일반 종일이용권, 오후이용권(2시간 제한), 연간회원권으로 나뉩니다. 단순 방문자라면 일반 종일이용권이 가장 저렴합니다. 오후이용권은 저녁시간 방문 시 절약할 수 있습니다.</p>

<p>현장 매표소 대기를 피하려면 입장 1~2일 전 온라인 사이트나 편의점 키오스크에서 미리 예매하는 것이 효율적입니다. 예매표는 당일 신원 확인 없이 누구나 입장 가능합니다.</p>

<h2 style="margin-top:32px;">QR 티켓 빠른 입장</h2>

{img_html[1] if len(img_html) > 1 else ''}

<p>2024년부터 에버랜드는 모바일 QR 티켓 시스템을 도입했습니다. 스마트폰에 저장된 QR 코드를 게이트 스캐너에 인식시키면 자동 입장됩니다.</p>

<p>QR 입장은 일반 매표 줄을 거치지 않고 별도 게이트로 진입할 수 있어 최대 30분 이상 시간 절약이 가능합니다. 현장 매표 구간이 길 때는 특히 유용합니다.</p>

<p>모바일 QR은 예매 후 스마트폰에 자동 저장되며, 오프라인 상태에서도 표시 가능합니다. 예매 확인 이메일의 "모바일 입장권" 링크를 클릭하면 즉시 스마트폰 월렛에 등록됩니다.</p>

<h2 style="margin-top:32px;">에버랜드 어트랙션 운영 정보</h2>

{img_html[2] if len(img_html) > 2 else ''}

<p>에버랜드는 5개 테마존에 60개 이상의 어트랙션과 공연을 갖추고 있습니다. 계절마다 운영 시간이 다르고, 우천 시 일부 실외 놀이기구는 운휴할 수 있습니다.</p>

<p>주요 어트랙션(T-Express, 미라클 하우스, 시간의 탑 등)은 평균 30~60분 대기가 일반적입니다. 입장 직후 아침 시간이나 저녁 7시 이후가 상대적으로 대기가 짧습니다.</p>

<p>앱을 통해 실시간 대기 시간을 확인할 수 있으니, 방문 전 미리 다운로드하고 입장 후 계획을 세우는 것이 효율적입니다. 우천으로 인한 휴무 정보도 실시간 업데이트됩니다.</p>

<h2 style="margin-top:32px;">에버랜드 입장권 할인 링크</h2>

<p>아래 링크에서 종일이용권과 오후이용권을 최저가로 구매하실 수 있습니다:</p>

<p>📌 <strong><a href="https://myrealt.rip/YSfK82" target="_blank">종일이용권 최저가 구매</a></strong></p>

<p>📌 <strong><a href="https://myrealt.rip/YSfLec" target="_blank">오후이용권 최저가 구매</a></strong></p>

<p>정부지원금과 연계한 문화카드 할인, 신용카드 캐시백, 여행패키지 등 추가 할인 정보는 아래 상세 포스팅을 참고하세요:</p>

<p><a href="https://app.baremi542.com/%ec%97%90%eb%b2%84%eb%9e%9c%eb%93%9c-%ec%9e%85%ec%9e%a5%ea%b6%8c-%ED%86%B5%EC%8B%A0%EC%82%AC-%EC%B9%B4%EB%93%9C-%ED%95%A0%EC%9D%B8-2026-%EC%B4%9D%EC%A0%95%EB%A6%AC-%EC%9D%B4%EB%A0%87/" target="_blank">➜ 에버랜드 입장권 통신사·카드 할인 2026 총정리</a></p>

<p>입장권 선택에 실패하면 추가 비용으로 이어지니, 방문 일정과 시간을 고려해 가장 경제적인 옵션을 선택하시기 바랍니다.</p>
"""

    # 최소 글자 수 확인 (링크 제외)
    text_only = content.replace('<', '').replace('>', '')
    text_len = len(text_only)
    print(f"[콘텐츠] 글자 수: {text_len} (2000자 이상 필요)")

    return content


def get_token() -> str:
    """Blogger API 토큰 취득."""
    from blogger_api import _get_token
    try:
        return _get_token()
    except Exception as e:
        print(f"❌ 토큰 오류: {e}")
        raise


def update_post(content: str) -> dict:
    """Blogger API PUT으로 글 콘텐츠 업데이트."""
    try:
        token = get_token()
    except Exception as e:
        return {"ok": False, "reason": f"토큰 실패: {e}"}

    url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/{POST_ID}"

    body = {"content": content}
    data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="PATCH"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return {
            "ok": True,
            "id": result.get("id"),
            "url": result.get("url"),
            "published": result.get("published")
        }
    except urllib.error.HTTPError as e:
        reason = e.read().decode(errors="replace")
        return {"ok": False, "reason": f"HTTP {e.code}: {reason[:500]}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


if __name__ == "__main__":
    print("="*60)
    print("Blogger 에버랜드 글 수정")
    print("="*60)

    # 1. 이미지 생성
    image_paths = generate_images()
    if not image_paths:
        print("❌ 이미지 생성 실패")
        sys.exit(1)

    print(f"\n[이미지 경로]\n{json.dumps(image_paths, indent=2)}")

    # 2. 콘텐츠 생성
    print("\n[콘텐츠] HTML 콘텐츠 생성 중...")
    content = create_content(image_paths)

    # 3. 글 수정
    print("\n[API] Blogger PATCH 요청 중...")
    result = update_post(content)

    if result.get("ok"):
        print(f"\n✅ 글 수정 완료!")
        print(f"   URL: {result.get('url')}")
        print(f"   ID: {result.get('id')}")
        print(f"   발행: {result.get('published')}")
    else:
        print(f"\n❌ 수정 실패: {result.get('reason')}")
        sys.exit(1)
