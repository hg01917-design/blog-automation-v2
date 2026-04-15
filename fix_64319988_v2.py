import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp("http://localhost:9223")
        ctx = browser.contexts[0]
        dg_page = next((p for p in ctx.pages if 'domeggook.com' in p.url), ctx.pages[0])

        edit_url = "https://domeggook.com/main/mySell/register/my_sellInfoForm.php?mode=editItem&no=64319988"
        await dg_page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # 유의사항 팝업 닫기
        await dg_page.evaluate("() => { const dlg=document.getElementById('lDialogSellReg'); if(dlg){dlg.querySelector('button')?.click();} }")
        await asyncio.sleep(1)

        # 현재 상품명 확인
        cur_title = await dg_page.locator('input[name="itemTitle"]').input_value()
        print(f"현재 상품명: {cur_title}")

        # JS 전역 함수/이벤트 리스너 파악
        js_info = await dg_page.evaluate("""
            () => {
                // 버튼의 이벤트 리스너 정보 (jQuery 포함)
                const btn = document.querySelector('button.lBtnNavy');
                if(!btn) return {error: '버튼 없음'};

                // jQuery 이벤트
                let jqEvents = null;
                if(window.jQuery) {
                    const data = jQuery._data ? jQuery._data(btn, 'events') : null;
                    jqEvents = data ? Object.keys(data) : 'no jQuery._data';
                }

                // 사용 가능한 전역 함수
                const fns = Object.keys(window).filter(k => typeof window[k] === 'function' &&
                    (k.toLowerCase().includes('sell') || k.toLowerCase().includes('reg') ||
                     k.toLowerCase().includes('save') || k.toLowerCase().includes('submit')));

                return {
                    btnOuterHTML: btn.outerHTML,
                    jqEvents,
                    globalFns: fns.slice(0, 30)
                };
            }
        """)
        print("JS 정보:", js_info)

        # 상품명 설정 (triple click → type 방식)
        title_input = dg_page.locator('input[name="itemTitle"]')
        await title_input.triple_click()
        await title_input.type('판다 니트백 뜨개 미니크로스백 여성 캐릭터가방', delay=30)
        await asyncio.sleep(0.5)
        new_title = await title_input.input_value()
        print(f"입력 후 상품명: {new_title}")

        # 태그 10개 설정
        tags = ['판다가방', '니트백', '뜨개가방', '캐릭터가방', '여성핸드백',
                '미니크로스백', '귀여운가방', '숄더백', '토트백', '캐릭터핸드백']
        kw_inputs = dg_page.locator('input.lKeywordTmp')
        kw_count = await kw_inputs.count()
        print(f"태그 입력 필드 수: {kw_count}")
        for i, tag in enumerate(tags):
            if i >= kw_count: break
            loc = kw_inputs.nth(i)
            await loc.triple_click()
            await loc.type(tag, delay=20)
        await asyncio.sleep(0.5)

        # 저장 전 입력값 최종 확인
        check_title = await title_input.input_value()
        check_tags = await dg_page.evaluate("() => [...document.querySelectorAll('input.lKeywordTmp')].map(el=>el.value)")
        print(f"저장 전 상품명: {check_title}")
        print(f"저장 전 태그: {check_tags}")

        # dialog 자동 수락
        dialogs = []
        def handle_dialog(d):
            print(f"  [dialog] type={d.type}, msg={d.message}")
            dialogs.append(d.message)
            asyncio.ensure_future(d.accept())
        dg_page.on("dialog", handle_dialog)

        # 버튼 클릭 전 response 모니터링
        responses = []
        def handle_response(r):
            if 'sellInfoForm' in r.url or 'sell' in r.url.lower():
                responses.append({'url': r.url, 'status': r.status})
        dg_page.on("response", handle_response)

        # 상품등록(lBtnNavy) 버튼 클릭
        save_btn = dg_page.locator('button.lBtnNavy').first
        print("상품등록 버튼 클릭...")
        await save_btn.click()
        await asyncio.sleep(5)

        print(f"저장 후 URL: {dg_page.url}")
        print(f"dialog 메시지: {dialogs}")
        print(f"응답 URLs: {responses}")

        # 에러 메시지 확인
        err_msgs = await dg_page.evaluate("""
            () => {
                const errs = [...document.querySelectorAll('.lErrMsg, .error, .alert, [class*="err"]')]
                    .map(el => el.textContent.trim()).filter(t => t);
                return errs;
            }
        """)
        print(f"에러 메시지: {err_msgs}")

        # 현재 페이지 상태의 상품명 (변경됐는지)
        try:
            cur = await dg_page.locator('input[name="itemTitle"]').input_value()
            print(f"클릭 후 페이지 상품명: {cur}")
        except:
            print("상품명 input 없음 (다른 페이지로 이동됨)")

asyncio.run(main())
