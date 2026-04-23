"""
goodisak Tistory 발행 스크립트 - 댓글 비허용으로 발행
이미지는 이미 삽입되어 있음
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

        # 이미지 수 재확인
        iframe_el = page.query_selector("iframe#editor-tistory_ifr")
        if not iframe_el:
            iframe_el = page.query_selector("iframe.tox-edit-area__iframe")
        if not iframe_el:
            iframes = page.query_selector_all("iframe")
            if iframes:
                iframe_el = iframes[0]

        if iframe_el:
            frame = iframe_el.content_frame()
            if frame:
                img_count = frame.evaluate("() => document.body.querySelectorAll('img').length")
                text_len = frame.evaluate("() => document.body.innerText.length")
                log(f"이미지 수: {img_count}, 글자 수: {text_len}")

        # "완료" 버튼 클릭 → 발행 설정 패널로 이동
        log("'완료' 버튼 클릭...")

        # 완료 버튼 찾기
        complete_btn = page.query_selector("button.btn.btn-default")
        if complete_btn:
            btn_text = complete_btn.inner_text().strip()
            log(f"발견된 버튼: '{btn_text}'")
            complete_btn.click()
            page.wait_for_timeout(2000)
        else:
            log("'완료' 버튼을 찾지 못함, 다른 방법 시도...")
            # 텍스트로 찾기
            page.get_by_text("완료").first.click()
            page.wait_for_timeout(2000)

        # 스크린샷으로 현재 상태 확인
        page.screenshot(path="/tmp/goodisak_after_complete.png")
        log("완료 버튼 클릭 후 스크린샷 저장")

        # 발행 설정 패널 확인
        log("발행 설정 패널 확인...")
        setting_info = page.evaluate("""
        () => {
            // 모든 텍스트 내용 확인
            const allText = document.body.innerText;
            // 댓글, 발행 관련 부분 추출
            const lines = allText.split('\\n').filter(l =>
                l.includes('댓글') || l.includes('발행') || l.includes('공개') ||
                l.includes('비공개') || l.includes('카테고리')
            );
            return lines.slice(0, 20);
        }
        """)
        log(f"패널 텍스트: {setting_info}")

        # 라디오/체크박스 상태 확인
        inputs = page.evaluate("""
        () => {
            const inputs = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
            return Array.from(inputs).map(inp => ({
                type: inp.type,
                name: inp.name,
                value: inp.value,
                id: inp.id,
                checked: inp.checked,
                label: (() => {
                    const lbl = document.querySelector('label[for="' + inp.id + '"]');
                    return lbl ? lbl.textContent.trim().substring(0, 30) : '';
                })()
            }));
        }
        """)
        log(f"입력 요소들: {inputs}")

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
