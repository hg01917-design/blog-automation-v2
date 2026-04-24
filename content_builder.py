"""최종 HTML 조립 — 이미지 삽입 + 애드센스 삽입 로직"""
import re
import os
from pathlib import Path

# .env에서 ADSENSE_CODE 읽기
_env_path = Path(__file__).parent / ".env"
_adsense_code = ""
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("ADSENSE_CODE="):
            _adsense_code = line.split("=", 1)[1].strip()


def insert_adsense_markers(marker_text: str, blog_id: str = "") -> str:
    """마커 텍스트에 ##AD## 마커를 규칙에 맞게 삽입한다.

    삽입 위치 규칙:
    - H2 소제목 바로 앞에만 삽입
    - 표(##TABLE:N##) 바로 뒤에 삽입 가능
    - 이미지 위/아래 삽입 금지 (이미지는 H2 뒤에 삽입되므로 H2 앞은 안전)
    - 본문 맨 마지막 삽입 금지 (티스토리 — 카카오광고 자리)
    - 워드프레스(baremi542)는 본문 말미 가능

    글자수 기준 (마커/태그 제외 순수 텍스트):
    - 3000자 미만 → 1개 (첫번째 H2 앞)
    - 3000~5000자 → 2개 (첫번째 H2 앞, 두번째 H2 앞)
    - 5000자 이상 → 3개 (첫번째 H2 앞, 두번째 H2 앞, 표 아래)
    """
    # 네이버 블로그(salim1su)는 애드센스 미적용
    if blog_id == "salim1su":
        return marker_text

    if '##AD##' in marker_text or '[애드센스]' in marker_text:
        return marker_text  # 이미 삽입되어 있으면 건드리지 않음

    lines = marker_text.split('\n')

    # 순수 텍스트 길이 계산 (마커, 태그 제외)
    plain = re.sub(r'##(H[23]|AD|TABLE:\d+):?.*?##', '', marker_text)
    plain = re.sub(r'<[^>]+>', '', plain)
    plain = re.sub(r'\s+', '', plain)
    char_count = len(plain)

    # 광고 개수 결정
    if char_count < 3000:
        max_ads = 1
    elif char_count < 5000:
        max_ads = 2
    else:
        max_ads = 3

    # H2 위치와 TABLE 위치 찾기
    # ##H2:heading## 형식(마커) 또는 ## heading (마크다운) 모두 인식
    h2_indices = [i for i, ln in enumerate(lines)
                  if re.match(r'##H2:.+?##', ln.strip())
                  or re.match(r'^##\s+\S', ln.strip())
                  or re.match(r'^\[H2\].+\[/H2\]', ln.strip(), re.IGNORECASE)]
    table_indices = [i for i, ln in enumerate(lines) if re.match(r'##TABLE:\d+##', ln.strip())]

    # 삽입 위치 계산 (line index 기준, 뒤에서부터 삽입하기 위해 역순 정렬)
    insert_positions = []

    # 1순위: 첫번째 H2 앞
    if len(h2_indices) >= 1:
        insert_positions.append(h2_indices[0])

    # 2순위: 두번째 H2 앞
    if max_ads >= 2 and len(h2_indices) >= 2:
        insert_positions.append(h2_indices[1])

    # 3순위: 표 아래 (5000자 이상일 때)
    if max_ads >= 3 and table_indices:
        # 첫 번째 표 바로 다음 줄에 삽입
        table_after = table_indices[0] + 1
        # H2 바로 앞에 이미 삽입되는 위치와 겹치지 않도록
        if table_after not in insert_positions:
            insert_positions.append(table_after)

    # 본문 말미 — 워드프레스(baremi542)만 허용
    is_wordpress = blog_id == "baremi542"
    if is_wordpress and len(insert_positions) < max_ads:
        insert_positions.append(len(lines))

    # max_ads 개수만큼만
    insert_positions = insert_positions[:max_ads]

    # 뒤에서부터 삽입 (인덱스 밀림 방지)
    for pos in sorted(insert_positions, reverse=True):
        lines.insert(pos, '##AD##')

    return '\n'.join(lines)


def build_html(html_body: str, image_paths: dict = None, image_infos: list = None):
    """HTML 본문에 실제 애드센스 코드와 이미지를 삽입한다.

    Args:
        html_body: Claude가 생성한 HTML
        image_paths: {index: filepath} 이미지 경로 (gemini_image 결과)
        image_infos: [{"index": 1, "section": "...", "alt": "...", "filename": "..."}, ...]

    Returns:
        최종 HTML 문자열
    """
    image_paths = image_paths or {}
    image_infos = image_infos or []

    # 1. 애드센스 코드 치환 (ca-pub-XXXXXXXX → 실제 코드)
    if _adsense_code:
        html_body = html_body.replace("ca-pub-XXXXXXXX", _adsense_code)

    # 2. <body>...</body> 사이만 추출 (있으면)
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html_body, re.DOTALL | re.IGNORECASE)
    if body_match:
        html_body = body_match.group(1).strip()

    # 3. <h1> 제거 (제목은 에디터 제목 필드에 입력)
    title = ""
    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_body, re.DOTALL | re.IGNORECASE)
    if h1_match:
        title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()
        html_body = html_body[:h1_match.start()] + html_body[h1_match.end():]

    # 4. 이미지 삽입 — 각 H2 아래에 대응하는 이미지 추가
    if image_paths and image_infos:
        # H2 태그 위치 찾기
        h2_positions = [(m.start(), m.end()) for m in re.finditer(r'<h2[^>]*>.*?</h2>', html_body, re.DOTALL | re.IGNORECASE)]

        # 뒤에서부터 삽입 (인덱스 안 밀리게)
        for info in reversed(image_infos):
            idx = info["index"]
            if idx not in image_paths:
                continue
            filepath = image_paths[idx]
            alt = info.get("alt", "")

            # 이미지 idx번째 → h2_positions[idx-1] 뒤에 삽입
            h2_idx = idx - 1
            if h2_idx < len(h2_positions):
                insert_pos = h2_positions[h2_idx][1]
                img_tag = f'\n<p><img src="file://{filepath}" alt="{alt}" /></p>\n'
                html_body = html_body[:insert_pos] + img_tag + html_body[insert_pos:]

    # 5. 불필요한 wrapper 정리
    html_body = html_body.strip()
    html_body = re.sub(r'<!DOCTYPE[^>]*>', '', html_body, flags=re.IGNORECASE)
    html_body = re.sub(r'</?html[^>]*>', '', html_body, flags=re.IGNORECASE)
    html_body = re.sub(r'<head[^>]*>.*?</head>', '', html_body, flags=re.DOTALL | re.IGNORECASE)

    return title, html_body.strip()
