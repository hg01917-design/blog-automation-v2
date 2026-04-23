"""에버랜드 현장구매 경고 글 — nolja100 Tistory 임시저장 스크립트"""
import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from gemini_image import generate_images
from poster import _post_tistory
from config import ACCOUNT_MAP

def log(msg):
    print(msg, flush=True)

# ── 계정 설정 ──
account = ACCOUNT_MAP["nolja100"]

# ── 글 제목 ──
TITLE = "에버랜드 당일 현장 구매하면 생기는 일"

# ── 본문 — poster.py _body_to_tinymce_html 마커 형식 사용 ──
# {{이미지N}} 마커는 줄 단위로 처리되므로 반드시 단독 줄에 위치해야 함
BODY_HTML = """솔직히 말하면, 저도 그랬어요. "에버랜드쯤이야 당일에 가서 사면 되겠지" 하고 가볍게 생각했거든요. 그런데 지난 봄, 친구들과 에버랜드를 찾았다가 매표소 앞에서 한 시간 넘게 줄을 서다가... 결국 입장도 못 하고 근처 카페에서 시간을 때우고 돌아왔습니다. 티켓은 구했지만 스마트줄서기 예약은 이미 전부 마감, 인기 어트랙션은 대기 3시간. 반나절이 그냥 날아갔어요.

그날 이후로 에버랜드 방문은 반드시 사전 예약이라는 걸 뼛속 깊이 새겼습니다. 아직도 현장 구매를 생각하고 계신다면, 이 글을 먼저 읽어보시길 강력히 권합니다.

{{이미지1}}

## 현장 구매의 3가지 결정적 문제점

현장 구매가 왜 손해인지, 구체적인 숫자로 살펴볼게요.

**첫 번째, 가격 차이가 생각보다 훨씬 큽니다.** 에버랜드 정문 매표소의 현장 판매 가격과 온라인 사전 예매 가격은 적게는 5,000원, 많게는 2만 원 이상 차이가 납니다. 어른 2명, 아이 1명이 방문한다면 현장 구매만으로도 3만~6만 원을 추가로 내는 셈이에요. 여기에 제휴 카드, 통신사 할인, 각종 쿠폰을 활용하는 온라인 예매와 비교하면 격차는 더 벌어집니다. 같은 입장권인데 가격이 이렇게 다르다는 게 믿기지 않으실 수 있지만, 이건 에버랜드 공식 홈페이지에서도 확인할 수 있는 사실입니다.

{{이미지2}}

**두 번째, 매표소 대기 시간이 상상을 초월합니다.** 성수기 주말 기준으로 에버랜드 정문 매표소 대기 시간은 평균 1시간에서 길면 2시간에 달합니다. 놀이공원에 입장하기 전에 이미 체력의 상당 부분을 소진하는 거죠. 아이가 있는 가족이라면 이 대기 시간이 얼마나 고역인지 잘 아실 거예요. 반면 온라인 사전 예매를 한 경우엔 QR코드를 찍고 바로 입장이 가능한 전용 게이트를 이용할 수 있어서, 매표소 줄과는 완전히 별도로 움직일 수 있습니다.

**세 번째, 스마트줄서기가 이미 마감되어 있습니다.** 에버랜드의 인기 어트랙션인 T익스프레스, 후렌치레볼루션, 아마존 익스프레스 등은 스마트줄서기(모바일 가상 대기) 시스템을 운영합니다. 이 예약은 당일 아침 일찍부터 시작되는데, 인기 어트랙션은 개장 후 1~2시간 내에 전 타임이 마감됩니다. 현장에서 티켓을 사는 동안 이미 스마트줄서기는 끝나버리는 거예요. 현장 구매객은 당일 현장 대기줄에 서야 하는데, 성수기 T익스프레스 대기 시간은 2~3시간이 기본입니다.

## 언제 특히 더 심각한가

에버랜드 현장 구매의 피해가 가장 극심한 시기가 따로 있습니다. 이 시기에 방문 계획이 있다면 더욱 주의가 필요합니다.

**봄 벚꽃 시즌(3월 말~4월 초)**이 가장 혼잡한 시기입니다. 에버랜드 내 벚꽃 명소는 전국적으로 유명해서, 이 기간에는 평소 대비 방문객이 2~3배 몰립니다. 매표소 대기 시간은 기본 1~2시간을 넘기고, 인기 어트랙션 대기는 3시간을 훌쩍 넘기도 합니다.

**여름 워터파크 시즌(7~8월)**도 극성수기입니다. 캐리비안 베이와 에버랜드를 함께 이용하려는 방문객이 몰리면서, 두 곳 모두 현장 구매 티켓은 가격이 오르고 대기는 길어집니다. 특히 워터파크 입장 정원 초과로 현장에서 입장이 거부되는 경우도 종종 발생합니다.

**주말과 공휴일 연휴**는 사실상 연중 내내 혼잡합니다. 특히 추석, 설날 연휴, 어린이날, 크리스마스 시즌에는 주중 대비 방문객이 50% 이상 증가합니다. 이 기간에 현장 구매를 시도하면 앞서 말한 3가지 문제점이 모두 극대화됩니다.

**학교 방학 기간(1~2월, 7~8월)**도 빼놓을 수 없습니다. 어린이와 청소년을 동반한 가족 방문객이 급증하는 시기로, 평일임에도 주말 수준의 혼잡도를 보입니다.

## 그래서 얼마나 일찍 예약해야 하나

결론부터 말씀드리면, 성수기 주말 기준으로는 최소 1~2주 전에 예약하는 것이 좋습니다. 특히 벚꽃 시즌, 여름 워터파크 시즌, 크리스마스 시즌은 한 달 전에도 인기 날짜는 매진될 수 있습니다.

비성수기 평일이라면 3~5일 전 예약으로도 원하는 날짜를 잡을 수 있습니다. 하지만 예약을 미룰수록 선택지가 줄어드는 건 사실이에요. 특히 단체 할인이나 제휴 카드 할인을 함께 챙기려면 시간적 여유가 있어야 합니다.

{{이미지3}}

에버랜드 공식 앱이나 홈페이지에서 예매하면 QR코드가 즉시 발급되어 당일 빠른 입장이 가능합니다. 날짜 변경이나 환불 조건은 예매처마다 다를 수 있으니, 예매 전에 꼭 확인해보세요.

스마트줄서기 예약은 당일 에버랜드 앱을 통해 개장 시간 직전부터 시작됩니다. 방문 당일 아침에 앱을 켜고, 원하는 어트랙션의 스마트줄서기를 바로 신청하는 게 핵심입니다. 이 타이밍을 놓치면 하루 종일 긴 줄에서 기다려야 할 수 있어요.

그럼 어디서 어떻게 예약하면 제일 싸냐고요? 할인 티켓 구매처와 제휴 할인 정보를 한곳에 정리해 둔 글이 있습니다.

→ <a href="https://travel.baremi542.com/" target="_blank">에버랜드 티켓 할인받고 예약까지 한번에 끝내는 법</a>"""

# ── 이미지 프롬프트 ──
IMAGE_INFOS = [
    {
        "index": 1,
        "prompt": "A long queue of people waiting at an amusement park ticket booth on a sunny spring day in South Korea. Cherry blossoms visible in the background. Photorealistic style.",
        "filename": "everland_queue_ticket_booth.webp",
        "alt": "에버랜드 매표소 앞 긴 대기줄 성수기",
        "section": "도입부"
    },
    {
        "index": 2,
        "prompt": "Comparison graphic showing two price tags — one labeled 'online reservation' in Korean with a lower price, and one labeled 'on-site purchase' with a higher price, at a Korean amusement park. Clean, modern infographic style.",
        "filename": "everland_price_comparison.webp",
        "alt": "에버랜드 온라인 예매 vs 현장 구매 가격 비교",
        "section": "현장구매 문제점"
    },
    {
        "index": 3,
        "prompt": "A smartphone displaying a Korean amusement park reservation app with a QR ticket. The background shows a bright amusement park entrance gate. Clean and modern photo.",
        "filename": "everland_mobile_reservation.webp",
        "alt": "에버랜드 모바일 사전 예약 QR 티켓 빠른 입장",
        "section": "예약 방법"
    },
]

TAGS = ["에버랜드", "에버랜드현장구매", "에버랜드티켓", "에버랜드예매", "에버랜드가격", "에버랜드대기시간", "에버랜드입장권", "에버랜드할인", "에버랜드봄", "에버랜드주말"]

if __name__ == "__main__":
    log("=" * 60)
    log("[에버랜드 임시저장] 시작")
    log("=" * 60)

    # ── 1. 이미지 생성 ──
    log("\n[1단계] Gemini 이미지 생성 중...")
    image_paths = generate_images(IMAGE_INFOS, on_log=log)
    log(f"[이미지] 생성 완료: {len(image_paths)}장 — {list(image_paths.values())}")

    if len(image_paths) < 3:
        log(f"[경고] 이미지가 {len(image_paths)}장으로 3장 미만. 계속 진행합니다.")

    # ── 2. 썸네일 생성 ──
    thumbnail_path = None
    if image_paths:
        from image_router import add_title_overlay
        first_img = image_paths[min(image_paths.keys())]
        try:
            thumb_out = str(Path(first_img).with_suffix('')) + "_thumb.webp"
            result = add_title_overlay(first_img, TITLE, "nolja100", thumb_out)
            if result:
                thumbnail_path = result
                log(f"[썸네일] 생성 완료: {thumbnail_path}")
        except Exception as e:
            log(f"[썸네일] 생성 실패: {e} — 스킵")

    # ── 3. 티스토리 임시저장 ──
    log("\n[2단계] Tistory 임시저장 중...")
    ok = _post_tistory(
        account=account,
        title=TITLE,
        body_html=BODY_HTML,
        tags=TAGS,
        image_paths=image_paths,
        image_infos=IMAGE_INFOS,
        keyword="에버랜드 현장구매",
        thumbnail_path=thumbnail_path,
        on_log=log,
    )

    if ok:
        log("\n✅ nolja100 임시저장 완료!")
        log(f"제목: {TITLE}")
        log("확인: https://nolja100.tistory.com/manage/posts")
    else:
        log("\n❌ 임시저장 실패. 로그를 확인하세요.")
        sys.exit(1)
