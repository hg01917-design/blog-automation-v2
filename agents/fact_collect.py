"""사전 팩트 수집 — 키워드 → 팩트 쿼리 변환 → 공식 페이지 직접 방문 → 수치/조건 추출"""
import re
import sys
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from browser import connect_cdp

# ── 키워드 → 팩트 쿼리 변환 테이블 ────────────────────────────────────────
# 블로그 키워드(SEO용)와 실제 팩트 조회 쿼리는 다름
# 예: "다자녀 전기요금 할인 몇 자녀부터" → "한전 다자녀 전기요금 할인 조건 자녀수 금액"
_FACT_QUERIES = [
    # 전기요금
    (["전기요금", "전기세", "전기비", "누진세", "누진요금", "kWh", "kwh"],
     "한전 주택용 전기요금 누진세 구간 금액 2026 site:kepco.co.kr OR site:한전.com"),
    (["다자녀 전기", "전기 할인", "전기요금 할인"],
     "한전 다자녀 전기요금 할인 자녀수 기준 할인금액 신청방법 site:kepco.co.kr"),
    (["절약", "전기 절약", "전기요금 줄이기"],
     "한전 가정용 전기요금 절약 방법 누진세 구간 절감 금액"),

    # 가스/난방
    (["가스요금", "도시가스", "가스비", "난방비"],
     "도시가스 요금 단가 MJ 2026 가스공사 site:kogas.or.kr"),

    # 통신비
    (["알뜰폰", "통신비", "요금제"],
     "알뜰폰 요금제 비교 월정액 데이터 통화 2026 site:mvno.or.kr"),

    # 관리비/수도
    (["관리비", "관리비 절약"],
     "아파트 관리비 항목 절약 방법 평균 금액"),
    (["수도요금", "수도세"],
     "수도요금 체계 사용량 구간 금액 절약 방법"),

    # 건강보험
    (["건강보험료", "건보료"],
     "건강보험료 계산 직장 지역 보험료율 2026 site:nhis.or.kr"),
    (["피부양자", "건강보험 피부양자"],
     "건강보험 피부양자 등록 조건 소득 재산 기준 2026 site:nhis.or.kr"),

    # 실업급여/고용보험
    (["실업급여", "구직급여"],
     "실업급여 수급액 계산 지급기간 상한액 하한액 2026 site:ei.go.kr"),
    (["실업인정", "실업급여 신청"],
     "실업급여 실업인정 신청 방법 고용24 온라인 절차 site:ei.go.kr"),

    # 육아/출산
    (["육아휴직", "육아휴직 급여"],
     "육아휴직 급여 지원금액 신청방법 상한액 2026 site:ei.go.kr"),
    (["출산", "출산급여", "출산휴가"],
     "출산휴가 급여 지원금액 신청방법 2026 site:ei.go.kr"),
    (["자녀장려금"],
     "자녀장려금 지원금액 신청자격 소득기준 2026 site:nts.go.kr"),

    # 연말정산
    (["연말정산", "세액공제", "월세공제"],
     "연말정산 세액공제 항목 한도 금액 2026 site:nts.go.kr"),

    # 소상공인/자영업
    (["소상공인", "소상공인 지원"],
     "소상공인 지원금 신청자격 지원금액 2026 site:semas.or.kr OR site:mss.go.kr"),

    # 기초생활/복지
    (["기초생활", "기초수급"],
     "기초생활수급자 선정기준 급여 지원금액 2026 site:mohw.go.kr OR site:bokjiro.go.kr"),
    (["차상위", "차상위계층"],
     "차상위계층 선정기준 혜택 지원내용 2026 site:bokjiro.go.kr"),
    (["지원금", "복지급여", "보조금"],
     "정부지원금 복지급여 신청자격 금액 2026 site:bokjiro.go.kr"),

    # 국민연금
    (["국민연금", "노령연금"],
     "국민연금 수령액 계산 납부액 2026 site:nps.or.kr"),

    # 장기수선충당금
    (["장기수선충당금", "이사비용"],
     "장기수선충당금 반환 조건 신청방법 이사"),

    # IT 제품 스펙/가격
    (["갤럭시", "삼성"],
     "삼성 갤럭시 공식 스펙 가격 site:samsung.com/kr"),
    (["아이폰", "맥북", "아이패드"],
     "애플 공식 스펙 가격 site:apple.com/kr"),
    (["LG", "그램"],
     "LG 공식 스펙 가격 site:lg.com/kr"),

    # 여행 입장료/운영시간
    (["입장료", "관람료", "운영시간", "개장"],
     "관광지 입장료 운영시간 주차 공식 안내"),
    (["국립공원"],
     "국립공원 탐방 정보 탐방로 주차 site:knps.or.kr"),
]

# 공식 도메인 (검색 결과에서 우선 방문)
_OFFICIAL_DOMAINS = [
    "kepco.co.kr", "kogas.or.kr", "nhis.or.kr", "nps.or.kr",
    "ei.go.kr", "nts.go.kr", "bokjiro.go.kr", "mohw.go.kr",
    "mss.go.kr", "semas.or.kr", "samsung.com", "apple.com/kr",
    "lg.com/kr", "knps.or.kr", "jejutour.go.kr", "visitkorea.or.kr",
    "moel.go.kr", "work.go.kr", "gov.kr", "go.kr",
]

# ── goodisak IT 전용 ──────────────────────────────────────────────────────
# 네이버 쇼핑 API 대상 IT 제품 트리거
_IT_PRODUCT_TRIGGERS = [
    "노트북", "랩탑", "맥북", "그램", "갤럭시북",
    "이어폰", "헤드폰", "헤드셋", "에어팟", "버즈", "낫싱이어", "비츠",
    "스마트폰", "갤럭시", "아이폰", "폴드", "플립",
    "태블릿", "아이패드",
    "스마트워치", "갤럭시워치", "애플워치",
    "모니터", "키보드", "마우스",
    "SSD", "ssd", "메모리", "램", "그래픽카드",
    "로봇청소기", "공기청정기", "청소기",
    "TV", "OLED", "QLED", "냉장고", "세탁기", "건조기",
    "카메라", "미러리스", "블루투스", "스피커", "충전기",
    "프리티케어", "다이슨", "샤오미", "드론",
]

def _is_it_product(keyword: str) -> bool:
    kw = keyword.lower()
    return any(t.lower() in kw for t in _IT_PRODUCT_TRIGGERS)


def _naver_api(endpoint: str, query: str, display: int = 5,
               extra_params: str = "", on_log=None) -> list:
    """네이버 검색 Open API 공통 호출. 결과 items 리스트 반환."""
    client_id = os.environ.get("NAVER_SEARCH_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_SEARCH_CLIENT_SECRET", "")
    if not client_id:
        return []
    encoded = urllib.parse.quote(query)
    url = (f"https://openapi.naver.com/v1/search/{endpoint}.json"
           f"?query={encoded}&display={display}&start=1{extra_params}")
    req = urllib.request.Request(url, headers={
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode("utf-8")).get("items", [])
    except Exception as e:
        if on_log:
            on_log(f"[팩트수집] 네이버 API({endpoint}) 오류: {e}")
        return []


def _naver_shopping_facts(keyword: str, on_log=None) -> str:
    """네이버 쇼핑 API → 실제 가격·브랜드·카테고리 데이터."""
    def log(msg):
        if on_log: on_log(msg)

    items = _naver_api("shop", keyword, display=5, extra_params="&sort=sim", on_log=on_log)
    if not items:
        log(f"[팩트수집] 네이버쇼핑 결과 없음: '{keyword}'")
        return ""

    lines = [f"## 네이버쇼핑 실제 가격 데이터 (키워드: {keyword})"]
    price_list = []
    for item in items:
        title = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
        lprice = item.get("lprice", "")
        hprice = item.get("hprice", "")
        brand  = item.get("brand", "") or item.get("maker", "")
        cat    = item.get("category3", "") or item.get("category2", "") or item.get("category1", "")
        mall   = item.get("mallName", "")

        if lprice:
            price_list.append(int(lprice))

        line = f"- {title}"
        if brand:
            line += f" | 브랜드: {brand}"
        if lprice:
            price_str = f"{int(lprice):,}원"
            if hprice and hprice != lprice:
                price_str += f" ~ {int(hprice):,}원"
            line += f" | 가격: {price_str}"
        if cat:
            line += f" | 분류: {cat}"
        if mall:
            line += f" | 판매처: {mall}"
        lines.append(line)

    # 가격 범위 요약
    if price_list:
        lines.append(f"\n[가격 범위] 최저 {min(price_list):,}원 ~ 최고 {max(price_list):,}원"
                     f" (평균 {sum(price_list)//len(price_list):,}원)")

    log(f"[팩트수집] 네이버쇼핑 {len(items)}개 수집 완료")
    return "\n".join(lines)


def _naver_news_facts(keyword: str, on_log=None) -> str:
    """네이버 뉴스 API → 최신 정책·가격·정보 (날짜순)."""
    def log(msg):
        if on_log: on_log(msg)

    items = _naver_api("news", keyword, display=5, extra_params="&sort=date", on_log=on_log)
    if not items:
        log(f"[팩트수집] 네이버뉴스 결과 없음: '{keyword}'")
        return ""

    lines = [f"## 최신 뉴스 정보 (키워드: {keyword})"]
    for item in items[:4]:
        title = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
        desc  = re.sub(r"<[^>]+>", "", item.get("description", "")).strip()
        pub   = item.get("pubDate", "")[:16]
        if title:
            lines.append(f"\n### {title} ({pub})")
        if desc:
            lines.append(desc[:300])

    log(f"[팩트수집] 네이버뉴스 {len(items)}개 수집 완료")
    return "\n".join(lines)


def _naver_blog_facts(keyword: str, on_log=None) -> str:
    """네이버 블로그 검색 API → 최신 리뷰·정보 요약 (제목+내용 발췌)."""
    def log(msg):
        if on_log: on_log(msg)

    items = _naver_api("blog", keyword, display=5, extra_params="&sort=date", on_log=on_log)
    if not items:
        log(f"[팩트수집] 네이버블로그 결과 없음: '{keyword}'")
        return ""

    lines = [f"## 네이버 블로그 최신 정보 (키워드: {keyword})"]
    for item in items[:4]:
        title   = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
        desc    = re.sub(r"<[^>]+>", "", item.get("description", "")).strip()
        date    = item.get("postdate", "")
        if title:
            lines.append(f"\n### {title} ({date})")
        if desc:
            lines.append(desc[:300])

    log(f"[팩트수집] 네이버블로그 {len(items)}개 수집 완료")
    return "\n".join(lines)


def _collect_goodisak(keyword: str, on_log=None) -> dict:
    """goodisak IT 블로그 전용 팩트 수집.
    - IT 제품 키워드 → 네이버쇼핑 API (실제 가격·스펙)
    - 정보성 키워드 → 네이버블로그 API (최신 리뷰·방법)
    - 둘 다 실패 → 기존 Google+공식페이지 방식
    """
    def log(msg):
        if on_log: on_log(msg)

    parts = []
    is_product = _is_it_product(keyword)

    if is_product:
        shop_kw = _shopping_keyword(keyword)
        log(f"[팩트수집] IT 제품 키워드 감지 → 네이버쇼핑 API 조회: '{shop_kw}' (원본: '{keyword}')")
        shop = _naver_shopping_facts(shop_kw, on_log)
        if shop:
            parts.append(shop)
        # IT 제품은 쇼핑 데이터만 사용 — 블로그는 악세서리·무관 글이 섞여 노이즈
    else:
        # 정보성 키워드만 블로그 수집
        log(f"[팩트수집] 네이버블로그 최신 정보 조회: '{keyword}'")
        blog = _naver_blog_facts(keyword, on_log)
        if blog:
            parts.append(blog)

    if not parts:
        log("[팩트수집] 네이버 API 결과 없음 — 기존 방식으로 폴백")
        # 기존 Google+공식페이지 방식
        fact_query = _derive_fact_query_legacy(keyword)
        if not fact_query:
            return {"context": "", "success": False}
        return _collect_via_browser(keyword, fact_query, on_log, blog_id="goodisak")

    context = (
        f"## '{keyword}' 관련 실시간 데이터 (네이버 쇼핑 API)\n"
        f"⚠️ 가격은 반드시 아래 실제 데이터 범위 내에서만 작성하세요. "
        f"여기 없는 가격을 임의로 만들지 마세요.\n\n"
        + "\n\n".join(parts)
    )
    log(f"[팩트수집] ✓ goodisak 팩트 수집 완료 ({len(context)}자)")
    return {"context": context, "success": True}


_SEO_STRIP = re.compile(
    r"서류\s*준비\s*없이|빠르게|쉽게|간단하게|한번에|"
    r"신청하는\s*법|신청\s*방법|조건\s*금액|신청\s*자격|"
    r"총정리|완벽정리|한눈에|꼼꼼히|알아보기|"
    r"\d{4}년?\s*최신|\d{4}\s*년?\s*기준|최신\s*정보|\d{4}|"
    r"얼마\s*받나|얼마나|받나|몇\s*만원|지급액과|대상자별|혜택금액|"
    r"지원금액|지급방법|지급일|지급기준|얼마씩|월\s*얼마|"
    r"어떻게|어디서|왜|뭐가|누가|언제",
    re.IGNORECASE,
)

# API 검색용 추가 제거 단어 (복지로·정부24·관광 API에서 검색 방해)
_API_NOISE = re.compile(
    r"자격조건|소득기준|혜택|지원내용|지원대상|대상자|수급자격|"
    r"상한액|하한액|급여액|지급액|등록|조회|확인|변경|개편|개정|"
    r"방법|절차|기준|조건|금액|서류|신청|준비|안내|정리|총정리",
    re.IGNORECASE,
)

_STOP_WORDS = {"월", "일", "년", "원", "명", "개", "건", "회", "번", "차",
               "및", "또", "등", "의", "을", "를", "이", "가", "은", "는",
               "얼마", "몇", "어떤", "누구", "언제", "어디", "왜", "어떻게",
               "받을", "받나", "있나", "있어", "있는", "수", "되나", "되는",
               "하는", "하나", "인지", "인가", "할까", "해야", "인데", "이고"}


def _core_keyword(keyword: str) -> str:
    """SEO 부사구·의문어 제거 후 핵심 명사구 추출 (API 검색용)."""
    cleaned = _SEO_STRIP.sub("", keyword).strip()
    cleaned = _API_NOISE.sub("", cleaned).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    words = [w for w in cleaned.split() if len(w) >= 2 and w not in _STOP_WORDS]
    # API 검색은 핵심 단어 1~2개만 (너무 길면 검색 안 됨)
    return " ".join(words[:2]) if words else keyword.split()[0]


# 쇼핑 검색에서 제거할 SEO 수식어 (제품명/브랜드/카테고리만 남김)
_SHOPPING_NOISE = re.compile(
    r"가성비|추천|비교|순위|후기|리뷰|테스트|구매|사는\s*법|싸게|저렴|"
    r"최신|신제품|출시|2025|2026|\d{4}|베스트|인기|핫한|갓성비|"
    r"어떤거|어떤게|어떤|괜찮은거|괜찮은|좋은거|좋은|뭐가|뭐|"  # 긴 것 먼저
    r"노트북\s*추천|폰\s*추천|이어폰\s*추천|"
    r"[A-Za-z가-힣]*\s*좋을까|[A-Za-z가-힣]*\s*할까",
    re.IGNORECASE,
)


def _shopping_keyword(keyword: str) -> str:
    """쇼핑 검색용 키워드: 브랜드+제품명+모델만 남기고 SEO 수식어 제거."""
    cleaned = _SHOPPING_NOISE.sub("", keyword)
    # 한국어 조사·어미 잔재 제거 (예: "게 좋을까", "이 좋은", "을 사야")
    cleaned = re.sub(r"\s+[가-힣]{1,4}\s*$", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    # 남은 단어가 너무 적으면 원본 keyword에서 앞 2단어만 사용
    if len(cleaned) < 3:
        words = keyword.split()
        cleaned = " ".join(words[:2])
    return cleaned


def _derive_fact_query_legacy(keyword: str, blog_id: str = "") -> str:
    """키워드에서 팩트 수집에 최적화된 검색 쿼리 도출.
    수치/조건 데이터가 없는 카테고리는 빈 문자열 반환 → 팩트 수집 건너뜀.
    goodisak는 _collect_goodisak()에서 처리하므로 여기서 제외."""

    # baremi542/salim1su: 키워드 자체로 직접 검색 (고정 쿼리보다 정확)
    if blog_id in ("baremi542", "salim1su"):
        core = _core_keyword(keyword)
        return f"{core} 지원금액 신청자격 공식 site:go.kr OR site:or.kr"

    for triggers, query in _FACT_QUERIES:
        if any(t in keyword for t in triggers):
            return query

    # nolja100(여행): 입장료/운영시간 언급 없는 일반 여행 키워드는 팩트 수집 불필요
    if blog_id == "nolja100":
        TRAVEL_FACT_TRIGGERS = ["입장료", "운영시간", "개장", "요금", "예약", "주차요금"]
        if any(t in keyword for t in TRAVEL_FACT_TRIGGERS):
            return keyword + " 입장료 운영시간 주차 공식"
        return ""  # 일반 여행 키워드는 팩트 수집 생략

    return keyword + " 공식 정보"


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _clean_body_text(text: str) -> str:
    """body 전체 텍스트에서 내비/광고/반복 라인 제거."""
    lines = text.splitlines()
    seen = set()
    result = []
    # 내비게이션 전형 패턴
    nav_pattern = re.compile(
        r"바로가기|대메뉴|전체메뉴|로그인|언어 선택|KOR|ENG|복사하기|프린트|"
        r"목록보기|지도보기|SNS공유|블로그|인스타그램|유튜브|페이스북|카카오스토리|"
        r"개인정보|저작권|이용약관|사이트맵|All Rights|©20|ⓒ20"
    )
    for line in lines:
        line = line.strip()
        if not line or len(line) < 15:  # 짧은 라인(메뉴 항목) 제거
            continue
        if nav_pattern.search(line):  # 내비/푸터 라인 제거
            continue
        if re.match(r"^https?://", line):  # 단독 URL 라인 제거
            continue
        if line in seen:  # 중복 라인 제거 (광고 위젯 반복)
            continue
        seen.add(line)
        result.append(line)
    return "\n".join(result)


def _has_useful_data(text: str) -> bool:
    """숫자/금액/날짜/조건이 실제로 포함된 유용한 팩트인지 판단."""
    # 숫자 포함 여부 (금액, 조건 수치 등)
    has_numbers = bool(re.search(r'\d+', text))
    # 최소 100자 이상
    has_length = len(text) > 100
    return has_numbers and has_length


def _extract_page_facts(page, url: str, on_log=None) -> str:
    """주어진 URL 페이지에서 수치/조건 중심 내용 추출."""
    def log(msg):
        if on_log:
            on_log(msg)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
    except Exception as e:
        log(f"[팩트수집] 페이지 접속 실패: {e}")
        return ""

    # 표(table) 우선 추출 — 요금표/지원 금액표 등
    tables = ""
    try:
        tables = page.evaluate("""() => {
            const tbs = document.querySelectorAll('table');
            return Array.from(tbs).slice(0, 3).map(t => t.innerText.trim()).join('\\n\\n');
        }""")
    except Exception:
        pass

    # 본문 텍스트 추출 (main/article/content 우선, body는 정제 후 사용)
    body_text = ""
    for sel in ["main", "article", "#content", ".content", "#articleBody",
                ".article", ".view_content", ".cont_view"]:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                text = _clean(el.inner_text(timeout=3000))
                if len(text) > 200:
                    body_text = text[:3000]
                    break
        except Exception:
            continue
    # 본문 전용 선택자 실패 시 body 사용 — 내비/광고/반복 라인 정제 후
    if not body_text:
        try:
            raw_body = _clean(page.locator("body").first.inner_text(timeout=3000))
            body_text = _clean_body_text(raw_body)[:2000]
        except Exception:
            pass

    # 표 + 본문 조합 (표 우선)
    result = ""
    if tables and len(tables.strip()) > 50:
        result += f"[표/요금표]\n{tables[:1500]}\n\n"
    if body_text:
        result += f"[본문]\n{body_text[:1500]}"

    return result.strip()


def _search_and_get_official_url(page, query: str, blog_id: str, on_log=None) -> str:
    """Google 검색 → 공식 도메인(.go.kr/.or.kr) URL 반환.
    Naver는 go.kr 링크를 auth redirect로 감싸므로 Google 사용.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    encoded = urllib.parse.quote(query)
    search_url = f"https://www.google.com/search?q={encoded}&hl=ko&num=10"

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
    except Exception as e:
        log(f"[팩트수집] Google 검색 실패: {e}")
        return ""

    # Google 결과에서 공식 도메인 직접 URL 추출
    try:
        urls = page.evaluate("""() => {
            const anchors = document.querySelectorAll('a[href]');
            const result = [];
            for (const a of anchors) {
                const href = a.href || '';
                if (href.startsWith('http') &&
                    (href.includes('.go.kr') || href.includes('.or.kr')) &&
                    !href.includes('google') && !href.includes('accounts') &&
                    !href.includes('translate')) {
                    result.push(href);
                }
            }
            return [...new Set(result)].slice(0, 5);
        }""")
        if urls:
            log(f"[팩트수집] Google에서 공식 URL 발견: {urls[0][:80]}")
            return urls[0]
    except Exception:
        pass

    return ""


def _fallback_public_api(keyword: str, blog_id: str, on_log=None) -> dict:
    """웹 스크래핑 실패 시 공공데이터포털 API로 팩트 수집."""
    def log(msg):
        if on_log:
            on_log(msg)
    try:
        try:
            from public_api import fetch_context_for_blog
        except ImportError:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from public_api import fetch_context_for_blog
        # 핵심 키워드로 압축 후 API 호출
        core = _core_keyword(keyword)
        if core != keyword:
            log(f"[팩트수집] 핵심 키워드 추출: '{keyword}' → '{core}'")
        ctx = fetch_context_for_blog(blog_id, core, on_log=on_log)
        if ctx and len(ctx) > 50:
            log(f"[팩트수집] ✓ 공공API 폴백 성공 ({len(ctx)}자)")
            return {"context": ctx, "success": True}
        log("[팩트수집] 공공API 폴백도 데이터 없음 — 건너뜀")
    except Exception as e:
        log(f"[팩트수집] 공공API 폴백 실패: {e}")
    return {"context": "", "success": False}


def _collect_via_browser(keyword: str, fact_query: str,
                         on_log=None, blog_id: str = "") -> dict:
    """Google 검색 → 공식 페이지 방문 → 팩트 추출 (기존 브라우저 방식)."""
    def log(msg):
        if on_log:
            on_log(msg)

    try:
        pw, browser = connect_cdp(on_log)
    except Exception as e:
        log(f"[팩트수집] CDP 연결 실패: {e} — 공공API 폴백 시도")
        return _fallback_public_api(keyword, blog_id, on_log)

    facts = ""
    official_url = ""
    try:
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        try:
            official_url = _search_and_get_official_url(page, fact_query, blog_id, on_log)
            if not official_url:
                log("[팩트수집] 공식 페이지 URL 없음 — 공공API 폴백 시도")
                return _fallback_public_api(keyword, blog_id, on_log)
            log(f"[팩트수집] 공식 페이지 방문: {official_url[:80]}")
            facts = _extract_page_facts(page, official_url, on_log)
        finally:
            try:
                page.close()
            except Exception:
                pass
    except Exception as e:
        log(f"[팩트수집] 오류: {e}")
        facts = ""
    finally:
        try:
            pw.stop()
        except Exception:
            pass

    if not facts or not _has_useful_data(facts):
        log("[팩트수집] 유효한 수치 데이터 없음 — 공공API 폴백 시도")
        return _fallback_public_api(keyword, blog_id, on_log)

    context_text = (
        f"## '{keyword}' 관련 공식 출처 데이터\n"
        f"출처: {official_url[:100]}\n\n"
        f"아래 수치/조건만 사용하세요. 여기 없는 수치는 '확인 필요'로 표기하세요.\n\n"
        f"{facts[:3000]}"
    )
    log(f"[팩트수집] ✓ 공식 데이터 {len(facts)}자 수집 완료")
    return {"context": context_text, "success": True}


def collect(keyword: str, blog_id: str, on_log=None) -> dict:
    """글 생성 전 키워드 관련 팩트를 API로 수집.

    흐름 (Playwright/브라우저 스크래핑 없음):
      - goodisak/blogspot_it: 네이버쇼핑 API + 네이버블로그 API
      - 그 외 IT 트리거 포함: 네이버쇼핑 API
      - 정부지원/복지: 공공API (복지로, 정부24)
      - 여행: 한국관광공사 API
      - 생활정보 등 나머지: 네이버블로그 API

    Returns:
        {"context": str, "success": bool}
    """
    def log(msg):
        if on_log:
            on_log(msg)

    log(f"[팩트수집] 시작: blog={blog_id}, keyword='{keyword}'")

    # ── IT 제품 블로그 ──────────────────────────────────────────────────────
    if blog_id in ("goodisak", "blogspot_it") or _is_it_product(keyword):
        return _collect_goodisak(keyword, on_log)

    # ── 공공API 우선 (정부지원/복지/연금/보험 등) ────────────────────────────
    ctx = _fallback_public_api(keyword, blog_id, on_log)
    if ctx["success"]:
        return ctx

    # ── 네이버 뉴스 API (최신 정책·수치 우선) ────────────────────────────────
    news_kw = _core_keyword(keyword)
    log(f"[팩트수집] 네이버뉴스 조회: '{news_kw}'")
    news = _naver_news_facts(news_kw, on_log)

    # ── 네이버 블로그 API (보완) ──────────────────────────────────────────────
    blog = _naver_blog_facts(news_kw, on_log)

    parts = [p for p in [news, blog] if p]
    if parts:
        context = (
            f"## '{keyword}' 관련 참고 정보\n"
            f"아래 내용을 참고해 글을 작성하세요. 내용을 그대로 옮기지 말고 "
            f"핵심 수치·사실만 추출해서 자신의 문체로 재작성하세요.\n\n"
            + "\n\n".join(parts)
        )
        log(f"[팩트수집] ✓ 뉴스+블로그 참고 정보 수집 완료")
        return {"context": context, "success": True}

    log("[팩트수집] 수집 가능한 데이터 없음 — 건너뜀")
    return {"context": "", "success": False}
