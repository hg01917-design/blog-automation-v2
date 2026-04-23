"""Bing 현재 페이지 DOM 구조 분석"""
import sys
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')
from browser import connect_cdp, get_or_create_page

pw, browser = connect_cdp()

# 현재 열린 Bing 탭 찾기
bing_page = None
for ctx in browser.contexts:
    for p in ctx.pages:
        if 'bing.com' in p.url:
            bing_page = p
            print(f"탭 발견: {p.url[:100]}")
            break

if not bing_page:
    print("Bing 탭 없음")
    pw.stop()
    exit()

# 이미지 관련 클래스/셀렉터 탐색
result = bing_page.evaluate("""() => {
    const info = {};
    // 이미지 요소 탐색
    const imgs = document.querySelectorAll('img');
    info.total_imgs = imgs.length;

    // 큰 이미지만 (100px 이상)
    const big_imgs = [...imgs].filter(img => {
        const r = img.getBoundingClientRect();
        return r.width > 100 && r.height > 100;
    });
    info.big_imgs = big_imgs.map(img => ({
        src: (img.src || img.getAttribute('src') || '').substring(0, 100),
        alt: img.alt || '',
        class: img.className || '',
        parent_class: img.parentElement ? img.parentElement.className : '',
        grandparent_class: img.parentElement && img.parentElement.parentElement ? img.parentElement.parentElement.className : '',
    }));

    // 다운로드 링크/버튼 탐색
    const dl_links = [...document.querySelectorAll('a[download], [class*="download"], [class*="dl"], [aria-label*="download"], [aria-label*="다운"]')];
    info.dl_elements = dl_links.slice(0, 10).map(el => ({
        tag: el.tagName,
        class: el.className.substring(0, 80),
        href: (el.href || '').substring(0, 80),
        aria: el.getAttribute('aria-label') || '',
    }));

    return info;
}""")

print(f"\n총 이미지: {result['total_imgs']}개")
print(f"큰 이미지 ({len(result['big_imgs'])}개):")
for img in result['big_imgs']:
    print(f"  src: {img['src']}")
    print(f"  alt: {img['alt'][:60]}")
    print(f"  class: {img['class'][:60]}")
    print(f"  parent: {img['parent_class'][:60]}")
    print(f"  grandparent: {img['grandparent_class'][:60]}")
    print()

print(f"다운로드 요소 ({len(result['dl_elements'])}개):")
for el in result['dl_elements']:
    print(f"  {el['tag']} class='{el['class']}' aria='{el['aria']}' href='{el['href']}'")

pw.stop()
