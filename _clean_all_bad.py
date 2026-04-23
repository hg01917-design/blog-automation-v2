"""모든 data:base64 이미지 제거, kakao CDN 이미지만 유지"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp


def log(msg):
    print(f"[clean] {msg}", flush=True)


def find_iframe(page):
    for sel in ["iframe#editor-tistory_ifr", "iframe.tox-edit-area__iframe",
                "iframe[id*='mce']", "iframe[id*='editor']"]:
        el = page.query_selector(sel)
        if el:
            f = el.content_frame()
            if f:
                return f
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
                if "goodisak.tistory.com" in p.url:
                    page = p
                    break
            if page:
                break
        if not page:
            ctx = browser.contexts[0]
            page = ctx.pages[0]
        page.bring_to_front()

        title = page.evaluate("() => { const i = document.querySelector('[placeholder*=\"제목\"]'); return i ? i.value : ''; }")
        log(f"제목: '{title}'")

        frame = find_iframe(page)
        if not frame:
            log("iframe 없음!")
            return

        imgs = frame.evaluate("""() => Array.from(document.body.querySelectorAll('img')).map((img, i) => ({
            idx: i, src: img.src.substring(0, 90)
        }))""")
        log(f"현재 이미지 {len(imgs)}개:")
        for im in imgs:
            log(f"  [{im['idx']}] {im['src'][:80]}")

        # 모든 data: 이미지 제거 (kakao CDN은 유지)
        res = frame.evaluate("""() => {
            const imgs = Array.from(document.body.querySelectorAll('img'));
            let removed = 0;
            for (let i = imgs.length - 1; i >= 0; i--) {
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

        imgs_after = frame.evaluate("""() => Array.from(document.body.querySelectorAll('img')).map((img, i) => ({
            idx: i, src: img.src.substring(0, 90)
        }))""")
        for im in imgs_after:
            log(f"  남은[{im['idx']}] {im['src'][:80]}")

        # 임시저장
        saved = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                if (btn.textContent.trim().includes('임시저장')) { btn.click(); return true; }
            }
            return false;
        }""")
        if not saved:
            page.keyboard.press("Control+s")
        page.wait_for_timeout(2000)
        log("임시저장 완료")

    finally:
        pw.stop()
        log("완료")


if __name__ == "__main__":
    main()
