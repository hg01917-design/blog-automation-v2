"""
이미 등록된 다온나 상품 일괄 수정
- 썸네일: esmplus 원본 크롭 + 흰 배경 88% 배치
- 상세내용: esmplus 이미지 HTML 주입

실행:
  python daonna_fix_bot.py           # progress.json의 done 목록 전체
  python daonna_fix_bot.py 55384364  # 특정 도매꾹 원본ID만
"""
import asyncio, json, re, sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from daonna_upload_bot import (
    CDP_URL, THUMB_DIR, download_image, make_detail_html,
    make_seo_keywords, make_detail_html,
)

PROGRESS_FILE = Path("/tmp/daonna_upload_progress.json")
# 프로젝트 파일 우선 (_img_url 포함), 없으면 /tmp 버전
_prj = Path(__file__).parent / "daonna_compare.json"
_tmp = Path("/tmp/daonna_compare.json")
COMPARE_FILE = _prj if _prj.exists() else _tmp
ID_MAP_FILE  = Path(__file__).parent / "daonna_id_map.json"  # source_id → daonna_no


def load_product_map() -> dict:
    """도매꾹 원본ID → {name, img_url} 매핑"""
    result = {}
    if COMPARE_FILE.exists():
        d = json.loads(COMPARE_FILE.read_text(encoding="utf-8"))
        for p in d.get("missing_in_daonna", []):
            result[p["id"]] = p
    return result


def make_thumb(img_url: str, pid: str) -> Path | None:
    """esmplus URL → 흰 배경 760×760 썸네일 생성"""
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    tmp = THUMB_DIR / f"{pid}_fix_tmp.jpg"
    out = THUMB_DIR / f"{pid}_thumb_fix.jpg"
    if not download_image(img_url, tmp):
        return None
    try:
        img = Image.open(tmp).convert("RGB")
        w, h = img.size
        ratio = w / h if h else 0
        if ratio >= 0.65:
            side = min(w, h)
            left, top = (w - side) // 2, (h - side) // 2
            crop = img.crop((left, top, left + side, top + side))
        else:
            side = w
            crop = img.crop((0, 0, side, side))
        canvas = Image.new("RGB", (760, 760), (255, 255, 255))
        inner = int(760 * 0.88)
        resized = crop.resize((inner, inner), Image.LANCZOS)
        offset = (760 - inner) // 2
        canvas.paste(resized, (offset, offset))
        canvas.save(str(out), "JPEG", quality=92)
        return out
    except Exception as e:
        print(f"  ❌ 썸네일 생성 실패: {e}", flush=True)
        return None


async def dismiss_dialogs(page):
    await page.evaluate("""
        () => {
            document.querySelectorAll('.pDialog, .pDialogOverlay, .pOverlay').forEach(el => {
                el.style.display = 'none';
            });
            window.confirm = () => true;
        }
    """)
    await asyncio.sleep(0.3)


_SELL_LIST_CACHE: list | None = None  # 페이지 전체 rows 캐시


async def load_sell_list(page) -> list:
    """셀러센터 전체 상품 목록 수집 (캐시)"""
    global _SELL_LIST_CACHE
    if _SELL_LIST_CACHE is not None:
        return _SELL_LIST_CACHE

    rows = []
    page_no = 1
    while True:
        url = f"https://domeggook.com/main/mySell/register/my_sellList.php?pageNum={page_no}"
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(1.5)
        page_rows = await page.evaluate("""
            () => [...document.querySelectorAll('tr')].map(r => ({
                text: r.innerText?.replace(/\\s+/g, ' ') || '',
                link: (r.querySelector('a[href*="editItem"]') || {}).href || ''
            })).filter(r => r.link)
        """)
        if not page_rows:
            break
        rows.extend(page_rows)
        # 다음 페이지 있는지 확인
        has_next = await page.evaluate(f"""
            () => !!document.querySelector('a[href*="pageNum={page_no + 1}"]')
        """)
        if not has_next:
            break
        page_no += 1

    print(f"  [목록] 전체 {len(rows)}개 상품 로드", flush=True)
    _SELL_LIST_CACHE = rows
    return rows


def load_id_map() -> dict:
    """daonna_id_map.json — source_id → daonna_no 매핑 로드"""
    if ID_MAP_FILE.exists():
        try:
            return json.loads(ID_MAP_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


async def get_daonna_no(page, pid: str, name: str) -> str | None:
    """daonna_no 찾기: 매핑 파일 우선, 없으면 키워드 매칭"""
    # 1. 매핑 파일에서 직접 조회
    id_map = load_id_map()
    if pid in id_map:
        print(f"  [매핑] {pid} → {id_map[pid]} (파일)", flush=True)
        return id_map[pid]

    # 2. 셀러센터 목록에서 키워드 매칭
    rows = await load_sell_list(page)

    # 원본 이름에서 3글자 이상 토큰 추출 (짧은 토큰은 다중 매칭 오류 유발)
    tokens = [t for t in re.split(r'[\s\(\)\[\]/,×Xx]+', name) if len(t) >= 3]

    best_no, best_score = None, 0
    for r in rows:
        text = r["text"]
        score = sum(1 for t in tokens if t in text)
        if score > best_score:
            best_score = score
            m = re.search(r'no=(\d+)', r["link"])
            if m:
                best_no = m.group(1)

    # 최소 3개 토큰 매칭돼야 유효 (2개는 오탐 위험)
    if best_score >= 3:
        return best_no

    print(f"  ⚠️ 키워드 매칭 점수 낮음 ({best_score}개) — 건너뜀", flush=True)
    return None


async def fix_product(page, daonna_no: str, img_url: str, pid: str, name: str):
    """editItem에서 썸네일 + 상세내용 수정 후 저장"""
    edit_url = f"https://domeggook.com/main/mySell/register/my_sellInfoForm.php?mode=editItem&no={daonna_no}"
    await page.goto(edit_url, wait_until="domcontentloaded", timeout=20000)
    await asyncio.sleep(2)
    await dismiss_dialogs(page)

    fixed = []

    # 1. 썸네일
    thumb_path = make_thumb(img_url, pid)
    if thumb_path:
        try:
            fi = page.locator('#lImageNormal, input[name="image0"]').first
            await fi.set_input_files(str(thumb_path))
            await asyncio.sleep(2)
            fixed.append("썸네일")
            print(f"  ✅ 썸네일 업로드", flush=True)
        except Exception as e:
            print(f"  ❌ 썸네일 업로드 실패: {e}", flush=True)
    else:
        print(f"  ❌ 썸네일 생성 실패 → 건너뜀", flush=True)

    # 2. 상세내용
    desc = f'<center><img src="{img_url}" style="max-width:100%;display:block;" /></center>'
    desc_escaped = desc.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    detail_set = await page.evaluate(f"""
        () => {{
            const ta = document.querySelector('textarea[name="itemMemo[Item]"]');
            if (!ta) return 'NO_TEXTAREA';
            ta.value = `{desc_escaped}`;
            ta.dispatchEvent(new Event('change'));
            if (typeof lEditorPopupSubmit === 'function') {{
                lEditorPopupSubmit([`{desc_escaped}`, '', '', '']);
            }}
            window.itemMemoExist = true;
            return 'OK:' + ta.value.length;
        }}
    """)
    if "OK" in str(detail_set):
        fixed.append("상세내용")
        print(f"  ✅ 상세내용 설정 ({detail_set})", flush=True)
    else:
        print(f"  ⚠️ 상세내용 설정 실패: {detail_set}", flush=True)

    if not fixed:
        return False

    # 3. 저장
    await page.evaluate("""
        () => {
            window.confirm = () => true;
            window.itemMemoExist = true;
            if (window.module && module.submitController && module.submitController.submit) {
                module.submitController.submit();
            } else {
                const btn = document.querySelector('#lItemRegBtnSubmit button');
                if (btn) btn.click();
            }
        }
    """)
    await asyncio.sleep(4)

    # sellOptionForm 다시 나오면 바로 제출
    if "sellOptionForm" in page.url:
        await page.evaluate("""
            () => {
                window.confirm = () => true;
                const frm = document.getElementById('frmRegOption');
                if (frm) { chkRegister(frm); frm.submit(); }
            }
        """)
        await asyncio.sleep(3)

    print(f"  ✅ 저장 완료 ({', '.join(fixed)})", flush=True)
    return True


async def main():
    from playwright.async_api import async_playwright

    product_map = load_product_map()

    # 수정 대상 결정
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        target_pids = [sys.argv[1]]
    else:
        if PROGRESS_FILE.exists():
            prog = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            target_pids = prog.get("done", [])
        else:
            print("❌ progress.json 없음 — 대상 ID를 인자로 지정해줘", flush=True)
            return

    print(f"수정 대상: {len(target_pids)}개", flush=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = next((p for p in ctx.pages if "domeggook" in p.url), ctx.pages[0])

        success, fail = 0, 0
        for pid in target_pids:
            product = product_map.get(pid)
            if not product:
                print(f"\n[{pid}] compare.json에 없음 — 건너뜀", flush=True)
                continue

            name    = product.get("name", "")
            img_url = product.get("_img_url") or product.get("img_url", "")

            if not img_url:
                print(f"\n[{pid}] img_url 없음 — 건너뜀", flush=True)
                fail += 1
                continue

            print(f"\n[{pid}] {name[:45]}", flush=True)

            daonna_no = await get_daonna_no(page, pid, name)
            if not daonna_no:
                print(f"  ❌ daonna 번호 못 찾음", flush=True)
                fail += 1
                continue
            print(f"  daonna no: {daonna_no}", flush=True)

            ok = await fix_product(page, daonna_no, img_url, pid, name)
            if ok:
                success += 1
            else:
                fail += 1
            await asyncio.sleep(1)

    print(f"\n=== 완료 === 성공: {success} | 실패: {fail}")


asyncio.run(main())
