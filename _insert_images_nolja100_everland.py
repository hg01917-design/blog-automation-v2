"""에버랜드 임시저장 글에 이미지 삽입 스크립트"""
import sys
import time
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from browser import connect_cdp, get_or_create_page
from poster import _tistory_upload_image

def log(msg):
    print(msg, flush=True)

IMAGE_PATHS = [
    "/Users/hana/Downloads/blog-automation-v2/images/everland_queue_ticket_booth.webp",
    "/Users/hana/Downloads/blog-automation-v2/images/everland_price_comparison.webp",
    "/Users/hana/Downloads/blog-automation-v2/images/everland_mobile_reservation.webp",
]

IMAGE_ALTS = [
    "에버랜드 매표소 앞 긴 대기줄 성수기",
    "에버랜드 온라인 예매 vs 현장 구매 가격 비교",
    "에버랜드 모바일 사전 예약 QR 티켓 빠른 입장",
]

DRAFT_URL = "https://nolja100.tistory.com/manage/posts?category=&type=temp"

pw, browser = connect_cdp(log)
try:
    log("[1] 임시저장 글 목록 이동...")
    page = get_or_create_page(browser, navigate_to=DRAFT_URL)
    time.sleep(3)
    log(f"현재 URL: {page.url}")

    # 첫 번째 임시저장 글 클릭 (가장 최근)
    log("[2] 가장 최근 임시저장 글 클릭...")
    clicked = page.evaluate("""() => {
        // 임시저장 목록에서 첫 번째 글의 수정 링크 찾기
        const links = document.querySelectorAll('.link_item, a[href*="manage/posts"]');
        for (const link of links) {
            if (link.href && link.href.includes('manage/posts/') && !link.href.includes('?')) {
                link.click();
                return link.href;
            }
        }
        // 수정 버튼 방식
        const editBtns = document.querySelectorAll('a.btn_edit, .btn_manage a, button[title*="수정"]');
        if (editBtns.length > 0) {
            editBtns[0].click();
            return editBtns[0].href || '클릭됨';
        }
        return null;
    }""")
    log(f"[2] 클릭 결과: {clicked}")
    time.sleep(4)
    log(f"[2] 현재 URL: {page.url}")

    if "manage/posts" in page.url and "edit" not in page.url:
        # 글 목록에서 에디터로 이동 필요
        log("[2b] 에디터 URL 직접 찾는 중...")
        edit_url = page.evaluate("""() => {
            // 제목에 '에버랜드' 포함된 글 찾기
            const items = document.querySelectorAll('.tbl_manage tr, .list_post_row, [class*="post"]');
            for (const item of items) {
                if (item.textContent && item.textContent.includes('에버랜드')) {
                    const link = item.querySelector('a[href*="manage/posts/"]');
                    if (link) return link.href;
                }
            }
            // 폴백: 첫 번째 수정 링크
            const allLinks = document.querySelectorAll('a[href*="manage/posts/"]');
            for (const link of allLinks) {
                const href = link.href;
                if (href.match(/manage\\/posts\\/\\d+/)) return href;
            }
            return null;
        }""")
        log(f"[2b] 에디터 URL: {edit_url}")
        if edit_url:
            page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)
            log(f"[2b] 이동 후 URL: {page.url}")

    # 에디터 로드 확인
    log("[3] 에디터 로드 확인...")
    try:
        page.wait_for_selector("#editor-tistory_ifr, #post-title-inp", timeout=15000)
        log("[3] 에디터 로드 완료")
    except Exception as e:
        log(f"[3] 에디터 로드 실패: {e}, URL: {page.url}")
        # 임시저장 목록에서 직접 숫자 기반 URL 찾기
        log("[3b] 임시저장 글 수동 탐색...")
        page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)

        post_urls = page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="/manage/posts/"]');
            return Array.from(links).map(l => l.href).filter(h => /\\/manage\\/posts\\/\\d+/.test(h));
        }""")
        log(f"[3b] 발견된 글 URL: {post_urls[:5]}")

        if post_urls:
            # 에버랜드 글이 있을 가능성이 높은 URL로 이동 (숫자 큰 것 = 최신)
            import re
            url_nums = [(re.search(r'/(\d+)$', u), u) for u in post_urls]
            url_nums = [(int(m.group(1)), u) for m, u in url_nums if m]
            url_nums.sort(reverse=True)
            target_url = url_nums[0][1] if url_nums else None
            log(f"[3b] 가장 최근 글: {target_url}")
            if target_url:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(4)
                page.wait_for_selector("#editor-tistory_ifr", timeout=15000)
                log(f"[3b] 에디터 이동 완료: {page.url}")

    # 이미지 커서를 본문 특정 위치에 놓고 업로드
    # 에버랜드 글에는 이미지가 없으므로, 각 H2 섹션 뒤에 커서 위치 후 이미지 삽입
    log("[4] 이미지 삽입 시작...")

    # 삽입 위치: 도입부 끝, 문제점 섹션 중간, 마무리 전
    # TinyMCE에서 H2 요소 사이에 이미지 삽입
    INSERT_POSITIONS = [
        # (위치설명, 찾을_텍스트, 삽입_방향)
        ("도입부 뒤", "체력의 상당", "after_p"),
        ("문제점 섹션 뒤", "스마트줄서기 예약은", "after_p"),
        ("마무리 전", "에버랜드 공식 앱이나", "after_p"),
    ]

    for i, (img_path, alt) in enumerate(zip(IMAGE_PATHS, IMAGE_ALTS)):
        if not os.path.exists(img_path):
            log(f"[이미지 {i+1}] 파일 없음: {img_path}")
            continue

        # 삽입 위치로 커서 이동
        pos_text = INSERT_POSITIONS[i][1] if i < len(INSERT_POSITIONS) else None
        if pos_text:
            moved = page.evaluate(f"""() => {{
                const ed = tinymce.activeEditor;
                if (!ed) return false;
                const body = ed.getBody();
                const allP = body.querySelectorAll('p');
                for (const p of allP) {{
                    if (p.textContent.includes('{pos_text}')) {{
                        const range = ed.getDoc().createRange();
                        range.setStartAfter(p);
                        range.collapse(true);
                        ed.selection.setRng(range);
                        ed.focus();
                        return true;
                    }}
                }}
                // 폴백: 본문 끝에 커서
                const lastP = body.lastElementChild;
                if (lastP) {{
                    const range = ed.getDoc().createRange();
                    range.setStartAfter(lastP);
                    range.collapse(true);
                    ed.selection.setRng(range);
                    ed.focus();
                    return true;
                }}
                return false;
            }}""")
            log(f"[이미지 {i+1}] 커서 이동: {moved} (위치: {pos_text[:20]})")

        time.sleep(0.5)
        log(f"[이미지 {i+1}] 업로드 중: {Path(img_path).name}")
        ok = _tistory_upload_image(page, img_path, alt, on_log=log)
        log(f"[이미지 {i+1}] 결과: {'성공' if ok else '실패'}")
        time.sleep(2)

    # 임시저장 다시 클릭
    log("[5] 다시 임시저장 중...")
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
    time.sleep(3)
    if saved:
        log(f"✅ 이미지 삽입 + 임시저장 완료!")
        log(f"확인: https://nolja100.tistory.com/manage/posts")
    else:
        log("⚠️ 임시저장 버튼을 못 찾음. 수동 확인 필요.")

finally:
    pw.stop()
