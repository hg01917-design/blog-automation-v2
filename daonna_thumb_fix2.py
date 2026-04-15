"""
썸네일 재교체 + 줄노트 옵션 추가
- 64333218 줄노트: 썸네일 교체 + 옵션 3종 추가
- 64333221 투두리스트: 썸네일 교체
- 64333233 팔찌: 썸네일 교체
"""
import asyncio, re, sys, requests
from pathlib import Path
from PIL import Image
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')
from daonna_upload_bot import download_image, THUMB_DIR

# daonna번호 → 도매꾹 원본상품번호
FIX_THUMBS = {
    64333218: "56845967",   # 줄노트
    64333221: "62991936",   # 투두리스트
    64333233: "61435320",   # 팔찌
}

# 줄노트 옵션 (56845967 상품의 실제 옵션)
NOTE_OPTIONS = ["핑크 줄무늬 표정", "블루 체크 표정", "스마일 레인보우"]


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


async def get_best_thumb_from_detail(page, pid: str) -> Path | None:
    """도매꾹 상세페이지에서 정방형에 가까운 이미지 찾아 760x760 저장"""
    dg_url = f"https://domeggook.com/main/item/itemView.php?no={pid}"
    await page.goto(dg_url, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    # 상세 콘텐츠 내 모든 img 태그 URL 수집
    img_urls = await page.evaluate("""
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
    print(f"  상세 이미지 {len(img_urls)}개 발견", flush=True)

    thumb_path = THUMB_DIR / f"{pid}_thumb_new.jpg"
    for url in img_urls:
        try:
            tmp = THUMB_DIR / f"{pid}_tmp_check.jpg"
            if not download_image(url, tmp):
                continue
            img = Image.open(tmp).convert("RGB")
            w, h = img.size
            ratio = w / h if h else 0
            print(f"    {url[:60]} → {w}x{h} ratio={ratio:.2f}", flush=True)
            if 0.65 <= ratio <= 1.55:
                img.resize((760, 760), Image.LANCZOS).save(str(thumb_path), "JPEG", quality=92)
                print(f"  ✅ 정방형 이미지 발견 저장: {url[:60]}", flush=True)
                return thumb_path
        except Exception as e:
            print(f"    오류: {e}", flush=True)
            continue

    # 정방형 없으면 첫 이미지 중앙 크롭 (단, 원본 이미지가 아닌 상세 이미지 기준)
    print(f"  ⚠️ 정방형 없음 → 첫 이미지 중앙 크롭 시도", flush=True)
    for url in img_urls:
        try:
            tmp = THUMB_DIR / f"{pid}_tmp_check.jpg"
            if not download_image(url, tmp):
                continue
            img = Image.open(tmp).convert("RGB")
            w, h = img.size
            # 첫 번째 이미지 (가장 큰 것으로 상정) 중앙 크롭
            if w >= 400 and h >= 400:
                side = min(w, h)
                left = (w - side) // 2
                top = (h - side) // 2
                cropped = img.crop((left, top, left + side, top + side))
                cropped.resize((760, 760), Image.LANCZOS).save(str(thumb_path), "JPEG", quality=92)
                print(f"  ✅ 중앙 크롭 저장: {url[:60]}", flush=True)
                return thumb_path
        except Exception:
            continue

    return None


async def upload_thumb(page, daonna_no: int, thumb_path: Path) -> bool:
    """편집 페이지에서 썸네일 업로드"""
    url = f"https://domeggook.com/main/mySell/register/my_sellInfoForm.php?mode=editItem&no={daonna_no}"
    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(2)
    await dismiss_dialogs(page)

    try:
        file_input = page.locator('#lImageNormal, input[name="image0"]').first
        await file_input.set_input_files(str(thumb_path))
        await asyncio.sleep(2)
        print(f"  ✅ 썸네일 업로드 완료", flush=True)
        return True
    except Exception as e:
        print(f"  ❌ 썸네일 업로드 실패: {e}", flush=True)
        return False


async def add_note_options(page, daonna_no: int):
    """줄노트 옵션 3종 추가"""
    url = f"https://domeggook.com/main/mySell/register/my_sellInfoForm.php?mode=editItem&no={daonna_no}"
    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(2)
    await dismiss_dialogs(page)

    # 옵션 탭으로 이동 or 옵션 추가 버튼
    # 먼저 옵션 관련 요소 확인
    opt_info = await page.evaluate("""
        () => {
            // 옵션 탭/섹션 찾기
            const optTab = document.querySelector('#lOptionTab, [href*="option"], .itemOptionArea');
            const optAdd = document.querySelector('#lOptionAddBtn, .itemOptAddBtn, [id*="optionAdd"]');
            const optSec = document.querySelector('#lItemOptionArea, .optionArea');
            return {
                hasTab: !!optTab,
                hasAddBtn: !!optAdd,
                hasSec: !!optSec,
                addBtnId: optAdd ? optAdd.id : '',
                secId: optSec ? optSec.id : '',
                pageTitle: document.title,
            };
        }
    """)
    print(f"  옵션 정보: {opt_info}", flush=True)

    # 옵션 섹션 HTML 확인
    opt_html = await page.evaluate("""
        () => {
            const el = document.getElementById('lItemOptionArea') || document.querySelector('.optionArea') || document.querySelector('[class*="option"]');
            return el ? el.outerHTML.slice(0,500) : 'NOT FOUND';
        }
    """)
    print(f"  옵션 HTML: {opt_html[:200]}", flush=True)


async def save_and_confirm(page, daonna_no: int) -> bool:
    """저장 버튼 클릭 후 확인"""
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
    else:
        print(f"  ⚠️ 저장 불확실 URL: {final_url[:80]}", flush=True)
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

        # 1. 썸네일 교체
        for daonna_no, pid in FIX_THUMBS.items():
            print(f"\n{'='*50}", flush=True)
            print(f"[썸네일] daonna SE{daonna_no} ← 도매꾹 {pid}", flush=True)

            thumb_path = await get_best_thumb_from_detail(page, pid)
            if not thumb_path:
                print(f"  ❌ 썸네일 이미지 찾기 실패", flush=True)
                continue

            ok = await upload_thumb(page, daonna_no, thumb_path)
            if ok:
                ok2 = await save_and_confirm(page, daonna_no)

        # 2. 줄노트 옵션 확인
        print(f"\n{'='*50}", flush=True)
        print(f"[옵션 확인] 줄노트 SE64333218", flush=True)
        await add_note_options(page, 64333218)

        print("\n=== 완료 ===", flush=True)


asyncio.run(main())
