import sys
import os
from pathlib import Path as _Path

# ── 프로젝트 루트 경로 설정 (.app 번들 / 일반 실행 모두 대응) ──────────────
if getattr(sys, "frozen", False):
    # .app/Contents/MacOS/executable → 5단계 위가 프로젝트 루트
    _PROJECT_ROOT = _Path(sys.executable).parent.parent.parent.parent.parent
else:
    _PROJECT_ROOT = _Path(__file__).parent

os.environ["BLOG_AUTO_PROJECT_ROOT"] = str(_PROJECT_ROOT)

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QFrame, QSizePolicy,
    QDialog, QLineEdit, QFormLayout, QDialogButtonBox, QMessageBox,
    QCheckBox, QScrollArea,
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QPoint, QSize,
)
from PyQt5.QtGui import QFont, QPainter, QColor, QPen, QBrush, QMovie, QFontMetrics
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ACCOUNTS, ACCOUNT_MAP

try:
    _base = Path(sys._MEIPASS)
except AttributeError:
    _base = Path(__file__).parent
ASSETS_DIR = _base / "assets"

AGENT_ORDER = ["goodisak", "nolja100", "salim1su", "baremi542", "common_review"]
AGENT_LABELS = {
    "goodisak":      "goodisak",
    "nolja100":      "nolja100",
    "salim1su":      "salim1su",
    "baremi542":     "baremi542",
    "common_review": "공통검수",
}
# 블로그 ID → 기존 GIF 파일명 매핑
GIF_STEMS = {
    "goodisak":      "keyword",
    "nolja100":      "writer",
    "salim1su":      "review",
    "baremi542":     "final_review",
    "common_review": "poster",
}

BLOG_CATEGORIES = {
    "goodisak":  "IT",
    "nolja100":  "여행",
    "salim1su":  "살림",
    "baremi542": "정부지원금",
}


# ─── 픽셀 아트 캐릭터 위젯 (GIF 없을 때 폴백) ────────────────────────────

class PixelCharLabel(QWidget):
    """8×13 픽셀 캐릭터 — QPainter로 그림. GIF 파일 없을 때 폴백."""

    PIX = 4  # 1 게임픽셀 = 화면 4×4 px

    AGENT_CLOTH = {
        "goodisak":      "#4da6ff",
        "nolja100":      "#ff9966",
        "salim1su":      "#55dd77",
        "baremi542":     "#cc88ff",
        "common_review": "#ffdd44",
    }
    STATE_CLOTH = {
        "done":   "#22dd55",
        "failed": "#ff5555",
    }

    # 각 행: 8 픽셀 (S=피부, H=머리카락, E=눈, C=옷, .=투명)
    WALK_F = [
        [   # frame 0 — 왼발 앞
            "..HHHH..",
            ".HSSSSH.",
            ".HSEESH.",
            ".HSSSSH.",
            "..SSSS..",
            ".CCCCCC.",
            "CCCCCCCC",
            ".CCCCCC.",
            "..CCCC..",
            ".CC..CC.",
            ".CC..CC.",
            "CC....CC",
            "C......C",
        ],
        [   # frame 1 — 오른발 앞
            "..HHHH..",
            ".HSSSSH.",
            ".HSEESH.",
            ".HSSSSH.",
            "..SSSS..",
            ".CCCCCC.",
            "CCCCCCCC",
            ".CCCCCC.",
            "..CCCC..",
            "..CCCC..",
            ".CC..CC.",
            "CC....CC",
            ".C....C.",
        ],
    ]

    def __init__(self, agent_id, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 64)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._agent = agent_id
        self._frame = 0
        self._state = "idle"
        self._walk_timer = QTimer(self)
        self._walk_timer.setInterval(500)
        self._walk_timer.timeout.connect(self._next_frame)
        self._walk_timer.start()

    def set_state(self, state: str):
        self._state = state
        self.update()

    def start_walk(self):
        self._walk_timer.setInterval(130)

    def stop_walk(self):
        self._walk_timer.setInterval(500)
        self._frame = 0
        self.update()

    def _next_frame(self):
        self._frame = (self._frame + 1) % len(self.WALK_F)
        self.update()

    def paintEvent(self, event):
        frame = self.WALK_F[self._frame]
        cloth_hex = self.STATE_CLOTH.get(self._state) or \
                    self.AGENT_CLOTH.get(self._agent, "#aaaaaa")
        cloth = QColor(cloth_hex)
        skin  = QColor("#f5cba7")
        hair  = QColor("#5d4037")
        eye   = QColor("#111111")

        ox = (64 - 8 * self.PIX) // 2   # x 오프셋 — 가운데 정렬
        oy = (64 - 13 * self.PIX) // 2  # y 오프셋

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        for r, row in enumerate(frame):
            for ci, px in enumerate(row):
                if px == '.':
                    continue
                x = ox + ci * self.PIX
                y = oy + r  * self.PIX
                col = {"S": skin, "H": hair, "E": eye}.get(px, cloth)
                p.fillRect(x, y, self.PIX, self.PIX, col)
        p.end()


# ─── 씬 내부 캐릭터 위젯 ──────────────────────────────────────────────────

class SceneChar(QWidget):
    """씬 안에서 절대좌표로 배치되는 소형 캐릭터 위젯"""

    W, H = 88, 116

    def __init__(self, agent_id, parent=None):
        super().__init__(parent)
        self.agent_id = agent_id
        self.state = "idle"
        self.setFixedSize(self.W, self.H)

        # GIF 로드 (블로그 ID → 기존 GIF 파일명 매핑)
        gif_stem = GIF_STEMS.get(agent_id, agent_id)
        self.movies = {}
        for state in ("idle", "working", "done", "failed"):
            p = ASSETS_DIR / f"{gif_stem}_{state}.gif"
            if p.exists():
                m = QMovie(str(p))
                m.setScaledSize(QSize(64, 64))
                self.movies[state] = m

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 4)
        lay.setSpacing(2)

        self.gif_label = QLabel()
        self.gif_label.setFixedSize(64, 64)
        self.gif_label.setAlignment(Qt.AlignCenter)
        self.gif_label.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(self.gif_label, alignment=Qt.AlignCenter)

        self.pixel_char = PixelCharLabel(agent_id)
        lay.addWidget(self.pixel_char, alignment=Qt.AlignCenter)

        # GIF 유효 여부에 따라 초기 표시 결정
        if self.movies:
            self.pixel_char.hide()
        else:
            self.gif_label.hide()

        self.name_label = QLabel(AGENT_LABELS.get(agent_id, agent_id))
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet(
            "color:#fff; font-size:10px; font-weight:bold;"
            "background:#333; border-radius:3px; padding:1px 4px; border:none;")
        lay.addWidget(self.name_label)

        self.status_label = QLabel("대기")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            "color:#888; font-size:9px; background:transparent; border:none;")
        lay.addWidget(self.status_label)

        self._apply_state("idle")

    def set_state(self, state):
        self.state = state
        self._apply_state(state)

    def set_walking(self, walking: bool):
        if walking:
            self.pixel_char.start_walk()
        else:
            self.pixel_char.stop_walk()

    def _apply_state(self, state):
        for m in self.movies.values():
            m.stop()

        bg  = {"idle":"#1e1e2e","working":"#0b2a1a","done":"#0a250a","failed":"#2a0b0b"}
        bdr = {"idle":"#444455","working":"#4ade80","done":"#22c55e","failed":"#ef4444"}
        col = {"idle":"#888","working":"#4ade80","done":"#22c55e","failed":"#f87171"}
        txt = {"idle":"대기","working":"작업 중","done":"완료!","failed":"실패"}
        nbg = {"idle":"#333344","working":"#14532d","done":"#166534","failed":"#7f1d1d"}

        self.setStyleSheet(
            f"background:{bg.get(state,'#1e1e2e')};"
            f"border:2px solid {bdr.get(state,'#444455')};"
            "border-radius:8px;")
        self.name_label.setStyleSheet(
            f"color:#fff; font-size:10px; font-weight:bold;"
            f"background:{nbg.get(state,'#333344')}; border-radius:3px;"
            "padding:1px 4px; border:none;")
        self.status_label.setText(txt.get(state, state))
        self.status_label.setStyleSheet(
            f"color:{col.get(state,'#888')}; font-size:9px;"
            "background:transparent; border:none;")

        m = self.movies.get(state)
        if m and m.isValid():
            self.gif_label.show()
            self.pixel_char.hide()
            self.gif_label.setMovie(m)
            m.start()
        else:
            self.gif_label.hide()
            self.pixel_char.show()
            self.pixel_char.set_state(state)


# ─── 거실 + 작업실 씬 위젯 ───────────────────────────────────────────────

class SceneWidget(QFrame):
    """캐릭터들이 거실 ↔ 작업실을 오가는 씬"""

    SCENE_W = 1100
    SCENE_H = 300

    # 거실 소파 위치 (5개) — 씬 왼쪽
    SOFA_X = [28, 116, 204, 292, 380]
    SOFA_Y = 160

    # 작업실 책상 위치 (5개) — 씬 오른쪽
    DESK_X = [600, 695, 790, 885, 980]
    DESK_Y = 140

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SCENE_W, self.SCENE_H)
        self.setStyleSheet("background:#12121e; border-radius:14px;")

        self._chars: dict[str, tuple[SceneChar, int]] = {}
        self._anims: dict[str, QTimer] = {}

        for i, aid in enumerate(AGENT_ORDER):
            c = SceneChar(aid, self)
            sx, sy = self.SOFA_X[i], self.SOFA_Y
            c.move(sx, sy)
            self._chars[aid] = (c, i)

    # ── 상태 업데이트 (외부에서 호출) ──
    def set_agent_state(self, agent_id: str, state: str):
        item = self._chars.get(agent_id)
        if not item:
            return
        c, idx = item
        c.set_state(state)
        if state == "working":
            self._move_to(agent_id, c, self.DESK_X[idx], self.DESK_Y)
        elif state in ("done", "failed", "idle"):
            # 완료 후 잠시 뒤에 복귀
            QTimer.singleShot(
                1500,
                lambda _aid=agent_id, _c=c, _i=idx: self._move_to(
                    _aid, _c, self.SOFA_X[_i], self.SOFA_Y
                ),
            )

    def reset_all(self):
        for aid, (c, i) in self._chars.items():
            c.set_state("idle")
            c.move(self.SOFA_X[i], self.SOFA_Y)

    # ── 애니메이션 (QTimer 프레임별 x좌표 이동) ──
    def _move_to(self, agent_id: str, c: SceneChar, tx: int, ty: int):
        if agent_id in self._anims:
            self._anims[agent_id].stop()
            self._anims[agent_id].deleteLater()

        STEPS = 20
        INTERVAL_MS = 45  # 20 steps × 45ms ≈ 900ms

        start_x = c.pos().x()
        dx = tx - start_x
        step = [0]

        # y는 즉시 이동, x만 프레임별 이동
        c.move(start_x, ty)
        c.set_walking(True)

        timer = QTimer(c)
        timer.setInterval(INTERVAL_MS)

        def _tick():
            step[0] += 1
            if step[0] >= STEPS:
                c.move(tx, ty)
                c.set_walking(False)
                timer.stop()
                return
            new_x = int(start_x + dx * step[0] / STEPS)
            c.move(new_x, ty)

        timer.timeout.connect(_tick)
        self._anims[agent_id] = timer
        timer.start()

    # ── 배경 그리기 ──
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        W, H = self.SCENE_W, self.SCENE_H

        # ── 거실 배경 ──
        p.fillRect(0, 0, 500, H, QColor("#1a1a2e"))

        # 소파
        sofa_color = QColor("#2d2d5e")
        p.setBrush(QBrush(sofa_color))
        p.setPen(QPen(QColor("#4444aa"), 2))
        p.drawRoundedRect(15, H - 80, 455, 50, 8, 8)
        # 소파 등받이
        p.drawRoundedRect(15, H - 110, 455, 35, 6, 6)

        # 거실 바닥
        p.fillRect(0, H - 30, 500, 30, QColor("#0f0f20"))

        # 거실 라벨
        p.setPen(QPen(QColor("#5555aa")))
        p.setFont(QFont("Arial", 11, QFont.Bold))
        p.drawText(10, 22, "🛋  거실")

        # ── 구분 벽 ──
        p.fillRect(498, 0, 6, H, QColor("#333355"))
        # 문
        p.setBrush(QBrush(QColor("#1a1a2e")))
        p.setPen(QPen(QColor("#6655aa"), 2))
        p.drawRoundedRect(498, H // 2 - 55, 6, 110, 3, 3)

        # ── 작업실 배경 ──
        p.fillRect(504, 0, W - 504, H, QColor("#0f1e1a"))

        # 책상들
        desk_color = QColor("#1a3a30")
        p.setBrush(QBrush(desk_color))
        p.setPen(QPen(QColor("#2a6050"), 2))
        desk_w = 76
        for dx in self.DESK_X:
            p.drawRoundedRect(dx - 2, H - 95, desk_w, 12, 3, 3)
            # 책상 다리
            p.drawRect(dx + 4, H - 83, 6, 25)
            p.drawRect(dx + desk_w - 12, H - 83, 6, 25)
            # 모니터
            p.setBrush(QBrush(QColor("#0d2a22")))
            p.setPen(QPen(QColor("#1a6050"), 1))
            p.drawRoundedRect(dx + 10, H - 135, 55, 38, 4, 4)
            p.setBrush(QBrush(desk_color))

        # 작업실 바닥
        p.fillRect(504, H - 30, W - 504, 30, QColor("#0a1410"))

        # 작업실 라벨
        p.setPen(QPen(QColor("#2a8060")))
        p.setFont(QFont("Arial", 11, QFont.Bold))
        p.drawText(514, 22, "💻  작업실")

        p.end()


# ─── 블로그 ON/OFF 토글 카드 ─────────────────────────────────────────────

class BlogCard(QFrame):
    """블로그 스케줄링 포함 여부 ON/OFF 토글 카드"""

    toggled = pyqtSignal(str, bool)  # blog_id, enabled
    run_requested = pyqtSignal(str)  # 즉시 실행 요청
    retry_requested = pyqtSignal(str)  # 실패 키워드 재시도 요청

    def __init__(self, blog_id: str, parent=None):
        super().__init__(parent)
        self.blog_id = blog_id
        self._enabled = True
        category = BLOG_CATEGORIES.get(blog_id, "")

        self.setFixedSize(220, 72)
        self._apply_style(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(3)

        top = QHBoxLayout()
        name = QLabel(blog_id)
        name.setStyleSheet("color:#fff; font-size:13px; font-weight:bold;"
                           "background:transparent; border:none;")
        top.addWidget(name)
        top.addStretch()

        self.toggle_btn = QPushButton("ON")
        self.toggle_btn.setFixedSize(40, 22)
        self.toggle_btn.setStyleSheet(
            "background:#22c55e; color:#fff; font-size:10px; font-weight:bold;"
            "border-radius:11px; border:none;")
        self.toggle_btn.clicked.connect(self._toggle)
        top.addWidget(self.toggle_btn)

        self.run_btn = QPushButton("▶")
        self.run_btn.setFixedSize(28, 22)
        self.run_btn.setStyleSheet(
            "background:#2563eb; color:#fff; font-size:11px; font-weight:bold;"
            "border-radius:11px; border:none;")
        self.run_btn.setToolTip(f"{blog_id} 즉시 실행")
        self.run_btn.clicked.connect(lambda: self.run_requested.emit(self.blog_id))
        top.addWidget(self.run_btn)

        self.retry_btn = QPushButton("↺")
        self.retry_btn.setFixedSize(28, 22)
        self.retry_btn.setStyleSheet(
            "background:#b45309; color:#fff; font-size:13px; font-weight:bold;"
            "border-radius:11px; border:none;")
        self.retry_btn.setToolTip(f"{blog_id} 실패 키워드 재시도")
        self.retry_btn.clicked.connect(lambda: self.retry_requested.emit(self.blog_id))
        top.addWidget(self.retry_btn)
        lay.addLayout(top)

        cat_label = QLabel(category)
        cat_label.setStyleSheet(
            "color:#aaa; font-size:11px; background:transparent; border:none;")
        lay.addWidget(cat_label)

    def _toggle(self):
        self._enabled = not self._enabled
        self._apply_style(self._enabled)
        self.toggle_btn.setText("ON" if self._enabled else "OFF")
        self.toggle_btn.setStyleSheet(
            f"background:{'#22c55e' if self._enabled else '#555'};"
            "color:#fff; font-size:10px; font-weight:bold;"
            "border-radius:11px; border:none;")
        self.toggled.emit(self.blog_id, self._enabled)

    def set_active(self, active: bool):
        """현재 처리 중인 블로그 하이라이트"""
        if active:
            self.setStyleSheet(
                "background:#1a2a3a; border:2px solid #facc15; border-radius:10px;")
        else:
            self._apply_style(self._enabled)

    def _apply_style(self, enabled: bool):
        bg  = "#1e2a1e" if enabled else "#1e1e1e"
        bdr = "#22c55e" if enabled else "#444"
        self.setStyleSheet(
            f"background:{bg}; border:2px solid {bdr}; border-radius:10px;")

    @property
    def is_enabled(self) -> bool:
        return self._enabled


# ─── 단일 블로그 즉시 실행 워커 ──────────────────────────────────────────

class SingleRunWorker(QThread):
    """단일 블로그 즉시 실행 워커"""
    log_signal    = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)
    blog_signal   = pyqtSignal(str)
    finished      = pyqtSignal(str)

    def __init__(self, blog_id: str):
        super().__init__()
        self.blog_id = blog_id

    def run(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents"))
        from agents import orchestrator
        self.blog_signal.emit(self.blog_id)
        try:
            result = orchestrator.run_single(
                self.blog_id,
                on_log=self._log,
                on_status=self._status,
            )
            if result["success"]:
                self.finished.emit(f"[완료] {self.blog_id}: {result['title']}")
            else:
                self.finished.emit(f"[실패] {self.blog_id}: {result['reason']}")
        except Exception as e:
            self.finished.emit(f"[오류] {self.blog_id}: {e}")
        finally:
            self.blog_signal.emit("")

    def _log(self, msg):
        self.log_signal.emit(msg)

    def _status(self, agent, state):
        self.status_signal.emit(agent, state)


# ─── 스케줄러 워커 ────────────────────────────────────────────────────────

class SchedulerWorker(QThread):
    log_signal    = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)
    blog_signal   = pyqtSignal(str)   # 현재 처리 중인 blog_id ("" = 없음)
    finished      = pyqtSignal(str)

    def __init__(self, enabled_blogs: list[str]):
        super().__init__()
        self._stop_flag    = False
        self.enabled_blogs = enabled_blogs

    def stop(self):
        self._stop_flag = True

    def run(self):
        import random
        from datetime import datetime, timedelta
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents"))
        from agents import orchestrator

        START_HOUR, END_HOUR   = 7, 23
        KEYWORD_ENGINE_HOUR    = 8   # 매일 오전 8시 키워드 수집
        MIN_INTERVAL, MAX_INTERVAL = 60, 180

        _keyword_engine_last_run = None  # 오늘 날짜 (str) 저장

        def _run_keyword_engine():
            nonlocal _keyword_engine_last_run
            today = datetime.now().strftime("%Y-%m-%d")
            if _keyword_engine_last_run == today:
                return  # 오늘 이미 실행
            self._log("[키워드수집] 오전 8시 키워드 엔진 시작...")
            try:
                from keyword_engine.main import run as run_engine
                run_engine(on_log=self._log)
                _keyword_engine_last_run = today
                self._log("[키워드수집] ✓ 키워드 수집 완료")
            except Exception as e:
                self._log(f"[키워드수집] 오류: {e}")

        self._log(f"[스케줄러] 시작 (7:00~23:00, 60~180분 간격, 8시 키워드수집)")
        self._log(f"[스케줄러] 활성 블로그: {self.enabled_blogs}")

        while not self._stop_flag:
            hour = datetime.now().hour
            if hour < START_HOUR or hour >= END_HOUR:
                now = datetime.now()
                if hour >= END_HOUR:
                    target = (now + timedelta(days=1)).replace(
                        hour=START_HOUR, minute=0, second=0)
                else:
                    target = now.replace(hour=START_HOUR, minute=0, second=0)
                wait = (target - now).total_seconds()
                self._log(f"[스케줄러] 비활동 시간 — {target.strftime('%H:%M')}까지 대기")
                self._sleep(wait)
                continue

            # 오전 8시: 키워드 수집 (하루 1회)
            if datetime.now().hour == KEYWORD_ENGINE_HOUR:
                _run_keyword_engine()

            blogs = [b for b in self.enabled_blogs
                     if b in orchestrator.DEFAULT_BLOG_ORDER
                     or b in orchestrator.BLOG_AGENT_MAP]

            for blog_id in blogs:
                if self._stop_flag:
                    break
                if not (START_HOUR <= datetime.now().hour < END_HOUR):
                    break

                self._log(f"[스케줄러] {blog_id} 파이프라인 시작")
                self.blog_signal.emit(blog_id)
                try:
                    result = orchestrator.run_single(
                        blog_id,
                        on_log=self._log,
                        on_status=self._status,
                    )
                    if result["success"]:
                        self._log(f"[스케줄러] ✅ {blog_id} 완료: {result['title']}")
                    else:
                        self._log(f"[스케줄러] ❌ {blog_id} 실패: {result['reason']}")
                except Exception as e:
                    self._log(f"[스케줄러] {blog_id} 오류: {e}")
                finally:
                    self.blog_signal.emit("")  # 처리 완료

                if blogs and blog_id != blogs[-1] and not self._stop_flag:
                    cd = random.randint(5, 15) * 60
                    self._log(f"[스케줄러] 다음 블로그까지 {cd // 60}분 대기")
                    self._sleep(cd)

            if self._stop_flag:
                break

            interval = random.randint(MIN_INTERVAL, MAX_INTERVAL) * 60
            from datetime import timedelta
            next_t = datetime.now() + timedelta(seconds=interval)
            self._log(f"[스케줄러] 다음 사이클: {next_t.strftime('%H:%M')} ({interval // 60}분 후)")
            self._sleep(interval)

        self.finished.emit("[스케줄러] 종료됨")

    def _sleep(self, seconds):
        import time as _t
        end = _t.time() + seconds
        while _t.time() < end and not self._stop_flag:
            _t.sleep(min(5, end - _t.time()))

    def _log(self, msg):
        self.log_signal.emit(msg)

    def _status(self, agent, state):
        self.status_signal.emit(agent, state)


# ─── 메인 앱 ─────────────────────────────────────────────────────────────

DARK_STYLE = """
QMainWindow { background: #13131f; }
QWidget     { background: #13131f; color: #e0e0e0; }
QLabel      { color: #e0e0e0; font-size: 13px; }
QTextEdit {
    background: #0e0e1a; color: #d4d4d4;
    border: 1px solid #2a2a44; border-radius: 8px;
    padding: 8px; font-size: 12px;
}
QPushButton {
    padding: 8px 18px; border: none; border-radius: 6px;
    font-size: 13px; color: #fff;
}
#startBtn { background: #16a34a; }
#startBtn:disabled { background: #555; }
#stopBtn  { background: #dc2626; }
#stopBtn:disabled { background: #555; }
#clearBtn { background: #333; }
"""


class SettingsDialog(QDialog):
    """API 키 / 환경변수 설정 다이얼로그 — 저장 시 .env 파일에 반영"""

    _ENV_PATH = _Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(_Path(__file__).parent))) / ".env"

    # 표시할 키 목록: (env_key, 레이블, placeholder, 비밀번호여부)
    _FIELDS = [
        ("WP_USER",         "WordPress 사용자명",      "admin",                   False),
        ("WP_APP_PASSWORD", "WordPress 애플리케이션 비밀번호", "xxxx xxxx xxxx xxxx xxxx xxxx", True),
        ("NOTION_TOKEN",    "Notion API 토큰",         "secret_...",              True),
        ("GEMINI_API_KEY",  "Gemini API 키",           "AIza...",                 True),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙ 설정 — API 키 관리")
        self.setMinimumWidth(520)
        self._inputs: dict[str, QLineEdit] = {}

        env_vals = self._load_env()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 안내 문구
        hint = QLabel("저장 버튼을 누르면 .env 파일에 즉시 반영됩니다.")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(8)
        for key, label, placeholder, is_pw in self._FIELDS:
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setText(env_vals.get(key, ""))
            edit.setMinimumHeight(30)
            if is_pw:
                edit.setEchoMode(QLineEdit.Password)
            self._inputs[key] = edit
            form.addRow(f"{label}:", edit)
        layout.addLayout(form)

        # 비밀번호 표시 토글
        toggle_btn = QPushButton("🔑  비밀번호 표시 / 숨기기")
        toggle_btn.setFixedHeight(28)
        toggle_btn.clicked.connect(self._toggle_pw_visibility)
        layout.addWidget(toggle_btn)

        # 버튼 박스
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Save).setText("저장")
        btn_box.button(QDialogButtonBox.Cancel).setText("취소")
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _toggle_pw_visibility(self):
        for key, _, _, is_pw in self._FIELDS:
            if is_pw:
                edit = self._inputs[key]
                edit.setEchoMode(
                    QLineEdit.Normal if edit.echoMode() == QLineEdit.Password
                    else QLineEdit.Password
                )

    def _load_env(self) -> dict:
        """현재 .env 파일에서 key=value 파싱"""
        vals = {}
        if self._ENV_PATH.exists():
            for line in self._ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    vals[k.strip()] = v.strip()
        return vals

    def _save(self):
        """입력값을 .env 파일에 반영 (기존 다른 키는 유지)"""
        # 현재 .env 전체 줄 읽기
        if self._ENV_PATH.exists():
            lines = self._ENV_PATH.read_text(encoding="utf-8").splitlines()
        else:
            lines = []

        new_vals = {key: self._inputs[key].text().strip() for key in self._inputs}

        # 기존 줄 중 해당 키 업데이트
        updated_keys = set()
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, _ = stripped.partition("=")
                k = k.strip()
                if k in new_vals:
                    new_lines.append(f"{k}={new_vals[k]}")
                    updated_keys.add(k)
                    continue
            new_lines.append(line)

        # 없던 키는 파일 끝에 추가
        for key, val in new_vals.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={val}")

        self._ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        # os.environ 즉시 반영
        for key, val in new_vals.items():
            if val:
                os.environ[key] = val

        QMessageBox.information(self, "저장 완료", ".env 파일에 저장되었습니다.\n앱 재시작 없이 즉시 적용됩니다.")
        self.accept()


class RetryFailedDialog(QDialog):
    """실패 키워드 목록을 보여주고 선택한 항목을 '대기'로 초기화하는 다이얼로그"""

    def __init__(self, blog_id: str, parent=None):
        super().__init__(parent)
        self.blog_id = blog_id
        self.setWindowTitle(f"↺  {blog_id} — 실패 키워드 재시도")
        self.setMinimumWidth(420)
        self._checks: list[tuple[QCheckBox, str]] = []  # (checkbox, page_id)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hint = QLabel("재시도할 키워드를 선택하면 상태를 '대기'로 초기화합니다.")
        hint.setStyleSheet("color:#888; font-size:11px;")
        layout.addWidget(hint)

        # 로딩 중 표시
        self._status_label = QLabel("키워드 목록 불러오는 중...")
        self._status_label.setStyleSheet("color:#aaa; font-size:12px;")
        layout.addWidget(self._status_label)

        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(260)
        scroll.setStyleSheet("background:#1a1a2e; border:1px solid #333;")
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setSpacing(4)
        self._list_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll)

        # 전체 선택 / 해제
        sel_row = QHBoxLayout()
        all_btn = QPushButton("전체 선택")
        all_btn.setFixedHeight(26)
        all_btn.clicked.connect(lambda: [c.setChecked(True) for c, _ in self._checks])
        none_btn = QPushButton("전체 해제")
        none_btn.setFixedHeight(26)
        none_btn.clicked.connect(lambda: [c.setChecked(False) for c, _ in self._checks])
        sel_row.addWidget(all_btn)
        sel_row.addWidget(none_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("선택 항목 재시도")
        btn_box.button(QDialogButtonBox.Cancel).setText("닫기")
        btn_box.accepted.connect(self._reset_selected)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        # 비동기로 목록 불러오기
        QTimer.singleShot(0, self._load_keywords)

    def _load_keywords(self):
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from overnight_run import fetch_failed_keywords
            items = fetch_failed_keywords(self.blog_id)
        except Exception as e:
            self._status_label.setText(f"오류: {e}")
            return

        if not items:
            self._status_label.setText("실패 키워드가 없습니다.")
            return

        self._status_label.setText(f"실패 키워드 {len(items)}개")
        for keyword, page_id in items:
            cb = QCheckBox(keyword)
            cb.setChecked(True)
            cb.setStyleSheet("color:#e0e0e0; font-size:12px;")
            self._list_layout.addWidget(cb)
            self._checks.append((cb, page_id))

    def _reset_selected(self):
        selected = [(c.text(), pid) for c, pid in self._checks if c.isChecked()]
        if not selected:
            QMessageBox.warning(self, "선택 없음", "재시도할 키워드를 선택해주세요.")
            return

        from overnight_run import update_keyword_status
        success = 0
        for keyword, page_id in selected:
            try:
                update_keyword_status(page_id, "대기")
                success += 1
            except Exception:
                pass

        QMessageBox.information(
            self, "완료",
            f"{success}/{len(selected)}개 키워드를 '대기' 상태로 초기화했습니다.\n"
            "다음 실행 시 자동으로 처리됩니다."
        )
        self.accept()


class BlogAutomationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Blog Automation v2")
        self.resize(1140, 760)
        self.sched_worker = None

        self._blog_enabled: dict[str, bool] = {
            a["blog"]: True for a in ACCOUNTS
        }

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # ── 씬 ──
        self.scene = SceneWidget()
        root.addWidget(self.scene, alignment=Qt.AlignHCenter)

        # ── 블로그 카드 행 ──
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        self._cards: dict[str, BlogCard] = {}
        for a in ACCOUNTS:
            card = BlogCard(a["blog"])
            card.toggled.connect(self._on_blog_toggled)
            card.run_requested.connect(self._run_single_blog)
            card.retry_requested.connect(self._on_retry_requested)
            self._cards[a["blog"]] = card
            cards_row.addWidget(card)
        cards_row.addStretch()

        # 스케줄러 시작/중지 버튼
        self.start_btn = QPushButton("▶  스케줄러 시작")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setFixedHeight(36)
        self.start_btn.clicked.connect(self._run_scheduler)
        cards_row.addWidget(self.start_btn, alignment=Qt.AlignVCenter)

        self.stop_btn = QPushButton("⏹  스케줄러 중지")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setFixedHeight(36)
        self.stop_btn.clicked.connect(self._stop_scheduler)
        self.stop_btn.setEnabled(False)
        cards_row.addWidget(self.stop_btn, alignment=Qt.AlignVCenter)
        root.addLayout(cards_row)

        # ── 로그 ──
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Menlo", 11))
        root.addWidget(self.log_box)

        # 하단 버튼 행
        bottom_row = QHBoxLayout()

        settings_btn = QPushButton("⚙  설정")
        settings_btn.setObjectName("clearBtn")
        settings_btn.setFixedWidth(80)
        settings_btn.clicked.connect(self._open_settings)
        bottom_row.addWidget(settings_btn, alignment=Qt.AlignLeft)

        bottom_row.addStretch()

        clear_btn = QPushButton("로그 지우기")
        clear_btn.setObjectName("clearBtn")
        clear_btn.setFixedWidth(100)
        clear_btn.clicked.connect(self.log_box.clear)
        bottom_row.addWidget(clear_btn, alignment=Qt.AlignRight)

        root.addLayout(bottom_row)

    # ── 설정 ──
    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec_()

    # ── 블로그 ON/OFF ──
    def _on_blog_toggled(self, blog_id: str, enabled: bool):
        self._blog_enabled[blog_id] = enabled
        self.log_box.append(
            f"[카드] {blog_id} {'활성화' if enabled else '비활성화'}")

    # ── 스케줄러 ──
    def _run_scheduler(self):
        if self.sched_worker and self.sched_worker.isRunning():
            return

        enabled = [bid for bid, on in self._blog_enabled.items() if on]
        if not enabled:
            self.log_box.append("[스케줄러] 활성 블로그 없음 — 시작 안 함")
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.scene.reset_all()

        self.sched_worker = SchedulerWorker(enabled)
        self.sched_worker.log_signal.connect(self.log_box.append)
        self.sched_worker.status_signal.connect(self._on_status)
        self.sched_worker.blog_signal.connect(self._on_blog_active)
        self.sched_worker.finished.connect(self._on_scheduler_done)
        self.sched_worker.start()

    def _stop_scheduler(self):
        if self.sched_worker and self.sched_worker.isRunning():
            self.sched_worker.stop()
            self.log_box.append("[스케줄러] 중지 요청...")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _on_scheduler_done(self, text):
        self.log_box.append(text)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.scene.reset_all()

    # ── 카드 클릭 → 단일 블로그 즉시 실행 ──
    def _run_single_blog(self, blog_id: str):
        if hasattr(self, 'sched_worker') and self.sched_worker and self.sched_worker.isRunning():
            self.log_box.append(f"[수동실행] 스케줄러 실행 중 — {blog_id} 건너뜀")
            return
        if hasattr(self, '_single_worker') and self._single_worker and self._single_worker.isRunning():
            self.log_box.append(f"[수동실행] 이미 실행 중 — {blog_id} 건너뜀")
            return
        self.log_box.append(f"[수동실행] {blog_id} 시작")
        self.scene.reset_all()
        self._single_worker = SingleRunWorker(blog_id)
        self._single_worker.log_signal.connect(self.log_box.append)
        self._single_worker.status_signal.connect(self._on_status)
        self._single_worker.blog_signal.connect(self._on_blog_active)
        self._single_worker.finished.connect(self._on_single_run_done)
        self._single_worker.start()

    def _on_single_run_done(self, text):
        self.log_box.append(text)

    def _on_retry_requested(self, blog_id: str):
        dlg = RetryFailedDialog(blog_id, self)
        dlg.exec_()

    # ── 블로그 처리 시작/종료 → 카드 하이라이트 + 캐릭터 이동 ──
    def _on_blog_active(self, blog_id: str):
        for bid, card in self._cards.items():
            card.set_active(bid == blog_id and blog_id != "")
        if blog_id:
            self.scene.set_agent_state(blog_id, "working")
        else:
            for aid in ["goodisak", "nolja100", "salim1su", "baremi542"]:
                self.scene.set_agent_state(aid, "idle")

    # ── 에이전트 상태 → 씬 업데이트 (검수 단계만 공통검수 캐릭터 이동) ──
    def _on_status(self, agent_id: str, state: str):
        if agent_id in ("review", "final_review"):
            self.scene.set_agent_state("common_review", state)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)
    window = BlogAutomationApp()
    window.show()
    sys.exit(app.exec_())
