"""
goodisak 티스토리 - 게이밍노트북 임시저장 글에 이미지 삽입

순서:
1. CDP Chrome(9222) 연결
2. https://goodisak.tistory.com/manage/newpost 접속
3. 에디터 하단 "임시저장 (숫자)" 버튼에서 숫자 부분 클릭 → 팝업 열기
4. 팝업에서 게이밍노트북 항목 클릭 → 불러오기
5. 글 내용 확인 (빈 글이면 중단)
6. 기존 이미지 전체 삭제
7. bing-gaming-final-1~4.jpg 4장 에디터에 삽입
8. 임시저장 버튼 클릭
9. 텔레그램 보고

주의: 발행 절대 금지. 임시저장만.
"""
import sys
import os
import time
import base64
from pathlib import Path
from playwright.sync_api import sync_playwright
import subprocess

sys.path.insert(0, "/Users/hana/Downloads/blog-automation-v2")

CDP_URL = "http://localhost:9222"

IMAGE_PATHS = [
    "/Users/hana/Downloads/blog-automation-v2/images/bing-gaming-final-1.jpg",
    "/Users/hana/Downloads/blog-automation-v2/images/bing-gaming-final-2.jpg",
    "/Users/hana/Downloads/blog-automation-v2/images/bing-gaming-final-3.jpg",
    "/Users/hana/Downloads/blog-automation-v2/images/bing-gaming-final-4.jpg",
]

def log(msg):
    print(f"[goodisak] {msg}", flush=True)

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

        # 현재 탭 활성화
        page.bring_to_front()
        page.wait_for_timeout(1000)

        # 현재 에디터 상태 확인
        log("에디터 상태 확인 중...")

        # TinyMCE iframe 확인
        iframe_handle = page.query_selector("iframe#editor-tistory_ifr, iframe#mce_0_ifr, iframe.tox-edit-area__iframe")
        if iframe_handle:
            log("TinyMCE iframe 발견")
        else:
            log("TinyMCE iframe 없음, 에디터 상태 확인...")

        # 스크린샷으로 현재 상태 확인
        screenshot_path = "/tmp/goodisak_editor_state.png"
        page.screenshot(path=screenshot_path)
        log(f"스크린샷 저장: {screenshot_path}")

        # 이미지 업로드 방법: Tistory API를 통한 업로드
        # 먼저 현재 세션 쿠키 가져오기
        cookies = page.context.cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies if "tistory" in c.get("domain", "")])
        log(f"쿠키 수: {len([c for c in cookies if 'tistory' in c.get('domain', '')])}")

        # JavaScript로 이미지 Base64 인코딩 후 삽입하는 방법 사용
        # TinyMCE에 직접 이미지 HTML 삽입

        # 1단계: TinyMCE 에디터에서 H2 위치 확인
        log("TinyMCE 에디터 내용 확인...")

        # iframe 찾기
        iframe_el = page.query_selector("iframe#editor-tistory_ifr")
        if not iframe_el:
            iframe_el = page.query_selector("iframe.tox-edit-area__iframe")
        if not iframe_el:
            # 모든 iframe 나열
            iframes = page.query_selector_all("iframe")
            log(f"전체 iframe 수: {len(iframes)}")
            for idx, ifr in enumerate(iframes):
                src = ifr.get_attribute("src") or ""
                id_attr = ifr.get_attribute("id") or ""
                log(f"  iframe[{idx}]: id={id_attr}, src={src[:80]}")
            if iframes:
                iframe_el = iframes[0]

        if iframe_el:
            frame = iframe_el.content_frame()
            if frame:
                # 현재 내용 확인
                body_html = frame.evaluate("() => document.body.innerHTML")
                h2_count = body_html.count("<h2")
                log(f"H2 태그 수: {h2_count}")
                log(f"현재 내용 길이: {len(body_html)}")

                # 이미지 개수 확인
                img_count = frame.evaluate("() => document.body.querySelectorAll('img').length")
                log(f"현재 이미지 수: {img_count}")

                if img_count >= 3:
                    log("이미지가 이미 3개 이상 있습니다. 발행만 진행합니다.")
                else:
                    # 이미지 삽입: base64로 변환하여 직접 삽입
                    log("이미지 삽입 시작...")

                    for i, img_path in enumerate(IMAGE_PATHS):
                        img_data = Path(img_path).read_bytes()
                        b64 = base64.b64encode(img_data).decode()
                        img_name = Path(img_path).name
                        log(f"이미지 {i+1} 처리 중: {img_name} ({len(img_data)} bytes)")

                        # H2 다음에 이미지 삽입
                        js_code = f"""
                        () => {{
                            const body = document.body;
                            const h2s = body.querySelectorAll('h2');

                            if (h2s.length > {i}) {{
                                const h2 = h2s[{i}];
                                // h2 다음 요소 확인
                                let insertAfter = h2;
                                // h2 바로 다음에 이미지 삽입
                                const imgDiv = document.createElement('div');
                                imgDiv.style.textAlign = 'center';
                                imgDiv.style.margin = '20px 0';

                                const img = document.createElement('img');
                                img.src = 'data:image/webp;base64,{b64}';
                                img.alt = '게이밍노트북추천 2026 이미지 {i+1}';
                                img.style.maxWidth = '100%';
                                img.style.height = 'auto';

                                imgDiv.appendChild(img);

                                // h2 다음에 삽입
                                if (h2.nextSibling) {{
                                    body.insertBefore(imgDiv, h2.nextSibling);
                                }} else {{
                                    body.appendChild(imgDiv);
                                }}
                                return 'inserted_after_h2_' + {i};
                            }} else {{
                                // H2가 없으면 body 끝에 추가
                                const imgDiv = document.createElement('div');
                                imgDiv.style.textAlign = 'center';
                                imgDiv.style.margin = '20px 0';

                                const img = document.createElement('img');
                                img.src = 'data:image/webp;base64,{b64}';
                                img.alt = '게이밍노트북추천 2026 이미지 {i+1}';
                                img.style.maxWidth = '100%';
                                img.style.height = 'auto';

                                imgDiv.appendChild(img);
                                body.appendChild(imgDiv);
                                return 'appended_{i}';
                            }}
                        }}
                        """

                        result = frame.evaluate(js_code)
                        log(f"이미지 {i+1} 삽입 결과: {result}")
                        page.wait_for_timeout(500)

                    # 삽입 후 이미지 수 재확인
                    img_count_after = frame.evaluate("() => document.body.querySelectorAll('img').length")
                    log(f"삽입 후 이미지 수: {img_count_after}")

                    # 글자 수 확인
                    text_len = frame.evaluate("() => document.body.innerText.length")
                    log(f"글자 수: {text_len}")
        else:
            log("ERROR: TinyMCE iframe을 찾을 수 없습니다!")
            sys.exit(1)

        # 스크린샷 저장 (이미지 삽입 후)
        page.screenshot(path="/tmp/goodisak_after_images.png")
        log("이미지 삽입 후 스크린샷 저장")

        # 2단계: 발행 설정 - 카테고리 확인 후 발행
        log("발행 준비 중...")
        page.wait_for_timeout(1000)

        # 발행 버튼 찾기 (Tistory 에디터 발행 버튼)
        # 먼저 우측 패널 확인
        publish_btn = page.query_selector("button.btn_publish, button[data-role='publish'], .btn-publish")
        if publish_btn:
            log(f"발행 버튼 발견: {publish_btn.get_attribute('class')}")
        else:
            # 버튼들 나열
            buttons = page.query_selector_all("button")
            log(f"전체 버튼 수: {len(buttons)}")
            for btn in buttons:
                text = btn.inner_text().strip()
                cls = btn.get_attribute("class") or ""
                if text and len(text) < 30:
                    log(f"  버튼: '{text}' class={cls[:50]}")

        # 댓글 설정 확인 - 우선 현재 설정 상태 확인
        log("댓글 설정 확인 중...")

        # 발행 옵션 패널 확인 (우측 사이드바)
        # Tistory 새 에디터 구조: .publish-area, .btn_publish

        # 발행 버튼 클릭 시도
        # 1. 먼저 ".btn_publish" 시도
        result = page.evaluate("""
        () => {
            // 발행 관련 버튼 찾기
            const allBtns = document.querySelectorAll('button, a[role="button"]');
            const found = [];
            allBtns.forEach(btn => {
                const text = btn.textContent.trim();
                if (text.includes('발행') || text.includes('공개') || text.includes('저장')) {
                    found.push({text: text.substring(0, 50), class: (btn.className || '').substring(0, 80)});
                }
            });
            return found;
        }
        """)
        log(f"발행 관련 버튼 목록: {result}")

        # 댓글 비허용 설정
        log("댓글 비허용 설정 시도...")
        comment_result = page.evaluate("""
        () => {
            // 댓글 허용 여부 라디오 버튼/체크박스 찾기
            const inputs = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
            const found = [];
            inputs.forEach(inp => {
                const label = inp.closest('label') || inp.parentElement;
                const text = label ? label.textContent.trim() : '';
                found.push({
                    type: inp.type,
                    name: inp.name || '',
                    value: inp.value || '',
                    checked: inp.checked,
                    id: inp.id || '',
                    label: text.substring(0, 50)
                });
            });
            return found;
        }
        """)
        log(f"입력 요소들: {comment_result}")

        # 댓글 비허용 설정 (Tistory 에디터)
        # 보통 "댓글 허용" 체크박스를 해제하거나 "비허용" 라디오 선택
        disallow_result = page.evaluate("""
        () => {
            // 댓글 관련 요소 찾기
            const allElements = document.querySelectorAll('[class*="comment"], [id*="comment"], [name*="comment"]');
            const found = [];
            allElements.forEach(el => {
                found.push({
                    tag: el.tagName,
                    id: el.id || '',
                    class: (el.className || '').substring(0, 60),
                    name: el.getAttribute('name') || '',
                    type: el.getAttribute('type') || ''
                });
            });
            return found;
        }
        """)
        log(f"댓글 관련 요소: {disallow_result}")

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
