"""Claude 생성 글에서 본문 HTML과 이미지 프롬프트를 분리"""
import re


def parse_content(raw_text: str):
    """Claude 응답에서 HTML 본문과 이미지 정보를 분리한다.

    Returns:
        (html_body, images) 튜플
        - html_body: HTML 본문 문자열 (이미지 섹션 완전 제거됨)
        - images: [{"index": 1, "section": "H2제목", "prompt": "영문프롬프트",
                     "filename": "파일명.webp", "alt": "한글설명"}, ...]
    """
    # 이미지 정보 파싱: [이미지1] - {H2 소제목명}
    images = []
    img_blocks = re.findall(
        r'\[이미지(\d+)\]\s*-\s*(.+?)(?:\n|$)'
        r'.*?이미지 프롬프트\(영문\):\s*(.+?)(?:\n|$)'
        r'.*?파일명:\s*(.+?)(?:\n|$)'
        r'.*?alt태그:\s*(.+?)(?:\n|$)',
        raw_text, re.DOTALL
    )
    for m in img_blocks:
        images.append({
            "index": int(m[0]),
            "section": m[1].strip(),
            "prompt": m[2].strip(),
            "filename": m[3].strip(),
            "alt": m[4].strip(),
        })

    # 이미지 섹션 전체 제거 (```javascript 블록 포함)
    # [이미지1] 부터 끝까지, 또는 ``` 코드블록 안의 이미지 정보
    cleaned = raw_text

    # ```javascript ... ``` 이미지 정보 블록 제거
    cleaned = re.sub(
        r'```javascript\s*\n\s*\[이미지\d+\].*?```',
        '', cleaned, flags=re.DOTALL
    )
    # ``` 없이 나오는 이미지 섹션도 제거
    cleaned = re.sub(
        r'\[이미지\d+\]\s*-\s*.+?(?=\[이미지\d+\]|\Z)',
        '', cleaned, flags=re.DOTALL
    )
    # "본문 작성 후 아래 형식으로 이미지 정보 출력" 안내문 제거
    cleaned = re.sub(
        r'본문 작성 후 아래 형식으로.*$',
        '', cleaned, flags=re.DOTALL
    )

    # ```html ... ``` 코드블록에서 HTML 추출
    html_match = re.search(r'```html?\s*\n(.*?)```', cleaned, re.DOTALL)
    if html_match:
        html_body = html_match.group(1).strip()
    else:
        # 코드블록 없으면 <h1 또는 <p 부터 시작하는 HTML 찾기
        html_match = re.search(r'(<(?:!DOCTYPE|h[12]|p|div).*)', cleaned, re.DOTALL | re.IGNORECASE)
        html_body = html_match.group(1).strip() if html_match else cleaned.strip()

    # HTML에서 남은 잔여 텍스트 정리
    html_body = re.sub(r'<!--.*?제목:.*?-->\s*', '', html_body)
    # 코드블록 잔여분 제거 (javascript, ``` 등)
    html_body = re.sub(r'\s*```\w*\s*$', '', html_body)
    html_body = re.sub(r'^\s*```\w*\s*', '', html_body)
    html_body = html_body.strip()

    return html_body, images
