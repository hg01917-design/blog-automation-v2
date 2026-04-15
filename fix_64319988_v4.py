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

        # --- 상품명 설정 ---
        await dg_page.click('input[name="itemTitle"]')
        await dg_page.evaluate("""
            () => {
                const el = document.querySelector('input[name="itemTitle"]');
                el.value = '판다 니트백 뜨개 미니크로스백 여성 캐릭터가방';
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }
        """)
        await asyncio.sleep(0.3)
        cur_title = await dg_page.locator('input[name="itemTitle"]').input_value()
        print(f"상품명 설정: {cur_title}")

        # --- 태그(키워드) 설정 ---
        # 먼저 태그 입력 구조 상세 파악
        kw_info = await dg_page.evaluate("""
            () => {
                const inputs = [...document.querySelectorAll('input.lKeywordTmp')];
                // module.keywordController 상태
                let ctrlInfo = 'N/A';
                try {
                    ctrlInfo = JSON.stringify(Object.keys(window.module?.keywordController || {}));
                } catch(e) {}
                return {
                    count: inputs.length,
                    values: inputs.map(el => el.value),
                    moduleKeywordCtrl: ctrlInfo
                };
            }
        """)
        print(f"키워드 현황: {kw_info}")

        tags = ['판다가방', '니트백', '뜨개가방', '캐릭터가방', '여성핸드백',
                '미니크로스백', '귀여운가방', '숄더백', '토트백', '캐릭터핸드백']

        for i, tag in enumerate(tags):
            if i >= kw_info['count']: break
            # 각 태그 input에 value 설정 + 이벤트 발생
            await dg_page.evaluate("""
                ([i, tag]) => {
                    const inputs = document.querySelectorAll('input.lKeywordTmp');
                    if(i >= inputs.length) return;
                    const el = inputs[i];
                    el.value = tag;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.dispatchEvent(new Event('blur', {bubbles: true}));
                }
            """, [i, tag])
            await asyncio.sleep(0.1)

        # 설정 후 확인
        set_tags = await dg_page.evaluate("() => [...document.querySelectorAll('input.lKeywordTmp')].map(el=>el.value)")
        print(f"태그 설정: {set_tags}")

        # keywordController validate 결과 확인
        kw_validate = await dg_page.evaluate("""
            () => {
                try {
                    if(window.module && window.module.keywordController) {
                        return {
                            validateResult: window.module.keywordController.validate(),
                            keys: Object.keys(window.module.keywordController)
                        };
                    }
                    return 'keywordController 없음';
                } catch(e) {
                    return 'error: ' + e.message;
                }
            }
        """)
        print(f"keywordController validate: {kw_validate}")

        # dialog 자동 수락
        dialogs = []
        def handle_dialog(d):
            print(f"  [DIALOG] type={d.type}, msg={d.message[:100]}")
            dialogs.append(d.message)
            asyncio.ensure_future(d.accept())
        dg_page.on("dialog", handle_dialog)

        # #lItemRegBtnSubmit 안의 button 클릭
        save_btn = dg_page.locator('#lItemRegBtnSubmit button')
        count = await save_btn.count()
        print(f"#lItemRegBtnSubmit button 개수: {count}")

        if count > 0:
            print("저장 버튼 클릭...")
            # scroll into view
            await save_btn.first.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            await save_btn.first.click()
        else:
            print("버튼 없음, chkRegister 직접 호출")
            await dg_page.evaluate("""
                () => {
                    window.confirm = () => true;
                    window.alert = () => {};
                    const form = document.querySelector('form[name="reg"]') || document.querySelector('form');
                    if(form && typeof chkRegister === 'function') {
                        if(chkRegister(form)) form.submit();
                    }
                }
            """)

        await asyncio.sleep(5)
        print(f"저장 후 URL: {dg_page.url}")
        print(f"dialog 메시지들: {dialogs}")

        # 에러 메시지
        err = await dg_page.evaluate("""
            () => [...document.querySelectorAll('.lErrMsg, .lAlert, [id*="Err"], [class*="error"]')]
                .map(el => el.textContent.trim()).filter(t => t).slice(0,5)
        """)
        if err:
            print(f"에러 메시지: {err}")

        # 저장 확인
        await dg_page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        await dg_page.evaluate("() => { const dlg=document.getElementById('lDialogSellReg'); if(dlg){dlg.querySelector('button')?.click();} }")
        await asyncio.sleep(1)

        saved_title = await dg_page.locator('input[name="itemTitle"]').input_value()
        saved_tags = await dg_page.evaluate("() => [...document.querySelectorAll('input.lKeywordTmp')].map(el=>el.value).filter(v=>v)")
        print(f"\n=== 저장 확인 ===")
        print(f"상품명: {saved_title}")
        print(f"태그({len(saved_tags)}개): {saved_tags}")

asyncio.run(main())
