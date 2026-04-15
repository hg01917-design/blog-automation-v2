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

        # 모든 버튼/링크를 전부 출력 (onclick 포함)
        all_btns = await dg_page.evaluate("""
            () => [...document.querySelectorAll('a[onclick], button[onclick], input[type=button][onclick], input[type=submit]')]
                .map(el => ({
                    tag: el.tagName,
                    text: (el.textContent || el.value || el.alt || '').trim().slice(0,40),
                    onclick: (el.getAttribute('onclick') || '').slice(0,100),
                    id: el.id,
                    class: el.className.slice(0,40)
                }))
        """)
        print(f"onclick 있는 버튼 ({len(all_btns)}개):")
        for b in all_btns: print(f"  {b}")

        # chkRegister 함수 소스 확인
        fn_src = await dg_page.evaluate("""
            () => {
                if(typeof chkRegister === 'function') return chkRegister.toString().slice(0, 500);
                return 'chkRegister 없음';
            }
        """)
        print(f"\nchkRegister 함수:\n{fn_src}")

        # 페이지 하단 저장 버튼 영역 HTML 확인
        bottom_html = await dg_page.evaluate("""
            () => {
                // 폼 제일 마지막 부분
                const form = document.querySelector('form[name="reg"]') || document.querySelector('form');
                if(!form) return '폼 없음';
                return form.innerHTML.slice(-2000);
            }
        """)
        print(f"\n폼 하단 HTML:\n{bottom_html}")

asyncio.run(main())
