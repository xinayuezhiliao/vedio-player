"""
VIP视频解析工具 - 基于 urllib（无外部依赖）
支持：Chrome App 小窗口播放 + 多平台搜索
"""
import tkinter
import tkinter.messagebox
import tkinter.ttk
import subprocess
import sys
import datetime
import json
import os
import re
import ssl
import threading
import urllib.request
import urllib.parse
from urllib.parse import urlparse, unquote, parse_qs

# 全局 SSL（忽略证书验证）
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def fetch(url, headers=None, timeout=8):
    """用内置 urllib 替代 requests.get"""
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout) as r:
        ct = r.headers.get("Content-Type", "")
        enc = "utf-8"
        for p in ct.split(";"):
            if "charset" in p:
                enc = p.split("charset=")[-1].strip()
                break
        return r.read().decode(enc, errors="ignore")


def get_app_data_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_PATH = get_app_data_path()
HISTORY_FILE = os.path.join(BASE_PATH, "video_parse_history.json")
FAVORITE_FILE = os.path.join(BASE_PATH, "video_favorite.json")

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
WINDOW_W, WINDOW_H = 960, 620


def get_chrome_env():
    env = os.environ.copy()
    env["PATH"] = r"C:\Program Files\Google\Chrome\Application;" + env.get("PATH", "")
    return env


def open_in_chrome_app(url):
    """以 Chrome App 模式（无地址栏小窗口）打开 URL"""
    try:
        subprocess.Popen(
            [CHROME_PATH,
             f"--app={url}",
             f"--window-size={WINDOW_W},{WINDOW_H}",
             "--no-scrollbar",
             "--disable-web-security"],
            env=get_chrome_env(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except FileNotFoundError:
        import webbrowser
        webbrowser.open(url)


# ---- 多平台搜索 ----

def search_iqiyi(keyword):
    results = []
    try:
        url = "https://so.iqiyi.com/so?q=" + urllib.parse.quote(keyword)
        text = fetch(url, headers={"Referer": "https://www.iqiyi.com"}, timeout=8)
        for m in re.finditer(r'href="(https://www\.iqiyi\.com/v_[^"]+)"', text):
            results.append((keyword, m.group(1)))
        seen = list(dict.fromkeys(results))[:5]
    except Exception:
        seen = []
    return seen


def search_tencent(keyword):
    results = []
    try:
        url = "https://v.qq.com/x/search/?q=" + urllib.parse.quote(keyword) + "&c=news"
        text = fetch(url, headers={"Referer": "https://v.qq.com"}, timeout=8)
        for m in re.finditer(r'href="(/cover/[^?"]+)"[^>]*>([^<]{5,60})<', text):
            title = m.group(2).strip()
            if title:
                results.append((title, "https://v.qq.com" + m.group(1)))
        seen = list(dict.fromkeys(results))[:5]
    except Exception:
        seen = []
    return seen


def search_youku(keyword):
    results = []
    try:
        url = "https://so.youku.com/search/video?q=" + urllib.parse.quote(keyword)
        text = fetch(url, headers={"Referer": "https://www.youku.com"}, timeout=8)
        for m in re.finditer(r'href="(https://v\.youku\.com/v_show/id_[^"]+)"[^>]*>([^<]{5,50})<', text):
            title = m.group(2).strip()
            if title:
                results.append((title, m.group(1)))
        seen = list(dict.fromkeys(results))[:5]
    except Exception:
        seen = []
    return seen


def search_mango(keyword):
    results = []
    try:
        url = "https://so.mgtv.com/list?k=" + urllib.parse.quote(keyword)
        text = fetch(url, headers={"Referer": "https://www.mgtv.com"}, timeout=8)
        for m in re.finditer(r'href="(https://www\.mgtv\.com/b/[^?"]+)"[^>]*>([^<]{5,50})<', text):
            title = m.group(2).strip()
            if title:
                results.append((title, m.group(1)))
        seen = list(dict.fromkeys(results))[:5]
    except Exception:
        seen = []
    return seen


def search_all_platforms(keyword):
    all_results = []
    def worker(platform, func):
        for title, url in func(keyword):
            all_results.append((platform, title, url))
    threads = [
        threading.Thread(target=worker, args=("爱奇艺", search_iqiyi)),
        threading.Thread(target=worker, args=("腾讯视频", search_tencent)),
        threading.Thread(target=worker, args=("优酷", search_youku)),
        threading.Thread(target=worker, args=("芒果TV", search_mango)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=12)
    return all_results


# ---- 主程序 ----

class VIPVideoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VIP视频解析工具")
        self.center_window(1000, 640)
        self.root.resizable(True, True)
        self.root.configure(bg="#f0f2f2")
        self.setup_style()
        self.parse_apis = {
            "默认接口": "https://www.ckplayer.vip/jiexi/?url=",
            "备用接口1": "https://jx.xmflv.com/?url=",
            "备用接口2": "https://jiexi.071811.cc/jx.php?url=",
        }
        self.history_records = self.load_history()
        self.favorite_records = self.load_favorite()
        self.update_untagged_history_titles()
        self.search_results = []
        self.create_widgets()

    def center_window(self, width, height):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{width}x{height}+{(sw-width)//2}+{(sh-height)//2}")

    def setup_style(self):
        self.COLOR_BG = "#f0f2f2"
        self.COLOR_PRIMARY = "#1890ff"
        self.COLOR_SECONDARY = "#52c41a"
        self.COLOR_FAVORITE = "#faad14"
        self.COLOR_WARNING = "#ff4d4f"
        self.COLOR_TEXT = "#333333"
        self.COLOR_FRAME = "#e8e8e8"
        self.COLOR_HISTORY = "#f8f9fa"
        self.COLOR_LINK = "#1890ff"
        self.COLOR_DELETE = "#fa8c16"
        self.COLOR_SEARCH_BG = "#fffbe6"
        self.FONT_TITLE = ("Microsoft YaHei", 18, "bold")
        self.FONT_NORMAL = ("Microsoft YaHei", 12)
        self.FONT_SMALL = ("Microsoft YaHei", 11)
        self.FONT_BUTTON = ("Microsoft YaHei", 14, "bold")
        self.FONT_SMALL_BUTTON = ("Microsoft YaHei", 12, "bold")

    def load_history(self):
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    records = json.load(f)
                    for record in records:
                        record.setdefault("is_manual", False)
                        if "title" not in record:
                            record["title"] = f"待更新_{record.get('url', '?')[:10]}..."
                    return records
        except Exception:
            pass
        return []

    def load_favorite(self):
        try:
            if os.path.exists(FAVORITE_FILE):
                with open(FAVORITE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def save_favorite(self):
        try:
            with open(FAVORITE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.favorite_records, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def update_untagged_history_titles(self):
        if not self.history_records:
            return
        for record in self.history_records:
            url = record.get("url", "")
            if (not record.get("is_manual", False) and record.get("title", "").startswith("待更新_") and url):
                record["title"] = self.extract_video_title(url)
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history_records, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def extract_video_title(self, url):
        url = url.strip()
        title = ""
        if "v.qq.com" in url:
            query = parse_qs(urlparse(url).query)
            if "title" in query:
                title = unquote(query["title"][0])
        elif "iqiyi.com" in url or "youku.com" in url:
            try:
                text = fetch(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
                m = re.search(r'<meta property="og:title" content="([^"]+)"', text)
                if m:
                    title = m.group(1)
            except Exception:
                pass
        if not title:
            cn = re.findall(r"[\u4e00-\u9fa5]{2,}", url)
            title = max(cn, key=len) if cn else f"视频_{url[-10:]}"
        return re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", "", title).strip()[:30] or "未知视频"

    def save_history(self, url, api_name, custom_title=""):
        is_manual = bool(custom_title.strip())
        video_title = custom_title.strip() or self.extract_video_title(url)
        record = {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "url": url,
            "api": api_name,
            "title": video_title,
            "is_manual": is_manual,
        }
        self.history_records.insert(0, record)
        if len(self.history_records) > 50:
            self.history_records = self.history_records[:50]
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history_records, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---- 搜索 ----

    def on_search_key(self, e):
        if e.keysym == "Return":
            self.do_search()

    def do_search(self):
        keyword = self.entry_search.get().strip()
        if not keyword:
            tkinter.messagebox.showwarning("提示", "请输入要搜索的电影或剧集名称")
            return
        self.search_var.set("正在搜索爱奇艺 / 腾讯 / 优酷 / 芒果TV ...")
        self.search_listbox.delete(0, tkinter.END)
        self.root.update()

        results = search_all_platforms(keyword)

        self.search_listbox.delete(0, tkinter.END)
        if not results:
            self.search_var.set("未找到结果，换个关键词试试")
            return

        self.search_results = results
        icons = {"爱奇艺": "🎬", "腾讯视频": "📺", "优酷": "🎞", "芒果TV": "🥭"}
        for platform, title, _ in results:
            self.search_listbox.insert(tkinter.END, f"{icons.get(platform,'▶')} [{platform}] {title}")
        self.search_var.set(f"找到 {len(results)} 条结果，双击或点播放")

    def play_selected_search(self):
        if not self.search_listbox.curselection():
            tkinter.messagebox.showwarning("提示", "请先选中要播放的影片")
            return
        idx = self.search_listbox.curselection()[0]
        platform, title, url = self.search_results[idx]
        api_name = self.api_var.get()
        api = self.parse_apis[api_name]
        self.save_history(url, api_name, title)
        self.update_history_listbox()
        open_in_chrome_app(api + url)
        tkinter.messagebox.showinfo("播放", f"正在 Chrome 播放：{title}\n来源：{platform}")

    # ---- 收藏 ----

    def add_to_favorite(self):
        target_url = self.entry_url.get().strip()
        if not target_url:
            tkinter.messagebox.showwarning("提示", "请输入视频网址！")
            return
        custom = self.entry_title.get().strip()
        if custom == "（可选，留空则自动识别）":
            custom = ""
        video_title = custom.strip() or self.extract_video_title(target_url)
        for f in self.favorite_records:
            if f.get("url") == target_url:
                tkinter.messagebox.showinfo("提示", "已收藏过该影片")
                return
        self.favorite_records.insert(0, {
            "title": video_title,
            "url": target_url,
            "api": self.api_var.get(),
            "add_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.save_favorite()
        tkinter.messagebox.showinfo("成功", f"已收藏：{video_title}")

    def open_favorite_window(self):
        w = tkinter.Toplevel(self.root)
        w.title("我的收藏")
        w.geometry("800x500")
        w.configure(bg=self.COLOR_BG)

        tkinter.Frame(w, bg=self.COLOR_FAVORITE, height=50).pack(fill="x")
        tkinter.Label(w, text="我的影片收藏", font=("Microsoft YaHei", 16, "bold"),
                      fg="white", bg=self.COLOR_FAVORITE).place(relx=0.5, rely=0.5, anchor="center")

        main = tkinter.Frame(w, bg=self.COLOR_BG)
        main.pack(fill="both", expand=True, padx=15, pady=15)

        canvas = tkinter.Canvas(main, bg="white", bd=0, highlightthickness=0)
        scrollbar = tkinter.ttk.Scrollbar(main, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        frame = tkinter.Frame(canvas, bg="white")
        canvas.create_window((0, 0), window=frame, anchor="nw")

        fav_listbox = tkinter.Listbox(frame, font=self.FONT_NORMAL, fg=self.COLOR_LINK, bg="white",
                                      selectbackground="#e6f7ff", selectforeground=self.COLOR_LINK,
                                      justify="left", width=80, height=18, bd=0)
        fav_listbox.pack(fill="both", expand=True, padx=5, pady=5)

        for idx, item in enumerate(self.favorite_records):
            fav_listbox.insert(tkinter.END, f"{idx+1}. {item.get('title','未知')}")
            fav_listbox.insert(tkinter.END, f"    {item.get('add_time','')} | {item.get('api','')}")
            fav_listbox.insert(tkinter.END, "")

        def on_config(_):
            canvas.configure(scrollregion=canvas.bbox("all"))
        frame.bind("<Configure>", on_config)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta//120), "units"))

        btn_frame = tkinter.Frame(w, bg=self.COLOR_BG)
        btn_frame.pack(fill="x", pady=10)

        def play_fav():
            if not fav_listbox.curselection():
                tkinter.messagebox.showwarning("提示", "请先选中要播放的影片")
                return
            idx = fav_listbox.curselection()[0] // 3
            item = self.favorite_records[idx]
            api = self.parse_apis.get(item.get("api", "默认接口"), self.parse_apis["默认接口"])
            open_in_chrome_app(api + item["url"])
            tkinter.messagebox.showinfo("播放", f"正在 Chrome 播放：{item['title']}")

        def del_fav():
            if not fav_listbox.curselection():
                return
            idx = fav_listbox.curselection()[0] // 3
            if tkinter.messagebox.askyesno("确认", "删除该收藏？"):
                self.favorite_records.pop(idx)
                self.save_favorite()
                w.destroy()
                self.open_favorite_window()

        def clear_fav():
            if tkinter.messagebox.askyesno("确认", "确定清空所有收藏？"):
                self.favorite_records = []
                self.save_favorite()
                w.destroy()
                self.open_favorite_window()

        for text, cmd, color in [("播放选中影片", play_fav, self.COLOR_SECONDARY),
                                  ("删除选中", del_fav, self.COLOR_DELETE),
                                  ("清空收藏", clear_fav, self.COLOR_WARNING)]:
            b = tkinter.Button(btn_frame, text=text, command=cmd, bg=color, fg="white",
                               font=self.FONT_SMALL_BUTTON, relief="flat", width=12)
            b.pack(side="left", padx=8)

    # ---- 历史记录 ----

    def play_selected_history(self):
        if not self.history_listbox.curselection():
            tkinter.messagebox.showwarning("提示", "请先选中要播放的历史记录")
            return
        idx = self.history_listbox.curselection()[0]
        if idx >= len(self.history_records):
            return
        r = self.history_records[idx]
        api = self.parse_apis.get(r["api"], self.parse_apis["默认接口"])
        open_in_chrome_app(api + r["url"])
        tkinter.messagebox.showinfo("播放", f"正在 Chrome 播放：{r['title']}")

    def delete_selected_history(self):
        if not self.history_listbox.curselection():
            return
        if tkinter.messagebox.askyesno("确认", "删除该记录？"):
            self.history_records.pop(self.history_listbox.curselection()[0])
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history_records, f, ensure_ascii=False, indent=2)
            self.update_history_listbox()

    def clear_all_history(self):
        if tkinter.messagebox.askyesno("确认", "清空所有历史？"):
            self.history_records = []
            self.update_history_listbox()
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)

    def _on_title_focus_in(self, e):
        if self.entry_title.get() == "（可选，留空则自动识别）":
            self.entry_title.delete(0, tkinter.END)
            self.entry_title.config(fg=self.COLOR_TEXT)

    def _on_title_focus_out(self, e):
        if not self.entry_title.get().strip():
            self.entry_title.insert(0, "（可选，留空则自动识别）")
            self.entry_title.config(fg="#999")

    def add_hover(self, widget, c1, c2):
        widget.bind("<Enter>", lambda e: widget.config(bg=c2))
        widget.bind("<Leave>", lambda e: widget.config(bg=c1))

    def play_video(self):
        url = self.entry_url.get().strip()
        if not url:
            tkinter.messagebox.showwarning("提示", "请输入网址")
            return
        title = self.entry_title.get().strip()
        if title == "（可选，留空则自动识别）":
            title = ""
        api_name = self.api_var.get()
        api = self.parse_apis[api_name]
        self.save_history(url, api_name, title)
        self.update_history_listbox()
        open_in_chrome_app(api + url)
        tkinter.messagebox.showinfo("播放", f"正在 Chrome 播放：{title or url}")

    def empty(self):
        self.entry_url.delete(0, tkinter.END)
        self.entry_title.delete(0, tkinter.END)
        self.entry_title.insert(0, "（可选，留空则自动识别）")
        self.entry_title.config(fg="#999")

    def create_widgets(self):
        # 顶部
        top = tkinter.Frame(self.root, bg=self.COLOR_PRIMARY, height=60)
        top.pack(fill="x")
        tkinter.Label(top, text="VIP视频解析工具", font=self.FONT_TITLE,
                      fg="white", bg=self.COLOR_PRIMARY).place(relx=0.5, rely=0.5, anchor="center")

        main = tkinter.Frame(self.root, bg=self.COLOR_BG)
        main.pack(fill="both", expand=True, padx=20, pady=12)

        # --- 左侧 ---
        left = tkinter.Frame(main, bg=self.COLOR_FRAME, bd=1, relief="solid")
        left.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=5)
        left.pack_propagate(False)
        left.configure(width=480, height=540)

        # 搜索区
        tkinter.Label(left, text="🔍 电影 / 剧集搜索", font=self.FONT_NORMAL,
                      bg=self.COLOR_FRAME, fg="#333").place(x=20, y=14, width=200, height=28)

        sf = tkinter.Frame(left, bg="#e8e8e8")
        sf.place(x=20, y=46, width=370, height=38)
        self.entry_search = tkinter.Entry(sf, font=("Microsoft YaHei", 13), bg="white", bd=0)
        self.entry_search.pack(side="left", fill="both", expand=True, padx=5, pady=4)
        self.entry_search.bind("<KeyPress>", self.on_search_key)
        btn_go = tkinter.Button(sf, text="搜索", command=self.do_search,
                                bg=self.COLOR_PRIMARY, fg="white",
                                font=self.FONT_SMALL_BUTTON, relief="flat", width=6)
        btn_go.pack(side="right", padx=4, pady=4)

        self.search_var = tkinter.StringVar(value="输入电影/剧名，支持双击直接播放")
        tkinter.Label(left, textvariable=self.search_var, font=self.FONT_SMALL,
                      fg="#888", bg=self.COLOR_FRAME, anchor="w") \
            .place(x=20, y=88, width=430, height=20)

        slf = tkinter.Frame(left)
        slf.place(x=20, y=112, width=440, height=190)
        sb_s = tkinter.Scrollbar(slf)
        sb_s.pack(side="right", fill="y")
        self.search_listbox = tkinter.Listbox(slf, font=self.FONT_SMALL,
                                              bg=self.COLOR_SEARCH_BG, fg="#8c5a00",
                                              selectbackground="#ffe58f", selectforeground="#8c5a00",
                                              yscrollcommand=sb_s.set, bd=0, highlightthickness=0)
        self.search_listbox.pack(side="left", fill="both", expand=True)
        sb_s.config(command=self.search_listbox.yview)
        self.search_listbox.bind("<Double-Button-1>", lambda _: self.play_selected_search())

        tkinter.Button(left, text="▶ 播放选中", command=self.play_selected_search,
                       bg=self.COLOR_SECONDARY, fg="white",
                       font=self.FONT_SMALL_BUTTON, relief="flat") \
            .place(x=20, y=308, width=130, height=36)
        tkinter.Button(left, text="＋ 收藏", command=self.add_to_favorite,
                       bg=self.COLOR_FAVORITE, fg="white",
                       font=self.FONT_SMALL_BUTTON, relief="flat") \
            .place(x=160, y=308, width=120, height=36)
        tkinter.Button(left, text="♥ 我的收藏", command=self.open_favorite_window,
                       bg="#722ed1", fg="white",
                       font=self.FONT_SMALL_BUTTON, relief="flat") \
            .place(x=290, y=308, width=130, height=36)

        # 分隔线
        tkinter.Frame(left, bg="#d9d9d9", height=1).place(x=20, y=352, width=430)

        # 手动输入
        tkinter.Label(left, text="目标网址：", font=self.FONT_NORMAL, bg=self.COLOR_FRAME) \
            .place(x=20, y=360, width=80, height=32)
        self.entry_url = tkinter.Entry(left, font=self.FONT_NORMAL, bg="white", bd=0)
        self.entry_url.place(x=105, y=360, width=290, height=32)
        btn_clear = tkinter.Button(left, text="清空", command=self.empty,
                                   bg=self.COLOR_WARNING, fg="white", relief="flat")
        btn_clear.place(x=405, y=360, width=55, height=32)

        tkinter.Label(left, text="影片名称：", font=self.FONT_NORMAL, bg=self.COLOR_FRAME) \
            .place(x=20, y=400, width=80, height=32)
        self.entry_title = tkinter.Entry(left, font=self.FONT_NORMAL, bg="white", fg="#999", bd=0)
        self.entry_title.place(x=105, y=400, width=290, height=32)
        self.entry_title.insert(0, "（可选，留空则自动识别）")
        self.entry_title.bind("<FocusIn>", self._on_title_focus_in)
        self.entry_title.bind("<FocusOut>", self._on_title_focus_out)

        tkinter.Label(left, text="解析接口：", font=self.FONT_NORMAL, bg=self.COLOR_FRAME) \
            .place(x=20, y=438, width=80, height=32)
        self.api_var = tkinter.StringVar(value="默认接口")
        tkinter.ttk.Combobox(left, textvariable=self.api_var,
                              values=list(self.parse_apis.keys()), state="readonly") \
            .place(x=105, y=438, width=160, height=32)

        btn_play = tkinter.Button(left, text="▶ 播放视频", command=self.play_video,
                                  bg=self.COLOR_SECONDARY, fg="white",
                                  font=self.FONT_BUTTON, relief="flat")
        btn_play.place(relx=0.5, y=485, anchor="center", width=180, height=44)

        # --- 右侧：历史记录 ---
        right = tkinter.Frame(main, bg=self.COLOR_FRAME, bd=1, relief="solid")
        right.pack(side="right", fill="both", expand=True, padx=(10, 0), pady=5)
        right.pack_propagate(False)
        right.configure(width=450, height=540)

        tkinter.Label(right, text="历史解析记录", font=self.FONT_NORMAL, bg=self.COLOR_FRAME) \
            .place(x=20, y=12)

        self.history_listbox = tkinter.Listbox(right, font=self.FONT_SMALL, bg=self.COLOR_HISTORY,
                                               fg=self.COLOR_LINK, selectbackground="#e6f7ff",
                                               selectforeground=self.COLOR_LINK)
        self.history_listbox.place(x=20, y=48, width=408, height=368)
        sb = tkinter.Scrollbar(right, command=self.history_listbox.yview)
        sb.place(x=428, y=48, height=368)
        self.history_listbox.config(yscrollcommand=sb.set)

        for label, cmd, color, x_pos in [
            ("播放选中", self.play_selected_history, self.COLOR_SECONDARY, 28),
            ("删除选中", self.delete_selected_history, self.COLOR_DELETE, 138),
            ("清空所有", self.clear_all_history, "#888", 248),
        ]:
            b = tkinter.Button(right, text=label, command=cmd, bg=color, fg="white", relief="flat")
            b.place(x=x_pos, y=428, width=100, height=34)

        self.update_history_listbox()

    def update_history_listbox(self):
        self.history_listbox.delete(0, tkinter.END)
        for r in self.history_records:
            self.history_listbox.insert(tkinter.END, r["title"])


if __name__ == "__main__":
    root = tkinter.Tk()
    app = VIPVideoApp(root)
    root.mainloop()
