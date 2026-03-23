"""제목 패턴 분석 — 카테고리 자동 도출, 상위 패턴 추출"""
import re
from collections import Counter

REGION_KEYWORDS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    "수원", "성남", "안양", "안산", "용인", "고양", "창원", "청주", "전주",
]

TITLE_PATTERNS = [
    ("TOP N 리스트", r"(top\s*\d+|베스트|추천\s*\d+|순위\s*\d+|\d+가지|\d+선)"),
    ("지역+업종", r"(" + "|".join(REGION_KEYWORDS) + r").{0,10}(추천|맛집|호텔|여행|관광|펜션|숙소)"),
    ("가격/비용", r"(가격|비용|요금|얼마|견적|금액)"),
    ("방법/팁", r"(방법|하는법|하는 법|팁|노하우|하려면)"),
    ("후기/리뷰", r"(후기|리뷰|사용기|체험기|솔직|실제로)"),
    ("비교/분석", r"(비교|분석|차이|vs\b|VS\b)"),
    ("시기/시즌", r"(시기|시즌|언제|몇월|개화|축제|일정)"),
    ("신청/절차", r"(신청|방법|절차|조건|자격|서류)"),
]

CATEGORIES = {
    "여행/숙박": ["여행", "호텔", "펜션", "맛집", "관광", "축제", "개화", "숙소"],
    "건강/의료": ["증상", "치료", "병원", "약", "건강", "다이어트", "영양"],
    "생활정보": ["방법", "하는법", "비용", "가격", "신청", "절약", "정리"],
    "IT/가전": ["추천", "비교", "성능", "사양", "후기", "노트북", "스마트폰"],
    "재테크/금융": ["금리", "이자", "투자", "주식", "부동산", "청약", "대출"],
    "정부지원": ["지원금", "장려금", "실업급여", "복지", "보조금", "바우처"],
}


def analyze(titles: list) -> dict:
    """제목 패턴 분석 결과 반환"""
    if not titles:
        return {}

    total = len(titles)

    pattern_counts = Counter()
    for title in titles:
        for name, pattern in TITLE_PATTERNS:
            if re.search(pattern, title, re.IGNORECASE):
                pattern_counts[name] += 1

    region_counts = Counter()
    for title in titles:
        for region in REGION_KEYWORDS:
            if region in title:
                region_counts[region] += 1

    category_counts = Counter()
    for title in titles:
        for cat, words in CATEGORIES.items():
            if any(w in title for w in words):
                category_counts[cat] += 1

    return {
        "total_titles": total,
        "patterns": {
            k: f"{v}/{total} ({100 * v // total}%)"
            for k, v in pattern_counts.most_common()
        },
        "top_regions": dict(region_counts.most_common(5)),
        "categories": {
            k: f"{100 * v // total}%"
            for k, v in category_counts.most_common(3)
        },
    }


def print_report(analysis: dict):
    total = analysis.get("total_titles", 0)
    print(f"\n📊 제목 분석 리포트 ({total}개)")
    print("─" * 45)

    if analysis.get("categories"):
        print("📂 카테고리 분포:")
        for cat, pct in analysis["categories"].items():
            print(f"   {cat}: {pct}")

    if analysis.get("patterns"):
        print("\n📌 제목 패턴:")
        for pat, cnt in list(analysis["patterns"].items())[:5]:
            print(f"   {pat}: {cnt}")

    if analysis.get("top_regions"):
        print("\n📍 상위 지역 키워드:")
        for region, cnt in analysis["top_regions"].items():
            print(f"   {region}: {cnt}회")
