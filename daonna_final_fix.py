"""
1. 줄노트(64333218): 썸네일 교체 + 옵션 2종 추가 (옐로우/핑크)
2. 투두리스트(64333221): 썸네일 교체
3. 팔찌(64333233): 썸네일 교체
"""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

THUMB_DIR = Path("/tmp/daonna_thumbs")

FIXES = [
    (64333218, "56845967"),   # 줄노트
    (64333221, "62991936"),   # 투두리스트
    (64333233, "61435320"),   # 팔찌
]


async def dismiss_dialogs(page):
    await page.evaluate("""
        () => {
            document.querySelectorAll('.pDialog .pDialogBtnOk, .pDialog button').forEach(btn => {
                if (btn.offsetParent !== null) btn.click();
            });
            document.querySelectorAll('.pDialog, .pDialogOverlay, .pOverlay').forEach(el => {
                el.style.display = 'none';
            });
        }
    """)
    await asyncio.sleep(0.5)


async def goto_edit(page, no):
    url = f"https://domeggook.com/main/mySell/register/my_sellInfoForm.php?mode=editItem&no={no}"
    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(2)
    await dismiss_dialogs(page)


async def save_page(page, no) -> bool:
    await dismiss_dialogs(page)
    await asyncio.sleep(0.5)
    await page.evaluate("""
        () => {
            window.confirm = () => true;
            if (window.module && module.submitController && module.submitController.submit) {
                module.submitController.submit();
            } else {
                const btn = document.querySelector('#lItemRegBtnSubmit button');
                if (btn) btn.click();
            }
        }
    """)
    await asyncio.sleep(3)
    final_url = page.url
    if "my_sellOptionForm" in final_url or "my_sellList" in final_url or "mode=DONE" in final_url:
        print(f"  ✅ 저장 완료", flush=True)
        if "my_sellOptionForm" in final_url:
            try:
                await page.evaluate("() => { const f = document.querySelector('form'); if(f) f.submit(); }")
                await asyncio.sleep(2)
            except Exception:
                pass
        return True
    print(f"  ⚠️ URL: {final_url[:80]}", flush=True)
    return False


async def fix_thumb(page, no, pid):
    """썸네일 교체"""
    thumb_path = THUMB_DIR / f"{pid}_thumb_new.jpg"
    if not thumb_path.exists():
        print(f"  ❌ 썸네일 파일 없음: {thumb_path}", flush=True)
        return False

    await goto_edit(page, no)

    try:
        file_input = page.locator('#lImageNormal, input[name="image0"]').first
        await file_input.set_input_files(str(thumb_path))
        await asyncio.sleep(2)
        print(f"  ✅ 썸네일 업로드: {thumb_path.name}", flush=True)
    except Exception as e:
        print(f"  ❌ 썸네일 업로드 실패: {e}", flush=True)
        return False

    return await save_page(page, no)


async def add_options_note(page, no):
    """줄노트 옵션 2종 추가: 옐로우 / 핑크"""
    await goto_edit(page, no)

    # 옵션 사용 체크박스 활성화
    try:
        chk = page.locator('#lItemOptUse')
        if not await chk.is_checked():
            await chk.check()
            await asyncio.sleep(0.5)
        print(f"  ✅ 옵션 사용 체크", flush=True)
    except Exception as e:
        print(f"  ⚠️ 옵션 체크박스 실패: {e}", flush=True)

    # 옵션 설정 버튼 클릭
    await page.evaluate("""
        () => {
            // 버튼을 강제로 보이게 하고 클릭
            const btn = document.getElementById('lBtnItemOpt');
            if (btn) {
                btn.style.display = '';
                btn.style.visibility = 'visible';
                btn.click();
            }
        }
    """)
    await asyncio.sleep(1.5)

    # 팝업/모달 확인
    modal_info = await page.evaluate("""
        () => {
            // 열린 팝업/모달 찾기
            const modals = [...document.querySelectorAll('.pDialog, .modal, [class*=popup], [class*=layer]')]
                .filter(el => el.offsetParent !== null)
                .map(el => ({tag: el.tagName, id: el.id, cls: el.className.slice(0,50)}));
            const inputs = [...document.querySelectorAll('input[type=text]')]
                .filter(el => el.offsetParent !== null)
                .map(el => ({id: el.id, name: el.name, ph: el.placeholder}))
                .slice(0,10);
            return {modals, inputs};
        }
    """)
    print(f"  모달: {modal_info['modals'][:3]}", flush=True)
    print(f"  입력필드: {modal_info['inputs'][:5]}", flush=True)

    # 옵션명 입력 필드 찾기
    opt_input_info = await page.evaluate("""
        () => {
            // 옵션 그룹명 입력 필드
            const nameInputs = [...document.querySelectorAll('#lOptNm, #lOptGroupNm, input[id*=OptNm], input[name*=optName], input[placeholder*=옵션명], input[placeholder*=옵션그룹]')]
                .filter(el => el.offsetParent !== null);
            return nameInputs.map(el => ({id: el.id, name: el.name, ph: el.placeholder}));
        }
    """)
    print(f"  옵션 입력필드: {opt_input_info}", flush=True)

    # setOptInp hidden field 직접 조작 방식으로 시도
    # 다온나/도매꾹의 옵션 형식 파악
    await page.evaluate("""
        () => {
            // setOptInp 현재 값 확인
            const el = document.getElementById('setOptInp');
            console.log('setOptInp:', el ? el.value : 'not found');
            // 옵션 관련 모든 input
            [...document.querySelectorAll('input')].forEach(i => {
                if(i.id.includes('pt') || i.name.includes('pt') || i.id.includes('Opt') || i.name.includes('opt')) {
                    console.log(i.id, i.name, i.type, i.value.slice(0,30));
                }
            });
        }
    """)

    logs = []
    page.on("console", lambda msg: logs.append(msg.text))
    await asyncio.sleep(0.5)

    # 페이지 소스에서 옵션 관련 JS 함수 확인
    js_funcs = await page.evaluate("""
        () => {
            const keys = Object.keys(window).filter(k => k.toLowerCase().includes('opt'));
            return keys.slice(0, 20);
        }
    """)
    print(f"  window 옵션 함수: {js_funcs}", flush=True)

    return True


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp("http://localhost:9223")
        ctx = browser.contexts[0]
        page = None
        for p in ctx.pages:
            if "domeggook" in p.url:
                page = p
                break
        if not page:
            page = ctx.pages[0]

        # 썸네일 교체 (3개)
        for no, pid in FIXES:
            print(f"\n[썸네일] SE{no} ← {pid}", flush=True)
            ok = await fix_thumb(page, no, pid)
            print(f"  결과: {'성공' if ok else '실패'}", flush=True)
            await asyncio.sleep(1)

        # 줄노트 옵션 구조 파악
        print(f"\n[옵션 구조 파악] SE64333218", flush=True)
        await add_options_note(page, 64333218)

        print("\n=== 완료 ===", flush=True)


asyncio.run(main())
