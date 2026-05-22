import argparse
import hashlib
import re
import textwrap
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright
from claude_direct import generate_text


BASE_DIR = Path(__file__).parent
OUT_DIR = BASE_DIR / "outputs" / "mrt"


def slugify(text: str) -> str:
    s = re.sub(r"\s+", "-", (text or "").strip().lower())
    s = re.sub(r"[^a-z0-9\-가-힣]", "", s)
    return s[:80] or "mrt"


def _to_blog_image_name(keyword: str, title: str, idx: int) -> str:
    return f"{slugify(keyword)[:40]}-{slugify(title)[:40]}-{idx:02d}.webp"


def extract_offer_url_from_search(page, keyword: str) -> str:
    q = urllib.parse.quote(keyword)
    url = f"https://www.myrealtrip.com/offers?q={q}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    links = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => e.href).filter(h => /myrealtrip\\.com\\/offers\\/\\d+/.test(h) || /experiences\\.myrealtrip\\.com\\/products\\/\\d+/.test(h))",
    )
    seen = []
    for link in links:
        if link not in seen:
            seen.append(link)
    return seen[0] if seen else ""


def crawl_offer(url: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        current = page.url
        ttl = page.title().lower()
        if any(x in current for x in ["404", "not-found"]) or "404" in ttl:
            browser.close()
            raise ValueError(f"유효하지 않은 상품 URL(404): {url}")

        title = page.title().strip()
        full_text = page.inner_text("body")
        text_lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]

        image_urls = page.eval_on_selector_all(
            "img[src]",
            "els => els.map(e => ({src: e.src || '', alt: e.alt || '', w: e.naturalWidth || 0, h: e.naturalHeight || 0})).filter(x => /^https?:/.test(x.src))",
        )
        browser.close()

    cleaned = []
    for ln in text_lines:
        if len(ln) < 2:
            continue
        if any(x in ln.lower() for x in ["로그인", "회원가입", "쿠키", "개인정보처리방침"]):
            continue
        cleaned.append(ln)

    noise_tokens = ["전체 보기", "더 보기", "로그인", "회원가입", "공유", "쿠키", "개인정보", "약관", "다운로드"]
    desc_candidates = [ln for ln in cleaned if len(ln) >= 25 and not any(t in ln for t in noise_tokens)][:40]
    review_candidates = [
        ln for ln in cleaned
        if any(k in ln for k in ["후기", "리뷰", "만족", "추천", "친절", "가이드", "재방문", "대기", "혼잡"])
        and not any(t in ln for t in noise_tokens)
        and not re.search(r"후기\s*[0-9,]+", ln)
    ][:30]

    return {
        "title": title,
        "url": url,
        "description_lines": desc_candidates,
        "review_lines": review_candidates,
        "image_urls": image_urls,
    }


def _is_good_image(meta: dict) -> bool:
    src = (meta.get("src") or "").lower()
    alt = (meta.get("alt") or "").lower()
    w = int(meta.get("w") or 0)
    h = int(meta.get("h") or 0)
    if not src.startswith("http"):
        return False
    bad_tokens = ["logo", "icon", "sprite", "banner", "ads", "footer", "gnb", "avatar", "badge"]
    if any(t in src or t in alt for t in bad_tokens):
        return False
    if min(w, h) and min(w, h) < 480:
        return False
    if w > 0 and h > 0:
        ratio = w / h
        if ratio > 2.3 or ratio < 0.43:
            return False
    path = urlparse(src).path
    if not re.search(r"\.(jpg|jpeg|png|webp)$", path, re.IGNORECASE):
        return False
    return True


def download_convert_all_webp(image_urls: list[dict], seed: str, title: str, img_dir: Path, limit: int = 5) -> list[Path]:
    img_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    seen = set()
    candidates = [m for m in image_urls if _is_good_image(m)]
    out_idx = 1
    for idx, meta in enumerate(candidates, start=1):
        if len(saved) >= limit:
            break
        img_url = meta.get("src", "")
        key = urlparse(img_url).path.lower()
        if key in seen:
            continue
        seen.add(key)
        tmp = img_dir / f"tmp_{idx}.bin"
        try:
            req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=20).read()
            digest = hashlib.sha1((seed + img_url + str(len(raw))).encode()).hexdigest()[:12]
            out = img_dir / _to_blog_image_name(seed, title, out_idx)
            if out.exists():
                out = img_dir / f"{out.stem}-{digest[:4]}.webp"
            tmp.write_bytes(raw)
            with Image.open(tmp) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                w, h = im.size
                if min(w, h) < 480:
                    tmp.unlink(missing_ok=True)
                    continue
                ratio = w / h
                if ratio > 2.3 or ratio < 0.43:
                    tmp.unlink(missing_ok=True)
                    continue
                if w > 1600:
                    im = im.resize((1600, int(h * 1600 / w)), Image.LANCZOS)
                im.save(out, format="WEBP", quality=84, method=6)
            tmp.unlink(missing_ok=True)
            saved.append(out)
            out_idx += 1
        except Exception:
            tmp.unlink(missing_ok=True)
            continue
    return saved


def generate_review_text(data: dict, keyword: str, affiliate_url: str) -> str:
    title = data["title"]
    desc = data["description_lines"][:10]
    rev = data["review_lines"][:10]
    bullets_desc = "\n".join([f"- {x}" for x in desc]) or "- 상품 설명 핵심 정보 추출 실패"
    bullets_rev = "\n".join([f"- {x}" for x in rev]) or "- 리뷰 핵심 포인트 추출 실패"
    highlights = [x for x in rev if len(x) >= 20][:3]
    tips = [x for x in desc if any(k in x for k in ["예약", "시간", "입장", "이용", "주의", "대기"])]
    tips_text = "\n".join([f"- {x}" for x in tips[:4]]) or "- 방문일 혼잡도를 고려해 이른 시간 입장을 권장합니다."
    hi_text = "\n".join([f"- {x}" for x in highlights]) or "- 후기는 대기 시간과 동선에 따라 만족도가 달라진다는 점을 반복적으로 보여줍니다."

    base_context = textwrap.dedent(
        f"""
        [원문 정보]
        제목: {title}
        원문 URL: {data['url']}

        [상품 설명 핵심 정리]
        {bullets_desc}

        [리뷰 포인트 재가공]
        {bullets_rev}

        [여행블로그형 재작성 본문]
        여행 준비를 하다 보면 입장권 하나를 고르는 일도 생각보다 복잡합니다. 이번 상품은 기본 정보가 비교적 명확하고, 후기 데이터가 많아 사전 판단에 유리한 편이었습니다.

        실제 리뷰 흐름을 보면 만족도를 좌우하는 핵심은 두 가지였습니다. 첫째는 방문 시간대, 둘째는 현장 동선입니다. 특히 혼잡 시간대를 피한 이용자일수록 체감 만족도가 높았고, 사전 안내를 꼼꼼히 확인한 경우 현장 변수에 덜 흔들렸습니다.

        리뷰에서 반복적으로 보인 포인트는 아래와 같습니다.
        {hi_text}

        방문 전에는 포함 범위와 이용 조건, 현장 추가 비용 가능성을 함께 체크하는 것이 좋습니다. 단순 최저가 비교보다 전체 동선을 기준으로 선택했을 때 체감 만족도가 높아지는 패턴이 확인됩니다.

        [실전 방문 팁]
        {tips_text}
        """
    ).strip()

    try:
        ai_text = generate_text(
            "",
            blog_id="triplog",
            keyword=keyword or title,
            extra_context=(
                base_context
                + "\n\n[추가 작성 지시]\n"
                + "- 여행자가 실제로 다녀온 듯한 체험형 톤을 유지하세요.\n"
                + "- 동선/대기시간/시간대 팁을 구체적으로 넣어주세요.\n"
                + "- 과장 없이 현실적인 팁 위주로 작성하세요.\n"
                + f"- 입장권 예약하기 링크는 반드시 이 제휴링크만 사용하세요: {affiliate_url}\n"
                + "- myrealtrip.com 원문 URL을 본문 CTA 링크로 직접 쓰지 마세요.\n"
                + "- [Image 1]은 할인쿠폰 배너가 들어갈 자리이므로 쿠폰 클릭 유도 문장을 자연스럽게 포함하세요.\n"
            ),
        )
        if ai_text and len(ai_text) >= 500:
            return ai_text.strip()
    except Exception:
        pass

    return base_context


def to_publish_text(full_text: str, affiliate_url: str) -> str:
    title = ""
    body = ""
    tags = ""

    m_title = re.search(r"===제목===\s*(.*?)\s*===제목끝===", full_text, re.DOTALL)
    if m_title:
        title = m_title.group(1).strip()
    m_body = re.search(r"===본문===\s*(.*?)\s*===본문끝===", full_text, re.DOTALL)
    if m_body:
        body = m_body.group(1).strip()
    m_tags = re.search(r"===태그===\s*(.*?)\s*===태그끝===", full_text, re.DOTALL)
    if m_tags:
        tags = m_tags.group(1).strip()

    if not body:
        return full_text.strip()

    parts = []
    if title:
        parts.append(title)
        parts.append("")
    parts.append(body)
    if tags:
        parts.append("")
        parts.append("태그: " + tags)
    pub = "\n".join(parts).strip()
    pub += (
        "\n\n[쿠폰배너삽입가이드]\n"
        "- [Image 1] 위치에 할인쿠폰 배너 이미지를 삽입하세요.\n"
        f"- 해당 이미지 링크 URL은 제휴링크 사용: {affiliate_url}\n"
    )
    return pub


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", default="오사카", help="검색 키워드")
    parser.add_argument("--offer-url", default="", help="직접 크롤링할 offers URL")
    parser.add_argument("--affiliate", default="https://myrealt.rip/ZYUtd2", help="예약/쿠폰용 제휴 링크")
    parser.add_argument("--headful", action="store_true", help="브라우저 창을 띄워서 크롤링")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_slug = slugify(args.keyword)
    run_dir = OUT_DIR / run_slug
    run_dir.mkdir(parents=True, exist_ok=True)

    offer_url = args.offer_url
    if not offer_url:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.headful)
            page = browser.new_page()
            offer_url = extract_offer_url_from_search(page, args.keyword)
            browser.close()
    if not offer_url:
        raise SystemExit("offers URL을 찾지 못했습니다. --offer-url로 직접 지정하세요.")

    data = crawl_offer(offer_url)
    saved_images = download_convert_all_webp(data["image_urls"], seed=args.keyword, title=data["title"], img_dir=run_dir)
    article = generate_review_text(data, args.keyword, args.affiliate)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = slugify(data["title"])
    txt_path = run_dir / f"{ts}_{slug}.txt"
    txt_path.write_text(article, encoding="utf-8")
    publish_path = run_dir / f"{ts}_{slug}_publish.txt"
    publish_path.write_text(to_publish_text(article, args.affiliate), encoding="utf-8")

    print(f"[완료] TXT 저장: {txt_path}")
    print(f"[완료] 발행용 TXT 저장: {publish_path}")
    print(f"[완료] 이미지 저장: {len(saved_images)}개 -> {run_dir}")
    print(f"[완료] 원문 URL: {offer_url}")


if __name__ == "__main__":
    main()
