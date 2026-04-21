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
    """URL에서 OIG ID 추출. OIG ID가 없는 blob URL은 쿼리스트링 제거.
    예: OIG2.abc123 (th.bing.com URL도 OIG ID 우선 추출)
    """
    # OIG ID가 있으면 항상 우선 추출 (th.bing.com 포함)
    m = re.search(r'(OIG[\w.]+)', url)
    if m:
        return m.group(1)
    # OIG ID 없는 blob URL: 인증 토큰이 매 세션 바뀌므로 경로만 사용
    if 'blob.core.windows.net' in url:
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

    # 콘텐츠 경고 자동 처리
    def _dismiss_warning():
        try:
            warned = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const back = btns.find(b => b.textContent.includes('돌아가기') || b.textContent.includes('Go back'));
                if (back) { back.click(); return true; }
                return false;
            }""")
            if warned:
                log("[Bing] 콘텐츠 경고 → 돌아가기 클릭")
                page.wait_for_timeout(2000)
                return True
        except Exception:
            pass
        return False

    # 로딩 시작 대기 (최대 15초)
    loading_detected = False
    for _ in range(15):
        page.wait_for_timeout(1000)
        _dismiss_warning()
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
            _dismiss_warning()
            still_loading = _safe_eval("""() => {
                return !!(document.querySelector('.gil_status, .giic_loading, [class*="loading"], [class*="progress"]'));
            }""")
            if not still_loading:
                log("[Bing] 로딩 완료")
                break
        else:
            log("[Bing] 로딩 60초 초과")

    # 에러 메시지 확인 루프
    for _ in range(5):
        page.wait_for_timeout(1000)
        err = _safe_eval("""() => {
            const errEl = document.querySelector('.gil_err, .gipc_err, [class*="error"]');
            return errEl ? errEl.innerText : null;
        }""")
        if err and ('limit' in err.lower() or 'boost' in err.lower()):
            log(f"[Bing] 쿼터 한계: {err[:80]}")
            return None

    # 새로 생성된 이미지 컨테이너에서 다운로드 버튼 클릭 (1장)
    img_containers = []
    for i in range(20):
        page.wait_for_timeout(1000)
        containers = page.query_selector_all('.giic_img, .giic_list .gil_imgcont, [class*="giic"] li')
        if containers:
            img_containers = containers
            log(f"[Bing] 이미지 컨테이너 {len(containers)}개 감지 ({i+1}초)")
            break

    if not img_containers:
        log("[Bing] 이미지 컨테이너 감지 실패")
        return None

    container = img_containers[0]
    try:
        container.hover()
        page.wait_for_timeout(800)
        dl_btn = container.query_selector('a[download], button[aria-label*="ownload"], a[aria-label*="ownload"], .gil_dldBtn, [class*="download"]')
        if dl_btn:
            with page.expect_download(timeout=30000) as dl_info:
                dl_btn.click()
            download = dl_info.value
            download.save_as(out_path)
            log(f"[Bing] 다운로드 완료: {Path(out_path).name}")
            return out_path
        else:
            # 폴백: img src 직접 다운로드
            img_el = container.query_selector('img')
            img_url = img_el.get_attribute('src') if img_el else None
            if img_url:
                if 'th.bing.com' in img_url:
                    img_url = img_url.split('?')[0]
                ok = _download_image(img_url, out_path, on_log)
                if ok:
                    return out_path
    except Exception as e:
        log(f"[Bing] 다운로드 오류: {e}")

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

    # 콘텐츠 경고 자동 처리 함수
    def _dismiss_content_warning():
        try:
            warned = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const back = btns.find(b => b.textContent.includes('돌아가기') || b.textContent.includes('Go back'));
                if (back) { back.click(); return true; }
                return false;
            }""")
            if warned:
                log("[Bing] 콘텐츠 경고 감지 → 돌아가기 클릭")
                page.wait_for_timeout(2000)
                return True
        except Exception:
            pass
        return False

    # 제출 후 URL 변경(결과 페이지 이동) 대기 — 최대 15초
    pre_url = page.url
    for _ in range(15):
        page.wait_for_timeout(1000)
        _dismiss_content_warning()
        if page.url != pre_url:
            log(f"[Bing] 결과 페이지 이동 감지: {page.url[:80]}")
            break

    # 로딩 인디케이터가 나타날 때까지 대기 — 최대 20초
    loading_detected = False
    for _ in range(20):
        page.wait_for_timeout(1000)
        _dismiss_content_warning()
        if _safe_eval("""() => !!(document.querySelector('.gil_status, .giic_loading, [class*="loading"], .loader, [aria-label*="loading"]'))"""):
            log("[Bing] 생성 중 로딩 감지됨, 완료 대기...")
            loading_detected = True
            break

    if not loading_detected:
        # 로딩 표시 못 잡은 경우 — 이미 완료됐거나 즉시 실패, 추가 10초 고정 대기
        log("[Bing] 로딩 인디케이터 미감지 — 10초 추가 대기")
        page.wait_for_timeout(10000)

    # 로딩이 사라질 때까지 대기 — 최대 90초
    for _ in range(90):
        page.wait_for_timeout(1000)
        _dismiss_content_warning()
        if not _safe_eval("""() => !!(document.querySelector('.gil_status, .giic_loading, [class*="loading"], .loader, [aria-label*="loading"]'))"""):
            break
    else:
        log("[Bing] 90초 초과 — 강제 진행")

    # 새로 생성된 이미지 컨테이너 대기 (최대 20초)
    img_containers = []
    for i in range(20):
        page.wait_for_timeout(1000)
        containers = page.query_selector_all('.giic_img, .giic_list .gil_imgcont, [class*="giic"] li')
        if len(containers) >= 4:
            img_containers = containers[:4]
            log(f"[Bing] 이미지 컨테이너 {len(img_containers)}개 감지 ({i+1}초)")
            break
        if containers:
            img_containers = containers

    if not img_containers:
        log("[Bing] 이미지 컨테이너 감지 실패 — OIG URL 직접 다운로드 시도")
        # 컨테이너 없어도 새로 생성된 OIG URL로 직접 다운로드 시도
        new_oig_urls = _safe_get_oig() - page_oig
        new_oig_urls = {u for u in new_oig_urls if _extract_oig_id(u) not in exclude_oig_ids}
        if not new_oig_urls:
            # 페이지 전체 img src 스캔
            all_imgs = _safe_eval("""() => {
                return Array.from(document.querySelectorAll('img')).map(i => i.src || '').filter(s => s.includes('th.bing.com') || s.includes('OIG'));
            }""") or []
            new_oig_urls = {u for u in all_imgs if _extract_oig_id(u) not in exclude_oig_ids}
        paths = []
        for n, url in enumerate(list(new_oig_urls)[:4], start=1):
            fname = f"{base_stem}-{n}{ext}"
            out_path = str(save_dir / fname)
            clean_url = url.split('?')[0] if 'th.bing.com' in url else url
            ok = _download_image(clean_url, out_path, on_log)
            if ok:
                paths.append(out_path)
                log(f"[Bing] OIG 직접 다운로드 [{n}]: {fname}")
        if paths:
            log(f"[Bing] OIG 폴백 완료: {len(paths)}장")
            return paths
        log("[Bing] OIG 폴백도 실패")
        return []

    # 1회 생성된 이미지 컨테이너를 하나씩 호버→다운로드 (추가 Bing 요청 없음)
    paths = []
    for n, container in enumerate(img_containers, start=1):
        fname = f"{base_stem}-{n}{ext}"
        out_path = str(save_dir / fname)
        try:
            container.hover()
            page.wait_for_timeout(600)
            dl_btn = container.query_selector(
                'a[download], button[aria-label*="ownload"], a[aria-label*="ownload"], '
                '.gil_dldBtn, [class*="download"]'
            )
            if dl_btn:
                with page.expect_download(timeout=20000) as dl_info:
                    dl_btn.click()
                dl_info.value.save_as(out_path)
                paths.append(out_path)
                log(f"[Bing] [{n}/{len(img_containers)}] 저장: {fname}")
            else:
                # 다운로드 버튼 없으면 img src 직접 다운로드
                img_el = container.query_selector('img')
                img_url = img_el.get_attribute('src') if img_el else None
                if img_url and 'th.bing.com' in img_url:
                    img_url = img_url.split('?')[0]
                if img_url:
                    ok = _download_image(img_url, out_path, on_log)
                    if ok:
                        paths.append(out_path)
                        log(f"[Bing] [{n}/{len(img_containers)}] img src 저장: {fname}")
        except Exception as e:
            log(f"[Bing] [{n}/{len(img_containers)}] 다운로드 실패: {e}")

    log(f"[Bing] 완료: {len(paths)}/{len(img_containers)}장 저장 (Bing 요청 1회)")
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

        # ★ 항상 _generate_all_four() 배치로 처리 (1회 요청 = 4장, 크레딧 절약)
        # 4장씩 묶어서 처리: 4장→1회, 5~8장→2회, 9~12장→3회
        n = len(image_infos)
        chunks = [image_infos[i:i+4] for i in range(0, n, 4)]
        all_paths: list[str] = []

        for chunk_idx, chunk in enumerate(chunks):
            if len(all_paths) >= n:
                break
            first = chunk[0]
            log(f"[Bing] 배치 {chunk_idx+1}/{len(chunks)}: 1회 요청으로 최대 4장 생성")
            paths = _generate_all_four(
                page, first['prompt'], first['filename'],
                skip_webp, on_log, session_used, output_dir=output_dir
            )
            all_paths.extend(paths)
            log(f"[Bing] 배치 {chunk_idx+1} 완료: {len(paths)}장 획득 (누적 {len(all_paths)}장)")

        # image_infos 슬롯에 순서대로 매핑
        for i, info in enumerate(image_infos):
            if i < len(all_paths):
                results[info['index']] = all_paths[i]
                log(f"[Bing] [{info['index']}] ✓ 저장: {all_paths[i]}")
            else:
                log(f"[Bing] [{info['index']}] 이미지 부족 (생성된 {len(all_paths)}장 < 요청 {n}장)")

        # image_infos보다 많이 생성된 경우 남은 이미지도 추가 인덱스로 저장
        if len(all_paths) > n:
            for extra_i, extra_path in enumerate(all_paths[n:], start=n + 1):
                results[extra_i] = extra_path
                log(f"[Bing] [extra {extra_i}] ✓ 추가 저장: {extra_path}")
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
