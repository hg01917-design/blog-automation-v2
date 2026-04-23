"""
goodisak 임시저장 97번 글 찾아서 에디터로 열기 + 이미지 교체
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

# 1번 이미지: gaming-laptop-1-1.webp (유지)
KEEP_IMAGE = str(IMAGES_DIR / "gaming-laptop-1-1.webp")


def log(msg):
    print(f"[draft97] {msg}", flush=True)


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
                log(f"iframe: {sel}")
                return frame
    iframes = page.query_selector_all("iframe")
    if iframes:
        frame = iframes[0].content_frame()
        if frame:
            return frame
    return None


def main():
    log("=== sequence 97 이미지 교체 시작 ===")

    # 이미지 파일 확인
    for p in INSERT_PATHS:
        if not Path(p).exists():
            log(f"ERROR: 이미지 없음: {p}")
            sys.exit(1)
        log(f"이미지: {Path(p).name} ({Path(p).stat().st_size//1024}KB)")

    pw, browser = connect_cdp(on_log=log)
    log("CDP 연결 성공")

    try:
        # 현재 열린 탭 목록 확인
        all_pages = []
        for ctx in browser.contexts:
            for p in ctx.pages:
                all_pages.append(p.url)
        log(f"현재 열린 탭 ({len(all_pages)}개):")
        for i, u in enumerate(all_pages):
            log(f"  [{i}] {u[:80]}")

        # goodisak 관련 탭 찾기
        page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "goodisak.tistory.com/manage" in p.url:
                    page = p
                    log(f"goodisak 탭 발견: {p.url[:80]}")
                    break
            if page:
                break

        if page is None:
            log("goodisak 탭 없음 — 새로 열기")
            ctx = browser.contexts[0]
            page = ctx.new_page()

        page.bring_to_front()

        # Step 1: 임시저장 목록 페이지 이동
        log("임시저장 목록 이동...")
        page.goto("https://goodisak.tistory.com/manage/posts?state=temp",
                  wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        page.screenshot(path="/tmp/temp_list.png")
        log("임시저장 목록 스크린샷: /tmp/temp_list.png")

        # 글 목록에서 sequence 번호나 게이밍노트북 글 찾기
        draft_links = page.evaluate("""() => {
            const results = [];
            // 관리 목록의 글 링크들
            const selectors = [
                'a[href*="manage/post/"]',
                '.list-item a',
                '.post-list a',
                'table td a',
                '.manage-post a',
            ];
            const seen = new Set();
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                for (const a of els) {
                    const href = a.href || '';
                    if (href.includes('manage/post/') && !seen.has(href)) {
                        seen.add(href);
                        const li = a.closest('li, tr, .item') || a.parentElement;
                        const text = (li ? li.textContent : a.textContent).trim().replace(/\\s+/g, ' ');
                        results.push({href: href, text: text.substring(0, 120)});
                    }
                }
            }
            return results;
        }""")

        log(f"임시저장 글 링크 {len(draft_links)}개:")
        gaming_href = None
        for d in draft_links:
            log(f"  {d['href'].split('/')[-1]}: {d['text'][:80]}")
            if ("게이밍" in d["text"] or "gaming" in d["text"].lower() or
                    "노트북" in d["text"] or d["href"].endswith("/97")):
                gaming_href = d["href"]
                log(f"  ★ 게이밍노트북 글 발견!")

        # sequence 97 직접 찾기
        if not gaming_href:
            log("목록에서 못 찾음 — 페이지 HTML 분석...")
            # 페이지 소스에서 97 포함 링크 찾기
            src_links = page.evaluate("""() => {
                const all = document.querySelectorAll('a');
                const r = [];
                for (const a of all) {
                    if ((a.href || '').includes('/97')) {
                        r.push({href: a.href, text: a.textContent.trim().substring(0, 60)});
                    }
                }
                return r;
            }""")
            log(f"97 포함 링크: {src_links}")
            for l in src_links:
                if "manage/post" in l["href"]:
                    gaming_href = l["href"]
                    break

        if not gaming_href:
            log("임시저장 글 직접 순회...")
            # 모든 임시저장 글 목록에서 찾기 (페이지네이션 포함)
            for pg in range(1, 6):
                if pg > 1:
                    page.goto(f"https://goodisak.tistory.com/manage/posts?state=temp&page={pg}",
                              wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)

                found = page.evaluate("""() => {
                    const links = document.querySelectorAll('a[href*="manage/post/"]');
                    for (const a of links) {
                        const li = a.closest('li, tr, .item') || a.parentElement;
                        const text = (li ? li.textContent : a.textContent).trim();
                        if (text.includes('게이밍') || text.includes('gaming') ||
                                text.includes('노트북') || a.href.includes('/97')) {
                            return {href: a.href, text: text.substring(0, 100)};
                        }
                    }
                    return null;
                }""")

                if found:
                    gaming_href = found["href"]
                    log(f"페이지 {pg}에서 발견: {found['text'][:60]} → {gaming_href}")
                    break

                # 이 페이지에 글이 있는지 확인
                count = page.evaluate("() => document.querySelectorAll('a[href*=\"manage/post/\"]').length")
                if count == 0:
                    log(f"페이지 {pg}: 글 없음. 탐색 종료.")
                    break

        if not gaming_href:
            log("게이밍노트북 글을 찾을 수 없습니다!")
            log("현재 임시저장 목록 전체 텍스트 확인:")
            body_text = page.evaluate("() => document.body.innerText.substring(0, 2000)")
            log(body_text)
            pw.stop()
            sys.exit(1)

        # 에디터로 이동
        log(f"에디터 이동: {gaming_href}")
        page.goto(gaming_href, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        page.screenshot(path="/tmp/editor_97_real.png")
        log(f"에디터 URL: {page.url}")
        log("에디터 스크린샷: /tmp/editor_97_real.png")

        # 에디터 제목 확인
        title = page.evaluate("""() => {
            const inp = document.querySelector('[placeholder*="제목"], .tit-inp, input[name="title"]');
            return inp ? inp.value || inp.textContent : document.title;
        }""")
        log(f"글 제목: {title}")

        frame = find_iframe(page)
        if not frame:
            log("ERROR: iframe 없음!")
            pw.stop()
            sys.exit(1)

        # 현재 이미지 현황
        imgs_before = frame.evaluate("""() => {
            const imgs = document.body.querySelectorAll('img');
            return Array.from(imgs).map((img, i) => ({
                idx: i,
                src: img.src.substring(0, 80),
                alt: img.alt
            }));
        }""")
        log(f"현재 이미지 수: {len(imgs_before)}")
        for im in imgs_before:
            log(f"  [{im['idx']}] {im['src'][:70]}")

        # 이미지 2,3,4번 삭제 (0번=1번 이미지 유지)
        del_res = frame.evaluate("""() => {
            const imgs = Array.from(document.body.querySelectorAll('img'));
            let deleted = 0;
            for (let i = imgs.length - 1; i >= 1; i--) {
                const img = imgs[i];
                const p = img.parentElement;
                if (p && p !== document.body &&
                    (p.children.length === 1 || ['P','DIV','FIGURE'].includes(p.tagName))) {
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
        insert_count = 0
        for i, img_path in enumerate(INSERT_PATHS):
            img_data = Path(img_path).read_bytes()
            b64 = base64.b64encode(img_data).decode()
            mime = "image/jpeg"

            result = frame.evaluate("""(args) => {
                const {idx, b64, mime} = args;
                const wrapper = document.createElement('p');
                wrapper.style.textAlign = 'center';
                wrapper.style.margin = '20px 0';

                const img = document.createElement('img');
                img.src = 'data:' + mime + ';base64,' + b64;
                img.alt = '게이밍노트북 추천 이미지 ' + (idx + 2);
                img.style.maxWidth = '100%';
                img.style.height = 'auto';
                wrapper.appendChild(img);

                // 소제목 뒤에 삽입
                const headings = document.body.querySelectorAll('h2, h3');
                if (headings.length > idx) {
                    const h = headings[idx];
                    if (h.nextSibling) {
                        h.parentNode.insertBefore(wrapper, h.nextSibling);
                    } else {
                        h.parentNode.appendChild(wrapper);
                    }
                    return 'after_h' + idx + ': ' + (h.textContent || '').trim().substring(0, 30);
                } else {
                    document.body.appendChild(wrapper);
                    return 'appended_' + idx;
                }
            }""", {"idx": i, "b64": b64, "mime": mime})

            log(f"  [{i+1}/3] {Path(img_path).name}: {result}")
            if result:
                insert_count += 1
            page.wait_for_timeout(500)

        final_count = frame.evaluate("() => document.body.querySelectorAll('img').length")
        log(f"최종 이미지 수: {final_count}개 (삽입: {insert_count}/3개)")

        page.screenshot(path="/tmp/after_insert_97.png")
        log("삽입 후 스크린샷: /tmp/after_insert_97.png")

        # 임시저장 버튼 클릭
        log("임시저장 시도...")
        save_btn = page.query_selector("button:has-text('임시저장'), .btn-save-draft")
        if not save_btn:
            # JS로 탐색
            save_text = page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.trim().includes('임시저장')) {
                        btn.click();
                        return btn.textContent.trim();
                    }
                }
                return null;
            }""")
            if save_text:
                log(f"임시저장 클릭: '{save_text}'")
            else:
                log("임시저장 버튼 못 찾음 — Ctrl+S")
                page.keyboard.press("Control+s")
        else:
            save_btn.click()
            log("임시저장 버튼 클릭")

        page.wait_for_timeout(3000)
        page.screenshot(path="/tmp/saved_97.png")
        log("임시저장 완료 스크린샷: /tmp/saved_97.png")

        log("=== 완료 ===")
        log(f"sequence 97: 이미지 {insert_count}장 삽입 + 임시저장 완료")

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pw.stop()
        log("CDP 연결 종료")


if __name__ == "__main__":
    main()
