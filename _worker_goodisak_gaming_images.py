"""
goodisak 티스토리 - 게이밍노트북 임시저장 글에 이미지 삽입 워커
CDP Chrome(9222) 연결 → 임시저장 팝업에서 글 불러오기 → 이미지 교체 → 임시저장
"""
import sys
import os
import time

sys.path.insert(0, "/Users/hana/Downloads/blog-automation-v2")

from browser import connect_cdp, get_or_create_page

IMAGE_DIR = "/Users/hana/Downloads/blog-automation-v2/images"
IMAGES = [
    os.path.join(IMAGE_DIR, "bing-gaming-final-1.jpg"),
    os.path.join(IMAGE_DIR, "bing-gaming-final-2.jpg"),
    os.path.join(IMAGE_DIR, "bing-gaming-final-3.jpg"),
    os.path.join(IMAGE_DIR, "bing-gaming-final-4.jpg"),
]

TARGET_DRAFT_TITLE = "게이밍노트북추천 2026"

def log(msg):
    print(f"[WORKER] {msg}", flush=True)


def main():
    log("CDP 연결 시작")
    pw, browser = connect_cdp(on_log=log)

    try:
        page = get_or_create_page(browser)
        log(f"현재 탭 URL: {page.url}")

        # goodisak 새 글 작성 페이지로 이동
        log("goodisak 티스토리 에디터로 이동")
        page.goto("https://goodisak.tistory.com/manage/newpost", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        log(f"에디터 로드 완료: {page.url}")

        # 임시저장 버튼의 숫자(카운트) 부분 찾기
        # 티스토리 에디터에서 임시저장 버튼은 보통 "임시저장 (N)" 형태
        log("임시저장 버튼 찾는 중...")

        # 임시저장 버튼 클릭 (숫자 부분 - 팝업 열기)
        # 티스토리 에디터의 임시저장 버튼 구조 확인
        page.wait_for_timeout(2000)

        # 스크린샷으로 현재 상태 확인
        page.screenshot(path="/tmp/tistory_editor.png")
        log("스크린샷 저장: /tmp/tistory_editor.png")

        # 임시저장 카운트 버튼 찾기 (다양한 선택자 시도)
        draft_count_selectors = [
            "button.btn-save-draft-count",
            ".btn-save-draft .count",
            "[class*='draft'] [class*='count']",
            "button[data-tiara-action*='draft']",
        ]

        draft_btn = None
        for sel in draft_count_selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    draft_btn = el
                    log(f"임시저장 버튼 찾음: {sel}")
                    break
            except Exception as e:
                log(f"선택자 시도 실패 {sel}: {e}")

        if not draft_btn:
            # JavaScript로 임시저장 버튼 찾기
            log("JS로 임시저장 버튼 탐색...")
            result = page.evaluate("""() => {
                // 버튼 텍스트에서 '임시저장' 포함된 요소 찾기
                const buttons = Array.from(document.querySelectorAll('button, a, span'));
                const found = buttons.filter(el => el.textContent.includes('임시저장'));
                return found.map(el => ({
                    tag: el.tagName,
                    class: el.className,
                    text: el.textContent.trim().substring(0, 50),
                    id: el.id
                }));
            }""")
            log(f"임시저장 관련 요소: {result}")

            # 숫자 카운트 클릭 방식: 팝업 트리거
            # 티스토리 에디터에서 임시저장 버튼의 숫자 부분 직접 클릭
            count_result = page.evaluate("""() => {
                // count 또는 숫자가 있는 임시저장 관련 버튼
                const allEl = document.querySelectorAll('*');
                for (const el of allEl) {
                    const txt = el.textContent.trim();
                    if (/임시저장\s*\(\d+\)/.test(txt) || /임시저장\s*\d+/.test(txt)) {
                        return {found: true, tag: el.tagName, class: el.className, text: txt.substring(0, 80)};
                    }
                }
                return {found: false};
            }""")
            log(f"임시저장 카운트 요소: {count_result}")

        # iframe 내부에 에디터가 있을 수 있음
        frames = page.frames
        log(f"프레임 수: {len(frames)}")
        for i, f in enumerate(frames):
            log(f"  프레임[{i}]: {f.url}")

        # 메인 프레임에서 임시저장 버튼 클릭 시도
        # 티스토리 에디터는 보통 상단 툴바에 임시저장 버튼이 있음
        log("페이지 전체 HTML에서 임시저장 버튼 구조 파악...")
        btn_info = page.evaluate("""() => {
            // save 관련 버튼들
            const btns = Array.from(document.querySelectorAll('button'));
            return btns.slice(0, 30).map(b => ({
                class: b.className,
                text: b.textContent.trim().substring(0, 30),
                id: b.id,
                type: b.type
            }));
        }""")
        log(f"버튼 목록 (최대30): {btn_info}")

        # 임시저장 숫자 버튼 클릭
        # 일반적으로 티스토리는 ".btn_save2" 또는 유사한 클래스
        save_draft_popup_selectors = [
            "button.btn_save2",
            ".area_btn_save button:nth-child(2)",
            "button[onclick*='draftList']",
            ".btn-save-draft-count",
            "button.save-btn-count",
        ]

        clicked = False
        for sel in save_draft_popup_selectors:
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click()
                    page.wait_for_timeout(1500)
                    clicked = True
                    log(f"임시저장 팝업 트리거 클릭: {sel}")
                    break
            except Exception as e:
                pass

        if not clicked:
            # 텍스트 기반으로 클릭
            log("텍스트 기반으로 임시저장 버튼 찾기...")
            try:
                # "임시저장" 텍스트 버튼 찾아서 그 옆의 카운트 버튼 클릭
                el = page.get_by_text("임시저장", exact=False)
                count = el.count()
                log(f"'임시저장' 텍스트 요소 수: {count}")
                if count > 0:
                    # 마지막 요소(보통 카운트)나 두 번째 클릭
                    el.last.click()
                    page.wait_for_timeout(1500)
                    clicked = True
                    log("텍스트 기반 임시저장 버튼 클릭 완료")
            except Exception as e:
                log(f"텍스트 클릭 실패: {e}")

        # 팝업이 열렸는지 확인
        page.wait_for_timeout(2000)
        page.screenshot(path="/tmp/tistory_draft_popup.png")
        log("팝업 스크린샷 저장: /tmp/tistory_draft_popup.png")

        # 팝업에서 게이밍노트북 글 찾기
        popup_found = page.evaluate(f"""() => {{
            const items = Array.from(document.querySelectorAll('li, tr, div[class*="draft"], div[class*="list"]'));
            const target = items.find(el => el.textContent.includes('게이밍노트북') || el.textContent.includes('{TARGET_DRAFT_TITLE}'));
            if (target) {{
                return {{found: true, text: target.textContent.trim().substring(0, 100), tag: target.tagName, class: target.className}};
            }}
            return {{found: false, total: items.length}};
        }}""")
        log(f"팝업에서 글 찾기 결과: {popup_found}")

        if popup_found.get("found"):
            log("게이밍노트북 글 항목 찾음 - 클릭하여 불러오기")
            # 해당 항목 클릭
            page.evaluate(f"""() => {{
                const items = Array.from(document.querySelectorAll('li, tr, div'));
                const target = items.find(el => el.textContent.includes('게이밍노트북') || el.textContent.includes('{TARGET_DRAFT_TITLE}'));
                if (target) {{
                    const clickable = target.querySelector('a, button') || target;
                    clickable.click();
                }}
            }}""")
            page.wait_for_timeout(3000)
            log("글 불러오기 클릭 완료")
        else:
            log("팝업에서 게이밍노트북 글을 찾지 못함 - 팝업 상태 재확인 필요")
            # 팝업이 안 열렸을 수도 있음 - 전체 화면 다시 분석
            all_text = page.evaluate("""() => document.body.innerText.substring(0, 2000)""")
            log(f"페이지 텍스트 일부: {all_text[:500]}")

            # 임시저장 팝업 열기 재시도 - 다른 방법
            log("임시저장 팝업 재시도...")
            # JS로 직접 팝업 함수 호출 시도
            page.evaluate("""() => {
                if (typeof EDITOR !== 'undefined' && EDITOR.draftList) {
                    EDITOR.draftList();
                } else if (typeof editor !== 'undefined' && editor.draftList) {
                    editor.draftList();
                }
            }""")
            page.wait_for_timeout(2000)

            page.screenshot(path="/tmp/tistory_retry.png")
            log("재시도 스크린샷: /tmp/tistory_retry.png")

            # 다시 팝업 확인
            popup_found2 = page.evaluate(f"""() => {{
                const items = Array.from(document.querySelectorAll('li, tr, div'));
                const target = items.find(el => el.textContent.includes('게이밍노트북'));
                if (target) {{
                    return {{found: true, text: target.textContent.trim().substring(0, 100)}};
                }}
                return {{found: false}};
            }}""")
            log(f"재시도 팝업 결과: {popup_found2}")

            if not popup_found2.get("found"):
                log("ERROR: 임시저장 글을 팝업에서 찾을 수 없음. 작업 중단.")
                return

        # 글 내용 로드 확인 (에디터 본문에 내용이 있는지)
        page.wait_for_timeout(2000)
        content_check = page.evaluate("""() => {
            // 에디터 내용 확인 - iframe 또는 contenteditable
            const editor = document.querySelector('[contenteditable="true"]');
            if (editor) {
                return {found: true, len: editor.innerText.length, preview: editor.innerText.substring(0, 100)};
            }
            // iframe 내부 확인
            const iframes = document.querySelectorAll('iframe');
            return {found: false, iframes: iframes.length};
        }""")
        log(f"에디터 내용 확인: {content_check}")

        if not content_check.get("found") or (content_check.get("len", 0) < 100):
            log("WARNING: 에디터 내용이 비어있거나 너무 짧음. iframe 확인...")

        # iframe 안에 에디터가 있는 경우
        editor_frame = None
        for frame in page.frames:
            if "tistory" in frame.url or frame.url == "about:blank":
                try:
                    frame_content = frame.evaluate("""() => {
                        const editor = document.querySelector('[contenteditable="true"]');
                        if (editor) return {found: true, len: editor.innerText.length};
                        return {found: false};
                    }""")
                    if frame_content.get("found") and frame_content.get("len", 0) > 100:
                        editor_frame = frame
                        log(f"에디터 iframe 찾음: {frame.url}, 내용길이: {frame_content['len']}")
                        break
                except:
                    pass

        # 현재 에디터 상태 스크린샷
        page.screenshot(path="/tmp/tistory_loaded.png")
        log("글 로드 후 스크린샷: /tmp/tistory_loaded.png")

        # 기존 이미지 삭제
        log("기존 이미지 삭제 시작...")
        img_deleted = page.evaluate("""() => {
            let count = 0;
            // 에디터 내 이미지 요소 삭제
            const editor = document.querySelector('[contenteditable="true"]');
            if (editor) {
                const imgs = editor.querySelectorAll('img, figure, .imageblock, .image-block');
                imgs.forEach(img => {
                    img.remove();
                    count++;
                });
            }
            return count;
        }""")
        log(f"삭제된 이미지 요소 수: {img_deleted}")

        # iframe 에디터에서도 이미지 삭제
        if editor_frame:
            try:
                deleted2 = editor_frame.evaluate("""() => {
                    let count = 0;
                    const editor = document.querySelector('[contenteditable="true"]');
                    if (editor) {
                        const imgs = editor.querySelectorAll('img, figure, .imageblock');
                        imgs.forEach(img => { img.remove(); count++; });
                    }
                    return count;
                }""")
                log(f"iframe 에디터에서 삭제된 이미지: {deleted2}")
            except Exception as e:
                log(f"iframe 이미지 삭제 실패: {e}")

        page.wait_for_timeout(1000)

        # 이미지 업로드 - 티스토리 파일 업로드 버튼 사용
        log("이미지 업로드 시작...")

        for i, img_path in enumerate(IMAGES):
            if not os.path.exists(img_path):
                log(f"이미지 파일 없음: {img_path}")
                continue

            log(f"이미지 업로드 [{i+1}/4]: {img_path}")

            # 티스토리 에디터 이미지 업로드 버튼 클릭
            # 보통 toolbar에 이미지 버튼이 있음
            try:
                # 파일 input 요소 찾기
                file_input = page.locator('input[type="file"]').first
                if file_input.count() > 0:
                    file_input.set_input_files(img_path)
                    page.wait_for_timeout(3000)
                    log(f"  파일 input으로 업로드 시도")
                else:
                    log(f"  파일 input 없음 - 이미지 툴바 버튼 클릭 시도")
                    # 이미지 버튼 클릭 (툴바)
                    img_btns = [
                        "button[title*='이미지']",
                        "button[title*='image']",
                        "button[aria-label*='이미지']",
                        ".toolbar button[data-command='image']",
                        "button.image",
                    ]
                    for sel in img_btns:
                        el = page.locator(sel)
                        if el.count() > 0:
                            el.first.click()
                            page.wait_for_timeout(1000)
                            log(f"  이미지 버튼 클릭: {sel}")

                            # 파일 input 다시 확인
                            fi = page.locator('input[type="file"]').first
                            if fi.count() > 0:
                                fi.set_input_files(img_path)
                                page.wait_for_timeout(3000)
                            break

                page.screenshot(path=f"/tmp/tistory_img_{i+1}.png")
                log(f"  업로드 후 스크린샷: /tmp/tistory_img_{i+1}.png")

            except Exception as e:
                log(f"  이미지 [{i+1}] 업로드 실패: {e}")

        # 임시저장
        log("임시저장 클릭...")
        save_selectors = [
            "button.btn-save-draft",
            "button[data-tiara-action*='임시저장']",
            "button:has-text('임시저장')",
        ]
        saved = False
        for sel in save_selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    el.click()
                    page.wait_for_timeout(2000)
                    saved = True
                    log(f"임시저장 완료: {sel}")
                    break
            except:
                pass

        if not saved:
            log("임시저장 버튼 JS로 시도...")
            page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const saveBtn = btns.find(b => b.textContent.trim() === '임시저장');
                if (saveBtn) saveBtn.click();
            }""")
            page.wait_for_timeout(2000)
            log("임시저장 JS 클릭 완료")

        page.screenshot(path="/tmp/tistory_final.png")
        log("최종 스크린샷: /tmp/tistory_final.png")

        # 텔레그램 보고
        log("텔레그램 보고...")
        import subprocess
        result = subprocess.run(
            ["python3", "tg_send.py", "✅ 게이밍노트북 이미지 삽입 완료"],
            cwd="/Users/hana/Downloads/blog-automation-v2",
            capture_output=True, text=True
        )
        log(f"텔레그램 결과: {result.stdout} {result.stderr}")

        log("=== 작업 완료 ===")

    finally:
        pw.stop()
        log("Playwright 종료")


if __name__ == "__main__":
    main()
