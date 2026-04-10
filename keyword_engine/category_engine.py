"""카테고리별 키워드 수집 엔진 — 캐시 우선 + 백그라운드 사이트 발견"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from keyword_engine import db_handler
from keyword_engine import gsc_connector
from keyword_engine import naver_api
from keyword_engine import pub_finder
from keyword_engine import title_collector
from keyword_engine import keyword_scorer

# 카테고리 ↔ 블로그 ID 매핑
CATEGORY_MAP = {
    "IT":         "goodisak",
    "여행":       "nolja100",
    "살림":       "salim1su",
    "정부지원금": "baremi542",
}
BLOG_TO_CATEGORY = {v: k for k, v in CATEGORY_MAP.items()}
ALL_CATEGORIES   = list(CATEGORY_MAP.keys())

# 카테고리별 제목 필터
CATEGORY_TITLE_KEYWORDS = {
    "IT": {
        "갤럭시", "아이폰", "맥북", "노트북", "스마트폰", "이어폰", "태블릿",
        "모니터", "스피커", "웹캠", "게이밍", "미니PC", "워치",
        "OTT", "넷플릭스", "티빙", "왓챠", "웨이브", "요금제",
        "앱", "프로그램", "소프트웨어", "CPU", "GPU", "SSD", "RAM",
        "윈도우", "맥OS", "안드로이드", "iOS", "공유기", "블루투스",
        "청정기", "청소기", "에어컨", "냉장고", "세탁기",
    },
    "여행": {
        "여행", "코스", "맛집", "숙소", "카페", "관광", "명소", "드라이브", "캠핑",
        "글램핑", "호텔", "펜션", "리조트", "휴가", "제주", "부산", "강원", "경주",
        "속초", "전주", "여수", "통영", "남해", "당일치기", "국내여행", "해외여행",
        "등산", "국립공원", "둘레길", "트레킹",
    },
    "살림": {
        # 고정지출 절약 핵심
        "전기요금", "전기세", "전기비", "가스비", "도시가스", "관리비", "통신비",
        "알뜰폰", "인터넷요금", "구독서비스", "넷플릭스 요금", "OTT 절약",
        "보일러", "난방비", "수도요금", "수도세",
        # 세금/환급/공제
        "연말정산", "월세공제", "세액공제", "건강보험료", "피부양자",
        "장기수선충당금", "이사비용",
        # 식비/생활비 절약
        "식비절약", "식비 줄이기", "생활비 절약", "고정지출",
        # 살림/절약 복합
        "절약 방법", "절약 꿀팁", "요금 줄이기", "비용 줄이기",
    },
    "정부지원금": {
        "지원금", "복지", "혜택", "지원", "신청", "급여", "바우처", "수급", "청년",
        "장애인", "출산", "육아", "노인", "실업", "취업", "주거", "교육", "의료",
        "정부", "보조금", "감면", "제도", "정책",
    },
}

DEFAULT_MIN_SCORE   = 100_000
DEFAULT_MIN_VOLUME  = 500
DEFAULT_TOP_N       = 50
MIN_DOMAINS_PER_PUB = 2
TOP_PUB_OWNERS      = 10


def _log(msg, on_log=None):
    print(msg, flush=True)
    if on_log:
        on_log(msg)


def _background_discover(category: str, queries: list, on_log=None):
    """백그라운드: Naver 검색 → 펍코드 수집 → DB 저장 (최대 100개)"""
    try:
        _log(f"[백그라운드/{category}] 사이트 발견 시작...", on_log)
        tistory_urls = naver_api.collect_tistory_urls(queries, display=100)
        url_list = list(tistory_urls)[:100]  # 최대 100개만
        _log(f"[백그라운드/{category}] {len(url_list)}개 URL 펍코드 수집 중...", on_log)
        if not url_list:
            return
        pub_map = pub_finder.find_pub_codes_fast(url_list)
        for url, pub in pub_map.items():
            db_handler.save_site(url, pub, category=category)
        _log(f"[백그라운드/{category}] 펍코드 확인 사이트 {len(pub_map)}개 DB 저장 완료", on_log)
    except Exception as e:
        _log(f"[백그라운드/{category}] 오류: {e}", on_log)


def run_category(
    category: str,
    top_n: int = DEFAULT_TOP_N,
    min_score: float = DEFAULT_MIN_SCORE,
    min_volume: int = DEFAULT_MIN_VOLUME,
    use_playwright: bool = False,
    on_log=None,
    on_keyword=None,
) -> list:
    """
    캐시 우선 키워드 수집 + 백그라운드 사이트 발견

    흐름:
      즉시: DB 캐시(다수 도메인 펍코드 소유자 사이트) → RSS → 키워드 추출 → 표시
      백그라운드: Naver 검색 → 펍코드 수집 → DB 업데이트 (다음 실행에 반영)
      첫 실행(캐시 없음): 백그라운드 완료 후 진행
    """
    blog_id = CATEGORY_MAP.get(category)
    if not blog_id:
        _log(f"[category_engine] 알 수 없는 카테고리: {category}", on_log)
        return []

    _log("═" * 55, on_log)
    _log(f"  카테고리: {category}  블로그: {blog_id}", on_log)
    _log("═" * 55, on_log)

    queries = naver_api.BLOG_QUERIES.get(blog_id, [])

    # ── 백그라운드: 사이트 발견 스레드 시작 ─────────────────
    bg_thread = threading.Thread(
        target=_background_discover,
        args=(category, queries, on_log),
        daemon=True,
    )
    bg_thread.start()

    # ── 캐시에서 사이트 조회 (즉시, 백그라운드와 무관) ──────────
    # 1순위: 다수 도메인 보유 펍코드 소유자 사이트
    collect_urls = set(db_handler.get_multidomain_sites(
        category, min_domains=MIN_DOMAINS_PER_PUB, top_owners=TOP_PUB_OWNERS
    ))
    if collect_urls:
        _log(f"\n[캐시] 다수도메인 사이트 {len(collect_urls)}개 → 즉시 추출", on_log)
    else:
        # 2순위: 카테고리 내 전체 사이트 (펍코드 여부 무관)
        all_sites = db_handler.get_sites_by_category(category)
        if all_sites:
            collect_urls = {s["url"] for s in all_sites}
            _log(f"\n[캐시] 전체 사이트 {len(collect_urls)}개 → 즉시 추출", on_log)
        else:
            # 3순위: DB 완전 비어있음 — 백그라운드 완료 1회만 대기
            _log("\n[초기화] DB 비어있음 — 첫 수집 완료까지 1회 대기...", on_log)
            bg_thread.join()
            collect_urls = set(db_handler.get_multidomain_sites(
                category, min_domains=MIN_DOMAINS_PER_PUB, top_owners=TOP_PUB_OWNERS
            ))
            if not collect_urls:
                all_sites = db_handler.get_sites_by_category(category)
                collect_urls = {s["url"] for s in all_sites}
            if not collect_urls:
                _log("[오류] 수집된 사이트 없음 — 종료", on_log)
                return []
            _log(f"[초기화 완료] {len(collect_urls)}개 사이트 확보", on_log)

    # ── RSS 제목 수집 ──────────────────────────────────────
    _log(f"\n[RSS] {len(collect_urls)}개 사이트에서 제목 수집 중...", on_log)
    all_titles = title_collector.collect_from_all(collect_urls, use_playwright=use_playwright, on_log=on_log)
    _log(f"[RSS] {len(all_titles)}개 제목 수집", on_log)

    if not all_titles:
        _log("[오류] 제목 수집 실패 — 종료", on_log)
        return []

    # ── 카테고리 필터 ──────────────────────────────────────
    cat_filter = CATEGORY_TITLE_KEYWORDS.get(category, set())
    if cat_filter:
        filtered_titles = [t for t in all_titles if any(kw in t for kw in cat_filter)]
        _log(f"[필터] {len(all_titles)}개 → {len(filtered_titles)}개 ({category} 관련)", on_log)
        if len(filtered_titles) >= 20:
            all_titles = filtered_titles

    # ── 키워드 추출 ────────────────────────────────────────
    _log("\n[추출] 키워드 추출 중...", on_log)
    candidates = title_collector.extract_keywords_from_titles(all_titles, top_n=100)
    _log(f"[추출] {len(candidates)}개 후보 발견", on_log)

    if not candidates:
        _log("[오류] 키워드 추출 실패 — 종료", on_log)
        return []

    # ── 즉시 표시: 점수 계산 전 키워드 후보 모두 전달 ─────────
    if on_keyword:
        for kw in candidates:
            on_keyword({"keyword": kw, "score": 0, "volume": 0, "pub_count": 0})

    # ── 점수 계산 ──────────────────────────────────────────
    _log(f"\n[점수] {len(candidates)}개 점수 계산 중...", on_log)

    def _emit(item):
        if item["volume"] > 0 and on_keyword:
            on_keyword(item)

    scored = keyword_scorer.score_keywords(
        candidates,
        get_pub_count_fn=naver_api.get_blog_count,
        on_log=on_log,
        on_keyword=_emit,
    )

    # ── DB 저장: 검색량 있는 것 모두 누적 저장 (점수 기준 필터 없음) ──────
    # 검색량 > 0 이면 모두 DB에 저장 (사용자가 직접 삭제)
    to_save = [k for k in scored if k["volume"] > 0]
    _log(f"\n[DB] {len(to_save)}개 누적 저장", on_log)

    gsc_boost = set(gsc_connector.get_rising_keywords())
    if gsc_boost:
        to_save = ([k for k in to_save if k["keyword"] in gsc_boost] +
                   [k for k in to_save if k["keyword"] not in gsc_boost])

    for item in to_save:
        db_handler.upsert_keyword(
            item["keyword"], item["score"], item["volume"], item["pub_count"],
            category=category,
        )

    # 반환은 기존 필터 기준 (Notion 등 외부용)
    result = [k for k in to_save if k["volume"] >= min_volume and k["score"] >= min_score]
    top = result[:top_n]

    _log(f"\n{'═' * 55}", on_log)
    _log(f"  [{category}] 완료: {len(top)}개 (DB 저장)", on_log)
    _log(f"{'═' * 55}", on_log)

    return top


# ── 에이전트/GUI 조회용 ──────────────────────────────────

def get_keywords(category: str, n: int = 20, min_score: float = 0) -> list:
    return db_handler.get_keywords_by_category(category, n=n, min_score=min_score)

def get_stats() -> dict:
    return db_handler.get_category_stats()

def get_sites(category: str) -> list:
    return db_handler.get_sites_by_category(category)


# ── CLI ──────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="카테고리별 키워드 엔진")
    parser.add_argument("--category", choices=ALL_CATEGORIES, required=True)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--min-volume", type=int, default=DEFAULT_MIN_VOLUME)
    parser.add_argument("--query", action="store_true")
    args = parser.parse_args()

    if args.query:
        kws = get_keywords(args.category, n=args.top)
        print(f"\n[{args.category}] 저장된 키워드 {len(kws)}개:")
        for i, k in enumerate(kws, 1):
            print(f"{i:3}. {k['keyword']:<22} 점수:{k['score']:>12,.0f}  검색량:{k['volume']:>7,}")
    else:
        run_category(
            category=args.category,
            top_n=args.top,
            min_score=args.min_score,
            min_volume=args.min_volume,
        )
