"""
Bing Image Creator로 게이밍노트북 이미지 3장 새로 생성
+ goodisak 에디터에 삽입 + 임시저장
"""
import sys
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp, get_or_create_page
from bing_image import generate_images_bing

IMAGES_DIR = Path(__file__).parent / "images"


def log(msg):
    print(f"[bing_gen] {msg}", flush=True)


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
    log("=== Bing으로 게이밍노트북 이미지 생성 + 삽입 ===")

    # Bing으로 이미지 3장 생성
    log("Bing 이미지 생성 중...")
    results = generate_images_bing([
        {'index': 2, 'prompt': 'Gaming laptop with RGB keyboard glowing, high-performance GPU benchmark on screen, dark gaming desk setup, professional product photo, no text', 'filename': 'gaming-laptop-b-2.jpg'},
        {'index': 3, 'prompt': 'Gaming laptop with large cooling fan vents and heat pipes visible, thermal management diagram, tech product photo, dark background', 'filename': 'gaming-laptop-b-3.jpg'},
        {'index': 4, 'prompt': 'Gaming laptop side by side comparison of different GPU models RTX laptop, performance chart style, clean tech background', 'filename': 'gaming-laptop-b-4.jpg'},
    ], skip_webp=True, on_log=log, output_dir=str(IMAGES_DIR))

    log(f"Bing 결과: {results}")

    if not results:
        log("Bing 생성 실패!")
        sys.exit(1)

    # 생성된 이미지 확인
    img_paths = [results.get(2), results.get(3), results.get(4)]
    img_paths = [p for p in img_paths if p and Path(p).exists()]

    if not img_paths:
        log("이미지 파일 없음!")
        sys.exit(1)

    log(f"생성된 이미지 {len(img_paths)}장:")
    for p in img_paths:
        log(f"  {p}")

    # 에디터에 삽입
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
        log(f"현재 에디터 제목: '{title}'")

        if "게이밍노트북" not in title:
            log("게이밍노트북 글 로드 필요")
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
            log("ERROR: iframe 없음!")
            return

        # 현재 이미지 확인
        imgs = frame.evaluate("""() => Array.from(document.body.querySelectorAll('img')).map((img,i) => ({
            idx: i, src: img.src.substring(0,80)
        }))""")
        log(f"현재 이미지 {len(imgs)}개:")
        for im in imgs:
            log(f"  [{im['idx']}] {im['src'][:70]}")

        # 이미지 삽입
        count = 0
        for i, img_path in enumerate(img_paths):
            img_data = Path(img_path).read_bytes()
            b64 = base64.b64encode(img_data).decode()
            ext = Path(img_path).suffix.lower()
            mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/webp"

            result = frame.evaluate("""(args) => {
                const {idx, b64, mime} = args;
                const wrapper = document.createElement('p');
                wrapper.style.textAlign = 'center';
                wrapper.style.margin = '20px 0';
                const img = document.createElement('img');
                img.src = 'data:' + mime + ';base64,' + b64;
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
            }""", {"idx": i, "b64": b64, "mime": mime})

            log(f"  [{i+1}/{len(img_paths)}] {Path(img_path).name}: {result}")
            if result:
                count += 1
            page.wait_for_timeout(400)

        final = frame.evaluate("() => document.body.querySelectorAll('img').length")
        log(f"최종 이미지: {final}개 (삽입 {count}/{len(img_paths)})")

        page.screenshot(path="/tmp/gaming_bing_inserted.png")

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

        page.wait_for_timeout(3000)
        page.screenshot(path="/tmp/gaming_bing_saved.png")
        log("=== 완료 ===")
        log(f"이미지 {count}장 삽입 + 임시저장")

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pw.stop()
        log("CDP 종료")


if __name__ == "__main__":
    main()
