"""
goodisak Tistory 실제 발행 실행 스크립트
- 댓글 비허용 설정
- 카테고리 선택
- 공개 발행
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

        # 현재 이미지 수 확인
        iframe_el = page.query_selector("iframe#editor-tistory_ifr")
        frame = iframe_el.content_frame()
        img_count = frame.evaluate("() => document.body.querySelectorAll('img').length")
        text_len = frame.evaluate("() => document.body.innerText.length")
        log(f"이미지 수: {img_count}, 글자 수: {text_len}")

        if img_count < 3:
            log(f"ERROR: 이미지가 {img_count}개뿐입니다. 최소 3개 필요!")
            sys.exit(1)

        if text_len < 1700:
            log(f"ERROR: 글자 수 {text_len}자가 1700자 미만입니다!")
            sys.exit(1)

        # 이미지 선택 해제 - ESC 키 누르기
        frame.evaluate("() => { document.body.click(); }")
        page.wait_for_timeout(500)

        # "완료" 버튼 클릭 (발행 패널 열기)
        log("'완료' 버튼 클릭...")

        # 완료 버튼을 텍스트로 찾기
        complete_btn = None
        buttons = page.query_selector_all("button")
        for btn in buttons:
            text = btn.inner_text().strip()
            if text == "완료":
                complete_btn = btn
                log(f"'완료' 버튼 발견")
                break

        if complete_btn:
            complete_btn.click()
        else:
            # locator로 시도
            page.locator("button:has-text('완료')").first.click()

        page.wait_for_timeout(2000)

        # 스크린샷 (발행 패널 열린 후)
        page.screenshot(path="/tmp/goodisak_publish_open.png")
        log("발행 패널 스크린샷 저장")

        # 발행 패널 내 요소 확인
        publish_text = page.evaluate("() => document.body.innerText")
        if "발행" in publish_text and "댓글" in publish_text:
            log("발행 패널이 열렸습니다!")
        else:
            log(f"발행 패널 텍스트 (첫 500자): {publish_text[:500]}")

        # 발행 패널 HTML 구조 (레이어)
        panel_html = page.evaluate("""
        () => {
            // 발행 관련 레이어/팝업 찾기
            const layers = document.querySelectorAll('[class*="layer"], [class*="publish"], [class*="popup"]');
            for (const layer of layers) {
                const text = layer.textContent;
                if (text.includes('댓글') && text.includes('발행')) {
                    return {
                        class: (layer.className || '').substring(0, 100),
                        html: layer.outerHTML.substring(0, 5000)
                    };
                }
            }
            return null;
        }
        """)
        log(f"발행 패널 HTML: {panel_html}")

        # 댓글 비허용 설정
        # Tistory 발행 패널에서 댓글 설정
        log("댓글 비허용 설정 중...")

        # 댓글 설정 요소 탐색
        comment_elements = page.evaluate("""
        () => {
            const allText = document.body.innerHTML;
            // 댓글 관련 인덱스 찾기
            const idx = allText.indexOf('댓글');
            if (idx >= 0) {
                return allText.substring(Math.max(0, idx - 100), idx + 500);
            }
            return '없음';
        }
        """)
        log(f"댓글 관련 HTML: {comment_elements[:1000]}")

        # 댓글 허용/비허용 버튼 찾기 및 클릭
        comment_result = page.evaluate("""
        () => {
            // '댓글 허용' 텍스트 인근 더보기 버튼 찾기
            const allElems = document.querySelectorAll('button, a, span');
            const results = [];
            allElems.forEach(el => {
                const text = el.textContent.trim();
                if (text === '더보기' || text.includes('댓글') || text.includes('허용') || text.includes('비허용')) {
                    const rect = el.getBoundingClientRect();
                    results.push({
                        tag: el.tagName,
                        text: text.substring(0, 50),
                        visible: rect.width > 0 && rect.height > 0,
                        x: rect.x,
                        y: rect.y
                    });
                }
            });
            return results;
        }
        """)
        log(f"댓글 관련 요소들: {comment_result}")

        page.wait_for_timeout(1000)

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        pw.stop()

if __name__ == "__main__":
    main()
