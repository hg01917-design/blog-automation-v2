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


def _generate_via_fallback(prompt: str, filename: str, on_log=None, skip_webp=False, save_dir: Path = None):
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

    _save_dir = Path(save_dir) if save_dir else IMAGES_DIR
    _save_dir.mkdir(parents=True, exist_ok=True)

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
        final_path = _save_dir / filename
        if skip_webp:
            img.convert("RGB").save(str(final_path), "JPEG", quality=90)
        else:
            img.convert("RGB").save(str(final_path), "WEBP", quality=85)
        log(f"[이미지] picsum.photos 저장 완료: {filename} ({w}x{h})")
        return str(final_path)
    except Exception as e:
        log(f"[이미지] picsum.photos 폴백 실패: {e}")
        return None


def generate_images(image_infos: list, on_log=None, skip_webp=False, reference_images: list = None, output_dir: Path = None) -> dict:
    """이미지 프롬프트 리스트로 Gemini에서 이미지 생성 후 저장.

    Args:
        skip_webp: True면 webp 변환 없이 PNG 그대로 저장 (네이버 블로그용)
        reference_images: 참고 이미지 경로 리스트. image_infos와 1:1 매칭.
        output_dir: 저장 폴더 (None이면 기본 images/ 사용)

    Returns:
        {index: filepath} 딕셔너리 (성공한 것만)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if not image_infos:
        log("[이미지] 생성할 이미지 없음")
        return {}

    # 블로그별 저장 폴더 (output_dir 우선, 없으면 기본 images/)
    save_dir = Path(output_dir) if output_dir else IMAGES_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

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
            fp = _generate_via_fallback(prompt, filename, on_log, skip_webp, save_dir=save_dir)
            if fp:
                results[idx] = fp
                log(f"[이미지 {idx}] 저장 완료: {fp}")
        return results

    # 동시 실행 시 Gemini 탭 충돌 방지 (me1091과 다른 블로그가 동시에 생성하면 컨텍스트 오염)
    import fcntl as _fcntl
    _lock_path = Path("/tmp/gemini_image_session.lock")
    _lock_file = open(_lock_path, "w")
    _fcntl.flock(_lock_file, _fcntl.LOCK_EX)

    pw, browser = _connect_cdp(on_log)

    try:
        # 이미지마다 새 Gemini 채팅 시작 — 같은 채팅 재사용 시 이전 이미지 컨텍스트로 중복 생성됨
        for _img_i, info in enumerate(image_infos):
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
                    open_new_chat=True,  # 매 이미지마다 새 채팅 (중복 방지)
                    reference_image=ref_img,
                    save_dir=save_dir,
                )
                if filepath:
                    results[idx] = filepath
                    log(f"[이미지 {idx}] 저장 완료: {filepath}")
                else:
                    log(f"[이미지 {idx}] 생성 실패")
            except Exception as e:
                log(f"[이미지 {idx}] 오류: {e}")

    finally:
        pw.stop()
        _fcntl.flock(_lock_file, _fcntl.LOCK_UN)
        _lock_file.close()

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
                     open_new_chat: bool = True, reference_image: str = None, save_dir: Path = None):
    """단일 이미지 생성 → 스크린샷 캡처 → webp 변환 (skip_webp=True면 PNG 그대로)

    Args:
        open_new_chat: True면 새 채팅 시작 (첫 이미지). False면 기존 채팅 이어서 사용.
        reference_image: 참고 이미지 로컬 경로. 지정 시 Gemini에 파일 첨부 후 생성 요청.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    _save_dir = Path(save_dir) if save_dir else IMAGES_DIR
    _save_dir.mkdir(parents=True, exist_ok=True)

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
    # ⚠️ 핵심: 반드시 page.goto()로 강제 새 페이지 로드
    #    "새 채팅" 버튼 클릭은 aria-label 변경 시 조용히 실패해서
    #    이전 블로그의 이미지가 채팅에 남아있어 캡처 오염 발생
    if open_new_chat:
        try:
            page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            log("[이미지] Gemini 새 세션 로드 완료")
        except Exception as e:
            log(f"[이미지] Gemini 페이지 이동 실패 ({e}) — 새 채팅 버튼 시도")
            try:
                new_chat_btn = page.locator(
                    'a[aria-label="새 채팅"], a[aria-label="New chat"], '
                    'a[href="/app"], [data-test-id="new-chat-button"]'
                ).first
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
    # "이미지 만들기" 버튼 — Gemini 새 채팅은 기본 활성화 상태이므로 클릭 불필요
    # 클릭하면 오히려 비활성화됨 → 버튼 조작 생략
    log("[이미지] '이미지 만들기' 기본 활성화 상태 유지 (클릭 생략)")

    input_el = page.locator('.ql-editor').first
    input_el.click()
    page.wait_for_timeout(300)

    # 프롬프트 전송 전 다운로드 버튼 수 기록 (새로 생성된 이미지 버튼만 클릭하기 위함)
    try:
        _dl_btn_count_before = page.locator('[data-test-id="download-generated-image-button"]').count()
    except Exception:
        _dl_btn_count_before = 0

    if reference_image and Path(reference_image).exists():
        # 참고 이미지 있을 때: Claude가 만든 프롬프트를 Gemini 지시어로 감싸서 사용
        full_prompt = (
            f"이 사진을 참고해서 비슷한 분위기로 실사진 스타일 이미지를 새로 생성해주세요. "
            f"프롬프트: {prompt}"
        )
    else:
        full_prompt = prompt  # "이미지 만들기" 모드에서는 prefix 불필요

    # 기존 내용 먼저 지우기 (이전 실패한 프롬프트가 남아있을 수 있음)
    page.evaluate("""() => {
        const el = document.querySelector(".ql-editor");
        if (!el) return;
        el.focus();
        document.execCommand("selectAll", false, null);
        document.execCommand("delete", false, null);
    }""")
    page.wait_for_timeout(300)
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

    # ── 네트워크 인터셉트 설정 (전송 후 도착하는 이미지만 캡처, DOM 무관) ──
    import time as _time
    _sent_at = [0.0]
    _captured: list[tuple[bytes, str]] = []   # (image_bytes, content_type)
    _SKIP_URL_TOKENS = ["favicon", "/icon-", "avatar", "/a/", "logo", "profile",
                        "sprite", "badge", "emoji"]

    def _on_response(resp):
        if not _sent_at[0]:
            return
        # 전송 후 5초 이내 캡처는 이전 대화 이미지 lazy-load → 무시
        if _time.time() - _sent_at[0] < 5.0:
            return
        try:
            ct = resp.headers.get("content-type", "")
            if resp.status != 200 or "image" not in ct:
                return
            url = resp.url
            if any(t in url for t in _SKIP_URL_TOKENS):
                return
            body = resp.body()
            if len(body) < 10_000:   # 10KB 미만 아이콘·썸네일 제외
                return
            _captured.append((body, ct))
            log(f"[이미지] 네트워크 캡처 ({len(body)//1024}KB): {url[:70]}")
        except Exception:
            pass

    page.on("response", _on_response)
    send_btn.click(timeout=15000)
    _sent_at[0] = _time.time()
    log("[이미지] 프롬프트 전송, 네트워크 캡처 대기...")

    _QUOTA_KEYWORDS = [
        "can't generate more images", "generate more images for you today",
        "이미지를 더 생성할 수 없", "come back tom",
        "I can't create more images",
    ]

    # 생성 완료 대기 — 네트워크 캡처 우선 감지, 쿼터/오류 보조 감지
    for i in range(240):
        page.wait_for_timeout(1000)

        if _captured and i > 2:
            log(f"[이미지] 생성 완료 ({i}초, 네트워크 {len(_captured)}건 캡처)")
            break

        # 이미지 감지: 모든 프레임 blob/data URL + 큰 이미지 요소 스크린샷
        if i > 5 and not _captured:
            # 방법 1: 모든 프레임에서 blob:/data: URL 검색 (shadow DOM 대응)
            for frame in page.frames:
                if _captured:
                    break
                try:
                    blob_imgs = frame.evaluate("""() => {
                        return Array.from(document.querySelectorAll('img'))
                            .filter(img => (img.src.startsWith('blob:') || img.src.startsWith('data:image'))
                                          && img.naturalWidth > 50)
                            .map(img => img.src);
                    }""")
                    for blob_url in blob_imgs:
                        try:
                            b64 = frame.evaluate("""async (url) => {
                                if (url.startsWith('data:')) return url;
                                const resp = await fetch(url);
                                const blob = await resp.blob();
                                return new Promise(res => {
                                    const r = new FileReader();
                                    r.onloadend = () => res(r.result);
                                    r.readAsDataURL(blob);
                                });
                            }""", blob_url)
                            if b64 and b64.startswith("data:image"):
                                import base64 as _b64
                                header, data = b64.split(",", 1)
                                ct = header.split(";")[0].replace("data:", "")
                                img_bytes = _b64.b64decode(data)
                                if len(img_bytes) > 10_000:
                                    _captured.append((img_bytes, ct))
                                    log(f"[이미지] blob URL 캡처 ({len(img_bytes)//1024}KB)")
                        except Exception:
                            pass
                except Exception:
                    pass

        # 방법 2: 30초 후부터 큰 이미지 요소 스크린샷 (생성 완료 기준)
        if i > 30 and not _captured:
            try:
                # 마지막 model-response 안의 이미지 우선, 없으면 페이지 전체에서 탐색
                for sel in [
                    'model-response img', '.model-response img',
                    'ms-chat-turn:last-of-type img', '[class*="response"] img',
                    'img',
                ]:
                    if _captured:
                        break
                    all_imgs = page.locator(sel).all()
                    # 크기 순 내림차순으로 최대 이미지부터 시도
                    sized = []
                    for img_el in all_imgs:
                        try:
                            bb = img_el.bounding_box()
                            if bb and bb['width'] > 280 and bb['height'] > 280:
                                sized.append((img_el, bb))
                        except Exception:
                            pass
                    sized.sort(key=lambda x: x[1]['width'] * x[1]['height'], reverse=True)
                    for img_el, bb in sized[:3]:
                        try:
                            screenshot = img_el.screenshot(type='jpeg', quality=92)
                            if len(screenshot) > 20_000:
                                _captured.append((screenshot, 'image/jpeg'))
                                log(f"[이미지] 스크린샷 캡처 ({len(screenshot)//1024}KB, {int(bb['width'])}×{int(bb['height'])})")
                                break
                        except Exception:
                            pass
            except Exception:
                pass

        if i > 10:
            try:
                err_text = page.evaluate("""() => {
                    const msgs = document.querySelectorAll('model-response, .response-container');
                    if (!msgs.length) return '';
                    return (msgs[msgs.length - 1].innerText || '').trim();
                }""")
                if err_text and len(err_text) > 20:
                    is_quota = any(kw in err_text for kw in _QUOTA_KEYWORDS)
                    if is_quota:
                        until = _parse_quota_until(err_text)
                        _save_quota_block(until)
                        log(f"[이미지] Gemini 쿼터 초과 ({i}초) — 해제: {until.strftime('%m/%d %H:%M')} → 폴백")
                        page.remove_listener("response", _on_response)
                        return _generate_via_fallback(prompt, filename, on_log, skip_webp, save_dir=save_dir)
                    # "Finalizing the Image" 등 생성 중 정상 메시지는 오류가 아님
                    _GENERATING_KEYWORDS = ["finalizing", "creating your image", "이미지를 만들", "generating", "refining", "crafting", "rendering"]
                    is_generating = any(kw in err_text.lower() for kw in _GENERATING_KEYWORDS)
                    if i > 120 and not _captured and not is_generating:
                        log(f"[이미지] 텍스트 오류 응답 ({i}초) → 조기 종료")
                        page.remove_listener("response", _on_response)
                        return None
            except Exception:
                pass

        if i % 15 == 0 and i > 0:
            log(f"[이미지] {i}초 대기 중... (캡처: {len(_captured)}건)")
    else:
        log("[이미지] 타임아웃")
        page.remove_listener("response", _on_response)
        return None

    page.remove_listener("response", _on_response)
    final_path = _save_dir / filename
    saved = False

    # ── 1차: Gemini 다운로드 버튼 방식 (새로 생성된 버튼만 클릭) ──
    if not saved:
        log("[이미지] 다운로드 버튼 방식 시도...")
        try:
            # 새로 생성된 다운로드 버튼 찾기 (before 카운트 이후에 추가된 버튼)
            try:
                page.wait_for_function(
                    f"() => document.querySelectorAll('[data-test-id=\"download-generated-image-button\"]').length > {_dl_btn_count_before}",
                    timeout=5000
                )
            except Exception:
                pass
            dl_btns = page.locator('[data-test-id="download-generated-image-button"]')
            total_dl = dl_btns.count()
            # 새로 추가된 버튼이 없으면 이전 이미지 버튼 재클릭 방지 — 바로 네트워크 캡처 폴백
            if total_dl <= _dl_btn_count_before:
                log("[이미지] 새 다운로드 버튼 미생성 — 네트워크 캡처 폴백으로 전환")
                raise Exception("no_new_button")
            new_btn_idx = _dl_btn_count_before  # 새로 추가된 첫 번째 버튼
            dl_btn = dl_btns.nth(new_btn_idx)
            if dl_btn.is_visible(timeout=3000):
                with page.expect_download(timeout=30000) as dl_info:
                    dl_btn.evaluate("el => el.click()")
                dl = dl_info.value
                temp_dl_path = _save_dir / f"temp_dl_{filename}"
                dl.save_as(str(temp_dl_path))
                # 워터마크 제거 후 저장
                dl_img = Image.open(str(temp_dl_path))
                dw, dh = dl_img.size
                cropped_dl = dl_img.crop((0, 0, dw, int(dh * 0.90)))
                if skip_webp:
                    cropped_dl.convert("RGB").save(str(final_path), "JPEG", quality=90)
                else:
                    cropped_dl.convert("RGB").save(str(final_path), "WEBP", quality=85)
                Path(str(temp_dl_path)).unlink(missing_ok=True)
                saved = True
                log(f"[이미지] 다운로드 방식 저장 완료: {final_path.name} ({dw}x{dh})")
            else:
                log("[이미지] 다운로드 버튼 미발견 — 네트워크 캡처 폴백으로 전환")
        except Exception as e:
            log(f"[이미지] 다운로드 버튼 방식 실패: {e}")

    # ── 2차 폴백: 네트워크 캡처 이미지 저장 ──
    if not saved and _captured:
        body, ct = _captured[-1]
        try:
            img = Image.open(io.BytesIO(body))
            w, h = img.size
            log(f"[이미지] 네트워크 캡처 폴백: {w}x{h}, {len(body)//1024}KB")
            cropped = img.crop((0, 0, w, int(h * 0.90)))
            if skip_webp:
                cropped.convert("RGB").save(str(final_path), "JPEG", quality=90)
                log(f"[이미지] JPG 저장 완료(네트워크): {final_path.name}")
            else:
                cropped.convert("RGB").save(str(final_path), "WEBP", quality=85)
                log(f"[이미지] WEBP 저장 완료(네트워크): {final_path.name}")
            saved = True
        except Exception as e:
            log(f"[이미지] 네트워크 캡처 저장 실패: {e}")

    # ── 3차 폴백: DOM canvas 추출 ──
    if not saved:
        log("[이미지] 네트워크 캡처 없음 — DOM canvas 폴백...")
        _canvas_js = """(selector) => {
            const imgs = Array.from(document.querySelectorAll(selector));
            let el = null;
            for (let i = imgs.length - 1; i >= 0; i--) {
                const img = imgs[i];
                if (img.classList.contains('user-icon')) continue;
                if ((img.alt || '').includes('프로필')) continue;
                const inUserMsg = img.closest('user-query, .user-message, .human-turn, [data-turn-type="user"]');
                if (inUserMsg) continue;
                const w = img.naturalWidth || img.width;
                const h = img.naturalHeight || img.height;
                if (w >= 100 && h >= 100) { el = img; break; }
            }
            if (!el) return null;
            const w = el.naturalWidth || el.width;
            const h = el.naturalHeight || el.height;
            if (!w || !h) return null;
            const canvas = document.createElement('canvas');
            canvas.width = w; canvas.height = h;
            canvas.getContext('2d').drawImage(el, 0, 0, w, h);
            try { return canvas.toDataURL('image/png').split(',')[1]; } catch(e) { return null; }
        }"""
        try:
            img_el = page.locator(
                'model-response:last-of-type img:not(.user-icon), '
                '.response-container:last-of-type img:not(.user-icon)'
            ).last
            img_el.click()
            page.wait_for_timeout(2000)
            b64 = None
            for sel in ['dialog img', '[role="dialog"] img', 'mat-dialog-container img']:
                try:
                    if page.locator(sel).count() > 0:
                        b64 = page.evaluate(_canvas_js, sel)
                        if b64:
                            log(f"[이미지] DOM canvas 추출 성공 ({sel})")
                            break
                except Exception:
                    continue
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception:
                pass
            if not b64:
                b64 = page.evaluate(_canvas_js, 'model-response img')
                if b64:
                    log("[이미지] DOM canvas 썸네일 추출 성공")
            if b64:
                import base64 as _b64
                raw_bytes = _b64.b64decode(b64)
                img = Image.open(io.BytesIO(raw_bytes))
                w, h = img.size
                cropped = img.crop((0, 0, w, int(h * 0.9)))
                if skip_webp:
                    cropped.convert("RGB").save(str(final_path), "JPEG", quality=90)
                else:
                    cropped.convert("RGB").save(str(final_path), "WEBP", quality=85)
                saved = True
                log(f"[이미지] DOM canvas 저장 완료: {final_path.name}")
        except Exception as e:
            log(f"[이미지] DOM canvas 실패: {e}")

    # ── 최종 폴백: 엘리먼트 스크린샷 ──
    if not saved:
        log("[이미지] 스크린샷 폴백...")
        png_path = _save_dir / f"temp_{filename}.png"
        try:
            img_el = page.locator(
                'model-response:last-of-type img:not(.user-icon)'
            ).last
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
            log(f"[이미지] 스크린샷 저장: {final_path.name}")
            saved = True
        except Exception as e2:
            log(f"[이미지] 스크린샷도 실패: {e2}")

    return str(final_path) if saved else None
