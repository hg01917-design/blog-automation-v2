"""이미 등록된 다온나 상품 수정: 태그 교체 + 모델명없음 체크박스 + 썸네일 교체"""
import asyncio, re, sys, requests
from pathlib import Path
from PIL import Image
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')
from daonna_upload_bot import download_image, THUMB_DIR, make_seo_keywords

# 썸네일 교체 필요한 상품: (daonna_no, domeggook_product_id)
THUMB_FIX = {
    64333215: "58572259",
    64333218: "56845967",
    64333221: "62991936",
    64333233: "61435320",
}

# 수정 대상: (daonna_no, original_name)
# 3차 실행: 전체 10개 태그 재수정 (실구매자 검색어 기준)
TARGETS = [
    (64333198, "국산 노루지 35g 소 180X270(mm) 500매 베이킹 유산지 쿠키"),
    (64333200, "국산 노루지 35g 소소 135X135(mm) 1000매 베이킹 유산지"),
    (64333201, "초강접 택배 박스 취급주의 스티커 70 x 90mm 낱장 1000매"),
    (64333202, "발레 무용 팬던트 털뭉치 키링 가방 열쇠고리 2컬러"),
    (64333203, "O링 은색 스틸 도금 오링 100P 키링 열쇠고리 마감 부자재"),
    (64333207, "D고리 은색 도금 버클 50P 키링 부자재 회전 붕어고리"),
    (64333215, "랜덤 혼합색상 군번줄 구슬 체인 12cm DIY 버클 키링 부자재 100P"),
    (64333218, "표정 미니 줄노트 스프링 A7 사이즈 2컬러"),
    (64333221, "To Do List 투두 리스트 체크 보드 화이트 일일 플래너 메모"),
    (64333233, "파스텔 핑크 로즈 쿼츠 여성 패션 팔찌 복 행운 기원"),
]

# 55384364 (초강접 취급주의 스티커) → 상품목록에서 번호 찾기
FIND_55384364 = "초강접 택배 박스 취급주의 스티커 1000매"



async def dismiss_dialogs(page):
    """pDialog 팝업 모두 닫기"""
    await page.evaluate("""
        () => {
            // 확인 버튼 클릭
            document.querySelectorAll('.pDialog .pDialogBtnOk, .pDialog button').forEach(btn => {
                if (btn.offsetParent !== null) btn.click();
            });
            // 강제 숨기기
            document.querySelectorAll('.pDialog, .pDialogOverlay, .pOverlay').forEach(el => {
                el.style.display = 'none';
            });
        }
    """)
    await asyncio.sleep(0.5)


async def fix_product(page, no: int, orig_name: str):
    """단일 상품 수정: 태그 + 모델명없음 체크박스"""
    url = f"https://domeggook.com/main/mySell/register/my_sellInfoForm.php?mode=editItem&no={no}"
    print(f"\n[수정] SE{no} — {orig_name[:40]}", flush=True)
    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(2)
    # 페이지 로드 후 다이얼로그 닫기
    await dismiss_dialogs(page)

    # 1. 모델명없음 체크박스
    try:
        chk = page.locator('#lItemCodeChk')
        if not await chk.is_checked():
            await chk.check()
        print(f"  ✅ 모델명없음 체크", flush=True)
    except Exception as e:
        print(f"  ⚠️ 모델명없음 체크 실패: {e}", flush=True)

    # 2. 기존 태그 전체 삭제 후 새 태그 입력
    kws = make_seo_keywords(orig_name)
    kw_inputs = await page.evaluate("() => [...document.querySelectorAll('input.lKeywordTmp')].map((_, i) => i)")
    for i in range(len(kw_inputs)):
        try:
            loc = page.locator('input.lKeywordTmp').nth(i)
            await loc.click()
            await asyncio.sleep(0.1)
            # 기존 값 지우기
            await loc.triple_click()
            await loc.fill(kws[i] if i < len(kws) else "")
        except Exception:
            pass
    # hidden 필드 동기화
    await page.evaluate("""
        (kws) => {
            const hidden = document.getElementById('lKeyword') || document.querySelector('input[name="itemKeyword"]');
            if (hidden) { hidden.value = kws.join(','); hidden.dispatchEvent(new Event('change')); }
        }
    """, kws)
    print(f"  ✅ 태그: {kws}", flush=True)

    # 3. 썸네일 교체 (원본 이미지 사용된 경우만)
    pid = THUMB_FIX.get(no)
    if pid:
        print(f"  [썸네일] 상세이미지에서 교체 시도...", flush=True)
        # 도매꾹 상품 페이지에서 상세이미지 URL 수집
        dg_url = f"https://domeggook.com/main/item/itemView.php?no={pid}"
        await page.goto(dg_url, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        detail_urls = await page.evaluate("""
            () => {
                const el = document.getElementById('lInfoViewItemContents');
                if (!el) return [];
                const seen = new Set();
                return [...el.querySelectorAll('img')].map(img =>
                    img.getAttribute('data-src') || img.getAttribute('src') || ''
                ).filter(src => {
                    if (!src || src.startsWith('data:') || seen.has(src)) return false;
                    seen.add(src); return true;
                });
            }
        """)
        thumb_path = THUMB_DIR / f"{pid}_thumb.jpg"
        replaced = False
        for durl in detail_urls:
            try:
                fallback_path = THUMB_DIR / f"{pid}_detail_tmp.jpg"
                if not download_image(durl, fallback_path):
                    continue
                img = Image.open(fallback_path).convert("RGB")
                w, h = img.size
                ratio = w / h if h else 0
                if 0.7 <= ratio <= 1.5:
                    img.resize((760, 760), Image.LANCZOS).save(str(thumb_path), "JPEG", quality=92)
                    print(f"  [썸네일] 대체 이미지 저장: {durl[:60]}", flush=True)
                    replaced = True
                    break
            except Exception:
                continue
        if not replaced:
            print(f"  [썸네일] 대체 실패", flush=True)
            # 실패 시 원래 편집 페이지로 복귀
            await page.goto(f"https://domeggook.com/main/mySell/register/my_sellInfoForm.php?mode=editItem&no={no}", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await dismiss_dialogs(page)
        else:
            # 편집 페이지로 복귀 후 썸네일 업로드
            await page.goto(f"https://domeggook.com/main/mySell/register/my_sellInfoForm.php?mode=editItem&no={no}", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await dismiss_dialogs(page)
            try:
                file_input = page.locator('#lImageNormal, input[name="image0"]').first
                await file_input.set_input_files(str(thumb_path))
                await asyncio.sleep(2)
                print(f"  [썸네일] 업로드 완료", flush=True)
            except Exception as e:
                print(f"  [썸네일] 업로드 실패: {e}", flush=True)

    # 4. 저장 버튼 클릭
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
        # 판매기간 설정 페이지면 바로 제출
        if "my_sellOptionForm" in final_url:
            try:
                await page.evaluate("""
                    () => {
                        const f = document.querySelector('form');
                        if (f) f.submit();
                    }
                """)
                await asyncio.sleep(2)
            except Exception:
                pass
        return True
    else:
        print(f"  ⚠️ 저장 불확실 (URL: {final_url[:80]})", flush=True)
        return False


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

        # 55384364 번호 찾기
        print("55384364 다온나 번호 검색 중...", flush=True)
        await page.goto("https://domeggook.com/main/mySell/register/my_sellList.php", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        rows = await page.evaluate("""
            () => [...document.querySelectorAll('tr')].map(r => ({
                text: r.innerText?.slice(0,80) || '',
                link: (r.querySelector('a[href*="editItem"]') || {}).href || ''
            })).filter(r => r.link)
        """)
        extra_no = None
        for r in rows:
            if "취급주의" in r["text"] and "1000매" in r["text"] and "낱장" in r["text"]:
                m = re.search(r'no=(\d+)', r["link"])
                if m:
                    extra_no = int(m.group(1))
                    print(f"  55384364 → SE{extra_no} 발견", flush=True)
                    break

        targets = list(TARGETS)
        if extra_no:
            targets.insert(0, (extra_no, FIND_55384364))
        else:
            print("  55384364 번호 미발견 — 건너뜀", flush=True)

        success, fail = 0, 0
        for no, name in targets:
            ok = await fix_product(page, no, name)
            if ok:
                success += 1
            else:
                fail += 1
            await asyncio.sleep(1)

        print(f"\n=== 수정 완료 ===")
        print(f"  성공: {success}개 | 실패/불확실: {fail}개")

asyncio.run(main())
