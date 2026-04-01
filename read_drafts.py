"""
read_drafts.py
각 블로그의 임시저장 글 내용을 읽어서 출력 (발행 X)
"""
import sys
import time
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp, get_or_create_page
from login_playwright import login_blog
from config import ACCOUNT_MAP

def _log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

SKIP_TITLES = {'제목 없음', '토스 행운퀴즈', '[내용 없음]'}


def read_tistory_drafts(blog_id: str, max_drafts: int = 3):
    """Tistory 블로그 임시저장 글 내용 읽기"""
    _log(f"=== {blog_id} 임시저장 글 확인 ===")

    # 로그인
    ok = login_blog(blog_id, on_log=_log)
    if not ok:
        _log(f"[{blog_id}] 로그인 실패")
        return []
    time.sleep(2)

    pw, browser = connect_cdp(on_log=_log)
    try:
        page = get_or_create_page(browser)

        editor_url = f"https://{blog_id}.tistory.com/manage/newpost/"
        page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # 임시저장 버튼 클릭
        count_btn = page.query_selector('a.count[aria-label*="임시저장"]')
        if not count_btn:
            _log(f"[{blog_id}] 임시저장 버튼 없음")
            return []

        count_text = count_btn.text_content() or ''
        _log(f"[{blog_id}] 임시저장: {count_text.strip()}")
        count_btn.click()
        time.sleep(2)

        # 드래프트 목록
        links = page.query_selector_all('a.link_info')
        _log(f"[{blog_id}] 드래프트 {len(links)}개 발견")

        # 드래프트 목록에서 유효한 제목들 수집 (element handle 저장 X)
        draft_titles = []
        for link in links:
            try:
                t = (link.text_content() or '').strip()
                if t and t not in SKIP_TITLES and '규칙 확인' not in t and '[내용 없음]' not in t:
                    draft_titles.append(t)
            except:
                pass

        _log(f"[{blog_id}] 유효 드래프트 제목 {len(draft_titles)}개: {draft_titles[:5]}")

        drafts = []

        for idx, target_title in enumerate(draft_titles[:max_drafts]):
            # 매번 에디터 페이지로 돌아가서 드래프트 목록 재오픈
            page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            count_btn2 = page.query_selector('a.count[aria-label*="임시저장"]')
            if not count_btn2:
                break
            count_btn2.click()
            time.sleep(2)

            # 제목으로 해당 링크 찾기
            fresh_links = page.query_selector_all('a.link_info')
            clicked = False
            for link in fresh_links:
                try:
                    t = (link.text_content() or '').strip()
                    if t == target_title:
                        _log(f"  드래프트 [{idx+1}] 로드: '{target_title}'")
                        link.click()
                        time.sleep(5)
                        clicked = True
                        break
                except:
                    pass

            if not clicked:
                _log(f"  드래프트 [{idx+1}] '{target_title}' 못 찾음 — 첫 번째 항목 클릭")
                fresh_links2 = page.query_selector_all('a.link_info')
                for link in fresh_links2:
                    try:
                        t = (link.text_content() or '').strip()
                        if t and t not in SKIP_TITLES:
                            link.click()
                            time.sleep(5)
                            break
                    except:
                        pass

            # 내용 읽기
            try:
                content = page.evaluate("() => tinymce.activeEditor ? tinymce.activeEditor.getContent() : ''")
            except:
                content = ""

            # 제목
            try:
                title_el = page.query_selector('#post-title-inp') or page.query_selector('#title')
                actual_title = title_el.input_value() if title_el else target_title
            except:
                actual_title = target_title

            # 태그
            try:
                tag_val = page.evaluate("() => document.getElementById('tagText')?.value || ''")
            except:
                tag_val = ""

            # 분석
            clean_text = re.sub(r'<[^>]+>', '', content)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            char_count = len(clean_text)
            img_count = content.count('[##_Image') + len(re.findall(r'<img\s', content))

            # 품질 평가
            quality = "✓"
            issues = []
            if char_count < 1700:
                issues.append(f"글자수 부족({char_count}자)")
                quality = "✗"
            if img_count < 3:
                issues.append(f"이미지 부족({img_count}개)")
                quality = "⚠" if quality == "✓" else quality
            if not tag_val.strip():
                issues.append("태그 없음")
                quality = "⚠" if quality == "✓" else quality

            draft_info = {
                'index': idx,
                'title': actual_title,
                'char_count': char_count,
                'img_count': img_count,
                'tags': tag_val,
                'quality': quality,
                'issues': issues,
                'preview': clean_text[:800],
            }
            drafts.append(draft_info)

            _log(f"    {quality} 제목: {actual_title}")
            _log(f"    글자수: {char_count}자 | 이미지: {img_count}개 | 태그: {tag_val[:60] or '(없음)'}")
            if issues:
                _log(f"    문제: {', '.join(issues)}")
            _log(f"    내용 미리보기: {clean_text[:300]}")
            _log("")

        return drafts

    finally:
        pw.stop()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else 'all'

    results = {}

    if target in ('all', 'goodisak'):
        results['goodisak'] = read_tistory_drafts('goodisak', max_drafts=5)

    if target in ('all', 'nolja100'):
        results['nolja100'] = read_tistory_drafts('nolja100', max_drafts=5)

    # 요약 출력
    _log("\n========== 임시저장 글 요약 ==========")
    for blog_id, drafts in results.items():
        _log(f"\n[{blog_id}] {len(drafts)}개 확인")
        for d in drafts:
            _log(f"  {d['quality']} {d['title']} ({d['char_count']}자, 이미지{d['img_count']}개)")
            if d['issues']:
                _log(f"     → {', '.join(d['issues'])}")

    # JSON 저장
    out = Path("draft_review.json")
    save_data = {k: [{kk: vv for kk, vv in d.items() if kk != 'preview'} for d in v]
                 for k, v in results.items()}
    out.write_text(json.dumps(save_data, ensure_ascii=False, indent=2))
    _log(f"\n결과 저장: {out}")
