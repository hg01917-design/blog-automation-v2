"""
goodisak Tistory 최종 발행:
1. 카테고리 선택 (IT/컴퓨터 관련)
2. 댓글 비허용 설정
3. 공개 발행 버튼 클릭
"""
import sys
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9222"

def log(msg):
    print(f"[publish] {msg}", flush=True)

def main():
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        log("CDP 연결 성공")

        # goodisak newpost 탭 찾기
        page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "goodisak.tistory.com/manage/newpost" in p.url:
                    page = p
                    log(f"에디터 탭 발견: {p.url}")
                    break
            if page:
                break

        if page is None:
            log("ERROR: goodisak 에디터 탭을 찾을 수 없습니다!")
            sys.exit(1)

        page.bring_to_front()
        page.wait_for_timeout(1000)

        # 발행 패널이 열려있는지 확인
        panel_open = page.evaluate("""
        () => {
            const panel = document.querySelector('.ReactModal__Content.editor_layer');
            return panel ? panel.textContent.includes('발행') : false;
        }
        """)
        log(f"발행 패널 열림: {panel_open}")

        if not panel_open:
            # 완료 버튼 클릭
            log("완료 버튼 클릭...")
            buttons = page.query_selector_all("button")
            for btn in buttons:
                if btn.inner_text().strip() == "완료":
                    btn.click()
                    page.wait_for_timeout(2000)
                    break

        # --- 1단계: 카테고리 선택 ---
        log("카테고리 드롭다운 확인...")

        # 카테고리 버튼 위치 확인
        cat_info = page.evaluate("""
        () => {
            // 카테고리 선택 버튼
            const catBtn = document.querySelector('.btn_category, button[class*="category"]');
            if (catBtn) {
                const rect = catBtn.getBoundingClientRect();
                return {found: true, x: rect.x, y: rect.y, text: catBtn.textContent.trim().substring(0, 50)};
            }

            // "카테고리 선택" 텍스트를 포함하는 버튼
            const allBtns = document.querySelectorAll('button');
            for (const btn of allBtns) {
                if (btn.textContent.includes('카테고리') || btn.textContent.includes('선택')) {
                    const rect = btn.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        return {found: true, x: rect.x, y: rect.y, text: btn.textContent.trim().substring(0, 50), class: btn.className};
                    }
                }
            }
            return {found: false};
        }
        """)
        log(f"카테고리 버튼: {cat_info}")

        # --- 2단계: 댓글 비허용 설정 ---
        log("댓글 비허용 설정 시작...")

        # 댓글 허용 버튼 클릭 (드롭다운 열기)
        comment_btn_result = page.evaluate("""
        () => {
            // 발행 패널 내 댓글 허용 버튼 찾기
            const panel = document.querySelector('.ReactModal__Content.editor_layer') ||
                         document.querySelector('[class*="editor_layer"]');
            if (!panel) return {error: '패널 없음'};

            const btns = panel.querySelectorAll('button');
            for (const btn of btns) {
                const text = btn.textContent.trim();
                if (text.includes('댓글')) {
                    btn.click();
                    return {clicked: true, text: text.substring(0, 50)};
                }
            }
            return {error: '댓글 버튼 없음'};
        }
        """)
        log(f"댓글 버튼 클릭 결과: {comment_btn_result}")
        page.wait_for_timeout(1000)

        # 드롭다운 메뉴 확인 및 비허용 선택
        page.screenshot(path="/tmp/goodisak_comment_dropdown.png")

        dropdown_result = page.evaluate("""
        () => {
            // 드롭다운 메뉴 찾기
            const dropdowns = document.querySelectorAll('[class*="dropdown"], [class*="select-menu"], ul.mce-menu, .mce-floatpanel');
            const results = [];
            dropdowns.forEach(dd => {
                if (dd.offsetParent !== null) {  // visible
                    results.push({
                        class: (dd.className || '').substring(0, 80),
                        text: dd.textContent.trim().substring(0, 200)
                    });
                }
            });

            // 화면에 보이는 메뉴 아이템들
            const menuItems = document.querySelectorAll('li.mce-menu-item, li[role="option"], [class*="menu"] li');
            const items = [];
            menuItems.forEach(item => {
                if (item.offsetParent !== null) {
                    items.push({
                        text: item.textContent.trim().substring(0, 50),
                        class: (item.className || '').substring(0, 80)
                    });
                }
            });

            return {dropdowns: results, menuItems: items};
        }
        """)
        log(f"드롭다운 상태: {dropdown_result}")

        # 비허용 선택 시도
        disallow_result = page.evaluate("""
        () => {
            // 모든 li, span, div 중 '비허용' 텍스트 찾기
            const allElems = document.querySelectorAll('li, span, div, a');
            for (const el of allElems) {
                const text = el.textContent.trim();
                if (text === '비허용' || text === '허용 안함' || text === '댓글 비허용') {
                    if (el.offsetParent !== null) {  // visible
                        el.click();
                        return {clicked: true, text: text};
                    }
                }
            }
            return {clicked: false, message: '비허용 항목 없음'};
        }
        """)
        log(f"비허용 선택 결과: {disallow_result}")
        page.wait_for_timeout(500)

        page.screenshot(path="/tmp/goodisak_after_comment_set.png")

        # 댓글 버튼 텍스트 변경 확인
        comment_status = page.evaluate("""
        () => {
            const panel = document.querySelector('.ReactModal__Content.editor_layer') ||
                         document.querySelector('[class*="editor_layer"]');
            if (!panel) return '패널 없음';
            const btns = panel.querySelectorAll('button');
            for (const btn of btns) {
                if (btn.textContent.includes('댓글') || btn.textContent.includes('허용')) {
                    return btn.textContent.trim().substring(0, 50);
                }
            }
            return '댓글 버튼 없음';
        }
        """)
        log(f"댓글 현재 설정: {comment_status}")

        page.wait_for_timeout(1000)

        # --- 3단계: 카테고리 선택 (발행 패널의 좌측 카테고리) ---
        # 발행 패널이 아닌 왼쪽 사이드바의 카테고리
        # 발행 패널은 별도 모달이므로 카테고리는 사이드바에 있음
        # 그런데 발행 패널에는 카테고리 정보가 없음 (사이드바에서 이미 설정해야 함)
        # 패널 닫기 전 카테고리 확인
        log("발행 패널 내 카테고리 설정 확인...")
        cat_in_panel = page.evaluate("""
        () => {
            const panel = document.querySelector('.ReactModal__Content.editor_layer');
            return panel ? panel.textContent.substring(0, 100) : '패널 없음';
        }
        """)
        log(f"패널 내 텍스트: {cat_in_panel}")

        # --- 4단계: 공개 발행 버튼 클릭 ---
        log("'공개 발행' 버튼 클릭...")

        publish_result = page.evaluate("""
        () => {
            // 발행 버튼 찾기
            const publishBtn = document.querySelector('#publish-btn') ||
                              document.querySelector('button.btn-default[type="submit"]') ||
                              document.querySelector('button.btn-default');

            if (publishBtn) {
                const text = publishBtn.textContent.trim();
                publishBtn.click();
                return {clicked: true, text: text.substring(0, 50)};
            }
            return {clicked: false, message: '발행 버튼 없음'};
        }
        """)
        log(f"발행 버튼 클릭 결과: {publish_result}")

        # 발행 완료 대기
        log("발행 완료 대기 중...")
        page.wait_for_timeout(5000)

        # 발행 후 URL 확인
        current_url = page.url
        log(f"발행 후 URL: {current_url}")

        page.screenshot(path="/tmp/goodisak_published.png")
        log("발행 후 스크린샷 저장")

        # 발행 성공 여부 확인
        if "goodisak.tistory.com" in current_url and "/manage/newpost" not in current_url:
            log(f"✅ 발행 성공! URL: {current_url}")
        else:
            # 페이지 내 성공 메시지 확인
            success_msg = page.evaluate("""
            () => {
                const bodyText = document.body.innerText;
                return bodyText.substring(0, 500);
            }
            """)
            log(f"현재 페이지 내용: {success_msg[:300]}")

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        pw.stop()

if __name__ == "__main__":
    main()
