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

        # 유의사항 닫기
        await dg_page.evaluate("() => { const dlg=document.getElementById('lDialogSellReg'); if(dlg){dlg.querySelector('button')?.click();} }")
        await asyncio.sleep(1)

        # 저장/등록 버튼 전체 파악
        btns = await dg_page.evaluate("""
            () => [...document.querySelectorAll('a, button, input[type=button], input[type=submit]')]
                .filter(el => {
                    const t = (el.textContent || el.value || '').trim();
                    const oc = el.getAttribute('onclick') || '';
                    return t.includes('등록') || t.includes('저장') || oc.includes('sellReg') || oc.includes('Save');
                })
                .map(el => ({
                    tag: el.tagName,
                    text: (el.textContent || el.value || '').trim().slice(0,30),
                    onclick: (el.getAttribute('onclick') || '').slice(0,60),
                    id: el.id,
                    class: el.className.slice(0,30)
                }))
        """)
        print("저장 버튼 목록:")
        for b in btns: print(f"  {b}")

        # 상품명 설정
        await dg_page.click('input[name="itemTitle"]')
        await dg_page.fill('input[name="itemTitle"]', '판다 니트백 뜨개 미니크로스백 여성 캐릭터가방')

        # 태그 10개 설정
        tags = ['판다가방', '니트백', '뜨개가방', '캐릭터가방', '여성핸드백',
                '미니크로스백', '귀여운가방', '숄더백', '토트백', '캐릭터핸드백']
        kw_inputs = dg_page.locator('input.lKeywordTmp')
        kw_count = await kw_inputs.count()
        print(f"태그 입력 필드 수: {kw_count}")
        for i, tag in enumerate(tags):
            if i >= kw_count: break
            loc = kw_inputs.nth(i)
            await loc.click()
            await loc.fill('')
            await loc.fill(tag)

        # dialog 자동 수락 설정
        dg_page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        # '상품등록' 버튼 = class lBtnNavy 인 버튼이 실제 저장 버튼
        save_btn = dg_page.locator('button.lBtnNavy').first
        count = await save_btn.count()
        print(f"lBtnNavy(상품등록) 버튼 개수: {count}")

        if count > 0:
            print("상품등록 버튼 클릭")
            await save_btn.click()
        else:
            # fallback: JS로 전역 함수 호출
            print("버튼 못찾음 — JS 전역함수 시도")
            await dg_page.evaluate("""
                () => {
                    window.confirm = () => true;
                    window.alert = () => {};
                    if(typeof sellReg === 'function') { sellReg(); }
                    else if(typeof doSellReg === 'function') { doSellReg(); }
                    else {
                        const f = document.querySelector('form');
                        if(f) f.submit();
                    }
                }
            """)

        await asyncio.sleep(5)
        print("저장 후 URL:", dg_page.url)

        # 확인 — 다시 수정 페이지 열어서 저장됐는지 확인
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
