"""Bing Image Creator (DALL-E 3) Playwright 이미지 생성 — Gemini 쿼터 차단 시 대안

사용법:
    from bing_image import generate_images_bing
    result = generate_images_bing([
        {'index': 1, 'prompt': '세탁기에 이불 넣는 모습', 'filename': 'laundry1.jpg'},
    ], skip_webp=True)
"""
import json
import re
import time
import urllib.request
import ssl
from pathlib import Path

from browser import connect_cdp, get_or_create_page

IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)
BING_URL = "https://www.bing.com/images/create"

# 세션 간 사용된 OIG URL 추적 (중복 방지)
_USED_OIG_FILE = IMAGES_DIR / ".bing_used_oig.json"

def _load_used_oig() -> set:
    try:
        return set(json.loads(_USED_OIG_FILE.read_text()))
    except Exception:
        return set()

def _save_used_oig(oig_id: str):
    used = _load_used_oig()
    used.add(oig_id)
    # 최대 500개 유지 (오래된 것부터 제거)
    used_list = list(used)[-500:]
    _USED_OIG_FILE.write_text(json.dumps(used_list))

def _extract_oig_id(url: str) -> str:
    """URL에서 OIG ID 추출. blob URL은 쿼리스트링 제거(토큰이 매 세션 변경되므로).
    예: OIG2.abc123 / blob.core.windows.net/path (쿼리 제거)
    """
    m = re.search(r'(OIG[\w.]+)', url)
    if m:
        return m.group(1)
    # blob/th.bing URL: 토큰이 매 세션 바뀌므로 경로만 사용
    if 'blob.core.windows.net' in url or 'th.bing.com' in url:
        return url.split('?')[0]
    return url


def _download_image(url: str, filepath: str, on_log=None) -> bool:
    def log(msg):
        if on_log:
            on_log(msg)
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        data = resp.read()
        if len(data) < 5000:
            log(f"[Bing] 이미지 크기 너무 작음: {len(data)}bytes")
            return False
        Path(filepath).write_bytes(data)
        log(f"[Bing] 저장 완료: {Path(filepath).name} ({len(data)//1024}KB)")
        return True
    except Exception as e:
        log(f"[Bing] 다운로드 실패: {e}")
        return False


def _generate_one(page, prompt: str, filename: str, skip_webp: bool = False, on_log=None, session_used: set = None, output_dir=None) -> str | None:
    """Bing Image Creator에서 이미지 1장 생성 후 저장. 경로 반환."""
    def log(msg):
        if on_log:
            on_log(msg)

    # 파일명 정리
    filename = re.sub(r'[^\w\-.]', '-', filename)
    filename = re.sub(r'-+', '-', filename).strip('-')
    if skip_webp:
        if not filename.endswith(('.jpg', '.jpeg', '.png')):
            filename = Path(filename).stem + '.jpg'
    else:
        if not filename.endswith('.webp'):
            filename = Path(filename).stem + '.webp'

    save_dir = Path(output_dir) if output_dir else IMAGES_DIR
    save_dir.mkdir(parents=True, exist_ok=True)
    out_path = str(save_dir / filename)

    # Bing 이미지 생성 페이지로 이동
    page.goto(BING_URL, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)

    # 로그인 확인
    if 'login' in page.url.lower() or 'signin' in page.url.lower():
        log("[Bing] 로그인 필요 — Microsoft 계정 로그인 상태 확인")
        return None

    JS_GET_OIG = """() => {
        const selectors = [
            '.giic_img img', '.giic_list img', 'img.mimg',
            '.imgpt img', 'a.iusc img', 'img[src*="th.bing.com"]',
        ];
        const found = [];
        for (const sel of selectors) {
            for (const img of document.querySelectorAll(sel)) {
                const src = img.src || img.getAttribute('data-src') || '';
                if (src && src.includes('OIG')) found.push(src);
            }
        }
        for (const sel of selectors) {
            for (const img of document.querySelectorAll(sel)) {
                const src = img.src || img.getAttribute('data-src') || '';
                if (src && src.includes('blob.core.windows.net')) found.push(src);
            }
        }
        return [...new Set(found)];
    }"""

    def _safe_get_oig():
        try:
            return set(page.evaluate(JS_GET_OIG))
        except Exception:
            return set()

    def _safe_eval(js):
        try:
            return page.evaluate(js)
        except Exception:
            return None

    # ★ 제출 전에 현재 OIG 이미지 목록 캡처
    # session_used: 이번 generate_images_bing 호출에서 이미 생성된 OIG ID 세트 (세션 내 중복 방지)
    if session_used is None:
        session_used = set()
    page_oig = _safe_get_oig()
    # 페이지에 있던 것 + 이번 세션에서 이미 생성한 것 모두 제외
    exclude_oigs = page_oig | {u for u in page_oig if _extract_oig_id(u) in {_extract_oig_id(s) for s in session_used}}
    exclude_oigs |= session_used
    log(f"[Bing] 제출 전 페이지 OIG 수: {len(page_oig)}, 세션 생성됨: {len(session_used)}")

    # Image Creator 전용 입력창: #gi_form_q (TEXTAREA, class="b_searchbox gi_sb")
    inp = page.query_selector('#gi_form_q')
    if not inp:
        # 폴백 순서
        for sel in ['textarea.gi_sb', 'textarea[name="q"]', '#gipc_textbox']:
            inp = page.query_selector(sel)
            if inp:
                break
    if not inp:
        log("[Bing] Image Creator 입력창 없음")
        return None

    inp.click()
    page.wait_for_timeout(300)
    inp.fill(prompt)
    page.wait_for_timeout(500)

    # 생성 버튼 또는 Enter 키
    create_btn = page.query_selector('#create_btn_c, button.gi_submit, button[aria-label*="Create"]')
    if create_btn:
        create_btn.click()
        log(f"[Bing] 생성 버튼 클릭")
    else:
        inp.press('Enter')
        log(f"[Bing] Enter로 전송")
    log(f"[Bing] 프롬프트 전송: {prompt[:50]}")
    page.wait_for_timeout(5000)

    # 네비게이션 완료 대기
    try:
        page.wait_for_load_state('domcontentloaded', timeout=10000)
    except Exception:
        pass

    # 로딩 시작 대기 (최대 15초)
    loading_detected = False
    for _ in range(15):
        page.wait_for_timeout(1000)
        is_loading = _safe_eval("""() => {
            return !!(document.querySelector('.gil_status, .giic_loading, [class*="loading"], [class*="progress"]'));
        }""")
        if is_loading:
            log("[Bing] 로딩 감지됨, 생성 대기 중...")
            loading_detected = True
            break

    # 로딩 중이면 완료될 때까지 대기
    if loading_detected:
        for _ in range(60):
            page.wait_for_timeout(1000)
            still_loading = _safe_eval("""() => {
                return !!(document.querySelector('.gil_status, .giic_loading, [class*="loading"], [class*="progress"]'));
            }""")
            if not still_loading:
                log("[Bing] 로딩 완료")
                break
        else:
            log("[Bing] 로딩 60초 초과")

    # 이미지 생성 완료 대기 (최대 30초 추가 확인)
    all_new_urls = []
    for i in range(30):
        page.wait_for_timeout(1000)
        urls = _safe_get_oig()
        # 페이지 기존 + 세션 내 이미 생성된 OIG 모두 제외
        new_urls = [u for u in urls if u not in exclude_oigs and _extract_oig_id(u) not in {_extract_oig_id(s) for s in session_used}]

        # 4장 모두 로딩될 때까지 대기 (최대 30초)
        if len(new_urls) >= 4 or (new_urls and i >= 10):
            all_new_urls = new_urls
            log(f"[Bing] 이미지 {len(all_new_urls)}장 감지 ({i+1}초)")
            break
        elif new_urls and not all_new_urls:
            all_new_urls = new_urls  # 일단 저장, 더 로딩 기다림

        # 에러 메시지 확인
        err = _safe_eval("""() => {
            const errEl = document.querySelector('.gil_err, .gipc_err, [class*="error"]');
            return errEl ? errEl.innerText : null;
        }""")
        if err and ('limit' in err.lower() or 'boost' in err.lower()):
            log(f"[Bing] 쿼터 한계: {err[:80]}")
            return None

    if not all_new_urls:
        log("[Bing] 이미지 URL 감지 실패 (60초 초과)")
        return None

    # 1장 모드: 첫 번째 이미지만 저장 (기존 _generate_one 호환)
    img_url = all_new_urls[0]

    # 사용된 OIG ID 기록
    for u in all_new_urls:
        session_used.add(u)
        _save_used_oig(_extract_oig_id(u))
    log(f"[Bing] OIG {len(all_new_urls)}장 기록")

    # 고해상도 URL로 변환
    if 'th.bing.com' in img_url:
        img_url = img_url.split('?')[0]

    ok = _download_image(img_url, out_path, on_log)
    if ok:
        return out_path

    # 스크린샷 폴백
    try:
        page.screenshot(path=out_path.replace('.jpg', '_screen.png'))
        log(f"[Bing] 스크린샷 폴백: {out_path}")
    except Exception:
        pass
    return None


def _generate_all_four(page, prompt: str, base_filename: str, skip_webp: bool = False,
                        on_log=None, session_used: set = None, output_dir=None) -> list[str]:
    """Bing 1회 요청으로 생성된 이미지 최대 4장 전부 다운로드. 경로 리스트 반환."""
    def log(msg):
        if on_log:
            on_log(msg)

    if session_used is None:
        session_used = set()

    save_dir = Path(output_dir) if output_dir else IMAGES_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    ext = '.jpg' if skip_webp else '.webp'
    base_stem = re.sub(r'[^\w\-]', '-', Path(base_filename).stem)
    base_stem = re.sub(r'-+', '-', base_stem).strip('-')

    # Bing 이미지 생성 페이지로 이동
    page.goto(BING_URL, wait_until='domcontentloaded')
    page.wait_for_timeout(6000)  # lazy load 이미지 충분히 대기

    if 'login' in page.url.lower() or 'signin' in page.url.lower():
        log("[Bing] 로그인 필요")
        return []

    JS_GET_OIG = """() => {
        const selectors = [
            '.giic_img img', '.giic_list img', 'img.mimg',
            '.imgpt img', 'a.iusc img', 'img[src*="th.bing.com"]',
        ];
        const found = [];
        for (const sel of selectors) {
            for (const img of document.querySelectorAll(sel)) {
                const src = img.src || img.getAttribute('data-src') || '';
                if (src && src.includes('OIG')) found.push(src);
            }
        }
        for (const sel of selectors) {
            for (const img of document.querySelectorAll(sel)) {
                const src = img.src || img.getAttribute('data-src') || '';
                if (src && src.includes('blob.core.windows.net')) found.push(src);
            }
        }
        return [...new Set(found)];
    }"""

    def _safe_get_oig():
        try:
            return set(page.evaluate(JS_GET_OIG))
        except Exception:
            return set()

    def _safe_eval(js):
        try:
            return page.evaluate(js)
        except Exception:
            return None

    # 스크롤 3회 반복 → 히스토리/갤러리 lazy 이미지 전부 로드
    try:
        for _ in range(3):
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(2000)
    except Exception:
        pass
    page_oig = _safe_get_oig()
    # 이전 세션 생성 OIG ID도 exclude에 포함 (blob URL은 쿼리 제거 후 비교)
    _prev_oig_ids = _load_used_oig()
    exclude_oig_ids = (
        {_extract_oig_id(u) for u in page_oig}
        | {_extract_oig_id(u) for u in session_used}
        | _prev_oig_ids
    )
    # URL 집합도 normalized 버전으로 (blob 토큰 변경 대응)
    exclude_oigs = {_extract_oig_id(u) for u in page_oig} | {_extract_oig_id(u) for u in session_used}
    log(f"[Bing] 기존 OIG {len(page_oig)}개, 이전세션 ID {len(_prev_oig_ids)}개 exclude")

    # 입력창 찾기
    inp = page.query_selector('#gi_form_q')
    if not inp:
        for sel in ['textarea.gi_sb', 'textarea[name="q"]', '#gipc_textbox']:
            inp = page.query_selector(sel)
            if inp:
                break
    if not inp:
        log("[Bing] 입력창 없음")
        return []

    inp.click()
    page.wait_for_timeout(300)
    inp.fill(prompt)
    page.wait_for_timeout(500)

    create_btn = page.query_selector('#create_btn_c, button.gi_submit, button[aria-label*="Create"]')
    if create_btn:
        create_btn.click()
    else:
        inp.press('Enter')
    log(f"[Bing] 프롬프트 전송 (4장 모드): {prompt[:50]}")
    page.wait_for_timeout(5000)

    try:
        page.wait_for_load_state('domcontentloaded', timeout=10000)
    except Exception:
        pass

    # 로딩 대기
    for _ in range(15):
        page.wait_for_timeout(1000)
        if _safe_eval("""() => !!(document.querySelector('.gil_status, .giic_loading, [class*="loading"]'))"""):
            log("[Bing] 로딩 감지됨, 4장 대기 중...")
            break

    for _ in range(60):
        page.wait_for_timeout(1000)
        if not _safe_eval("""() => !!(document.querySelector('.gil_status, .giic_loading, [class*="loading"]'))"""):
            break

    # 4장 수집 (최대 15초 대기) — normalized ID 기반 비교
    all_new_urls = []
    for i in range(15):
        page.wait_for_timeout(1000)
        urls = _safe_get_oig()
        new_urls = [u for u in urls if _extract_oig_id(u) not in exclude_oig_ids]
        if len(new_urls) >= 4:
            all_new_urls = new_urls[:4]
            log(f"[Bing] 4장 모두 감지 ({i+1}초)")
            break
        if new_urls:
            all_new_urls = new_urls

    if not all_new_urls:
        log("[Bing] 이미지 감지 실패")
        return []

    log(f"[Bing] {len(all_new_urls)}장 다운로드 시작")

    paths = []
    for n, img_url in enumerate(all_new_urls, start=1):
        fname = f"{base_stem}-{n}{ext}"
        out_path = str(save_dir / fname)

        if 'th.bing.com' in img_url:
            img_url = img_url.split('?')[0]

        session_used.add(_extract_oig_id(img_url))  # normalized ID 저장
        _save_used_oig(_extract_oig_id(img_url))

        ok = _download_image(img_url, out_path, on_log)
        if ok:
            paths.append(out_path)
            log(f"[Bing] [{n}/4] 저장: {fname}")
        else:
            log(f"[Bing] [{n}/4] 다운로드 실패: {img_url[:60]}")

    log(f"[Bing] 4장 모드 완료: {len(paths)}장 저장")
    return paths


def generate_images_bing(image_infos: list, skip_webp: bool = False, on_log=None, output_dir=None) -> dict:
    """Bing Image Creator로 이미지 목록 생성.

    Args:
        image_infos: [{'index': int, 'prompt': str, 'filename': str}, ...]
        skip_webp: True면 .jpg 저장 (Naver용)
        on_log: 로그 콜백

    Returns:
        {index: filepath} 딕셔너리
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if not image_infos:
        return {}

    results = {}
    session_used: set = set()  # 이번 호출에서 이미 생성된 이미지 URL 추적 (세션 내 중복 방지)
    pw, browser = connect_cdp()
    try:
        page = get_or_create_page(browser, url_contains="bing.com", navigate_to=BING_URL)
        page.wait_for_timeout(3000)

        # ★ 4장 이하 요청 → Bing 1회 호출로 전부 해결 (크레딧 절약)
        if len(image_infos) <= 4:
            first = image_infos[0]
            log(f"[Bing] 4장 모드: 1회 요청으로 {len(image_infos)}장 생성")
            paths = _generate_all_four(
                page, first['prompt'], first['filename'],
                skip_webp, on_log, session_used, output_dir=output_dir
            )
            for i, info in enumerate(image_infos):
                if i < len(paths):
                    results[info['index']] = paths[i]
                    log(f"[Bing] [{info['index']}] ✓ 저장: {paths[i]}")
                else:
                    log(f"[Bing] [{info['index']}] 이미지 부족 — 추가 생성")
                    path = _generate_one(page, info['prompt'], info['filename'],
                                         skip_webp, on_log, session_used, output_dir=output_dir)
                    if path:
                        results[info['index']] = path
        else:
            # 5장 이상: 기존 방식 (각각 1장씩 생성)
            for info in image_infos:
                idx = info['index']
                prompt = info['prompt']
                filename = info['filename']

                log(f"[Bing] [{idx}] 생성 중: {prompt[:60]}")
                path = _generate_one(page, prompt, filename, skip_webp, on_log, session_used, output_dir=output_dir)
                if path:
                    results[idx] = path
                    log(f"[Bing] [{idx}] ✓ 저장: {path}")
                else:
                    log(f"[Bing] [{idx}] 생성 실패")

                time.sleep(2)
    finally:
        # Bing 탭 닫기 (탭 누적 방지)
        try:
            for ctx in browser.contexts:
                for p in ctx.pages:
                    if 'bing.com' in p.url:
                        p.close()
        except Exception:
            pass
        pw.stop()
    return results


if __name__ == '__main__':
    result = generate_images_bing([
        {'index': 1, 'prompt': '세탁기에 이불을 넣고 세탁하는 가정집 모습, 밝고 깔끔한 분위기', 'filename': 'test_bing1.jpg'},
    ], skip_webp=True, on_log=print)
    print('결과:', result)
