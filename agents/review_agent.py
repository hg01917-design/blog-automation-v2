"""자동 검수 에이전트 — 규칙 기반 품질 체크"""
import re
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from agents import fact_check as _fact_check
except ImportError:
    import fact_check as _fact_check

FORBIDDEN_PATTERNS = [
    "완벽정리", "총정리", "완벽가이드", "완벽 정리", "총 정리",
]

# 네이버 제한어 (salim1su 전용 — 저품질 판정 원인)
NAVER_RESTRICTED = {
    "의료": ["유발", "진단", "처방", "치료", "완치", "증상", "임상", "효과 있음"],
    "법률/금융": ["상담", "보장", "환급 확정", "수익 보장"],
    "과장": ["무조건", "반드시", "100%", "즉시 효과", "유일한"],
}

# AI가 쓴 티 나는 표현 패턴 (본문 전체 대상)
AI_PATTERNS = [
    "물론입니다",
    "당연히",
    "주목해야",
    "살펴보겠습니다",
    "알아보겠습니다",
    "정리해보겠습니다",
    "해드리겠습니다",
    "첫째,",
    "둘째,",
    "셋째,",
    "핵심은",
    "포인트는",
    "AI",
    "ChatGPT",
    "LLM",
]

IMAGES_DIR = Path(__file__).parent.parent / "images"


def run(result: dict, keyword: str, blog_id: str,
        on_log=None, on_status=None):
    """자동 검수를 실행한다.

    Args:
        result: writer_agent 반환값
        keyword: 메인 키워드
        blog_id: 블로그 ID

    Returns:
        dict: {"passed": bool, "issues": list[str], "result": dict}
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if on_status:
        on_status("review", "working")

    log("[검수] 자동 검수 시작")

    title = result["title"]
    body = result["body"]
    tags = result["tags"]
    images = result.get("images", [])
    image_paths = result.get("image_paths", {})

    issues = []

    # 1. 글자수 체크 (본문 전체 길이 — 공백 제외)
    body_chars = len(re.sub(r"\s+", "", body))
    if body_chars < 1500:
        issues.append(f"글자수 부족: {body_chars}자 < 1500자")

    # 2. 태그 수 체크
    if len(tags) < 10:
        issues.append(f"태그 부족: {len(tags)}개 < 10개")

    # 3. 제목에 메인키워드가 앞에 위치
    kw_words = keyword.split()
    first_word = kw_words[0] if kw_words else keyword
    if first_word not in title[:len(first_word) + 5]:
        # 키워드 첫 단어가 제목 앞부분에 없으면
        if keyword not in title:
            issues.append(f"제목에 메인키워드 없음: '{keyword}'")
        else:
            kw_pos = title.index(keyword)
            if kw_pos > 5:
                issues.append(f"메인키워드가 제목 앞이 아닌 {kw_pos}번째 위치")

    # 4. 제목 40자 이하
    if len(title) > 40:
        issues.append(f"제목 길이 초과: {len(title)}자 > 40자")

    # 5. 금지패턴 체크
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in title:
            issues.append(f"제목 금지패턴: '{pattern}'")
        if pattern in body[:200]:
            issues.append(f"본문 금지패턴: '{pattern}'")

    # N가지/N종류 패턴
    n_pattern = re.search(r'\d+가지|\d+종류', title)
    if n_pattern:
        issues.append(f"제목 금지패턴: '{n_pattern.group()}'")

    # 6. 이미지 파일 존재 여부
    for img_info in images:
        idx = img_info["index"]
        filepath = image_paths.get(idx)
        if not filepath:
            candidate = IMAGES_DIR / img_info.get("filename", "")
            if not candidate.exists():
                issues.append(f"이미지 {idx} 파일 없음")
            else:
                image_paths[idx] = str(candidate)
        elif not os.path.exists(filepath):
            issues.append(f"이미지 {idx} 파일 없음: {filepath}")

    # 6-2. AI 패턴 체크 (본문 전체)
    for pattern in AI_PATTERNS:
        if pattern in body:
            issues.append(f"AI 패턴 감지: '{pattern}' 사용됨")
            log(f"[검수] AI 패턴 감지: '{pattern}'")

    # 6-3. 네이버 제한어 체크 (salim1su 전용)
    if blog_id == "salim1su":
        for category, words in NAVER_RESTRICTED.items():
            for word in words:
                if word in body:
                    issues.append(f"네이버 제한어({category}): '{word}' 사용됨")
                    log(f"[검수] 네이버 제한어 감지 [{category}]: '{word}'")

    # 7. {{이미지N}} 마커가 본문에 남아있지 않음 확인은
    #    poster에서 처리하므로 여기서는 이미지 없이 마커만 있는 경우 체크
    remaining_markers = re.findall(r'\{\{이미지(\d+)\}\}', body)
    for marker_idx in remaining_markers:
        idx = int(marker_idx)
        if idx not in image_paths and not any(
            img["index"] == idx for img in images
        ):
            issues.append(f"{{{{이미지{idx}}}}} 마커 있지만 이미지 정보 없음")

    # 결과 (AI 패턴이 하나라도 감지되면 불합격)
    passed = len(issues) == 0

    if passed:
        log("[검수] ✓ 자동 검수 통과")

        # ── 팩트체크 (가격/스펙 검증 및 자동 수정) ──
        try:
            fc = _fact_check.run(body, keyword, blog_name=blog_id, on_log=on_log)
            if fc["corrections"]:
                log(f"[팩트체크] {len(fc['corrections'])}건 수정됨:")
                for c in fc["corrections"]:
                    log(
                        f"  - '{c['old_text']}' → '{c['new_text']}' "
                        f"(명시 {c['stated']:,.0f}원 / 실제 {c['actual']:,.0f}원 / "
                        f"오차 {c['ratio']:.0%})"
                    )
                result["body"] = fc["body"]
            elif fc["checked"]:
                log("[팩트체크] ✓ 수정 없음")
        except Exception as _fc_err:
            log(f"[팩트체크] 오류로 건너뜀: {_fc_err}")

    else:
        log(f"[검수] ⚠ 불합격 ({len(issues)}건)")
        for issue in issues:
            log(f"  - {issue}")

    if on_status:
        on_status("review", "done" if passed else "failed")

    return {
        "passed": passed,
        "issues": issues,
        "result": result,
    }
