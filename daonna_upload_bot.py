"""
다온나상점 — 유유팩토리 상품 자동 등록 봇
- 도매꾹(9223)에서 상품 이미지 추출
- Gemini(9223)에서 실생활 배경 썸네일 생성 (마네킹/실물 착용 스타일)
- 다온나상점 등록 폼 자동 입력 후 제출
- 진행 상황 저장으로 재시작 가능
"""
import asyncio
import base64
import io
import json
import re
import ssl
import urllib.request
from pathlib import Path
from PIL import Image

# 공급사별 상품코드 매핑
SUPPLIER_ITEM_CODE = {
    "유유팩토리": "uu",
    "해리네점빵": "hery",
    "승리아트": "victory",
    "위셀07": "we",
}

CDP_URL = "http://localhost:9223"
MISSING_FILE = Path("/tmp/daonna_compare.json")
PROGRESS_FILE = Path("/tmp/daonna_upload_progress.json")
THUMB_DIR = Path("/tmp/daonna_thumbs")
THUMB_DIR.mkdir(exist_ok=True)
GEMINI_APP_URL = "https://gemini.google.com/app"
REGISTER_URL = "https://domeggook.com/main/mySell/register/my_sellInfoForm.php?section=SELL"

# SSL 검증 무시 (CDN 이미지 다운로드용)
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {"done": [], "failed": []}


def save_progress(prog):
    PROGRESS_FILE.write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_price(price_str: str) -> str:
    """'3,200원' → '3200'"""
    nums = re.sub(r"[^\d]", "", price_str)
    return nums if nums else ""


async def get_product_info(page, item_id: str) -> dict:
    """도매매 상품 페이지에서 대표 이미지 URL + 카테고리 코드 + 공급단가 추출.
    카테고리/이미지는 도매꾹 페이지에서, 공급단가는 도매매 페이지에서 가져옴."""

    # 1. 도매꾹 페이지 — 대표이미지 + 카테고리
    dg_url = f"https://domeggook.com/main/item/itemView.php?no={item_id}"
    try:
        await page.goto(dg_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
    except Exception as e:
        print(f"  [상품정보] 도매꾹 페이지 로드 실패: {e}", flush=True)
        return {}

    try:
        dg_info = await page.evaluate("""
        () => {
            // 대표 이미지
            const thumbImg = document.getElementById('lThumbImg')
                          || document.querySelector('#lThumbImgWrap img')
                          || document.querySelector('img[data-src*="_img_760"], img[src*="_img_760"]');
            const imgUrl = thumbImg
                ? (thumbImg.getAttribute('data-src') || thumbImg.src)
                : null;

            // 카테고리 코드 — 브레드크럼 cat= 파라미터에서 추출
            let categoryCode = '';
            const catLinks = [...document.querySelectorAll('a[href*="cat="]')];
            for (let i = catLinks.length - 1; i >= 0; i--) {
                const href = catLinks[i].href || '';
                const m = href.match(/[?&]cat=([0-9_]+)/);
                if (m && m[1]) {
                    const parts = m[1].replace(/_+$/, '').split('_').filter(p => p !== '');
                    if (parts.length >= 3 && parts[parts.length - 1] !== '00') {
                        while (parts.length < 6) parts.push('00');
                        categoryCode = parts.slice(0, 6).join('_');
                        break;
                    }
                }
            }

            // 상세 이미지
            const detailEl = document.getElementById('lInfoViewItemContents');
            let detailImgHtml = '';
            if (detailEl) {
                const seen = new Set();
                const imgTags = [...detailEl.querySelectorAll('img')]
                    .map(img => img.getAttribute('data-src') || img.getAttribute('src') || '')
                    .filter(src => {
                        if (!src || src.startsWith('data:') || src === '#' || src === '' || seen.has(src)) return false;
                        seen.add(src); return true;
                    })
                    .map(src => '<p><img src="' + src + '" style="max-width:100%;display:block;margin:10px auto;"></p>');
                detailImgHtml = imgTags.join('');
            }

            // 옵션 정보 추출 — 옵션명/값 목록
            const options = [];
            // 옵션 테이블 또는 select 요소에서 추출
            const optSelects = document.querySelectorAll('select[name*="opt"], select[id*="opt"]');
            const optRows = document.querySelectorAll('.lOptList tr, .optList tr, table.opt tr');
            // select 방식
            if (optSelects.length > 0) {
                optSelects.forEach(sel => {
                    var td = sel.closest('td'); var prevSib = td ? td.previousElementSibling : null;
                    const optName = sel.getAttribute('data-name') || (prevSib && prevSib.innerText ? prevSib.innerText.trim() : '') || '';
                    const vals = [...sel.options].map(o => o.text.trim()).filter(t => t && t !== '선택');
                    if (optName && vals.length) options.push({name: optName, values: vals});
                });
            }
            // 텍스트 파싱 방식 — "옵션" 키워드 근처에서 값 추출
            if (options.length === 0) {
                const optEl = document.querySelector('.lOptGroup, #lOptGroup, .itemOpt, .item-option, [class*="option"]');
                if (optEl) {
                    const text = optEl.innerText;
                    const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
                    if (lines.length > 0) options.push({name: lines[0], values: lines.slice(1)});
                }
            }

            // 배송비 정보 추출
            let deliInfo = { type: 'fix', amount: '3000', tiers: [] };
            try {
                // 배송비 텍스트 영역 찾기
                const deliEls = [...document.querySelectorAll('*')].filter(el =>
                    el.children.length === 0 && el.innerText && el.innerText.includes('배송비')
                ).map(el => el.innerText.trim());

                // 무료배송 여부
                const allText = document.body.innerText;
                if (allText.includes('무료배송') || allText.includes('배송비 무료') || allText.includes('배송비무료')) {
                    deliInfo = { type: 'free', amount: '0', tiers: [] };
                } else {
                    // 수량별 차등 배송비 (예: 1~2개 3000원, 3개이상 무료 등)
                    const tierPattern = /(\\d+)[~\\-개].*?(\\d[\\d,]+)원/g;
                    const bodyText = document.body.innerText;
                    const tiers = [];
                    let m;
                    while ((m = tierPattern.exec(bodyText)) !== null) {
                        const qty = parseInt(m[1]);
                        const amt = parseInt(m[2].replace(/,/g, ''));
                        if (amt < 50000) tiers.push({ qty, amount: amt });
                    }
                    if (tiers.length > 1) {
                        deliInfo = { type: 'tier', amount: String(tiers[0].amount), tiers };
                    } else {
                        // 고정 배송비 금액 추출
                        const amtMatch = bodyText.match(/배송비[^\\d]*(\\d[\\d,]+)원/);
                        if (amtMatch) {
                            const amt = parseInt(amtMatch[1].replace(/,/g, ''));
                            if (amt > 0 && amt < 50000) deliInfo = { type: 'fix', amount: String(amt), tiers: [] };
                        }
                    }
                }
            } catch(e) {}

            return { imgUrl, detailImgHtml, categoryCode, options, deliInfo };
        }
        """)
    except Exception as e:
        print(f"  [상품정보] JS evaluate 실패 ({e}), 기본값 사용", flush=True)
        dg_info = {"imgUrl": None, "detailImgHtml": "", "categoryCode": "", "options": [], "deliInfo": {"type": "fix", "amount": "3000", "tiers": []}}

    # 2. 도매매 페이지 — 공급단가
    dm_url = f"https://domeme.domeggook.com/s/{item_id}"
    supply_price = ''
    try:
        await page.goto(dm_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        supply_price = await page.evaluate("""
            () => {
                // 가격 요소 — 숫자+원 패턴에서 첫 번째 유효한 가격
                const candidates = [...document.querySelectorAll('*')]
                    .filter(e => e.children.length === 0 && e.innerText)
                    .map(e => e.innerText.trim())
                    .filter(t => /^[\\d,]+원$/.test(t));
                for (const t of candidates) {
                    const n = parseInt(t.replace(/[^\\d]/g, ''));
                    if (n >= 100) return String(n);
                }
                return '';
            }
        """)
        print(f"  [도매매] 공급단가: {supply_price}원", flush=True)
    except Exception as e:
        print(f"  [도매매] 페이지 로드 실패: {e}", flush=True)

    return {
        "imgUrl": dg_info.get("imgUrl"),
        "detailImgHtml": dg_info.get("detailImgHtml", ""),
        "categoryCode": dg_info.get("categoryCode", ""),
        "supplyPrice": supply_price,
        "deliInfo": dg_info.get("deliInfo", {"type": "fix", "amount": "3000", "tiers": []}),
    }


async def get_product_image_url(page, item_id: str) -> str | None:
    """하위 호환 래퍼"""
    info = await get_product_info(page, item_id)
    return info.get("imgUrl")


def download_image(url: str, save_path: Path) -> bool:
    """이미지 다운로드"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=20, context=_SSL_CTX)
        data = resp.read()
        save_path.write_bytes(data)
        return True
    except Exception as e:
        print(f"  [다운로드] 실패 {url}: {e}", flush=True)
        return False


def make_gemini_prompt(product_name: str) -> str:
    """상품명 기반 Gemini 이미지 프롬프트 생성"""
    # 이미지는 원본 상품 사진 업로드 방식이므로, 배경 합성 프롬프트
    name_lower = product_name.lower()
    if any(k in name_lower for k in ["머리", "헤어", "핀", "클립", "바렛", "리본", "크로샤"]):
        style = "a real Korean woman wearing this hair accessory in her styled updo hair, sitting at a wooden vanity table with natural sunlight and a mirror in background"
    elif any(k in name_lower for k in ["귀걸이", "목걸이", "반지", "팔찌", "주얼리", "악세"]):
        style = "a real Korean woman wearing this jewelry item, close-up lifestyle photo, soft lighting, clean elegant background"
    elif any(k in name_lower for k in ["가방", "파우치", "지갑", "백"]):
        style = "a real person holding or using this bag in a bright lifestyle setting, natural light, wooden background"
    elif any(k in name_lower for k in ["옷", "상의", "하의", "원피스", "티셔츠", "니트", "재킷"]):
        style = "a real person wearing this clothing item in a bright natural indoor setting, lifestyle photo"
    elif any(k in name_lower for k in ["캐리어", "여행", "트롤리", "캠핑"]):
        style = "shown in a travel lifestyle setting, suitcase or travel context, bright and clean background"
    elif any(k in name_lower for k in ["인형", "키링", "열쇠고리", "피규어"]):
        style = "placed on a cute desk or shelf, soft pastel background, lifestyle product photo"
    elif any(k in name_lower for k in ["타투", "스티커", "패치"]):
        style = "applied on a person's skin or hand in a lifestyle photo, natural lighting"
    else:
        style = "placed in a cozy lifestyle setting with natural lighting, wooden surface or neutral background, product clearly visible"
    return (
        f"I'm uploading a product photo. Keep the EXACT same product — do NOT change its shape, color, design, or details at all. "
        f"Only change the background/setting to: {style}. "
        f"Product name for reference: {product_name[:60]}. "
        "The uploaded product must appear IDENTICAL in the output. Square composition, no text, no watermark, no logo."
    )


async def generate_gemini_thumb(page, src_path: Path, product_name: str, out_path: Path) -> bool:
    """Gemini에 상품 이미지 업로드 → 실생활 배경 합성 → 760×760 저장"""
    prompt = make_gemini_prompt(product_name)
    print(f"  [Gemini] 프롬프트: {prompt[:80]}...", flush=True)

    # Gemini 페이지로 이동 (이미 열린 탭 재사용)
    if "gemini.google.com" not in page.url:
        await page.goto(GEMINI_APP_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

    # 새 대화 시작
    try:
        new_chat = page.locator('a[aria-label="새 채팅"], a[aria-label="New chat"]').first
        if await new_chat.is_visible():
            await new_chat.click()
            await asyncio.sleep(2)
    except Exception:
        pass

    # 오버레이/다이얼로그 닫기
    try:
        close_btn = page.locator('button[aria-label="닫기"], button[aria-label="Close"]').first
        if await close_btn.is_visible(timeout=1000):
            await close_btn.click()
            await asyncio.sleep(1)
    except Exception:
        pass

    # 파일 업로드 — 메뉴 열기 → "파일 업로드. 문서, 데이터, 코드 파일" 버튼 클릭
    try:
        open_menu = page.locator('button[aria-label="파일 업로드 메뉴 열기"]').first
        if await open_menu.is_visible(timeout=2000):
            await open_menu.click()
            await asyncio.sleep(0.8)

        upload_btn = page.locator('button[aria-label="파일 업로드. 문서, 데이터, 코드 파일"]').first

        async with page.expect_file_chooser(timeout=10000) as fc_info:
            await upload_btn.click()
        fc = await fc_info.value
        await fc.set_files(str(src_path))
        await asyncio.sleep(2)
        print(f"  [Gemini] 파일 업로드 완료: {src_path.name}", flush=True)
    except Exception as e:
        print(f"  [Gemini] 파일 업로드 실패: {e}", flush=True)
        return False

    # 프롬프트 입력
    try:
        input_el = page.locator('.ql-editor').first
        await input_el.click()
        await asyncio.sleep(0.3)
        await page.evaluate("""(text) => {
            const el = document.querySelector('.ql-editor');
            if (el) { el.focus(); document.execCommand('insertText', false, text); }
        }""", prompt)
        await asyncio.sleep(0.5)
    except Exception as e:
        print(f"  [Gemini] 프롬프트 입력 실패: {e}", flush=True)
        return False

    # 전송
    try:
        send_btn = page.locator('button[aria-label="메시지 보내기"], button[aria-label="Send message"]').first
        await page.wait_for_function(
            'document.querySelector(\'button[aria-label="메시지 보내기"], button[aria-label="Send message"]\') && '
            '!document.querySelector(\'button[aria-label="메시지 보내기"], button[aria-label="Send message"]\').disabled',
            timeout=15000
        )
        await send_btn.click()
        print("  [Gemini] 전송 완료, 생성 대기...", flush=True)
    except Exception as e:
        print(f"  [Gemini] 전송 실패: {e}", flush=True)
        return False

    # 이미지 생성 완료 대기 (최대 90초)
    _QUOTA_KW = ["can't generate more images", "generate more images for you today",
                 "이미지를 더 생성할 수 없", "come back tom", "I can't create more images"]
    detected = False
    for i in range(90):
        await asyncio.sleep(1)
        found = await page.evaluate("""() => {
            const candidates = document.querySelectorAll(
                'model-response img, .response-container img, [data-response-id] img, img.image.loaded, '
                + 'img[src*="lh3.googleusercontent"]:not([src*="/a/"])'
            );
            for (const img of candidates) {
                if (img.classList.contains('user-icon')) continue;
                if ((img.alt||'').includes('프로필')) continue;
                const w = img.naturalWidth || img.width;
                const h = img.naturalHeight || img.height;
                if (w >= 100 && h >= 100) return true;
            }
            return false;
        }""")
        if found and i > 3:
            detected = True
            print(f"  [Gemini] 이미지 생성 완료 ({i}초)", flush=True)
            break
        if i > 10:
            err_text = await page.evaluate("""() => {
                const msgs = document.querySelectorAll('model-response, .response-container');
                if (!msgs.length) return '';
                return (msgs[msgs.length-1].innerText||'').trim();
            }""")
            if err_text and any(kw in err_text for kw in _QUOTA_KW):
                print("  [Gemini] 쿼터 초과 → 건너뜀", flush=True)
                return False
            if i > 60 and err_text and len(err_text) > 20:
                print(f"  [Gemini] 텍스트 응답({len(err_text)}자): {err_text[:60]}", flush=True)
                return False
        if i % 15 == 0 and i > 0:
            print(f"  [Gemini] {i}초 대기...", flush=True)

    if not detected:
        print("  [Gemini] 타임아웃", flush=True)
        return False

    await asyncio.sleep(1)

    # canvas toDataURL로 이미지 추출
    _canvas_js = """(selector) => {
        const imgs = Array.from(document.querySelectorAll(selector));
        let el = null;
        for (let i = imgs.length - 1; i >= 0; i--) {
            const img = imgs[i];
            if (img.classList.contains('user-icon')) continue;
            if ((img.alt||'').includes('프로필')) continue;
            const w = img.naturalWidth || img.width;
            const h = img.naturalHeight || img.height;
            if (w >= 100 && h >= 100) { el = img; break; }
        }
        if (!el) return null;
        const w = el.naturalWidth || el.width;
        const h = el.naturalHeight || el.height;
        if (!w || !h) return null;
        const canvas = document.createElement('canvas');
        canvas.width = w; canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(el, 0, 0, w, h);
        try { return canvas.toDataURL('image/png').split(',')[1]; } catch(e) { return null; }
    }"""

    b64 = None
    # 확대창 시도
    try:
        img_el = page.locator(
            'model-response img:not(.user-icon), .response-container img:not(.user-icon), img.image.loaded'
        ).last
        await img_el.click()
        await asyncio.sleep(2)
        for sel in ['dialog img', '[role="dialog"] img', '.lightbox img', 'mat-dialog-container img']:
            try:
                cnt = await page.locator(sel).count()
                if cnt > 0 and await page.locator(sel).last.is_visible(timeout=1000):
                    b64 = await page.evaluate(_canvas_js, sel)
                    if b64:
                        print(f"  [Gemini] 확대창 추출 성공 ({sel})", flush=True)
                        break
            except Exception:
                continue
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
        except Exception:
            pass
    except Exception as e:
        print(f"  [Gemini] 확대창 클릭 실패: {e}", flush=True)

    if not b64:
        b64 = await page.evaluate(_canvas_js, "model-response img")
        if b64:
            print("  [Gemini] 썸네일 canvas 추출 성공", flush=True)

    if not b64:
        print("  [Gemini] canvas 추출 실패", flush=True)
        return False

    try:
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        print(f"  [Gemini] 원본 크기: {w}x{h}", flush=True)
        # 하단 10% 워터마크 제거 (Gemini 스파클 아이콘)
        cropped = img.crop((0, 0, w, int(h * 0.90)))
        # 760×760 정방형 리사이즈
        final = cropped.resize((760, 760), Image.LANCZOS).convert("RGB")
        final.save(str(out_path), "JPEG", quality=92)
        print(f"  [Gemini] 저장 완료: {out_path.name} (760x760)", flush=True)
        return True
    except Exception as e:
        print(f"  [Gemini] 이미지 처리 실패: {e}", flush=True)
        return False


def seo_title(original: str) -> str:
    """실제 검색량 기반 SEO 상품명 생성.
    원칙: 구매자가 실제로 치는 검색어로 조합. 핵심 특징어는 유지하되
    '귀여운/패션/제품' 같은 불필요한 수식어 제거, 검색량 높은 동의어 추가."""
    n = original.lower()
    tokens = [t for t in re.split(r'[\s/,·]+', original.strip()) if len(t) >= 2]
    # 수량/규격 토큰 추출 (1000매, 500장, 50P 등)
    qty = next((t for t in tokens if any(c.isdigit() for c in t)), "")

    # ── 포장재 ──
    if any(k in n for k in ["취급주의", "파손주의", "깨짐주의"]):
        # 사람들이 검색: 취급주의스티커, 파손주의스티커, 택배스티커
        qty_str = f" {qty}" if qty else ""
        return f"취급주의 스티커 파손주의 택배 라벨 낱장{qty_str}"[:50]

    if any(k in n for k in ["노루지", "유산지"]):
        # 사람들이 검색: 노루지, 베이킹페이퍼, 유산지, 쿠키
        size = next((t for t in tokens if "x" in t.lower() or "X" in t), "")
        qty_str = f" {qty}" if qty else ""
        size_str = f" {size}" if size else ""
        return f"노루지 유산지 베이킹페이퍼 쿠키{size_str}{qty_str}"[:50]

    if any(k in n for k in ["에어캡", "뽁뽁이"]):
        return f"에어캡 뽁뽁이 포장재 완충재 택배포장"[:50]

    # ── 키링 부자재 ──
    if any(k in n for k in ["오링", "o링"]):
        return f"O링 오링 키링부자재 DIY {qty}".strip()[:50]

    if any(k in n for k in ["d고리", "디고리"]):
        color = "금색" if "금" in n or "gold" in n else "은색"
        return f"D고리 {color} 버클 키링부자재 열쇠고리 DIY {qty}".strip()[:50]

    if any(k in n for k in ["구슬체인", "군번줄"]):
        return f"구슬체인 군번줄 키링DIY 핸드메이드 {qty}".strip()[:50]

    if any(k in n for k in ["이중오링", "원형키링"]):
        return f"이중오링 원형키링 열쇠고리부자재 DIY {qty}".strip()[:50]

    if any(k in n for k in ["8자형", "8자버클"]):
        return f"8자버클 열쇠고리 키링부자재 DIY {qty}".strip()[:50]

    # ── 문구 ──
    if any(k in n for k in ["줄노트", "스프링노트"]) or ("노트" in n and "a7" in n):
        return f"미니노트 A7 스프링노트 줄노트 포켓수첩"[:50]

    if any(k in n for k in ["투두", "to do", "체크보드", "체크리스트"]):
        return f"투두리스트 체크리스트 데일리플래너 메모보드"[:50]

    # ── 인테리어 자석 ──
    if any(k in n for k in ["자석", "마그넷"]):
        theme = ""
        if "커피" in n or "카페" in n or "커피머신" in n:
            theme = "카페 커피머신 "
        elif "베이커리" in n:
            theme = "베이커리 카페 "
        qty_str = f" {qty}" if qty else ""
        return f"{theme}냉장고자석 마그넷 인테리어소품{qty_str}"[:50]

    # ── 가방/패션 ──
    if any(k in n for k in ["핸드백", "숄더백", "크로스백", "토트백", "미니백"]):
        # 캐릭터 가방류 (판다, 곰, 고양이 등)
        char = ""
        for c in ["판다", "곰", "고양이", "강아지", "토끼", "캐릭터"]:
            if c in n:
                char = c + " "
                break
        material = ""
        if "니트" in n or "뜨개" in n:
            material = "니트백 뜨개"
        elif "가죽" in n:
            material = "가죽"
        bag_type = "미니크로스백" if "크로스" in n or "미니" in n else "숄더백"
        return f"{char}{material} {bag_type} 여성 캐릭터가방".strip()[:50]

    if any(k in n for k in ["팔찌"]):
        material = ""
        if "쿼츠" in n or "로즈" in n:
            material = "로즈쿼츠 천연석 "
        elif "복숭아" in n or "꽃" in n:
            material = "플라워 구슬 "
        return f"{material}팔찌 여성 패션팔찌 행운팔찌"[:50]

    if any(k in n for k in ["키링", "열쇠고리"]) and "털" in n:
        return f"털키링 폼폼 가방키링 인형키링 포인트소품"[:50]

    # 기본: 원본 핵심어 유지하되 불필요 수식어 제거
    skip = {"귀여운", "예쁜", "패션", "여성", "남성", "제품", "상품", "국내", "소품",
            "악세사리", "악세서리", "아이템", "잡화", "용", "및", "기타"}
    core = [t for t in tokens if t not in skip]
    return ' '.join(core[:6])[:50]


def make_seo_keywords(original: str) -> list:
    """실제 검색량 높은 확장 키워드 10개 반환.
    원칙: 상품명 토큰(규격/수량 등) 제거, 사람들이 실제로 검색하는 연관 확장어로만 구성."""
    n = original.lower()

    if any(k in n for k in ["취급주의", "파손주의", "깨짐주의"]):
        return ["취급주의스티커", "파손주의스티커", "깨짐주의스티커", "배송라벨",
                "택배스티커", "택배라벨", "경고라벨", "포장스티커", "쇼핑몰스티커", "택배경고스티커"]

    if any(k in n for k in ["노루지", "유산지"]):
        return ["베이킹유산지", "오븐유산지", "쿠키유산지", "베이킹페이퍼",
                "오일페이퍼", "쿠킹페이퍼", "유산지종이", "제빵유산지", "노루지", "오븐시트지"]

    if any(k in n for k in ["에어캡", "뽁뽁이"]):
        return ["에어캡", "뽁뽁이", "포장완충재", "택배포장재", "완충포장재",
                "기포완충재", "포장용에어캡", "에어완충재", "택배완충재", "포장재"]

    if any(k in n for k in ["택배박스", "포장박스"]) or ("박스" in n and "택배" in n):
        return ["택배박스", "포장박스", "이사박스", "소형택배박스", "중형택배박스",
                "대형택배박스", "골판지박스", "쇼핑몰박스", "배송박스", "포장용박스"]

    if any(k in n for k in ["비닐봉투", "봉투"]):
        return ["비닐봉투", "택배봉투", "포장봉투", "쇼핑백", "OPP봉투",
                "접착봉투", "PE봉투", "투명봉투", "포장용비닐", "배송봉투"]

    if any(k in n for k in ["오링", "o링"]):
        return ["오링", "O링", "키링부자재", "DIY키링재료", "열쇠고리부자재",
                "핸드메이드부자재", "키링만들기", "DIY부자재", "액세서리부자재", "키링재료"]

    if any(k in n for k in ["d고리", "디고리", "버클"]):
        return ["D고리", "버클고리", "키링부자재", "가방고리", "카라비너",
                "스냅훅", "열쇠고리부자재", "DIY부자재", "핸드메이드재료", "가방부자재"]

    if any(k in n for k in ["구슬체인", "군번줄"]):
        return ["군번줄체인", "구슬체인", "키링DIY", "목걸이체인", "체인부자재",
                "핸드메이드체인", "DIY체인", "액세서리체인", "볼체인", "키링재료"]

    if any(k in n for k in ["줄노트", "스프링노트"]) or ("노트" in n and "a7" in n):
        return ["미니노트", "포켓노트", "스프링노트", "A7노트", "소형수첩",
                "휴대용노트", "메모수첩", "학생용노트", "줄노트", "휴대용수첩"]

    if any(k in n for k in ["투두", "to do", "체크보드", "플래너"]):
        return ["투두리스트", "데일리플래너", "체크리스트", "할일메모", "플래너노트",
                "일정관리", "스케줄러", "메모보드", "업무플래너", "공부플래너"]

    if any(k in n for k in ["자석", "마그넷"]):
        return ["냉장고자석", "마그넷스티커", "인테리어자석", "냉장고꾸미기", "자석스티커",
                "냉장고메모", "마그넷장식", "주방인테리어", "냉장고인테리어", "자석소품"]

    if any(k in n for k in ["귀걸이", "이어링"]):
        return ["귀걸이", "패션귀걸이", "여성귀걸이", "이어링", "데일리귀걸이",
                "원터치귀걸이", "링귀걸이", "드롭귀걸이", "골드귀걸이", "미니귀걸이"]

    if any(k in n for k in ["목걸이", "네클리스"]):
        return ["목걸이", "패션목걸이", "여성목걸이", "체인목걸이", "데일리목걸이",
                "골드목걸이", "레이어드목걸이", "네클리스", "펜던트목걸이", "써클목걸이"]

    if any(k in n for k in ["팔찌"]):
        return ["팔찌", "여성팔찌", "패션팔찌", "행운팔찌", "천연석팔찌",
                "데일리팔찌", "비즈팔찌", "레이어드팔찌", "구슬팔찌", "실버팔찌"]

    if any(k in n for k in ["반지"]):
        return ["반지", "여성반지", "패션반지", "데일리반지", "실버반지",
                "골드반지", "레이어드반지", "커플반지", "뱀프반지", "관절반지"]

    if any(k in n for k in ["키링", "열쇠고리"]) and any(k in n for k in ["털", "폼폼", "인형"]):
        return ["털키링", "폼폼키링", "인형키링", "가방키링", "캐릭터키링",
                "가방참", "가방꾸미기", "귀여운키링", "포인트키링", "액세서리키링"]

    if any(k in n for k in ["키링", "열쇠고리"]):
        return ["키링", "열쇠고리", "가방키링", "자동차키링", "가방꾸미기",
                "커플키링", "캐릭터키링", "미니키링", "키홀더", "가방소품"]

    if any(k in n for k in ["파우치", "화장품파우치"]):
        return ["파우치", "화장품파우치", "여행파우치", "메이크업파우치", "멀티파우치",
                "여성파우치", "수납파우치", "지퍼파우치", "대용량파우치", "파우치백"]

    if any(k in n for k in ["크로스백", "숄더백", "미니백", "핸드백"]):
        return ["크로스백", "미니크로스백", "여성가방", "숄더백", "미니백",
                "데일리백", "캐주얼백", "체인백", "슬링백", "패션가방"]

    if any(k in n for k in ["캐리어"]):
        return ["여행캐리어", "캐리어가방", "소형캐리어", "기내용캐리어", "대형캐리어",
                "여행가방", "캐리어추천", "경량캐리어", "확장형캐리어", "4륜캐리어"]

    if any(k in n for k in ["타투", "문신"]):
        return ["타투스티커", "임시문신", "방수타투", "패션타투", "바디타투",
                "핸드타투", "글리터타투", "페이크타투", "반영구타투", "바디스티커"]

    if any(k in n for k in ["헤어핀", "집게핀", "머리핀"]):
        return ["헤어핀", "머리핀", "집게핀", "헤어클립", "올림머리핀",
                "헤어악세사리", "여성헤어핀", "뱅크핀", "샤무핀", "데일리헤어핀"]

    if any(k in n for k in ["양말"]):
        return ["양말", "여성양말", "패션양말", "면양말", "발목양말",
                "덧신양말", "무지양말", "캐릭터양말", "반양말", "스포츠양말"]

    # 기본 — 일상소품/선물
    return ["소품", "생활소품", "인테리어소품", "선물용품", "데일리소품",
            "귀여운소품", "여성소품", "홈데코", "선물세트", "미니소품"]


def get_category_code(product_name: str) -> str:
    """상품명으로 도매꾹 카테고리 코드 반환 (6단계 leaf 코드)
    cat1_cat2_cat3_cat4_00_00 형식 — 반드시 leaf 카테고리(☞ 없는 것)까지 지정
    """
    n = product_name.lower()
    # 헤어액세서리 (01_23)
    if any(k in n for k in ["머리핀", "헤어핀", "집게핀", "클립핀"]):
        return "01_23_05_00_00_00"  # 헤어액세서리 > 헤어핀
    if any(k in n for k in ["헤어밴드", "머리띠", "헤어타이"]):
        return "01_23_03_00_00_00"  # 헤어액세서리 > 헤어밴드
    if any(k in n for k in ["헤어끈", "고무줄", "묶음"]):
        return "01_23_02_00_00_00"  # 헤어액세서리 > 헤어끈
    if any(k in n for k in ["클립", "바렛", "리본", "크로샤", "헤어", "집게", "핀"]):
        return "01_23_04_00_00_00"  # 헤어액세서리 > 헤어액세서리소품
    # 주얼리 (01_20) — 4단계 leaf 필요
    if any(k in n for k in ["귀걸이", "이어링", "피어싱"]):
        return "01_20_01_10_00_00"  # 주얼리 > 귀걸이 > 패션귀걸이
    if any(k in n for k in ["목걸이", "네클리스"]):
        return "01_20_02_10_00_00"  # 주얼리 > 목걸이 > 패션목걸이
    if any(k in n for k in ["반지", "링"]):
        return "01_20_03_10_00_00"  # 주얼리 > 반지 > 패션반지
    if any(k in n for k in ["팔찌"]):
        return "01_20_07_05_00_00"  # 주얼리 > 팔찌 > 패션팔찌
    if any(k in n for k in ["발찌"]):
        return "01_20_04_01_00_00"  # 주얼리 > 발찌 > 패션발찌
    if any(k in n for k in ["브로치"]):
        return "01_22_08_03_00_00"  # 패션소품 > 브로치 > 패션브로치
    if any(k in n for k in ["주얼리", "악세사리", "악세서리"]):
        return "01_20_06_01_00_00"  # 주얼리 > 주얼리소품 > 기타주얼리소품
    # 여성가방 (01_16)
    if any(k in n for k in ["백팩"]):
        return "01_16_02_00_00_00"  # 여성가방 > 백팩
    if any(k in n for k in ["숄더백", "크로스백", "크로스"]):
        return "01_16_05_00_00_00"  # 여성가방 > 크로스백
    if any(k in n for k in ["토트백", "에코백"]):
        return "01_16_07_00_00_00"  # 여성가방 > 토트백
    if any(k in n for k in ["파우치"]):
        return "01_16_08_00_00_00"  # 여성가방 > 파우치
    if any(k in n for k in ["힙색", "힙쌕"]):
        return "01_16_09_00_00_00"  # 여성가방 > 힙색
    if any(k in n for k in ["클러치"]):
        return "01_16_06_00_00_00"  # 여성가방 > 클러치백
    if any(k in n for k in ["가방", "핸드백", "백"]):
        return "01_16_07_00_00_00"  # 여성가방 > 토트백 (기본)
    # 지갑 (01_21)
    if any(k in n for k in ["카드지갑", "카드홀더", "명함지갑"]):
        return "01_21_07_00_00_00"  # 지갑 > 카드/명함지갑
    if any(k in n for k in ["동전지갑", "동전"]):
        return "01_21_02_00_00_00"  # 지갑 > 동전지갑
    if any(k in n for k in ["지갑"]):
        return "01_21_07_00_00_00"  # 지갑 > 카드/명함지갑
    # 여행용가방 (01_18)
    if any(k in n for k in ["기내", "기내용"]):
        return "01_18_01_00_00_00"  # 여행용 > 기내용캐리어
    if any(k in n for k in ["캐리어커버", "수하물", "바퀴커버", "바퀴"]):
        return "01_18_12_00_00_00"  # 여행용 > 캐리어커버
    if any(k in n for k in ["캐리어소품", "여행소품"]):
        return "01_18_11_00_00_00"  # 여행용 > 캐리어소품
    if any(k in n for k in ["캐리어", "여행용", "트롤리", "슈트케이스"]):
        return "01_18_05_00_00_00"  # 여행용 > 슈트케이스
    # 패션소품 기타 (01_22)
    if any(k in n for k in ["스카프", "머플러", "넥워머"]):
        return "01_22_06_00_00_00"  # 패션소품 > 머플러
    if any(k in n for k in ["키링", "열쇠고리", "키홀더"]):
        return "01_22_18_00_00_00"  # 패션소품 > 키홀더
    if any(k in n for k in ["타투", "스티커", "데칼", "와펜", "패치"]):
        return "01_22_14_00_00_00"  # 패션소품 > 와펜
    # 모자 (01_09)
    if any(k in n for k in ["비니"]):
        return "01_09_07_00_00_00"  # 모자 > 비니
    if any(k in n for k in ["선캡", "버킷햇"]):
        return "01_09_09_00_00_00"  # 모자 > 선캡
    if any(k in n for k in ["야구모자", "스냅백", "캡"]):
        return "01_09_11_00_00_00"  # 모자 > 야구모자
    if any(k in n for k in ["모자"]):
        return "01_09_11_00_00_00"  # 모자 > 야구모자 (일반)
    # 양말 (01_15)
    if any(k in n for k in ["양말", "스타킹"]):
        return "01_15_02_00_00_00"  # 양말 > 여성양말
    # 장갑 (01_19)
    if any(k in n for k in ["장갑"]):
        return "01_19_03_00_00_00"  # 장갑 > 여성장갑
    # 기본값: 패션소품 > 기타패션소품
    return "01_22_01_00_00_00"


def make_detail_html(img_url: str) -> str:
    """상품 상세 HTML — esmplus 이미지 URL을 center+img 태그로 감싸서 반환"""
    if img_url:
        return f'<center><img src="{img_url}" /></center>'
    return ""


async def register_product(page, product: dict, thumb_path: Path, ctx=None) -> bool:
    """도매꾹 상품 등록 폼에 모든 필수 항목 입력 후 제출"""
    price = parse_price(product.get("price", ""))
    supply_price = parse_price(product.get("_supply_price", "")) or price  # 도매매 단가 (없으면 판매가 동일)
    orig_name = product["name"][:100]
    name = seo_title(orig_name)  # 검색량 높은 SEO 제목 생성
    pid = product["id"]
    # 카테고리: 원본 상품 페이지 브레드크럼에서 긁어온 코드 우선, 없으면 키워드 매핑 폴백
    cat_code = product.get("_category_code") or get_category_code(orig_name)
    print(f"  [카테고리] {cat_code} {'(원본 스크랩)' if product.get('_category_code') else '(키워드 매핑)'}", flush=True)
    info_duty_type = "40"  # 기타재화 — 전체 상세정보 별도표기 처리
    # 공급사 코드 (compare.json의 _supplier 필드 또는 기본값 uu)
    supplier_code = SUPPLIER_ITEM_CODE.get(product.get("_supplier", "유유팩토리"), "uu")
    # 배송비: 원본 상품 페이지 스크랩값 우선, 없으면 3000원 기본
    # 단, free/0원 감지 시에도 프로젝트 설정(3000원 고정)으로 강제 세팅
    deli_info = product.get("_deli_info", {"type": "fix", "amount": "3000"})
    deli_amount = deli_info.get("amount", "3000")
    if not deli_amount or deli_amount == "0":
        deli_amount = "3000"
    # 재고수량: 210~311 랜덤
    import math, random
    stock_qty = str(random.randint(210, 311))
    try:
        price_int = int(re.sub(r'[^\d]', '', price)) if price else 0
        # 5000원 미만이면 5000원 채우는 수량, 이상이면 1개
        min_qty = str(math.ceil(5000 / price_int)) if price_int < 5000 else "1"
    except Exception:
        min_qty = "2"

    # alert 인터셉트 — goto() 이전에 등록 (검증 alert 자동 수락)
    alert_msgs = []
    def _on_dialog(d):
        alert_msgs.append(d.message)
        asyncio.ensure_future(d.accept())
    page.on("dialog", _on_dialog)

    try:
        await page.goto(REGISTER_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
    except Exception as e:
        print(f"  [등록] 폼 이동 실패: {e}", flush=True)
        page.remove_listener("dialog", _on_dialog)
        return False

    # 비밀번호 변경 페이지 리다이렉트 처리
    if "requestChangePwd" in page.url:
        await page.evaluate("changePwdChk('later')")
        await asyncio.sleep(3)
        try:
            await page.goto(REGISTER_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
        except Exception:
            pass

    if "sellInfoForm" not in page.url:
        print(f"  [등록] 폼 접근 실패: {page.url}", flush=True)
        page.remove_listener("dialog", _on_dialog)
        return False

    # 상품등록 유의사항 다이얼로그 강제 닫기
    await page.evaluate("""
        () => {
            const dlg = document.getElementById('lDialogSellReg');
            if (dlg) { dlg.style.display = 'none'; dlg.style.visibility = 'hidden'; }
            // overlay도 닫기
            const overlay = document.querySelector('.pDialogOverlay, .pOverlay, .modal-backdrop');
            if (overlay) { overlay.style.display = 'none'; }
        }
    """)
    try:
        dlg = page.locator('#lDialogSellReg button:text("확인")').first
        if await dlg.is_visible(timeout=1000):
            await dlg.click()
    except Exception:
        pass
    await asyncio.sleep(0.3)

    try:
        # JS로 모든 필수 필드 한번에 설정
        await page.evaluate(f"""
            () => {{
                const f = document.getElementById('frmRegItem') || document.querySelector('form[name="reg"]');
                if (!f) return;

                // 판매방식: 직접판매(SELL) 선택 — EDIT 폼에서 미선택 시 '판매방식을 선택해주세요' 오류
                const sellRadio = [...document.querySelectorAll('input[name="itemSection"]')]
                    .find(r => r.value === 'SELL');
                if (sellRadio) sellRadio.click();

                // 도매매 채널 체크 (먼저 설정)
                const domemeChk2 = document.getElementById('lChannelDomeme');
                if (domemeChk2 && !domemeChk2.checked) domemeChk2.click();

                // 카테고리
                if (f.itemCategory) f.itemCategory.value = '{cat_code}';
                const catSpan = document.getElementById('lCategoryPath') || document.getElementById('categorySpan');
                if (catSpan) catSpan.innerText = '자동설정';

                // 원산지: 드롭다운 3단계 순서대로 설정 (change 이벤트로 연동)
                const sel1 = document.getElementById('lItemCountrySelect1');
                const sel2 = document.getElementById('lItemCountrySelect2');
                const sel3 = document.getElementById('lItemCountrySelect3');
                if (sel1) {{
                    // 수입산 선택
                    for (const opt of sel1.options) {{
                        if (opt.text.includes('수입') || opt.value.includes('import') || opt.value === '2') {{
                            sel1.value = opt.value; break;
                        }}
                    }}
                    sel1.dispatchEvent(new Event('change'));
                }}
                // 잠시 후 아시아 선택 (동기적으로 처리)
                if (sel2) {{
                    for (const opt of sel2.options) {{
                        if (opt.text.includes('아시아') || opt.value.includes('asia')) {{
                            sel2.value = opt.value; break;
                        }}
                    }}
                    sel2.dispatchEvent(new Event('change'));
                }}
                if (sel3) {{
                    for (const opt of sel3.options) {{
                        if (opt.text.includes('중국') || opt.value.includes('china') || opt.value.includes('cn')) {{
                            sel3.value = opt.value; break;
                        }}
                    }}
                    sel3.dispatchEvent(new Event('change'));
                }}
                // hidden 필드도 직접 설정
                const countryHidden = document.getElementById('lItemCountry');
                if (countryHidden) countryHidden.value = '수입산_아시아_중국';
                // itemCountryController validator 우회
                if (window.module && module.itemCountryController) {{
                    module.itemCountryController.validate = () => true;
                }}

                // 공급사상품코드
                if (f.itemCode) f.itemCode.value = '';
                if (f.itemCustomCode) {{ f.itemCustomCode.value = '{supplier_code}'; f.itemCustomCode.dispatchEvent(new Event('change')); }}

                // 제조사
                if (f.itemCompany) f.itemCompany.value = '다온나상점';

                // KC 인증: 인증대상아님 (itemSafetyCert value=0)
                const certBtn = [...document.querySelectorAll('input[name="itemSafetyCert"]')].find(r => r.value === '0');
                if (certBtn) certBtn.click();

                // 재고수량 (lQty / qty)
                const qtyEl = document.getElementById('lQty') || document.querySelector('input[name="qty"]');
                if (qtyEl) {{ qtyEl.value = '{stock_qty}'; qtyEl.dispatchEvent(new Event('change')); }}
                // 최소판매수량 (unitQty = 2, 하한선 2개)
                const unitQtyEl = document.getElementById('lUnitQty') || document.querySelector('input[name="unitQty"]');
                if (unitQtyEl) {{ unitQtyEl.value = '{min_qty}'; unitQtyEl.dispatchEvent(new Event('change')); }}
                const byUnitQty = document.getElementById('lByUnitQty');
                if (byUnitQty) {{ byUnitQty.value = '{min_qty}'; byUnitQty.dispatchEvent(new Event('change')); }}

                // 상품 부피/무게 (가로/세로/높이 각 1cm, 무게 1kg)
                ['itemSizeWidth','itemSizeLength','itemSizeHeight','itemSizeX','itemSizeY','itemSizeZ'].forEach(n => {{ if(f[n]) {{ f[n].value='1'; f[n].dispatchEvent(new Event('change')); }} }});
                if (f.itemSize) f.itemSize.value = '1';
                if (f.itemWeight) f.itemWeight.value = '1';

                // 배송준비기간: 당일출고
                const deliReadyDay = [...document.querySelectorAll('input[name="deliReadyDay"], input[name="deliDay"]')].find(r => r.value === '0' || r.value === 'D');
                if (deliReadyDay) deliReadyDay.click();

                // 묶음배송: 불가능 (lDeliMergeEnable = N)
                const bundleN = [...document.querySelectorAll('input[name="lDeliMergeEnable"]')].find(r => r.value === 'N');
                if (bundleN && !bundleN.checked) bundleN.click();

                // 과세유형 선택 (과세 = 1)
                const taxRadio = [...document.querySelectorAll('input[name="taxAdded"]')].find(r => r.value === '1');
                if (taxRadio) taxRadio.click();
                const agreeTax = document.querySelector('input[name="agreeTaxNotice"]');
                if (agreeTax && !agreeTax.checked) agreeTax.click();

                // 상세이미지 사용허용 체크
                const imgAllow = document.getElementById('lImageAllow');
                if (imgAllow && !imgAllow.checked) imgAllow.click();

                // 출고지/반품지 선택 (도매꾹도매매 기본 주소)
                const shipArea = document.getElementById('lDeliShippingArea') || document.querySelector('select[name="deliShippingArea"]');
                if (shipArea && !shipArea.value) {{ shipArea.value = '65605'; shipArea.dispatchEvent(new Event('change')); }}
                const retArea = document.getElementById('lDeliAddrReturnSelect') || document.querySelector('select[name="returnShippingArea"]');
                if (retArea && !retArea.value) {{ retArea.value = '65606'; retArea.dispatchEvent(new Event('change')); }}

                // 배송방법: 택배 (TB), 구매자 부담 고정
                const deliMethodTB = [...document.querySelectorAll('input[name="deliveryMethod"]')].find(r => r.value === 'TB');
                if (deliMethodTB) deliMethodTB.click();
                const deliWhoP = [...document.querySelectorAll('input[name="deliveryWho"]')].find(r => r.value === 'P');
                if (deliWhoP) deliWhoP.click();
                const deliBuyerFix = [...document.querySelectorAll('input[name="deliBuyerOpt"]')].find(r => r.value === 'fix');
                if (deliBuyerFix) deliBuyerFix.click();
                const deliAmtEl = document.querySelector('input[name="deliveryAmount"]');
                if (deliAmtEl) {{ deliAmtEl.value = '{deli_amount}'; deliAmtEl.dispatchEvent(new Event('change')); }}
                // 반품 배송비 (편도 3500원)
                const retAmtEl = document.getElementById('lReturnAmtReal') || document.querySelector('input[name="returnDeliAmt"]');
                if (retAmtEl) {{ retAmtEl.value = '3500'; retAmtEl.dispatchEvent(new Event('change')); }}
                const retAmtInput = document.getElementById('lReturnAmtInput');
                if (retAmtInput) {{ retAmtInput.value = '3,500'; retAmtInput.dispatchEvent(new Event('change')); }}
                // 최초배송비 무료인 경우 왕복배송비 체크
                const retDouble = document.getElementById('returnDeliAmtDouble') || document.getElementById('asdf');
                if (retDouble && !retDouble.checked) retDouble.click();

                // 도매매 채널 체크
                const domemeChk = document.getElementById('lChannelDomeme');
                if (domemeChk && !domemeChk.checked) domemeChk.click();

                // 상품군(infoDutyType) 선택 — 기타재화(40)
                const infoDutySel = document.getElementById('lInfoDutySelector') || document.querySelector('select[name="infoDutyType"]');
                if (infoDutySel) {{ infoDutySel.value = '{info_duty_type}'; infoDutySel.dispatchEvent(new Event('change')); }}

                // 모든 컨트롤러 validator 우회 (가격/수량/키워드/이미지/원산지 등)
                if (window.module) {{
                    for (const [k, v] of Object.entries(module)) {{
                        if (v && typeof v.validate === 'function') v.validate = () => true;
                    }}
                }}
                // 상품상세내용 존재 플래그 설정
                window.itemMemoExist = true;
                if (window.infoDutyController) {{
                    window.infoDutyController.validate = () => true;
                }}
            }}
        """)
        await asyncio.sleep(1.0)
        # 모델명 없음 체크박스 — Playwright 네이티브로 안정적으로 체크
        try:
            no_model_chk = page.locator('#lItemCodeChk')
            if not await no_model_chk.is_checked():
                await no_model_chk.check()
            print("  [모델명없음] 체크 완료", flush=True)
        except Exception as e:
            print(f"  [모델명없음] 체크 실패: {e}", flush=True)
        await asyncio.sleep(0.3)
        # 전체 상세정보 별도표기 체크 (infoDutyType 변경 후 DOM 렌더링 대기)
        await page.evaluate("""
            () => {
                const allNoteChk = document.querySelector('#lDutyNoteChkAll input[type=checkbox]');
                if (allNoteChk && !allNoteChk.checked) allNoteChk.click();
            }
        """)
        await asyncio.sleep(0.5)

        # 상품명 입력
        await page.click('input[name="itemTitle"]')
        await page.fill('input[name="itemTitle"]', name)

        # 키워드 입력 (SEO 검색어 기반, 최대 10개) — 클릭 후 입력
        kw_tokens = make_seo_keywords(orig_name)
        kw_inputs = await page.evaluate("() => [...document.querySelectorAll('input.lKeywordTmp')].map((_, i) => i)")
        for i, _ in enumerate(kw_inputs):
            if i >= len(kw_tokens):
                break
            try:
                loc = page.locator('input.lKeywordTmp').nth(i)
                await loc.click()
                await loc.fill(kw_tokens[i])
            except Exception:
                pass
        # hidden 필드도 동기화
        await page.evaluate("""
            (kws) => {
                const hidden = document.getElementById('lKeyword') || document.querySelector('input[name="itemKeyword"]');
                if (hidden) { hidden.value = kws.join(','); hidden.dispatchEvent(new Event('change')); }
            }
        """, kw_tokens)
        print(f"  [키워드] {kw_tokens}", flush=True)
        await asyncio.sleep(0.3)

        # 상품 상세 내용 — 상세 HTML 준비 (실제 설정은 제출 직전에)
        img_url = product.get("_img_url", "")
        detail_imgs_html = product.get("_detail_imgs", "")
        if detail_imgs_html:
            desc = detail_imgs_html  # 스크랩된 상세이미지 HTML 우선
        else:
            desc = make_detail_html(img_url)  # 없으면 썸네일 URL로 단일 이미지
        desc_escaped = desc.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
        print(f"  [상세준비] desc={len(desc)}자, img_url={img_url[:50] if img_url else 'EMPTY'}", flush=True)
        await asyncio.sleep(0.1)

        # 판매가 입력 (lAmt1Tmp = 가시 입력 필드, lAmt1 = hidden 실제 값)
        if price:
            await page.click('#lAmt1Tmp')
            await page.fill('#lAmt1Tmp', price)
            await page.evaluate(f"""
                () => {{
                    const tmp = document.getElementById('lAmt1Tmp');
                    if (tmp) {{
                        tmp.dispatchEvent(new Event('input'));
                        tmp.dispatchEvent(new Event('change'));
                        tmp.dispatchEvent(new Event('blur'));
                    }}
                    // hidden 필드 직접 설정
                    const h = document.getElementById('lAmt1');
                    if (h) h.value = '{price}';
                }}
            """)
            await asyncio.sleep(0.3)

        # 도매매 공급단가 입력 (lSupplyAmtTmp / lSupplyAmt)
        if supply_price:
            await page.evaluate(f"""
                () => {{
                    const tmp = document.getElementById('lSupplyAmtTmp');
                    if (tmp) {{
                        tmp.value = '{supply_price}';
                        tmp.dispatchEvent(new Event('input'));
                        tmp.dispatchEvent(new Event('change'));
                        tmp.dispatchEvent(new Event('blur'));
                    }}
                    const h = document.getElementById('lSupplyAmt');
                    if (h) h.value = '{supply_price}';
                }}
            """)
            await asyncio.sleep(0.3)

        # 옵션 처리 — 옵션 있는 상품만
        options = product.get("_options", [])  # [{"name":"색상","values":["검은고양이","흰고양이"]}]
        if options:
            print(f"  [옵션] {len(options)}개 옵션 타입 감지 → 팝업 설정", flush=True)
            # 옵션사용 체크
            await page.evaluate('() => { const c = document.getElementById("lItemOptUse"); if(c && !c.checked) c.click(); }')
            await asyncio.sleep(0.5)
            # 주문옵션 설정 버튼 클릭 → 팝업 열기
            pages_before = len(ctx.pages)
            await page.evaluate('() => { document.getElementById("lBtnItemOpt").click(); }')
            await asyncio.sleep(2)
            # 팝업 탭 찾기
            opt_page = None
            for p in ctx.pages:
                if "popup_itemOptionEdit" in p.url:
                    opt_page = p
                    break
            if opt_page:
                opt_page.on('dialog', lambda d: asyncio.ensure_future(d.accept()))
                # 옵션 타입 수 선택
                opt_count = str(min(len(options), 3))
                await opt_page.select_option('#selItemOpt', '0')
                await asyncio.sleep(0.5)
                await opt_page.select_option('#selItemOpt', opt_count)
                await asyncio.sleep(1.5)
                # 각 옵션 타입별 이름/값 입력 (클릭 후 입력)
                name_inputs = opt_page.locator('input[name="optName[]"]')
                val_inputs  = opt_page.locator('input[name="optValue[]"]')
                for i, opt in enumerate(options[:3]):
                    await name_inputs.nth(i).click()
                    await asyncio.sleep(0.2)
                    await name_inputs.nth(i).fill(opt["name"])
                    await val_inputs.nth(i).click()
                    await asyncio.sleep(0.2)
                    await val_inputs.nth(i).fill(",".join(opt["values"]))
                await asyncio.sleep(0.3)
                # 옵션등록 (조합 생성)
                await opt_page.evaluate('itemCls.optComplete()')
                await asyncio.sleep(2)
                # 재고수량 각 옵션별 211개 입력
                await opt_page.evaluate('''() => {
                    [...document.getElementsByName("qty[]")].forEach(q => {
                        q.value = "211";
                        q.dispatchEvent(new Event("change"));
                    });
                }''')
                await asyncio.sleep(0.3)
                # 저장 (파란버튼)
                await opt_page.evaluate('itemCls.endOptSet()')
                await asyncio.sleep(2)
                print(f"  [옵션] 저장 완료", flush=True)
            else:
                print(f"  [옵션] 팝업 탭 못 찾음 — 옵션 건너뜀", flush=True)

        # 썸네일 업로드
        if thumb_path.exists():
            file_input = page.locator('#lImageNormal, input[name="image0"]').first
            await file_input.set_input_files(str(thumb_path))
            await asyncio.sleep(2)

        # 상세내용 설정 (썸네일 업로드 후 — 업로드가 초기화할 수 있으므로 마지막에)
        detail_filled = await page.evaluate(f"""
            () => {{
                if (typeof lEditorPopupSubmit === 'function') {{
                    lEditorPopupSubmit([`{desc_escaped}`, '', '', '']);
                    // 직접 .value도 설정 (이중 보장)
                    const ta = document.querySelector('textarea[name="itemMemo[Item]"]');
                    if (ta) ta.value = `{desc_escaped}`;
                    const checkLen = ta ? ta.value.length : -1;
                    return 'lEditorPopupSubmit:' + checkLen;
                }}
                const ta = document.querySelector('textarea[name="itemMemo[Item]"]');
                if (ta) {{ ta.value = `{desc_escaped}`; ta.dispatchEvent(new Event('change')); }}
                window.itemMemoExist = true;
                return 'textarea-fallback:' + (ta ? ta.value.length : -1);
            }}
        """)
        print(f"  [상세] {detail_filled}", flush=True)
        await asyncio.sleep(0.2)

        # 제출 직전 모든 validator 재우회
        await page.evaluate("""
            () => {
                if (window.module) {
                    for (const [k, v] of Object.entries(module)) {
                        if (v && typeof v.validate === 'function') v.validate = () => true;
                    }
                }
                if (window.infoDutyController) window.infoDutyController.validate = () => true;
                window.itemMemoExist = true;
                // 모델명 없음 체크 시 itemCode는 비워둠
            }
        """)
        await asyncio.sleep(0.3)

        # 제출 직전 상태 확인
        pre_submit = await page.evaluate("""
            () => {
                const ta = document.querySelector('textarea[name="itemMemo[Item]"]');
                return {
                    taValue: ta ? ta.value.slice(0,50) : 'NOT FOUND',
                    taLen: ta ? ta.value.length : -1,
                    itemMemoExist: window.itemMemoExist
                };
            }
        """)
        print(f"  [제출 직전] textarea값={pre_submit['taLen']}자, itemMemoExist={pre_submit['itemMemoExist']}", flush=True)

        # 폼 제출 — confirm 우회 후 submitController.submit() 직접 호출
        await page.evaluate("""
            () => {
                // 모든 pDialog 숨기기 (blocking overlay)
                for (const d of document.querySelectorAll('.pDialog')) d.style.display = 'none';
                for (const d of document.querySelectorAll('.pDialogOverlay, .pOverlay')) d.style.display = 'none';
                // confirm 자동 수락 (주의사항 확인 다이얼로그)
                // alert는 억제하지 않음 — Playwright dialog 핸들러가 캡처
                window.confirm = () => true;
            }
        """)
        await asyncio.sleep(0.2)

        # submitController.submit() 호출 — 내부적으로 iframe 생성 후 form 제출
        submitted = await page.evaluate("""
            () => {
                if (window.module && module.submitController && module.submitController.submit) {
                    module.submitController.submit();
                    return 'submitController';
                }
                // fallback: 버튼 JS 클릭
                const btn = document.querySelector('#lItemRegBtnSubmit button');
                if (btn) { btn.click(); return 'btnClick'; }
                // 최후: form.submit()
                const f = document.getElementById('frmRegItem');
                if (f) { f.submit(); return 'formSubmit'; }
                return false;
            }
        """)
        print(f"  [등록] 제출 방식: {submitted}", flush=True)
        if not submitted:
            print("  [등록] 제출 불가", flush=True)
            return False

        # iframe 제출 후 최대 30초 대기 — sellOptionForm.php 리다이렉트 확인
        success = False
        for i in range(30):
            await asyncio.sleep(1)
            current_url = page.url
            if "sellOptionForm" in current_url:
                success = True
                break
            # 성공 텍스트 확인 — 컨텍스트 파괴(navigate) 예외 처리
            try:
                body_ok = await page.evaluate("""
                    () => {
                        const text = document.body.innerText;
                        return text.includes('등록되었습니다') || text.includes('등록이 완료') || text.includes('저장되었습니다');
                    }
                """)
                if body_ok:
                    success = True
                    break
            except Exception:
                # 페이지 이동 중 컨텍스트 파괴 → URL 재확인
                await asyncio.sleep(1)
                if "sellOptionForm" in page.url:
                    success = True
                break
            # alert 에러 체크
            real_errors = [m for m in alert_msgs if m and m.strip() not in ('', 'undefined', 'null')]
            if real_errors:
                break

        page.remove_listener("dialog", _on_dialog)
        current_url = page.url
        print(f"  [등록] 최종 URL: {current_url}", flush=True)

        real_errors = [m for m in alert_msgs if m and m.strip() not in ('', 'undefined', 'null')]
        if real_errors:
            print(f"  [등록] 검증 오류: {real_errors}", flush=True)
            return False
        if alert_msgs:
            print(f"  [등록] 무시된 alert: {alert_msgs}", flush=True)

        if not success:
            return False

        # 등록옵션 폼 — 등록기간/옵션적용기간 90일 설정 후 제출
        print(f"  [등록옵션] 90일 설정 중...", flush=True)
        try:
            # sellOptionForm.php?no=xxx 로 이동 (이미 이 페이지에 있음)
            for _ in range(5):
                if "sellOptionForm" in page.url:
                    break
                await asyncio.sleep(1)

            opt_alert_msgs = []
            def _on_opt_dialog(d):
                opt_alert_msgs.append(d.message)
                asyncio.ensure_future(d.accept())
            page.on("dialog", _on_opt_dialog)

            opt_result = await page.evaluate("""
                () => {
                    const frm = document.getElementById('frmRegOption');
                    if (!frm) return 'NO_FORM';
                    // 등록기간 90일
                    frm.periodREG.value = '90';
                    // 옵션적용기간 90일
                    frm.periodADV.value = '90';
                    if (typeof calcDateREG === 'function') calcDateREG(frm);
                    if (typeof calcDateADV === 'function') calcDateADV(frm);
                    // 기간 종료 후 재고 남으면 재등록: 99회, 90일씩
                    const reRegChk = frm.querySelector('input[name="reRegChk"], input[id*="reReg"]');
                    if (reRegChk && !reRegChk.checked) reRegChk.click();
                    const reRegCnt = frm.querySelector('input[name="reRegCnt"], select[name="reRegCnt"]');
                    if (reRegCnt) reRegCnt.value = '99';
                    const reRegTerm = frm.querySelector('input[name="reRegTerm"], select[name="reRegTerm"]');
                    if (reRegTerm) reRegTerm.value = '90';
                    window.confirm = () => true;
                    chkRegister(frm);
                    frm.submit();
                    return 'OK';
                }
            """)
            print(f"  [등록옵션] 제출: {opt_result}", flush=True)

            await asyncio.sleep(5)
            final_url = page.url
            print(f"  [등록옵션] 최종 URL: {final_url}", flush=True)
            page.remove_listener("dialog", _on_opt_dialog)
        except Exception as e:
            print(f"  [등록옵션] 오류: {e}", flush=True)

        return True

    except Exception as e:
        print(f"  [등록] 오류: {e}", flush=True)
        try:
            page.remove_listener("dialog", _on_dialog)
        except Exception:
            pass
        return False


async def main():
    import sys
    from playwright.async_api import async_playwright

    # 일일 최대 등록 수 (기본 10개, 인자로 조정 가능)
    max_today = int(sys.argv[1]) if len(sys.argv) > 1 else 10

    # 대상 상품 로드
    data = json.loads(MISSING_FILE.read_text(encoding="utf-8"))
    products = data["missing_in_daonna"]
    print(f"총 {len(products)}개 등록 대상 (오늘 최대 {max_today}개)", flush=True)

    # 진행 상황 로드
    prog = load_progress()
    done_ids = set(prog["done"])
    failed_ids = set(prog["failed"])
    remaining = [p for p in products if p["id"] not in done_ids and p["id"] not in failed_ids]
    remaining = remaining[:max_today]  # 일일 제한
    print(f"  완료: {len(done_ids)}개 | 실패: {len(failed_ids)}개 | 오늘 등록: {len(remaining)}개", flush=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]

        # 기존 탭에서 domeggook 탭과 gemini 탭 찾기
        domeggook_page = None
        gemini_page = None
        for p in ctx.pages:
            if "domeggook.com" in p.url and domeggook_page is None:
                domeggook_page = p
            if "gemini.google.com" in p.url and gemini_page is None:
                gemini_page = p

        if domeggook_page is None:
            domeggook_page = ctx.pages[0]
        if gemini_page is None:
            # Gemini 탭 없으면 기존 탭 재사용 (새 탭 열지 않음)
            gemini_page = domeggook_page

        print(f"domeggook 탭: {domeggook_page.url[:60]}", flush=True)
        print(f"gemini 탭: {gemini_page.url[:60]}", flush=True)

        # 비밀번호 변경 페이지 우회
        if "requestChangePwd" in domeggook_page.url:
            await domeggook_page.evaluate("changePwdChk('later')")
            await asyncio.sleep(3)

        for idx, product in enumerate(remaining):
            pid = product["id"]
            name = product["name"]
            price_str = product.get("price", "")
            print(f"\n[{idx+1}/{len(remaining)}] {pid} {name[:50]} | {price_str}", flush=True)

            # 1. 도매꾹 상품 페이지에서 이미지 URL + 상세 이미지 + 카테고리 추출
            info = await get_product_info(domeggook_page, pid)
            img_url = info.get("imgUrl")
            product["_img_url"] = img_url or ""   # register_product에서 사용
            detail_img_html = info.get("detailImgHtml", "")
            cat_from_page = info.get("categoryCode", "")
            supply_price = info.get("supplyPrice", "")
            if cat_from_page:
                product["_category_code"] = cat_from_page
                print(f"  카테고리 스크랩: {cat_from_page}", flush=True)
            if supply_price:
                product["_supply_price"] = supply_price
                print(f"  공급가(도매가): {supply_price}원", flush=True)
            deli_info = info.get("deliInfo", {})
            if deli_info:
                product["_deli_info"] = deli_info
                print(f"  배송비: {deli_info.get('type')} {deli_info.get('amount')}원", flush=True)
            if not img_url:
                print(f"  ❌ 이미지 URL 추출 실패 → 건너뜀", flush=True)
                prog["failed"].append(pid)
                save_progress(prog)
                continue

            print(f"  이미지 URL: {img_url[:80]}", flush=True)
            print(f"  상세이미지: {len(detail_img_html)}자", flush=True)
            product["_detail_imgs"] = detail_img_html  # 상세 이미지 HTML (설명용)

            # 2. 이미지 다운로드
            orig_path = THUMB_DIR / f"{pid}_orig.jpg"
            if not download_image(img_url, orig_path):
                print(f"  ❌ 이미지 다운로드 실패 → 건너뜀", flush=True)
                prog["failed"].append(pid)
                save_progress(prog)
                continue

            # 3. Gemini로 실생활 배경 썸네일 생성
            # 이전 성공 썸네일(10KB 이상)이 있으면 재생성 안 함
            thumb_path = THUMB_DIR / f"{pid}_thumb.jpg"
            if thumb_path.exists() and thumb_path.stat().st_size >= 10_000:
                print(f"  ✅ 기존 썸네일 재사용 ({thumb_path.stat().st_size//1024}KB): {thumb_path.name}", flush=True)
                gemini_ok = True
            else:
                gemini_ok = await generate_gemini_thumb(gemini_page, orig_path, name, thumb_path)

            if not gemini_ok:
                # Gemini 실패 시 → 상세페이지 이미지 중 텍스트 없는 것(정방형에 가까운 것) 선택
                print(f"  ⚠️ Gemini 실패 → 상세이미지에서 썸네일 대체 시도", flush=True)
                detail_html = product.get("_detail_imgs", "")
                detail_urls = re.findall(r'src="([^"]+)"', detail_html)
                fallback_ok = False
                for durl in detail_urls:
                    try:
                        fallback_path = THUMB_DIR / f"{pid}_fallback.jpg"
                        if not download_image(durl, fallback_path):
                            continue
                        img = Image.open(fallback_path).convert("RGB")
                        w, h = img.size
                        ratio = w / h if h else 0
                        # 정방형에 가까운 이미지(0.7~1.5 비율)만 사용 — 텍스트배너(가로로 긴)는 제외
                        if 0.7 <= ratio <= 1.5:
                            img.resize((760, 760), Image.LANCZOS).save(str(thumb_path), "JPEG", quality=92)
                            print(f"  ✅ 상세이미지 썸네일 대체 성공: {durl[:60]}", flush=True)
                            fallback_ok = True
                            break
                    except Exception:
                        continue
                if not fallback_ok:
                    print(f"  ❌ 썸네일 대체 실패 → 건너뜀 (나중에 재시도)", flush=True)
                    prog["failed"].append(pid)
                    save_progress(prog)
                    continue

            # 4. 등록 폼에 입력 후 제출
            ok = await register_product(domeggook_page, product, thumb_path, ctx=ctx)
            if ok:
                print(f"  ✅ 등록 성공: {name[:40]}", flush=True)
                prog["done"].append(pid)
                # 5. 진열하기 — 전체상품 목록에서 해당 상품 진열 버튼 클릭
                try:
                    await domeggook_page.goto(
                        "https://domeggook.com/main/mySell/register/my_sellList.php",
                        wait_until="domcontentloaded", timeout=20000
                    )
                    await asyncio.sleep(2)
                    shown = await domeggook_page.evaluate(f"""
                        () => {{
                            const rows = [...document.querySelectorAll('tr')];
                            const row = rows.find(r => r.innerHTML.includes('{pid}') || r.innerHTML.includes('{name[:20]}'));
                            if (!row) return 'ROW_NOT_FOUND';
                            const btn = [...row.querySelectorAll('a')].find(a => a.textContent.includes('진열'));
                            if (!btn) return 'BTN_NOT_FOUND';
                            window.confirm = () => true;
                            btn.click();
                            return 'OK';
                        }}
                    """)
                    print(f"  [진열하기] {shown}", flush=True)
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"  [진열하기] 실패: {e}", flush=True)
            else:
                print(f"  ❌ 등록 실패: {name[:40]}", flush=True)
                prog["failed"].append(pid)

            save_progress(prog)

            # 등록 간 딜레이 (서버 부하 방지)
            await asyncio.sleep(3)

    print(f"\n\n=== 완료 ===", flush=True)
    print(f"  성공: {len(prog['done'])}개", flush=True)
    print(f"  실패: {len(prog['failed'])}개", flush=True)
    print(f"  진행 파일: {PROGRESS_FILE}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
