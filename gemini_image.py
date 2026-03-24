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

    # 이미지 엘리먼트 스크린샷 캡처
    log("[이미지] 스크린샷 캡처 중...")
    img_el = page.locator('img.image.loaded').last

    png_path = IMAGES_DIR / f"temp_{filename}.png"
    img_el.screenshot(path=str(png_path))

    # 하단 10% 워터마크 잘라내기
    final_path = IMAGES_DIR / filename
    try:
        img = Image.open(png_path)
        w, h = img.size
        cropped = img.crop((0, 0, w, int(h * 0.9)))
        if skip_webp:
            # 네이버: 변환 없이 JPG로 저장
            cropped.save(str(final_path), "JPEG", quality=90)
            png_path.unlink()
            log(f"[이미지] JPG 저장 완료: {final_path.name}")
        else:
            cropped.save(str(final_path), "WEBP", quality=85)
            png_path.unlink()
            log(f"[이미지] webp 변환 완료: {final_path.name}")
    except Exception as e:
        log(f"[이미지] 저장 실패: {e}, png 유지")
        final_path = png_path

    return str(final_path)
