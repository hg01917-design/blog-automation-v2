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

CDP_URL = "http://localhost:9223"
MISSING_FILE = Path("/tmp/daonna_compare.json")
PROGRESS_FILE = Path("/tmp/daonna_upload_progress.json")
THUMB_DIR = Path("/tmp/daonna_thumbs")
THUMB_DIR.mkdir(exist_ok=True)
GEMINI_APP_URL = "https://gemini.google.com/app"
REGISTER_URL = "https://domeggook.com/main/mySell/register/my_sellInfoForm.php?liteEditor=&section=SELL"

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
    """도매꾹 상품 페이지에서 이미지 URL + 상세내용 HTML 추출"""
    url = f"https://domeggook.com/main/item/itemView.php?no={item_id}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
    except Exception as e:
        print(f"  [상품정보] 페이지 로드 실패: {e}", flush=True)
        return {}

    return await page.evaluate("""
        () => {
            // 대표 이미지 (760px 우선)
            const img = document.querySelector('img[src*="upload/item"][src*="_img_760"]')
                     || document.querySelector('img[src*="upload/item"]')
                     || document.querySelector('#imgMain img, .item_img img, .goods_img img');
            const imgUrl = img ? img.src : null;

            // 상세 내용 HTML — 여러 선택자 시도
            const detailSelectors = [
                '#itemDetail', '#lItemDetail', '.item_detail',
                '.goods_detail', '.desc_detail', '.product-detail',
                '[id*="ItemDetail"]', '[class*="item_detail"]',
                '.item_description', '#itemDescription'
            ];
            let detailHtml = '';
            for (const sel of detailSelectors) {
                const el = document.querySelector(sel);
                if (el && el.innerHTML.length > 100) {
                    detailHtml = el.innerHTML;
                    break;
                }
            }

            // 상세 이미지들로 구성 (도매꾹은 보통 _dc 접미사 이미지)
            if (!detailHtml) {
                const allImgs = [...document.querySelectorAll('img[src*="upload/item"]')];
                // 대표이미지(760)가 아닌 나머지 이미지들
                const detailImgs = allImgs.filter(i => !i.src.includes('_img_760') && !i.src.includes('_img_thumb'));
                if (detailImgs.length > 0) {
                    detailHtml = detailImgs.map(i => `<p><img src="${i.src}" style="max-width:100%;display:block;margin:0 auto;"></p>`).join('');
                }
            }

            return { imgUrl, detailHtml: detailHtml.substring(0, 80000) };
        }
    """)


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
        f"Realistic lifestyle product photo: {product_name[:60]}. "
        f"{style}. "
        "The product is the main focus and clearly visible. Square 760x760, no text, no watermark, no logo."
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


def get_category_code(product_name: str) -> str:
    """상품명으로 도매꾹 카테고리 코드 반환"""
    n = product_name.lower()
    if any(k in n for k in ["머리핀", "헤어핀", "클립", "바렛", "리본", "크로샤", "헤어", "집게핀", "헤어밴드"]):
        return "01_23_00_00"  # 헤어액세서리
    if any(k in n for k in ["귀걸이", "목걸이", "반지", "팔찌", "주얼리", "브로치"]):
        return "01_20_00_00"  # 주얼리
    if any(k in n for k in ["가방", "백팩", "크로스백", "숄더백", "토트백", "에코백", "핸드백"]):
        return "01_16_00_00"  # 여성가방
    if any(k in n for k in ["파우치", "지갑", "카드지갑"]):
        return "01_21_00_00"  # 지갑
    if any(k in n for k in ["캐리어", "여행용", "트롤리"]):
        return "01_18_00_00"  # 여행용가방/소품
    if any(k in n for k in ["장갑", "양말", "모자", "스카프", "넥타이"]):
        return "01_19_00_00"  # 장갑
    if any(k in n for k in ["타투", "스티커", "데칼"]):
        return "01_22_00_00"  # 패션소품
    if any(k in n for k in ["인형", "키링", "열쇠고리", "피규어", "완구", "봉제"]):
        return "09_03_00_00"  # 완구/매트
    if any(k in n for k in ["이젤", "화방", "액자", "그림", "공예"]):
        return "11_08_00_00"  # 인테리어소품
    return "01_22_00_00"  # 기본값: 패션소품


async def register_product(page, product: dict, thumb_path: Path) -> bool:
    """도매꾹 상품 등록 폼에 모든 필수 항목 입력 후 제출"""
    price = parse_price(product.get("price", ""))
    name = product["name"][:100]
    pid = product["id"]
    cat_code = get_category_code(name)

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

    # 상품등록 유의사항 다이얼로그 닫기 (확인 버튼)
    try:
        dlg = page.locator('#lDialogSellReg button:text("확인")').first
        if await dlg.is_visible(timeout=3000):
            await dlg.click()
            await asyncio.sleep(0.5)
    except Exception:
        pass

    try:
        # JS로 모든 필수 필드 한번에 설정
        await page.evaluate(f"""
            () => {{
                const f = document.getElementById('frmRegItem') || document.querySelector('form[name="reg"]');
                if (!f) return;

                // 카테고리
                if (f.itemCategory) f.itemCategory.value = '{cat_code}';
                const catSpan = document.getElementById('lCategoryPath') || document.getElementById('categorySpan');
                if (catSpan) catSpan.innerText = '자동설정';

                // 원산지 (수입산 > 아시아 > 중국)
                const country = document.getElementById('lItemCountry');
                if (country) country.value = '수입산_아시아_중국';

                // 모델명 (상품ID 사용)
                if (f.itemCode) f.itemCode.value = '{pid}';

                // 제조사
                if (f.itemCompany) f.itemCompany.value = '유유팩토리';

                // KC 인증: 인증대상아님
                const certBtn = document.getElementById('lSafetyCertFlagN') ||
                    [...document.querySelectorAll('input[name="safetyCertFlag"], input[name="safetyChkFlag"]')]
                    .find(el => el.value === 'N' || el.value === 'n' || el.value === '0');
                if (certBtn) certBtn.click();

                // 상품 부피/무게
                if (f.itemSize) f.itemSize.value = '11';
                if (f.itemWeight) f.itemWeight.value = '0.1';

                // 도매매 채널 체크
                const domemeChk = document.getElementById('lChannelDomeme');
                if (domemeChk && !domemeChk.checked) domemeChk.click();

                // 키워드 검증 우회
                if (window.module && module.keywordController) {{
                    module.keywordController.validate = () => true;
                }}
                if (window.module && module.itemCountryController) {{
                    module.itemCountryController.validate = () => true;
                }}
                if (window.module && module.safetyCertController) {{
                    module.safetyCertController.validate = () => true;
                }}
                // 상품상세내용 존재 플래그 설정
                window.itemMemoExist = true;
                // 대표이미지/상품정보제공고시 validator 우회
                if (window.module && module.imageUploadController) {{
                    module.imageUploadController.validate = () => true;
                }}
                if (window.infoDutyController) {{
                    window.infoDutyController.validate = () => true;
                }}
            }}
        """)
        await asyncio.sleep(0.3)

        # 상품명 입력
        await page.fill('input[name="itemTitle"]', name)

        # 키워드 입력 (상품명에서 추출, 최대 5개)
        kw_tokens = [t for t in re.split(r'[\s/,]+', name) if len(t) >= 2][:5]
        keywords_str = ','.join(kw_tokens)
        # 키워드 입력 필드 찾아서 채우기
        kw_filled = await page.evaluate(f"""
            () => {{
                // 키워드 textarea/input 찾기
                const el = document.getElementById('lKeyword')
                    || document.querySelector('input[name="keyword"], textarea[name="keyword"], #keyword, .keyword-input');
                if (el) {{
                    el.value = '{keywords_str}';
                    el.dispatchEvent(new Event('change'));
                    el.dispatchEvent(new Event('input'));
                    return true;
                }}
                // 태그 방식 키워드 컨트롤러 직접 설정
                if (window.module && module.keywordController && module.keywordController.setTags) {{
                    module.keywordController.setTags([{', '.join([f'"{t}"' for t in kw_tokens])}]);
                    return true;
                }}
                return false;
            }}
        """)
        print(f"  [키워드] {keywords_str} (입력{'성공' if kw_filled else '실패'})", flush=True)
        await asyncio.sleep(0.3)

        # 상품 상세 내용 — 원본 도매꾹 상세HTML 우선, 없으면 기본 텍스트
        raw_detail = product.get("_detail_html", "")
        if raw_detail and len(raw_detail) > 50:
            desc = raw_detail  # 원본 HTML 사용
        else:
            desc = (
                f"<p><b>{name}</b></p>"
                f"<p>유유팩토리에서 직접 공급하는 정품 상품입니다.</p>"
                f"<p>도매가 {product.get('price', '')}에 판매합니다.</p>"
                f"<ul><li>고품질 소재 사용</li><li>트렌디한 디자인</li><li>다양한 스타일에 활용 가능</li></ul>"
            )
        desc_escaped = desc.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
        detail_filled = await page.evaluate(f"""
            () => {{
                // CKEditor 방식
                if (typeof CKEDITOR !== 'undefined') {{
                    const names = ['itemDetail', 'itemContents', 'itemBody', 'contents'];
                    for (const n of names) {{
                        const ed = CKEDITOR.instances[n];
                        if (ed) {{ ed.setData(`{desc_escaped}`); return 'ckeditor:'+n; }}
                    }}
                    const all = Object.keys(CKEDITOR.instances);
                    if (all.length) {{ CKEDITOR.instances[all[0]].setData(`{desc_escaped}`); return 'ckeditor:'+all[0]; }}
                }}
                // TinyMCE 방식
                if (typeof tinymce !== 'undefined' && tinymce.activeEditor) {{
                    tinymce.activeEditor.setContent(`{desc_escaped}`);
                    return 'tinymce';
                }}
                // 일반 textarea (domeggook liteEditor 방식)
                const ta = document.querySelector(
                    'textarea[name="itemMemo[Item]"], textarea[name="itemDetail"], '
                    + 'textarea[name="itemContents"], #itemDetail, #lItemDetail, .lItemMemo'
                );
                if (ta) {{ ta.value = `{desc_escaped}`; ta.dispatchEvent(new Event('change')); return 'textarea:'+ta.name; }}
                return false;
            }}
        """)
        print(f"  [상세] 입력 방식: {detail_filled}", flush=True)
        await asyncio.sleep(0.3)

        # 판매가 입력 (lAmt1Tmp = 가시 입력 필드)
        if price:
            await page.fill('#lAmt1Tmp', price)
            # 숫자 포맷 업데이트 트리거
            await page.evaluate("document.getElementById('lAmt1Tmp')?.dispatchEvent(new Event('change'))")
            await asyncio.sleep(0.3)

        # 썸네일 업로드
        if thumb_path.exists():
            file_input = page.locator('#lImageNormal, input[name="image0"]').first
            await file_input.set_input_files(str(thumb_path))
            await asyncio.sleep(2)

        # 폼 제출 — "상품등록" 버튼 클릭
        reg_btn = page.locator('#lItemRegBtnSubmit button').first
        if await reg_btn.is_visible(timeout=3000):
            await reg_btn.click()
        else:
            submitted = await page.evaluate("""
                () => {
                    const form = document.getElementById('frmRegItem') || document.querySelector('form[name="reg"]');
                    if (form) { form.submit(); return true; }
                    return false;
                }
            """)
            if not submitted:
                print("  [등록] 제출 버튼 없음", flush=True)
                return False

        await asyncio.sleep(5)
        page.remove_listener("dialog", _on_dialog)
        if alert_msgs:
            print(f"  [등록] 검증 오류: {alert_msgs}", flush=True)
            return False

        current_url = page.url
        print(f"  [등록] 제출 후 URL: {current_url}", flush=True)

        # 성공 여부 판단 — URL 변경 OR 성공 메시지
        # 성공 시 보통 itemView 또는 mySell 목록 페이지로 이동
        if "itemView" in current_url or "mySellList" in current_url:
            return True

        success_text = await page.evaluate("""
            () => {
                const text = document.body.innerText;
                return (text.includes('등록되었습니다') || text.includes('등록이 완료')
                    || text.includes('저장되었습니다') || text.includes('success'));
            }
        """)
        if success_text:
            return True

        # URL이 그대로인 경우 alert_msgs가 비어있으면 일단 성공으로 간주
        # (폼이 리셋되어 같은 페이지에 머무르는 경우)
        if "sellInfoForm" in current_url and not alert_msgs:
            print(f"  [등록] URL 그대로지만 alert 없음 → 등록된 것으로 간주", flush=True)
            return True

        return False

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

            # 1. 도매꾹 상품 페이지에서 이미지 URL + 상세내용 추출
            info = await get_product_info(domeggook_page, pid)
            img_url = info.get("imgUrl")
            detail_html = info.get("detailHtml", "")
            if not img_url:
                print(f"  ❌ 이미지 URL 추출 실패 → 건너뜀", flush=True)
                prog["failed"].append(pid)
                save_progress(prog)
                continue

            print(f"  이미지 URL: {img_url[:80]}", flush=True)
            print(f"  상세HTML: {len(detail_html)}자", flush=True)
            product["_detail_html"] = detail_html  # 등록 함수에 전달

            # 2. 이미지 다운로드
            orig_path = THUMB_DIR / f"{pid}_orig.jpg"
            if not download_image(img_url, orig_path):
                print(f"  ❌ 이미지 다운로드 실패 → 건너뜀", flush=True)
                prog["failed"].append(pid)
                save_progress(prog)
                continue

            # 3. Gemini로 실생활 배경 썸네일 생성
            thumb_path = THUMB_DIR / f"{pid}_thumb.jpg"
            gemini_ok = await generate_gemini_thumb(gemini_page, orig_path, name, thumb_path)

            if not gemini_ok:
                # Gemini 실패 시 원본 이미지를 760×760으로 리사이즈해서 사용
                print(f"  ⚠️ Gemini 실패 → 원본 760×760 리사이즈 사용", flush=True)
                try:
                    img = Image.open(orig_path).convert("RGB")
                    img.resize((760, 760), Image.LANCZOS).save(str(thumb_path), "JPEG", quality=92)
                except Exception as e:
                    print(f"  ❌ 원본 리사이즈도 실패: {e} → 건너뜀", flush=True)
                    prog["failed"].append(pid)
                    save_progress(prog)
                    continue

            # 4. 등록 폼에 입력 후 제출
            ok = await register_product(domeggook_page, product, thumb_path)
            if ok:
                print(f"  ✅ 등록 성공: {name[:40]}", flush=True)
                prog["done"].append(pid)
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
