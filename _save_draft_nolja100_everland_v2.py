"""에버랜드 현장구매 경고 글 — nolja100 Tistory 임시저장 (이미지 포함)"""
import sys
import os
import time
import random
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from browser import connect_cdp, get_or_create_page
from poster import _tistory_upload_image
from config import ACCOUNT_MAP

def log(msg):
    print(msg, flush=True)

def rand_delay(page, min_ms=500, max_ms=1500):
    page.wait_for_timeout(random.randint(min_ms, max_ms))

account = ACCOUNT_MAP["nolja100"]
TITLE = "에버랜드 당일 현장 구매하면 생기는 일"

TAGS = ["에버랜드", "에버랜드현장구매", "에버랜드티켓", "에버랜드예매", "에버랜드가격",
        "에버랜드대기시간", "에버랜드입장권", "에버랜드할인", "에버랜드봄", "에버랜드주말"]

IMAGE_PATHS = [
    str(BASE_DIR / "images" / "everland_queue_ticket_booth.webp"),
    str(BASE_DIR / "images" / "everland_price_comparison.webp"),
    str(BASE_DIR / "images" / "everland_mobile_reservation.webp"),
]

IMAGE_ALTS = [
    "에버랜드 매표소 앞 긴 대기줄 성수기",
    "에버랜드 온라인 예매 vs 현장 구매 가격 비교",
    "에버랜드 모바일 사전 예약 QR 티켓",
]

# 본문 — 단락별로 분리 (이미지 삽입 위치 마킹)
BODY_PARAGRAPHS = [
    ("p", '솔직히 말하면, 저도 그랬어요. "에버랜드쯤이야 당일에 가서 사면 되겠지" 하고 가볍게 생각했거든요. 그런데 지난 봄, 친구들과 에버랜드를 찾았다가 매표소 앞에서 한 시간 넘게 줄을 서다가... 결국 입장도 못 하고 근처 카페에서 시간을 때우고 돌아왔습니다. 티켓은 구했지만 스마트줄서기 예약은 이미 전부 마감, 인기 어트랙션은 대기 3시간. 반나절이 그냥 날아갔어요.'),
    ("p", '그날 이후로 에버랜드 방문은 반드시 사전 예약이라는 걸 뼛속 깊이 새겼습니다. 아직도 현장 구매를 생각하고 계신다면, 이 글을 먼저 읽어보시길 강력히 권합니다.'),
    ("img", 0),  # 이미지 1
    ("h2", "현장 구매의 3가지 결정적 문제점"),
    ("p", "현장 구매가 왜 손해인지, 구체적인 숫자로 살펴볼게요."),
    ("p", "<strong>첫 번째, 가격 차이가 생각보다 훨씬 큽니다.</strong> 에버랜드 정문 매표소의 현장 판매 가격과 온라인 사전 예매 가격은 적게는 5,000원, 많게는 2만 원 이상 차이가 납니다. 어른 2명, 아이 1명이 방문한다면 현장 구매만으로도 3만~6만 원을 추가로 내는 셈이에요. 여기에 제휴 카드, 통신사 할인, 각종 쿠폰을 활용하는 온라인 예매와 비교하면 격차는 더 벌어집니다."),
    ("img", 1),  # 이미지 2
    ("p", "<strong>두 번째, 매표소 대기 시간이 상상을 초월합니다.</strong> 성수기 주말 기준으로 에버랜드 정문 매표소 대기 시간은 평균 1시간에서 길면 2시간에 달합니다. 놀이공원에 입장하기 전에 이미 체력의 상당 부분을 소진하는 거죠. 반면 온라인 사전 예매를 한 경우엔 QR코드를 찍고 바로 입장이 가능한 전용 게이트를 이용할 수 있습니다."),
    ("p", "<strong>세 번째, 스마트줄서기가 이미 마감되어 있습니다.</strong> 에버랜드의 인기 어트랙션인 T익스프레스, 후렌치레볼루션, 아마존 익스프레스 등은 스마트줄서기(모바일 가상 대기) 시스템을 운영합니다. 이 예약은 당일 아침 일찍부터 시작되는데, 인기 어트랙션은 개장 후 1~2시간 내에 전 타임이 마감됩니다. 현장에서 티켓을 사는 동안 이미 스마트줄서기는 끝나버리는 거예요."),
    ("h2", "언제 특히 더 심각한가"),
    ("p", "에버랜드 현장 구매의 피해가 가장 극심한 시기가 따로 있습니다. 이 시기에 방문 계획이 있다면 더욱 주의가 필요합니다."),
    ("p", "<strong>봄 벚꽃 시즌(3월 말~4월 초)</strong>이 가장 혼잡한 시기입니다. 에버랜드 내 벚꽃 명소는 전국적으로 유명해서, 이 기간에는 평소 대비 방문객이 2~3배 몰립니다. 매표소 대기 시간은 기본 1~2시간을 넘기고, 인기 어트랙션 대기는 3시간을 훌쩍 넘기도 합니다."),
    ("p", "<strong>여름 워터파크 시즌(7~8월)</strong>도 극성수기입니다. 캐리비안 베이와 에버랜드를 함께 이용하려는 방문객이 몰리면서, 두 곳 모두 현장 구매 티켓은 가격이 오르고 대기는 길어집니다. 특히 워터파크 입장 정원 초과로 현장에서 입장이 거부되는 경우도 종종 발생합니다."),
    ("p", "<strong>주말과 공휴일 연휴</strong>는 사실상 연중 내내 혼잡합니다. 특히 추석, 설날 연휴, 어린이날, 크리스마스 시즌에는 주중 대비 방문객이 50% 이상 증가합니다."),
    ("p", "<strong>학교 방학 기간(1~2월, 7~8월)</strong>도 빼놓을 수 없습니다. 어린이와 청소년을 동반한 가족 방문객이 급증하는 시기로, 평일임에도 주말 수준의 혼잡도를 보입니다."),
    ("h2", "그래서 얼마나 일찍 예약해야 하나"),
    ("p", "결론부터 말씀드리면, 성수기 주말 기준으로는 최소 1~2주 전에 예약하는 것이 좋습니다. 특히 벚꽃 시즌, 여름 워터파크 시즌, 크리스마스 시즌은 한 달 전에도 인기 날짜는 매진될 수 있습니다."),
    ("p", "비성수기 평일이라면 3~5일 전 예약으로도 원하는 날짜를 잡을 수 있습니다. 하지만 예약을 미룰수록 선택지가 줄어드는 건 사실이에요. 특히 단체 할인이나 제휴 카드 할인을 함께 챙기려면 시간적 여유가 있어야 합니다."),
    ("img", 2),  # 이미지 3
    ("p", "에버랜드 공식 앱이나 홈페이지에서 예매하면 QR코드가 즉시 발급되어 당일 빠른 입장이 가능합니다. 날짜 변경이나 환불 조건은 예매처마다 다를 수 있으니, 예매 전에 꼭 확인해보세요."),
    ("p", "스마트줄서기 예약은 당일 에버랜드 앱을 통해 개장 시간 직전부터 시작됩니다. 방문 당일 아침에 앱을 켜고, 원하는 어트랙션의 스마트줄서기를 바로 신청하는 게 핵심입니다. 이 타이밍을 놓치면 하루 종일 긴 줄에서 기다려야 할 수 있어요."),
    ("p", "그럼 어디서 어떻게 예약하면 제일 싸냐고요? 할인 티켓 구매처와 제휴 할인 정보를 한곳에 정리해 둔 글이 있습니다."),
    ("p", '→ <a href="https://travel.baremi542.com/" target="_blank">에버랜드 티켓 할인받고 예약까지 한번에 끝내는 법</a>'),
]

# 이미지 파일 존재 확인
for p in IMAGE_PATHS:
    if not os.path.exists(p):
        log(f"❌ 이미지 파일 없음: {p}")
        sys.exit(1)

log("=" * 60)
log("[에버랜드 임시저장 v2] 시작")
log("=" * 60)

pw, browser = connect_cdp(log)
try:
    log("[1] 새 글 작성 페이지 이동...")
    page = get_or_create_page(browser, navigate_to=account["editor_url"])
    rand_delay(page, 3000, 5000)
    log(f"현재 URL: {page.url}")

    # 로그인 확인
    if "accounts.kakao.com" in page.url or "auth/login" in page.url:
        log("❌ 로그인 안 됨 — 먼저 login_tistory('nolja100') 실행 필요")
        sys.exit(1)

    # 글 복원 팝업 닫기
    try:
        page.evaluate("""() => {
            const buttons = document.querySelectorAll('button, a');
            for (const btn of buttons) {
                const text = btn.textContent.trim();
                if (text.includes('새 글 작성') || text.includes('취소') || text.includes('아니오')) {
                    btn.click();
                    return text;
                }
            }
        }""")
        rand_delay(page, 1000, 2000)
    except Exception:
        pass

    # 에디터 로드 대기
    log("[2] 에디터 로드 대기...")
    page.wait_for_selector("#post-title-inp", timeout=15000)
    title_el = page.query_selector("#post-title-inp")
    log("[2] 에디터 로드 완료")

    # 제목 입력
    log(f"[3] 제목 입력: {TITLE}")
    title_el.click()
    rand_delay(page, 300, 600)
    import subprocess
    subprocess.run(['pbcopy'], input=TITLE.encode('utf-8'), check=True)
    page.keyboard.press('Meta+v')
    rand_delay(page, 500, 1000)

    # TinyMCE iframe 진입
    log("[4] 본문 입력 시작...")
    page.wait_for_selector("#editor-tistory_ifr", timeout=15000)
    iframe_el = page.query_selector("#editor-tistory_ifr")
    frame = iframe_el.content_frame()
    body_el = frame.query_selector("body")
    body_el.click()
    rand_delay(page, 500, 800)

    # 본문 단락별 삽입
    log("[4] 본문 단락 삽입 중...")
    img_count = 0
    for item in BODY_PARAGRAPHS:
        tag = item[0]
        content = item[1]

        if tag == "img":
            # 이미지 업로드
            idx = content  # 이미지 인덱스
            img_path = IMAGE_PATHS[idx]
            alt = IMAGE_ALTS[idx]
            log(f"[이미지 {idx+1}] 업로드: {Path(img_path).name}")
            ok = _tistory_upload_image(page, img_path, alt, on_log=log)
            log(f"[이미지 {idx+1}] {'성공' if ok else '실패'}")
            time.sleep(2)

        elif tag == "h2":
            # H2 삽입
            h2_html = f'<h2 data-ke-size="size26">{content}</h2>'
            page.evaluate("""(html) => {
                const ed = tinymce.activeEditor;
                if (!ed) return;
                ed.execCommand('mceInsertContent', false, html);
                ed.fire('change');
            }""", h2_html)
            rand_delay(page, 200, 400)

        elif tag == "p":
            # 단락 삽입
            p_html = f'<p data-ke-size="size19">{content}</p>'
            page.evaluate("""(html) => {
                const ed = tinymce.activeEditor;
                if (!ed) return;
                ed.execCommand('mceInsertContent', false, html);
                ed.fire('change');
            }""", p_html)
            rand_delay(page, 100, 300)

    # 저장
    page.evaluate("""() => {
        const ed = tinymce && tinymce.activeEditor;
        if (ed) { ed.fire('change'); ed.save(); }
    }""")
    rand_delay(page, 500, 800)

    log("[5] 태그 입력 중...")
    tag_input = page.query_selector(".tag-input, #tag-text, .area_tag input")
    if not tag_input:
        tag_input = page.query_selector("input[class*='tag'], .tag_content input")
    if tag_input:
        for tag in TAGS:
            tag_input.click()
            rand_delay(page, 200, 400)
            subprocess.run(['pbcopy'], input=tag.encode('utf-8'), check=True)
            page.keyboard.press('Meta+v')
            time.sleep(0.3)
            page.keyboard.press('Return')
            rand_delay(page, 200, 400)
        log(f"[5] 태그 {len(TAGS)}개 입력 완료")
    else:
        log("[5] ⚠️ 태그 입력창 못 찾음")

    log("[6] 카테고리 선택: 여행...")
    cat_selected = page.evaluate("""() => {
        const selects = document.querySelectorAll('select[name*="category"], select[id*="category"]');
        for (const sel of selects) {
            for (const opt of sel.options) {
                if (opt.text.includes('여행')) {
                    sel.value = opt.value;
                    sel.dispatchEvent(new Event('change'));
                    return opt.text;
                }
            }
        }
        // 버튼형 카테고리
        const btns = document.querySelectorAll('.category_btn, [class*="category"] button, [class*="category"] a');
        for (const btn of btns) {
            if (btn.textContent.includes('여행')) {
                btn.click();
                return '여행 (클릭)';
            }
        }
        return null;
    }""")
    log(f"[6] 카테고리: {cat_selected}")
    rand_delay(page, 500, 800)

    log("[7] 임시저장 중...")
    saved = page.evaluate("""() => {
        const buttons = document.querySelectorAll('button, a, input[type="button"]');
        for (const btn of buttons) {
            const text = btn.textContent.trim();
            if (text === '임시저장' || text.includes('임시저장')) {
                btn.click();
                return true;
            }
        }
        return false;
    }""")
    rand_delay(page, 2000, 3000)

    # 저장된 URL 확인
    current_url = page.url
    post_id = None
    import re
    m = re.search(r'/(\d+)$', current_url)
    if m:
        post_id = m.group(1)

    if saved:
        log(f"✅ 임시저장 완료!")
        log(f"제목: {TITLE}")
        log(f"URL: {current_url}")
        log(f"관리 페이지: https://nolja100.tistory.com/manage/posts?category=&type=temp")
        if post_id:
            log(f"글 ID: {post_id}")
            log(f"수정 URL: https://nolja100.tistory.com/manage/newpost/{post_id}")
    else:
        log("⚠️ 임시저장 버튼을 못 찾음. 수동으로 확인 필요.")

finally:
    pw.stop()
