"""Local desktop-window and input support for the anime companion."""
import ctypes
from ctypes import wintypes
import json
import math
from pathlib import Path
import queue
import subprocess
import threading
import time
import tkinter as tk

USER = ctypes.windll.user32
try:
    USER.SetProcessDPIAware()
except Exception:
    pass
USER.GetForegroundWindow.restype = wintypes.HWND
USER.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
USER.GetAncestor.restype = wintypes.HWND
USER.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
USER.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
KEY = '#ff00ff'
SETTINGS = Path(__file__).with_name('settings.json')


def desktop_bounds():
    return tuple(USER.GetSystemMetrics(i) for i in (76, 77, 78, 79))


def clamp_position(x, y):
    left, top, width, height = desktop_bounds()
    return max(left, min(x, left + width - 220)), max(top, min(y, top + height - 230))


class Pet:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Pip 桌面宠物')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True, '-transparentcolor', KEY)
        self.root.configure(bg=KEY)
        self.canvas = tk.Canvas(self.root, width=220, height=230, bg=KEY, highlightthickness=0)
        self.canvas.pack()
        self.follow = False
        self.reactions = True
        self.dragging = False
        self.drag_offset = None
        self.state = 'idle'
        self.until = 0
        self.message = '你好，我是 Pip！右键打开菜单'
        self.message_until = time.monotonic() + 8
        self.last_click = False
        self.last_key = False
        self.last_hover = 0
        self.last_query = 0
        self.query_busy = False
        self.results = queue.Queue()
        self.started = time.monotonic()
        self.x, self.y = clamp_position(self.root.winfo_screenwidth() - 260, self.root.winfo_screenheight() - 300)
        try:
            data = json.loads(SETTINGS.read_text(encoding='utf-8'))
            self.x, self.y = clamp_position(int(data['x']), int(data['y']))
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self.move(self.x, self.y)
        self.menu = tk.Menu(self.root, tearoff=False)
        self.menu.add_command(label='附在光标旁 / 停止跟随', command=self.toggle_follow)
        self.menu.add_command(label='摸摸 Pip', command=lambda: self.react('happy', '嘿嘿，再摸一下！', 2))
        self.menu.add_command(label='跳一跳', command=lambda: self.react('jump', '出发！', 1.5))
        self.menu.add_command(label='暂停 / 恢复操作反应', command=self.toggle_reactions)
        self.menu.add_separator()
        self.menu.add_command(label='退出', command=self.close)
        self.canvas.bind('<ButtonPress-1>', self.drag_start)
        self.canvas.bind('<B1-Motion>', self.drag_move)
        self.canvas.bind('<ButtonRelease-1>', self.drag_end)
        self.canvas.bind('<Button-3>', self.popup)
        self.root.bind('<Escape>', lambda e: self.stop_follow())
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.update_idletasks()
        self.hwnd = USER.GetAncestor(self.root.winfo_id(), 2)
        # A tool window stays out of Alt-Tab; do not activate it on ordinary clicks.
        style = USER.GetWindowLongW(self.hwnd, -20)
        USER.SetWindowLongW(self.hwnd, -20, style | 0x80 | 0x08000000)
        self.tick()

    def move(self, x, y):
        self.x, self.y = clamp_position(int(x), int(y))
        self.root.geometry(f'220x230{self.x:+d}{self.y:+d}')

    def react(self, state, message='', duration=1.0):
        self.state, self.until = state, time.monotonic() + duration
        if message:
            self.message, self.message_until = message, time.monotonic() + max(duration, 2.2)

    def toggle_follow(self):
        self.follow = not self.follow
        self.react('happy', '跟着你啦！右键我可停止' if self.follow else '我在这里陪你', 2)

    def stop_follow(self):
        self.follow = False

    def toggle_reactions(self):
        self.reactions = not self.reactions
        self.react('idle', '操作反应已开启' if self.reactions else '操作反应已暂停', 2)

    def popup(self, event):
        self.stop_follow()
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def drag_start(self, event):
        self.follow = False
        self.drag_offset = (event.x_root - self.x, event.y_root - self.y)
        self.dragging = True
        self.react('happy', '被你抓住啦', 1)

    def drag_move(self, event):
        if self.drag_offset:
            self.move(event.x_root - self.drag_offset[0], event.y_root - self.drag_offset[1])

    def drag_end(self, event):
        self.dragging = False
        self.drag_offset = None
        self.react('jump', '', .65)
        self.save()

    def save(self):
        try:
            SETTINGS.write_text(json.dumps({'x': self.x, 'y': self.y}), encoding='utf-8')
        except OSError:
            pass

    def close(self):
        self.save()
        self.root.destroy()

    def query_file(self, hwnd):
        if self.query_busy:
            return
        self.query_busy = True
        def worker():
            try:
                # Read only selected item names from the clicked Explorer window.
                script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                          "$s=New-Object -ComObject Shell.Application; "
                          f"foreach($w in $s.Windows()) {{ if([long]$w.HWND -eq {int(hwnd)}) {{ "
                          "$a=@($w.Document.SelectedItems()); if($a.Count -gt 0) { "
                          "$a[0].Name }; break } }")
                time.sleep(.25)
                result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                        capture_output=True, timeout=4, creationflags=0x08000000)
                name = result.stdout.decode('utf-8-sig', errors='replace').strip()
                if name:
                    self.results.put((time.monotonic(), name[:45]))
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                self.query_busy = False
        threading.Thread(target=worker, daemon=True).start()

    def tick(self):
        now = time.monotonic()
        point = wintypes.POINT()
        USER.GetCursorPos(ctypes.byref(point))
        down = bool(USER.GetAsyncKeyState(1) & 0x8000)
        # Holding Ctrl+Shift stops follow without depending on window focus.
        if USER.GetAsyncKeyState(0x11) & 0x8000 and USER.GetAsyncKeyState(0x10) & 0x8000:
            self.stop_follow()
        if self.follow and not self.dragging:
            self.move(self.x + (point.x + 24 - self.x) * .2, self.y + (point.y + 22 - self.y) * .2)
        inside = self.x <= point.x < self.x + 220 and self.y <= point.y < self.y + 230
        if self.reactions and inside and not self.follow and now - self.last_hover > 2.5:
            self.react('happy', '', 1)
            self.last_hover = now
        if down and not self.last_click and not inside and self.reactions:
            self.react('look', '', .65)
            hwnd = USER.GetForegroundWindow()
            cls = ctypes.create_unicode_buffer(256)
            USER.GetClassNameW(wintypes.HWND(hwnd), cls, 256)
            if cls.value in ('CabinetWClass', 'ExploreWClass') and now - self.last_query > 1.2:
                self.last_query = now
                self.react('look', '看看你选了什么…', 1)
                self.query_file(hwnd)
            elif cls.value in ('Progman', 'WorkerW'):
                self.react('jump', '桌面上有什么新发现？', .8)
        enter = bool(USER.GetAsyncKeyState(0x0D) & 0x8000)
        if enter and not self.last_key and self.reactions:
            self.react('jump', '收到，出发！', .85)
        self.last_click, self.last_key = down, enter
        while not self.results.empty():
            timestamp, name = self.results.get_nowait()
            if self.reactions and now - timestamp < 2:
                self.react('look', f'选中了：{name}', 2.5)
        if now > self.until:
            self.state = 'idle'
        self.draw(now, point)
        self.root.after(33, self.tick)

    def draw(self, now, point):
        c = self.canvas
        c.delete('all')
        t = now - self.started
        bounce = math.sin(t * 2.4) * 2
        if self.state == 'jump':
            bounce -= abs(math.sin(t * 9)) * 25
        elif self.state == 'happy':
            bounce += math.sin(t * 14) * 3
        y = 88 + bounce
        teal, dark, cream = '#37A89E', '#21565E', '#FFF1D2'
        # Vector character animation, deliberately independent of ChatGPT Pets sprites.
        sway = math.sin(t * (9 if self.state == 'happy' else 3)) * 10
        c.create_oval(140, y+38+sway, 203, y+100+sway, fill=teal, outline=dark, width=3)
        c.create_oval(175, y+40+sway, 204, y+70+sway, fill=cream, outline='')
        c.create_oval(65, y+51, 158, y+119, fill=teal, outline=dark, width=3)
        c.create_oval(85, y+68, 137, y+116, fill=cream, outline='')
        c.create_oval(66, y+105, 103, y+125, fill=dark, outline='')
        c.create_oval(124, y+105, 161, y+125, fill=dark, outline='')
        c.create_polygon(54,y+26, 57,y-31, 90,y+1, fill=teal, outline=dark, width=3)
        c.create_polygon(131,y+1, 167,y-31, 169,y+30, fill=teal, outline=dark, width=3)
        c.create_polygon(62,y-16, 66,y+16, 82,y+3, fill='#F5C0AD', outline='')
        c.create_polygon(142,y+3, 160,y-16, 160,y+18, fill='#F5C0AD', outline='')
        c.create_oval(49,y-1, 174,y+86, fill=teal, outline=dark, width=3)
        c.create_polygon(52,y+38, 109,y+62, 170,y+38, 154,y+73, 112,y+86, 70,y+71, fill=cream, smooth=True, outline='')
        blink = t % 4.7 < .15
        dx = max(-4, min(4, (point.x - (self.x+110))/80))
        dy = max(-3, min(3, (point.y - (self.y+y+35))/100))
        for ex in (83, 139):
            if blink or self.state == 'happy':
                c.create_arc(ex-9,y+24, ex+9,y+40, start=10, extent=160, style='arc', outline=dark, width=3)
            else:
                c.create_oval(ex-10,y+20, ex+10,y+43, fill=cream, outline='')
                c.create_oval(ex-5+dx,y+25+dy, ex+4+dx,y+38+dy, fill=dark, outline='')
                c.create_oval(ex-3+dx,y+26+dy, ex+dx,y+29+dy, fill='white', outline='')
        c.create_polygon(104,y+49, 119,y+49, 112,y+57, fill=dark, smooth=True)
        c.create_line(112,y+56,112,y+62,103,y+66, fill=dark,width=2,smooth=True)
        c.create_line(112,y+62,121,y+66, fill=dark,width=2,smooth=True)
        if self.state == 'happy':
            c.create_oval(145,y+63+math.sin(t*15)*6,168,y+87+math.sin(t*15)*6,fill=teal,outline=dark,width=2)
        if now < self.message_until:
            c.create_rectangle(8,4,212,49,fill='#FFF9EB',outline=dark,width=2)
            c.create_text(110,26,text=self.message,width=190,font=('Microsoft YaHei UI',9),fill=dark)



