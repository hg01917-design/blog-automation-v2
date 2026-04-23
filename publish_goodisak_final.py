"""
goodisak Tistory 최종 발행 - 댓글 비허용 설정 + 카테고리 설정 + 발행
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

        # 현재 상태 확인 - 발행 패널이 이미 열려있는지 체크
        publish_panel = page.query_selector(".layer-publish, .publish-layer, [class*='publish']")
        log(f"발행 패널: {publish_panel}")

        # 발행 패널 현재 상태 HTML 확인
        panel_html = page.evaluate("""
        () => {
            // 발행 관련 패널 찾기
            const panel = document.querySelector('.layer-publish') ||
                          document.querySelector('[class*="publish"]') ||
                          document.querySelector('.aside-publish');
            return panel ? panel.outerHTML.substring(0, 2000) : '패널 없음';
        }
        """)
        log(f"패널 HTML: {panel_html[:500]}")

        # 스크린샷 확인
        page.screenshot(path="/tmp/goodisak_publish_panel.png")

        # 1단계: 카테고리 선택 확인
        log("카테고리 상태 확인...")
        cat_info = page.evaluate("""
        () => {
            // 카테고리 선택 요소 찾기
            const catBtn = document.querySelector('.btn-category, [class*="category"]');
            const catText = catBtn ? catBtn.textContent.trim() : '없음';

            // select 요소 찾기
            const selects = document.querySelectorAll('select');
            const selectInfo = Array.from(selects).map(s => ({
                name: s.name || s.id,
                value: s.value,
                options: Array.from(s.options).map(o => o.text.trim()).slice(0, 10)
            }));

            return {catText, selectInfo};
        }
        """)
        log(f"카테고리 정보: {cat_info}")

        # 2단계: 댓글 허용 설정 - "더보기" 버튼 클릭
        log("댓글 설정 더보기 클릭...")
        comment_more = page.evaluate("""
        () => {
            // 댓글 허용 더보기 버튼 찾기
            const btns = document.querySelectorAll('button, a');
            for (const btn of btns) {
                const text = btn.textContent.trim();
                if (text.includes('더보기') || text.includes('댓글')) {
                    return {text: text.substring(0, 50), class: (btn.className || '').substring(0, 80)};
                }
            }
            return null;
        }
        """)
        log(f"댓글 더보기 버튼: {comment_more}")

        # 댓글 허용 버튼 클릭 (더보기 펼치기)
        page.evaluate("""
        () => {
            const btns = document.querySelectorAll('button, a, span');
            for (const btn of btns) {
                const text = btn.textContent.trim();
                if (text === '더보기' || (text.includes('댓글') && text.includes('더보기'))) {
                    btn.click();
                    return '클릭: ' + text;
                }
            }
            return '버튼 없음';
        }
        """)
        page.wait_for_timeout(1000)

        # 댓글 관련 라디오 버튼 확인
        comment_inputs = page.evaluate("""
        () => {
            const inputs = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
            return Array.from(inputs).map(inp => {
                const lbl = document.querySelector('label[for="' + inp.id + '"]') ||
                           inp.closest('label');
                return {
                    id: inp.id,
                    name: inp.name,
                    value: inp.value,
                    checked: inp.checked,
                    label: lbl ? lbl.textContent.trim().substring(0, 40) : ''
                };
            });
        }
        """)
        log(f"댓글 입력 요소들: {comment_inputs}")

        # 댓글 비허용 설정 시도
        # Tistory에서 댓글 비허용은 보통 'commentYn' 또는 'receiveComment' 관련
        disallow_result = page.evaluate("""
        () => {
            // 댓글 관련 모든 label 텍스트 확인
            const labels = document.querySelectorAll('label');
            const commentLabels = [];
            labels.forEach(lbl => {
                const text = lbl.textContent.trim();
                if (text.includes('댓글') || text.includes('허용') || text.includes('비허용')) {
                    commentLabels.push({
                        text: text.substring(0, 50),
                        for: lbl.getAttribute('for') || ''
                    });
                }
            });

            // 전체 본문 텍스트에서 댓글 설정 부분 찾기
            const bodyText = document.body.innerText;
            const commentIdx = bodyText.indexOf('댓글');
            const commentContext = commentIdx >= 0 ? bodyText.substring(commentIdx, commentIdx + 200) : '없음';

            return {commentLabels, commentContext};
        }
        """)
        log(f"댓글 라벨 정보: {disallow_result}")

        page.screenshot(path="/tmp/goodisak_comment_check.png")
        log("댓글 설정 화면 스크린샷 저장")

        # 발행 패널의 전체 HTML을 가져와서 댓글 설정 찾기
        full_panel = page.evaluate("""
        () => {
            // 발행 폼 전체 찾기
            const form = document.querySelector('form') ||
                         document.querySelector('.publish-aside') ||
                         document.querySelector('[class*="layer"]');
            if (form) {
                return form.innerHTML.substring(0, 3000);
            }
            // body 전체 시도
            return document.body.innerHTML.substring(0, 3000);
        }
        """)
        log(f"패널 전체 HTML (첫 2000자): {full_panel[:2000]}")

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        pw.stop()

if __name__ == "__main__":
    main()
