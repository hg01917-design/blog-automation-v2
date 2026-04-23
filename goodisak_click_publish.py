"""
goodisak Tistory 발행 버튼 직접 클릭 (ElementHandle 사용)
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
                if "goodisak.tistory.com/manage/newpost" in p.url:
                    page = p
                    break
            if page:
                break

        if page is None:
            log("ERROR: 탭 없음")
            sys.exit(1)

        page.bring_to_front()
        page.wait_for_timeout(1000)

        # 발행 패널 열려있는지 확인
        panel = page.query_selector(".ReactModal__Content.editor_layer")
        if panel:
            log("발행 패널이 이미 열려있음")
        else:
            log("발행 패널 없음, 완료 버튼 클릭...")
            # 완료 버튼 클릭
            buttons = page.query_selector_all("button")
            for btn in buttons:
                if btn.inner_text().strip() == "완료":
                    btn.click(force=True)
                    page.wait_for_timeout(2000)
                    log("완료 버튼 클릭됨")
                    break

        # 발행 패널 재확인
        page.wait_for_timeout(1000)
        panel = page.query_selector(".ReactModal__Content.editor_layer")
        if not panel:
            log("ERROR: 발행 패널 열기 실패")
            sys.exit(1)

        log("발행 패널 열림 확인")

        # 댓글 비허용 설정
        comment_btn = panel.query_selector("button.mce-btn-type1.select_btn")
        if comment_btn:
            comment_text = comment_btn.inner_text().strip()
            log(f"댓글 버튼 텍스트: {comment_text}")

            if "비허용" not in comment_text:
                # 댓글 드롭다운 클릭
                comment_btn.click(force=True)
                page.wait_for_timeout(1000)

                # '댓글 비허용' 항목 클릭
                disallow_items = page.query_selector_all(".mce-floatpanel .mce-text, .mce-menu .mce-text")
                for item in disallow_items:
                    if "비허용" in item.inner_text():
                        item.click(force=True)
                        log("댓글 비허용 선택됨")
                        page.wait_for_timeout(500)
                        break
                else:
                    # JavaScript로 클릭
                    result = page.evaluate("""
                    () => {
                        const spans = document.querySelectorAll('.mce-floatpanel span, .mce-menu span');
                        for (const span of spans) {
                            if (span.textContent.trim() === '댓글 비허용') {
                                span.click();
                                return '클릭됨';
                            }
                        }
                        return '없음';
                    }
                    """)
                    log(f"JS 댓글 비허용 클릭: {result}")
                    page.wait_for_timeout(500)
        else:
            # 여러 select_btn 중 첫 번째 (댓글 관련)
            select_btns = panel.query_selector_all("button.mce-btn-type1")
            log(f"select_btn 수: {len(select_btns)}")
            for btn in select_btns:
                text = btn.inner_text().strip()
                log(f"  버튼: {text}")

        # 댓글 상태 재확인
        panel = page.query_selector(".ReactModal__Content.editor_layer")
        if panel:
            comment_status = page.evaluate("""
            () => {
                const panel = document.querySelector('.ReactModal__Content.editor_layer');
                const btns = panel ? panel.querySelectorAll('button') : [];
                const result = [];
                btns.forEach(btn => {
                    const text = btn.textContent.trim();
                    if (text.length > 0 && text.length < 50) result.push(text);
                });
                return result;
            }
            """)
            log(f"패널 버튼들: {comment_status}")

        # 공개 발행 버튼 직접 클릭 (ElementHandle)
        log("공개 발행 버튼 클릭...")

        publish_btn = page.query_selector("#publish-btn")
        if not publish_btn:
            publish_btn = page.query_selector("button.btn-default[type='submit']")
        if not publish_btn:
            # panel에서 찾기
            panel = page.query_selector(".ReactModal__Content.editor_layer")
            if panel:
                publish_btn = panel.query_selector("button.btn-default")

        if publish_btn:
            btn_text = publish_btn.inner_text().strip()
            log(f"발행 버튼 발견: '{btn_text}'")

            # 스크린샷 (클릭 전)
            page.screenshot(path="/tmp/goodisak_before_publish.png")

            # ElementHandle.click() 사용
            publish_btn.click(force=True)
            log("발행 버튼 클릭 완료")
        else:
            log("ERROR: 발행 버튼을 찾을 수 없습니다!")
            # 모든 버튼 나열
            all_btns = page.query_selector_all("button")
            for btn in all_btns:
                text = btn.inner_text().strip()
                if text and len(text) < 30:
                    rect = btn.bounding_box()
                    if rect and rect['width'] > 0:
                        log(f"  버튼: '{text}' at ({rect['x']:.0f}, {rect['y']:.0f})")
            sys.exit(1)

        # 발행 완료 대기 (최대 10초)
        log("발행 처리 대기 중...")
        for i in range(10):
            page.wait_for_timeout(1000)
            current_url = page.url
            if "/manage/newpost" not in current_url:
                log(f"✅ URL 변경됨: {current_url}")
                break
            log(f"  대기 {i+1}초... URL: {current_url}")

        # 최종 상태 확인
        current_url = page.url
        page.screenshot(path="/tmp/goodisak_final_state.png")
        log(f"최종 URL: {current_url}")

        # 발행된 URL 또는 에러 메시지 확인
        page_text = page.evaluate("() => document.body.innerText.substring(0, 300)")
        log(f"현재 페이지 내용: {page_text[:200]}")

        return current_url

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        pw.stop()

if __name__ == "__main__":
    url = main()
    print(f"발행 URL: {url}")
