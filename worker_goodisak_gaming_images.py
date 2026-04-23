"""
워커: goodisak 티스토리 '게이밍노트북추천' 드래프트에 이미지 삽입
1. 드래프트 에디터 열기
2. H2/H3 소제목 파악
3. 기존 이미지 삭제
4. Bing으로 소제목별 이미지 생성
5. 소제목 바로 아래 이미지 삽입
6. 임시저장
"""
import sys
import time
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from browser import connect_cdp, get_or_create_page
from bing_image import generate_images_bing

OUTPUT_DIR = "/tmp/goodisak_gaming_images"
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

def log(msg):
    print(f"[worker_goodisak] {msg}", flush=True)


def upload_image_to_tistory(page, img_path: str) -> str | None:
    """Tistory API 파일 업로드 → 반환된 이미지 URL (or None)"""
    log(f"Tistory 업로드 시도: {Path(img_path).name}")
    try:
        # 1) 파일 input 찾기 (숨겨진 input[type=file])
        # Tistory 에디터: 이미지 업로드 버튼 클릭 → 파일 선택 팝업
        # set_input_files 방식으로 직접 주입
        file_input = page.query_selector("input[type='file'][accept*='image']")
        if not file_input:
            # 숨겨진 파일 input도 탐색
            file_inputs = page.query_selector_all("input[type='file']")
            log(f"파일 input 수: {len(file_inputs)}")
            if file_inputs:
                file_input = file_inputs[0]

        if file_input:
            page.set_input_files(file_input, img_path)
            page.wait_for_timeout(3000)
            log("파일 input에 경로 주입 완료")
            return img_path  # 임시 반환 (실제 URL은 업로드 후 에디터가 처리)
        else:
            log("파일 input 없음 — 카메라 버튼 클릭 시도")
            return None
    except Exception as e:
        log(f"업로드 실패: {e}")
        return None


def click_image_upload_btn(page) -> bool:
    """Tistory 에디터 이미지 업로드 버튼 클릭"""
    selectors = [
        "button[aria-label*='이미지']",
        "button[title*='이미지']",
        ".toolbar button[data-command='image']",
        ".tox-tbtn[aria-label*='이미지']",
        "button.btn_img",
        "[data-tiara-action='image']",
    ]
    for sel in selectors:
        btn = page.query_selector(sel)
        if btn:
            log(f"이미지 버튼 발견: {sel}")
            btn.click()
            page.wait_for_timeout(1500)
            return True

    # JS로 찾기
    result = page.evaluate("""() => {
        const btns = document.querySelectorAll('button, a');
        for (const btn of btns) {
            const label = (btn.getAttribute('aria-label') || btn.getAttribute('title') || btn.textContent || '').toLowerCase();
            if (label.includes('image') || label.includes('이미지') || label.includes('사진')) {
                btn.click();
                return btn.textContent.trim().substring(0, 30);
            }
        }
        return null;
    }""")
    if result:
        log(f"JS 이미지 버튼 클릭: {result}")
        page.wait_for_timeout(1500)
        return True
    return False


def insert_image_via_js(frame, img_path: str, after_heading_index: int, heading_tag: str = 'h2') -> bool:
    """이미지를 base64로 인코딩하여 지정 소제목 바로 다음에 삽입 (임시 방법)"""
    import base64
    img_data = Path(img_path).read_bytes()
    b64 = base64.b64encode(img_data).decode()

    ext = Path(img_path).suffix.lower()
    mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
    mime = mime_map.get(ext, 'image/jpeg')

    result = frame.evaluate(f"""(idx) => {{
        const headings = document.body.querySelectorAll('{heading_tag}, h2, h3');
        if (headings.length === 0) return 'no_headings';
        const h = headings[Math.min(idx, headings.length - 1)];

        const wrapper = document.createElement('p');
        wrapper.style.textAlign = 'center';
        wrapper.style.margin = '16px 0';

        const img = document.createElement('img');
        img.src = 'data:{mime};base64,{b64}';
        img.style.maxWidth = '100%';
        img.style.height = 'auto';
        img.setAttribute('data-inserted', 'bing');

        wrapper.appendChild(img);

        if (h.nextSibling) {{
            h.parentNode.insertBefore(wrapper, h.nextSibling);
        }} else {{
            h.parentNode.appendChild(wrapper);
        }}
        return 'ok_' + idx;
    }}""", after_heading_index)

    log(f"  JS 이미지 삽입 결과: {result}")
    return result and result.startswith('ok')


def tistory_upload_and_insert(page, frame, img_path: str, heading_index: int) -> bool:
    """
    Tistory 에디터에서 이미지 업로드 버튼 → 파일 선택 → 삽입 후
    JS로 해당 이미지를 소제목 다음으로 이동
    """
    log(f"이미지 삽입 시작 [소제목 {heading_index}]: {Path(img_path).name}")

    # 현재 이미지 수 기록
    before_count = frame.evaluate("() => document.body.querySelectorAll('img[data-tistory-image-id], img[src*=\"tistory\"], img[data-inserted]').length")

    # 소제목 뒤에 커서 배치 (클릭으로)
    placed = frame.evaluate(f"""(idx) => {{
        const headings = document.body.querySelectorAll('h2, h3');
        if (headings.length === 0) return false;
        const h = headings[Math.min(idx, headings.length - 1)];

        // h 다음에 있는 p/div 요소 클릭
        let target = h.nextElementSibling;
        if (!target) {{
            // 마지막 요소면 body 마지막 클릭
            const children = document.body.children;
            target = children[children.length - 1];
        }}

        if (target) {{
            const range = document.createRange();
            range.setStart(target, 0);
            range.collapse(true);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            return true;
        }}
        return false;
    }}""", heading_index)
    log(f"  커서 배치: {placed}")
    page.wait_for_timeout(500)

    # 파일 input 찾기 (숨겨진 것 포함)
    file_input = None
    for sel in ["input[type='file'][accept*='image']", "input[type='file']"]:
        inputs = page.query_selector_all(sel)
        if inputs:
            file_input = inputs[0]
            log(f"  파일 input 발견: {sel}")
            break

    if not file_input:
        log("  파일 input 없음 — JS 직접 삽입으로 폴백")
        return insert_image_via_js(frame, img_path, heading_index)

    try:
        page.set_input_files(file_input, img_path)
        log("  파일 경로 주입 완료")
        page.wait_for_timeout(4000)  # 업로드 대기

        # 업로드 후 이미지 수 확인
        after_count = frame.evaluate("() => document.body.querySelectorAll('img').length")
        log(f"  업로드 후 이미지 수: before={before_count}, after={after_count}")

        if after_count > before_count:
            # 새로 삽입된 이미지를 소제목 다음으로 이동
            moved = frame.evaluate(f"""(idx) => {{
                const imgs = document.body.querySelectorAll('img');
                const lastImg = imgs[imgs.length - 1];
                if (!lastImg) return 'no_img';

                const headings = document.body.querySelectorAll('h2, h3');
                if (headings.length === 0) return 'no_headings';
                const h = headings[Math.min(idx, headings.length - 1)];

                // 이미지의 부모(wrapper) 가져오기
                let imgWrapper = lastImg;
                while (imgWrapper.parentNode && imgWrapper.parentNode !== document.body) {{
                    imgWrapper = imgWrapper.parentNode;
                }}

                // 소제목 다음으로 이동
                if (h.nextSibling) {{
                    h.parentNode.insertBefore(imgWrapper, h.nextSibling);
                }} else {{
                    h.parentNode.appendChild(imgWrapper);
                }}
                return 'moved_' + idx;
            }}""", heading_index)
            log(f"  이미지 이동: {moved}")
            return True
        else:
            log("  업로드 후 이미지 증가 없음 — JS 직접 삽입으로 폴백")
            return insert_image_via_js(frame, img_path, heading_index)
    except Exception as e:
        log(f"  업로드 오류: {e}, JS 직접 삽입으로 폴백")
        return insert_image_via_js(frame, img_path, heading_index)


def main():
    log("=== goodisak 게이밍노트북추천 이미지 삽입 워커 시작 ===")

    pw, browser = connect_cdp(on_log=log)
    log("CDP 연결 성공")

    # 임시저장 목록에서 게이밍노트북 글 찾기
    # goodisak.tistory.com/manage/posts 탭 사용 또는 새 탐색
    manage_page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            url = p.url
            if "goodisak.tistory.com/manage" in url or "isag27511.tistory.com/manage" in url:
                manage_page = p
                log(f"관리 탭 발견: {url[:80]}")
                break
        if manage_page:
            break

    if manage_page is None:
        manage_page = get_or_create_page(browser, navigate_to="https://goodisak.tistory.com/manage/posts")
        log("관리 탭 새로 생성")

    manage_page.bring_to_front()

    # 임시저장 목록 URL로 이동
    log("임시저장 목록으로 이동...")
    manage_page.goto("https://goodisak.tistory.com/manage/posts?state=temp", wait_until='domcontentloaded')
    manage_page.wait_for_timeout(3000)

    # 스크린샷 저장
    manage_page.screenshot(path="/tmp/goodisak_draft_list_worker.png")
    log("임시저장 목록 스크린샷: /tmp/goodisak_draft_list_worker.png")

    # '게이밍노트북' 포함 글 찾기
    found = manage_page.evaluate("""() => {
        const items = document.querySelectorAll('a, .post-item, .list-item, tr, li');
        for (const el of items) {
            const text = el.textContent || '';
            if (text.includes('게이밍노트북') || text.includes('게이밍 노트북')) {
                const link = el.tagName === 'A' ? el : el.querySelector('a');
                if (link) {
                    return {href: link.href, text: text.substring(0, 100).trim()};
                }
            }
        }
        return null;
    }""")
    log(f"게이밍노트북 글 검색 결과: {found}")

    if not found or not found.get('href'):
        # 전체 페이지 텍스트 일부 확인
        page_text = manage_page.evaluate("() => document.body.innerText.substring(0, 1000)")
        log(f"페이지 텍스트 일부: {page_text[:500]}")

        # 임시저장 탭 클릭 후 재시도
        log("임시저장 탭 직접 클릭 시도...")
        manage_page.evaluate("""() => {
            const els = document.querySelectorAll('a, button, li, span');
            for (const el of els) {
                if (el.textContent.trim() === '임시저장') { el.click(); return; }
            }
        }""")
        manage_page.wait_for_timeout(2000)

        found = manage_page.evaluate("""() => {
            const items = document.querySelectorAll('a, .post-item, .list-item, tr, li');
            for (const el of items) {
                const text = el.textContent || '';
                if (text.includes('게이밍노트북') || text.includes('게이밍 노트북')) {
                    const link = el.tagName === 'A' ? el : el.querySelector('a');
                    if (link) {
                        return {href: link.href, text: text.substring(0, 100).trim()};
                    }
                }
            }
            return null;
        }""")
        log(f"재시도 검색 결과: {found}")

    page = None
    if found and found.get('href'):
        manage_page.goto(found['href'], wait_until='domcontentloaded')
        manage_page.wait_for_timeout(4000)
        log(f"에디터 이동: {found['href']}")
        page = manage_page
    else:
        log("ERROR: 게이밍노트북추천 드래프트를 찾을 수 없습니다!")
        manage_page.screenshot(path="/tmp/goodisak_draft_notfound.png")
        pw.stop()
        sys.exit(1)

    log(f"현재 URL: {page.url}")

    # TinyMCE iframe 찾기
    log("TinyMCE iframe 찾는 중...")
    page.wait_for_timeout(2000)

    frame = None
    for sel in [
        "iframe#editor-tistory_ifr",
        "iframe.tox-edit-area__iframe",
        "iframe[id*='mce']",
        "iframe[id*='editor']",
    ]:
        iframe_el = page.query_selector(sel)
        if iframe_el:
            frame = iframe_el.content_frame()
            if frame:
                log(f"iframe 발견: {sel}")
                break

    if not frame:
        # 모든 iframe 나열
        iframes = page.query_selector_all("iframe")
        log(f"전체 iframe 수: {len(iframes)}")
        for i, ifr in enumerate(iframes):
            id_attr = ifr.get_attribute("id") or ""
            src = ifr.get_attribute("src") or ""
            log(f"  iframe[{i}]: id={id_attr}, src={src[:60]}")
        if iframes:
            frame = iframes[0].content_frame()
            if frame:
                log("첫 번째 iframe 사용")

    if not frame:
        log("ERROR: 에디터 iframe 없음!")
        page.screenshot(path="/tmp/goodisak_no_iframe.png")
        pw.stop()
        sys.exit(1)

    # ── Step 2: 소제목 파악 ──────────────────────────
    log("소제목(H2/H3) 파악 중...")
    headings = frame.evaluate("""() => {
        const results = [];
        const els = document.body.querySelectorAll('h2, h3');
        els.forEach((el, idx) => {
            results.push({
                tag: el.tagName,
                text: el.innerText.trim().substring(0, 100),
                index: idx
            });
        });
        return results;
    }""")
    log(f"소제목 {len(headings)}개 발견:")
    for h in headings:
        log(f"  [{h['index']}] {h['tag']}: {h['text']}")

    if not headings:
        log("소제목이 없습니다. 에디터 내용 일부 확인:")
        body_preview = frame.evaluate("() => document.body.innerText.substring(0, 500)")
        log(f"내용 미리보기: {body_preview}")
        pw.stop()
        sys.exit(1)

    # ── Step 3: 기존 이미지 삭제 ──────────────────────────
    log("기존 이미지 삭제 중...")
    img_count_before = frame.evaluate("() => document.body.querySelectorAll('img').length")
    log(f"삭제 전 이미지 수: {img_count_before}")

    if img_count_before > 0:
        removed = frame.evaluate("""() => {
            const imgs = document.body.querySelectorAll('img');
            let count = 0;
            imgs.forEach(img => {
                // img 부모가 단독 p/div이면 부모째 삭제
                const parent = img.parentElement;
                if (parent && parent !== document.body && parent.children.length === 1) {
                    parent.remove();
                } else {
                    img.remove();
                }
                count++;
            });
            return count;
        }""")
        log(f"이미지 {removed}개 삭제 완료")
        page.wait_for_timeout(500)

    img_count_after_del = frame.evaluate("() => document.body.querySelectorAll('img').length")
    log(f"삭제 후 이미지 수: {img_count_after_del}")

    # ── Step 4: Bing 이미지 생성 ──────────────────────────
    log(f"Bing 이미지 생성 시작 (총 {len(headings)}개)...")

    image_infos = []
    for i, h in enumerate(headings):
        keyword = h['text'].replace(' ', '_')[:30]
        prompt = f"gaming laptop {h['text']} high performance product photo, sleek design, dark background"
        image_infos.append({
            'index': i,
            'prompt': prompt,
            'filename': f"gaming_{i}_{keyword}.jpg"
        })

    log("Bing Image Creator 호출 중 (pw.stop() 후 새 연결)...")

    # generate_images_bing은 자체적으로 connect_cdp + pw.stop() 함
    # 현재 pw 연결을 먼저 닫고 bing 생성 후 재연결
    pw.stop()
    log("기존 CDP 연결 해제 (Bing 생성을 위해)")

    bing_results = generate_images_bing(
        image_infos,
        skip_webp=True,  # .jpg 저장
        on_log=log,
        output_dir=OUTPUT_DIR
    )
    log(f"Bing 생성 결과: {len(bing_results)}개")
    for idx, path in bing_results.items():
        log(f"  [{idx}] {path}")

    if not bing_results:
        log("ERROR: Bing 이미지 생성 실패!")
        sys.exit(1)

    # ── Step 5: 에디터 재연결 후 이미지 삽입 ──────────────────────────
    log("CDP 재연결 중...")
    pw2, browser2 = connect_cdp(on_log=log)
    log("CDP 재연결 성공")

    # 에디터 탭 찾기
    page2 = None
    for ctx in browser2.contexts:
        for p in ctx.pages:
            url = p.url
            if "goodisak.tistory.com/manage" in url or "isag27511.tistory.com/manage" in url:
                page2 = p
                log(f"에디터 탭 재발견: {url[:80]}")
                break
        if page2:
            break

    if page2 is None:
        log("ERROR: 재연결 후 에디터 탭 없음!")
        pw2.stop()
        sys.exit(1)

    page2.bring_to_front()
    page2.wait_for_timeout(1000)

    # iframe 재탐색
    frame2 = None
    for sel in [
        "iframe#editor-tistory_ifr",
        "iframe.tox-edit-area__iframe",
        "iframe[id*='mce']",
        "iframe[id*='editor']",
    ]:
        iframe_el2 = page2.query_selector(sel)
        if iframe_el2:
            frame2 = iframe_el2.content_frame()
            if frame2:
                log(f"iframe 재발견: {sel}")
                break

    if not frame2:
        iframes2 = page2.query_selector_all("iframe")
        if iframes2:
            frame2 = iframes2[0].content_frame()
            if frame2:
                log("첫 번째 iframe 재사용")

    if not frame2:
        log("ERROR: 재연결 후 iframe 없음!")
        pw2.stop()
        sys.exit(1)

    # 이미지 삽입 (소제목 순서대로)
    log("이미지 삽입 시작...")
    inserted_count = 0
    for i, h in enumerate(headings):
        img_path = bing_results.get(i)
        if not img_path:
            log(f"  [소제목 {i}] 이미지 없음 — 스킵")
            continue

        log(f"  [소제목 {i}] '{h['text'][:40]}' 이미지 삽입 중...")
        ok = insert_image_via_js(frame2, img_path, i)
        if ok:
            inserted_count += 1
            log(f"  [소제목 {i}] 삽입 성공")
        else:
            # 재시도 1회
            log(f"  [소제목 {i}] 삽입 실패, 재시도...")
            page2.wait_for_timeout(1000)
            ok2 = insert_image_via_js(frame2, img_path, i)
            if ok2:
                inserted_count += 1
                log(f"  [소제목 {i}] 재시도 성공")
            else:
                log(f"  [소제목 {i}] 재시도도 실패 — 스킵")

        page2.wait_for_timeout(500)

    log(f"이미지 삽입 완료: {inserted_count}/{len(headings)}개")

    # 최종 이미지 수 확인
    final_img_count = frame2.evaluate("() => document.body.querySelectorAll('img').length")
    log(f"최종 이미지 수: {final_img_count}")

    # 스크린샷 저장
    page2.screenshot(path="/tmp/goodisak_gaming_after_insert.png")
    log("삽입 후 스크린샷: /tmp/goodisak_gaming_after_insert.png")

    # ── Step 6: 임시저장 ──────────────────────────
    log("임시저장 버튼 클릭 중...")
    save_btn = None
    for sel in [
        "button:has-text('임시저장')",
        "button[data-role='save']",
        ".btn_save",
        "button.save",
    ]:
        save_btn = page2.query_selector(sel)
        if save_btn:
            log(f"임시저장 버튼 발견: {sel}")
            break

    if not save_btn:
        # JS로 찾기
        saved = page2.evaluate("""() => {
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
            log(f"JS 임시저장 클릭: {saved}")
        else:
            log("임시저장 버튼 없음 — 키보드 단축키 시도 (Ctrl+S)")
            page2.keyboard.press("Control+s")
    else:
        save_btn.click()
        log("임시저장 클릭 완료")

    page2.wait_for_timeout(3000)
    page2.screenshot(path="/tmp/goodisak_gaming_final.png")
    log("최종 스크린샷: /tmp/goodisak_gaming_final.png")

    # ── 완료 보고 ──────────────────────────
    log("=== 작업 완료 ===")
    log(f"소제목 목록: {[h['text'] for h in headings]}")
    log(f"생성된 이미지: {list(bing_results.values())}")
    log(f"삽입 완료: {inserted_count}/{len(headings)}개")
    log(f"최종 에디터 이미지 수: {final_img_count}")

    # 결과 JSON 저장
    result = {
        "headings": headings,
        "images_generated": list(bing_results.values()),
        "inserted_count": inserted_count,
        "total_headings": len(headings),
        "final_image_count": final_img_count,
    }
    with open("/tmp/goodisak_gaming_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log("결과 저장: /tmp/goodisak_gaming_result.json")

    pw2.stop()
    log("CDP 연결 종료")


if __name__ == "__main__":
    main()
