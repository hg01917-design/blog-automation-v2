#!/usr/bin/env python3
"""ANTHROPIC_API_KEY 입력 GUI"""
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

def save_key():
    key = entry.get().strip()
    if not key.startswith("sk-ant-"):
        messagebox.showerror("오류", "API 키는 sk-ant-로 시작해야 합니다")
        return

    env_path = Path(__file__).parent / ".env"
    content = env_path.read_text() if env_path.exists() else ""

    # 이미 있으면 교체, 없으면 추가
    lines = content.splitlines()
    new_lines = [l for l in lines if not l.startswith("ANTHROPIC_API_KEY")]
    new_lines.append(f"ANTHROPIC_API_KEY={key}")
    env_path.write_text("\n".join(new_lines) + "\n")

    messagebox.showinfo("완료", f"ANTHROPIC_API_KEY 저장 완료!\n\n{key[:20]}...")
    root.destroy()

root = tk.Tk()
root.title("Anthropic API 키 입력")
root.geometry("480x160")
root.resizable(False, False)
root.lift()
root.attributes('-topmost', True)

tk.Label(root, text="ANTHROPIC_API_KEY 입력:", font=("Arial", 12)).pack(pady=(20, 5))

entry = tk.Entry(root, width=55, show="*", font=("Monaco", 11))
entry.pack(padx=20)
entry.focus()

frame = tk.Frame(root)
frame.pack(pady=15)

# 보기/숨기기 토글
def toggle():
    entry.config(show="" if entry.cget("show") == "*" else "*")
    btn_toggle.config(text="숨기기" if entry.cget("show") == "" else "보기")

btn_toggle = tk.Button(frame, text="보기", command=toggle, width=8)
btn_toggle.pack(side=tk.LEFT, padx=5)

tk.Button(frame, text="저장", command=save_key, width=10).pack(side=tk.LEFT, padx=5)

tk.Button(frame, text="취소", command=root.destroy, width=8).pack(side=tk.LEFT, padx=5)

root.bind('<Return>', lambda e: save_key())
root.mainloop()
