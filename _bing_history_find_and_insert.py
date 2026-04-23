"""
Bing 히스토리에서 게이밍노트북 이미지 찾기 → 다운로드 → 티스토리 sequence 97에 삽입

1단계: Bing Image Creator 히스토리에서 게이밍노트북 이미지 그룹 찾기
2단계: 이미지 4장 다운로드 → bing-gaming-1~4.jpg
3단계: goodisak.tistory.com sequence 97 draft 열기
4단계: 기존 2,3,4번 이미지 삭제 (1번 gaming-laptop-1-1.webp 유지)
5단계: 새 이미지 3장 삽입 후 임시저장

주의: 발행 절대 금지. 탭 1개만 사용.
"""
import sys
import base64
import urllib.request
import ssl
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp, get_or_create_page

IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)

# 새로 다운받을 파일명
NEW_IMAGE_PATHS = [
    str(IMAGES_DIR / "bing-gaming-1.jpg"),
    str(IMAGES_DIR / "bing-gaming-2.jpg"),
    str(IMAGES_DIR / "bing-gaming-3.jpg"),
    str(IMAGES_DIR / "bing-gaming-4.jpg"),
]

# 1번은 기존 이미지 유지 (gaming-laptop-1-1.webp)
KEEP_IMAGE_PATH = str(IMAGES_DIR / "gaming-laptop-1-1.webp")

BING_URL = "https://www.bing.com/images/create"


def log(msg):
    print(f"[bing_insert] {msg}", flush=True)


def _download_image(url: str, filepath: str) -> bool:
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        data = resp.read()
        if len(data) < 5000:
            log(f"이미지 크기 너무 작음: {len(data)}bytes")
            return False
        Path(filepath).write_bytes(data)
        log(f"저장 완료: {Path(filepath).name} ({len(data)//1024}KB)")
        return True
    except Exception as e:
        log(f"다운로드 실패: {e}")
        return False


def step1_find_bing_images(page) -> list:
    """Bing Image Creator 히스토리에서 게이밍노트북 이미지 URL 4개 추출"""
    log("=== Step 1: Bing 히스토리에서 이미지 찾기 ===")

    page.goto(BING_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)

    if "login" in page.url.lower() or "signin" in page.url.lower():
        log("ERROR: Bing 로그인 필요!")
        return []

    log(f"Bing URL: {page.url}")

    # 스크롤 내려서 히스토리 lazy load
    for _ in range(5):
        page.evaluate("() => window.scrollBy(0, 600)")
        page.wait_for_timeout(1500)

    page.evaluate("() => window.scrollTo(0, 0)")
    page.wait_for_timeout(2000)

    # 히스토리 섹션에서 게이밍노트북 관련 이미지 그룹 찾기
    result = page.evaluate("""() => {
        // 히스토리/작업목록 섹션 탐색
        const historySelectors = [
            '.gil_list', '.giis_list', '.giic_history',
            '[class*="history"]', '[class*="giis"]',
            '.gil_content', '[aria-label*="history"]',
        ];

        let historyEl = null;
        for (const sel of historySelectors) {
            historyEl = document.querySelector(sel);
            if (historyEl) break;
        }

        // 히스토리 섹션 내 모든 이미지 그룹 탐색
        const groups = [];

        // 그룹 컨테이너 찾기 (게이밍노트북 관련)
        const groupSelectors = [
            '.giis_item', '.gil_item', '[class*="giis_item"]',
            '.giic_item', '[class*="history_item"]',
        ];

        for (const sel of groupSelectors) {
            const items = document.querySelectorAll(sel);
            for (const item of items) {
                const text = item.textContent || '';
                const isGaming = text.includes('gaming') || text.includes('게이밍') ||
                                 text.includes('laptop') || text.includes('노트북') ||
                                 text.includes('Gaming');
                if (isGaming) {
                    const imgs = item.querySelectorAll('img');
                    const urls = [];
                    for (const img of imgs) {
                        const src = img.src || img.getAttribute('data-src') || '';
                        if (src && !src.startsWith('data:')) urls.push(src);
                    }
                    if (urls.length > 0) {
                        groups.push({text: text.trim().substring(0, 100), urls: urls});
                    }
                }
            }
        }

        // 그룹 못 찾으면 전체 이미지 중 OIG 포함된 것 수집
        if (groups.length === 0) {
            const allImgs = document.querySelectorAll('img');
            const oigUrls = [];
            for (const img of allImgs) {
                const src = img.src || img.getAttribute('data-src') || '';
                if (src && src.includes('OIG')) {
                    oigUrls.push(src);
                }
            }
            if (oigUrls.length > 0) {
                groups.push({text: 'OIG images (all)', urls: oigUrls});
            }
        }

        return {groups: groups, totalImgs: document.querySelectorAll('img').length};
    }""")

    log(f"전체 이미지 수: {result.get('totalImgs', 0)}")
    log(f"게이밍 그룹 수: {len(result.get('groups', []))}")

    for i, g in enumerate(result.get("groups", [])):
        log(f"  그룹[{i}]: '{g['text'][:60]}' — {len(g['urls'])}장")

    # 첫 번째 그룹의 이미지 URL 사용
    groups = result.get("groups", [])
    if groups:
        urls = groups[0]["urls"]
        log(f"사용할 이미지 URL {len(urls)}개:")
        for i, u in enumerate(urls[:4]):
            log(f"  [{i+1}] {u[:80]}")
        return urls[:4]
    else:
        log("게이밍노트북 이미지 그룹을 찾지 못함")
        return []


def step1b_find_bing_images_v2(page) -> list:
    """더 넓은 범위로 Bing 히스토리 탐색 - 4장짜리 세트 찾기"""
    log("=== Step 1b: Bing 이미지 광범위 탐색 ===")

    # 페이지 전체 이미지 분석
    all_img_data = page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        const result = [];
        for (const img of imgs) {
            const src = img.src || img.getAttribute('data-src') || '';
            const alt = img.alt || '';
            const cls = img.className || '';
            const parentCls = (img.parentElement && img.parentElement.className) || '';
            const grandParentCls = (img.parentElement && img.parentElement.parentElement &&
                                   img.parentElement.parentElement.className) || '';

            // Bing 히스토리 이미지 판별 기준
            const isBingHistory = src.includes('th.bing.com') || src.includes('OIG') ||
                                   src.includes('blob.core.windows.net') ||
                                   cls.includes('mimg') || parentCls.includes('giis') ||
                                   grandParentCls.includes('giis');
            if (isBingHistory && src) {
                result.push({src: src, alt: alt, cls: cls, parentCls: parentCls});
            }
        }
        return result;
    }""")

    log(f"Bing 히스토리 이미지 후보: {len(all_img_data)}개")
    for i, d in enumerate(all_img_data[:8]):
        log(f"  [{i+1}] {d['src'][:80]} (alt={d['alt'][:30]})")

    if all_img_data:
        # OIG 포함된 것 우선, 없으면 전체
        oig_urls = [d["src"] for d in all_img_data if "OIG" in d["src"]]
        if len(oig_urls) >= 4:
            log(f"OIG 이미지 {len(oig_urls)}개 발견, 처음 4개 사용")
            return oig_urls[:4]
        all_urls = [d["src"] for d in all_img_data]
        return all_urls[:4]

    return []


def step2_download_images(urls: list) -> list:
    """추출된 URL로 이미지 다운로드, 성공한 경로 반환"""
    log("=== Step 2: 이미지 다운로드 ===")
    downloaded = []
    for i, url in enumerate(urls):
        if i >= 4:
            break
        dest = NEW_IMAGE_PATHS[i]
        # th.bing.com URL: 쿼리스트링 제거 (크기 조정 파라미터 제거)
        clean_url = url.split("?")[0] if "th.bing.com" in url else url
        ok = _download_image(clean_url, dest)
        if ok:
            downloaded.append(dest)
        else:
            # 원본 URL로도 시도
            if clean_url != url:
                ok2 = _download_image(url, dest)
                if ok2:
                    downloaded.append(dest)
    log(f"다운로드 완료: {len(downloaded)}/4장")
    return downloaded


def step3_open_draft_97(page) -> bool:
    """goodisak.tistory.com/manage/newpost 에서 sequence 97 불러오기"""
    log("=== Step 3: goodisak 임시저장 글 97 열기 ===")

    # 임시저장 목록으로 이동
    page.goto("https://goodisak.tistory.com/manage/newpost", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    current_url = page.url
    log(f"현재 URL: {current_url}")

    # 로그인 확인
    if "login" in current_url or "kakao" in current_url or "auth" in current_url:
        log("ERROR: goodisak 로그인 필요!")
        return False

    # 임시저장 팝업 버튼 찾기
    page.wait_for_timeout(2000)

    # 팝업이 뜨는지 확인 (대부분 자동으로 팝업 뜸)
    popup_result = page.evaluate("""() => {
        // 임시저장 팝업 확인
        const popupSels = [
            '.layer-draft', '[class*="draft"]', '.draft-list',
            '.popup-draft', '[id*="draft"]',
        ];
        for (const sel of popupSels) {
            const el = document.querySelector(sel);
            if (el && el.offsetParent !== null) {
                return {found: true, sel: sel};
            }
        }
        return {found: false};
    }""")

    if popup_result.get("found"):
        log(f"임시저장 팝업 이미 열림: {popup_result['sel']}")
    else:
        # 임시저장 버튼 클릭해서 팝업 열기
        log("임시저장 팝업 열기 시도...")
        btn_result = page.evaluate("""() => {
            const btns = document.querySelectorAll('button, a');
            for (const btn of btns) {
                const t = btn.textContent.trim();
                if (t.includes('임시저장') || t.includes('불러오기') || t.includes('draft')) {
                    btn.click();
                    return t;
                }
            }
            return null;
        }""")
        if btn_result:
            log(f"버튼 클릭: '{btn_result}'")
        else:
            log("임시저장 버튼 없음 — 직접 URL로 이동 시도")
            # sequence 97 직접 접근
            page.goto("https://goodisak.tistory.com/manage/post/97", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            log(f"직접 이동 URL: {page.url}")
            return True

        page.wait_for_timeout(2000)

    # 팝업에서 sequence 97 찾기
    found_97 = page.evaluate("""() => {
        // sequence 97 링크 찾기
        const links = document.querySelectorAll('a[href*="post/97"], a[href*="manage/post/97"]');
        if (links.length > 0) {
            links[0].click();
            return {found: true, href: links[0].href};
        }

        // 팝업 내 글 목록 탐색 (번호 97)
        const items = document.querySelectorAll('[class*="draft"] li, [class*="layer"] li, .draft-item');
        for (const item of items) {
            const text = item.textContent;
            if (text.includes('97') || text.includes('게이밍노트북') || text.includes('게이밍 노트북')) {
                const a = item.querySelector('a');
                if (a) { a.click(); return {found: true, text: text.trim().substring(0, 80)}; }
            }
        }
        return {found: false};
    }""")

    log(f"sequence 97 탐색 결과: {found_97}")

    if not found_97.get("found"):
        log("팝업에서 못 찾음 — 직접 URL 이동")
        page.goto("https://goodisak.tistory.com/manage/post/97", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

    page.wait_for_timeout(3000)
    log(f"에디터 URL: {page.url}")
    page.screenshot(path="/tmp/editor_97_opened.png")
    log("에디터 스크린샷: /tmp/editor_97_opened.png")
    return True


def find_iframe(page):
    """TinyMCE iframe 찾기"""
    for sel in [
        "iframe#editor-tistory_ifr",
        "iframe.tox-edit-area__iframe",
        "iframe[id*='mce']",
        "iframe[id*='editor']",
    ]:
        el = page.query_selector(sel)
        if el:
            frame = el.content_frame()
            if frame:
                log(f"iframe 발견: {sel}")
                return frame

    iframes = page.query_selector_all("iframe")
    log(f"전체 iframe 수: {len(iframes)}")
    for i, ifr in enumerate(iframes[:5]):
        id_attr = ifr.get_attribute("id") or ""
        src = ifr.get_attribute("src") or ""
        log(f"  [{i}] id={id_attr}, src={src[:60]}")
    if iframes:
        frame = iframes[0].content_frame()
        if frame:
            log("첫 번째 iframe 사용")
            return frame
    return None


def step4_replace_images(page, new_image_paths: list) -> bool:
    """기존 이미지 2,3,4번 삭제 후 새 이미지 3장 삽입"""
    log("=== Step 4: 이미지 교체 ===")

    frame = find_iframe(page)
    if not frame:
        log("ERROR: 에디터 iframe 없음!")
        page.screenshot(path="/tmp/editor_no_iframe.png")
        return False

    # 현재 이미지 현황 파악
    img_info = frame.evaluate("""() => {
        const imgs = document.body.querySelectorAll('img');
        const result = [];
        for (const img of imgs) {
            result.push({
                src: img.src.substring(0, 80),
                alt: img.alt || '',
                idx: result.length
            });
        }
        return result;
    }""")

    log(f"현재 이미지 수: {len(img_info)}")
    for im in img_info:
        log(f"  [{im['idx']}] {im['src'][:60]} (alt={im['alt']})")

    # 이미지 2번(index 1), 3번(index 2), 4번(index 3) 삭제
    # 1번(index 0)은 gaming-laptop-1-1.webp → 유지
    del_result = frame.evaluate("""() => {
        const imgs = Array.from(document.body.querySelectorAll('img'));
        let deleted = 0;
        // index 1 이상 삭제 (0번 유지)
        for (let i = imgs.length - 1; i >= 1; i--) {
            const img = imgs[i];
            const parent = img.parentElement;
            if (parent && parent !== document.body &&
                (parent.children.length === 1 || parent.tagName === 'P' || parent.tagName === 'DIV')) {
                parent.remove();
            } else {
                img.remove();
            }
            deleted++;
        }
        return {deleted: deleted, remaining: document.body.querySelectorAll('img').length};
    }""")

    log(f"삭제 결과: {del_result['deleted']}개 삭제, {del_result['remaining']}개 남음")

    if del_result["remaining"] == 0:
        log("WARNING: 1번 이미지도 삭제됨. 복구 필요.")

    # 새 이미지 3장(bing-gaming-2~4.jpg)을 순서대로 삽입
    # 삽입 위치: 소제목(H2/H3) 뒤 또는 단락 사이
    insert_paths = new_image_paths[1:4]  # 2,3,4번 (index 1,2,3)
    log(f"삽입할 이미지: {[Path(p).name for p in insert_paths]}")

    insert_count = 0
    for i, img_path in enumerate(insert_paths):
        if not Path(img_path).exists():
            log(f"WARNING: 이미지 파일 없음: {img_path}")
            continue

        img_data = Path(img_path).read_bytes()
        b64 = base64.b64encode(img_data).decode()

        # 확장자로 mime 타입 결정
        ext = Path(img_path).suffix.lower()
        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/webp"

        result = frame.evaluate("""(args) => {
            const i = args.idx;
            const b64 = args.b64;
            const mime = args.mime;

            const wrapper = document.createElement('p');
            wrapper.style.textAlign = 'center';
            wrapper.style.margin = '20px 0';

            const img = document.createElement('img');
            img.src = 'data:' + mime + ';base64,' + b64;
            img.alt = '게이밍노트북 추천 이미지 ' + (i + 2);
            img.style.maxWidth = '100%';
            img.style.height = 'auto';
            img.setAttribute('data-new', '1');

            wrapper.appendChild(img);

            // 소제목(H2/H3) 다음 위치에 삽입
            const headings = document.body.querySelectorAll('h2, h3');

            // i번째 소제목 뒤에 삽입 (i+1번째 소제목이 있으면 그 앞에)
            if (headings.length > i) {
                const h = headings[i];
                // 이 소제목 다음에 이미 data-new 이미지가 있으면 그 뒤에
                let insertPoint = h;
                let next = h.nextSibling;
                while (next && next.nodeType === 1) {
                    const el = next;
                    if (el.querySelector && el.querySelector('img[data-new]')) {
                        insertPoint = el;
                        next = el.nextSibling;
                    } else {
                        break;
                    }
                }
                if (insertPoint.nextSibling) {
                    insertPoint.parentNode.insertBefore(wrapper, insertPoint.nextSibling);
                } else {
                    insertPoint.parentNode.appendChild(wrapper);
                }
                return 'inserted_after_h' + i + '_' + (h.textContent || '').trim().substring(0, 20);
            } else if (headings.length > 0) {
                // 소제목이 부족하면 마지막 소제목 뒤에 순서대로
                const lastH = headings[headings.length - 1];
                let insertPoint = lastH;
                let next = lastH.nextSibling;
                while (next) {
                    const el = next;
                    next = next.nextSibling;
                    if (el.nodeType === 1 && el.querySelector && el.querySelector('img[data-new]')) {
                        insertPoint = el;
                    } else {
                        break;
                    }
                }
                if (insertPoint.nextSibling) {
                    insertPoint.parentNode.insertBefore(wrapper, insertPoint.nextSibling);
                } else {
                    insertPoint.parentNode.appendChild(wrapper);
                }
                return 'appended_after_last_heading_' + i;
            } else {
                document.body.appendChild(wrapper);
                return 'appended_to_body_' + i;
            }
        }""", {"idx": i, "b64": b64, "mime": mime})

        log(f"  [{i+1}/3] {Path(img_path).name}: {result}")
        if result:
            insert_count += 1
        page.wait_for_timeout(300)

    final_count = frame.evaluate("() => document.body.querySelectorAll('img').length")
    log(f"최종 이미지 수: {final_count}개 (삽입: {insert_count}/3개)")
    page.screenshot(path="/tmp/after_image_insert.png")
    log("삽입 후 스크린샷: /tmp/after_image_insert.png")

    return insert_count > 0


def step5_save_draft(page) -> bool:
    """임시저장 (발행 금지)"""
    log("=== Step 5: 임시저장 ===")

    saved = page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            const text = btn.textContent.trim();
            if (text === '임시저장' || text.includes('임시저장')) {
                btn.click();
                return text;
            }
        }
        // 발행 버튼은 절대 클릭 금지
        return null;
    }""")

    if saved:
        log(f"임시저장 클릭: '{saved}'")
    else:
        log("임시저장 버튼 없음 — Ctrl+S 시도")
        page.keyboard.press("Control+s")

    page.wait_for_timeout(3000)
    page.screenshot(path="/tmp/after_save_draft.png")
    log("임시저장 후 스크린샷: /tmp/after_save_draft.png")

    # 저장 완료 확인
    save_check = page.evaluate("""() => {
        const body = document.body.textContent;
        if (body.includes('저장되었습니다') || body.includes('임시저장 완료') ||
            body.includes('saved') || body.includes('저장 완료')) {
            return '저장 완료 확인';
        }
        return null;
    }""")

    if save_check:
        log(f"저장 확인: {save_check}")
    else:
        log("저장 완료 메시지 미감지 (이미 저장됐을 수 있음)")

    return True


def main():
    log("=== goodisak sequence 97 게이밍노트북 이미지 교체 시작 ===")

    # 기존 이미지 존재 확인
    keep_img = Path(KEEP_IMAGE_PATH)
    if keep_img.exists():
        log(f"1번 이미지 확인: {keep_img.name} ({keep_img.stat().st_size:,} bytes)")
    else:
        log(f"WARNING: 1번 이미지 없음: {KEEP_IMAGE_PATH}")

    pw, browser = connect_cdp(on_log=log)
    log("CDP 연결 성공")

    try:
        # 탭 1개만 사용: Bing 탭 찾기 또는 새로 열기
        page = get_or_create_page(browser, url_contains="bing.com", navigate_to=None)

        # Step 1: Bing 히스토리에서 게이밍노트북 이미지 찾기
        # 현재 페이지가 Bing이 아니면 Bing으로 이동
        if "bing.com" not in page.url:
            log("Bing이 아닌 탭 — Bing으로 이동")
            page.goto("https://www.bing.com/images/create", wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

        img_urls = step1_find_bing_images(page)

        if not img_urls:
            log("Step 1 실패 — 광범위 탐색 시도")
            img_urls = step1b_find_bing_images_v2(page)

        # Step 2: 이미지 다운로드
        downloaded = []
        if img_urls:
            downloaded = step2_download_images(img_urls)
        else:
            log("Bing 히스토리에서 이미지 URL을 찾지 못함")
            log("기존 gaming-laptop-1-2~4.jpg 이미지를 대체 사용")
            # 폴백: 기존 gaming-laptop 이미지 사용
            fallback_paths = [
                str(IMAGES_DIR / "gaming-laptop-1-2.jpg"),
                str(IMAGES_DIR / "gaming-laptop-1-3.jpg"),
                str(IMAGES_DIR / "gaming-laptop-1-4.jpg"),
            ]
            import shutil
            for i, src in enumerate(fallback_paths):
                dst = NEW_IMAGE_PATHS[i + 1]  # bing-gaming-2,3,4
                if Path(src).exists():
                    shutil.copy2(src, dst)
                    downloaded.append(dst)
                    log(f"폴백 복사: {Path(src).name} → {Path(dst).name}")

        if not downloaded:
            log("ERROR: 사용 가능한 이미지 없음!")
            pw.stop()
            sys.exit(1)

        log(f"사용할 이미지: {[Path(d).name for d in downloaded]}")

        # Step 3: goodisak sequence 97 열기
        # (탭 재사용: page.goto()로 이동)
        ok = step3_open_draft_97(page)
        if not ok:
            log("ERROR: draft 97 열기 실패!")
            pw.stop()
            sys.exit(1)

        page.wait_for_timeout(2000)

        # Step 4: 이미지 교체
        # new_image_paths 구성: [bing-gaming-1.jpg(안 쓸 것), bing-gaming-2.jpg, ...]
        # 실제 삽입은 downloaded에 있는 것만
        all_new = [NEW_IMAGE_PATHS[0]] + downloaded  # [0]은 사용 안 함
        ok2 = step4_replace_images(page, all_new)
        if not ok2:
            log("ERROR: 이미지 삽입 실패!")
            pw.stop()
            sys.exit(1)

        # Step 5: 임시저장
        step5_save_draft(page)

        log("=== 모든 작업 완료 ===")
        log(f"삽입된 이미지: {[Path(d).name for d in downloaded]}")
        log("임시저장 완료. 발행은 별도 검수 후 진행 필요.")

    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pw.stop()
        log("CDP 연결 종료")


if __name__ == "__main__":
    main()
