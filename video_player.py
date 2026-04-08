import tkinter
import tkinter.messagebox
import tkinter.ttk
import webbrowser
import sys
import subprocess
import datetime
import json
import os
import re
import importlib
import subprocess
import requests
from urllib.parse import urlparse, unquote, parse_qs

# 忽略requests警告
requests.packages.urllib3.disable_warnings()

def get_app_data_path():
    """获取程序数据保存路径（优先exe所在目录，开发模式用脚本目录）"""
    if getattr(sys, 'frozen', False):
        # 打包成exe后的运行模式
        base_path = os.path.dirname(sys.executable)  # exe所在目录
    else:
        # 开发模式（运行py文件）
        base_path = os.path.dirname(os.path.abspath(__file__))
    return base_path

# 历史记录和收藏库保存路径（固定到exe/脚本所在目录）
BASE_PATH = get_app_data_path()
HISTORY_FILE = os.path.join(BASE_PATH, "video_parse_history.json")
FAVORITE_FILE = os.path.join(BASE_PATH, "video_favorite.json")

# VLC 路径
VLC_PATH = r"D:\Program Files\VideoLAN\VLC\vlc.exe"


class VIPVideoApp:
    def __init__(self, root):
        self.root = root
        self.root.title('VIP视频解析工具')
        self.center_window(1000, 500)
        self.root.resizable(True, True)
        self.root.configure(bg='#f0f2f2')

        self.setup_style()
        self.parse_apis = {
            "默认接口": "https://www.ckplayer.vip/jiexi/?url=",
            "备用接口1": "https://jx.xmflv.com/?url=",
            "备用接口2": "https://jiexi.071811.cc/jx.php?url="
        }
        self.history_records = self.load_history()
        self.favorite_records = self.load_favorite()
        self.update_untagged_history_titles()
        self.create_widgets()

    def center_window(self, width, height):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def setup_style(self):
        self.COLOR_BG = '#f0f2f2'
        self.COLOR_PRIMARY = '#1890ff'
        self.COLOR_SECONDARY = '#52c41a'
        self.COLOR_FAVORITE = '#faad14'
        self.COLOR_WARNING = '#ff4d4f'
        self.COLOR_TEXT = '#333333'
        self.COLOR_LIGHT = '#ffffff'
        self.COLOR_FRAME = '#e8e8e8'
        self.COLOR_HISTORY = '#f8f9fa'
        self.COLOR_LINK = '#1890ff'
        self.COLOR_DELETE = '#fa8c16'

        self.FONT_TITLE = ('Microsoft YaHei', 18, 'bold')
        self.FONT_NORMAL = ('Microsoft YaHei', 12)
        self.FONT_SMALL = ('Microsoft YaHei', 11)
        self.FONT_BUTTON = ('Microsoft YaHei', 14, 'bold')
        self.FONT_SMALL_BUTTON = ('Microsoft YaHei', 12, 'bold')

    def load_history(self):
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    records = json.load(f)
                    for record in records:
                        if 'title' not in record:
                            record['title'] = f"待更新_{record.get('url', '未知URL')[:10]}..."
                            record['is_manual'] = False
                        if 'is_manual' not in record:
                            record['is_manual'] = False
                    return records
            return []
        except Exception as e:
            tkinter.messagebox.showwarning('提示', f'加载历史记录失败：{str(e)}')
            return []

    def load_favorite(self):
        try:
            if os.path.exists(FAVORITE_FILE):
                with open(FAVORITE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            tkinter.messagebox.showwarning('提示', f'加载收藏库失败：{str(e)}')
            return []

    def save_favorite(self):
        try:
            with open(FAVORITE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.favorite_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            tkinter.messagebox.showwarning('提示', f'保存收藏失败：{str(e)}')

    def update_untagged_history_titles(self):
        if not self.history_records:
            return
        for record in self.history_records:
            if not record.get('is_manual', False) and record.get('title', '').startswith('待更新_'):
                url = record.get('url', '')
                if url:
                    new_title = self.extract_video_title(url)
                    record['title'] = new_title
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.history_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"更新历史记录失败：{e}")

    def extract_video_title(self, url):
        url = url.strip()
        title = ""

        if "v.qq.com" in url:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            if 'title' in query and query['title']:
                title = unquote(query['title'][0])
        elif "iqiyi.com" in url or "youku.com" in url:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                resp = requests.get(url, headers=headers, timeout=2, verify=False)
                resp.encoding = 'utf-8'
                match = re.search(r'<meta property="og:title" content="([^"]+)"', resp.text)
                if match:
                    title = match.group(1)
            except:
                pass

        if not title:
            cn = re.findall(r'[\u4e00-\u9fa5]{2,}', url)
            if cn:
                title = max(cn, key=len)
            else:
                title = f"视频_{url[-10:]}"

        title = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', '', title).strip()[:30]
        return title if title else "未知视频"

    def save_history(self, url, api_name, custom_title=""):
        is_manual = False
        if custom_title.strip():
            video_title = custom_title.strip()
            is_manual = True
        else:
            video_title = self.extract_video_title(url)

        record = {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "url": url,
            "api": api_name,
            "title": video_title,
            "is_manual": is_manual
        }
        self.history_records.insert(0, record)
        if len(self.history_records) > 50:
            self.history_records = self.history_records[:50]
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.history_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            tkinter.messagebox.showwarning('提示', f'保存历史失败：{str(e)}')

    def add_to_favorite(self):
        target_url = self.entry_url.get().strip()
        if not target_url:
            tkinter.messagebox.showwarning('提示', '请输入视频网址！')
            return

        custom_title = self.entry_title.get().strip()
        if custom_title == "（可选，留空则自动识别）":
            custom_title = ""

        if custom_title.strip():
            video_title = custom_title.strip()
        else:
            video_title = self.extract_video_title(target_url)

        selected_api = self.api_var.get()

        for f in self.favorite_records:
            if f.get('url') == target_url:
                tkinter.messagebox.showinfo('提示', '已收藏过该影片')
                return

        self.favorite_records.insert(0, {
            "title": video_title,
            "url": target_url,
            "api": selected_api,
            "add_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        self.save_favorite()
        tkinter.messagebox.showinfo('成功', f'已收藏：{video_title}')

    def open_favorite_window(self):
        w = tkinter.Toplevel(self.root)
        w.title('我的收藏')
        w.geometry('800x500')
        w.configure(bg=self.COLOR_BG)

        top = tkinter.Frame(w, bg=self.COLOR_FAVORITE, height=50)
        top.pack(fill='x')
        tkinter.Label(top, text='我的影片收藏', font=('Microsoft YaHei', 16, 'bold'),
                      fg='white', bg=self.COLOR_FAVORITE).place(relx=0.5, rely=0.5, anchor='center')

        main = tkinter.Frame(w, bg=self.COLOR_BG)
        main.pack(fill='both', expand=True, padx=15, pady=15)

        # 平滑滚动 + Listbox
        canvas = tkinter.Canvas(main, bg='white', bd=0, highlightthickness=0)
        scrollbar = tkinter.ttk.Scrollbar(main, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        frame = tkinter.Frame(canvas, bg='white')
        canvas.create_window((0, 0), window=frame, anchor='nw')

        self.fav_listbox = tkinter.Listbox(
            frame, font=self.FONT_NORMAL, fg=self.COLOR_LINK, bg='white',
            selectbackground='#e6f7ff', selectforeground=self.COLOR_LINK,
            justify='left', width=80, height=18, bd=0
        )
        self.fav_listbox.pack(fill='both', expand=True, padx=5, pady=5)

        for idx, item in enumerate(self.favorite_records):
            title = item.get('title', '未知')
            t = item.get('add_time', '')
            api = item.get('api', '默认接口')
            self.fav_listbox.insert(tkinter.END, f"{idx + 1}. {title}")
            self.fav_listbox.insert(tkinter.END, f"    {t} | {api}")
            self.fav_listbox.insert(tkinter.END, "")

        def on_config(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        frame.bind("<Configure>", on_config)

        def wheel(event):
            canvas.yview_scroll(int(-event.delta // 120), 'units')

        canvas.bind_all("<MouseWheel>", wheel)

        # 按钮区
        btn_frame = tkinter.Frame(w, bg=self.COLOR_BG)
        btn_frame.pack(fill='x', pady=10)

        tkinter.Button(btn_frame, text='播放选中影片', command=self.play_favorite,
                       bg=self.COLOR_SECONDARY, fg='white', font=self.FONT_SMALL_BUTTON,
                       width=14, relief='flat').pack(side='left', padx=10)
        tkinter.Button(btn_frame, text='删除选中', command=self.del_favorite,
                       bg=self.COLOR_DELETE, fg='white', font=self.FONT_SMALL_BUTTON,
                       width=10, relief='flat').pack(side='left', padx=5)
        tkinter.Button(btn_frame, text='清空收藏', command=self.clear_favorite,
                       bg=self.COLOR_WARNING, fg='white', font=self.FONT_SMALL_BUTTON,
                       width=10, relief='flat').pack(side='left', padx=5)

        self.fav_window = w

    def play_favorite(self):
        if not self.fav_listbox.curselection():
            tkinter.messagebox.showwarning('提示', '请先选中要播放的影片')
            return
        idx = self.fav_listbox.curselection()[0] // 3
        if idx >= len(self.favorite_records):
            return
        item = self.favorite_records[idx]
        api = self.parse_apis.get(item.get('api', '默认接口'), self.parse_apis['默认接口'])
        self._play_with_vlc(api + item['url'])
        tkinter.messagebox.showinfo('播放', f'正在用 VLC 播放：{item["title"]}')

    def del_favorite(self):
        if not self.fav_listbox.curselection():
            tkinter.messagebox.showwarning('提示', '请先选中')
            return
        idx = self.fav_listbox.curselection()[0] // 3
        if tkinter.messagebox.askyesno('确认', '确定删除该收藏？'):
            self.favorite_records.pop(idx)
            self.save_favorite()
            self.fav_window.destroy()
            self.open_favorite_window()

    def clear_favorite(self):
        if tkinter.messagebox.askyesno('确认', '确定清空所有收藏？不可恢复！'):
            self.favorite_records = []
            self.save_favorite()
            self.fav_window.destroy()
            self.open_favorite_window()

    # ========== 修改：历史记录只选中，不自动播放 ==========
    def play_selected_history(self):
        if not self.history_listbox.curselection():
            tkinter.messagebox.showwarning('提示', '请先选中要播放的历史记录')
            return
        idx = self.history_listbox.curselection()[0]
        if idx >= len(self.history_records):
            return
        r = self.history_records[idx]
        api = self.parse_apis.get(r['api'], self.parse_apis['默认接口'])
        self._play_with_vlc(api + r['url'])
        tkinter.messagebox.showinfo('播放', f'正在用 VLC 播放：{r["title"]}')

    def delete_selected_history(self):
        if not self.history_listbox.curselection():
            tkinter.messagebox.showwarning('提示', '请选中记录')
            return
        if tkinter.messagebox.askyesno('确认', '删除该记录？'):
            self.history_records.pop(self.history_listbox.curselection()[0])
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.history_records, f, ensure_ascii=False, indent=2)
            self.update_history_listbox()

    def clear_all_history(self):
        if tkinter.messagebox.askyesno('确认', '清空所有历史？'):
            self.history_records = []
            self.update_history_listbox()
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)

    def _on_title_focus_in(self, e):
        if self.entry_title.get() == "（可选，留空则自动识别）":
            self.entry_title.delete(0, 'end')
            self.entry_title.config(fg=self.COLOR_TEXT)

    def _on_title_focus_out(self, e):
        if not self.entry_title.get().strip():
            self.entry_title.insert(0, "（可选，留空则自动识别）")
            self.entry_title.config(fg='#999')

    def add_hover(self, widget, c1, c2):
        widget.bind('<Enter>', lambda e: widget.config(bg=c2))
        widget.bind('<Leave>', lambda e: widget.config(bg=c1))

    def _play_with_vlc(self, url):
        """使用本地 VLC 播放器直接播放视频流，不跳转浏览器"""
        try:
            subprocess.Popen([VLC_PATH, url], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            tkinter.messagebox.showwarning('提示', f'启动 VLC 失败：{str(e)}\n请确认 VLC 已正确安装')
            webbrowser.open(url)

    def play_video(self):
        url = self.entry_url.get().strip()
        if not url:
            tkinter.messagebox.showwarning('提示', '请输入网址')
            return
        title = self.entry_title.get().strip()
        if title == "（可选，留空则自动识别）":
            title = ""
        api_name = self.api_var.get()
        api = self.parse_apis[api_name]
        self.save_history(url, api_name, title)
        self.update_history_listbox()
        self._play_with_vlc(api + url)

    def empty(self):
        self.entry_url.delete(0, 'end')
        self.entry_title.delete(0, 'end')
        self.entry_title.insert(0, "（可选，留空则自动识别）")
        self.entry_title.config(fg='#999')

    def create_widgets(self):
        top = tkinter.Frame(self.root, bg=self.COLOR_PRIMARY, height=60)
        top.pack(fill='x')
        tkinter.Label(top, text='VIP视频解析工具', font=self.FONT_TITLE,
                      fg='white', bg=self.COLOR_PRIMARY).place(relx=0.5, rely=0.5, anchor='center')

        main = tkinter.Frame(self.root, bg=self.COLOR_BG)
        main.pack(fill='both', expand=True, padx=20, pady=15)

        # 左侧
        left = tkinter.Frame(main, bg=self.COLOR_FRAME, bd=1, relief='solid')
        left.pack(side='left', fill='both', expand=True, padx=(0, 10), pady=5)
        left.pack_propagate(False)
        left.configure(width=550, height=380)

        tkinter.Label(left, text='目标网址：', font=self.FONT_NORMAL, bg=self.COLOR_FRAME) \
            .place(x=30, y=30, width=80, height=35)
        self.entry_url = tkinter.Entry(left, font=self.FONT_NORMAL, bg='white', bd=0)
        self.entry_url.place(x=120, y=30, width=320, height=35)
        btn_clear = tkinter.Button(left, text='清空', command=self.empty, bg=self.COLOR_WARNING, fg='white')
        btn_clear.place(x=450, y=30, width=70, height=35)
        self.add_hover(btn_clear, self.COLOR_WARNING, '#ff7875')

        tkinter.Label(left, text='影片名称：', font=self.FONT_NORMAL, bg=self.COLOR_FRAME) \
            .place(x=30, y=80, width=80, height=35)
        self.entry_title = tkinter.Entry(left, font=self.FONT_NORMAL, bg='white', fg='#999', bd=0)
        self.entry_title.place(x=120, y=80, width=320, height=35)
        self.entry_title.insert(0, "（可选，留空则自动识别）")
        self.entry_title.bind('<FocusIn>', self._on_title_focus_in)
        self.entry_title.bind('<FocusOut>', self._on_title_focus_out)

        tkinter.Label(left, text='解析接口：', font=self.FONT_NORMAL, bg=self.COLOR_FRAME) \
            .place(x=30, y=130, width=80, height=35)
        self.api_var = tkinter.StringVar(value='默认接口')
        cb = tkinter.ttk.Combobox(left, textvariable=self.api_var, values=list(self.parse_apis.keys()),
                                  state='readonly')
        cb.place(x=120, y=130, width=160, height=35)

        btn_fav_add = tkinter.Button(left, text='添加到收藏', command=self.add_to_favorite,
                                     bg=self.COLOR_FAVORITE, fg='white', font=self.FONT_SMALL_BUTTON)
        btn_fav_add.place(x=120, y=180, width=150, height=40)
        self.add_hover(btn_fav_add, self.COLOR_FAVORITE, '#ffc53d')

        btn_fav_open = tkinter.Button(left, text='我的收藏库', command=self.open_favorite_window,
                                      bg='#722ed1', fg='white', font=self.FONT_SMALL_BUTTON)
        btn_fav_open.place(x=280, y=180, width=150, height=40)
        self.add_hover(btn_fav_open, '#722ed1', '#8a41e6')

        btn_play = tkinter.Button(left, text='播放视频', command=self.play_video,
                                  bg=self.COLOR_SECONDARY, fg='white', font=self.FONT_BUTTON)
        btn_play.place(relx=0.5, rely=0.8, anchor='center', width=160, height=50)
        self.add_hover(btn_play, self.COLOR_SECONDARY, '#73d13d')

        # 右侧
        right = tkinter.Frame(main, bg=self.COLOR_FRAME, bd=1, relief='solid')
        right.pack(side='right', fill='both', expand=True, padx=(10, 0), pady=5)
        right.pack_propagate(False)
        right.configure(width=380, height=380)

        tkinter.Label(right, text='历史解析记录', font=self.FONT_NORMAL, bg=self.COLOR_FRAME) \
            .place(x=20, y=10)

        self.history_listbox = tkinter.Listbox(right, font=self.FONT_SMALL, bg=self.COLOR_HISTORY,
                                               fg=self.COLOR_LINK, selectbackground='#e6f7ff',
                                               selectforeground=self.COLOR_LINK)
        self.history_listbox.place(x=20, y=50, width=340, height=220)
        # 移除自动播放的绑定
        # self.history_listbox.bind('<<ListboxSelect>>', self.on_history_click)
        sb = tkinter.Scrollbar(right, command=self.history_listbox.yview)
        sb.place(x=360, y=50, height=220)
        self.history_listbox.config(yscrollcommand=sb.set)

        # ========== 新增：历史记录播放按钮 ==========
        btn_play_hist = tkinter.Button(right, text='播放选中', command=self.play_selected_history,
                                       bg=self.COLOR_SECONDARY, fg='white')
        btn_play_hist.place(x=30, y=280, width=100, height=35)
        self.add_hover(btn_play_hist, self.COLOR_SECONDARY, '#73d13d')

        btn_del_sel = tkinter.Button(right, text='删除选中', command=self.delete_selected_history,
                                     bg=self.COLOR_DELETE, fg='white')
        btn_del_sel.place(x=140, y=280, width=100, height=35)
        self.add_hover(btn_del_sel, self.COLOR_DELETE, '#ff7d4d')

        btn_clear_hist = tkinter.Button(right, text='清空所有', command=self.clear_all_history,
                                        bg='#888', fg='white')
        btn_clear_hist.place(x=250, y=280, width=100, height=35)
        self.add_hover(btn_clear_hist, '#888', '#666')

        self.update_history_listbox()

    def update_history_listbox(self):
        self.history_listbox.delete(0, tkinter.END)
        for r in self.history_records:
            self.history_listbox.insert(tkinter.END, f"{r['title']}")


def install_dependency():
    try:
        import requests
    except ImportError:
        tkinter.messagebox.showinfo('提示', '正在安装依赖 requests')
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])


if __name__ == '__main__':
    install_dependency()
    root = tkinter.Tk()
    app = VIPVideoApp(root)
    root.mainloop()