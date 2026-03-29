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

    # 전송 — 버튼이 활성화될 때까지 대기 후 클릭
    send_btn = page.locator('button[aria-label="메시지 보내기"], button[aria-label="Send message"]').first
    try:
        page.wait_for_function("""
            () => {
                const btn = document.querySelector('button[aria-label="메시지 보내기"], button[aria-label="Send message"]');
                return btn && !btn.disabled && !btn.getAttribute('disabled');
            }
        """, timeout=20000)
    except Exception:
        pass
    send_btn.click(timeout=15000)
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
    final_path = IMAGES_DIR / filename

    log("[이미지] canvas 방식으로 이미지 추출 (툴바 없음)...")
    saved = False

    # canvas toDataURL: img 엘리먼트를 canvas에 그려 base64 추출 — 툴바 오버레이 없음
    _canvas_js = """(selector) => {
        const imgs = document.querySelectorAll(selector);
        const el = imgs[imgs.length - 1];
        if (!el) return null;
        const w = el.naturalWidth || el.width;
        const h = el.naturalHeight || el.height;
        if (!w || !h) return null;
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(el, 0, 0, w, h);
        try {
            return canvas.toDataURL('image/png').split(',')[1];
        } catch(e) {
            return null;
        }
    }"""

    # 1차: 확대창 열어서 고해상도 이미지 추출
    try:
        img_el.click()
        page.wait_for_timeout(2000)

        expanded_selectors = [
            'dialog img',
            '[role="dialog"] img',
            '.lightbox img',
            'mat-dialog-container img',
            'img-comparison-slider img',
        ]
        b64 = None
        for sel in expanded_selectors:
            try:
                cnt = page.locator(sel).count()
                if cnt > 0 and page.locator(sel).last.is_visible(timeout=1000):
                    b64 = page.evaluate(_canvas_js, sel)
                    if b64:
                        log(f"[이미지] 확대창 canvas 추출 성공 ({sel})")
                        break
            except Exception:
                continue

        # 확대창 닫기
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            pass

        if not b64:
            # 폴백: 썸네일에서 canvas 추출
            b64 = page.evaluate(_canvas_js, 'img.image.loaded')
            if b64:
                log("[이미지] 썸네일 canvas 추출 성공")

        if b64:
            import base64 as _b64
            import io
            raw_bytes = _b64.b64decode(b64)
            img = Image.open(io.BytesIO(raw_bytes))
            w, h = img.size
            log(f"[이미지] canvas 추출 크기: {w}x{h}")
            cropped = img.crop((0, 0, w, int(h * 0.9)))
            if skip_webp:
                cropped.convert("RGB").save(str(final_path), "JPEG", quality=90)
                log(f"[이미지] JPG 저장 완료: {final_path.name} ({w}x{int(h*0.9)})")
            else:
                cropped.convert("RGB").save(str(final_path), "WEBP", quality=85)
                log(f"[이미지] webp 저장 완료: {final_path.name} ({w}x{int(h*0.9)})")
            saved = True

    except Exception as e:
        log(f"[이미지] canvas 추출 실패: {e}")

    # 최종 폴백: 스크린샷 (툴바 포함될 수 있음)
    if not saved:
        log("[이미지] 스크린샷 폴백...")
        png_path = IMAGES_DIR / f"temp_{filename}.png"
        try:
            page.mouse.move(0, 0)
            page.wait_for_timeout(500)
            img_el.screenshot(path=str(png_path))
            img = Image.open(png_path)
            w, h = img.size
            cropped = img.crop((0, 0, w, int(h * 0.9)))
            if skip_webp:
                cropped.save(str(final_path), "JPEG", quality=90)
            else:
                cropped.save(str(final_path), "WEBP", quality=85)
            png_path.unlink(missing_ok=True)
            log(f"[이미지] 스크린샷 폴백 저장: {final_path.name}")
            saved = True
        except Exception as e2:
            log(f"[이미지] 스크린샷 폴백도 실패: {e2}")
            final_path = png_path

    return str(final_path) if saved else None
