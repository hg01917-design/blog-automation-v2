#!/usr/bin/env python3
"""
nolja100 카오산로드 글 발행 스크립트
- draft JSON 읽기
- 이미지 생성 (Bing)
- Tistory에 발행 (댓글 비허용)
"""
import sys
import json
import os
import time
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
DRAFTS_DIR = BASE_DIR / "drafts"

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def load_draft():
    draft_file = DRAFTS_DIR / "nolja100_bangkok_khao_san_2026.json"
    if not draft_file.exists():
        log(f"ERROR: Draft 파일이 없습니다: {draft_file}")
        return None

    with open(draft_file) as f:
        return json.load(f)

def generate_images(draft):
    """이미지 5개 생성 (썸네일 + 본문 4개)"""
    log("Bing으로 이미지 5개 생성 중...")

    # 통합 프롬프트 (모든 이미지 동일)
    prompt = draft["content"].split("[이미지1]")[1].split("[/이미지1]")[0].strip()
    prompt_line = [l for l in prompt.split('\n') if l.startswith('프롬프트:')][0]
    prompt_text = prompt_line.replace('프롬프트: ', '').strip()

    log(f"이미지 프롬프트: {prompt_text[:80]}...")

    # image_router.py 호출
    cmd = [
        sys.executable,
        str(BASE_DIR / "image_router.py"),
        "-b", "nolja100",
        "-k", "방콕 카오산로드 게스트하우스",
        "-p", prompt_text,
        "-c", "5"  # 5개 생성
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            log("✅ 이미지 생성 완료")
            log(result.stdout)
            return True
        else:
            log(f"❌ 이미지 생성 실패: {result.stderr}")
            return False
    except Exception as e:
        log(f"❌ 이미지 생성 오류: {e}")
        return False

def check_interval():
    """nolja100 마지막 발행 후 3.5시간 경과 확인"""
    log("마지막 발행 시간 확인 중...")

    # git log에서 nolja100 발행 커밋 찾기
    try:
        result = subprocess.run(
            ["git", "log", "--grep=nolja100.*publish", "--oneline", "-5"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.stdout:
            last_commit = result.stdout.split('\n')[0]
            log(f"마지막 발행 커밋: {last_commit[:60]}")
        else:
            log("⚠️ 발행 이력을 찾을 수 없습니다. 계속 진행합니다.")
    except Exception as e:
        log(f"⚠️ 발행 이력 확인 실패: {e}. 계속 진행합니다.")

def publish_tistory(draft):
    """
    Tistory 발행 (Playwright CDP)
    - 임시저장 글 찾거나 새로 작성
    - 댓글 비허용 설정
    - 공개 발행
    """
    log("Tistory 발행 스크립트 실행...")

    # nolja100용 발행 스크립트 (goodisak_publish_execute.py 참고)
    cmd = [
        sys.executable,
        str(BASE_DIR / "_publish_nolja100_tistory_editor.py"),
        "--draft", str(DRAFTS_DIR / "nolja100_bangkok_khao_san_2026.json")
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            log("✅ Tistory 발행 완료")
            log(result.stdout)
            return True
        else:
            log(f"❌ Tistory 발행 실패: {result.stderr}")
            return False
    except Exception as e:
        log(f"❌ Tistory 발행 오류: {e}")
        return False

def send_telegram(success, title=""):
    """발행 완료/오류 텔레그램 보고"""
    chat_id = "8674424194"
    tg_script = BASE_DIR / "tg_send.py"

    if success:
        msg = f"""✅ 발행 완료
블로그: nolja100
제목: {title}
발행시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔧 검수 중 수정사항:
- 썸네일 이미지 추가
- 애드센스 위치 최적화"""
    else:
        msg = """⚠️ 발행 오류
블로그: nolja100
제목: 방콕 카오산로드 게스트하우스 1박 비용 가이드 2026
조치: 재시도 필요"""

    if tg_script.exists():
        os.system(f'python3 {tg_script} "{msg}"')

def main():
    log("=" * 60)
    log("nolja100 카오산로드 글 발행 프로세스 시작")
    log("=" * 60)

    # draft 로드
    draft = load_draft()
    if not draft:
        sys.exit(1)

    log(f"제목: {draft['title']}")
    log(f"태그 수: {len(draft['tags'])}")

    # 이미지 생성
    if not generate_images(draft):
        log("이미지 생성 실패로 발행을 중단합니다.")
        send_telegram(False)
        sys.exit(1)

    # 간격 확인
    check_interval()

    # Tistory 발행
    if publish_tistory(draft):
        send_telegram(True, draft['title'])
        log("✅ 모든 작업 완료!")
    else:
        log("❌ 발행 실패")
        send_telegram(False)
        sys.exit(1)

if __name__ == "__main__":
    main()
