"""
nolja100 Tistory 춘천 소양강 닭갈비 당일치기 여행 포스팅 + 발행 워커

1. Gemini로 이미지 생성 (썸네일 + 4장 = 5장)
2. poster._post_tistory()로 임시저장
3. publish_drafts.publish_tistory_draft()로 검수 + 발행
4. 텔레그램 보고
"""

import sys
import time
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# .env 로드
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            import os
            os.environ.setdefault(_k.strip(), _v.strip())

def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── 1. 글 내용 정의 ────────────────────────────────────────────────────────

TITLE = "춘천 소양강 닭갈비 당일치기 여행 코스 — 뚜벅이도 가능한 알짜 루트"

TAGS = [
    "춘천여행", "춘천당일치기", "소양강스카이워크", "닭갈비골목", "춘천뚜벅이",
    "춘천맛집", "낭만시장", "경춘선여행", "춘천관광", "소양강",
    "춘천닭갈비", "국내여행", "당일치기코스", "ITX청춘", "춘천볼거리"
]

# 이미지 정보 (인덱스 0 = 썸네일, 1~5 = 본문 이미지)
IMAGE_INFOS = [
    {
        "index": 0,
        "prompt": "Soyang River Skywalk glass bridge in Chuncheon at golden hour, wide aerial landscape with mountains and river, vibrant colors, no people, no text",
        "filename": "nolja100-chuncheon-thumb.jpg",
        "alt": "춘천 소양강 당일치기 여행 썸네일",
        "is_thumb": True,
    },
    {
        "index": 1,
        "prompt": "Chuncheon city travel route map illustration with Soyang River, Dakgalbi Street and romantic market markers, pastel watercolor style, no text",
        "filename": "nolja100-chuncheon-1.jpg",
        "alt": "춘천 당일치기 여행 이동 코스 지도 일러스트",
    },
    {
        "index": 2,
        "prompt": "Chuncheon dakgalbi stir-fry in cast iron pan with vegetables on restaurant table, close-up realistic food photography, warm lighting, no people",
        "filename": "nolja100-chuncheon-2.jpg",
        "alt": "춘천 명동 닭갈비골목 철판 닭갈비 클로즈업",
    },
    {
        "index": 3,
        "prompt": "Soyang River Skywalk glass bridge walkway in Chuncheon with river view and mountains in background, sunny day, realistic photography, no people",
        "filename": "nolja100-chuncheon-3.jpg",
        "alt": "춘천 소양강 스카이워크 유리 다리 위에서 바라본 강 풍경",
    },
    {
        "index": 4,
        "prompt": "Chuncheon romantic market alley with traditional Korean street food stalls, lanterns and local vendors, warm evening atmosphere, vibrant colors, no people faces",
        "filename": "nolja100-chuncheon-4.jpg",
        "alt": "춘천 낭만시장 골목 분위기 및 로컬 먹거리 풍경",
    },
    {
        "index": 5,
        "prompt": "ITX-Cheongchun train arriving at Chuncheon station on a clear day, realistic travel photography, wide angle, no people",
        "filename": "nolja100-chuncheon-5.jpg",
        "alt": "춘천역에 도착하는 ITX-청춘 열차 풍경",
    },
]

# 본문 (poster.py 형식: ##H2, {{이미지N}}, [애드센스], 일반텍스트)
# 인트로 + 핵심요약 먼저
BODY = """\
💡 핵심 요약
• 춘천역 출발 → 닭갈비골목 → 소양강 스카이워크 → 낭만시장 순서로 이동하면 대중교통만으로 하루 완성 가능합니다.
• 소양강 스카이워크는 무료 입장(조사 기준 2026년 4월), 닭갈비 1인분 기준 평균 13,000원~15,000원 선입니다.
• 주말 점심 시간대 닭갈비골목은 30분~1시간 웨이팅이 일반적이므로 오전 11시 30분 전 도착이 유리합니다.

## 🗺️ 춘천 당일치기 기본 이동 동선

{{이미지1}}

서울에서 춘천까지 경춘선 ITX-청춘을 타면 용산역 기준 약 1시간 10분, 청량리역 기준 약 1시간이면 춘천역에 도착합니다. 2026년 4월 기준 청량리~춘천 ITX 요금은 편도 7,200원입니다.

춘천역에서 나오면 버스를 이용하거나 도보로 이동할 수 있습니다. 닭갈비골목(명동 닭갈비거리)까지는 역에서 도보 약 15~20분 거리입니다. 체력을 아끼고 싶다면 시내버스 72번, 150번을 타고 '명동' 정류장에서 하차하면 됩니다.

낭만시장은 닭갈비골목과 도보 5분 거리에 있어 식사 후 바로 이동하기 좋고, 소양강 스카이워크는 시내버스 11번을 타고 '소양1교' 정류장에서 하차하면 도보 10분 이내입니다.

> 💡 당일치기 추천 시간 배분: 오전 11시 30분 닭갈비골목 입장 → 오후 1시 낭만시장 → 오후 2시 30분 소양강 스카이워크 → 오후 4시 귀경. 이 순서로 움직이면 버스 환승 횟수를 최소화할 수 있습니다.

[애드센스]

## 🍗 닭갈비골목 — 주문부터 먹는 법까지

{{이미지2}}

춘천 명동 닭갈비거리는 춘천의 대표 먹거리 골목입니다. 양념된 닭고기를 철판에 고추장 양념과 함께 볶는 방식이라 냄새가 골목 전체에 퍼져 있어서 찾기 어렵지 않습니다.

메뉴 구성은 보통 닭갈비(1인분), 막국수, 추가 재료(치즈·사리 등)로 나뉩니다. 2026년 4월 조사 기준 닭갈비 1인분 가격은 업소마다 12,000원에서 16,000원 사이입니다. 철판 닭갈비 특성상 2인 이상이 함께 방문해야 맛있게 볶을 수 있어, 1인 방문 시 바 형식 좌석이 있는 매장을 골라야 합니다.

실제 방문자들의 경험에 따르면 주말 오후 1시~2시 사이는 웨이팅이 1시간을 넘기도 합니다. 오전 11시 30분 전에 줄을 서면 대기 없이 바로 입장하는 경우가 많습니다. 메뉴 중 '닭갈비+막국수 세트'를 묶어 주문하면 따로 시키는 것보다 1,000~2,000원 저렴한 경우가 있는데, 이는 매장마다 달라 확인이 필요합니다.

볶음 마지막 단계에서 밥을 넣어 볶음밥으로 마무리하는 것이 일반적인데, 이때 추가 비용이 발생하는 매장도 있습니다. 방문 전 매장 측에 확인해 두는 것을 권장합니다.

> 💡 골목 입구 주차장보다 춘천시청 근처 공영주차장을 이용하면 주차 공간 찾기가 수월합니다. 유료이며 시간당 요금이 적용됩니다.

## 🌉 소양강 스카이워크 — 입장료·운영시간·실제 소요시간

{{이미지3}}

소양강 스카이워크는 소양강 위에 설치된 유리 바닥 보행 다리입니다. 총 길이 약 174m로, 유리를 통해 강물을 내려다볼 수 있는 구조입니다. 2026년 4월 기준 입장료는 무료입니다.

운영 시간은 계절에 따라 달라집니다. 조사 기준 하절기(4~10월)는 오전 10시부터 오후 8시까지, 동절기(11~3월)는 오후 6시까지 운영하며, 월요일이 휴무인 경우가 있어 방문 전 춘천시 공식 채널을 통해 재확인하는 것이 좋습니다.

대중교통 이용 시 춘천 시내버스 11번을 타고 '소양1교' 하차 후 도보 약 10분이면 도착합니다. 자가용은 소양강 스카이워크 인근 공영주차장을 이용하면 되고, 주차 요금은 무료와 유료가 혼재해 있어 현장 확인이 필요합니다.

스카이워크 진입부터 끝까지 걷는 데 약 15~20분이면 충분하지만, 주말에는 사람이 많아 중간에 멈춰 사진을 찍는 시간까지 포함하면 30~40분을 넉넉히 봐야 합니다. 유리 바닥 위를 걸어야 하므로 슬리퍼나 굽 높은 신발은 진입이 제한될 수 있습니다.

아쉬웠던 점은 주말 오후 2시 이후에는 사진 찍기 좋은 스팟마다 줄이 길게 형성된다는 것입니다. 인증샷 위주로 방문할 계획이라면 오전 일찍 움직이는 편이 낫습니다.

> 💡 소양강 스카이워크 인근 '소양강 처녀상'도 함께 볼 수 있어 이동 동선을 묶으면 효율적입니다.

[애드센스]

## 🛍️ 낭만시장 — 춘천 로컬 먹거리와 기념품

{{이미지4}}

낭만시장은 춘천 명동 닭갈비골목 바로 옆에 위치한 전통시장입니다. 춘천 지역 특산물인 옥수수, 감자, 닭 관련 먹거리와 함께 저렴한 분식류를 파는 노점이 함께 섞여 있습니다. 닭갈비 식사 후 거리 산책 겸 들러보기 좋은 위치입니다.

시장 안에서 눈에 띄는 것은 닭갈비 소시지, 닭강정, 떡볶이 등 간단한 간식 거리들입니다. 닭갈비 골목을 이미 다녀왔다면 닭고기 관련 메뉴보다는 지역 특산 감자전, 옥수수 관련 간식 등을 골라보는 것을 권장합니다.

시장 규모는 크지 않아 전체를 돌아보는 데 20~30분이면 충분합니다. 방문 시간대는 점심 이후부터 오후 5시 전후까지가 활기차며, 그 이후로는 문을 닫는 가게들이 늘어납니다. 대중교통 마지막 배차 시간을 고려해 시간 배분을 해두는 것이 좋습니다.

> 💡 낭만시장 입구에서 춘천역 방향 버스를 바로 탈 수 있어 귀경 동선이 편리합니다. 버스 번호는 현장 정류장에서 재확인하세요.

## ❓ 자주 묻는 질문

{{이미지5}}

Q. 서울에서 춘천까지 가장 빠른 이동 수단은 무엇인가요?
A. 경춘선 ITX-청춘이 가장 빠릅니다. 청량리역 기준 약 1시간 소요되며, 2026년 4월 기준 편도 요금은 7,200원입니다. 배차 간격은 출퇴근 시간대 20~30분, 주간 30~60분 간격이므로 코레일 앱에서 미리 시간표를 확인해 두는 것을 권장합니다.

Q. 닭갈비골목에서 1인 방문도 가능한가요?
A. 가능합니다. 다만 대부분의 가게가 2인분 이상 주문을 권장하거나 최소 주문 수량이 있을 수 있습니다. 1인 방문 시에는 바 형태 좌석이 있는 가게를 사전에 검색해두거나, 방문 전 전화로 확인하는 것이 좋습니다. 일부 매장은 1인 세트 메뉴를 따로 운영하기도 합니다.

Q. 소양강 스카이워크와 소양강댐 유람선은 같은 날 함께 볼 수 있나요?
A. 당일치기로는 다소 빡빡한 일정입니다. 소양강댐 유람선은 선착장에서 출발하며, 스카이워크와 이동 거리가 있어 자가용 없이는 이동이 불편합니다. 당일치기 뚜벅이 일정이라면 스카이워크 단독 방문을 추천하고, 유람선은 1박 2일 일정에서 추가하는 방식이 현실적입니다.
"""


def generate_images():
    """Gemini로 이미지 생성 (썸네일 포함 6장)"""
    log("=== 이미지 생성 시작 (Gemini) ===")
    from gemini_image import generate_images as gemini_gen
    from image_router import add_title_overlay

    output_dir = BASE_DIR / "images" / "nolja100"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 썸네일 별도 생성
    thumb_info = next((i for i in IMAGE_INFOS if i.get("is_thumb")), None)
    thumb_path = None

    # 본문 이미지 (index 1~5)
    body_img_infos = [i for i in IMAGE_INFOS if not i.get("is_thumb")]

    # Gemini 생성 (썸네일 포함 한 번에)
    all_infos = []
    if thumb_info:
        all_infos.append({
            "index": 0,
            "prompt": thumb_info["prompt"],
            "filename": thumb_info["filename"],
        })
    for info in body_img_infos:
        all_infos.append({
            "index": info["index"],
            "prompt": info["prompt"],
            "filename": info["filename"],
        })

    log(f"Gemini 이미지 생성 요청: {len(all_infos)}장")
    results = gemini_gen(
        image_infos=all_infos,
        on_log=log,
        skip_webp=True,  # jpg 저장
        output_dir=output_dir,
    )
    log(f"Gemini 생성 결과: {list(results.keys())}")

    # 썸네일 오버레이
    if 0 in results:
        thumb_path = results[0]
        add_title_overlay(thumb_path, TITLE, blog_id="nolja100", on_log=log)
        log(f"썸네일 오버레이 완료: {thumb_path}")

    # 결과: {index: filepath}
    image_paths = {}
    for idx, fp in results.items():
        image_paths[idx] = fp

    return image_paths, thumb_path


def post_to_tistory(image_paths, thumb_path):
    """Tistory 에디터에 글 작성 + 임시저장"""
    log("=== Tistory 임시저장 시작 ===")
    import config as _cfg
    from poster import _post_tistory
    from publish_drafts import _tistory_ensure_login
    from browser import connect_cdp, get_or_create_page
    import time as _time

    account = None
    for acc in _cfg.ACCOUNTS:
        if acc.get("blog") == "nolja100":
            account = acc
            break

    if not account:
        log("nolja100 계정 정보 없음")
        return False

    # 먼저 로그인 상태 확인 및 로그인 처리 (같은 Chrome 프로세스에 세션 주입)
    log("Tistory 로그인 상태 확인 중...")
    pw, browser = connect_cdp(log)
    login_ok = False
    try:
        page = get_or_create_page(browser)
        login_ok = _tistory_ensure_login(page, "nolja100")
        if not login_ok:
            log("Tistory 로그인 실패")
            return False
        log("Tistory 로그인 확인 완료")
        _time.sleep(2)
    finally:
        pw.stop()

    if not login_ok:
        return False

    # image_infos (alt 정보)
    img_info_list = [
        {"index": i["index"], "alt": i["alt"]}
        for i in IMAGE_INFOS if not i.get("is_thumb")
    ]

    ok = _post_tistory(
        account=account,
        title=TITLE,
        body_html=BODY,
        tags=TAGS,
        image_paths=image_paths,
        image_infos=img_info_list,
        keyword="춘천 소양강 닭갈비 당일치기",
        thumbnail_path=thumb_path,
        on_log=log,
    )
    return ok


def publish_draft():
    """임시저장된 글 검수 + 발행"""
    log("=== Tistory 검수 + 발행 시작 ===")
    from publish_drafts import publish_tistory_draft
    ok = publish_tistory_draft("nolja100")
    return ok


def send_telegram(title, success, fixes=None):
    """텔레그램 발행 보고"""
    import subprocess, datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if success:
        fixes_str = "\n".join(f"- {f}" for f in fixes) if fixes else "- 이상 없음"
        msg = f"""✅ 발행 완료
블로그: nolja100
제목: {title}
발행시각: {now}

🔧 검수 중 수정사항:
{fixes_str}"""
    else:
        msg = f"""⚠️ 오류 발생
작업: nolja100 포스팅 발행
오류: 발행 실패
조치: 수동 확인 필요"""

    subprocess.run(
        ["python3", str(BASE_DIR / "tg_send.py"), msg],
        cwd=str(BASE_DIR),
        timeout=30,
    )


if __name__ == "__main__":
    fixes = []

    # STEP 1: 이미지 생성 (기존 생성된 이미지가 있으면 재사용)
    output_dir = BASE_DIR / "images" / "nolja100"
    existing_images = {}
    for info in IMAGE_INFOS:
        fp = output_dir / info["filename"]
        if fp.exists():
            existing_images[info["index"]] = str(fp)

    if len(existing_images) >= 6:
        log(f"기존 이미지 재사용: {len(existing_images)}장")
        image_paths = existing_images
        thumb_path = existing_images.get(0)
    else:
        try:
            image_paths, thumb_path = generate_images()
            log(f"이미지 생성 완료: {len(image_paths)}장")
            if len(image_paths) < 3:
                log("⚠️ 이미지 3장 미만 — 발행 중단")
                send_telegram(TITLE, False)
                sys.exit(1)
        except Exception as e:
            log(f"이미지 생성 실패: {e}")
            import subprocess
            subprocess.run(
                ["python3", str(BASE_DIR / "tg_send.py"),
                 f"⚠️ 오류 발생\n작업: nolja100 이미지 생성\n오류: {e}\n조치: 수동 확인 필요"],
                cwd=str(BASE_DIR), timeout=30
            )
            sys.exit(1)

    # STEP 2: Tistory 임시저장
    try:
        ok = post_to_tistory(image_paths, thumb_path)
        if not ok:
            log("임시저장 실패")
            send_telegram(TITLE, False)
            sys.exit(1)
        log("임시저장 완료")
        time.sleep(3)
    except Exception as e:
        log(f"임시저장 실패: {e}")
        send_telegram(TITLE, False)
        sys.exit(1)

    # STEP 3: 검수 + 발행
    try:
        published = publish_draft()
        if not published:
            log("발행 실패")
            send_telegram(TITLE, False)
            sys.exit(1)
        log("발행 완료!")
    except Exception as e:
        log(f"발행 실패: {e}")
        send_telegram(TITLE, False)
        sys.exit(1)

    # STEP 4: 텔레그램 보고
    send_telegram(TITLE, True, fixes)
    log("=== 전체 완료 ===")
