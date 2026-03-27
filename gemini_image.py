"""Gemini Playwright 이미지 생성 — CDP로 gemini.google.com 제어"""
import os
import time
from pathlib import Path
from PIL import Image
from browser import connect_cdp as _connect_cdp, get_or_create_page

GEMINI_URL = "https://gemini.google.com/app"
IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)


def generate_images(image_infos: list, on_log=None, skip_webp=False) -> dict:
    """이미지 프롬프트 리스트로 Gemini에서 이미지 생성 후 저장.

    Args:
        skip_webp: True면 webp 변환 없이 PNG 그대로 저장 (네이버 블로그용)

    Returns:
        {index: filepath} 딕셔너리 (성공한 것만)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if not image_infos:
        log("[이미지] 생성할 이미지 없음")
        return {}

    results = {}
    pw, browser = _connect_cdp(on_log)

    try:
        for info in image_infos:
            idx = info["index"]
            prompt = info["prompt"]
            filename = info["filename"]
            # 파일명 영문+숫자+하이픈만 허용 (한글 제거)
            import re as _re
            filename = _re.sub(r'[^\w\-.]', '-', filename)
            filename = _re.sub(r'-+', '-', filename).strip('-')
            if skip_webp:
                if not filename.endswith(".jpg") and not filename.endswith(".png"):
                    filename = filename.rsplit(".", 1)[0] + ".jpg"
            else:
                if not filename.endswith(".webp"):
                    filename += ".webp"

            log(f"[이미지 {idx}] 생성 시작: {prompt[:50]}...")

            try:
                filepath = _generate_single(browser, prompt, filename, on_log, skip_webp=skip_webp)
                if filepath:
                    results[idx] = filepath
                    log(f"[이미지 {idx}] 저장 완료: {filepath}")
                else:
                    log(f"[이미지 {idx}] 생성 실패")
            except Exception as e:
                log(f"[이미지 {idx}] 오류: {e}")

    finally:
        pw.stop()

    return results


def _drag_toolbar_away(page):
    """Gemini 확대창 편집 툴바를 이미지 밖으로 드래그해서 숨긴다.

    툴바를 찾아 페이지 좌상단(이미지 밖)으로 드래그.
    못 찾으면 JS로 숨기거나 마우스를 이동시킨다.
    """
    # JS로 툴바 위치 탐색 (색상 버튼 또는 draggable 편집 요소)
    toolbar_box = page.evaluate("""() => {
        const candidates = [
            ...document.querySelectorAll('color-palette, tool-bar, [class*="toolbar"], [class*="edit-bar"], [class*="action-bar"], [class*="color-picker"]'),
        ];
        // dialog 안에 있는 것만
        const dialog = document.querySelector('dialog, [role="dialog"]');
        for (const el of candidates) {
            if (!el.offsetParent && el.style.display === 'none') continue;
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
                return {x: r.x + r.width/2, y: r.y + r.height/2};
            }
        }
        return null;
    }""")

    if toolbar_box:
        cx, cy = toolbar_box['x'], toolbar_box['y']
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(10, 10, steps=15)
        page.mouse.up()
        page.wait_for_timeout(300)
    else:
        # 못 찾으면 JS로 편집 관련 요소 숨기기 시도
        page.evaluate("""() => {
            const sels = ['color-palette', 'tool-bar', '[class*="toolbar"]', '[class*="edit-bar"]'];
            for (const s of sels) {
                document.querySelectorAll(s).forEach(el => { el.style.visibility = 'hidden'; });
            }
        }""")
        page.mouse.move(0, 0)


def _generate_single(browser, prompt: str, filename: str, on_log=None, skip_webp=False):
    """단일 이미지 생성 → 스크린샷 캡처 → webp 변환 (skip_webp=True면 PNG 그대로)"""
    def log(msg):
        if on_log:
            on_log(msg)

    page = get_or_create_page(browser, url_contains="gemini.google",
                              navigate_to=GEMINI_URL)
    page.wait_for_timeout(2000)

    # 확대 뷰 오버레이가 열려있으면 닫기
    try:
        close_btn = page.locator('button[aria-label="닫기"]').first
        if close_btn.is_visible(timeout=1000):
            close_btn.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass

    # 새 대화 시작
    try:
        new_chat = page.locator('a[aria-label="새 채팅"], a[aria-label="New chat"]').first
        if new_chat.is_visible(timeout=2000):
            new_chat.click()
            page.wait_for_timeout(2000)
    except Exception:
        pass

    # 프롬프트 입력
    input_el = page.locator('.ql-editor').first
    input_el.click()
    page.wait_for_timeout(300)

    full_prompt = f"Generate an image: {prompt}"
    page.evaluate("""(text) => {
        const el = document.querySelector(".ql-editor");
        el.focus();
        document.execCommand("insertText", false, text);
    }""", full_prompt)
    page.wait_for_timeout(500)

    # 전송
    send_btn = page.locator('button[aria-label="메시지 보내기"], button[aria-label="Send message"]').first
    send_btn.click()
    log(f"[이미지] 프롬프트 전송, 생성 대기...")

    # 이미지 생성 완료 대기 (img.image.loaded)
    for i in range(90):
        page.wait_for_timeout(1000)
        loaded = page.locator('img.image.loaded').count()
        if loaded > 0 and i > 5:
            log(f"[이미지] 생성 완료! ({i}초)")
            break
        if i % 15 == 0 and i > 0:
            log(f"[이미지] {i}초 대기 중...")
    else:
        log("[이미지] 타임아웃")
        return None

    page.wait_for_timeout(1000)

    img_el = page.locator('img.image.loaded').last
    png_path = IMAGES_DIR / f"temp_{filename}.png"
    final_path = IMAGES_DIR / filename

    # 이미지 클릭 → 확대창 열기 → 확대된 이미지 스크린샷
    log("[이미지] 이미지 클릭 → 확대창 캡처...")
    captured = False
    try:
        img_el.click()
        page.wait_for_timeout(2000)

        # 확대창 내 큰 이미지 셀렉터 (Gemini 확대 오버레이)
        expanded_selectors = [
            'dialog img',
            '[role="dialog"] img',
            '.lightbox img',
            'mat-dialog-container img',
            'img-comparison-slider img',
        ]
        for sel in expanded_selectors:
            try:
                expanded_img = page.locator(sel).last
                if expanded_img.count() > 0 and expanded_img.is_visible(timeout=1000):
                    # 편집 툴바 드래그로 이미지 밖으로 이동
                    _drag_toolbar_away(page)
                    page.wait_for_timeout(500)
                    expanded_img.screenshot(path=str(png_path))
                    log(f"[이미지] 확대창 캡처 완료 ({sel})")
                    captured = True
                    break
            except Exception:
                continue

        # 확대창 닫기
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            pass

    except Exception as e:
        log(f"[이미지] 확대창 클릭 실패: {e}")

    if not captured:
        log("[이미지] 원본 스크린샷 폴백...")
        page.mouse.move(0, 0)
        page.wait_for_timeout(500)
        img_el.screenshot(path=str(png_path))

    # 하단 10% 워터마크 잘라내기
    try:
        img = Image.open(png_path)
        w, h = img.size
        log(f"[이미지] 원본 크기: {w}x{h}")
        cropped = img.crop((0, 0, w, int(h * 0.9)))
        if skip_webp:
            cropped.save(str(final_path), "JPEG", quality=90)
            png_path.unlink(missing_ok=True)
            log(f"[이미지] JPG 저장 완료: {final_path.name} ({w}x{int(h*0.9)})")
        else:
            cropped.save(str(final_path), "WEBP", quality=85)
            png_path.unlink(missing_ok=True)
            log(f"[이미지] webp 저장 완료: {final_path.name} ({w}x{int(h*0.9)})")
    except Exception as e:
        log(f"[이미지] 저장 실패: {e}, png 유지")
        final_path = png_path

    return str(final_path)
