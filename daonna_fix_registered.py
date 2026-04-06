"""이미 등록된 다온나 상품 수정: 태그 교체 + 모델명없음 체크박스 + 썸네일 교체"""
import asyncio, re, sys, requests
from pathlib import Path
from PIL import Image
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')
from daonna_upload_bot import download_image, THUMB_DIR

# 썸네일 교체 필요한 상품: (daonna_no, domeggook_product_id)
THUMB_FIX = {
    64333215: "58572259",
    64333218: "56845967",
    64333221: "62991936",
    64333233: "61435320",
}

# 수정 대상: (daonna_no, original_name)
# 2차 실행: 64333215 태그 재수정 + 썸네일 4개 교체
TARGETS = [
    (64333215, "랜덤 혼합색상 군번줄 구슬 체인 12cm DIY 버클 키링 부자재 100P"),
    (64333218, "표정 미니 줄노트 스프링 A7 사이즈 2컬러"),
    (64333221, "To Do List 투두 리스트 체크 보드 화이트 일일 플래너 메모"),
    (64333233, "파스텔 핑크 로즈 쿼츠 여성 패션 팔찌 복 행운 기원"),
]

# 55384364 (초강접 취급주의 스티커) → 상품목록에서 번호 찾기
FIND_55384364 = "초강접 택배 박스 취급주의 스티커 1000매"


def make_seo_keywords(original: str) -> list:
    """실제 검색량 높은 확장 키워드 10개 반환 (daonna_upload_bot.py 와 동일)"""
    n = original.lower()

    if any(k in n for k in ["취급주의", "파손주의", "깨짐주의"]):
        return ["취급주의스티커", "파손주의스티커", "깨짐주의스티커", "배송라벨",
                "택배스티커", "택배라벨", "경고라벨", "포장스티커", "쇼핑몰스티커", "택배경고스티커"]

    if any(k in n for k in ["노루지", "유산지"]):
        return ["베이킹유산지", "오븐유산지", "쿠키유산지", "베이킹페이퍼",
                "오일페이퍼", "쿠킹페이퍼", "유산지종이", "제빵유산지", "노루지", "오븐시트지"]

    if any(k in n for k in ["오링", "o링"]):
        return ["오링", "O링", "키링부자재", "DIY키링재료", "열쇠고리부자재",
                "핸드메이드부자재", "키링만들기", "DIY부자재", "액세서리부자재", "키링재료"]

    if any(k in n for k in ["구슬체인", "군번줄"]):
        return ["군번줄체인", "구슬체인", "키링DIY", "목걸이체인", "체인부자재",
                "핸드메이드체인", "DIY체인", "액세서리체인", "볼체인", "키링재료"]

    if any(k in n for k in ["d고리", "디고리", "버클"]):
        return ["D고리", "버클고리", "키링부자재", "가방고리", "카라비너",
                "스냅훅", "열쇠고리부자재", "DIY부자재", "핸드메이드재료", "가방부자재"]

    if any(k in n for k in ["줄노트", "스프링노트"]) or ("노트" in n and "a7" in n):
        return ["미니노트", "포켓노트", "스프링노트", "A7노트", "소형수첩",
                "휴대용노트", "메모수첩", "학생용노트", "줄노트", "휴대용수첩"]

    if any(k in n for k in ["투두", "to do", "체크보드", "플래너"]):
        return ["투두리스트", "데일리플래너", "체크리스트", "할일메모", "플래너노트",
                "일정관리", "스케줄러", "메모보드", "업무플래너", "공부플래너"]

    if any(k in n for k in ["팔찌"]):
        return ["팔찌", "여성팔찌", "패션팔찌", "행운팔찌", "천연석팔찌",
                "데일리팔찌", "비즈팔찌", "레이어드팔찌", "구슬팔찌", "실버팔찌"]

    if any(k in n for k in ["키링", "열쇠고리"]) and any(k in n for k in ["털", "폼폼", "인형"]):
        return ["털키링", "폼폼키링", "인형키링", "가방키링", "캐릭터키링",
                "가방참", "가방꾸미기", "귀여운키링", "포인트키링", "액세서리키링"]

    return ["소품", "생활소품", "인테리어소품", "선물용품", "데일리소품",
            "귀여운소품", "여성소품", "홈데코", "선물세트", "미니소품"]


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
