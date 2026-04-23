"""
goodisak Tistory 최종 발행 - 이미지가 CDN에 업로드됨, 발행만 진행
"""
import sys
import time
from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9222"

def log(msg):
    print(f"[publish] {msg}", flush=True)

def main():
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        log("CDP 연결 성공")

        page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "goodisak.tistory.com" in p.url:
                    page = p
                    break
            if page:
                break

        if page is None:
            log("ERROR: 탭 없음")
            sys.exit(1)

        log(f"현재 URL: {page.url}")
        page.bring_to_front()
        page.wait_for_timeout(1000)

        # 이미지 수 최종 확인
        iframe_el = page.query_selector("iframe#editor-tistory_ifr")
        if iframe_el:
            frame = iframe_el.content_frame()
            img_count = frame.evaluate("() => document.body.querySelectorAll('img').length")
            text_len = frame.evaluate("() => document.body.innerText.length")
            log(f"이미지 수: {img_count}, 글자 수: {text_len}")
        else:
            log("WARNING: iframe 없음")

        # 완료 버튼 클릭 (발행 패널 열기)
        log("완료 버튼 클릭...")
        complete_btn = None
        buttons = page.query_selector_all("button")
        for btn in buttons:
            text = btn.inner_text().strip()
            if text == "완료":
                complete_btn = btn
                break

        if complete_btn:
            complete_btn.click(force=True)
        else:
            # locator 시도
            page.locator("button", has_text="완료").first.click(force=True)

        page.wait_for_timeout(2000)
        page.screenshot(path="/tmp/goodisak_panel2.png")

        # 발행 패널 확인
        panel = page.query_selector(".ReactModal__Content.editor_layer")
        if not panel:
            log("ERROR: 발행 패널 열기 실패")
            # 다른 방법 시도
            page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.trim() === '완료') {
                        btn.click();
                        return '클릭';
                    }
                }
                return '없음';
            }
            """)
            page.wait_for_timeout(2000)
            panel = page.query_selector(".ReactModal__Content.editor_layer")

        if not panel:
            log("ERROR: 발행 패널을 열 수 없습니다")
            sys.exit(1)

        log("발행 패널 열림")

        # 댓글 비허용 설정
        log("댓글 설정 확인...")
        comment_text = page.evaluate("""
        () => {
            const panel = document.querySelector('.ReactModal__Content.editor_layer');
            if (!panel) return '';
            const btns = panel.querySelectorAll('button.mce-btn-type1, button.select_btn');
            for (const btn of btns) {
                const text = btn.textContent.trim();
                if (text.includes('댓글')) return text;
            }
            return '';
        }
        """)
        log(f"댓글 현재 설정: '{comment_text}'")

        if "비허용" not in comment_text:
            log("댓글 비허용으로 변경 중...")
            # 댓글 버튼 클릭 (드롭다운 열기)
            page.evaluate("""
            () => {
                const panel = document.querySelector('.ReactModal__Content.editor_layer');
                const btns = panel.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.includes('댓글')) {
                        btn.click();
                        return '클릭';
                    }
                }
            }
            """)
            page.wait_for_timeout(800)

            # 비허용 항목 클릭
            result = page.evaluate("""
            () => {
                // mce-floatpanel 내의 '댓글 비허용' 항목
                const panels = document.querySelectorAll('.mce-floatpanel, .mce-menu');
                for (const p of panels) {
                    const items = p.querySelectorAll('.mce-text, span, div');
                    for (const item of items) {
                        if (item.textContent.trim() === '댓글 비허용') {
                            item.click();
                            return '비허용 클릭됨';
                        }
                    }
                    // li 요소로도 시도
                    const lis = p.querySelectorAll('li');
                    for (const li of lis) {
                        if (li.textContent.includes('비허용')) {
                            li.click();
                            return 'li 비허용 클릭됨';
                        }
                    }
                }
                return '비허용 항목 없음';
            }
            """)
            log(f"비허용 선택: {result}")
            page.wait_for_timeout(500)

        # 발행 버튼 클릭 - #publish-btn 찾기
        log("'공개 발행' 버튼 찾기...")

        publish_btn = page.query_selector("#publish-btn")
        if publish_btn:
            log(f"#publish-btn 발견: '{publish_btn.inner_text().strip()}'")
        else:
            # 발행 패널 내 버튼 탐색
            panel = page.query_selector(".ReactModal__Content.editor_layer")
            if panel:
                btns = panel.query_selector_all("button")
                for btn in btns:
                    text = btn.inner_text().strip()
                    log(f"  패널 버튼: '{text}'")
                    if "발행" in text and "취소" not in text and "임시" not in text:
                        publish_btn = btn
                        break

        if publish_btn:
            btn_text = publish_btn.inner_text().strip()
            log(f"발행 버튼 클릭: '{btn_text}'")
            publish_btn.click(force=True)

            # 발행 완료 대기
            log("발행 처리 대기 중... (최대 30초)")
            for i in range(30):
                page.wait_for_timeout(1000)
                current_url = page.url

                # URL 변경 확인
                if "manage/newpost" not in current_url:
                    log(f"✅ URL 변경됨: {current_url}")
                    break

                # 에러 메시지 확인
                error_msg = page.evaluate("""
                () => {
                    const errEl = document.querySelector('.error, .alert, [class*="error"], [class*="alert"]');
                    return errEl ? errEl.textContent.trim().substring(0, 100) : '';
                }
                """)
                if error_msg:
                    log(f"ERROR 메시지: {error_msg}")
                    break

                if i % 5 == 0:
                    log(f"  {i+1}초 대기 중... URL: {current_url}")
        else:
            log("ERROR: 발행 버튼을 찾을 수 없음!")
            sys.exit(1)

        # 최종 결과
        final_url = page.url
        log(f"최종 URL: {final_url}")
        page.screenshot(path="/tmp/goodisak_final_published.png")

        if "manage/newpost" not in final_url:
            log(f"✅ 발행 완료! URL: {final_url}")
        else:
            # 발행 후 페이지로 이동하지 않은 경우 - 글 목록 확인
            log("URL이 변경되지 않음, 글 목록에서 확인...")
            page.goto("https://goodisak.tistory.com/manage/posts", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            posts_text = page.evaluate("() => document.body.innerText.substring(0, 1000)")
            log(f"글 목록: {posts_text[:500]}")
            page.screenshot(path="/tmp/goodisak_posts_after.png")

        return final_url

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        pw.stop()

if __name__ == "__main__":
    url = main()
    print(f"\n최종 발행 URL: {url}")
