"""롱테일 키워드 확장기

seed 키워드 → 네이버 검색광고 relKeyword API → 2단계 재귀 확장 → 카테고리 분류 → DB 저장
(relKeyword 실패 시 네이버 자동완성 폴백)

흐름:
  seed 키워드
      ↓ 1차: relKeyword API (검색량 100~3,000)
      ↓ 2차: 1차 결과 상위 5개 → 다시 relKeyword (재귀 2단계까지)
      ↓ 각 키워드 카테고리 자동 분류 (또는 명시적 카테고리 사용)
      ↓ 이미 DB에 있으면 스킵, 신규만 저장
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
import os

_root = Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent.parent)))
_env = _root / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


# ── 카테고리 분류 ─────────────────────────────────────────────────────────

_CAT_INCLUDE = {
    "IT": [
        "앱", "소프트웨어", "디지털", "스마트폰", "아이폰", "갤럭시", "노트북", "태블릿",
        "이어폰", "스피커", "모니터", "게임", "토스", "네이버페이", "카카오페이", "토스뱅크",
        "인터넷은행", "페이", "OTT", "넷플릭스", "유튜브", "티빙", "왓챠", "웨이브",
        "챗GPT", "ChatGPT", "AI", "클라우드", "VPN", "블루투스", "와이파이", "공유기",
        "케이블", "충전기", "배터리팩", "스마트TV", "셋톱박스",
    ],
    "정부지원금": [
        "지원금", "보조금", "복지", "신청방법", "신청자격", "수급자", "급여", "바우처",
        "취업지원", "실업급여", "육아휴직", "장애인", "노인혜택", "문화누리", "에너지바우처",
        "주거급여", "긴급복지", "국민취업", "출산지원", "다자녀", "청년수당", "생계급여",
        "의료급여", "교육급여", "한부모", "차상위", "기초생활", "근로장려금", "자녀장려금",
        "청년도약계좌", "국민연금", "건강보험료 환급", "통신비 감면",
    ],
    "살림": [
        "생활비", "절약", "청소", "정리", "수납", "살림", "꿀팁", "세탁", "주방",
        "냉장고", "세탁기", "에어컨", "보일러", "이불", "옷장", "재활용", "식비",
        "전기요금", "가스비", "통신비", "관리비", "수도요금", "인테리어",
        "욕실", "베이킹소다", "구연산", "락스", "분리수거", "음식물쓰레기",
    ],
    "여행": [
        "여행", "투어", "액티비티", "현지체험", "마이리얼트립", "맛집", "숙소", "항공",
        "호텔", "펜션", "캠핑", "드라이브", "관광", "1박2일", "2박3일", "당일치기",
        "뚜벅이", "글램핑", "리조트", "게스트하우스", "여행코스", "여행지",
    ],
}

# 살림 카테고리 제외 단어 (금융 상품 관련)
_CAT_EXCLUDE = {
    "살림": ["보험", "카드", "대출", "투자", "주식", "부동산", "청약", "저축", "적금",
             "예금", "금리", "환율", "증권"],
}

# 카테고리 우선순위: IT → 정부지원금 → 살림 → 여행
_CAT_ORDER = ["IT", "정부지원금", "살림", "여행"]


def _classify_category(keyword: str) -> str:
    """
    키워드를 카테고리로 자동 분류.

    Returns:
        "IT" | "정부지원금" | "살림" | "여행" | "unassigned"
    """
    for cat in _CAT_ORDER:
        # 제외 단어 먼저 확인
        if any(ex in keyword for ex in _CAT_EXCLUDE.get(cat, [])):
            continue
        # 포함 단어 확인
        if any(inc in keyword for inc in _CAT_INCLUDE[cat]):
            return cat
    return "unassigned"


# ── 네이버 자동완성 폴백 ─────────────────────────────────────────────────

def _naver_autocomplete(keyword: str) -> list:
    """네이버 자동완성 API (relKeyword 폴백용)"""
    q = urllib.parse.quote(keyword)
    url = (
        f"https://ac.search.naver.com/nx/ac"
        f"?q={q}&q_enc=UTF-8&st=100&frm=nv"
        f"&r_format=json&r_enc=UTF-8&r_unicode=0&t_koreng=1&ans=2&run=2&rev=4"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = json.loads(urllib.request.urlopen(req, timeout=8).read())
        results = []
        for group in data.get("items", []):
            for item in group:
                if isinstance(item, list) and item:
                    results.append(str(item[0]).strip())
                elif isinstance(item, str):
                    results.append(item.strip())
        return [r for r in results if r]
    except Exception:
        return []


_SKIP = re.compile(r"(쇼핑|광고|구매|구입|가격비교|공식홈|공식사이트)")


# ── 카테고리별 suffix ────────────────────────────────────────────────────

_SUFFIX_COMMON = [
    "안될때", "오류", "취소", "조회", "후기", "비교",
    "방법", "기간", "이유", "해결방법", "신청", "주의사항",
]

_SUFFIX_BY_CAT = {
    # 카테고리별 고유 suffix 먼저, 공통 suffix 뒤에
    "IT": [
        "안되는이유", "연동", "설정방법", "업데이트",
        "수수료", "한도", "계좌개설", "인증오류", "앱오류",
    ] + _SUFFIX_COMMON,
    "살림": [
        "직접해본후기", "추천", "효과있는", "저렴하게",
        "셀프", "비용", "주기", "순서", "안지워질때",
    ] + _SUFFIX_COMMON,
    "정부지원금": [
        "자격조건", "신청기간", "대상자", "지급일",
        "얼마나받나", "탈락이유", "재신청", "서류",
    ] + _SUFFIX_COMMON,
    "여행": [
        "혼자", "당일치기", "가족여행", "비용",
        "숙소추천", "맛집", "코스", "주차", "시즌",
    ] + _SUFFIX_COMMON,
}


def _build_suffix_seeds(base_kw: str, category: str, max_seeds: int = 5) -> list:
    """
    키워드 + suffix 조합 생성 (상위 max_seeds개).
    relKeyword API 쿼리용 seed 리스트 반환.
    """
    suffixes = _SUFFIX_BY_CAT.get(category, _SUFFIX_COMMON)
    # 공백 없이 붙이기 (네이버 검색광고 API는 공백 없는 쿼리로 더 잘 매칭)
    base = base_kw.replace(" ", "")
    return [f"{base}{s}" for s in suffixes[:max_seeds]]


# ── 메인 함수 ─────────────────────────────────────────────────────────────

_CAT_MIN_VOL = {
    "살림": 300,   # 살림은 경쟁 낮은 세부 키워드만
}
_DEFAULT_MIN_VOL = 100
_DEFAULT_MAX_VOL = 3000


def expand_longtail(
    base_keywords: list,
    category: str = "",
    blog_id: str = None,
    top_n: int = 8,
    on_log=None,
) -> int:
    """
    base_keywords를 relKeyword API로 2단계 재귀 확장해 DB에 저장.
    relKeyword 결과 없으면 자동완성 폴백.

    Args:
        base_keywords: seed 키워드 목록
        category: 저장 시 카테고리 (지정 시 해당 카테고리 제외 단어만 필터, 미지정 시 자동 분류)
        blog_id: 포화 체크용 (선택)
        top_n: seed 중 상위 N개만 처리
        on_log: 로그 콜백

    Returns:
        새로 저장된 키워드 수
    """
    from keyword_engine.db_handler import upsert_keyword, keyword_exists
    from keyword_engine.rel_keyword import get_rel_keywords

    min_vol = _CAT_MIN_VOL.get(category, _DEFAULT_MIN_VOL)
    max_vol = _DEFAULT_MAX_VOL

    def log(msg):
        if on_log:
            on_log(msg)

    saved = 0
    total_extracted = 0
    total_skipped_dup = 0
    total_skipped_cat = 0

    def _save(item: dict):
        """단일 키워드 항목을 검증 후 DB에 저장"""
        nonlocal saved, total_skipped_dup, total_skipped_cat
        kw = item["keyword"].strip()
        if not kw:
            return
        # 4글자 미만 제외 (단일어/너무 짧은 키워드)
        if len(kw.replace(" ", "")) < 4:
            return
        # 롱테일 필수: 공백으로 구분된 단어 2개 이상 (단일 복합어 "고용유지지원금" 등 제외)
        if len(kw.split()) < 2:
            return
        # 광고/쇼핑 관련 키워드 제외
        if _SKIP.search(kw):
            return
        # 시즌 필터: 현재 월 기준 ±2개월 벗어나는 특정 월 키워드 저장 안 함
        from datetime import datetime as _dt
        _cur_month = _dt.now().month
        _MONTH_HINTS = {
            1: ["1월", "일월", "신년", "새해"],
            2: ["2월", "이월", "발렌타인"],
            3: ["3월", "삼월"],
            4: ["4월", "사월"],
            5: ["5월", "오월", "어버이날", "어린이날"],
            6: ["6월", "유월"],
            7: ["7월", "칠월", "여름휴가"],
            8: ["8월", "팔월"],
            9: ["9월", "구월"],
            10: ["10월", "시월", "할로윈"],
            11: ["11월", "십일월"],
            12: ["12월", "십이월", "크리스마스", "연말"],
        }
        for _m, _hints in _MONTH_HINTS.items():
            if any(h in kw for h in _hints):
                _diff = min(abs(_m - _cur_month), 12 - abs(_m - _cur_month))
                if _diff > 2:
                    total_skipped_cat += 1
                    return
                break
        # 이미 DB에 있으면 스킵
        if keyword_exists(kw):
            total_skipped_dup += 1
            return
        # 카테고리 결정
        if category:
            # 명시적 카테고리: 해당 카테고리 제외 단어만 필터
            if any(ex in kw for ex in _CAT_EXCLUDE.get(category, [])):
                total_skipped_cat += 1
                return
            cat = category
        else:
            # 자동 분류
            cat = _classify_category(kw)
            if cat == "unassigned":
                total_skipped_cat += 1
                return
        # 검색량 기반 점수 (50~80점, 0이면 50점)
        vol = item.get("total_vol", 0)
        score = 50.0 + (vol / 3000) * 30 if vol > 0 else 50.0
        upsert_keyword(
            keyword=kw,
            score=round(score, 1),
            volume=vol,
            pub_count=1,
            category=cat,
            blog_id=blog_id,
        )
        saved += 1

    processed_seeds = set()

    for seed in base_keywords[:top_n]:
        seed = seed.strip()
        if not seed or seed in processed_seeds:
            continue
        processed_seeds.add(seed)

        # ── 1차: relKeyword API ──────────────────────────────────────────
        log(f"[롱테일] 1차 확장: '{seed}'")
        results_1 = get_rel_keywords([seed], min_vol=min_vol, max_vol=max_vol, on_log=on_log)
        time.sleep(0.5)

        # relKeyword 결과 없으면 자동완성 폴백
        if not results_1:
            ac = _naver_autocomplete(seed)
            # 자동완성 결과는 검색량 0으로 저장
            results_1 = [
                {"keyword": kw, "total_vol": 0, "pc_vol": 0, "mobile_vol": 0}
                for kw in ac
                if len(kw) > len(seed) and len(kw.split()) >= 2
            ]
            if ac:
                log(f"[롱테일] 자동완성 폴백: {len(ac)}개 → 필터 후 {len(results_1)}개")

        total_extracted += len(results_1)
        for item in results_1:
            _save(item)

        # ── 2차: 1차 결과 상위 5개 → 재귀 확장 ──────────────────────────
        # 검색량 있는 것 우선, 상위 5개 seed로 재사용
        top5 = [x for x in results_1 if x.get("total_vol", 0) > 0][:5]
        if not top5:
            top5 = results_1[:5]

        top5_kws = [x["keyword"] for x in top5 if x["keyword"] != seed]
        if not top5_kws:
            continue

        log(f"[롱테일] 2차 확장: {top5_kws[:3]}{'...' if len(top5_kws) > 3 else ''}")
        results_2 = get_rel_keywords(top5_kws, min_vol=min_vol, max_vol=max_vol, on_log=on_log)
        time.sleep(0.5)

        total_extracted += len(results_2)
        for item in results_2:
            _save(item)

        # ── 2차-suffix: seed + 카테고리별 suffix 조합 쿼리 ───────────────
        suffix_seeds = _build_suffix_seeds(seed, category, max_seeds=5)
        log(f"[롱테일] suffix 확장: '{seed}' + {len(suffix_seeds)}개 suffix")
        results_sfx = get_rel_keywords(suffix_seeds, min_vol=min_vol, max_vol=max_vol, on_log=on_log)
        time.sleep(0.5)

        total_extracted += len(results_sfx)
        for item in results_sfx:
            _save(item)

    log(
        f"[롱테일] 완료 — 추출 {total_extracted}개 | "
        f"저장 {saved}개 | "
        f"중복 스킵 {total_skipped_dup}개 | "
        f"카테고리 불일치 {total_skipped_cat}개"
    )
    return saved
