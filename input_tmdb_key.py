#!/usr/bin/env python3
"""TMDB API Key 입력 GUI"""
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

def save_key():
    key = entry.get().strip()
    if not key:
        messagebox.showerror("오류", "API 키를 입력해주세요")
        return

    env_path = Path(__file__).parent / ".env"
    content = env_path.read_text() if env_path.exists() else ""

    lines = content.splitlines()
    new_lines = [l for l in lines if not l.startswith("TMDB_API_KEY")]
    new_lines.append(f"TMDB_API_KEY={key}")
    env_path.write_text("\n".join(new_lines) + "\n")

    messagebox.showinfo("완료", f"TMDB_API_KEY 저장 완료!\n\n{key[:10]}...")
    root.destroy()

root = tk.Tk()
root.title("TMDB API 키 입력")
root.geometry("520x180")
root.resizable(False, False)
root.lift()
root.attributes('-topmost', True)

tk.Label(root, text="TMDB API Key (v3) 입력:", font=("Arial", 13)).pack(pady=(20, 5))

entry = tk.Entry(root, width=58, font=("Monaco", 11))
entry.pack(padx=20)
entry.focus()

# Cmd+V 붙여넣기 명시 바인딩
entry.bind('<Command-v>', lambda e: None)

frame = tk.Frame(root)
frame.pack(pady=15)

tk.Button(frame, text="저장", command=save_key, width=12, bg="#1565c0", fg="white", font=("Arial", 12)).pack(side=tk.LEFT, padx=5)
tk.Button(frame, text="취소", command=root.destroy, width=8).pack(side=tk.LEFT, padx=5)

root.bind('<Return>', lambda e: save_key())
root.mainloop()
