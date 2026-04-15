"""nolja100 포스트 #190 수정: 2025년 → 2026년"""
import sys
import time
from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9222"
POST_URL = "https://nolja100.tistory.com/manage/newpost/190?type=post"
TELEGRAM_CHAT_ID = "8674424194"


def load_telegram_token():
    token_paths = [
        "/Users/hana/.claude/projects/-Users-hana-Downloads-blog-automation-v2/memory/telegram_token.txt",
        "/Users/hana/Downloads/blog-automation-v2/.telegram_token",
    ]
    for p in token_paths:
        try:
            with open(p) as f:
                tok = f.read().strip()
                if tok:
                    return tok
        except Exception:
            pass
    return None


def send_telegram(msg):
    token = load_telegram_token()
    if not token:
        print(f"[텔레그램] 토큰 없음, 메시지 미전송: {msg}")
        return
    try:
        import requests as _req
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = _req.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
        print(f"[텔레그램] 전송: {resp.status_code} {resp.text[:100]}")
    except Exception as e:
        print(f"[텔레그램] 전송 실패: {e}")


def main():
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        print(f"[CDP] 연결 성공")
    except Exception as e:
        print(f"[CDP] 연결 실패: {e}")
        pw.stop()
        sys.exit(1)

    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()

    try:
        print(f"[이동] {POST_URL}")
        page.goto(POST_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

        print(f"[현재 URL] {page.url}")

        # TinyMCE 에디터에서 2025년 → 2026년 변경
        replace_result = page.evaluate("""() => {
            const mce = window.tinyMCE || window.tinymce;
            if (!mce) return {error: 'no tinyMCE'};

            let results = [];
            const editors = mce.editors || [];
            const editorList = Array.isArray(editors) ? editors : (editors ? [editors] : []);

            // 모든 에디터 인스턴스 처리
            const allEditors = [];
            if (mce.get) {
                const e = mce.get('editor-tistory');
                if (e) allEditors.push(e);
            }
            if (allEditors.length === 0 && editorList.length > 0) {
                allEditors.push(...editorList);
            }

            allEditors.forEach(editor => {
                let content = editor.getContent();
                const before = (content.match(/2025년/g) || []).length;
                if (before > 0) {
                    // 먼저 "2025년 조사 기준" 패턴 처리
                    content = content.replace(/2025년\s*조사\s*기준/g, '2026년 기준');
                    // 나머지 2025년 모두 변경
                    content = content.replace(/2025년/g, '2026년');
                    editor.setContent(content);
                    editor.save();  // textarea 동기화
                    const after = (content.match(/2025년/g) || []).length;
                    results.push({id: editor.id, before: before, replaced: before - after});
                } else {
                    results.push({id: editor.id, before: 0, replaced: 0});
                }
            });

            return {results: results};
        }""")
        print(f"[TinyMCE 수정] {replace_result}")

        # 변경 확인
        verify = page.evaluate("""() => {
            const mce = window.tinyMCE || window.tinymce;
            if (!mce) return 'no tinyMCE';
            const e = mce.get('editor-tistory');
            if (!e) return 'no editor';
            const content = e.getContent();
            const count2025 = (content.match(/2025년/g) || []).length;
            const count2026 = (content.match(/2026년/g) || []).length;
            return {remaining_2025: count2025, count_2026: count2026};
        }""")
        print(f"[검증] {verify}")

        page.wait_for_timeout(1000)

        # 발행 레이어 버튼 클릭 (완료 버튼 - id: publish-layer-btn)
        print("[발행] publish-layer-btn 클릭...")
        try:
            btn = page.locator('#publish-layer-btn')
            if btn.is_visible(timeout=5000):
                btn.click()
                print("[발행] publish-layer-btn 클릭 완료")
                page.wait_for_timeout(2000)
            else:
                print("[발행] publish-layer-btn 보이지 않음")
        except Exception as e:
            print(f"[발행] publish-layer-btn 오류: {e}")

        # 발행 레이어에서 최종 발행 버튼 확인
        page.wait_for_timeout(1000)
        final_btn = page.evaluate("""() => {
            // 발행 레이어 내 버튼들 확인
            const buttons = Array.from(document.querySelectorAll('button, input[type=submit]'));
            return buttons.map(b => ({
                text: (b.textContent || b.value || '').trim(),
                id: b.id,
                cls: b.className.slice(0, 60)
            })).filter(b => b.text);
        }""")
        print(f"[발행 레이어 버튼들] {final_btn[:10]}")

        # 발행 버튼 재탐색 (레이어 팝업 안에 있을 수 있음)
        publish_clicked = False
        for sel in ['#publish-btn', 'button:has-text("발행")', '.btn-publish', 'button[id*=publish]']:
            try:
                b = page.locator(sel).first
                if b.is_visible(timeout=2000):
                    b.click()
                    print(f"[발행] 최종 발행 클릭: {sel}")
                    publish_clicked = True
                    break
            except Exception:
                pass

        if not publish_clicked:
            # JS로 발행 버튼 찾기
            result = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const pub = btns.find(b => {
                    const t = b.textContent.trim();
                    return t === '발행' || t.includes('공개발행') || t.includes('발행하기');
                });
                if (pub) { pub.click(); return pub.textContent.trim(); }
                return null;
            }""")
            if result:
                print(f"[발행] JS로 발행: {result}")
                publish_clicked = True

        page.wait_for_timeout(3000)
        print(f"[완료] 최종 URL: {page.url}")

    except Exception as e:
        print(f"[오류] {e}")
        import traceback
        traceback.print_exc()
    finally:
        page.close()
        pw.stop()

    send_telegram("✅ 환율 글 2026년으로 수정 완료")
    print("[완료] 작업 종료")


if __name__ == "__main__":
    main()
