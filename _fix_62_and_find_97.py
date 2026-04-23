"""
1. 62번 글 복구 (Ctrl+Z로 되돌리기 또는 이미지 제거)
2. 97번 글 찾기 (전체 글 목록에서 탐색)
3. 97번 글에 이미지 교체 + 임시저장
"""
import sys
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp, get_or_create_page

IMAGES_DIR = Path(__file__).parent / "images"

INSERT_PATHS = [
    str(IMAGES_DIR / "bing-gaming-2.jpg"),
    str(IMAGES_DIR / "bing-gaming-3.jpg"),
    str(IMAGES_DIR / "bing-gaming-4.jpg"),
]


def log(msg):
    print(f"[fix97] {msg}", flush=True)


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


def restore_62(page):
    """62번 글에서 방금 삽입한 bing 이미지 제거 후 임시저장"""
    log("=== 62번 글 복구 ===")

    frame = find_iframe(page)
    if not frame:
        log("iframe 없음")
        return

    imgs = frame.evaluate("""() => {
        return Array.from(document.body.querySelectorAll('img')).map((img,i) => ({
            idx: i, src: img.src.substring(0, 80), alt: img.alt
        }));
    }""")
    log(f"현재 이미지 {len(imgs)}개:")
    for im in imgs:
        log(f"  [{im['idx']}] {im['src'][:70]}")

    # data:image/jpeg 로 시작하는 이미지 (방금 삽입한 것) 제거
    removed = frame.evaluate("""() => {
        const imgs = Array.from(document.body.querySelectorAll('img'));
        let count = 0;
        for (const img of imgs) {
            if (img.src.startsWith('data:image/jpeg')) {
                const p = img.parentElement;
                if (p && p !== document.body &&
                    ['P','DIV','FIGURE'].includes(p.tagName) && p.children.length === 1) {
                    p.remove();
                } else {
                    img.remove();
                }
                count++;
            }
        }
        return {removed: count, remaining: document.body.querySelectorAll('img').length};
    }""")
    log(f"base64 이미지 {removed['removed']}개 제거, 남음: {removed['remaining']}개")

    # 임시저장
    saved = page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.textContent.trim().includes('임시저장')) {
                btn.click();
                return btn.textContent.trim();
            }
        }
        return null;
    }""")
    if saved:
        log(f"62번 임시저장: '{saved}'")
    else:
        page.keyboard.press("Control+s")
        log("62번 Ctrl+S")

    page.wait_for_timeout(3000)
    log("62번 복구 완료")


def find_97(page):
    """전체 글 목록에서 sequence 97 또는 게이밍노트북 글 찾기"""
    log("=== 97번 글 찾기 ===")

    # 전체 글 목록 (임시저장 포함)
    for state in ["temp", "public", "private", "protect", ""]:
        url = f"https://goodisak.tistory.com/manage/posts"
        if state:
            url += f"?state={state}"
        log(f"상태 '{state}' 탐색: {url}")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # 페이지네이션 포함 최대 5페이지
        for pg in range(1, 6):
            if pg > 1:
                purl = url + ("&" if "?" in url else "?") + f"page={pg}"
                page.goto(purl, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

            found = page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="manage/post/"]');
                for (const a of links) {
                    const href = a.href || '';
                    const m = href.match(/manage\\/post\\/(\\d+)/);
                    const num = m ? parseInt(m[1]) : 0;
                    const li = a.closest('li, tr, .item') || a.parentElement;
                    const text = (li ? li.textContent : a.textContent).trim().replace(/\\s+/g, ' ');

                    if (num === 97) {
                        return {href: href, num: num, text: text.substring(0, 120)};
                    }
                    if (text.includes('게이밍노트북') || text.includes('게이밍 노트북') ||
                        (text.includes('게이밍') && text.includes('노트북'))) {
                        return {href: href, num: num, text: text.substring(0, 120)};
                    }
                }
                // 페이지 최대 번호 확인
                const nums = [];
                for (const a of links) {
                    const m = (a.href || '').match(/manage\\/post\\/(\\d+)/);
                    if (m) nums.push(parseInt(m[1]));
                }
                return {not_found: true, max: nums.length > 0 ? Math.max(...nums) : 0,
                        min: nums.length > 0 ? Math.min(...nums) : 0, count: nums.length};
            }""")

            if found and not found.get("not_found"):
                log(f"발견! num={found['num']}, {found['text'][:80]}")
                return found["href"]
            elif found:
                log(f"  페이지 {pg}: {found['count']}개, 번호 {found['min']}~{found['max']}")
                if found["count"] == 0:
                    break
                # 97번보다 낮은 번호만 있으면 이 상태에선 없음
                if found["max"] < 97 and pg >= 2:
                    break

    log("97번 글 없음")
    return None


def insert_images_to_post(page, gaming_href):
    """글 에디터 열고 이미지 교체"""
    log(f"=== 이미지 삽입: {gaming_href} ===")

    page.goto(gaming_href, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)

    page.screenshot(path="/tmp/target_editor.png")
    log(f"에디터 URL: {page.url}")

    # 제목 확인
    title = page.evaluate("""() => {
        const inp = document.querySelector('[placeholder*="제목"], .tit-inp, input[name="title"], [contenteditable][class*="title"]');
        if (inp) return inp.value || inp.textContent || '';
        return document.title;
    }""")
    log(f"글 제목: {title}")

    frame = find_iframe(page)
    if not frame:
        log("ERROR: iframe 없음!")
        return False

    # 현재 이미지
    imgs_before = frame.evaluate("""() => {
        return Array.from(document.body.querySelectorAll('img')).map((img,i) => ({
            idx: i, src: img.src.substring(0, 80), alt: img.alt
        }));
    }""")
    log(f"현재 이미지 {len(imgs_before)}개:")
    for im in imgs_before:
        log(f"  [{im['idx']}] {im['src'][:70]}")

    # 이미지 2,3,4번 삭제 (0번 유지)
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

    # 이미지 3장 삽입
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
                return 'h' + idx + ': ' + (h.textContent||'').trim().substring(0,25);
            }
            document.body.appendChild(wrapper);
            return 'body_' + idx;
        }""", {"idx": i, "b64": b64})

        log(f"  [{i+1}/3] {Path(img_path).name}: {result}")
        if result:
            count += 1
        page.wait_for_timeout(400)

    final = frame.evaluate("() => document.body.querySelectorAll('img').length")
    log(f"최종 이미지: {final}개 (삽입 {count}/3)")

    page.screenshot(path="/tmp/target_after_insert.png")

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
        log(f"임시저장: '{saved}'")
    else:
        page.keyboard.press("Control+s")
        log("Ctrl+S")

    page.wait_for_timeout(3000)
    page.screenshot(path="/tmp/target_saved.png")
    log("임시저장 완료")
    return count > 0


def main():
    log("=== sequence 97 찾기 + 이미지 교체 ===")

    for p in INSERT_PATHS:
        if not Path(p).exists():
            log(f"ERROR: {p}")
            sys.exit(1)

    pw, browser = connect_cdp(on_log=log)
    log("CDP 연결")

    try:
        # 현재 62번 에디터 탭 사용
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

        # 62번 복구
        log("62번 글 복구 중...")
        restore_62(page)

        # 97번 찾기
        gaming_href = find_97(page)

        if not gaming_href:
            log("97번 글을 찾을 수 없습니다")
            log("전체 임시저장 글 목록을 다시 확인해주세요")
            # 임시저장 목록 전체 텍스트 덤프
            page.goto("https://goodisak.tistory.com/manage/posts?state=temp",
                      wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            all_text = page.evaluate("() => document.body.innerText.substring(0, 3000)")
            log(f"현재 임시저장 목록:\n{all_text}")
            pw.stop()
            sys.exit(1)

        # 97번에 이미지 삽입
        ok = insert_images_to_post(page, gaming_href)
        if ok:
            log("=== 완료 ===")
        else:
            log("이미지 삽입 실패")

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pw.stop()
        log("CDP 종료")


if __name__ == "__main__":
    main()
