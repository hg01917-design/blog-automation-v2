"""phn0502 Tistory 파묘 draft 이미지 교체"""
import sys
import time
from pathlib import Path
from browser import connect_cdp, get_or_create_page
from poster import _tistory_upload_image

NEW_IMAGES = [
    Path("images/phn0502/phn0502-pamyo-1-1.jpg"),
    Path("images/phn0502/phn0502-pamyo-1-2.jpg"),
    Path("images/phn0502/phn0502-pamyo-1-3.jpg"),
]

def log(msg):
    print(msg)
    sys.stdout.flush()

def run():
    pw, browser = connect_cdp(on_log=log)
    try:
        page = get_or_create_page(browser)

        # 글쓰기 페이지 열기
        log("[phn0502] 글쓰기 페이지 접근")
        page.goto("https://phn0502.tistory.com/manage/newpost/", wait_until='domcontentloaded')
        time.sleep(5)

        log(f"  현재 URL: {page.url}")

        # 임시저장 버튼 클릭
        draft_btn = page.query_selector('button.btn_draft, .btn-draft, [data-tiara-layer="draft_list"], button:has-text("임시저장")')
        if not draft_btn:
            # JS로 찾기
            draft_btn_exists = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const btn = btns.find(b => b.textContent.includes('임시저장'));
                if (btn) { btn.click(); return true; }
                return false;
            }""")
            log(f"  임시저장 버튼 JS 클릭: {draft_btn_exists}")
        else:
            draft_btn.click()
            log("  임시저장 버튼 클릭")
        time.sleep(2)

        # 드래프트 목록에서 파묘 관련 항목 찾기
        draft_items = page.query_selector_all('.draft-item, .list_draft li, [class*="draft"] li, li[data-id]')
        log(f"  드래프트 항목 수: {len(draft_items)}")

        target_item = None
        for item in draft_items:
            text = item.inner_text().strip()
            log(f"  항목: {text[:50]}")
            if '파묘' in text or '악령' in text or '결말' in text:
                target_item = item
                break

        if not target_item and draft_items:
            target_item = draft_items[0]
            log(f"  파묘 항목 미발견 — 첫 번째 항목 사용")

        if not target_item:
            # 임시저장 팝업에서 직접 찾기
            log("  팝업에서 검색")
            page.evaluate("""() => {
                const items = document.querySelectorAll('[class*="draft"] li, .list_draft li');
                items.forEach(i => console.log(i.textContent));
            }""")
            # 팝업 전체 HTML 출력
            popup_html = page.evaluate("""() => {
                const popup = document.querySelector('[class*="draft"], .layer_draft, .popup_draft');
                return popup ? popup.innerHTML.substring(0, 2000) : 'no popup';
            }""")
            log(f"  팝업 HTML: {popup_html[:500]}")
            return False

        target_item.click()
        log("[phn0502] 드래프트 항목 클릭")
        time.sleep(5)

        # 로드된 제목 확인
        title_el = page.query_selector('#post-title-inp, #title, input[name="title"]')
        if title_el:
            title = title_el.input_value() or ""
            log(f"  로드된 글 제목: {title}")

        # TinyMCE 에디터 내 기존 이미지 모두 삭제
        removed = page.evaluate("""() => {
            try {
                const editor = tinymce && tinymce.activeEditor;
                if (!editor) return -1;
                const imgs = editor.dom.select('img');
                const count = imgs.length;
                imgs.forEach(img => img.remove());
                editor.fire('change');
                return count;
            } catch(e) {
                return -2;
            }
        }""")
        log(f"[phn0502] 기존 이미지 {removed}개 삭제")
        time.sleep(2)

        # 새 이미지 업로드 (각 이미지를 에디터 끝에 삽입)
        success_count = 0
        for i, img_path in enumerate(NEW_IMAGES):
            if not img_path.exists():
                log(f"[phn0502] 이미지 없음: {img_path}")
                continue
            alt = f"파묘 영화 장면 {i+1}"
            ok = _tistory_upload_image(page, str(img_path), alt=alt, on_log=log)
            if ok:
                success_count += 1
                log(f"[phn0502] 이미지 {i+1}/{len(NEW_IMAGES)} 업로드 완료")
            else:
                log(f"[phn0502] 이미지 {i+1}/{len(NEW_IMAGES)} 업로드 실패")
            time.sleep(2)

        log(f"[phn0502] 이미지 교체 완료: {success_count}/{len(NEW_IMAGES)}장")

        # 임시저장
        save_result = page.evaluate("""() => {
            try {
                const btns = Array.from(document.querySelectorAll('button'));
                const saveBtn = btns.find(b => b.textContent.trim() === '임시저장' && !b.closest('.layer_draft'));
                if (saveBtn) { saveBtn.click(); return 'clicked'; }
                return 'not found';
            } catch(e) { return e.toString(); }
        }""")
        log(f"[phn0502] 임시저장 버튼: {save_result}")
        time.sleep(3)

        return success_count > 0

    finally:
        pw.stop()

if __name__ == '__main__':
    ok = run()
    print("성공" if ok else "실패")
