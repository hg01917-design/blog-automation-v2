"""
게이밍노트북 임시저장 글 이미지 교체 워커
1. Bing 내 창작물에서 게이밍노트북 이미지 4장 다운로드
2. goodisak 에디터에서 임시저장 글 불러오기
3. 기존 이미지 전체 삭제 후 H2 아래 이미지 삽입
4. 임시저장 후 스크린샷 + 텔레그램 보고
"""

import sys
import time
import subprocess
from pathlib import Path

sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')
from browser import connect_cdp, get_or_create_page

def log(msg):
    print(msg, flush=True)

def main():
    log("[워커] 게이밍노트북 이미지 교체 시작")

    # images 디렉토리 확보
    img_dir = Path('/Users/hana/Downloads/blog-automation-v2/images')
    img_dir.mkdir(exist_ok=True)

    pw, browser = connect_cdp(on_log=log)

    try:
        # ── 1단계: Bing 내 창작물에서 이미지 다운로드 ──────────────────────────
        log("[1단계] Bing 내 창작물 탭 열기")
        bing_page = get_or_create_page(
            browser,
            url_contains="bing.com/images/create",
            navigate_to="https://www.bing.com/images/create"
        )
        bing_page.wait_for_timeout(3000)

        # 내 창작물 탭 클릭 (다양한 셀렉터 시도)
        log("[1단계] 내 창작물 탭 클릭 시도")
        try:
            bing_page.get_by_text("내 창작물").first.click()
        except Exception:
            try:
                bing_page.get_by_text("My creations").first.click()
            except Exception:
                log("[1단계] 내 창작물 버튼 텍스트 못 찾음 — 탭 목록 확인")
                # 탭 목록 출력
                tabs = bing_page.query_selector_all('[role="tab"], .tab, .gi-tabs li')
                for t in tabs:
                    log(f"  탭: '{t.text_content()}'")
                # 그냥 계속 진행 (이미 내 창작물 페이지일 수 있음)

        bing_page.wait_for_timeout(3000)

        # 현재 URL 확인
        log(f"[1단계] 현재 URL: {bing_page.url}")

        # 현재 Bing 페이지가 생성 결과 페이지인지 확인
        # 이미지는 img.image-row-img.mimg 셀렉터로 직접 추출
        import urllib.request
        import re

        current_url = bing_page.url
        log(f"[1단계] 현재 Bing URL: {current_url}")

        # 내 창작물 페이지로 이동 (현재 페이지가 생성 결과 페이지면 그냥 사용)
        # img.mimg 추출
        img_data = bing_page.evaluate("""() => {
            const imgs = [...document.querySelectorAll('img.mimg, img.image-row-img')];
            const big = imgs.filter(img => {
                const r = img.getBoundingClientRect();
                return r.width > 80 && r.height > 80;
            });
            return big.map(img => ({
                src: img.src || img.getAttribute('src') || '',
                alt: img.alt || '',
            }));
        }""")

        log(f"[1단계] 큰 이미지 {len(img_data)}개 발견")
        for d in img_data:
            log(f"  alt='{d['alt'][:60]}' src='{d['src'][:80]}'")

        if not img_data:
            log("[1단계] 이미지 없음 — 스크린샷")
            ss_path = str(img_dir / 'bing_debug.png')
            bing_page.screenshot(path=ss_path)
            subprocess.run(['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
                            '--photo', ss_path, 'Bing 이미지 없음. 확인 필요'])
            return

        # URL 고화질 변환: w=270&h=270 → w=1024&h=1024
        # 원본 URL 예: https://th.bing.com/th/id/OIG2.xxx?w=270&h=270&c=6&r=0&o=5&pid=ImgGn
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        def to_hq_url(src):
            parsed = urlparse(src)
            params = parse_qs(parsed.query, keep_blank_values=True)
            # 크기만 변경
            params['w'] = ['1024']
            params['h'] = ['1024']
            params['c'] = ['7']
            params['r'] = ['0']
            params['o'] = ['5']
            # pid 유지 (없으면 ImgGn)
            if 'pid' not in params:
                params['pid'] = ['ImgGn']
            new_query = urlencode({k: v[0] for k, v in params.items()})
            return urlunparse(parsed._replace(query=new_query))

        saved = []
        for i, d in enumerate(img_data[:4], 1):
            src = d['src']
            if not src or not src.startswith('http'):
                log(f"  [{i}] src 없음 — 스킵")
                continue

            # 고화질 URL과 원본 URL 모두 시도
            urls_to_try = [to_hq_url(src), src]
            save_path = img_dir / f'gaming-correct-{i}.jpg'
            saved_ok = False

            for url in urls_to_try:
                log(f"  [{i}] 다운로드 시도: {url[:100]}")
                try:
                    req = urllib.request.Request(url, headers={
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Referer': 'https://www.bing.com/',
                        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                    })
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = resp.read()
                    save_path.write_bytes(data)
                    size = save_path.stat().st_size
                    log(f"  [{i}] 저장: {save_path} ({size//1024}KB)")
                    if size > 5 * 1024:
                        saved.append(str(save_path))
                        saved_ok = True
                        break
                    else:
                        log(f"  [{i}] 파일 너무 작음 ({size}B)")
                except Exception as e:
                    log(f"  [{i}] 오류: {e}")

            if not saved_ok:
                log(f"  [{i}] 모든 URL 실패 — 브라우저로 다운로드 시도")
                # 브라우저 컨텍스트로 이미지 요청 (쿠키/세션 포함)
                try:
                    img_response = bing_page.evaluate(f"""async () => {{
                        const resp = await fetch('{src}', {{credentials: 'include'}});
                        const buf = await resp.arrayBuffer();
                        return Array.from(new Uint8Array(buf));
                    }}""")
                    if img_response and len(img_response) > 5000:
                        save_path.write_bytes(bytes(img_response))
                        size = save_path.stat().st_size
                        log(f"  [{i}] 브라우저 fetch 저장: {size//1024}KB")
                        if size > 5 * 1024:
                            saved.append(str(save_path))
                except Exception as e:
                    log(f"  [{i}] 브라우저 fetch 실패: {e}")

        log(f"[1단계] 다운로드 완료: {len(saved)}개")
        for p in saved:
            size = Path(p).stat().st_size
            log(f"  - {p} ({size//1024}KB)")

        if not saved:
            log("[1단계] 다운로드된 이미지 없음 — 중단")
            bing_page.screenshot(path=str(img_dir / 'bing_fail.png'))
            subprocess.run(['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
                            '--photo', str(img_dir / 'bing_fail.png'),
                            'Bing 내 창작물 이미지 다운로드 실패. 수동 확인 필요'])
            return

        # ── 2단계: goodisak 에디터 접속 및 임시저장 글 불러오기 ─────────────────
        log("[2단계] goodisak 에디터 접속")
        tistory_page = get_or_create_page(
            browser,
            url_contains="goodisak.tistory.com/manage/newpost",
            navigate_to="https://goodisak.tistory.com/manage/newpost"
        )
        tistory_page.wait_for_timeout(3000)
        log(f"[2단계] 에디터 URL: {tistory_page.url}")

        # 현재 에디터에 게이밍 글이 이미 열려있는지 확인
        current_title = tistory_page.evaluate("""() => {
            const t = document.querySelector('[data-id="title"], #title, .title-input, input[name="title"]');
            return t ? t.value || t.textContent : '';
        }""")
        log(f"[2단계] 현재 에디터 제목: '{current_title[:60]}'")

        gaming_loaded = '게이밍' in current_title or 'gaming' in current_title.lower() or '노트북' in current_title

        # 임시저장 팝업이 열려있으면 먼저 닫기
        overlay_exists = tistory_page.evaluate("""() => !!document.querySelector('.ReactModal__Overlay')""")
        if overlay_exists:
            log("[2단계] 임시저장 팝업 감지 — 처리 중")
            if not gaming_loaded:
                # 팝업에서 게이밍 항목 JS 클릭
                clicked = tistory_page.evaluate("""() => {
                    const items = document.querySelectorAll('[class*="title"], li');
                    for (const item of items) {
                        const text = item.textContent || '';
                        if (text.includes('게이밍') || text.toLowerCase().includes('gaming') || text.includes('노트북')) {
                            item.click();
                            return text.trim().substring(0, 60);
                        }
                    }
                    return null;
                }""")
                if clicked:
                    log(f"[2단계] JS 클릭: '{clicked}'")
                    tistory_page.wait_for_timeout(3000)
                    gaming_loaded = True
                else:
                    # 취소 버튼 눌러서 팝업 닫기
                    tistory_page.evaluate("""() => {
                        const btns = [...document.querySelectorAll('button')];
                        const cancel = btns.find(b => b.textContent.includes('취소'));
                        if (cancel) cancel.click();
                    }""")
                    tistory_page.wait_for_timeout(1000)
            else:
                # 게이밍 글 이미 로드됨 — 취소로 팝업만 닫기
                tistory_page.evaluate("""() => {
                    const btns = [...document.querySelectorAll('button')];
                    const cancel = btns.find(b => b.textContent.includes('취소'));
                    if (cancel) cancel.click();
                }""")
                tistory_page.wait_for_timeout(1000)
                log("[2단계] 팝업 닫음 (게이밍 글 이미 로드됨)")

        if not gaming_loaded:
            # 임시저장 팝업 열기
            log("[2단계] 임시저장 팝업 열기")
            draft_btn_clicked = False
            for sel in ['a.count', '.btn-draft-count', '.draft-count']:
                try:
                    el = tistory_page.query_selector(sel)
                    if el:
                        el.evaluate('el => el.click()')
                        log(f"[2단계] 임시저장 버튼 JS 클릭: {sel}")
                        draft_btn_clicked = True
                        break
                except Exception:
                    pass

            if not draft_btn_clicked:
                log("[2단계] 임시저장 버튼 못 찾음 — 스크린샷")
                ss = str(img_dir / 'editor_debug.png')
                tistory_page.screenshot(path=ss)
                subprocess.run(['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
                                '--photo', ss, '임시저장 버튼 못 찾음 — 수동 확인 필요'])
                return

            tistory_page.wait_for_timeout(1500)

            # 팝업에서 게이밍노트북 항목 JS 클릭
            clicked = tistory_page.evaluate("""() => {
                const sels = ['.list-title', '.draft-title', '[class*="title"]', 'li'];
                for (const sel of sels) {
                    const items = document.querySelectorAll(sel);
                    for (const item of items) {
                        const text = item.textContent || '';
                        if (text.includes('게이밍') || text.toLowerCase().includes('gaming') || text.includes('노트북')) {
                            item.click();
                            return text.trim().substring(0, 60);
                        }
                    }
                }
                return null;
            }""")
            if clicked:
                log(f"[2단계] 게이밍 항목 클릭: '{clicked}'")
                tistory_page.wait_for_timeout(3000)
            else:
                log("[2단계] 게이밍 항목 못 찾음")
                ss = str(img_dir / 'draft_popup.png')
                tistory_page.screenshot(path=ss)
                subprocess.run(['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
                                '--photo', ss, '게이밍노트북 임시저장 항목 못 찾음. 수동 확인 필요'])
                return

        log("[2단계] 게이밍노트북 글 불러오기 완료")

        # 현재 에디터 H2 수 확인
        h2_count = tistory_page.evaluate("""() => {
            const ed = window.tinymce && (tinymce.get('content') || tinymce.activeEditor);
            if (!ed) return 0;
            return ed.getBody().querySelectorAll('h2').length;
        }""")
        log(f"[2단계] H2 수: {h2_count}")

        # ── 3단계: 기존 이미지 전체 삭제 ──────────────────────────────────────
        log("[3단계] 기존 이미지 전체 삭제")
        deleted = tistory_page.evaluate("""() => {
            const ed = window.tinymce && (tinymce.get('content') || tinymce.activeEditor);
            if (!ed) return 0;
            const imgs = ed.getBody().querySelectorAll('img');
            let count = 0;
            imgs.forEach(img => {
                const parent = img.closest('p,figure,div') || img.parentElement;
                if (parent && parent !== ed.getBody()) parent.remove();
                else img.remove();
                count++;
            });
            return count;
        }""")
        log(f"[3단계] 삭제된 이미지: {deleted}개")
        tistory_page.wait_for_timeout(1000)

        # ── 4단계: H2 아래 이미지 삽입 ───────────────────────────────────────
        log("[4단계] 이미지 삽입 시작")

        # poster.py의 _tistory_upload_image 임포트
        from poster import _tistory_upload_image

        # 삽입할 이미지 수 = min(saved, h2_count, 4) — 최소 1개는 삽입
        insert_count = max(1, min(len(saved), max(h2_count, 1), 4))
        log(f"[4단계] 삽입 예정: {insert_count}개")

        for i in range(insert_count):
            img_path = saved[i] if i < len(saved) else saved[-1]

            # H2 i번째 뒤로 커서 이동
            if h2_count > 0:
                moved = tistory_page.evaluate(f"""() => {{
                    const ed = window.tinymce && (tinymce.get('content') || tinymce.activeEditor);
                    if (!ed) return false;
                    const h2s = ed.getBody().querySelectorAll('h2');
                    if (!h2s[{i}]) return false;
                    const next = h2s[{i}].nextElementSibling;
                    if (next) ed.selection.setCursorLocation(next, 0);
                    else ed.selection.setCursorLocation(h2s[{i}].parentElement,
                             h2s[{i}].parentElement.childNodes.length);
                    return true;
                }}""")
                log(f"[4단계] H2[{i}] 뒤 커서 이동: {moved}")
            tistory_page.wait_for_timeout(300)

            success = _tistory_upload_image(tistory_page, img_path, on_log=log)
            log(f"[4단계] 이미지 {i+1} 삽입: {'성공' if success else '실패'}")
            tistory_page.wait_for_timeout(1000)

        # ── 5단계: 임시저장 + 스크린샷 + 텔레그램 ───────────────────────────────
        log("[5단계] 임시저장")
        tistory_page.keyboard.press('Control+s')
        tistory_page.wait_for_timeout(2000)

        ss_path = str(img_dir / 'editor_done.png')
        tistory_page.screenshot(path=ss_path)
        log(f"[5단계] 스크린샷 저장: {ss_path}")

        result = subprocess.run(
            ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
             '--photo', ss_path,
             f'게이밍노트북 이미지 {insert_count}장 삽입 완료 (Bing 내 창작물). 확인 후 발행해주세요.'],
            capture_output=True, text=True
        )
        log(f"[5단계] 텔레그램 발송: {result.returncode}")

        log("[워커] 모든 작업 완료")

    except Exception as e:
        log(f"[워커] 오류: {e}")
        import traceback
        traceback.print_exc()
        subprocess.run([
            'python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
            f'⚠️ 게이밍노트북 이미지 교체 오류\n{str(e)[:200]}'
        ])
    finally:
        pw.stop()
        log("[워커] Playwright 종료")

if __name__ == '__main__':
    main()
