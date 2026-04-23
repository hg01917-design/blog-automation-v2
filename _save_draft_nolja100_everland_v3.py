"""에버랜드 현장구매 경고 글 — nolja100 Tistory 임시저장 v3
네트워크 응답을 모니터링하여 실제 저장 URL 확인
"""
import sys
import os
import time
import random
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from browser import connect_cdp, get_or_create_page
from poster import _tistory_upload_image, _body_to_tinymce_html
from config import ACCOUNT_MAP

def log(msg):
    print(msg, flush=True)

account = ACCOUNT_MAP["nolja100"]
TITLE = "에버랜드 당일 현장 구매하면 생기는 일"

TAGS = ["에버랜드", "에버랜드현장구매", "에버랜드티켓", "에버랜드예매", "에버랜드가격",
        "에버랜드대기시간", "에버랜드입장권", "에버랜드할인", "에버랜드봄", "에버랜드주말"]

IMAGE_PATHS = [
    str(BASE_DIR / "images" / "bs_everland" / "bs_everland-에버랜드-매표소-긴-줄-1-833198-1.webp"),
    str(BASE_DIR / "images" / "bs_everland" / "bs_everland-에버랜드-매표소-긴-줄-1-833263-1.webp"),
    str(BASE_DIR / "images" / "bs_ev2" / "bs_ev2-에버랜드-매표소-긴-줄-1-837730-2.webp"),
]

IMAGE_ALTS = [
    "에버랜드 매표소 앞 긴 대기줄 성수기",
    "에버랜드 온라인 예매 vs 현장 구매 가격 비교",
    "에버랜드 모바일 사전 예약 QR 티켓",
]

BODY_TEXT = """솔직히 말하면, 저도 그랬어요. "에버랜드쯤이야 당일에 가서 사면 되겠지" 하고 가볍게 생각했거든요. 그런데 지난 봄, 친구들과 에버랜드를 찾았다가 매표소 앞에서 한 시간 넘게 줄을 서다가... 결국 입장도 못 하고 근처 카페에서 시간을 때우고 돌아왔습니다. 티켓은 구했지만 스마트줄서기 예약은 이미 전부 마감, 인기 어트랙션은 대기 3시간. 반나절이 그냥 날아갔어요.

그날 이후로 에버랜드 방문은 반드시 사전 예약이라는 걸 뼛속 깊이 새겼습니다. 아직도 현장 구매를 생각하고 계신다면, 이 글을 먼저 읽어보시길 강력히 권합니다.

{{이미지1}}

## 현장 구매의 3가지 결정적 문제점

현장 구매가 왜 손해인지, 구체적인 숫자로 살펴볼게요.

**첫 번째, 가격 차이가 생각보다 훨씬 큽니다.** 에버랜드 정문 매표소의 현장 판매 가격과 온라인 사전 예매 가격은 적게는 5,000원, 많게는 2만 원 이상 차이가 납니다. 어른 2명, 아이 1명이 방문한다면 현장 구매만으로도 3만~6만 원을 추가로 내는 셈이에요. 여기에 제휴 카드, 통신사 할인, 각종 쿠폰을 활용하는 온라인 예매와 비교하면 격차는 더 벌어집니다.

{{이미지2}}

**두 번째, 매표소 대기 시간이 상상을 초월합니다.** 성수기 주말 기준으로 에버랜드 정문 매표소 대기 시간은 평균 1시간에서 길면 2시간에 달합니다. 놀이공원에 입장하기 전에 이미 체력의 상당 부분을 소진하는 거죠. 반면 온라인 사전 예매를 한 경우엔 QR코드를 찍고 바로 입장이 가능한 전용 게이트를 이용할 수 있습니다.

**세 번째, 스마트줄서기가 이미 마감되어 있습니다.** 에버랜드의 인기 어트랙션인 T익스프레스, 후렌치레볼루션, 아마존 익스프레스 등은 스마트줄서기(모바일 가상 대기) 시스템을 운영합니다. 개장 후 1~2시간 내에 전 타임이 마감됩니다. 현장 구매객은 당일 현장 대기줄에 서야 하는데, 성수기 T익스프레스 대기 시간은 2~3시간이 기본입니다.

## 언제 특히 더 심각한가

**봄 벚꽃 시즌(3월 말~4월 초)**이 가장 혼잡한 시기입니다. 이 기간에는 평소 대비 방문객이 2~3배 몰립니다. 매표소 대기 시간은 기본 1~2시간을 넘기고, 인기 어트랙션 대기는 3시간을 훌쩍 넘기도 합니다.

**여름 워터파크 시즌(7~8월)**도 극성수기입니다. 특히 워터파크 입장 정원 초과로 현장에서 입장이 거부되는 경우도 종종 발생합니다.

**주말과 공휴일 연휴**는 사실상 연중 내내 혼잡합니다. 추석, 설날 연휴, 어린이날, 크리스마스 시즌에는 주중 대비 방문객이 50% 이상 증가합니다.

**학교 방학 기간(1~2월, 7~8월)**에도 어린이와 청소년을 동반한 가족 방문객이 급증합니다.

## 그래서 얼마나 일찍 예약해야 하나

성수기 주말 기준으로는 최소 1~2주 전에 예약하는 것이 좋습니다. 벚꽃 시즌, 여름 워터파크 시즌, 크리스마스 시즌은 한 달 전에도 인기 날짜는 매진될 수 있습니다.

비성수기 평일이라면 3~5일 전 예약으로도 원하는 날짜를 잡을 수 있습니다. 제휴 카드 할인을 함께 챙기려면 시간적 여유가 있어야 합니다.

{{이미지3}}

에버랜드 공식 앱이나 홈페이지에서 예매하면 QR코드가 즉시 발급되어 당일 빠른 입장이 가능합니다.

스마트줄서기 예약은 당일 에버랜드 앱을 통해 개장 시간 직전부터 시작됩니다. 방문 당일 아침에 앱을 켜고, 원하는 어트랙션의 스마트줄서기를 바로 신청하는 게 핵심입니다.

그럼 어디서 어떻게 예약하면 제일 싸냐고요? 할인 티켓 구매처와 제휴 할인 정보를 한곳에 정리해 둔 글이 있습니다.

→ <a href="https://m.site.naver.com/26hbF" target="_blank" rel="noopener">에버랜드 티켓 할인받고 예약까지 한번에 끝내는 법</a>"""

# 이미지 파일 존재 확인
for p in IMAGE_PATHS:
    if not os.path.exists(p):
        log(f"❌ 이미지 파일 없음: {p}")
        sys.exit(1)

log("=" * 60)
log("[에버랜드 임시저장 v3] 시작")
log("=" * 60)

pw, browser = connect_cdp(log)
saved_post_url = None
try:
    editor_url = account["editor_url"]
    log(f"[1] 기존 nolja100 탭 찾기 또는 에디터 이동: {editor_url}")
    page = get_or_create_page(browser, url_contains="nolja100.tistory.com")
    if "manage" not in page.url:
        page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
    elif "newpost" not in page.url:
        page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(3, 5))

    if "accounts.kakao.com" in page.url or "auth/login" in page.url:
        log("❌ 로그인 안 됨 — 중단")
        sys.exit(1)

    # 글 복원 팝업 닫기
    try:
        page.evaluate("""() => {
            const btns = document.querySelectorAll('button, a');
            for (const btn of btns) {
                const t = btn.textContent.trim();
                if (t.includes('새 글 작성') || t.includes('취소') || t.includes('아니오')) {
                    btn.click();
                    return;
                }
            }
        }""")
        time.sleep(1)
    except Exception:
        pass

    log("[2] 에디터 로드 대기...")
    page.wait_for_selector("#post-title-inp", timeout=15000)
    log("[2] 에디터 로드 완료")

    # 네트워크 응답 감시 — 임시저장 완료 후 글 ID 캡처
    draft_urls = []
    def on_response(resp):
        if 'tistory.com' in resp.url and ('draft' in resp.url or 'write' in resp.url.lower() or 'save' in resp.url.lower()):
            draft_urls.append(resp.url)
    page.on('response', on_response)

    # 제목 입력
    log(f"[3] 제목 입력: {TITLE}")
    title_el = page.query_selector("#post-title-inp")
    title_el.click()
    time.sleep(0.4)
    subprocess.run(['pbcopy'], input=TITLE.encode('utf-8'), check=True)
    page.keyboard.press('Meta+v')
    time.sleep(0.8)

    # TinyMCE 본문 입력
    log("[4] 본문 입력...")
    page.wait_for_selector("#editor-tistory_ifr", timeout=15000)

    full_html = _body_to_tinymce_html(BODY_TEXT, "nolja100")
    page.evaluate("""(html) => {
        const ed = tinymce.activeEditor;
        if (!ed) return;
        ed.setContent(html);
        ed.fire('change');
        ed.save();
    }""", full_html)
    time.sleep(1.5)
    log("[4] 본문 setContent 완료")

    # 이미지 placeholder 위치에 업로드
    for idx in range(1, 4):
        img_path = IMAGE_PATHS[idx - 1]
        alt = IMAGE_ALTS[idx - 1]

        placed = page.evaluate(f"""() => {{
            const ed = tinymce.activeEditor;
            const body = ed.getBody();
            const p = body.querySelector('[data-img-slot="{idx}"]');
            if (!p) return false;
            const range = ed.getDoc().createRange();
            range.selectNode(p);
            ed.selection.setRng(range);
            ed.focus();
            p.parentNode.removeChild(p);
            ed.fire('change');
            return true;
        }}""")

        if placed:
            log(f"[이미지 {idx}] 업로드: {Path(img_path).name}")
            ok = _tistory_upload_image(page, img_path, alt, on_log=log)
            log(f"[이미지 {idx}] {'성공' if ok else '실패'}")
            # 커서 복구
            page.evaluate("""() => {
                const ed = tinymce.activeEditor;
                if (!ed) return;
                const body = ed.getBody();
                const p = ed.getDoc().createElement('p');
                p.setAttribute('data-ke-size', 'size19');
                p.innerHTML = '<br data-mce-bogus="1">';
                body.appendChild(p);
                const range = ed.getDoc().createRange();
                range.setStart(p, 0);
                range.collapse(true);
                ed.selection.setRng(range);
                ed.focus();
            }""")
            time.sleep(0.3)
        else:
            log(f"[이미지 {idx}] placeholder 없음 — 스킵")

    # 남은 placeholder 제거
    page.evaluate("""() => {
        const ed = tinymce && tinymce.activeEditor;
        if (!ed) return;
        const body = ed.getBody();
        body.querySelectorAll('[data-img-slot]').forEach(p => p.parentNode.removeChild(p));
        ed.fire('change');
    }""")

    # size19 일괄 적용
    page.evaluate("""() => {
        const ed = tinymce && tinymce.activeEditor;
        if (!ed) return;
        ed.getBody().querySelectorAll('p:not([data-ke-size])').forEach(p => p.setAttribute('data-ke-size', 'size19'));
        ed.fire('change');
        ed.save();
    }""")
    time.sleep(0.8)

    # 태그 입력
    log("[5] 태그 입력 중...")
    for tag in TAGS:
        tag_input = page.query_selector("#tagText")
        if tag_input:
            tag_input.click()
            time.sleep(0.2)
            subprocess.run(['pbcopy'], input=tag.encode('utf-8'), check=True)
            page.keyboard.press('Meta+v')
            time.sleep(0.3)
            page.keyboard.press('Enter')
            time.sleep(0.3)
    log(f"[5] 태그 {len(TAGS)}개 입력 완료")

    # 카테고리 선택
    log("[6] 카테고리 선택: 여행...")
    page.evaluate("""() => {
        const btn = document.querySelector('#category-btn');
        if (btn) btn.click();
    }""")
    time.sleep(1)
    cat_result = page.evaluate("""() => {
        const spans = document.querySelectorAll('.mce-text');
        for (const span of spans) {
            if (span.textContent.trim() === '여행') {
                const li = span.closest('li');
                if (li) { li.click(); return '여행(li)'; }
                span.click();
                return '여행(span)';
            }
        }
        return null;
    }""")
    log(f"[6] 카테고리: {cat_result}")
    time.sleep(0.5)

    # 임시저장 — 좌표 기반 클릭으로 실제 저장 보장
    log("[7] 임시저장 클릭...")
    save_btn_rect = page.evaluate("""() => {
        const btns = document.querySelectorAll('a.action, button, a');
        for (const btn of btns) {
            if (btn.textContent.trim() === '임시저장') {
                const rect = btn.getBoundingClientRect();
                return {x: rect.x + rect.width/2, y: rect.y + rect.height/2};
            }
        }
        return null;
    }""")

    if save_btn_rect:
        log(f"[7] 임시저장 버튼 좌표: ({save_btn_rect['x']:.0f}, {save_btn_rect['y']:.0f})")
        page.mouse.click(save_btn_rect['x'], save_btn_rect['y'])
    else:
        # 폴백: evaluate로 클릭
        page.evaluate("""() => {
            document.querySelectorAll('button, a, input[type=button]').forEach(btn => {
                if (btn.textContent.trim() === '임시저장') btn.click();
            });
        }""")

    log("[7] 임시저장 완료 대기 중...")
    time.sleep(6)  # 충분히 대기

    # 저장된 URL 확인
    current_url = page.url
    log(f"[7] 저장 후 URL: {current_url}")
    log(f"[7] 캡처된 draft URL: {draft_urls}")

    # 임시저장 목록에서 글 ID 확인
    page.goto('https://nolja100.tistory.com/manage/posts?category=&type=temp', wait_until='domcontentloaded')
    time.sleep(4)
    txt = page.inner_text('body')
    if '에버랜드' in txt:
        idx = txt.find('에버랜드')
        print(f'\n✅ 임시저장 목록 확인: {txt[max(0,idx-20):idx+80]}')
    else:
        # 최신 글 링크 확인
        links = page.evaluate("""() => {
            const all = document.querySelectorAll('a[href*="manage/post/"]');
            return Array.from(all).slice(0, 4).map(a => a.href);
        }""")
        log(f"[확인] 임시저장 목록 최신 링크: {links}")

        # 최신 글 열어서 제목 확인
        import re
        nums = []
        for link in links:
            m = re.search(r'/(\d+)\?', link)
            if m:
                nums.append(int(m.group(1)))
        if nums:
            newest = max(nums)
            log(f"[확인] 최신 글 ID: {newest}, 확인 중...")
            page.goto(f'https://nolja100.tistory.com/manage/newpost/{newest}', wait_until='domcontentloaded')
            time.sleep(5)
            t = page.evaluate('() => { const inp = document.querySelector("#post-title-inp"); return inp ? inp.value : "없음"; }')
            img_c = page.evaluate('() => { try { return tinymce.activeEditor.getBody().querySelectorAll("img").length; } catch(e) { return -1; } }')
            log(f"[확인] 글 ID {newest}: 제목={t}, 이미지={img_c}")

            if '에버랜드' in t:
                log(f"\n✅ 임시저장 성공!")
                log(f"제목: {t}")
                log(f"글 ID: {newest}")
                log(f"수정 URL: https://nolja100.tistory.com/manage/newpost/{newest}")
            else:
                # draft_urls에서 ID 추출
                draft_id = None
                for du in draft_urls:
                    m = re.search(r'/drafts?/(\d+)', du)
                    if m:
                        draft_id = m.group(1)
                log(f"⚠️ 목록에서 에버랜드 글 못 찾음. draft 응답 URL: {draft_urls}")
                log(f"draft_id: {draft_id}")

finally:
    pw.stop()
