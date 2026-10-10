from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from .config import DEFAULT_CONFIG_PATH, load_settings, update_persona
from .database import Labyrinth
from .runtime import ShepardRuntime
from .webapp import create_server


BG = "#080a11"
SURFACE = "#0f1320"
RAISED = "#171c2a"
LINE = "#2a3143"
TEXT = "#f4f6fb"
MUTED = "#99a3b8"
AMBER = "#f5b942"
RED = "#ff726f"


class ShepardDesktop:
    def __init__(self, root: tk.Tk, config_path: str | Path | None = None):
        self.root = root
        self.config_path = str(config_path or DEFAULT_CONFIG_PATH)
        self.settings = load_settings(self.config_path)
        self.db = Labyrinth(self.settings.database_path)
        self.db.initialize()
        self.selected_job_id: str | None = None
        self.runtime_lock = threading.Lock()
        self.web_server = None

        self.root.title("Shepard · Control Room")
        self.root.geometry("1220x790")
        self.root.minsize(900, 620)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._configure_style()
        self._build()
        self.refresh()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                        rowheight=34, borderwidth=0, font=("Helvetica", 12))
        style.configure("Treeview.Heading", background=RAISED, foreground=MUTED,
                        relief="flat", borderwidth=0, font=("Helvetica", 10, "bold"))
        style.map("Treeview", background=[("selected", "#2a2c2b")], foreground=[("selected", TEXT)])
        style.map("Treeview.Heading", background=[("active", RAISED)])

    def _label(self, parent, text: str, *, color: str = TEXT, size: int = 12,
               weight: str = "normal", **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Helvetica", size, weight), **kwargs)

    def _button(self, parent, text: str, command, *, primary: bool = False):
        return tk.Button(
            parent, text=text, command=command, cursor="hand2", relief="flat", bd=0,
            padx=16, pady=9, bg=AMBER if primary else RAISED,
            fg="#171006" if primary else TEXT,
            activebackground="#ffc95d" if primary else "#22293a",
            activeforeground="#171006" if primary else TEXT,
            font=("Helvetica", 11, "bold" if primary else "normal"),
        )

    def _build(self) -> None:
        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)

        rail = tk.Frame(shell, bg="#0b0f19", width=224, highlightbackground=LINE, highlightthickness=1)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        brand = tk.Frame(rail, bg=rail.cget("bg"))
        brand.pack(fill="x", padx=22, pady=(28, 18))
        mark = tk.Label(brand, text="S", width=3, height=1, bg=AMBER, fg="#171006",
                        font=("Helvetica", 17, "bold"))
        mark.pack(side="left", padx=(0, 12))
        brand_text = tk.Frame(brand, bg=brand.cget("bg"))
        brand_text.pack(side="left")
        self._label(brand_text, "Shepard", size=15, weight="bold").pack(anchor="w")
        self._label(brand_text, "CONTROL ROOM", color=MUTED, size=8).pack(anchor="w")

        self._label(rail, "THE FLOCK", color=AMBER, size=9, weight="bold").pack(anchor="w", padx=22, pady=(24, 8))
        self.agent_list = tk.Listbox(rail, bg=rail.cget("bg"), fg=TEXT, selectbackground=RAISED,
                                     selectforeground=TEXT, relief="flat", bd=0,
                                     highlightthickness=0, font=("Helvetica", 12), activestyle="none")
        self.agent_list.pack(fill="both", expand=True, padx=12)
        self.agent_list.bind("<Double-Button-1>", self.edit_selected_agent)

        web_button = self._button(rail, "Open web dashboard", self.open_web)
        web_button.pack(fill="x", padx=16, pady=(12, 8))
        self.status_label = self._label(rail, "●  Shepard ready", color="#62d394", size=10)
        self.status_label.pack(anchor="w", padx=22, pady=(8, 24))

        main = tk.Frame(shell, bg=BG)
        main.pack(side="left", fill="both", expand=True, padx=28, pady=24)

        header = tk.Frame(main, bg=BG)
        header.pack(fill="x", pady=(0, 20))
        header_left = tk.Frame(header, bg=BG)
        header_left.pack(side="left")
        self._label(header_left, "OWNER WORKSPACE", color=AMBER, size=9, weight="bold").pack(anchor="w")
        self._label(header_left, "The Labyrinth", size=28, weight="bold").pack(anchor="w")
        self._button(header, "Refresh", self.refresh).pack(side="right", pady=8)

        command = tk.Frame(main, bg=SURFACE, highlightbackground="#3b3527", highlightthickness=1)
        command.pack(fill="x")
        command_head = tk.Frame(command, bg=SURFACE)
        command_head.pack(fill="x", padx=20, pady=(17, 8))
        self._label(command_head, "WHAT SHOULD SHEPARD COORDINATE?", color=AMBER, size=9, weight="bold").pack(side="left")
        self.goal_text = tk.Text(command, height=4, wrap="word", bg="#0b0e17", fg=TEXT,
                                 insertbackground=AMBER, relief="flat", padx=14, pady=12,
                                 font=("Helvetica", 13), undo=True)
        self.goal_text.pack(fill="x", padx=20, pady=(0, 10))
        self.goal_text.bind("<Command-Return>", lambda _event: self.dispatch_goal())
        self.goal_text.bind("<Control-Return>", lambda _event: self.dispatch_goal())
        action_row = tk.Frame(command, bg=SURFACE)
        action_row.pack(fill="x", padx=20, pady=(0, 17))
        self._label(action_row, "⌘ Enter to dispatch", color=MUTED, size=9).pack(side="left")
        self.run_button = self._button(action_row, "Dispatch goal  ↗", self.dispatch_goal, primary=True)
        self.run_button.pack(side="right")

        content = tk.PanedWindow(main, orient="horizontal", bg=BG, sashwidth=8, bd=0,
                                 sashrelief="flat", opaqueresize=True)
        content.pack(fill="both", expand=True, pady=(20, 0))

        jobs_frame = tk.Frame(content, bg=SURFACE, highlightbackground=LINE, highlightthickness=1)
        detail_frame = tk.Frame(content, bg=SURFACE, highlightbackground=LINE, highlightthickness=1)
        content.add(jobs_frame, minsize=340, width=420)
        content.add(detail_frame, minsize=430)

        jobs_head = tk.Frame(jobs_frame, bg=SURFACE)
        jobs_head.pack(fill="x", padx=16, pady=15)
        self._label(jobs_head, "RECENT JOBS", size=12, weight="bold").pack(side="left")
        self.jobs_tree = ttk.Treeview(jobs_frame, columns=("status", "goal"), show="headings")
        self.jobs_tree.heading("status", text="STATUS")
        self.jobs_tree.heading("goal", text="GOAL")
        self.jobs_tree.column("status", width=110, stretch=False)
        self.jobs_tree.column("goal", width=300)
        self.jobs_tree.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        self.jobs_tree.bind("<<TreeviewSelect>>", self.select_job)

        detail_head = tk.Frame(detail_frame, bg=SURFACE)
        detail_head.pack(fill="x", padx=18, pady=15)
        self._label(detail_head, "LIVE TRACE", size=12, weight="bold").pack(side="left")
        self.detail_text = tk.Text(detail_frame, wrap="word", state="disabled", bg="#0b0e17", fg=TEXT,
                                   relief="flat", padx=18, pady=16, spacing1=3, spacing3=8,
                                   font=("Menlo", 11), insertbackground=AMBER)
        self.detail_text.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        self.detail_text.tag_configure("title", foreground=AMBER, font=("Helvetica", 14, "bold"))
        self.detail_text.tag_configure("muted", foreground=MUTED)
        self.detail_text.tag_configure("error", foreground=RED)

    def refresh(self) -> None:
        self.settings = load_settings(self.config_path)
        profiles = [self.settings.shepard, *self.settings.sheep]
        selected_agent = self.agent_list.curselection()
        self.agent_list.delete(0, "end")
        for profile in profiles:
            self.agent_list.insert("end", f"  {profile.name}\n    {profile.model}")
        if selected_agent and selected_agent[0] < len(profiles):
            self.agent_list.selection_set(selected_agent[0])

        current_selection = self.selected_job_id
        for row in self.jobs_tree.get_children():
            self.jobs_tree.delete(row)
        for job in self.db.list_jobs(50):
            self.jobs_tree.insert("", "end", iid=job["id"], values=(job["status"].replace("_", " "), job["goal"]))
        if current_selection and self.jobs_tree.exists(current_selection):
            self.jobs_tree.selection_set(current_selection)
            self._show_job(current_selection)
        self.root.after(3000, self.refresh)

    def select_job(self, _event=None) -> None:
        selected = self.jobs_tree.selection()
        if selected:
            self.selected_job_id = selected[0]
            self._show_job(selected[0])

    def _show_job(self, job_id: str) -> None:
        job = self.db.get_job(job_id)
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("end", f"{job['status'].upper().replace('_', ' ')}\n", "title")
        self.detail_text.insert("end", f"{job['goal']}\n\n")
        if job.get("plan_summary"):
            self.detail_text.insert("end", f"Plan: {job['plan_summary']}\n\n", "muted")
        for task in job["tasks"]:
            self.detail_text.insert("end", f"{task['position']:02d}  {task['sheep_id'].upper()} · {task['status']}\n", "muted")
            self.detail_text.insert("end", f"{task['title']}\n")
            if task.get("result"):
                result = task["result"]
                preview = result if len(result) <= 900 else result[:900] + "…"
                self.detail_text.insert("end", f"{preview}\n\n")
            else:
                self.detail_text.insert("end", f"{task['instructions']}\n\n")
        if job.get("final_output"):
            self.detail_text.insert("end", "SHEPARD'S RESULT\n", "title")
            self.detail_text.insert("end", job["final_output"])
        if job.get("error"):
            self.detail_text.insert("end", f"\nERROR\n{job['error']}", "error")
        self.detail_text.configure(state="disabled")

    def dispatch_goal(self) -> None:
        goal = self.goal_text.get("1.0", "end").strip()
        if not goal:
            messagebox.showinfo("Shepard", "Give Shepard a goal first.")
            return
        job_id = self.db.create_job(goal)
        self.selected_job_id = job_id
        self.goal_text.delete("1.0", "end")
        self.run_button.configure(state="disabled", text="Working…")
        self.status_label.configure(text="●  Goal in the Labyrinth", fg=AMBER)

        def worker() -> None:
            try:
                with self.runtime_lock:
                    settings = load_settings(self.config_path)
                    ShepardRuntime(settings, labyrinth=self.db).run(goal, job_id=job_id)
            finally:
                self.root.after(0, self._run_finished)

        threading.Thread(target=worker, name=f"desktop-{job_id}", daemon=True).start()
        self.refresh()

    def _run_finished(self) -> None:
        self.run_button.configure(state="normal", text="Dispatch goal  ↗")
        self.status_label.configure(text="●  Shepard ready", fg="#62d394")
        self.refresh()

    def edit_selected_agent(self, _event=None) -> None:
        selected = self.agent_list.curselection()
        if not selected:
            return
        profiles = [self.settings.shepard, *self.settings.sheep]
        profile = profiles[selected[0]]
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Customize {profile.name}")
        dialog.geometry("500x410")
        dialog.configure(bg=SURFACE)
        dialog.transient(self.root)
        dialog.grab_set()
        body = tk.Frame(dialog, bg=SURFACE)
        body.pack(fill="both", expand=True, padx=24, pady=22)
        self._label(body, "CHARACTER PROFILE", color=AMBER, size=9, weight="bold").pack(anchor="w")
        self._label(body, f"Customize {profile.name}", size=19, weight="bold").pack(anchor="w", pady=(2, 18))

        fields = {}
        for label, value, height in (("Name", profile.name, 1), ("Model", profile.model, 1), ("Character", profile.persona, 5)):
            self._label(body, label, color=MUTED, size=9).pack(anchor="w", pady=(8, 4))
            if height == 1:
                widget = tk.Entry(body, bg="#0b0e17", fg=TEXT, insertbackground=AMBER, relief="flat", font=("Helvetica", 12))
                widget.insert(0, value)
            else:
                widget = tk.Text(body, height=height, wrap="word", bg="#0b0e17", fg=TEXT,
                                 insertbackground=AMBER, relief="flat", font=("Helvetica", 12))
                widget.insert("1.0", value)
            widget.pack(fill="x", ipady=6)
            fields[label] = widget

        def save() -> None:
            update_persona(
                self.config_path, profile.id,
                name=fields["Name"].get().strip(),
                model=fields["Model"].get().strip(),
                persona=fields["Character"].get("1.0", "end").strip(),
            )
            dialog.destroy()
            self.refresh()

        self._button(body, "Save character", save, primary=True).pack(anchor="e", pady=(18, 0))

    def open_web(self) -> None:
        if self.web_server is None:
            try:
                self.web_server = create_server("127.0.0.1", 8765, self.config_path)
                threading.Thread(target=self.web_server.serve_forever, daemon=True, name="shepard-web").start()
            except OSError:
                self.web_server = False
        webbrowser.open("http://127.0.0.1:8765")

    def close(self) -> None:
        if self.web_server:
            self.web_server.shutdown()
            self.web_server.server_close()
        self.root.destroy()


def launch(config_path: str | Path | None = None) -> None:
    root = tk.Tk()
    ShepardDesktop(root, config_path)
    root.mainloop()
