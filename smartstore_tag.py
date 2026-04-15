"""스마트스토어 상품 태그 자동 추가 스크립트"""
import sys, re, json, time, os
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')
from browser import connect_cdp

def close_all_modals(page):
    """열린 모달 모두 닫기"""
    for _ in range(10):
        try:
            result = page.evaluate("""
            () => {
                const modal = document.querySelector('.modal.in');
                if (!modal) return false;
                // 확인 버튼 또는 X 버튼 클릭
                const btn = modal.querySelector('.btn-primary, button[type="button"]');
                if (btn) { btn.click(); return true; }
                // ESC 키로 닫기
                modal.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
                return true;
            }
            """)
            if not result:
                break
            page.wait_for_timeout(400)
        except Exception:
            break

def load_tags_for_keyword(page, keyword):
    """키워드로 태그 검색 API 호출"""
    page.evaluate(f"""
    () => {{
        window._kwTags = null;
        const s = Array.from(document.querySelectorAll('select')).find(s=>s.selectize&&s.multiple);
        if (!s) return;
        s.selectize.settings.load('{keyword}', data => {{
            window._kwTags = data || [];
        }});
    }}
    """)
    page.wait_for_timeout(1800)
    return page.evaluate("() => window._kwTags") or []

def add_tag(page, tag_code, tag_text):
    """태그 하나 추가. 성공=True, 최대초과=None, 실패=False"""
    page.evaluate(f"""
    () => {{
        const s = Array.from(document.querySelectorAll('select')).find(s=>s.selectize&&s.multiple);
        if (!s) return;
        s.selectize.addOption({{code: {tag_code}, text: '{tag_text}'}});
        s.selectize.addItem({tag_code}, false);
    }}
    """)
    page.wait_for_timeout(600)

    modal = page.query_selector('.modal.in')
    if not modal:
        return True  # 성공

    modal_text = page.evaluate("() => { const m=document.querySelector('.modal.in'); return m?m.textContent:''; }")
    close_all_modals(page)

    if '최대 10개' in modal_text:
        return None  # 최대치 도달
    elif '동일한 태그' in modal_text:
        return 'dup'  # 중복
    else:
        return False  # 불가 태그

def process_product(page, product_id, product_name):
    """상품 하나에 태그 추가 후 저장. 반환: (성공여부, 추가된태그수)"""
    print(f"\n[{product_id}] {product_name}")

    page.goto(f'https://sell.smartstore.naver.com/#/products/edit/{product_id}',
              wait_until='domcontentloaded', timeout=30000)

    try:
        page.wait_for_selector('input[name="product.name"]', timeout=12000)
    except Exception:
        print("  → 페이지 로드 실패")
        return False, 0
    # 상품명 필드 + 제목줄 태그가 이 상품으로 업데이트될 때까지 대기
    expected_word = product_name.split()[0] if product_name.split() else product_name[:4]
    for _ in range(30):
        val = page.evaluate("() => { const i=document.querySelector('input[name=\"product.name\"]'); return i?i.value:''; }")
        if val and expected_word in val:
            break
        page.wait_for_timeout(500)
    page.wait_for_timeout(3000)  # Angular 바인딩 완료 대기

    WRONG_TAG_SET = {'학교용품','선물용','학용품펜','행사용','겨울','크리스마스','크리스마스선물','답례용','인형볼펜','크리스마스장식'}

    # 섹션 제목줄에서 현재 태그 확인 (섹션 닫힌 상태에서 태그 요약 표시됨 — 가장 신뢰할 수 있음)
    title_text = page.evaluate("""
    () => {
        for (const sec of document.querySelectorAll('.form-section')) {
            if (!sec.textContent.includes('검색설정')) continue;
            const tl = sec.querySelector('.title-line');
            return tl ? tl.textContent.trim() : '';
        }
        return '';
    }
    """)
    # 태그 목록 파싱: 태그(태그1,태그2,...) 형식
    tag_match = re.search(r'태그\(([^)]+)\)', title_text)
    existing_tag_texts = [t.strip() for t in tag_match.group(1).split(',') if t.strip()] if tag_match else []
    existing_tags = set(existing_tag_texts)
    tag_count = len(existing_tags)

    need_replace = False
    if existing_tags == WRONG_TAG_SET:
        print(f"  → 잘못된 일괄태그 감지, 교체 필요")
        need_replace = True
    elif tag_count >= 5:
        print(f"  → 태그 충분({tag_count}개): {','.join(list(existing_tags)[:5])}")
        return True, 0
    elif tag_count > 0:
        print(f"  → 태그 부족({tag_count}개), 추가 필요: {','.join(existing_tag_texts)}")

    # 검색설정 섹션 열기
    page.evaluate("""
    () => {
        for (const s of document.querySelectorAll('.form-section')) {
            if (!s.textContent.includes('검색설정')) continue;
            const tl = s.querySelector('.title-line');
            const inp = s.querySelector('[placeholder="태그를 입력해주세요."]');
            if (!inp || inp.getBoundingClientRect().height === 0) { tl && tl.click(); }
            return;
        }
    }
    """)
    page.wait_for_timeout(2000)

    # 태그 input 확인
    inp = page.query_selector('[placeholder="태그를 입력해주세요."]')
    if not inp:
        print("  → 태그 입력 필드 없음")
        return False, 0

    # 모달 닫기 후 클릭 (모달이 입력 필드를 가리는 경우 대비)
    close_all_modals(page)
    inp.scroll_into_view_if_needed()
    page.evaluate("() => { const i=document.querySelector('[placeholder=\"태그를 입력해주세요.\"]'); if(i) i.click(); }")
    page.wait_for_timeout(300)

    # 잘못된 태그 교체 시: 기존 태그 모두 삭제 버튼 클릭
    if need_replace:
        for _ in range(15):
            deleted = page.evaluate("""
            () => {
                const sec = Array.from(document.querySelectorAll('.form-section')).find(s=>s.textContent.includes('검색설정'));
                const btn = sec ? sec.querySelector('a[ng-click*="deleteTag"]') : null;
                if (btn) { btn.click(); return true; }
                return false;
            }
            """)
            if not deleted:
                break
            page.wait_for_timeout(300)
        page.wait_for_timeout(300)

    # 상품명 키워드 추출
    keywords = [w for w in product_name.split() if len(w) >= 2]
    # 추가 키워드 (상품명 전체도 검색)
    if product_name not in keywords:
        keywords = [product_name.replace(' ', '')] + keywords

    # 태그 수집 및 추가
    added_tags = []
    seen = set()

    for kw in keywords[:8]:
        if len(added_tags) >= 10:
            break

        tags = load_tags_for_keyword(page, kw[:10])  # 최대 10자

        for t in tags:
            if len(added_tags) >= 10:
                break
            if t['code'] in seen:
                continue
            seen.add(t['code'])

            result = add_tag(page, t['code'], t['text'])
            if result is None:  # 최대치
                print(f"  → 최대 10개 도달")
                break
            elif result == True:
                added_tags.append(t['text'])
                print(f"  ✓ 태그 추가: {t['text']}")
            elif result == 'dup':
                added_tags.append(t['text'] + '(기존)')
            # False는 불가 태그, 스킵

        if len(added_tags) >= 10 or (added_tags and result is None):
            break

    if not added_tags:
        print("  → 유효한 태그 없음")
        return False, 0

    # 저장
    page.wait_for_timeout(500)
    save_btn = page.query_selector('button:has-text("저장하기")')
    if not save_btn:
        print("  → 저장 버튼 없음")
        return False, len(added_tags)

    close_all_modals(page)
    page.evaluate("() => { const b=document.querySelector('button'); const btns=Array.from(document.querySelectorAll('button')); const sb=btns.find(b=>b.textContent.includes('저장하기')); if(sb) sb.click(); }")
    page.wait_for_timeout(3000)

    # 저장 완료 확인
    body_after = page.inner_text('body')
    if '저장' in body_after or '완료' in body_after:
        print(f"  → 저장 완료 (태그 {len([t for t in added_tags if '(기존)' not in t])}개 추가)")
        return True, len([t for t in added_tags if '(기존)' not in t])

    # 저장 모달 처리
    modal = page.query_selector('.modal.in')
    if modal:
        modal_text = page.evaluate("() => { const m=document.querySelector('.modal.in'); return m?m.textContent:''; }")
        print(f"  → 저장 모달: {modal_text.strip()[:60]}")
        close_all_modals(page)

    page.wait_for_timeout(2000)
    return True, len([t for t in added_tags if '(기존)' not in t])


if __name__ == '__main__':
    pw, browser = connect_cdp()
    context = browser.contexts[0]

    # 상품 목록 로드 — API 직접 호출로 전체 상품 수집
    list_page = context.new_page()
    list_page.goto('https://sell.smartstore.naver.com/#/products/origin-list',
                   wait_until='domcontentloaded', timeout=30000)
    list_page.wait_for_timeout(3000)
    list_page.click('button:has-text("초기화")')
    list_page.wait_for_timeout(1000)
    list_page.click('button:has-text("전체")')
    list_page.wait_for_timeout(500)

    # API 요청 페이로드 캡처
    captured_payload = [None]
    def on_req(req):
        if 'api/products/list/search' in req.url:
            captured_payload[0] = req.post_data
    list_page.on('request', on_req)
    list_page.click('button:has-text("검색")')
    list_page.wait_for_timeout(6000)

    # 전체 상품 수집 (페이지별 API 호출)
    products = []
    if captured_payload[0]:
        base_payload = json.loads(captured_payload[0])
        page_num = 0
        while True:
            base_payload['page'] = page_num
            result = list_page.evaluate(f"""
            async () => {{
                const resp = await fetch('/api/products/list/search', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({json.dumps(base_payload)})
                }});
                if (!resp.ok) return null;
                const data = await resp.json();
                return data.content ? data.content.map(p=>({{'id':p.id,'name':p.productName}})) : [];
            }}
            """)
            if not result:
                break
            products.extend(result)
            if len(result) < 100:
                break
            page_num += 1
    else:
        # 폴백: ag-grid에서 수집
        products = list_page.evaluate("""
        () => {
            const gridDiv = document.querySelector('.ag-root-wrapper');
            if (!gridDiv) return [];
            const api = gridDiv.__agComponent.gridApi;
            const rows = [];
            api.forEachNode(n => { if(n.data) rows.push({id: n.data.id, name: n.data.productName}); });
            return rows;
        }
        """)
    list_page.close()

    # 이전 진행 상황 로드 (재시작 시 스킵 가능)
    PROGRESS_FILE = '/tmp/smartstore_tag_progress.json'
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            done_ids = set(json.load(f))
        print(f"이전 진행 {len(done_ids)}개 건너뜀")
    else:
        done_ids = set()

    print(f"총 {len(products)}개 상품 처리 시작")

    total_added = 0
    total_processed = 0

    for i, prod in enumerate(products):
        pid = prod['id']
        name = prod['name']

        if pid in done_ids:
            print(f"[{pid}] 이전 완료, 스킵")
            continue

        # 각 상품마다 새 탭 사용 — Angular 라우터 DOM 캐시 문제 방지
        prod_page = context.new_page()
        try:
            success, count = process_product(prod_page, pid, name)
        except Exception as e:
            print(f"  → 오류 발생: {e}")
            count = 0
        finally:
            prod_page.close()

        total_processed += 1
        total_added += count
        done_ids.add(pid)

        # 진행 저장
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(list(done_ids), f)

        if (i + 1) % 10 == 0:
            print(f"\n=== 진행: {i+1}/{len(products)}, 태그 추가/교체: {total_added}개 ===\n")

    print(f"\n완료: 상품 {total_processed}개 처리, 태그 {total_added}개 추가/교체")
