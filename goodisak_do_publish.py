"""
goodisak Tistory 발행 실행 - 댓글 비허용 설정 후 공개 발행
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

        # 발행 패널 전체 HTML 가져오기 (더 많이)
        full_html = page.evaluate("""
        () => {
            const fieldset = document.querySelector('fieldset');
            return fieldset ? fieldset.innerHTML : document.body.innerHTML;
        }
        """)
        log(f"발행 패널 HTML 길이: {len(full_html)}")

        # 댓글 설정 부분 찾기
        comment_section = page.evaluate("""
        () => {
            // 댓글 관련 dl, div 찾기
            const allElements = document.querySelectorAll('dl, .info_comment, [class*="comment"]');
            const results = [];
            allElements.forEach(el => {
                const text = el.textContent.trim();
                if (text.includes('댓글') || text.includes('comment')) {
                    results.push({
                        tag: el.tagName,
                        class: (el.className || '').substring(0, 80),
                        text: text.substring(0, 100),
                        html: el.outerHTML.substring(0, 500)
                    });
                }
            });
            return results;
        }
        """)
        log(f"댓글 관련 요소: {comment_section}")

        # 카테고리 설정 더보기 버튼 찾기
        cat_more_btn = page.evaluate("""
        () => {
            // 카테고리 더보기 버튼
            const spans = document.querySelectorAll('button, span, a');
            const results = [];
            spans.forEach(el => {
                const text = el.textContent.trim();
                if (text.includes('더보기') || text === '선택 안 함') {
                    results.push({
                        tag: el.tagName,
                        text: text.substring(0, 50),
                        class: (el.className || '').substring(0, 80)
                    });
                }
            });
            return results;
        }
        """)
        log(f"더보기 버튼들: {cat_more_btn}")

        # 발행 패널 전체 HTML 구조 (댓글 섹션 포함) 분석
        layer_body = page.evaluate("""
        () => {
            const layerBody = document.querySelector('.layer_body');
            return layerBody ? layerBody.innerHTML.substring(0, 5000) : '없음';
        }
        """)
        log(f"layer_body HTML: {layer_body[:3000]}")

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        pw.stop()

if __name__ == "__main__":
    main()
