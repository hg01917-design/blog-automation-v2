"""Gemini Playwright 이미지 생성 — CDP로 gemini.google.com 제어
Gemini 쿼터 초과 시 loremflickr 스톡 이미지로 자동 폴백.
쿼터 차단 시간을 파일에 기록하고, 해당 시간 전까지는 Gemini 시도 자체를 건너뜀.
"""
import io
import json
import os
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
from browser import connect_cdp as _connect_cdp, get_or_create_page

GEMINI_URL = "https://gemini.google.com/app"
IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)
_QUOTA_FILE = IMAGES_DIR / ".gemini_quota.json"


def _quota_blocked_until() -> datetime | None:
    """Gemini 쿼터 차단 종료 시각 반환. 차단 중이 아니면 None."""
    if not _QUOTA_FILE.exists():
        return None
    try:
        data = json.loads(_QUOTA_FILE.read_text())
        until = datetime.fromisoformat(data["until"])
        if datetime.now() < until:
            return until
        _QUOTA_FILE.unlink(missing_ok=True)  # 만료되면 삭제
    except Exception:
        pass
    return None


def _save_quota_block(until: datetime):
    """쿼터 차단 종료 시각을 파일에 저장."""
    _QUOTA_FILE.write_text(json.dumps({"until": until.isoformat()}))


def _parse_quota_until(err_text: str) -> datetime:
    """Gemini 오류 메시지에서 차단 해제 시각을 파싱.

    파싱 실패 시 내일 오전 10시를 반환.
    """
    now = datetime.now()
    # "come back at HH:MM" 또는 "try again at HH:MM"
    m = re.search(r'(?:come back|try again)(?: at)? (\d{1,2}):(\d{2})', err_text, re.IGNORECASE)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        candidate = now.replace(hour=h, minute=mn, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    # "tomorrow" 또는 "내일" → 내일 오전 10시
    return (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)


def _generate_via_fallback(prompt: str, filename: str, on_log=None, skip_webp=False):
    """Gemini 쿼터 초과 시 무료 스톡 이미지 폴백 (loremflickr.com).

    프롬프트에서 영문 키워드를 추출해 관련 CC 라이선스 이미지 다운로드.
    API 키 불필요.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    import re as _re
    import ssl as _ssl

    _ctx = _ssl.create_default_context()
    _ctx.check_hostname = False
    _ctx.verify_mode = _ssl.CERT_NONE

    # 프롬프트에서 명사 키워드 추출 (영문 단어 2~3개)
    words = _re.findall(r'[A-Za-z]{4,}', prompt)
    _STOP = {'with', 'from', 'that', 'this', 'photo', 'image', 'realistic',
             'style', 'Korean', 'modern', 'clean', 'bright', 'flat', 'close',
             'showing', 'placed', 'design', 'ratio', 'text', 'watermark'}
    keywords = [w.lower() for w in words if w not in _STOP][:3]
    kw_str = ','.join(keywords) if keywords else 'lifestyle'

    try:
        seed = abs(hash(kw_str)) % 1000
        url = f"https://picsum.photos/seed/{seed}/1024/768"
        log(f"[이미지] picsum.photos 폴백: seed={seed} ({kw_str})")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30, context=_ctx)
        data = resp.read()

        img = Image.open(io.BytesIO(data))
        w, h = img.size
        final_path = IMAGES_DIR / filename
        if skip_webp:
            img.convert("RGB").save(str(final_path), "JPEG", quality=90)
        else:
            img.convert("RGB").save(str(final_path), "WEBP", quality=85)
        log(f"[이미지] picsum.photos 저장 완료: {filename} ({w}x{h})")
        return str(final_path)
    except Exception as e:
        log(f"[이미지] picsum.photos 폴백 실패: {e}")
        return None


def generate_images(image_infos: list, on_log=None, skip_webp=False, reference_images: list = None) -> dict:
    """이미지 프롬프트 리스트로 Gemini에서 이미지 생성 후 저장.

    Args:
        skip_webp: True면 webp 변환 없이 PNG 그대로 저장 (네이버 블로그용)
        reference_images: 참고 이미지 경로 리스트. image_infos와 1:1 매칭.
                          e.g. ['/path/review_1.jpg', '/path/review_2.jpg', None]

    Returns:
        {index: filepath} 딕셔너리 (성공한 것만)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if not image_infos:
        log("[이미지] 생성할 이미지 없음")
        return {}

    # Gemini 쿼터 차단 여부 사전 확인
    _blocked_until = _quota_blocked_until()
    if _blocked_until:
        log(f"[이미지] Gemini 쿼터 차단 중 (해제: {_blocked_until.strftime('%m/%d %H:%M')}) → loremflickr 폴백 모드")

    results = {}

    # 쿼터 차단 중이면 Playwright 없이 폴백만 실행
    if _blocked_until:
        for info in image_infos:
            idx = info["index"]
            prompt = info["prompt"]
            filename = info["filename"]
            filename = re.sub(r'[^\w\-.]', '-', filename)
            filename = re.sub(r'-+', '-', filename).strip('-')
            if skip_webp:
                if not filename.endswith(".jpg") and not filename.endswith(".png"):
                    filename = filename.rsplit(".", 1)[0] + ".jpg"
            else:
                if not filename.endswith(".webp"):
                    filename += ".webp"
            log(f"[이미지 {idx}] 폴백 모드 생성: {prompt[:50]}...")
            fp = _generate_via_fallback(prompt, filename, on_log, skip_webp)
            if fp:
                results[idx] = fp
                log(f"[이미지 {idx}] 저장 완료: {fp}")
        return results

    pw, browser = _connect_cdp(on_log)

    try:
        is_first = True  # 블로그당 첫 이미지만 새 채팅, 나머지는 같은 창 유지
        for info in image_infos:
            idx = info["index"]
            prompt = info["prompt"]
            filename = info["filename"]
            # 파일명 영문+숫자+하이픈만 허용 (한글 제거)
            filename = re.sub(r'[^\w\-.]', '-', filename)
            filename = re.sub(r'-+', '-', filename).strip('-')
            if skip_webp:
                if not filename.endswith(".jpg") and not filename.endswith(".png"):
                    filename = filename.rsplit(".", 1)[0] + ".jpg"
            else:
                if not filename.endswith(".webp"):
                    filename += ".webp"

            log(f"[이미지 {idx}] 생성 시작: {prompt[:50]}...")

            try:
                # 참고 이미지 매칭 (index 기반)
                ref_img = None
                if reference_images:
                    list_idx = next((j for j, inf in enumerate(image_infos) if inf["index"] == idx), None)
                    if list_idx is not None and list_idx < len(reference_images):
                        ref_img = reference_images[list_idx]

                filepath = _generate_single(
                    browser, prompt, filename, on_log,
                    skip_webp=skip_webp,
                    open_new_chat=is_first,
                    reference_image=ref_img,
                )
                is_first = False
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


def _generate_single(browser, prompt: str, filename: str, on_log=None, skip_webp=False,
                     open_new_chat: bool = True, reference_image: str = None):
    """단일 이미지 생성 → 스크린샷 캡처 → webp 변환 (skip_webp=True면 PNG 그대로)

    Args:
        open_new_chat: True면 새 채팅 시작 (첫 이미지). False면 기존 채팅 이어서 사용.
        reference_image: 참고 이미지 로컬 경로. 지정 시 Gemini에 파일 첨부 후 생성 요청.
    """
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

    # 새 대화 시작 (첫 이미지만) — 이후는 같은 채팅창에 이어서 전송
    if open_new_chat:
        try:
            new_chat_btn = page.locator('a[aria-label="새 채팅"], a[aria-label="New chat"]').first
            if new_chat_btn.is_visible(timeout=2000):
                new_chat_btn.click()
                page.wait_for_timeout(2000)
        except Exception:
            pass

    # ── 참고 이미지 첨부 (me1091 쿠팡 리뷰 이미지 등) ─────────────
    if reference_image and Path(reference_image).exists():
        try:
            log(f"[이미지] 참고 이미지 첨부: {Path(reference_image).name}")
            # 파일 업로드 메뉴 열기 버튼 클릭
            upload_menu_btn = page.locator(
                'button[aria-label="파일 업로드 메뉴 열기"], button[aria-label="파일 업로드 메뉴 닫기"]'
            ).first
            if upload_menu_btn.is_visible(timeout=3000):
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    upload_menu_btn.click()
                    page.wait_for_timeout(800)
                    # "파일 업로드" 항목 클릭
                    file_item = page.get_by_text("파일 업로드", exact=True)
                    if file_item.is_visible(timeout=2000):
                        file_item.click()
                    else:
                        # 첫 번째 메뉴 항목 클릭
                        page.locator('[role="menuitem"]').first.click()
                fc = fc_info.value
                fc.set_files(reference_image)
                page.wait_for_timeout(2000)
                log(f"[이미지] 참고 이미지 첨부 완료")
        except Exception as e:
            log(f"[이미지] 참고 이미지 첨부 실패 (무시): {e}")

    # 프롬프트 입력
    input_el = page.locator('.ql-editor').first
    input_el.click()
    page.wait_for_timeout(300)

    if reference_image and Path(reference_image).exists():
        # 참고 이미지 있을 때: 이미지 기반 재생성 지시
        full_prompt = (
            f"이 사진을 참고해서, 비슷한 분위기와 구도로 실사진 스타일의 이미지를 새로 생성해주세요. "
            f"추가 조건: {prompt}. "
            f"사람 얼굴 없음, 텍스트 없음, 로고 없음, 실사진 스타일."
        )
    else:
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

    _QUOTA_KEYWORDS = [
        "can't generate more images", "generate more images for you today",
        "이미지를 더 생성할 수 없", "come back tom",
        "I can't create more images",
    ]

    # 이미지 생성 완료 대기 — JS 기반 감지 (프로필사진 제외, 최소 크기 100px 이상)
    detected_sel = None
    for i in range(90):
        page.wait_for_timeout(1000)
        # JS로 실제 생성 이미지 감지 (user-icon·프로필사진 제외, 100px 이상)
        try:
            found = page.evaluate("""() => {
                const candidates = document.querySelectorAll(
                    'model-response img, .response-container img, [data-response-id] img, ' +
                    '.generated-image img, img.image.loaded, ' +
                    'img[src*="lh3.googleusercontent"]:not([src*="/a/"])'
                );
                for (const img of candidates) {
                    if (img.classList.contains('user-icon')) continue;
                    if ((img.alt || '').includes('프로필')) continue;
                    const w = img.naturalWidth || img.width;
                    const h = img.naturalHeight || img.height;
                    if (w >= 100 && h >= 100) return true;
                }
                return false;
            }""")
            if found and i > 3:
                detected_sel = "model-response img"
                log(f"[이미지] 생성 완료! ({i}초, JS감지)")
                break
        except Exception:
            pass
        # 오류 응답 감지 (10초 이상 경과 후 쿼터 오류 즉시 감지 / 60초 이상이면 일반 오류도 감지)
        if i > 10:
            try:
                has_generated = page.evaluate("""() => {
                    const candidates = document.querySelectorAll(
                        'model-response img, .response-container img, [data-response-id] img'
                    );
                    for (const img of candidates) {
                        if (img.classList.contains('user-icon')) continue;
                        if ((img.alt || '').includes('프로필')) continue;
                        const w = img.naturalWidth || img.width;
                        const h = img.naturalHeight || img.height;
                        if (w >= 100 && h >= 100) return true;
                    }
                    return false;
                }""")
                if not has_generated:
                    err_text = page.evaluate("""() => {
                        const msgs = document.querySelectorAll('model-response, .response-container');
                        if (!msgs.length) return '';
                        const last = msgs[msgs.length - 1];
                        return (last.innerText || '').trim();
                    }""")
                    if err_text and len(err_text) > 20:
                        is_quota = any(kw in err_text for kw in _QUOTA_KEYWORDS)
                        if is_quota:
                            until = _parse_quota_until(err_text)
                            _save_quota_block(until)
                            log(f"[이미지] Gemini 쿼터 초과 감지 ({i}초) — 차단 해제: {until.strftime('%m/%d %H:%M')} → loremflickr 폴백")
                            return _generate_via_fallback(prompt, filename, on_log, skip_webp)
                        if i > 60:
                            log(f"[이미지] 텍스트 응답({len(err_text)}자): {err_text[:80]!r}")
                            log(f"[이미지] 텍스트 오류 응답 감지 ({i}초) — 조기 종료")
                            return None
            except Exception:
                pass
        if i % 15 == 0 and i > 0:
            log(f"[이미지] {i}초 대기 중...")
    else:
        log("[이미지] 타임아웃")
        return None

    page.wait_for_timeout(1000)

    # 생성된 이미지 엘리먼트 찾기 (프로필사진 제외, 100px 이상)
    img_el = page.locator(
        'model-response img:not(.user-icon), .response-container img:not(.user-icon), '
        '[data-response-id] img:not(.user-icon), img.image.loaded'
    ).last
    final_path = IMAGES_DIR / filename

    log("[이미지] canvas 방식으로 이미지 추출 (툴바 없음)...")
    saved = False

    # canvas toDataURL: 생성 이미지(100px 이상)만 추출 — 프로필사진 제외
    _canvas_js = """(selector) => {
        const imgs = Array.from(document.querySelectorAll(selector));
        // 100px 이상인 마지막 이미지 선택 (프로필사진 제외)
        let el = null;
        for (let i = imgs.length - 1; i >= 0; i--) {
            const img = imgs[i];
            if (img.classList.contains('user-icon')) continue;
            if ((img.alt || '').includes('프로필')) continue;
            const w = img.naturalWidth || img.width;
            const h = img.naturalHeight || img.height;
            if (w >= 100 && h >= 100) { el = img; break; }
        }
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
            b64 = page.evaluate(_canvas_js, detected_sel)
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
