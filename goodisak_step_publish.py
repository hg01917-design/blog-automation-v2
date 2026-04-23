"""
goodisak Tistory 단계별 발행 스크립트
- 완료 버튼 클릭
- 발행 패널에서 댓글 비허용 설정
- 공개 발행 버튼 클릭
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

        # 이미지 수 확인
        iframe_el = page.query_selector("iframe#editor-tistory_ifr")
        if iframe_el:
            frame = iframe_el.content_frame()
            img_count = frame.evaluate("() => document.body.querySelectorAll('img').length")
            text_len = frame.evaluate("() => document.body.innerText.length")
            log(f"이미지 수: {img_count}, 글자 수: {text_len}")

        # --- 완료 버튼 클릭 ---
        log("완료 버튼 직접 클릭...")

        # 완료 버튼을 Locator로 찾아 클릭
        complete_locator = page.locator("button", has_text="완료")
        count = complete_locator.count()
        log(f"완료 버튼 수: {count}")

        if count > 0:
            complete_locator.first.click(force=True)
            log("완료 버튼 클릭됨")
        else:
            # ElementHandle로 시도
            buttons = page.query_selector_all("button")
            for btn in buttons:
                if btn.inner_text().strip() == "완료":
                    btn.click(force=True)
                    log("완료 버튼 (ElementHandle) 클릭됨")
                    break

        # 발행 패널 대기
        log("발행 패널 대기 중...")
        try:
            page.wait_for_selector(".ReactModal__Content.editor_layer", timeout=5000)
            log("발행 패널 로드됨")
        except:
            log("발행 패널 타임아웃, 계속 진행...")

        page.wait_for_timeout(2000)
        page.screenshot(path="/tmp/goodisak_panel_after_click.png")

        # 패널 상태 확인
        panel = page.query_selector(".ReactModal__Content.editor_layer")
        log(f"패널 존재: {panel is not None}")

        if panel:
            # 패널 내 모든 버튼 나열
            btns = panel.query_selector_all("button")
            log(f"패널 내 버튼 수: {len(btns)}")
            for btn in btns:
                text = btn.inner_text().strip()
                bid = btn.get_attribute("id") or ""
                cls = btn.get_attribute("class") or ""
                rect = btn.bounding_box()
                visible = rect and rect['width'] > 0
                log(f"  버튼: '{text}' id={bid} class={cls[:60]} visible={visible}")

            # 댓글 비허용 설정
            log("댓글 비허용 설정...")
            # 댓글 허용 버튼 찾기
            for btn in btns:
                text = btn.inner_text().strip()
                if "댓글" in text:
                    log(f"댓글 버튼 찾음: '{text}'")
                    if "비허용" not in text:
                        btn.click(force=True)
                        page.wait_for_timeout(800)

                        # 드롭다운에서 비허용 선택
                        page.screenshot(path="/tmp/goodisak_comment_menu.png")

                        # 비허용 항목 찾기
                        result = page.evaluate("""
                        () => {
                            // mce-floatpanel 내 항목 찾기
                            const menuContainers = document.querySelectorAll('.mce-floatpanel, .mce-container.mce-panel');
                            for (const mc of menuContainers) {
                                if (mc.offsetParent !== null) {
                                    const texts = mc.querySelectorAll('.mce-text, span');
                                    for (const t of texts) {
                                        if (t.textContent.trim() === '댓글 비허용') {
                                            t.click();
                                            return '클릭: ' + t.textContent.trim();
                                        }
                                    }
                                    // menu-item 전체 클릭
                                    const items = mc.querySelectorAll('[class*="menu-item"], li, div[role="option"]');
                                    for (const item of items) {
                                        if (item.textContent.includes('비허용')) {
                                            item.click();
                                            return '메뉴아이템 클릭: ' + item.textContent.trim().substring(0, 30);
                                        }
                                    }
                                }
                            }
                            return '없음';
                        }
                        """)
                        log(f"비허용 선택 결과: {result}")
                        page.wait_for_timeout(500)
                    break

            # 발행 버튼 클릭
            log("공개 발행 버튼 클릭...")
            page.wait_for_timeout(500)

            # 패널 재탐색
            panel = page.query_selector(".ReactModal__Content.editor_layer")
            if panel:
                # #publish-btn 직접 찾기
                publish_btn = page.query_selector("#publish-btn")
                if publish_btn:
                    log(f"#publish-btn 텍스트: '{publish_btn.inner_text().strip()}'")
                    publish_btn.click(force=True)
                    log("발행 버튼 클릭됨")
                else:
                    # 패널에서 '발행' 포함 버튼 찾기
                    all_btns = panel.query_selector_all("button")
                    for btn in all_btns:
                        text = btn.inner_text().strip()
                        if "발행" in text and "취소" not in text:
                            log(f"발행 버튼 클릭: '{text}'")
                            btn.click(force=True)
                            break
                    else:
                        log("ERROR: 발행 버튼 없음")
                        # 전체 버튼 목록 출력
                        for btn in all_btns:
                            log(f"  패널 버튼: '{btn.inner_text().strip()}'")
            else:
                # 패널이 없는 경우, 전체 페이지에서 발행 버튼 찾기
                log("패널 없음, 전체 페이지에서 발행 버튼 찾기...")
                publish_btn = page.query_selector("#publish-btn")
                if publish_btn:
                    publish_btn.click(force=True)
                    log("발행 버튼 클릭됨")

        else:
            log("ERROR: 발행 패널이 없습니다")
            sys.exit(1)

        # 발행 완료 대기
        log("발행 완료 대기 중... (최대 30초)")
        for i in range(30):
            page.wait_for_timeout(1000)
            current_url = page.url
            if "manage/newpost" not in current_url:
                log(f"✅ URL 변경됨: {current_url}")
                break
            if i % 5 == 0 and i > 0:
                log(f"  {i+1}초 대기... URL: {current_url}")

        final_url = page.url
        page.screenshot(path="/tmp/goodisak_final_published.png")
        log(f"최종 URL: {final_url}")

        if "manage/newpost" not in final_url:
            log(f"✅ 발행 성공!")
        else:
            log("발행이 완료되지 않은 것 같습니다. 글 목록 확인...")
            page.goto("https://goodisak.tistory.com/manage/posts", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            page.screenshot(path="/tmp/goodisak_posts_final.png")
            posts = page.evaluate("() => document.body.innerText.substring(0, 800)")
            log(f"글 목록: {posts[:500]}")

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
