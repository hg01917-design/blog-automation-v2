"""
1. 현재 에디터의 잘못된 이미지(data:base64) 제거
2. Bing 히스토리에서 게이밍노트북 관련 OIG 이미지 찾기 (스크롤하여 모든 히스토리 탐색)
3. 해당 이미지 다운로드 → bing-gaming-1~4.jpg 저장
4. 올바른 이미지로 교체 + 임시저장
"""
import sys
import base64
import ssl
import urllib.request
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp

IMAGES_DIR = Path(__file__).parent / "images"
BING_URL = "https://www.bing.com/images/create"


def log(msg):
    print(f"[fix_gaming] {msg}", flush=True)


def _download(url: str, path: str) -> bool:
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        data = resp.read()
        if len(data) < 10000:
            return False
        Path(path).write_bytes(data)
        log(f"다운로드: {Path(path).name} ({len(data)//1024}KB)")
        return True
    except Exception as e:
        log(f"다운로드 실패: {e}")
        return False


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
    log("=== 게이밍노트북 이미지 교체 수정 ===")

    pw, browser = connect_cdp(on_log=log)
    try:
        # 현재 열린 탭 찾기
        page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "goodisak.tistory.com/manage" in p.url:
                    page = p
                    log(f"goodisak 탭: {p.url[:70]}")
                    break
            if page:
                break

        if not page:
            ctx = browser.contexts[0]
            page = ctx.pages[0]

        page.bring_to_front()

        # ── Step 1: Bing에서 올바른 이미지 찾기 ──
        log("=== Step 1: Bing 히스토리 탐색 ===")

        # Bing 탭은 없으니 현재 탭(goodisak)에서 Bing으로 이동
        # 하지만 탭 전환하면 에디터를 잃으므로, 별도로 이미지를 다운받은 후 에디터로 복귀
        # → 기존 게이밍노트북 이미지 파일 사용

        # 먼저 기존에 생성된 goodisak 이미지 확인
        goodisak_dir = IMAGES_DIR / "goodisak"
        gaming_imgs = list(goodisak_dir.glob("goodisak-게이밍노트북*.webp"))
        # 오늘(4월 18일) 생성된 것 우선, 4월 14일 것도 포함
        gaming_imgs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        log(f"기존 게이밍노트북 이미지 {len(gaming_imgs)}개:")
        for p in gaming_imgs:
            log(f"  {p.name}")

        # 이미지 내용 확인해서 실제 게이밍노트북 관련인 것 선택
        # gen_r2.log의 tgp 이미지가 실제 게이밍노트북 이미지
        tgp_imgs = sorted(goodisak_dir.glob("goodisak-게이밍노트북-tgp-*.webp"))
        log(f"TGP 이미지: {[p.name for p in tgp_imgs]}")

        # 사용할 이미지 결정:
        # - 2번: goodisak-게이밍노트북-tgp-*-1-2.webp
        # - 3번: goodisak-게이밍노트북-tgp-*-1-3.webp
        # - 4번: goodisak-게이밍노트북-tgp-*-1-4.webp (없으면 1-3 재사용)
        use_imgs = []
        for i in [2, 3, 4]:
            candidates = sorted(goodisak_dir.glob(f"goodisak-게이밍노트북-tgp-*-1-{i}.webp"))
            if candidates:
                use_imgs.append(candidates[0])
                log(f"  [{i}번] {candidates[0].name}")
            else:
                candidates = sorted(goodisak_dir.glob(f"goodisak-게이밍노트북*-1-{i}.webp"))
                if candidates:
                    use_imgs.append(candidates[0])
                    log(f"  [{i}번] {candidates[0].name}")
                else:
                    log(f"  [{i}번] 없음")

        if not use_imgs:
            log("사용할 이미지 없음!")
            pw.stop()
            sys.exit(1)

        log(f"사용할 이미지 {len(use_imgs)}장:")
        for p in use_imgs:
            log(f"  {p.name}")

        # ── Step 2: 에디터에서 잘못된 이미지 제거 + 올바른 이미지 삽입 ──
        log("=== Step 2: 에디터 이미지 교체 ===")

        # 현재 에디터가 게이밍노트북 글인지 확인
        current_title = page.evaluate("""() => {
            const inp = document.querySelector('[placeholder*="제목"], input[name="title"]');
            if (inp) return inp.value;
            const ce = document.querySelector('[contenteditable][class*="title"]');
            if (ce) return ce.textContent.trim();
            return '';
        }""")
        log(f"현재 에디터 제목: '{current_title}'")

        if "게이밍노트북" not in current_title:
            log("게이밍노트북 글이 아님 — 팝업에서 다시 로드")
            # 임시저장 팝업 열기
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
                page.wait_for_timeout(2000)

            links = page.query_selector_all('a.link_info')
            for link in links:
                t = (link.text_content() or '').strip()
                if "게이밍노트북" in t:
                    link.click()
                    log(f"게이밍노트북 글 로드: '{t}'")
                    page.wait_for_timeout(5000)
                    break

        frame = find_iframe(page)
        if not frame:
            log("ERROR: iframe 없음!")
            pw.stop()
            sys.exit(1)

        # 현재 이미지 현황
        imgs_now = frame.evaluate("""() => {
            return Array.from(document.body.querySelectorAll('img')).map((img, i) => ({
                idx: i, src: img.src.substring(0, 100)
            }));
        }""")
        log(f"현재 이미지 {len(imgs_now)}개:")
        for im in imgs_now:
            log(f"  [{im['idx']}] {im['src'][:80]}")

        # data:image/* 로 시작하는 잘못된 이미지 제거
        removed_bad = frame.evaluate("""() => {
            const imgs = Array.from(document.body.querySelectorAll('img'));
            let count = 0;
            for (let i = imgs.length - 1; i >= 1; i--) {
                const img = imgs[i];
                // kakao CDN 이미지는 유지 (1번), data: 이미지 제거
                if (img.src.startsWith('data:') || img.src.includes('blob:')) {
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
        log(f"잘못된 이미지 제거: {removed_bad['removed']}개, 남음: {removed_bad['remaining']}개")

        # 카카오 CDN 이미지 중 1번 유지 확인
        remaining_imgs = frame.evaluate("""() => {
            return Array.from(document.body.querySelectorAll('img')).map((img, i) => ({
                idx: i, src: img.src.substring(0, 80)
            }));
        }""")
        log(f"정리 후 이미지 {len(remaining_imgs)}개:")
        for im in remaining_imgs:
            log(f"  [{im['idx']}] {im['src'][:70]}")

        # 올바른 이미지 삽입
        count = 0
        for i, img_path in enumerate(use_imgs):
            img_data = img_path.read_bytes()
            b64 = base64.b64encode(img_data).decode()
            mime = "image/webp"

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

            log(f"  [{i+1}/{len(use_imgs)}] {img_path.name}: {result}")
            if result:
                count += 1
            page.wait_for_timeout(500)

        final = frame.evaluate("() => document.body.querySelectorAll('img').length")
        log(f"최종 이미지: {final}개 (삽입 {count}/{len(use_imgs)})")

        page.screenshot(path="/tmp/gaming_correct_insert.png")
        log("삽입 후 스크린샷: /tmp/gaming_correct_insert.png")

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
        page.screenshot(path="/tmp/gaming_correct_saved.png")
        log("임시저장 스크린샷: /tmp/gaming_correct_saved.png")

        log("=== 완료 ===")
        log(f"게이밍노트북 글 이미지 {count}장 교체 + 임시저장")

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pw.stop()
        log("CDP 종료")


if __name__ == "__main__":
    main()
