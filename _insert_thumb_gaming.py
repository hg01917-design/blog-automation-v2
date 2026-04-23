"""
thumb-게이밍노트북추천-36140-2,3,4.webp를
goodisak 게이밍노트북 draft에 삽입 (임시저장)
"""
import sys
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp

IMAGES_DIR = Path(__file__).parent / "images" / "goodisak"

IMG_PATHS = [
    IMAGES_DIR / "thumb-게이밍노트북추천-36140-2.webp",
    IMAGES_DIR / "thumb-게이밍노트북추천-36140-3.webp",
    IMAGES_DIR / "thumb-게이밍노트북추천-36140-4.webp",
]


def log(msg):
    print(f"[insert_thumb] {msg}", flush=True)


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
    log("=== 게이밍노트북 draft 이미지 삽입 ===")

    # 이미지 파일 확인
    for p in IMG_PATHS:
        if not p.exists():
            log(f"ERROR: 파일 없음: {p}")
            sys.exit(1)
        log(f"  OK: {p.name} ({p.stat().st_size // 1024}KB)")

    pw, browser = connect_cdp(on_log=log)
    try:
        # goodisak 탭 찾기
        page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "goodisak.tistory.com" in p.url or "welfare.baremi542.com" in p.url:
                    page = p
                    log(f"goodisak 탭: {p.url[:70]}")
                    break
            if page:
                break
        if not page:
            ctx = browser.contexts[0]
            page = ctx.pages[0]
            log(f"첫 번째 탭 사용: {page.url[:70]}")

        page.bring_to_front()

        # 현재 에디터 제목 확인
        title = page.evaluate("""() => {
            const inp = document.querySelector('[placeholder*="제목"], input[name="title"]');
            if (inp) return inp.value;
            const ce = document.querySelector('[contenteditable][class*="title"]');
            if (ce) return ce.textContent.trim();
            return '';
        }""")
        log(f"현재 에디터 제목: '{title}'")

        # 게이밍노트북 글이 아니면 임시저장 팝업에서 로드
        if "게이밍노트북" not in title:
            log("게이밍노트북 글 로드 필요 — 임시저장 팝업 열기")
            try:
                page.evaluate("window.onbeforeunload = null")
            except Exception:
                pass
            page.goto("https://goodisak.tistory.com/manage/newpost/",
                      wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            count_btn = page.query_selector('a.count[aria-label*="임시저장"]')
            if count_btn:
                count_btn.click()
                log("임시저장 버튼 클릭")
                page.wait_for_timeout(2000)

            links = page.query_selector_all('a.link_info')
            log(f"임시저장 팝업 링크 {len(links)}개")
            found = False
            for link in links:
                t = (link.text_content() or '').strip()
                if "게이밍노트북" in t:
                    link.click()
                    log(f"게이밍노트북 글 로드: '{t}'")
                    page.wait_for_timeout(5000)
                    found = True
                    break
            if not found:
                log("ERROR: 게이밍노트북 임시저장 글 없음!")
                pw.stop()
                sys.exit(1)

        # iframe 찾기
        frame = find_iframe(page)
        if not frame:
            log("ERROR: iframe 없음!")
            pw.stop()
            sys.exit(1)

        # 현재 이미지 현황
        imgs_now = frame.evaluate("""() => Array.from(document.body.querySelectorAll('img')).map((img, i) => ({
            idx: i, src: img.src.substring(0, 100)
        }))""")
        log(f"현재 이미지 {len(imgs_now)}개:")
        for im in imgs_now:
            log(f"  [{im['idx']}] {im['src'][:80]}")

        # data: 이미지 제거 (0번 kakao CDN 유지)
        res = frame.evaluate("""() => {
            const imgs = Array.from(document.body.querySelectorAll('img'));
            let removed = 0;
            for (let i = imgs.length - 1; i >= 0; i--) {
                const img = imgs[i];
                if (img.src.startsWith('data:') || img.src.startsWith('blob:')) {
                    const p = img.parentElement;
                    if (p && p !== document.body &&
                        ['P','DIV','FIGURE'].includes(p.tagName) && p.children.length === 1) {
                        p.remove();
                    } else {
                        img.remove();
                    }
                    removed++;
                }
            }
            return {removed, remaining: document.body.querySelectorAll('img').length};
        }""")
        log(f"data: 이미지 제거: {res['removed']}개, 남음: {res['remaining']}개")

        # 이미지 삽입 (h2/h3 다음에 순서대로)
        inserted = 0
        for i, img_path in enumerate(IMG_PATHS):
            img_data = img_path.read_bytes()
            b64 = base64.b64encode(img_data).decode()
            mime = "image/webp"

            result = frame.evaluate("""(args) => {
                const {idx, b64, mime, altText} = args;
                const wrapper = document.createElement('p');
                wrapper.style.textAlign = 'center';
                wrapper.style.margin = '20px 0';
                const img = document.createElement('img');
                img.src = 'data:' + mime + ';base64,' + b64;
                img.alt = altText;
                img.style.maxWidth = '100%';
                wrapper.appendChild(img);

                const headings = document.body.querySelectorAll('h2, h3');
                if (headings.length > idx) {
                    const h = headings[idx];
                    if (h.nextSibling) {
                        h.parentNode.insertBefore(wrapper, h.nextSibling);
                    } else {
                        h.parentNode.appendChild(wrapper);
                    }
                    return 'h' + idx + ': ' + (h.textContent||'').trim().substring(0,30);
                }
                document.body.appendChild(wrapper);
                return 'body_' + idx;
            }""", {"idx": i, "b64": b64, "mime": mime, "altText": f"게이밍노트북 추천 이미지 {i+2}"})

            log(f"  [{i+1}/{len(IMG_PATHS)}] {img_path.name}: {result}")
            if result:
                inserted += 1
            page.wait_for_timeout(400)

        final = frame.evaluate("() => document.body.querySelectorAll('img').length")
        log(f"최종 이미지: {final}개 (삽입 {inserted}/{len(IMG_PATHS)})")

        page.screenshot(path="/tmp/gaming_thumb_inserted.png")
        log("스크린샷: /tmp/gaming_thumb_inserted.png")

        # 임시저장 (발행하지 않음)
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
            log(f"임시저장: '{saved}'")
        else:
            page.keyboard.press("Control+s")
            log("Ctrl+S")

        page.wait_for_timeout(3000)
        page.screenshot(path="/tmp/gaming_thumb_saved.png")
        log("=== 완료 ===")
        log(f"이미지 {final}개 (kakao CDN 1개 + 새 이미지 {inserted}개)")

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pw.stop()
        log("CDP 종료")


if __name__ == "__main__":
    main()
