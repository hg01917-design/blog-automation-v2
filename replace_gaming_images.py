"""
goodisak 티스토리 게이밍노트북 draft: 기존 이미지 삭제 → Bing 3장 생성 → 업로드
발행/임시저장 버튼 클릭 절대 금지. 이미지 교체만 수행.
"""
import sys
import time
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from browser import connect_cdp, get_or_create_page
from bing_image import generate_images_bing
from poster import _tistory_upload_image

OUTPUT_DIR = "/tmp/goodisak_gaming_bing_images"
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


def log(msg):
    print(f"[replace_gaming] {msg}", flush=True)


def send_telegram(msg: str):
    try:
        subprocess.run(
            ["python3", "/Users/hana/Downloads/blog-automation-v2/tg_send.py", msg],
            timeout=30,
            check=False,
        )
    except Exception as e:
        log(f"텔레그램 전송 오류: {e}")


def main():
    log("=== goodisak 게이밍노트북 이미지 교체 시작 ===")

    # ── Step 1: 티스토리 draft 열기 ──────────────────────────
    pw, browser = connect_cdp(on_log=log)
    log("CDP 연결 성공")

    # 기존 탭에서 goodisak 관리 탭 찾기
    page = None
    for ctx in browser.contexts:
        for p in ctx.pages:
            url = p.url
            if "goodisak.tistory.com/manage" in url or "isag27511.tistory.com/manage" in url:
                page = p
                log(f"기존 goodisak 관리 탭 발견: {url[:80]}")
                break
        if page:
            break

    if page is None:
        page = get_or_create_page(browser, navigate_to="https://goodisak.tistory.com/manage/posts")
        log("goodisak 관리 탭 생성")

    page.bring_to_front()

    # 임시저장 목록으로 이동
    log("임시저장 목록으로 이동...")
    page.goto("https://goodisak.tistory.com/manage/posts?state=temp", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.screenshot(path="/tmp/gaming_draft_list.png")

    # 게이밍노트북 draft 링크 찾기
    found = page.evaluate("""() => {
        const items = document.querySelectorAll('a, .post-item, tr, li');
        for (const el of items) {
            const text = el.textContent || '';
            if (text.includes('게이밍노트북') || text.includes('게이밍 노트북') || text.toLowerCase().includes('gaming')) {
                const link = el.tagName === 'A' ? el : el.querySelector('a');
                if (link && link.href) {
                    return {href: link.href, text: text.trim().substring(0, 100)};
                }
            }
        }
        return null;
    }""")
    log(f"게이밍노트북 draft 검색: {found}")

    if not found or not found.get('href'):
        # 페이지 텍스트 일부 확인
        page_text = page.evaluate("() => document.body.innerText.substring(0, 800)")
        log(f"페이지 텍스트: {page_text[:500]}")

        # 임시저장 탭 클릭 후 재시도
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('a, button, li, span')) {
                if (el.textContent.trim() === '임시저장') { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(2000)

        found = page.evaluate("""() => {
            const items = document.querySelectorAll('a, .post-item, tr, li');
            for (const el of items) {
                const text = el.textContent || '';
                if (text.includes('게이밍노트북') || text.includes('게이밍 노트북') || text.toLowerCase().includes('gaming')) {
                    const link = el.tagName === 'A' ? el : el.querySelector('a');
                    if (link && link.href) {
                        return {href: link.href, text: text.trim().substring(0, 100)};
                    }
                }
            }
            return null;
        }""")
        log(f"재시도 결과: {found}")

    if not found or not found.get('href'):
        msg = "⚠️ 오류 발생\n작업: goodisak 게이밍노트북 draft 열기\n오류: draft를 찾을 수 없음\n조치: 중단"
        send_telegram(msg)
        pw.stop()
        sys.exit(1)

    # 에디터로 이동
    log(f"에디터로 이동: {found['href']}")
    page.goto(found['href'], wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    log(f"현재 URL: {page.url}")

    # ── Step 2: TinyMCE 에디터에서 기존 이미지 삭제 ──────────────────────────
    log("TinyMCE에서 기존 이미지 삭제 중...")

    # TinyMCE 직접 접근
    img_count_before = page.evaluate("""() => {
        try {
            const ed = tinymce.get('content') || tinymce.activeEditor;
            if (ed) {
                return ed.getBody().querySelectorAll('img').length;
            }
        } catch(e) {}
        // iframe 방식 폴백
        const iframe = document.querySelector('iframe#editor-tistory_ifr, iframe.tox-edit-area__iframe, iframe[id*=mce]');
        if (iframe && iframe.contentDocument) {
            return iframe.contentDocument.body.querySelectorAll('img').length;
        }
        return -1;
    }""")
    log(f"삭제 전 이미지 수 (TinyMCE): {img_count_before}")

    removed = page.evaluate("""() => {
        try {
            const ed = tinymce.get('content') || tinymce.activeEditor;
            if (ed) {
                const imgs = ed.getBody().querySelectorAll('img');
                let count = 0;
                imgs.forEach(img => { img.remove(); count++; });
                return {method: 'tinymce', count: count};
            }
        } catch(e) {}
        // iframe 방식 폴백
        const iframe = document.querySelector('iframe#editor-tistory_ifr, iframe.tox-edit-area__iframe, iframe[id*=mce]');
        if (iframe && iframe.contentDocument) {
            const imgs = iframe.contentDocument.body.querySelectorAll('img');
            let count = 0;
            imgs.forEach(img => { img.remove(); count++; });
            return {method: 'iframe', count: count};
        }
        return {method: 'none', count: 0};
    }""")
    log(f"이미지 삭제 결과: {removed}")

    img_count_after_del = page.evaluate("""() => {
        try {
            const ed = tinymce.get('content') || tinymce.activeEditor;
            if (ed) return ed.getBody().querySelectorAll('img').length;
        } catch(e) {}
        const iframe = document.querySelector('iframe#editor-tistory_ifr, iframe.tox-edit-area__iframe, iframe[id*=mce]');
        if (iframe && iframe.contentDocument) {
            return iframe.contentDocument.body.querySelectorAll('img').length;
        }
        return -1;
    }""")
    log(f"삭제 후 이미지 수: {img_count_after_del}")

    # CDP 연결 종료 (Bing 생성은 자체 connect_cdp 사용)
    log("CDP 연결 해제 (Bing 이미지 생성을 위해)...")
    pw.stop()

    # ── Step 3: Bing으로 이미지 3장 생성 ──────────────────────────
    log("Bing 이미지 생성 시작...")
    image_infos = [
        {
            'index': 1,
            'prompt': 'high performance gaming laptop RGB keyboard glowing on dark desk, professional gaming setup',
            'filename': 'gaming-laptop-1.jpg',
        },
        {
            'index': 2,
            'prompt': 'gaming laptop screen showing game with high FPS, colorful game graphics, close-up',
            'filename': 'gaming-laptop-2.jpg',
        },
        {
            'index': 3,
            'prompt': 'gaming laptop comparison chart specs RAM GPU processor, clean infographic style',
            'filename': 'gaming-laptop-3.jpg',
        },
    ]

    try:
        bing_paths = generate_images_bing(
            image_infos,
            skip_webp=True,
            on_log=log,
            output_dir=OUTPUT_DIR,
        )
    except Exception as e:
        err_msg = f"⚠️ 오류 발생\n작업: Bing 이미지 생성\n오류: {str(e)[:200]}\n조치: 중단"
        send_telegram(err_msg)
        raise

    log(f"Bing 생성 결과: {len(bing_paths)}장")
    for idx, path in bing_paths.items():
        log(f"  [{idx}] {path}")

    if not bing_paths:
        msg = "⚠️ 오류 발생\n작업: goodisak 게이밍노트북 Bing 이미지 생성\n오류: 이미지 생성 실패 (0장)\n조치: 중단"
        send_telegram(msg)
        sys.exit(1)

    # ── Step 4: 에디터 재연결 후 이미지 업로드 ──────────────────────────
    log("CDP 재연결 중...")
    pw2, browser2 = connect_cdp(on_log=log)
    log("CDP 재연결 성공")

    # 에디터 탭 찾기
    page2 = None
    for ctx in browser2.contexts:
        for p in ctx.pages:
            url = p.url
            if "goodisak.tistory.com/manage" in url or "isag27511.tistory.com/manage" in url:
                page2 = p
                log(f"에디터 탭 발견: {url[:80]}")
                break
        if page2:
            break

    if page2 is None:
        msg = "⚠️ 오류 발생\n작업: goodisak 에디터 탭 재연결\n오류: 에디터 탭을 찾을 수 없음\n조치: 중단"
        send_telegram(msg)
        pw2.stop()
        sys.exit(1)

    page2.bring_to_front()
    page2.wait_for_timeout(1000)

    # _tistory_upload_image()로 이미지 업로드
    log("이미지 업로드 시작 (_tistory_upload_image 사용)...")
    uploaded_count = 0
    failed_indices = []

    for idx in sorted(bing_paths.keys()):
        img_path = bing_paths[idx]
        if not Path(img_path).exists():
            log(f"  [{idx}] 파일 없음: {img_path}")
            failed_indices.append(idx)
            continue

        log(f"  [{idx}] 업로드 중: {Path(img_path).name}")
        ok = _tistory_upload_image(page2, img_path, alt='게이밍노트북추천', on_log=log)
        if ok:
            uploaded_count += 1
            log(f"  [{idx}] 업로드 성공")
        else:
            log(f"  [{idx}] 업로드 실패")
            failed_indices.append(idx)
        time.sleep(1)

    log(f"업로드 완료: {uploaded_count}/{len(bing_paths)}장")

    # 최종 이미지 수 확인
    final_img_count = page2.evaluate("""() => {
        try {
            const ed = tinymce.get('content') || tinymce.activeEditor;
            if (ed) return ed.getBody().querySelectorAll('img').length;
        } catch(e) {}
        const iframe = document.querySelector('iframe#editor-tistory_ifr, iframe.tox-edit-area__iframe, iframe[id*=mce]');
        if (iframe && iframe.contentDocument) {
            return iframe.contentDocument.body.querySelectorAll('img').length;
        }
        return -1;
    }""")
    log(f"최종 에디터 이미지 수: {final_img_count}")

    page2.screenshot(path="/tmp/goodisak_gaming_replaced.png")
    log("최종 스크린샷: /tmp/goodisak_gaming_replaced.png")

    pw2.stop()
    log("CDP 연결 종료")

    # ── Step 5: 텔레그램 보고 ──────────────────────────
    if uploaded_count == 0:
        err_msg = (
            "⚠️ 오류 발생\n"
            "작업: goodisak 게이밍노트북 이미지 업로드\n"
            f"오류: 전체 {len(bing_paths)}장 업로드 실패\n"
            "조치: 수동 확인 필요"
        )
        send_telegram(err_msg)
    else:
        report = (
            "🖼️ 이미지 교체 완료\n"
            "블로그: goodisak\n"
            "글: 게이밍노트북추천\n"
            f"교체: 기존 이미지 {img_count_before}개 삭제 → 새 이미지 {uploaded_count}장 업로드"
        )
        if failed_indices:
            report += f"\n⚠️ 업로드 실패: {failed_indices}"
        send_telegram(report)
        log("텔레그램 보고 완료")

    log("=== 완료 ===")


if __name__ == "__main__":
    main()
