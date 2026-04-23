#!/usr/bin/env python3
"""Blogspot 블로그 ID 입력 GUI"""
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import json

def save():
    blog_id = entry_id.get().strip()
    if not blog_id.isdigit():
        messagebox.showerror("오류", "블로그 ID는 숫자만 입력해주세요")
        return

    env_path = Path(__file__).parent / ".env"
    content = env_path.read_text() if env_path.exists() else ""

    lines = content.splitlines()

    # BLOGGER_BLOG_ID 교체 또는 추가
    new_lines = [l for l in lines if not l.startswith("BLOGGER_BLOG_ID")]
    new_lines.append(f"BLOGGER_BLOG_ID={blog_id}")

    env_path.write_text("\n".join(new_lines) + "\n")
    messagebox.showinfo("완료", f"저장 완료!\n\nBLOGGER_BLOG_ID={blog_id}")
    root.destroy()

root = tk.Tk()
root.title("Blogspot 블로그 ID 입력")
root.geometry("480x160")
root.resizable(False, False)
root.lift()
root.attributes('-topmost', True)

tk.Label(root, text="Blogger 블로그 ID (숫자):", font=("Arial", 12)).pack(pady=(20, 5))

entry_id = tk.Entry(root, width=55, font=("Monaco", 11))
entry_id.pack(padx=20)
entry_id.focus()

frame = tk.Frame(root)
frame.pack(pady=15)

tk.Button(frame, text="저장", command=save, width=10).pack(side=tk.LEFT, padx=5)
tk.Button(frame, text="취소", command=root.destroy, width=8).pack(side=tk.LEFT, padx=5)

root.bind('<Return>', lambda e: save())
root.mainloop()
