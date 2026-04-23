"""
goodisak.tistory.com/manage/newpost/ 에디터 팝업에서 게이밍노트북 글 찾기
+ 기존 이미지 1번 유지, 2,3,4번 교체
"""
import sys
import base64
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp, get_or_create_page

IMAGES_DIR = Path(__file__).parent / "images"

# 삽입할 이미지: 2,3,4번 위치에 bing-gaming-2,3,4.jpg
INSERT_PATHS = [
    str(IMAGES_DIR / "bing-gaming-2.jpg"),
    str(IMAGES_DIR / "bing-gaming-3.jpg"),
    str(IMAGES_DIR / "bing-gaming-4.jpg"),
]


def log(msg):
    print(f"[popup_find] {msg}", flush=True)


def find_iframe(page):
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
                return frame
    iframes = page.query_selector_all("iframe")
    if iframes:
        return iframes[0].content_frame()
    return None


def main():
    log("=== 게이밍노트북 팝업 탐색 + 이미지 교체 ===")

    for p in INSERT_PATHS:
        if not Path(p).exists():
            log(f"ERROR: 이미지 없음: {p}")
            sys.exit(1)
        log(f"이미지: {Path(p).name} ({Path(p).stat().st_size//1024}KB)")

    pw, browser = connect_cdp(on_log=log)
    log("CDP 연결 성공")

    try:
        # 현재 탭 중 goodisak 탭 찾기
        page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "goodisak.tistory.com/manage" in p.url:
                    page = p
                    break
            if page:
                break

        if page is None:
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

        page.bring_to_front()

        # 에디터로 이동
        log("goodisak 에디터 이동...")
        try:
            page.evaluate("window.onbeforeunload = null")
        except Exception:
            pass
        page.goto("https://goodisak.tistory.com/manage/newpost/", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        page.screenshot(path="/tmp/newpost_before.png")
        log(f"에디터 URL: {page.url}")

        # 임시저장 버튼 찾기
        count_btn = page.query_selector('a.count[aria-label*="임시저장"]')
        if not count_btn:
            log("임시저장 버튼 없음 — 다른 선택자 시도")
            count_btn = page.query_selector('[aria-label*="임시저장"], .count_temp, .btn_temp')

        if not count_btn:
            # JS로 찾기
            count_btn_found = page.evaluate("""() => {
                const all = document.querySelectorAll('a, button');
                for (const el of all) {
                    const aria = el.getAttribute('aria-label') || '';
                    const text = el.textContent || '';
                    if (aria.includes('임시저장') || text.includes('임시저장')) {
                        el.click();
                        return el.textContent.trim().substring(0, 50);
                    }
                }
                return null;
            }""")
            if count_btn_found:
                log(f"임시저장 버튼 JS 클릭: '{count_btn_found}'")
            else:
                log("임시저장 버튼을 찾을 수 없음!")
                page.screenshot(path="/tmp/no_count_btn.png")
        else:
            count_btn.click()
            log("임시저장 버튼 클릭")

        page.wait_for_timeout(3000)
        page.screenshot(path="/tmp/popup_opened.png")
        log("팝업 스크린샷: /tmp/popup_opened.png")

        # 팝업 내 글 목록 확인
        draft_titles = page.evaluate("""() => {
            const links = document.querySelectorAll('a.link_info');
            return Array.from(links).map(a => ({
                text: a.textContent.trim(),
                href: a.href || ''
            }));
        }""")

        log(f"임시저장 목록 ({len(draft_titles)}개):")
        gaming_idx = -1
        for i, d in enumerate(draft_titles):
            gaming = "★" if ("게이밍노트북" in d["text"] or "gaming" in d["text"].lower()) else " "
            log(f"  {gaming}[{i}] {d['text'][:70]}")
            if gaming == "★":
                gaming_idx = i

        if gaming_idx == -1:
            log("게이밍노트북 글을 팝업에서 찾지 못함")
            log("모든 팝업 텍스트:")
            all_popup = page.evaluate("() => document.body.innerText.substring(0, 1000)")
            log(all_popup)
            pw.stop()
            sys.exit(1)

        # 게이밍노트북 글 클릭
        log(f"게이밍노트북 글 클릭: [{gaming_idx}] '{draft_titles[gaming_idx]['text']}'")
        links = page.query_selector_all('a.link_info')
        if gaming_idx < len(links):
            links[gaming_idx].click()
        else:
            log("ERROR: 링크 인덱스 초과!")
            pw.stop()
            sys.exit(1)

        page.wait_for_timeout(5000)
        page.screenshot(path="/tmp/gaming_editor_loaded.png")
        log(f"에디터 URL: {page.url}")

        # 제목 확인
        title = page.evaluate("""() => {
            const inp = document.querySelector('[placeholder*="제목"], input[name="title"]');
            if (inp) return inp.value;
            const ce = document.querySelector('[contenteditable][class*="title"]');
            if (ce) return ce.textContent.trim();
            return '';
        }""")
        log(f"글 제목: '{title}'")

        # iframe 찾기
        frame = find_iframe(page)
        if not frame:
            log("ERROR: iframe 없음!")
            pw.stop()
            sys.exit(1)

        # 현재 이미지 현황
        imgs = frame.evaluate("""() => {
            return Array.from(document.body.querySelectorAll('img')).map((img, i) => ({
                idx: i, src: img.src.substring(0, 100), alt: img.alt
            }));
        }""")
        log(f"현재 이미지 {len(imgs)}개:")
        for im in imgs:
            log(f"  [{im['idx']}] {im['src'][:80]}")

        # 이미지 2,3,4번 삭제 (0번=1번 이미지 유지)
        del_res = frame.evaluate("""() => {
            const imgs = Array.from(document.body.querySelectorAll('img'));
            let deleted = 0;
            for (let i = imgs.length - 1; i >= 1; i--) {
                const img = imgs[i];
                const p = img.parentElement;
                if (p && p !== document.body &&
                    ['P','DIV','FIGURE'].includes(p.tagName) && p.children.length === 1) {
                    p.remove();
                } else {
                    img.remove();
                }
                deleted++;
            }
            return {deleted, remaining: document.body.querySelectorAll('img').length};
        }""")
        log(f"삭제: {del_res['deleted']}개, 남음: {del_res['remaining']}개")

        # 새 이미지 3장 삽입
        count = 0
        for i, img_path in enumerate(INSERT_PATHS):
            img_data = Path(img_path).read_bytes()
            b64 = base64.b64encode(img_data).decode()

            result = frame.evaluate("""(args) => {
                const {idx, b64} = args;
                const wrapper = document.createElement('p');
                wrapper.style.textAlign = 'center';
                wrapper.style.margin = '20px 0';
                const img = document.createElement('img');
                img.src = 'data:image/jpeg;base64,' + b64;
                img.alt = '게이밍노트북 추천 이미지 ' + (idx + 2);
                img.style.maxWidth = '100%';
                wrapper.appendChild(img);

                const headings = document.body.querySelectorAll('h2, h3');
                if (headings.length > idx) {
                    const h = headings[idx];
                    if (h.nextSibling) h.parentNode.insertBefore(wrapper, h.nextSibling);
                    else h.parentNode.appendChild(wrapper);
                    return 'h' + idx + ': ' + (h.textContent||'').trim().substring(0,30);
                }
                document.body.appendChild(wrapper);
                return 'body_' + idx;
            }""", {"idx": i, "b64": b64})

            log(f"  [{i+1}/3] {Path(img_path).name}: {result}")
            if result:
                count += 1
            page.wait_for_timeout(500)

        final = frame.evaluate("() => document.body.querySelectorAll('img').length")
        log(f"최종 이미지: {final}개 (삽입 {count}/3)")

        page.screenshot(path="/tmp/gaming_after_insert.png")
        log("삽입 후 스크린샷: /tmp/gaming_after_insert.png")

        # 임시저장
        saved = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                if (btn.textContent.trim().includes('임시저장')) {
                    btn.click();
                    return btn.textContent.trim();
                }
            }
            return null;
        }""")
        if saved:
            log(f"임시저장 클릭: '{saved}'")
        else:
            page.keyboard.press("Control+s")
            log("Ctrl+S")

        page.wait_for_timeout(3000)
        page.screenshot(path="/tmp/gaming_saved.png")
        log("임시저장 완료 스크린샷: /tmp/gaming_saved.png")

        log("=== 완료 ===")
        log(f"이미지 {count}장 삽입 + 임시저장 완료")

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pw.stop()
        log("CDP 종료")


if __name__ == "__main__":
    main()
