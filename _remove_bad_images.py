"""
에디터에서 data:base64 이미지(잘못 삽입된 것) 제거만 수행.
1번 카카오 CDN 이미지는 유지.
임시저장.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp


def log(msg):
    print(f"[remove_bad] {msg}", flush=True)


def find_iframe(page):
    for sel in ["iframe#editor-tistory_ifr", "iframe.tox-edit-area__iframe",
                "iframe[id*='mce']", "iframe[id*='editor']"]:
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
    pw, browser = connect_cdp(on_log=log)
    try:
        page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "goodisak.tistory.com/manage" in p.url:
                    page = p
                    break
            if page:
                break
        if not page:
            ctx = browser.contexts[0]
            page = ctx.pages[0]
        page.bring_to_front()

        title = page.evaluate("""() => {
            const inp = document.querySelector('[placeholder*="제목"], input[name="title"]');
            if (inp) return inp.value;
            return '';
        }""")
        log(f"현재 제목: '{title}'")

        if "게이밍노트북" not in title:
            log("게이밍노트북 글 아님 — 팝업에서 로드")
            try:
                page.evaluate("window.onbeforeunload = null")
            except Exception:
                pass
            page.goto("https://goodisak.tistory.com/manage/newpost/",
                      wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            btn = page.query_selector('a.count[aria-label*="임시저장"]')
            if btn:
                btn.click()
                page.wait_for_timeout(2000)
            links = page.query_selector_all('a.link_info')
            for link in links:
                t = (link.text_content() or '').strip()
                if "게이밍노트북" in t:
                    link.click()
                    log(f"로드: '{t}'")
                    page.wait_for_timeout(5000)
                    break

        frame = find_iframe(page)
        if not frame:
            log("iframe 없음!")
            pw.stop()
            return

        # 현재 이미지
        imgs = frame.evaluate("""() => Array.from(document.body.querySelectorAll('img')).map((img, i) => ({
            idx: i, src: img.src.substring(0, 80)
        }))""")
        log(f"현재 이미지 {len(imgs)}개:")
        for im in imgs:
            log(f"  [{im['idx']}] {im['src'][:70]}")

        # data: 이미지 제거 (0번 인덱스 제외)
        res = frame.evaluate("""() => {
            const imgs = Array.from(document.body.querySelectorAll('img'));
            let removed = 0;
            for (let i = imgs.length - 1; i >= 1; i--) {
                const img = imgs[i];
                if (img.src.startsWith('data:') || img.src.startsWith('blob:')) {
                    const p = img.parentElement;
                    if (p && p !== document.body && p.children.length === 1) {
                        p.remove();
                    } else {
                        img.remove();
                    }
                    removed++;
                }
            }
            return {removed, remaining: document.body.querySelectorAll('img').length};
        }""")
        log(f"제거: {res['removed']}개, 남음: {res['remaining']}개")

        # 임시저장
        saved = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                if (btn.textContent.trim().includes('임시저장')) { btn.click(); return btn.textContent.trim(); }
            }
            return null;
        }""")
        if saved:
            log(f"임시저장: '{saved}'")
        else:
            page.keyboard.press("Control+s")
            log("Ctrl+S")
        page.wait_for_timeout(2000)
        log(f"완료: 이미지 {res['remaining']}개 유지 (1번 카카오CDN 이미지)")

    finally:
        pw.stop()
        log("CDP 종료")


if __name__ == "__main__":
    main()
