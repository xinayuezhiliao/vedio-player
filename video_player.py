"""
VIP视频解析工具 - 基于 urllib (无外部依赖)
- 真实能用的功能: 本地资源索引库 + VLC/Chrome/浏览器 fallback 播放链 + 跳转平台搜索页
- 老实承认做不到: 远程搜爱奇艺/腾讯/优酷/芒果的真实视频链接 (它们是 JS 渲染 SPA + 反爬)
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
import shutil
import ssl
import threading
import urllib.request
import webbrowser
from urllib.parse import urlparse, unquote, parse_qs, quote

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
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout) as r:
            ct = r.headers.get("Content-Type", "")
            enc = "utf-8"
            for p in ct.split(";"):
                if "charset" in p:
                    enc = p.split("charset=")[-1].strip()
                    break
            return r.read().decode(enc, errors="ignore")
    except Exception:
        return ""


def get_app_data_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_PATH = get_app_data_path()
HISTORY_FILE = os.path.join(BASE_PATH, "video_parse_history.json")
FAVORITE_FILE = os.path.join(BASE_PATH, "video_favorite.json")
# 新增: 本地资源索引 - 用户手动维护,搜得到
LOCAL_RESOURCES_FILE = os.path.join(BASE_PATH, "local_resources.json")

# ============== 播放器链 (VLC → Chrome → 浏览器) ==============
# 优先级: VLC (本地无广告) > Chrome App (无地址栏) > webbrowser (兜底)
VLC_CANDIDATE_PATHS = [
    r"D:\Program Files\VideoLAN\VLC\vlc.exe",
    r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
]
CHROME_CANDIDATE_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_vlc_path():
    """探测 VLC 安装路径。返回路径字符串或 None。"""
    for p in VLC_CANDIDATE_PATHS:
        if os.path.exists(p):
            return p
    # 用 where 兜底
    try:
        out = subprocess.check_output(["where", "vlc"], stderr=subprocess.DEVNULL, timeout=3)
        path = out.decode(errors="ignore").strip().splitlines()[0].strip()
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    return None


def find_chrome_path():
    """探测 Chrome 安装路径。返回路径字符串或 None。"""
    for p in CHROME_CANDIDATE_PATHS:
        if os.path.exists(p):
            return p
    try:
        out = subprocess.check_output(["where", "chrome"], stderr=subprocess.DEVNULL, timeout=3)
        path = out.decode(errors="ignore").strip().splitlines()[0].strip()
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    return None


def play_url(url):
    """播放链: VLC → Chrome App → webbrowser。返回实际使用的播放器名。"""
    vlc = find_vlc_path()
    if vlc:
        try:
            subprocess.Popen(
                [vlc, url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return "VLC"
        except Exception:
            pass
    chrome = find_chrome_path()
    if chrome:
        try:
            subprocess.Popen(
                [chrome, f"--app={url}", "--window-size=960,620",
                 "--no-scrollbar", "--disable-web-security"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return "Chrome"
        except Exception:
            pass
    # 兜底
    webbrowser.open(url)
    return "Browser"


# ============== 平台搜索页跳转 ==============
# 老实承认: 直接爬这些平台的搜索 API 抓不到东西(JS 渲染 + 反爬)
# 替代方案: 跳到搜索页让用户自己看、自己复制 URL
PLATFORM_SEARCH_URLS = {
    "爱奇艺": "https://so.iqiyi.com/so?q={q}",
    "腾讯视频": "https://v.qq.com/x/search/?q={q}",
    "优酷": "https://so.youku.com/search/video?q={q}",
    "芒果TV": "https://so.mgtv.com/list?k={q}",
}


def open_platform_search(platform, keyword):
    """跳转到平台搜索页"""
    tmpl = PLATFORM_SEARCH_URLS.get(platform)
    if not tmpl:
        return
    url = tmpl.format(q=quote(keyword))
    webbrowser.open(url)


# ============== 本地资源索引库 ==============
# 这是真正能搜到的"假搜索":
# - 数据来源: local_resources.json (用户手动维护)
# - 字段: { "title": "...", "url": "...", "source": "..." }
# - 不存在时返回空,UI 提示"本地库为空,去浏览器搜或手动添加"
#
# 用户手动添加方法: 收藏库里的项目可以"导出到本地库",也可以直接编辑 local_resources.json

def load_local_resources():
    if not os.path.exists(LOCAL_RESOURCES_FILE):
        return []
    try:
        with open(LOCAL_RESOURCES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_local_resources(items):
    try:
        with open(LOCAL_RESOURCES_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def search_local_resources(keyword, favorite_records=None, history_records=None):
    """本地搜: 搜 local_resources.json + 收藏库 + 历史记录
    这是当前唯一能保证搜出东西的搜索实现。
    """
    kw = (keyword or "").strip().lower()
    if not kw:
        return []
    seen = set()
    results = []

    # 1. 本地索引库
    for item in load_local_resources():
        t = (item.get("title") or "").lower()
        u = (item.get("url") or "").lower()
        if (kw in t or kw in u) and u not in seen:
            results.append({
                "title": item.get("title", "未知"),
                "url": item.get("url", ""),
                "source": item.get("source", "本地库"),
            })
            seen.add(u)

    # 2. 收藏库
    for fav in (favorite_records or []):
        t = (fav.get("title") or "").lower()
        u = (fav.get("url") or "").lower()
        if (kw in t or kw in u) and u not in seen:
            results.append({
                "title": fav.get("title", "未知"),
                "url": fav.get("url", ""),
                "source": "收藏库",
            })
            seen.add(u)

    # 3. 历史记录
    for h in (history_records or []):
        t = (h.get("title") or "").lower()
        u = (h.get("url") or "").lower()
        if (kw in t or kw in u) and u not in seen:
            results.append({
                "title": h.get("title", "未知"),
                "url": h.get("url", ""),
                "source": "历史记录",
            })
            seen.add(u)

    return results


# ============== 主程序 ==============

class VIPVideoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VIP视频解析工具")
        self.center_window(1000, 720)
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
        # 启动时后台更新占位标题 (不阻塞 UI)
        threading.Thread(target=self._async_update_untagged, daemon=True).start()
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

    def save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history_records, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _async_update_untagged(self):
        """后台线程: 更新待识别的历史标题 (不阻塞 UI 启动)"""
        if not self.history_records:
            return
        for record in self.history_records:
            url = record.get("url", "")
            if (not record.get("is_manual", False)
                    and record.get("title", "").startswith("待更新_")
                    and url):
                try:
                    record["title"] = self.extract_video_title(url)
                except Exception:
                    pass
        self.save_history()
        # 通过 after 安全刷新 UI
        try:
            self.root.after(0, self.update_history_listbox)
        except Exception:
            pass

    def extract_video_title(self, url):
        """智能提取视频标题。
        老实承认: 优酷/爱奇艺/腾讯的 og:title 90% 抓不到(JS 渲染 + 反爬),
        所以这里不再浪费时间去爬,直接走 URL 末段 fallback。
        """
        url = (url or "").strip()
        if not url:
            return "未知视频"

        # 腾讯: URL 自带 ?title= 时拿
        if "v.qq.com" in url:
            query = parse_qs(urlparse(url).query)
            if query.get("title"):
                title = unquote(query["title"][0])
                return re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", "", title).strip()[:30] or "未知视频"
            # cover id 兜底
            m = re.search(r"/cover/([A-Za-z0-9]+)\.html", url)
            if m:
                return f"腾讯视频_{m.group(1)[:8]}"

        # 抠中文片段
        cn = re.findall(r"[\u4e00-\u9fa5]{2,}", url)
        if cn:
            return re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", "", max(cn, key=len)).strip()[:30] or "未知视频"

        # ID 末段 (要求 6+ 位)
        m = re.search(r"/(?:cover|v_show/id_|v_)([A-Za-z0-9]{6,})", url)
        if m:
            return f"视频_{m.group(1)[-8:]}"

        # 兜底: 取 URL path 最后一段 (剥 .html),再做清洗
        path = url.split("?")[0].rstrip("/").split("/")
        last = path[-1] if path else ""
        last_clean = re.sub(r"\.html?", "", last, flags=re.IGNORECASE)
        last_clean = re.sub(r"[^A-Za-z0-9_-]", "", last_clean)
        # 太短(<2)就用整段末 10
        if len(last_clean) < 2:
            tail = re.sub(r"[^A-Za-z0-9_-]", "", url.split("?")[0])[-10:]
            last_clean = tail
        return f"视频_{last_clean[:10]}" if last_clean else "未知视频"

    def add_to_favorite(self, override_url=None, override_title=None):
        """收藏。
        override_url/override_title: 用于搜索结果收藏 (从参数传,不走 UI)
        """
        target_url = (override_url or self.entry_url.get()).strip()
        if not target_url:
            tkinter.messagebox.showwarning("提示", "请输入视频网址！")
            return
        if override_title:
            video_title = override_title
        else:
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
        if not override_url:
            tkinter.messagebox.showinfo("成功", f"已收藏：{video_title}")

    def add_to_local_resources(self, override_url=None, override_title=None, source=None):
        """加入本地资源库 (真正能搜到的索引)"""
        target_url = (override_url or self.entry_url.get()).strip()
        if not target_url:
            tkinter.messagebox.showwarning("提示", "请输入视频网址！")
            return
        if override_title:
            video_title = override_title
        else:
            custom = self.entry_title.get().strip()
            if custom == "（可选，留空则自动识别）":
                custom = ""
            video_title = custom.strip() or self.extract_video_title(target_url)
        items = load_local_resources()
        for item in items:
            if item.get("url") == target_url:
                tkinter.messagebox.showinfo("提示", "本地资源库已有该影片")
                return
        items.insert(0, {
            "title": video_title,
            "url": target_url,
            "source": source or self.api_var.get(),
            "add_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        if save_local_resources(items):
            if not override_url:
                tkinter.messagebox.showinfo("成功", f"已加入本地资源库：{video_title}\n下次搜索「{video_title[:6]}」就能搜到了")
        else:
            tkinter.messagebox.showerror("失败", "保存本地资源库失败")

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
            if idx >= len(self.favorite_records):
                return
            item = self.favorite_records[idx]
            api = self.parse_apis.get(item.get("api", "默认接口"), self.parse_apis["默认接口"])
            self._play_and_record(api + item["url"], item.get("title", ""), item.get("api", "默认接口"))

        def to_local():
            """导出当前选中到本地资源库"""
            if not fav_listbox.curselection():
                tkinter.messagebox.showwarning("提示", "请先选中")
                return
            idx = fav_listbox.curselection()[0] // 3
            if idx >= len(self.favorite_records):
                return
            item = self.favorite_records[idx]
            self.add_to_local_resources(override_url=item["url"], override_title=item.get("title", ""), source=item.get("api", ""))

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
                                  ("→ 本地库", to_local, "#722ed1"),
                                  ("删除选中", del_fav, self.COLOR_DELETE),
                                  ("清空收藏", clear_fav, self.COLOR_WARNING)]:
            b = tkinter.Button(btn_frame, text=text, command=cmd, bg=color, fg="white",
                               font=self.FONT_SMALL_BUTTON, relief="flat", width=12)
            b.pack(side="left", padx=8)

    def open_local_resources_window(self):
        """本地资源库管理窗口"""
        w = tkinter.Toplevel(self.root)
        w.title("本地资源库")
        w.geometry("800x500")
        w.configure(bg=self.COLOR_BG)

        tkinter.Frame(w, bg="#13c2c2", height=50).pack(fill="x")
        tkinter.Label(w, text="本地资源库 (搜得到)", font=("Microsoft YaHei", 16, "bold"),
                      fg="white", bg="#13c2c2").place(relx=0.5, rely=0.5, anchor="center")

        # 提示
        tkinter.Label(w, text="手动维护,搜什么有什么。建议把常用的影片 URL 都加进来。",
                      font=self.FONT_SMALL, fg="#666", bg=self.COLOR_BG).place(x=15, y=58, width=770)

        main = tkinter.Frame(w, bg=self.COLOR_BG)
        main.pack(fill="both", expand=True, padx=15, pady=15)

        canvas = tkinter.Canvas(main, bg="white", bd=0, highlightthickness=0)
        scrollbar = tkinter.ttk.Scrollbar(main, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        frame = tkinter.Frame(canvas, bg="white")
        canvas.create_window((0, 0), window=frame, anchor="nw")

        items = load_local_resources()
        lb = tkinter.Listbox(frame, font=self.FONT_NORMAL, fg=self.COLOR_TEXT, bg="white",
                             selectbackground="#e6f7ff", selectforeground=self.COLOR_LINK,
                             justify="left", width=80, height=15, bd=0)
        lb.pack(fill="both", expand=True, padx=5, pady=5)
        for i, it in enumerate(items):
            lb.insert(tkinter.END, f"{i+1}. {it.get('title','未知')}  [{it.get('source','')}]")
            lb.insert(tkinter.END, f"    {it.get('url','')}")
            lb.insert(tkinter.END, "")

        def on_config(_):
            canvas.configure(scrollregion=canvas.bbox("all"))
        frame.bind("<Configure>", on_config)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta//120), "units"))

        btn_frame = tkinter.Frame(w, bg=self.COLOR_BG)
        btn_frame.pack(fill="x", pady=10)

        def play_sel():
            if not lb.curselection():
                tkinter.messagebox.showwarning("提示", "请先选中")
                return
            idx = lb.curselection()[0] // 3
            if idx >= len(items):
                return
            it = items[idx]
            api = self.parse_apis.get(it.get("source", "默认接口"), self.parse_apis["默认接口"])
            self._play_and_record(api + it["url"], it.get("title", ""), it.get("source", "默认接口"))

        def del_sel():
            if not lb.curselection():
                tkinter.messagebox.showwarning("提示", "请先选中")
                return
            idx = lb.curselection()[0] // 3
            if tkinter.messagebox.askyesno("确认", "从本地资源库删除？"):
                items.pop(idx)
                save_local_resources(items)
                w.destroy()
                self.open_local_resources_window()

        def add_manual():
            """手动添加条目"""
            dialog = tkinter.Toplevel(w)
            dialog.title("手动添加本地资源")
            dialog.geometry("500x220")
            dialog.configure(bg=self.COLOR_BG)
            tkinter.Label(dialog, text="影片名:", bg=self.COLOR_BG).place(x=20, y=20)
            e_t = tkinter.Entry(dialog, width=50); e_t.place(x=80, y=20, height=28)
            tkinter.Label(dialog, text="URL:", bg=self.COLOR_BG).place(x=20, y=60)
            e_u = tkinter.Entry(dialog, width=50); e_u.place(x=80, y=60, height=28)
            tkinter.Label(dialog, text="来源:", bg=self.COLOR_BG).place(x=20, y=100)
            e_s = tkinter.Entry(dialog, width=50); e_s.place(x=80, y=100, height=28)
            e_s.insert(0, "手动")
            def save_one():
                t = e_t.get().strip(); u = e_u.get().strip(); s = e_s.get().strip() or "手动"
                if not t or not u:
                    tkinter.messagebox.showwarning("提示", "影片名和 URL 必填")
                    return
                items.insert(0, {"title": t, "url": u, "source": s,
                                 "add_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                save_local_resources(items)
                dialog.destroy()
                w.destroy()
                self.open_local_resources_window()
            tkinter.Button(dialog, text="保存", command=save_one,
                           bg=self.COLOR_SECONDARY, fg="white").place(x=200, y=150, width=100, height=35)

        for text, cmd, color in [("播放选中", play_sel, self.COLOR_SECONDARY),
                                  ("手动添加", add_manual, self.COLOR_PRIMARY),
                                  ("删除选中", del_sel, self.COLOR_DELETE)]:
            b = tkinter.Button(btn_frame, text=text, command=cmd, bg=color, fg="white",
                               font=self.FONT_SMALL_BUTTON, relief="flat", width=12)
            b.pack(side="left", padx=8)

    # ---- 搜索 ----

    def on_search_key(self, e):
        if e.keysym == "Return":
            self.do_search()

    def do_search(self):
        keyword = self.entry_search.get().strip()
        if not keyword:
            tkinter.messagebox.showwarning("提示", "请输入要搜索的电影或剧集名称")
            return
        self.search_results = []
        self.search_var.set(f"正在搜本地资源库 / 收藏 / 历史 ...")
        self.search_listbox.delete(0, tkinter.END)
        self.root.update()

        # 真能搜到东西的: 本地索引库 + 收藏 + 历史
        results = search_local_resources(keyword, self.favorite_records, self.history_records)

        if results:
            self.search_results = results
            for item in results:
                self.search_listbox.insert(
                    tkinter.END,
                    f"  [{item['source']}] {item['title']}"
                )
            self.search_var.set(
                f"✅ 本地命中 {len(results)} 条 | 找不到时点「浏览器搜」去 4 大平台搜"
            )
        else:
            self.search_var.set(
                f"❌ 本地无命中。建议: 点下方「浏览器搜」跳到平台搜,或者手动加进本地库"
            )

    def play_selected_search(self):
        if not self.search_results:
            self._open_browser_search_prompt()
            return
        if not self.search_listbox.curselection():
            tkinter.messagebox.showwarning("提示", "请先选中要播放的影片")
            return
        idx = self.search_listbox.curselection()[0]
        if idx >= len(self.search_results):
            return
        item = self.search_results[idx]
        api_name = self.api_var.get()
        api = self.parse_apis[api_name]
        self._play_and_record(api + item["url"], item.get("title", ""), api_name)

    def favorite_search_result(self):
        if not self.search_results:
            return
        if not self.search_listbox.curselection():
            tkinter.messagebox.showwarning("提示", "请先选中")
            return
        idx = self.search_listbox.curselection()[0]
        if idx >= len(self.search_results):
            return
        item = self.search_results[idx]
        self.add_to_favorite(override_url=item["url"], override_title=item.get("title", ""))

    def add_search_to_local(self):
        if not self.search_results:
            return
        if not self.search_listbox.curselection():
            tkinter.messagebox.showwarning("提示", "请先选中")
            return
        idx = self.search_listbox.curselection()[0]
        if idx >= len(self.search_results):
            return
        item = self.search_results[idx]
        self.add_to_local_resources(override_url=item["url"], override_title=item.get("title", ""), source=item.get("source", ""))

    def _open_browser_search_prompt(self):
        """搜不到时,弹一个 '用浏览器去哪个平台搜' 的菜单"""
        keyword = self.entry_search.get().strip()
        if not keyword:
            return
        # 用一个简单 Toplevel 让用户选
        w = tkinter.Toplevel(self.root)
        w.title("用浏览器搜")
        w.geometry("380x380")
        w.configure(bg=self.COLOR_BG)
        tkinter.Label(w, text=f"本地无「{keyword}」结果,选个平台去搜:",
                      font=self.FONT_NORMAL, bg=self.COLOR_BG, wraplength=350).pack(pady=15)
        for name in PLATFORM_SEARCH_URLS:
            tkinter.Button(
                w, text=f"🌐 {name}",
                command=lambda p=name, k=keyword: (open_platform_search(p, k), w.destroy()),
                bg=self.COLOR_PRIMARY, fg="white",
                font=self.FONT_SMALL_BUTTON, relief="flat", width=20, height=2,
            ).pack(pady=6)

    def _play_and_record(self, full_url, title, api_name):
        """统一的播放入口: 写历史 + 选播放器"""
        self.save_history_record(full_url, title, api_name)
        self.update_history_listbox()
        player = play_url(full_url)
        tkinter.messagebox.showinfo(
            "播放", f"已用 {player} 播放: {title or full_url}\n\n(链: VLC → Chrome → Browser)"
        )

    # ---- 内部: 把记录写到历史 ----

    def save_history_record(self, full_url, title, api_name):
        # title 里可能要剥离 URL 部分(那是解析 API 加的前缀)
        # 简单做法: full_url 包含解析 API,记录里只存原始 URL
        # 但 parse_api 已经拼好了,这里只存原始 url 和 title
        # 简化: 直接全存
        record = {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "url": full_url,
            "api": api_name,
            "title": title or self.extract_video_title(full_url),
            "is_manual": bool(title),
        }
        self.history_records.insert(0, record)
        if len(self.history_records) > 50:
            self.history_records = self.history_records[:50]
        self.save_history()

    # ---- 历史记录 ----

    def play_selected_history(self):
        if not self.history_listbox.curselection():
            tkinter.messagebox.showwarning("提示", "请先选中要播放的历史记录")
            return
        idx = self._history_row_to_index(self.history_listbox.curselection()[0])
        if idx is None or idx >= len(self.history_records):
            return
        r = self.history_records[idx]
        api = self.parse_apis.get(r["api"], self.parse_apis["默认接口"])
        # 历史里存的 url 可能已经是解析过的完整 URL
        self._play_and_record(r["url"], r["title"], r["api"])

    def delete_selected_history(self):
        if not self.history_listbox.curselection():
            tkinter.messagebox.showwarning("提示", "请先选中")
            return
        idx = self._history_row_to_index(self.history_listbox.curselection()[0])
        if idx is None:
            return
        if tkinter.messagebox.askyesno("确认", "删除该记录？"):
            self.history_records.pop(idx)
            self.save_history()
            self.update_history_listbox()

    def clear_all_history(self):
        if tkinter.messagebox.askyesno("确认", "清空所有历史？"):
            self.history_records = []
            self.update_history_listbox()
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)

    def _history_row_to_index(self, row):
        """listbox 行号 -> history_records 索引 (3 行/条)"""
        if row is None or row < 0:
            return None
        idx = row // 3
        if idx >= len(self.history_records):
            return None
        return idx

    # ---- 焦点占位 ----

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
        self._play_and_record(api + url, title, api_name)

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

        # 顶部状态栏: 显示探测到的播放器
        status = tkinter.Frame(self.root, bg="#fafafa", height=24)
        status.pack(fill="x")
        vlc = find_vlc_path()
        chrome = find_chrome_path()
        players = []
        if vlc: players.append(f"✅ VLC ({os.path.basename(vlc)})")
        else:   players.append("❌ VLC 未找到")
        if chrome: players.append(f"✅ Chrome ({os.path.basename(chrome)})")
        else:   players.append("❌ Chrome 未找到")
        players.append("✅ Browser (兜底)")
        tkinter.Label(status, text="播放器链: " + "  →  ".join(players),
                      font=("Microsoft YaHei", 9), fg="#555", bg="#fafafa", anchor="w") \
            .place(x=20, y=4, width=960)

        main = tkinter.Frame(self.root, bg=self.COLOR_BG)
        main.pack(fill="both", expand=True, padx=20, pady=12)

        # --- 左侧: 搜索 + 解析 ---
        left = tkinter.Frame(main, bg=self.COLOR_FRAME, bd=1, relief="solid")
        left.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=5)
        left.pack_propagate(False)
        left.configure(width=520, height=620)

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

        self.search_var = tkinter.StringVar(value="搜本地库 + 收藏 + 历史 (真能搜到)")
        tkinter.Label(left, textvariable=self.search_var, font=self.FONT_SMALL,
                      fg="#888", bg=self.COLOR_FRAME, anchor="w", wraplength=470) \
            .place(x=20, y=88, width=470, height=20)

        slf = tkinter.Frame(left)
        slf.place(x=20, y=112, width=470, height=200)
        sb_s = tkinter.Scrollbar(slf)
        sb_s.pack(side="right", fill="y")
        self.search_listbox = tkinter.Listbox(slf, font=self.FONT_SMALL,
                                              bg=self.COLOR_SEARCH_BG, fg="#8c5a00",
                                              selectbackground="#ffe58f", selectforeground="#8c5a00",
                                              yscrollcommand=sb_s.set, bd=0, highlightthickness=0)
        self.search_listbox.pack(side="left", fill="both", expand=True)
        sb_s.config(command=self.search_listbox.yview)
        self.search_listbox.bind("<Double-Button-1>", lambda _: self.play_selected_search())

        # 搜索区按钮
        tkinter.Button(left, text="▶ 播放", command=self.play_selected_search,
                       bg=self.COLOR_SECONDARY, fg="white",
                       font=self.FONT_SMALL_BUTTON, relief="flat") \
            .place(x=20, y=320, width=85, height=34)
        tkinter.Button(left, text="＋ 收藏", command=self.favorite_search_result,
                       bg=self.COLOR_FAVORITE, fg="white",
                       font=self.FONT_SMALL_BUTTON, relief="flat") \
            .place(x=115, y=320, width=80, height=34)
        tkinter.Button(left, text="＋ 本地库", command=self.add_search_to_local,
                       bg="#13c2c2", fg="white",
                       font=self.FONT_SMALL_BUTTON, relief="flat") \
            .place(x=205, y=320, width=90, height=34)
        tkinter.Button(left, text="🌐 浏览器搜", command=self._open_browser_search_prompt,
                       bg="#722ed1", fg="white",
                       font=self.FONT_SMALL_BUTTON, relief="flat") \
            .place(x=305, y=320, width=105, height=34)

        tkinter.Button(left, text="📚 我的收藏", command=self.open_favorite_window,
                       bg="#722ed1", fg="white",
                       font=self.FONT_SMALL_BUTTON, relief="flat") \
            .place(x=20, y=360, width=120, height=32)
        tkinter.Button(left, text="💾 本地库", command=self.open_local_resources_window,
                       bg="#13c2c2", fg="white",
                       font=self.FONT_SMALL_BUTTON, relief="flat") \
            .place(x=150, y=360, width=110, height=32)

        # 分隔线
        tkinter.Frame(left, bg="#d9d9d9", height=1).place(x=20, y=402, width=470)

        # 手动输入
        tkinter.Label(left, text="目标网址：", font=self.FONT_NORMAL, bg=self.COLOR_FRAME) \
            .place(x=20, y=412, width=80, height=32)
        self.entry_url = tkinter.Entry(left, font=self.FONT_NORMAL, bg="white", bd=0)
        self.entry_url.place(x=105, y=412, width=290, height=32)
        btn_clear = tkinter.Button(left, text="清空", command=self.empty,
                                   bg=self.COLOR_WARNING, fg="white", relief="flat")
        btn_clear.place(x=405, y=412, width=55, height=32)

        tkinter.Label(left, text="影片名称：", font=self.FONT_NORMAL, bg=self.COLOR_FRAME) \
            .place(x=20, y=452, width=80, height=32)
        self.entry_title = tkinter.Entry(left, font=self.FONT_NORMAL, bg="white", fg="#999", bd=0)
        self.entry_title.place(x=105, y=452, width=290, height=32)
        self.entry_title.insert(0, "（可选，留空则自动识别）")
        self.entry_title.bind("<FocusIn>", self._on_title_focus_in)
        self.entry_title.bind("<FocusOut>", self._on_title_focus_out)

        tkinter.Label(left, text="解析接口：", font=self.FONT_NORMAL, bg=self.COLOR_FRAME) \
            .place(x=20, y=492, width=80, height=32)
        self.api_var = tkinter.StringVar(value="默认接口")
        tkinter.ttk.Combobox(left, textvariable=self.api_var,
                              values=list(self.parse_apis.keys()), state="readonly") \
            .place(x=105, y=492, width=160, height=32)

        btn_play = tkinter.Button(left, text="▶ 播放视频", command=self.play_video,
                                  bg=self.COLOR_SECONDARY, fg="white",
                                  font=self.FONT_BUTTON, relief="flat")
        btn_play.place(x=105, y=540, width=180, height=44)
        tkinter.Button(left, text="＋ 收藏", command=self.add_to_favorite,
                       bg=self.COLOR_FAVORITE, fg="white",
                       font=self.FONT_SMALL_BUTTON, relief="flat") \
            .place(x=295, y=540, width=100, height=44)
        tkinter.Button(left, text="＋ 本地库", command=lambda: self.add_to_local_resources(),
                       bg="#13c2c2", fg="white",
                       font=self.FONT_SMALL_BUTTON, relief="flat") \
            .place(x=105, y=590, width=290, height=30)

        # --- 右侧: 历史记录 ---
        right = tkinter.Frame(main, bg=self.COLOR_FRAME, bd=1, relief="solid")
        right.pack(side="right", fill="both", expand=True, padx=(10, 0), pady=5)
        right.pack_propagate(False)
        right.configure(width=420, height=620)

        tkinter.Label(right, text="历史解析记录", font=self.FONT_NORMAL, bg=self.COLOR_FRAME) \
            .place(x=20, y=12)

        self.history_listbox = tkinter.Listbox(right, font=self.FONT_SMALL, bg=self.COLOR_HISTORY,
                                               fg=self.COLOR_LINK, selectbackground="#e6f7ff",
                                               selectforeground=self.COLOR_LINK)
        self.history_listbox.place(x=20, y=48, width=378, height=448)
        sb = tkinter.Scrollbar(right, command=self.history_listbox.yview)
        sb.place(x=398, y=48, height=448)
        self.history_listbox.config(yscrollcommand=sb.set)

        for label, cmd, color, x_pos in [
            ("播放选中", self.play_selected_history, self.COLOR_SECONDARY, 28),
            ("删除选中", self.delete_selected_history, self.COLOR_DELETE, 138),
            ("清空所有", self.clear_all_history, "#888", 248),
        ]:
            b = tkinter.Button(right, text=label, command=cmd, bg=color, fg="white", relief="flat")
            b.place(x=x_pos, y=508, width=100, height=34)

        self.update_history_listbox()

    def update_history_listbox(self):
        """渲染历史列表。每条记录占 3 行: 标题 / 时间+接口 / 空行"""
        self.history_listbox.delete(0, tkinter.END)
        for r in self.history_records:
            title = r.get("title", "未知")
            t = r.get("time", "")
            api = r.get("api", "默认接口")
            self.history_listbox.insert(tkinter.END, f"{title}")
            self.history_listbox.insert(tkinter.END, f"    {t} | {api}")
            self.history_listbox.insert(tkinter.END, "")


if __name__ == "__main__":
    root = tkinter.Tk()
    app = VIPVideoApp(root)
    root.mainloop()