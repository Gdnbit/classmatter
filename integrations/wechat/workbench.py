"""Separate native connector workbench; does not enable Capture inside frozen R1."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import queue
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import uuid

from .cli import ROOT, isolated
from .model import ConnectorError, Message, Page, PRESETS, Scope
from .runtime import approval, capture, desktop_lock, read_json, restart_capture, submit


class Workbench:
    def __init__(self, window: tk.Tk, runtime_root: Path | None = None):
        self.window = window
        self.root = runtime_root or ROOT / ".local-runtime" / "wechat"
        self.results = queue.Queue()
        self.busy = False
        self.prepared = None
        window.title("ClassMatter · 个人微信连接器实验工作台")
        window.geometry("1050x760")
        self.values = {}
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="个人微信连接器 · 独立实验，不写正式业务库", font=("Segoe UI", 15)).pack(anchor="w")
        ttk.Label(frame, text="默认合成模式。历史仅限可访问的本机记录；无完整云端历史承诺。所有连接器实机验收仍待完成。").pack(anchor="w", pady=8)
        fields = ttk.Frame(frame)
        fields.pack(fill="x")
        specs = [("provider", "连接方案", "usechat"), ("account", "本机账号/目录标识", "synthetic-account"),
                 ("chat", "对话精确名称；replica 填原生会话 ID", "synthetic-chat"),
                 ("python", "隔离 Python 可执行文件", sys.executable),
                 ("command", "UseChat 命令数组 JSON（node.exe 与 CLI 脚本绝对路径）", "[]"),
                 ("limit", "本轮历史条数上限（replica 可续读，最高 100000）", "1000")]
        for row, (key, title, default) in enumerate(specs):
            ttk.Label(fields, text=title).grid(row=row, column=0, sticky="w", pady=3)
            value = tk.StringVar(value=default)
            self.values[key] = value
            widget = ttk.Combobox(fields, textvariable=value, values=list(PRESETS), state="readonly") if key == "provider" else ttk.Entry(fields, textvariable=value)
            widget.grid(row=row, column=1, sticky="ew", padx=10)
        fields.columnconfigure(1, weight=1)
        self.live = tk.BooleanVar(value=False)
        self.model = tk.BooleanVar(value=False)
        self.restart = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="使用本人已登录的真实微信（不会自动安装依赖）", variable=self.live).pack(anchor="w", pady=4)
        ttk.Checkbutton(frame, text="允许本次 UseChat 向已配置视觉模型发送截图并产生模型费用", variable=self.model).pack(anchor="w")
        ttk.Checkbutton(frame, text="重新扫描：保留旧候选存档，从最新消息开始（来源变化后使用）", variable=self.restart).pack(anchor="w")
        provider_actions = ttk.Frame(frame)
        provider_actions.pack(fill="x", pady=4)
        ttk.Button(provider_actions, text="配置智谱 Key / 免费型号", command=self.provider_config).pack(side="left")
        ttk.Button(provider_actions, text="免费视觉自测（合成图）", command=self.provider_eval).pack(side="left", padx=8)
        self.status = tk.StringVar(value="合成模式待命；连接器未接入正式 R1 数据和 Agent 工具。")
        ttk.Label(frame, textvariable=self.status, wraplength=980).pack(anchor="w", pady=8)
        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        ttk.Button(actions, text="读取 / 继续补读历史", command=self.start_capture).pack(side="left")
        ttk.Button(actions, text="选择本地库会话", command=self.list_chats).pack(side="left", padx=8)
        ttk.Label(actions, text="UIA 需控件树可用；视觉方案仅当前窗口；replica 读取本地数据库。", wraplength=650).pack(side="left", padx=12)
        self.output = tk.Text(frame, height=15, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True, pady=8)
        scrollbar = ttk.Scrollbar(self.output, command=self.output.yview)
        scrollbar.pack(side="right", fill="y")
        self.output.configure(yscrollcommand=scrollbar.set)
        ttk.Label(frame, text="单条回复草稿（不自动生成、不自动发送；本轮仅文本）：").pack(anchor="w")
        self.text = tk.Text(frame, height=3, wrap="word")
        self.text.pack(fill="x", pady=4)
        send_actions = ttk.Frame(frame)
        send_actions.pack(fill="x")
        ttk.Button(send_actions, text="预览目标与正文", command=self.prepare).pack(side="left")
        ttk.Button(send_actions, text="确认单次发送", command=self.start_send).pack(side="left", padx=10)
        ttk.Label(send_actions, text="发送后仍需人工核对；不确定不重试。replica 发送禁用。").pack(side="left")
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.after(100, self.poll)

    def config(self):
        scope = Scope(self.values["provider"].get(), self.values["account"].get(), self.values["chat"].get())
        live = self.live.get()
        if live and scope.account == "synthetic-account":
            raise ConnectorError("explicit_account_required")
        if live and scope.provider == "usechat" and not self.model.get():
            raise ConnectorError("model_authorization_required")
        command = json.loads(self.values["command"].get())
        if not isinstance(command, list) or not all(isinstance(c, str) for c in command):
            raise ConnectorError("invalid_command")
        limit = int(self.values["limit"].get())
        if not 1 <= limit <= 100_000:
            raise ConnectorError("invalid_limit")
        return scope, live, self.values["python"].get(), command, limit

    def display(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("end", text)
        self.output.configure(state="disabled")

    def provider_config(self):
        if self.busy:
            return
        python = ROOT / "backend" / ".venv" / "Scripts" / "pythonw.exe"
        if os.name != "nt" or not python.is_file():
            self.status.set("本机加密配置入口需要已安装的 Windows 后端 Python 环境。")
            return
        subprocess.Popen([str(python), "-m", "integrations.wechat.provider_profile"], cwd=ROOT,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.status.set("已打开独立的密钥配置窗口；密钥不进入工作台输出或命令参数。")

    def provider_eval(self):
        if self.busy:
            return
        python = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
        fixtures = ROOT / ".local-runtime" / "vision-fixtures"
        if not python.is_file() or not (fixtures / "manifest.json").is_file():
            self.status.set("需先准备后端环境和合成图；参见连接器 README 的免费视觉自测步骤。")
            return
        if not messagebox.askokcancel("免费视觉自测", "将调用本机配置的官方免费型号，发送8张程序生成的合成图。\n不读取微信、不发送真实资料；遇到服务不可用会熔断。是否继续？", parent=self.window):
            return
        report_path = ROOT / "test-results" / ("vision-workbench-" + uuid.uuid4().hex + ".json")
        def operation():
            process = subprocess.run([str(python), "-m", "integrations.wechat.vision_eval", "run",
                                      "--live", "--local-profile", "--fixtures", str(fixtures),
                                      "--output", str(report_path)], cwd=ROOT, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=360,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if process.returncode not in (0, 2) or not report_path.is_file():
                raise ConnectorError("provider_eval_failed_check_local_profile")
            value = read_json(report_path)
            if value.get("kind") != "classmatter.synthetic-vision-evidence.v1" or "summary" not in value:
                raise ConnectorError("provider_eval_incomplete")
            return json.dumps({"summary": value["summary"], "requests": value["requests"],
                               "formal_gate": False, "real_wechat_tested": False,
                               "report": str(report_path)}, ensure_ascii=False, indent=2)
        self.run(operation)

    def list_chats(self):
        if self.busy:
            return
        try:
            scope, live, python, command, _ = self.config()
            if scope.provider != "replica":
                raise ConnectorError("仅本地库方案支持此列表；其他方案填写微信精确名称")
            if live and not messagebox.askokcancel("会话列表读取", "将读取所选本机账号的会话及联系人名称，不读取正文。是否继续？", parent=self.window):
                return
            def operation():
                result = isolated(python, {"live": True, "scope": asdict(scope), "command": command,
                                           "action": "list-chats"}, 300) if live else {
                    "conversations": [{"id": "synthetic-chat", "title": "合成班级群"}]}
                return {"choose_conversation": result["conversations"], "scope": asdict(scope), "live": live}
            self.run(operation)
        except Exception as exc:
            self.status.set(str(exc) if isinstance(exc, ConnectorError) else "配置无效")

    def run(self, operation):
        if self.busy:
            return
        self.busy = True
        self.status.set("执行中；请勿切换微信窗口。超时或关闭不会自动重发。")
        def execute():
            try:
                with desktop_lock():
                    result = operation()
                self.results.put((True, result))
            except Exception as exc:
                self.results.put((False, str(exc) if isinstance(exc, ConnectorError) else "connector_failed"))
        threading.Thread(target=execute, daemon=False).start()

    def start_capture(self):
        if self.busy:
            return
        try:
            scope, live, python, command, limit = self.config()
            restart = self.restart.get()
            if live and not messagebox.askokcancel("读取确认", "将读取所选真实微信对话，候选保存在本机忽略目录。\n账号标识不等于自动验证登录身份，请先核对微信账号和目标。\n视觉模型选项开启时会传输截图并可能计费。是否继续？", parent=self.window):
                return
            def operation():
                root = self.root / ("live" if live else "synthetic")
                if restart:
                    restart_capture(root, scope)
                if live:
                    result = isolated(python, {"live": True, "scope": asdict(scope), "command": command,
                                               "action": "capture", "root": str(root), "page_size": 100,
                                               "max_messages": limit}, 300)
                    stored = read_json(root / (scope.key + ".candidate.json"))
                    result["displayed_messages"] = stored["messages"][:100]
                    result["display_limit"] = 100
                    return json.dumps({"mode": "live-candidate", **result}, ensure_ascii=False, indent=2)
                def read(size, offset):
                    if not live:
                        rows = tuple(Message(f"fixture:{i}", "合成发送者", f"合成消息 {i}", None,
                                             "text", "local-db-row") for i in range(7, 0, -1))
                        return Page(rows[offset:offset+size], PRESETS[scope.provider]["history"],
                                    offset+size > len(rows) if scope.provider == "replica" else None)
                    value = isolated(python, {"live": True, "scope": asdict(scope), "command": command,
                                              "action": "read", "limit": size, "offset": offset}, 90)
                    return Page(tuple(Message(**m) for m in value["messages"]), value["coverage"], value["exhausted"])
                result = capture(root, scope, read, max_messages=limit)
                return json.dumps({"mode": "live-candidate" if live else "synthetic", **result}, ensure_ascii=False, indent=2)
            self.run(operation)
        except Exception as exc:
            self.status.set(str(exc) if isinstance(exc, ConnectorError) else "配置无效")

    def prepare(self):
        if self.busy:
            return
        try:
            scope, live, python, command, _ = self.config()
            text = self.text.get("1.0", "end-1c")
            request = str(uuid.uuid4())
            token = approval(scope, text, request)
            self.prepared = (scope, live, python, command, text, request, token)
            self.display(json.dumps({"mode": "live" if live else "synthetic", "scope": asdict(scope),
                                     "text": text, "request": request, "status": "仅预览"}, ensure_ascii=False, indent=2))
            self.status.set("请核对账号、接收人和完整正文。修改任一配置后需要重新预览。")
        except Exception:
            self.prepared = None
            self.status.set("无法预览：请检查配置及非空正文（不超过 2000 字）。")

    def start_send(self):
        if self.busy or self.prepared is None:
            return
        try:
            scope, live, python, command, text, request, token = self.prepared
            now_scope, now_live, now_python, now_command, _ = self.config()
            if (now_scope, now_live, now_python, now_command, self.text.get("1.0", "end-1c")) != (scope, live, python, command, text):
                raise ConnectorError("approval_mismatch")
            if not PRESETS[scope.provider]["send"]:
                raise ConnectorError("send_not_supported")
            if not messagebox.askokcancel("单次发送确认", f"模式：{'真实微信' if live else '合成模拟'}\n目标：{scope.chat}\n\n{text}\n\n本次仅提交一次；不代表已确认送达。", parent=self.window):
                return
            self.prepared = None
            def operation():
                def send(content):
                    if not live:
                        return "submitted-unconfirmed"
                    return isolated(python, {"live": True, "scope": asdict(scope), "command": command,
                                             "action": "send", "text": content,
                                             "root": str(self.root / "live"), "request_id": request}, 90)["status"]
                result = submit(self.root / ("live" if live else "synthetic"), scope, text, request, token, send)
                return json.dumps({"mode": "live" if live else "synthetic", **result}, ensure_ascii=False, indent=2)
            self.run(operation)
        except Exception as exc:
            self.status.set(str(exc) if isinstance(exc, ConnectorError) else "配置无效")

    def poll(self):
        try:
            ok, result = self.results.get_nowait()
            self.busy = False
            self.status.set("操作结束；请查看覆盖范围及不确定状态。" if ok else f"已停止：{result}；未自动重试。")
            if ok and isinstance(result, dict) and "choose_conversation" in result:
                popup = tk.Toplevel(self.window)
                popup.title("选择会话 · 不代表已验证接收人身份")
                choices = tk.Listbox(popup, width=85, height=18)
                choices.pack(fill="both", expand=True)
                for conversation in result["choose_conversation"]:
                    choices.insert("end", f"{conversation['title']} · {conversation['id']}")
                def choose():
                    selection = choices.curselection()
                    if not selection:
                        return
                    if (self.live.get() != result["live"] or self.values["account"].get() != result["scope"]["account"]
                            or self.values["provider"].get() != result["scope"]["provider"]):
                        self.status.set("账号/模式已变，请重新读取会话列表。")
                    else:
                        self.values["chat"].set(result["choose_conversation"][selection[0]]["id"])
                        self.prepared = None
                    popup.destroy()
                ttk.Button(popup, text="选用该会话", command=choose).pack(pady=8)
            else:
                self.display(result)
        except queue.Empty:
            pass
        self.window.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo("操作仍在运行", "请等待当前读取或发送结束；超时会停止。不能通过关闭窗口假定操作已取消。", parent=self.window)
            return
        self.window.destroy()


def main():
    window = tk.Tk()
    if "--smoke" in sys.argv:
        window.withdraw()
        with tempfile.TemporaryDirectory() as directory:
            workbench = Workbench(window, Path(directory))
            workbench.values["provider"].set("replica")
            workbench.start_capture()
            passed = []
            def finish():
                if workbench.busy:
                    window.after(50, finish)
                else:
                    output = workbench.output.get("1.0", "end")
                    passed.append('"mode": "synthetic"' in output and '"source-exhausted"' in output)
                    window.destroy()
            window.after(100, finish)
            window.after(10000, window.destroy)
            window.mainloop()
            if passed != [True]:
                raise SystemExit("Native synthetic workbench smoke failed or timed out")
        print("Synthetic native workbench smoke passed; no WeChat or model access")
    else:
        Workbench(window)
        window.mainloop()


if __name__ == "__main__":
    main()
