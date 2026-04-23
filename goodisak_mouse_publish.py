"""
goodisak Tistory 발행 - 마우스 좌표 클릭 방식
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

        # 완료 버튼 클릭
        log("완료 버튼 클릭...")
        btns = page.query_selector_all("button")
        for btn in btns:
            if btn.inner_text().strip() == "완료":
                rect = btn.bounding_box()
                log(f"완료 버튼 좌표: {rect}")
                # 마우스 클릭
                page.mouse.click(rect['x'] + rect['width']/2, rect['y'] + rect['height']/2)
                log("완료 버튼 마우스 클릭됨")
                break

        # 발행 패널 대기
        page.wait_for_timeout(2000)

        # 패널 확인
        panel = page.query_selector(".ReactModal__Content.editor_layer")
        if not panel:
            log("패널 없음, 재시도...")
            page.wait_for_timeout(2000)
            panel = page.query_selector(".ReactModal__Content.editor_layer")

        if not panel:
            log("ERROR: 발행 패널 없음")
            page.screenshot(path="/tmp/goodisak_no_panel.png")
            sys.exit(1)

        log("발행 패널 열림")
        page.screenshot(path="/tmp/goodisak_panel_open.png")

        # 패널 내 버튼들 위치 파악
        btns = panel.query_selector_all("button")
        btn_info = []
        for btn in btns:
            text = btn.inner_text().strip()
            bid = btn.get_attribute("id") or ""
            rect = btn.bounding_box()
            if rect:
                btn_info.append({
                    'text': text,
                    'id': bid,
                    'x': rect['x'],
                    'y': rect['y'],
                    'w': rect['width'],
                    'h': rect['height']
                })
                log(f"  버튼: '{text}' id={bid} at ({rect['x']:.0f}, {rect['y']:.0f})")

        # 댓글 허용 버튼 찾아서 드롭다운 열기
        comment_btn_info = None
        for b in btn_info:
            if "댓글" in b['text']:
                comment_btn_info = b
                break

        if comment_btn_info:
            log(f"댓글 버튼 마우스 클릭: ({comment_btn_info['x']:.0f}, {comment_btn_info['y']:.0f})")
            cx = comment_btn_info['x'] + comment_btn_info['w'] / 2
            cy = comment_btn_info['y'] + comment_btn_info['h'] / 2
            page.mouse.click(cx, cy)
            page.wait_for_timeout(1000)
            page.screenshot(path="/tmp/goodisak_comment_dropdown2.png")

            # 드롭다운 메뉴 확인
            menu = page.query_selector(".mce-floatpanel, .mce-menu")
            if menu:
                log("드롭다운 메뉴 열림")
                menu_items = menu.query_selector_all(".mce-text, li, div")
                for item in menu_items:
                    text = item.inner_text().strip()
                    if text:
                        rect = item.bounding_box()
                        if rect and rect['width'] > 0:
                            log(f"  메뉴 항목: '{text}' at ({rect['x']:.0f}, {rect['y']:.0f})")
                            if "비허용" in text:
                                log(f"비허용 마우스 클릭: ({rect['x']:.0f}, {rect['y']:.0f})")
                                page.mouse.click(rect['x'] + rect['width']/2, rect['y'] + rect['height']/2)
                                page.wait_for_timeout(500)
                                break
            else:
                log("드롭다운 메뉴 없음, 좌표 기반 클릭 시도...")
                # mce-floatpanel이 있는지 전체 페이지에서 찾기
                all_panels = page.query_selector_all("[class*='floatpanel'], [class*='mce-menu']")
                log(f"floatpanel 수: {len(all_panels)}")
                for ap in all_panels:
                    text = ap.inner_text().strip()
                    if text:
                        log(f"  panel text: {text[:100]}")

                # 드롭다운 항목을 화면에서 찾기
                visible_items = page.evaluate("""
                () => {
                    const items = document.querySelectorAll('div, li, span');
                    const results = [];
                    for (const item of items) {
                        const text = item.textContent.trim();
                        if (text === '댓글 비허용' || text === '댓글 허용') {
                            const rect = item.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                results.push({
                                    text: text,
                                    x: rect.x,
                                    y: rect.y,
                                    w: rect.width,
                                    h: rect.height
                                });
                            }
                        }
                    }
                    return results;
                }
                """)
                log(f"화면에서 보이는 댓글 항목들: {visible_items}")

                for item in visible_items:
                    if "비허용" in item['text']:
                        cx = item['x'] + item['w'] / 2
                        cy = item['y'] + item['h'] / 2
                        log(f"비허용 마우스 클릭 (좌표): ({cx:.0f}, {cy:.0f})")
                        page.mouse.click(cx, cy)
                        page.wait_for_timeout(500)
                        break

        page.wait_for_timeout(500)
        page.screenshot(path="/tmp/goodisak_after_comment2.png")

        # 패널 다시 확인
        panel = page.query_selector(".ReactModal__Content.editor_layer")
        if panel:
            log("패널 아직 열려있음 - 발행 버튼 클릭")

            # 발행 버튼 좌표 클릭
            publish_btn = page.query_selector("#publish-btn")
            if not publish_btn and panel:
                publish_btn = panel.query_selector("button.btn-default")

            if publish_btn:
                rect = publish_btn.bounding_box()
                btn_text = publish_btn.inner_text().strip()
                log(f"발행 버튼: '{btn_text}' at ({rect['x']:.0f}, {rect['y']:.0f})")
                page.mouse.click(rect['x'] + rect['width']/2, rect['y'] + rect['height']/2)
                log("발행 버튼 마우스 클릭됨")
            else:
                # 공개 발행 텍스트 찾기
                pub_result = page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button');
                    for (const btn of btns) {
                        if (btn.textContent.trim().includes('발행') && !btn.textContent.includes('임시')) {
                            const rect = btn.getBoundingClientRect();
                            if (rect.width > 0) {
                                btn.click();
                                return '클릭: ' + btn.textContent.trim().substring(0, 30);
                            }
                        }
                    }
                    return '없음';
                }
                """)
                log(f"JS 발행 버튼 클릭: {pub_result}")
        else:
            log("패널이 닫혔습니다. 발행이 진행 중일 수 있습니다...")

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
        page.screenshot(path="/tmp/goodisak_final2.png")
        log(f"최종 URL: {final_url}")

        if "manage/newpost" not in final_url:
            log(f"✅ 발행 성공!")
            return final_url
        else:
            # 글 목록에서 확인
            log("글 목록에서 게이밍노트북 글 확인...")
            page.goto("https://goodisak.tistory.com/manage/posts", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            # 최신 글 확인
            latest = page.evaluate("""
            () => {
                const items = document.querySelectorAll('[class*="post"], .list_post, tr');
                const results = [];
                items.forEach(item => {
                    const text = item.textContent.trim();
                    if (text.includes('게이밍')) {
                        results.push(text.substring(0, 100));
                    }
                });
                return results;
            }
            """)
            log(f"게이밍 관련 글: {latest}")
            page.screenshot(path="/tmp/goodisak_posts_check.png")
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
