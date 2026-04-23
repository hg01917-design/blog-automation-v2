"""
goodisak 티스토리 게이밍노트북 draft:
1. 현재 열린 newpost 탭 또는 임시저장 목록에서 게이밍노트북 글 찾기
2. poster._tistory_upload_image 사용해서 이미지 4장 삽입
3. 임시저장

주의: 발행 버튼 절대 클릭 금지. 이미지 삽입 + 임시저장만.
"""
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp, get_or_create_page
from poster import _tistory_upload_image

# bing-gaming-final-*.webp 없음 → bing-gaming-1~4.jpg 사용
IMAGE_PATHS = [
    "/Users/hana/Downloads/blog-automation-v2/images/bing-gaming-1.jpg",
    "/Users/hana/Downloads/blog-automation-v2/images/bing-gaming-2.jpg",
    "/Users/hana/Downloads/blog-automation-v2/images/bing-gaming-3.jpg",
    "/Users/hana/Downloads/blog-automation-v2/images/bing-gaming-4.jpg",
]


def log(msg):
    print(f"[gaming_insert] {msg}", flush=True)


def find_iframe(page):
    """TinyMCE iframe 찾기"""
    for sel in [
        "iframe#editor-tistory_ifr",
        "iframe.tox-edit-area__iframe",
        "iframe[id*='mce']",
        "iframe[id*='editor']",
    ]:
        el = page.query_selector(sel)
        if el:
            frame = el.content_frame()
            if frame:
                log(f"iframe 발견: {sel}")
                return frame

    iframes = page.query_selector_all("iframe")
    log(f"전체 iframe 수: {len(iframes)}")
    for i, ifr in enumerate(iframes):
        id_attr = ifr.get_attribute("id") or ""
        src = ifr.get_attribute("src") or ""
        log(f"  [{i}] id={id_attr}, src={src[:60]}")
    if iframes:
        frame = iframes[0].content_frame()
        if frame:
            log("첫 번째 iframe 사용")
            return frame
    return None


def main():
    log("=== goodisak 게이밍노트북 이미지 삽입 시작 ===")

    # 이미지 파일 존재 확인
    for p in IMAGE_PATHS:
        if not Path(p).exists():
            log(f"ERROR: 이미지 파일 없음: {p}")
            sys.exit(1)
        log(f"이미지 확인: {Path(p).name} ({Path(p).stat().st_size:,} bytes)")

    pw, browser = connect_cdp(on_log=log)
    log("CDP 연결 성공")

    # ── Step 1: 에디터 탭 찾기 ──
    # 우선순위: 1) newpost 탭(에디터 직접 열린 것), 2) 임시저장 목록으로 이동 후 탐색
    page = None

    # 현재 열린 탭 중 goodisak newpost 탭 찾기
    for ctx in browser.contexts:
        for p in ctx.pages:
            url = p.url
            if "goodisak.tistory.com/manage/newpost" in url or "goodisak.tistory.com/manage/post/" in url:
                page = p
                log(f"goodisak 에디터 탭 발견: {url[:80]}")
                break
        if page:
            break

    if page:
        page.bring_to_front()
        page.wait_for_timeout(1000)

        # 에디터 탭의 제목 확인
        editor_title = page.evaluate("""() => {
            const inp = document.querySelector('input[name=title], #title, .title-input');
            if (inp) return inp.value;
            const titleEl = document.querySelector('.editor-title, .tt_article_title');
            if (titleEl) return titleEl.textContent.trim();
            return '';
        }""")
        log(f"에디터 글 제목: '{editor_title}'")

        # 제목에 게이밍노트북 없으면 iframe에서 내용 확인
        frame = find_iframe(page)
        if frame:
            body_preview = frame.evaluate("() => document.body.innerText.substring(0, 300)")
            log(f"에디터 내용 미리보기: {body_preview[:200]}")
    else:
        # newpost 탭이 없으면 임시저장 목록에서 찾기
        log("newpost 탭 없음. 임시저장 목록에서 탐색...")

        # goodisak 관리 탭 찾기
        manage_page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "goodisak.tistory.com/manage" in p.url:
                    manage_page = p
                    break
            if manage_page:
                break

        if manage_page is None:
            manage_page = get_or_create_page(browser, navigate_to="https://goodisak.tistory.com/manage/posts")

        manage_page.bring_to_front()
        manage_page.goto("https://goodisak.tistory.com/manage/posts?state=temp", wait_until="domcontentloaded")
        manage_page.wait_for_timeout(3000)

        # 게이밍노트북 글 링크 찾기 (전 페이지)
        found_href = None
        for pg_num in range(1, 6):
            if pg_num > 1:
                manage_page.goto(f"https://goodisak.tistory.com/manage/posts?state=temp&page={pg_num}",
                                 wait_until="domcontentloaded")
                manage_page.wait_for_timeout(2000)

            found = manage_page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="manage/post/"]');
                for (const a of links) {
                    const li = a.closest('li') || a.parentElement;
                    const text = li ? li.textContent : a.textContent;
                    if (text.includes('게이밍노트북') || text.includes('게이밍 노트북') ||
                        text.includes('gaming laptop') || text.includes('게이밍노트북 추천')) {
                        return {href: a.href, text: text.trim().substring(0, 100)};
                    }
                }
                return null;
            }""")

            if found and found.get("href"):
                log(f"페이지 {pg_num}에서 발견: {found['href']}")
                found_href = found["href"]
                break

        if not found_href:
            log("ERROR: 게이밍노트북 임시저장 글을 찾을 수 없습니다!")
            log("현재 열린 에디터 탭이 없고, 임시저장 목록에도 없습니다.")
            pw.stop()
            sys.exit(1)

        manage_page.goto(found_href, wait_until="domcontentloaded")
        manage_page.wait_for_timeout(4000)
        page = manage_page

    if page is None:
        log("ERROR: 에디터 페이지 없음!")
        pw.stop()
        sys.exit(1)

    page.screenshot(path="/tmp/goodisak_editor_open.png")
    log(f"에디터 URL: {page.url}")
    log("에디터 스크린샷: /tmp/goodisak_editor_open.png")

    # ── Step 2: TinyMCE iframe으로 글 내용 확인 ──
    frame = find_iframe(page)

    if not frame:
        log("WARNING: 에디터 iframe 없음 — 계속 진행 (외부 에디터일 수 있음)")

    if frame:
        content_len = frame.evaluate("() => document.body.innerText.length")
        log(f"글자 수: {content_len}")

        if content_len < 100:
            log("WARNING: 글자 수가 너무 적습니다. 게이밍노트북 글이 맞는지 확인 필요.")
            body_text = frame.evaluate("() => document.body.innerText.substring(0, 500)")
            log(f"본문 내용:\n{body_text}")

    # ── Step 3: poster._tistory_upload_image 로 이미지 4장 삽입 ──
    log("=== _tistory_upload_image 방식으로 이미지 삽입 시작 ===")
    success_count = 0
    for i, img_path in enumerate(IMAGE_PATHS, 1):
        if not os.path.exists(img_path):
            log(f"[{i}/4] 파일 없음: {img_path}")
            continue
        log(f"[{i}/4] 업로드 중: {Path(img_path).name}")
        ok = _tistory_upload_image(page, img_path, alt=f"게이밍노트북추천 {i}", on_log=log)
        if ok:
            success_count += 1
            log(f"[{i}/4] 완료")
        else:
            log(f"[{i}/4] 실패")
        page.wait_for_timeout(1500)

    log(f"이미지 삽입 완료: {success_count}/4장")

    page.screenshot(path="/tmp/goodisak_gaming_after_insert.png")
    log("삽입 후 스크린샷: /tmp/goodisak_gaming_after_insert.png")

    # ── Step 4: 임시저장 ──
    log("임시저장 시도...")
    saved = page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            const text = btn.textContent.trim();
            if (text.includes('임시저장') || text === '저장') {
                btn.click();
                return text;
            }
        }
        return null;
    }""")
    if saved:
        log(f"임시저장 클릭: '{saved}'")
    else:
        log("임시저장 버튼 없음 — Ctrl+S 시도")
        page.keyboard.press("Control+s")

    page.wait_for_timeout(3000)
    page.screenshot(path="/tmp/goodisak_gaming_final.png")
    log("최종 스크린샷: /tmp/goodisak_gaming_final.png")

    # ── Step 5: 텔레그램 보고 ──
    import subprocess
    tg_msg = f"✅ 이미지 삽입 완료\n블로그: goodisak\n글: 게이밍노트북추천 2026\n삽입: {success_count}/4장"
    subprocess.run(
        ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
         '--photo', '/tmp/goodisak_gaming_after_insert.png', tg_msg],
        capture_output=True, timeout=30
    )
    log("텔레그램 보고 완료")

    log("=== 완료 ===")
    log(f"삽입된 이미지: {success_count}/4장")

    pw.stop()
    log("CDP 연결 종료")


if __name__ == "__main__":
    main()
