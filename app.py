import sys
import os
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QLineEdit, QTextEdit, QPushButton, QFrame,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRect, QPoint
from PyQt5.QtGui import QFont, QPainter, QColor, QPen, QBrush

# 같은 디렉토리의 모듈 import를 위해 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ACCOUNTS, ACCOUNT_MAP
from claude_playwright import generate_text
from login_playwright import login_blog, login_naver
from poster import post_single, post_all


# ─── 픽셀 캐릭터 위젯 ───

AGENT_COLORS = {
    "keyword":      {"shirt": "#3b82f6", "pants": "#1e40af", "name": "키워드"},
    "writer":       {"shirt": "#22c55e", "pants": "#15803d", "name": "작성"},
    "review":       {"shirt": "#eab308", "pants": "#a16207", "name": "검수"},
    "final_review": {"shirt": "#a855f7", "pants": "#7e22ce", "name": "최종"},
    "poster":       {"shirt": "#ef4444", "pants": "#b91c1c", "name": "포스팅"},
}


class PixelCharacterWidget(QWidget):
    """96x96 Stardew Valley 스타일 픽셀 캐릭터 — 관절 움직임 애니메이션"""

    def __init__(self, agent_id, parent=None):
        super().__init__(parent)
        self.agent_id = agent_id
        info = AGENT_COLORS.get(agent_id, {"shirt": "#888", "pants": "#555", "name": agent_id})
        self.shirt = QColor(info["shirt"])
        self.pants = QColor(info["pants"])
        self.shirt_hi = self.shirt.lighter(125)
        self.shirt_dk = self.shirt.darker(125)
        self.pants_dk = self.pants.darker(120)
        self.agent_name = info["name"]
        self.state = "idle"
        self.frame = 0
        self.task_text = "대기"

        self.setFixedSize(110, 140)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(150)

    def set_state(self, state):
        self.state = state
        self.task_text = {"idle": "대기", "working": "작업 중...",
                          "done": "완료!", "failed": "실패"}.get(state, state)
        self.frame = 0
        self.update()

    def _tick(self):
        self.frame += 1
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        ox = (self.width() - 96) // 2
        oy = 0
        s = 2  # pixel scale: 48x48 grid → 96x96 px

        nf = 4 if self.state == "working" else 3
        f = self.frame % nf

        # ── Stardew Valley Palette ──
        SK = QColor("#f5c8a0")        # skin
        SK_S = QColor("#d4a070")      # skin shadow
        HR = QColor("#5a3825")        # hair
        HR_H = QColor("#7a5040")      # hair highlight
        EY = QColor("#1a1008")        # eye pupil
        EW = QColor("#ffffff")        # eye white
        BL = QColor("#e8a0a0")        # blush
        MO = QColor("#c0806a")        # mouth
        DK = QColor("#c49060")        # desk
        DK_D = QColor("#a07048")      # desk dark
        MN = QColor("#404050")        # monitor
        MS = QColor("#0a0a1e")        # monitor screen
        CH = QColor("#705038")        # chair
        CH_L = QColor("#907060")      # chair light
        KB = QColor("#505058")        # keyboard
        SH = QColor("#3a2a1a")        # shoes

        def F(x, y, w, h, c):
            p.fillRect(QRect(ox + x * s, oy + y * s, w * s, h * s), QBrush(c))

        # ── Animation offsets (grid units) ──
        hdy = bdy = 0
        lax = lay = rax = ray = 0
        stand = fcover = mblink = False

        # 호흡 애니메이션 (모든 상태에서 미세하게)
        breath = 1 if (self.frame // 4) % 2 == 0 else 0

        if self.state == "idle":
            if f == 1:
                hdy = 1                  # 머리 살짝 아래 (꾸벅)
        elif self.state == "working":
            if f == 1:
                ray = -2                 # 오른팔 살짝 올림
            elif f == 2:
                lay = -2                 # 왼팔 살짝 올림
            elif f == 3:
                lay = 1; ray = 1         # 양팔 내림
                mblink = True            # 모니터 깜빡
        elif self.state == "done":
            if f == 0:
                bdy = -1; hdy = -2       # 일어서는 모션
            else:
                stand = True
                bdy = -3; hdy = -5       # 완전히 일어남
                lay = ray = -10          # 양팔 번쩍
                lax = -2; rax = 2        # 팔 벌림
        elif self.state == "failed":
            if f == 0:
                hdy = 2                  # 고개 숙임
            else:
                hdy = 3                  # 더 숙임
                fcover = True            # 손으로 얼굴 가림

        # ═══ 1. CHAIR BACK (뒤쪽) ═══
        F(4, 14, 2, 16, CH)
        F(5, 14, 1, 16, CH_L)

        # ═══ 2. MONITOR ═══
        F(28, 0, 18, 14, MN)
        scr = QColor("#162040") if mblink else MS
        F(30, 2, 14, 10, scr)
        F(35, 14, 4, 2, MN)           # 받침대
        F(33, 16, 8, 1, MN)           # 받침 바닥
        # 화면 내용
        if self.state == "working":
            g = QColor("#4ade80")
            for r in range(4):
                w = 3 + (f + r) % 5
                if not (f == 3 and r >= 3):
                    F(31, 3 + r * 2, min(w, 12), 1, g)
            if f % 2 == 0:
                F(31 + 3 + f % 3, 9, 1, 1, QColor("#ffffff"))  # 커서
        elif self.state == "done":
            p.setPen(QPen(QColor("#4ade80")))
            p.setFont(QFont("Courier", 8, QFont.Bold))
            p.drawText(QRect(ox + 30 * s, oy + 2 * s, 14 * s, 10 * s),
                       Qt.AlignCenter, "OK!")
        elif self.state == "failed":
            p.setPen(QPen(QColor("#ef4444")))
            p.setFont(QFont("Courier", 7, QFont.Bold))
            p.drawText(QRect(ox + 30 * s, oy + 2 * s, 14 * s, 10 * s),
                       Qt.AlignCenter, "ERR")
        else:
            # 스크린세이버 — 바운싱 도트
            t = self.frame % 20
            dx = t if t < 10 else 20 - t
            dy = (self.frame // 3) % 6
            dy = dy if dy < 3 else 6 - dy
            F(31 + dx, 5 + dy, 1, 1, QColor("#303050"))
            F(31 + (10 - dx), 5 + (3 - dy), 1, 1, QColor("#252540"))

        # ═══ 3. LEGS — 앉은 자세 (책상 뒤) ═══
        if not stand:
            F(11, 26, 5, 6, self.pants)
            F(11, 26, 1, 6, self.pants_dk)
            F(16, 26, 5, 6, self.pants)
            F(16, 26, 1, 6, self.pants_dk)
            F(10, 32, 6, 2, SH)        # 왼쪽 신발
            F(16, 32, 6, 2, SH)        # 오른쪽 신발

        # ═══ 4. DESK ═══
        F(2, 24, 44, 2, DK)
        F(2, 24, 44, 1, DK.lighter(110))   # 책상 상판 하이라이트
        F(4, 26, 2, 14, DK_D)              # 왼쪽 다리
        F(42, 26, 2, 14, DK_D)             # 오른쪽 다리
        # 키보드 (작업 중 글로우 효과)
        if self.state == "working":
            kb_glow = QColor("#606878") if f % 2 == 0 else KB
            F(26, 23, 10, 1, kb_glow)
            # 눌리는 키 애니메이션
            key_pos = [27, 29, 31, 33]
            active_key = key_pos[f % 4]
            for kp in key_pos:
                c = QColor("#90e0a0") if kp == active_key else QColor("#606068")
                F(kp, 23, 2, 1, c)
        else:
            F(26, 23, 10, 1, KB)
            F(27, 23, 2, 1, QColor("#606068"))
            F(31, 23, 2, 1, QColor("#606068"))

        # ═══ 5. CHAIR SEAT + FRONT LEGS ═══
        F(4, 30, 20, 2, CH)
        F(4, 30, 20, 1, CH_L)
        F(6, 32, 2, 8, CH)             # 왼쪽 의자 다리
        F(20, 32, 2, 8, CH)            # 오른쪽 의자 다리

        # ═══ 6. LEGS — 서 있는 자세 (의자/책상 앞) ═══
        if stand:
            ly = 24 + bdy
            lh = 34 - ly
            F(11, ly, 5, lh, self.pants)
            F(16, ly, 5, lh, self.pants)
            F(10, 34, 6, 2, SH)
            F(16, 34, 6, 2, SH)

        # ═══ 7. BODY (셔츠) + 호흡 ═══
        F(10, 16 + bdy, 12, 8 + breath, self.shirt)
        F(10, 16 + bdy, 2, 8 + breath, self.shirt_dk)   # 왼쪽 음영
        F(15, 17 + bdy, 3, 4, self.shirt_hi)              # 하이라이트
        F(13, 16 + bdy, 6, 1, self.shirt_dk)              # 칼라

        # ═══ 8. ARMS ═══
        if fcover:
            # 손으로 얼굴 가림
            F(10, 9 + hdy, 4, 5, SK)
            F(18, 9 + hdy, 4, 5, SK)
        else:
            # 왼팔 — 소매 + 팔뚝 + 손
            lx, ly2 = 7 + lax, 17 + lay + bdy
            F(lx, ly2, 3, 4, self.shirt)
            F(lx, ly2 + 4, 3, 3, SK)
            F(lx - 1, ly2 + 6, 4, 2, SK)
            # 오른팔
            rx, ry = 22 + rax, 17 + ray + bdy
            F(rx, ry, 3, 4, self.shirt)
            F(rx, ry + 4, 3, 3, SK)
            F(rx, ry + 6, 4, 2, SK)

        # ═══ 9. HEAD ═══
        hy = hdy
        # 머리카락 (뒷부분)
        F(9, 2 + hy, 14, 4, HR)
        F(10, 1 + hy, 12, 2, HR)
        F(13, 2 + hy, 4, 2, HR_H)          # 하이라이트
        # 얼굴
        F(9, 5 + hy, 14, 10, SK)
        F(9, 5 + hy, 1, 10, SK_S)          # 왼쪽 음영
        F(22, 5 + hy, 1, 10, SK_S)         # 오른쪽 음영
        # 앞머리 (얼굴 위에)
        F(8, 4 + hy, 3, 5, HR)
        F(21, 4 + hy, 3, 4, HR)
        F(10, 5 + hy, 3, 3, HR)

        # 눈
        if self.state == "idle" and f == 1:
            # 감은 눈 (졸림)
            F(12, 9 + hy, 3, 1, EY)
            F(18, 9 + hy, 3, 1, EY)
        elif self.state == "done":
            # ^_^ 해피 아이
            F(12, 9 + hy, 1, 1, EY); F(14, 9 + hy, 1, 1, EY)
            F(13, 8 + hy, 1, 1, EY)
            F(18, 9 + hy, 1, 1, EY); F(20, 9 + hy, 1, 1, EY)
            F(19, 8 + hy, 1, 1, EY)
        elif self.state == "failed" and f >= 1:
            # X_X 실패 눈
            F(12, 8 + hy, 1, 1, EY); F(14, 8 + hy, 1, 1, EY)
            F(13, 9 + hy, 1, 1, EY)
            F(12, 10 + hy, 1, 1, EY); F(14, 10 + hy, 1, 1, EY)
            F(18, 8 + hy, 1, 1, EY); F(20, 8 + hy, 1, 1, EY)
            F(19, 9 + hy, 1, 1, EY)
            F(18, 10 + hy, 1, 1, EY); F(20, 10 + hy, 1, 1, EY)
        else:
            # 기본 눈 (흰자 + 동공)
            F(12, 8 + hy, 3, 3, EW)
            F(13, 9 + hy, 2, 2, EY)
            F(18, 8 + hy, 3, 3, EW)
            F(19, 9 + hy, 2, 2, EY)

        # 볼터치 (Stardew Valley 스타일)
        if self.state != "failed":
            F(10, 11 + hy, 2, 1, BL)
            F(20, 11 + hy, 2, 1, BL)

        # 입
        if self.state == "done":
            # 웃는 입 ∪
            F(14, 13 + hy, 4, 1, MO)
            F(13, 12 + hy, 1, 1, MO)
            F(18, 12 + hy, 1, 1, MO)
        elif self.state == "failed":
            # 슬픈 입 ∩
            F(14, 12 + hy, 4, 1, MO)
            F(13, 13 + hy, 1, 1, MO)
            F(18, 13 + hy, 1, 1, MO)
        else:
            # 기본 입 —
            F(14, 13 + hy, 4, 1, MO)

        # ✦ 반짝이 효과 (완료)
        if self.state == "done" and f >= 1:
            sparkle = QColor("#fff44f")
            sparkle2 = QColor("#ffffff")
            # 머리 위 별
            sp = (self.frame // 2) % 4
            sx = [6, 25, 12, 20][sp]
            sy = [0, 2, -1, 1][sp]
            F(sx, sy + hy, 1, 1, sparkle2)
            F(sx - 1, sy + 1 + hy, 1, 1, sparkle)
            F(sx + 1, sy + 1 + hy, 1, 1, sparkle)
            F(sx, sy + 2 + hy, 1, 1, sparkle2)
            # 추가 작은 별
            sp2 = (self.frame // 3) % 3
            sx2 = [3, 27, 15][sp2]
            sy2 = [4, 0, 2][sp2]
            F(sx2, sy2 + hy, 1, 1, sparkle)

        # 땀방울 (실패)
        if self.state == "failed" and f >= 1:
            F(24, 6 + hy, 2, 3, QColor("#60a5fa"))
            F(25, 9 + hy, 1, 1, QColor("#60a5fa"))

        # ═══ 10. TEXT ═══
        p.setPen(QPen(QColor("#e0e0e0")))
        p.setFont(QFont("Arial", 9, QFont.Bold))
        p.drawText(QRect(0, 100, self.width(), 16), Qt.AlignCenter, self.agent_name)

        p.setFont(QFont("Arial", 8))
        stc = {"idle": "#888", "working": "#4ade80",
               "done": "#22c55e", "failed": "#ef4444"}
        p.setPen(QPen(QColor(stc.get(self.state, "#888"))))
        p.drawText(QRect(0, 116, self.width(), 16), Qt.AlignCenter, self.task_text)

        p.end()


class PixelOfficeWidget(QWidget):
    """탑다운 Stardew Valley 스타일 픽셀 사무실 — 에이전트 5명 작업 시각화"""

    DESKS = [
        (15, 14, "keyword"),
        (78, 14, "writer"),
        (15, 65, "review"),
        (78, 65, "final_review"),
        (168, 40, "poster"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("agentPanel")
        self.agents = {}
        for *_, aid in self.DESKS:
            info = AGENT_COLORS.get(aid, {"shirt": "#888", "pants": "#555", "name": aid})
            self.agents[aid] = {
                "state": "idle", "frame": 0,
                "shirt": QColor(info["shirt"]),
                "pants": QColor(info["pants"]),
                "name": info["name"],
            }
        self.setMinimumSize(700, 390)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(150)

    def set_agent_state(self, agent_id, state):
        if agent_id in self.agents:
            self.agents[agent_id]["state"] = state
            self.agents[agent_id]["frame"] = 0
            self.update()

    def reset_all(self):
        for a in self.agents.values():
            a["state"] = "idle"
            a["frame"] = 0
        self.update()

    def _tick(self):
        for a in self.agents.values():
            a["frame"] += 1
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        s = 3
        ow = self.width() // s
        oh = self.height() // s

        def F(x, y, w, h, c):
            p.fillRect(QRect(x * s, y * s, w * s, h * s), QBrush(c))

        # ═══ FLOOR ═══
        main_w = 152
        F(0, 0, main_w, oh, QColor("#7a6548"))
        F(main_w + 3, 0, ow - main_w - 3, oh, QColor("#4a5568"))
        F(main_w, 0, 3, oh, QColor("#5a4a3a"))
        # Tile grid — office
        for tx in range(0, main_w, 10):
            F(tx, 0, 1, oh, QColor("#6e5b40"))
        for ty in range(0, oh, 10):
            F(0, ty, main_w, 1, QColor("#6e5b40"))
        # Tile grid — lounge
        lx0 = main_w + 3
        for tx in range(lx0, ow, 12):
            F(tx, 0, 1, oh, QColor("#424d5e"))
        for ty in range(0, oh, 12):
            F(lx0, ty, ow - lx0, 1, QColor("#424d5e"))

        # ═══ WALLS ═══
        F(0, 0, ow, 8, QColor("#5a4a3a"))
        F(0, 0, ow, 2, QColor("#4a3a2a"))
        F(0, 7, ow, 1, QColor("#6a5a48"))

        # ═══ BOOKSHELVES ═══
        bk_colors = ["#c44040", "#4080b0", "#40a040", "#c0a030", "#a040a0", "#40a0a0"]
        for sx in [5, 42, 80, 118]:
            F(sx, 2, 28, 5, QColor("#6a5040"))
            F(sx, 2, 28, 1, QColor("#8a7060"))
            F(sx + 27, 2, 1, 5, QColor("#5a4030"))
            for i in range(6):
                bx = sx + 1 + i * 4
                bh = 2 + (i % 3)
                F(bx, 3, 3, bh, QColor(bk_colors[i]))
                F(bx, 3, 1, bh, QColor(bk_colors[i]).lighter(130))

        # ═══ LOUNGE ═══
        lrx = main_w + 8
        # Wall painting
        F(lrx + 10, 2, 16, 10, QColor("#8a7060"))
        F(lrx + 11, 3, 14, 8, QColor("#87ceeb"))
        F(lrx + 11, 8, 14, 3, QColor("#4a8a4a"))
        F(lrx + 17, 4, 3, 3, QColor("#f0e060"))
        # Sofa
        sofa_x, sofa_y = lrx + 3, 85
        F(sofa_x, sofa_y, 30, 3, QColor("#8a4040"))
        F(sofa_x, sofa_y + 3, 30, 8, QColor("#a05050"))
        F(sofa_x, sofa_y + 3, 30, 2, QColor("#b06060"))
        F(sofa_x, sofa_y + 3, 4, 8, QColor("#8a4040"))
        F(sofa_x + 26, sofa_y + 3, 4, 8, QColor("#8a4040"))
        F(sofa_x + 6, sofa_y + 4, 5, 4, QColor("#e0c060"))
        # Coffee table
        F(sofa_x + 8, sofa_y + 13, 14, 5, QColor("#7a6a5a"))
        F(sofa_x + 8, sofa_y + 13, 14, 1, QColor("#8a7a6a"))
        F(sofa_x + 12, sofa_y + 14, 3, 2, QColor("#e8e0d0"))
        # Vending machine
        vm_x = lrx + 38
        if vm_x + 12 < ow:
            F(vm_x, 8, 10, 16, QColor("#4a6a8a"))
            F(vm_x + 1, 9, 8, 8, QColor("#2a4a6a"))
            F(vm_x + 1, 9, 8, 1, QColor("#3a5a7a"))
            for i in range(3):
                F(vm_x + 2 + i * 2, 11, 1, 4, QColor("#e0a040"))
                F(vm_x + 3 + i * 2, 11, 1, 4, QColor("#40a0e0"))
            F(vm_x + 3, 18, 4, 2, QColor("#3a5a7a"))
            F(vm_x + 4, 19, 2, 1, QColor("#60e060"))

        # ═══ PLANTS ═══
        for px, py in [(60, 50), (130, 50), (8, 100), (140, 100),
                        (lrx + 38, 75), (lrx, 30)]:
            if px + 6 < ow and py + 8 < oh:
                F(px + 1, py + 5, 4, 3, QColor("#8a6040"))
                F(px + 1, py + 5, 4, 1, QColor("#a07050"))
                F(px + 1, py + 1, 4, 4, QColor("#2d8a4e"))
                F(px, py + 2, 6, 2, QColor("#3aaa5e"))
                F(px + 2, py, 2, 2, QColor("#2d8a4e"))

        # ═══ WALL CLOCK ═══
        clx = main_w - 12
        F(clx, 1, 8, 6, QColor("#d0c8b8"))
        F(clx + 1, 2, 6, 4, QColor("#f0e8d8"))
        F(clx + 4, 2, 1, 3, QColor("#333"))
        F(clx + 4, 4, 2, 1, QColor("#333"))

        # ═══ DESKS + AGENTS ═══
        for dx, dy, aid in self.DESKS:
            ag = self.agents[aid]
            nf = 4 if ag["state"] == "working" else 3
            f = ag["frame"] % nf
            st = ag["state"]
            shirt = ag["shirt"]

            # ── Animation offsets ──
            cdy = 0
            typing = False
            if st == "idle":
                cdy = 1 if f == 1 else 0
            elif st == "working":
                cdy = -1; typing = True
            elif st == "done":
                cdy = 3 if f >= 1 else 1
            elif st == "failed":
                cdy = 1

            # ── Monitor ──
            F(dx + 7, dy, 10, 5, QColor("#303040"))
            msc = QColor("#162040") if (st == "working" and f == 3) else QColor("#0a0a1e")
            F(dx + 8, dy + 1, 8, 3, msc)
            F(dx + 11, dy + 5, 2, 1, QColor("#303040"))
            if st == "working":
                gc = QColor("#4ade80")
                for r in range(3):
                    lw = 2 + (f + r) % 5
                    if not (f == 3 and r == 2):
                        F(dx + 8, dy + 1 + r, min(lw, 7), 1, gc)
                if f % 2 == 0:
                    F(dx + 8 + 2 + f % 3, dy + 3, 1, 1, QColor("#fff"))
            elif st == "done":
                F(dx + 9, dy + 2, 5, 1, QColor("#4ade80"))
            elif st == "failed":
                F(dx + 9, dy + 2, 5, 1, QColor("#ef4444"))
            else:
                dot = ag["frame"] % 6
                F(dx + 8 + dot, dy + 2, 1, 1, QColor("#252540"))

            # ── Desk surface ──
            F(dx, dy + 6, 24, 5, QColor("#9a7a56"))
            F(dx, dy + 6, 24, 1, QColor("#b09070"))
            F(dx, dy + 10, 24, 1, QColor("#7a6040"))
            # Keyboard
            F(dx + 8, dy + 7, 8, 2, QColor("#404048"))
            if typing:
                kx = dx + 9 + (f % 3) * 2
                F(kx, dy + 7, 2, 1, QColor("#80d0a0"))
            # Mug
            F(dx + 20, dy + 7, 2, 2, QColor("#e8e0d0"))
            F(dx + 20, dy + 7, 2, 1, QColor("#c49060"))
            # Papers
            F(dx + 2, dy + 7, 4, 3, QColor("#e8e0d0"))
            F(dx + 2, dy + 7, 4, 1, QColor("#d0c8b8"))

            # ── Chair ──
            chy = dy + 13 + cdy
            F(dx + 7, chy + 7, 10, 3, QColor("#454545"))
            F(dx + 6, chy + 2, 12, 6, QColor("#505050"))
            F(dx + 6, chy + 2, 12, 1, QColor("#5a5a5a"))
            F(dx + 7, chy + 10, 2, 1, QColor("#333"))
            F(dx + 15, chy + 10, 2, 1, QColor("#333"))

            # ── Character (top-down back view) ──
            skin = QColor("#f5c8a0")
            hair = QColor("#5a3825")
            cx = dx + 8
            cy = dy + 13 + cdy

            if st == "done" and f >= 1:
                # Standing up — celebration
                F(cx + 1, cy, 6, 1, hair)
                F(cx, cy + 1, 8, 2, hair)
                F(cx + 2, cy + 1, 3, 1, QColor("#7a5040"))
                F(cx + 2, cy + 3, 4, 1, skin)
                F(cx - 1, cy + 4, 10, 4, shirt)
                F(cx + 2, cy + 5, 4, 2, shirt.lighter(120))
                F(cx, cy + 8, 3, 3, ag["pants"])
                F(cx + 5, cy + 8, 3, 3, ag["pants"])
                # Arms spread
                F(cx - 3, cy + 4, 2, 2, skin)
                F(cx + 9, cy + 4, 2, 2, skin)
                # Sparkles
                sp = ag["frame"] // 2 % 4
                sps = [(cx - 4, cy - 1), (cx + 11, cy),
                       (cx + 4, cy - 2), (cx + 9, cy - 1)]
                sx, sy = sps[sp]
                F(sx, sy, 1, 1, QColor("#fff44f"))
                F(sx + 1, sy - 1, 1, 1, QColor("#ffffff"))
            else:
                # Sitting — back of head + shoulders
                F(cx + 1, cy, 6, 1, hair)
                F(cx, cy + 1, 8, 3, hair)
                F(cx + 2, cy + 1, 3, 1, QColor("#7a5040"))
                F(cx - 1, cy + 2, 1, 2, skin)     # left ear
                F(cx + 8, cy + 2, 1, 2, skin)      # right ear
                F(cx + 2, cy + 4, 4, 1, skin)      # neck
                F(cx - 1, cy + 5, 10, 1, shirt)    # shoulders
                F(cx, cy + 6, 8, 3, shirt)          # back
                F(cx + 3, cy + 6, 2, 2, shirt.lighter(120))
                if typing:
                    # Arms reaching forward
                    F(cx - 2, cy + 4, 2, 2, shirt.darker(110))
                    F(cx + 8, cy + 4, 2, 2, shirt.darker(110))
                    F(cx - 2, cy + 3, 2, 1, skin)
                    F(cx + 8, cy + 3, 2, 1, skin)
                if st == "failed" and f >= 1:
                    # Sweat + dark cloud
                    F(cx + 9, cy + 1, 1, 2, QColor("#60a5fa"))
                    F(cx, cy - 1, 8, 1, QColor("#40405a"))

            # ── Agent label ──
            ly = dy + 27 + (cdy if st != "done" else 5)
            p.setPen(QPen(QColor("#e0e0e0")))
            p.setFont(QFont("Arial", 8, QFont.Bold))
            p.drawText(QRect((dx - 2) * s, ly * s, 28 * s, 5 * s),
                       Qt.AlignCenter, ag["name"])
            # Status dot
            dot_c = {"idle": "#666", "working": "#4ade80",
                     "done": "#22c55e", "failed": "#ef4444"}
            F(dx + 10, ly + 5, 4, 2, QColor(dot_c.get(st, "#666")))

        p.end()


class OrchestratorWorker(QThread):
    """orchestrator.run_all()을 실행하는 워커"""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)  # (agent_name, state)
    finished = pyqtSignal(str)

    def __init__(self, blog_ids=None):
        super().__init__()
        self.blog_ids = blog_ids

    def run(self):
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents"))
            from agents import orchestrator
            results = orchestrator.run_all(
                blog_ids=self.blog_ids,
                on_log=self._emit_log,
                on_status=self._emit_status,
            )
            success = sum(1 for r in results if r["success"])
            total = len(results)
            self.finished.emit(f"[에이전트] 완료: {success}/{total} 성공")
        except Exception as e:
            self.finished.emit(f"[에이전트 오류] {e}")

    def _emit_log(self, msg):
        self.log_signal.emit(msg)

    def _emit_status(self, agent, state):
        self.status_signal.emit(agent, state)


class SingleAgentWorker(QThread):
    """orchestrator.run_single()을 실행하는 워커"""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)
    finished = pyqtSignal(str)

    def __init__(self, blog_id, keyword=None):
        super().__init__()
        self.blog_id = blog_id
        self.keyword = keyword

    def run(self):
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents"))
            from agents import orchestrator
            result = orchestrator.run_single(
                self.blog_id,
                keyword=self.keyword,
                on_log=self._emit_log,
                on_status=self._emit_status,
            )
            if result["success"]:
                self.finished.emit(f"[에이전트] 발행 완료: {result['title']}")
            else:
                self.finished.emit(f"[에이전트] 실패: {result['reason']}")
        except Exception as e:
            self.finished.emit(f"[에이전트 오류] {e}")

    def _emit_log(self, msg):
        self.log_signal.emit(msg)

    def _emit_status(self, agent, state):
        self.status_signal.emit(agent, state)


DARK_STYLE = """
QMainWindow { background: #1e1e1e; }
QLabel { color: #e0e0e0; font-size: 14px; }
QComboBox, QLineEdit {
    background: #2d2d2d; color: #e0e0e0; border: 1px solid #555;
    border-radius: 6px; padding: 6px 10px; font-size: 14px;
}
QTextEdit {
    background: #111; color: #d4d4d4; border: 1px solid #333;
    border-radius: 8px; padding: 8px; font-size: 13px;
}
QPushButton {
    padding: 10px 20px; border: none; border-radius: 6px;
    font-size: 14px; color: #fff;
}
#runBtn { background: #2563eb; }
#runBtn:disabled { background: #555; }
#loginBtn { background: #16a34a; }
#loginBtn:disabled { background: #555; }
#naverBtn { background: #03c75a; }
#naverBtn:disabled { background: #555; }
#postBtn { background: #dc2626; }
#postBtn:disabled { background: #555; }
#postAllBtn { background: #9333ea; }
#postAllBtn:disabled { background: #555; }
#clearBtn { background: #444; }
#agentBtn { background: #f59e0b; }
#agentBtn:disabled { background: #555; }
#agentAllBtn { background: #9333ea; }
#agentAllBtn:disabled { background: #555; }
#agentPanel {
    background: #181818; border: 1px solid #333;
    border-radius: 8px;
}
"""


class CliWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword

    def run(self):
        prompt = f"{self.keyword} 블로그 글 3줄만 써줘"
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        try:
            result = subprocess.run(
                ["claude", "-p", prompt, "--print"],
                capture_output=True, text=True, timeout=60, env=env,
            )
            output = result.stdout.strip() if result.stdout else result.stderr.strip()
            self.finished.emit(f"[응답]\n{output}")
        except subprocess.TimeoutExpired:
            self.finished.emit("[오류] 60초 타임아웃 초과")
        except FileNotFoundError:
            self.finished.emit("[오류] claude CLI를 찾을 수 없습니다. PATH를 확인하세요.")
        except Exception as e:
            self.finished.emit(f"[오류] {e}")


class PlaywrightWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, keyword, blog_id=None):
        super().__init__()
        self.keyword = keyword
        self.blog_id = blog_id

    def run(self):
        try:
            result = generate_text(
                prompt=f"{self.keyword} 블로그 글 써줘",
                blog_id=self.blog_id,
                keyword=self.keyword,
                on_log=self._emit_log,
            )
            self.finished.emit(f"[Playwright 결과]\n{result}")
        except Exception as e:
            self.finished.emit(f"[Playwright 오류] {e}")

    def _emit_log(self, msg):
        self.log_signal.emit(msg)


class LoginWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, blog_id):
        super().__init__()
        self.blog_id = blog_id

    def run(self):
        try:
            ok = login_blog(self.blog_id, on_log=self._emit_log)
            status = "성공" if ok else "수동 확인 필요"
            self.finished.emit(f"[로그인 {status}]")
        except Exception as e:
            self.finished.emit(f"[로그인 오류] {e}")

    def _emit_log(self, msg):
        self.log_signal.emit(msg)


class PostSingleWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, blog_id, keyword):
        super().__init__()
        self.blog_id = blog_id
        self.keyword = keyword

    def run(self):
        try:
            # 테스트용 콘텐츠
            title = f"{self.keyword} — 블로그 자동 포스팅 테스트"
            content = (
                f"{self.keyword}에 대한 자동 생성 테스트 글입니다.\n"
                f"이 글은 blog-automation-v2로 자동 작성되었습니다.\n"
                f"테스트가 완료되면 삭제해 주세요."
            )
            tags = [self.keyword, "자동포스팅", "테스트"]
            ok = post_single(self.blog_id, title, content, tags,
                             on_log=self._emit_log)
            status = "성공" if ok else "실패"
            self.finished.emit(f"[포스팅 {status}]")
        except Exception as e:
            self.finished.emit(f"[포스팅 오류] {e}")

    def _emit_log(self, msg):
        self.log_signal.emit(msg)


class PostAllWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword

    def run(self):
        try:
            # 모든 계정용 테스트 콘텐츠 생성
            contents = {}
            for a in ACCOUNTS:
                blog_id = a["blog"]
                contents[blog_id] = {
                    "title": f"{self.keyword} — {blog_id} 자동 포스팅",
                    "content": (
                        f"{self.keyword}에 대한 자동 생성 글입니다.\n"
                        f"블로그: {blog_id} ({a['platform']})\n"
                        f"테스트 완료 후 삭제해 주세요."
                    ),
                }
            tags_map = {a["blog"]: [self.keyword, "자동포스팅"] for a in ACCOUNTS}
            results = post_all(self.keyword, contents, tags_map,
                               on_log=self._emit_log)
            self.finished.emit("[순환 포스팅 완료]")
        except Exception as e:
            self.finished.emit(f"[순환 포스팅 오류] {e}")

    def _emit_log(self, msg):
        self.log_signal.emit(msg)


class BlogAutomationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Blog Automation v2")
        self.resize(900, 800)
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # --- 상단: 블로그 선택 + 키워드 ---
        top = QHBoxLayout()
        top.addWidget(QLabel("블로그 선택"))
        self.blog_combo = QComboBox()
        self.blog_combo.addItems([a["blog"] for a in ACCOUNTS])
        self.blog_combo.setFixedWidth(160)
        top.addWidget(self.blog_combo)

        top.addWidget(QLabel("키워드"))
        self.keyword_input = QLineEdit("도쿄 여행")
        top.addWidget(self.keyword_input)
        layout.addLayout(top)

        # --- 에이전트 사무실 뷰 (탑다운 픽셀 아트) ---
        self.office = PixelOfficeWidget()
        layout.addWidget(self.office)

        # --- 로그인 + 포스팅 + 에이전트 버튼 행 ---
        action_row = QHBoxLayout()

        self.login_btn = QPushButton("로그인")
        self.login_btn.setObjectName("loginBtn")
        self.login_btn.clicked.connect(self._run_login)
        action_row.addWidget(self.login_btn)

        self.agent_btn = QPushButton("에이전트 실행")
        self.agent_btn.setObjectName("agentBtn")
        self.agent_btn.clicked.connect(self._run_agent_single)
        action_row.addWidget(self.agent_btn)

        self.agent_all_btn = QPushButton("전체 에이전트")
        self.agent_all_btn.setObjectName("agentAllBtn")
        self.agent_all_btn.clicked.connect(self._run_agent_all)
        action_row.addWidget(self.agent_all_btn)

        self.post_btn = QPushButton("단일 포스팅")
        self.post_btn.setObjectName("postBtn")
        self.post_btn.clicked.connect(self._run_post_single)
        action_row.addWidget(self.post_btn)

        self.post_all_btn = QPushButton("전체 순환 포스팅")
        self.post_all_btn.setObjectName("postAllBtn")
        self.post_all_btn.clicked.connect(self._run_post_all)
        action_row.addWidget(self.post_all_btn)

        action_row.addStretch()
        layout.addLayout(action_row)

        # --- 중앙: 로그 ---
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Menlo", 12))
        layout.addWidget(self.log_box)

        # --- 하단: 버튼 ---
        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("Claude CLI 테스트")
        self.run_btn.setObjectName("runBtn")
        self.run_btn.clicked.connect(self._run_test)
        btn_row.addWidget(self.run_btn)

        self.pw_btn = QPushButton("Playwright 글 생성")
        self.pw_btn.setObjectName("runBtn")
        self.pw_btn.clicked.connect(self._run_playwright)
        btn_row.addWidget(self.pw_btn)

        btn_row.addStretch()

        clear_btn = QPushButton("로그 지우기")
        clear_btn.setObjectName("clearBtn")
        clear_btn.clicked.connect(self.log_box.clear)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

    def _run_test(self):
        self.run_btn.setEnabled(False)
        self.run_btn.setText("실행 중...")
        self.log_box.append(">>> Claude CLI 호출 시작...")

        keyword = self.keyword_input.text().strip() or "도쿄 여행"
        self.worker = CliWorker(keyword)
        self.worker.finished.connect(self._on_result)
        self.worker.start()

    def _on_result(self, text):
        self.log_box.append(text)
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Claude CLI 테스트")

    # --- Playwright 글 생성 ---
    def _run_playwright(self):
        self.pw_btn.setEnabled(False)
        self.pw_btn.setText("생성 중...")
        self.log_box.append(">>> Playwright claude.ai 글 생성 시작...")

        keyword = self.keyword_input.text().strip() or "도쿄 여행"
        blog_id = self.blog_combo.currentText()
        self.pw_worker = PlaywrightWorker(keyword, blog_id=blog_id)
        self.pw_worker.log_signal.connect(self.log_box.append)
        self.pw_worker.finished.connect(self._on_pw_result)
        self.pw_worker.start()

    def _on_pw_result(self, text):
        self.log_box.append(text)
        self.pw_btn.setEnabled(True)
        self.pw_btn.setText("Playwright 글 생성")

    # --- 로그인 (선택된 블로그) ---
    def _run_login(self):
        self.login_btn.setEnabled(False)
        self.login_btn.setText("로그인 중...")
        blog_id = self.blog_combo.currentText()
        self.login_worker = LoginWorker(blog_id)
        self.login_worker.log_signal.connect(self.log_box.append)
        self.login_worker.finished.connect(self._on_login_done)
        self.login_worker.start()

    def _on_login_done(self, text):
        self.log_box.append(text)
        self.login_btn.setEnabled(True)
        self.login_btn.setText("로그인")

    # --- 단일 포스팅 (선택된 블로그) ---
    def _run_post_single(self):
        self.post_btn.setEnabled(False)
        self.post_btn.setText("포스팅 중...")
        blog_id = self.blog_combo.currentText()
        keyword = self.keyword_input.text().strip() or "도쿄 여행"
        self.post_worker = PostSingleWorker(blog_id, keyword)
        self.post_worker.log_signal.connect(self.log_box.append)
        self.post_worker.finished.connect(self._on_post_done)
        self.post_worker.start()

    def _on_post_done(self, text):
        self.log_box.append(text)
        self.post_btn.setEnabled(True)
        self.post_btn.setText("단일 포스팅")

    # --- 전체 순환 포스팅 ---
    def _run_post_all(self):
        self.post_all_btn.setEnabled(False)
        self.post_all_btn.setText("순환 중...")
        keyword = self.keyword_input.text().strip() or "도쿄 여행"
        self.post_all_worker = PostAllWorker(keyword)
        self.post_all_worker.log_signal.connect(self.log_box.append)
        self.post_all_worker.finished.connect(self._on_post_all_done)
        self.post_all_worker.start()

    def _on_post_all_done(self, text):
        self.log_box.append(text)
        self.post_all_btn.setEnabled(True)
        self.post_all_btn.setText("전체 순환 포스팅")

    # --- 에이전트 실행 (단일 블로그) ---
    def _run_agent_single(self):
        self.agent_btn.setEnabled(False)
        self.agent_btn.setText("실행 중...")
        self._reset_characters()
        blog_id = self.blog_combo.currentText()
        keyword = self.keyword_input.text().strip() or None
        self.agent_worker = SingleAgentWorker(blog_id, keyword)
        self.agent_worker.log_signal.connect(self.log_box.append)
        self.agent_worker.status_signal.connect(self._update_character)
        self.agent_worker.finished.connect(self._on_agent_done)
        self.agent_worker.start()

    # --- 에이전트 실행 (전체 블로그) ---
    def _run_agent_all(self):
        self.agent_all_btn.setEnabled(False)
        self.agent_all_btn.setText("실행 중...")
        self._reset_characters()
        self.agent_all_worker = OrchestratorWorker()
        self.agent_all_worker.log_signal.connect(self.log_box.append)
        self.agent_all_worker.status_signal.connect(self._update_character)
        self.agent_all_worker.finished.connect(self._on_agent_all_done)
        self.agent_all_worker.start()

    def _on_agent_done(self, text):
        self.log_box.append(text)
        self.agent_btn.setEnabled(True)
        self.agent_btn.setText("에이전트 실행")

    def _on_agent_all_done(self, text):
        self.log_box.append(text)
        self.agent_all_btn.setEnabled(True)
        self.agent_all_btn.setText("전체 에이전트")

    def _update_character(self, agent_name, state):
        """on_status 콜백 → 사무실 에이전트 상태 업데이트"""
        self.office.set_agent_state(agent_name, state)

    def _reset_characters(self):
        self.office.reset_all()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)
    window = BlogAutomationApp()
    window.show()
    sys.exit(app.exec_())
