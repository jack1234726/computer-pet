"""Reference-based chibi skin for the local Pip desktop companion."""
import ctypes
from ctypes import wintypes
import hashlib
import math
from pathlib import Path
import time
from PIL import Image, ImageTk
import pet_core as core
from wardrobe import OUTFITS, get_outfit, save_outfit, WardrobeDialog
from adventure_audio import Audio

ASSETS = Path(__file__).with_name('assets')


def desktop_identity():
    """Keep sandbox test pets independent of the user's interactive desktop."""
    user=ctypes.windll.user32
    user.GetThreadDesktop.argtypes=[wintypes.DWORD]
    user.GetThreadDesktop.restype=wintypes.HANDLE
    user.GetUserObjectInformationW.argtypes=[wintypes.HANDLE,ctypes.c_int,wintypes.LPVOID,
                                           wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    handle=user.GetThreadDesktop(ctypes.windll.kernel32.GetCurrentThreadId())
    name=ctypes.create_unicode_buffer(512)
    needed=wintypes.DWORD()
    if not user.GetUserObjectInformationW(handle,2,name,ctypes.sizeof(name),ctypes.byref(needed)):
        raise ctypes.WinError()
    return hashlib.sha256(name.value.encode('utf-8')).hexdigest()[:16]


DESKTOP_ID=desktop_identity()
WAKE_REQUEST = Path(__file__).with_name('pet-wake-'+DESKTOP_ID+'.request')
core.SETTINGS = Path(__file__).with_name('anime-settings.json')


class AnimePet(core.Pet):
    def __init__(self):
        self.sprites = []
        self.last_activity = time.monotonic()
        self.reaction_started = self.last_activity
        self.previous_cursor = None
        self.game = None
        self.wardrobe = None
        self.outfit = get_outfit()
        self.next_outfit_check = 0.
        self.wake_stamp = WAKE_REQUEST.stat().st_mtime_ns if WAKE_REQUEST.exists() else 0
        self.volume_dialog = None
        self.audio = None
        self.desktop_voice_ready = False
        self.idle_sleeping = False
        self.cursor_inside = False
        self.drag_origin = None
        self.drag_spoken = False
        super().__init__()
        self.audio = Audio()
        self.root.title('Q版少女 · 桌面宠物')
        self.menu.entryconfigure(1, label='摸摸头', command=self.pet_touch)
        self.menu.insert_command(3, label='挥挥手', command=lambda: self.react('wave', '你好呀！', 2.5))
        self.menu.insert_command(4, label='打个盹', command=lambda: self.react('sleep', '休息一下下…', 10))
        self.menu.insert_command(0, label='开始星屿小冒险（双击）', command=self.open_game)
        self.menu.insert_command(1, label='换装 · 打开小衣橱', command=self.open_wardrobe)
        self.menu.insert_command(2, label='人物配音：开（点击关闭）', command=self.toggle_voice)
        self.menu.insert_command(3, label='音量调节…', command=self.open_volume)
        self.canvas.bind('<Double-Button-1>', self.open_game)
        self.react('wave', '双击我，一起去冒险！', 3)
        self.message_until = time.monotonic() + 6
        self.audio.speak('welcome')
        self.desktop_voice_ready=True
        self.root.after(6500,self.invite_adventure)

    def invite_adventure(self):
        if (self.game is None and not self.follow and not self.dragging
                and time.monotonic()-self.last_activity>=4):
            self.react('wave','双击我，一起去冒险！',4)

    def stop_follow(self):
        was_following=self.follow
        super().stop_follow()
        if was_following:
            self.react('happy','我在这里陪你',3)

    def open_volume(self):
        self.follow=False
        if self.volume_dialog is not None and not self.volume_dialog.closed:
            self.volume_dialog.window.lift()
            return
        from volume_dialog import VolumeDialog
        self.volume_dialog=VolumeDialog(self.root,self.audio)

    def toggle_voice(self):
        self.audio.toggle_voice()
        label='人物配音：关（点击开启）' if self.audio.voice_muted else '人物配音：开（点击关闭）'
        self.menu.entryconfigure(2,label=label)

    def pet_touch(self):
        self.react('happy','嘿嘿～',2)
        if self.audio:
            self.audio.speak('touch')

    def drag_start(self,event):
        self.drag_origin=(event.x_root,event.y_root)
        self.drag_spoken=False
        super().drag_start(event)

    def drag_move(self,event):
        super().drag_move(event)
        if self.drag_origin and not self.drag_spoken:
            dx=event.x_root-self.drag_origin[0]
            dy=event.y_root-self.drag_origin[1]
            if dx*dx+dy*dy>=64:
                self.drag_spoken=True
                if self.audio:
                    self.audio.speak('drag')

    def close(self):
        self.desktop_voice_ready=False
        if self.volume_dialog is not None and not self.volume_dialog.closed:
            self.volume_dialog.close()
        if self.audio:
            self.audio.close()
        if self.game is not None and not self.game.closed:
            self.game.close()
        super().close()

    def open_game(self,event=None):
        if self.volume_dialog is not None and not self.volume_dialog.closed:
            self.volume_dialog.close()
        if self.wardrobe is not None and not self.wardrobe.closed:
            self.wardrobe.close()
        if self.game is not None and not self.game.closed:
            self.game.window.lift()
            return 'break'
        from adventure_game import Adventure
        self.audio.stop()
        self.follow = False
        self.dragging = False
        self.drag_offset = None
        self.game = Adventure(self.root,self.game_closed)
        self.root.withdraw()
        return 'break'

    def game_closed(self):
        self.game = None
        chosen=get_outfit()
        if chosen!=self.outfit:
            self.outfit=chosen
            self.load_sprites()
        self.root.deiconify()
        self.react('happy','回来啦～ 双击可以再冒险',3)

    def tick(self):
        try:
            stamp=WAKE_REQUEST.stat().st_mtime_ns
        except OSError:
            stamp=0
        if stamp and stamp!=self.wake_stamp:
            self.wake_stamp=stamp
            if self.game is not None and not self.game.closed:
                self.game.window.deiconify()
                self.game.window.lift()
            else:
                self.follow=False
                self.dragging=False
                self.drag_offset=None
                self.move((self.root.winfo_screenwidth()-220)//2,
                          (self.root.winfo_screenheight()-230)//2)
                self.root.deiconify()
                self.root.lift()
                self.react('wave','我在这里呀！右键打开菜单',5)
        if self.audio:
            self.audio.collect()
        if self.game is not None and not self.game.closed:
            self.root.after(160,self.tick)
            return
        now=time.monotonic()
        if now>=self.next_outfit_check:
            self.next_outfit_check=now+1
            chosen=get_outfit()
            if chosen!=self.outfit:
                self.outfit=chosen
                self.load_sprites()
                if self.wardrobe is not None and not self.wardrobe.closed:
                    self.wardrobe.current=chosen
                    self.wardrobe.draw()
        super().tick()

    def load_sprites(self):
        sheet = Image.open(OUTFITS[self.outfit]['pet']).convert('RGBA')
        sprites=[]
        cell_w, cell_h = sheet.width // 3, sheet.height // 2
        for index in range(6):
            col, row = index % 3, index // 3
            cell = sheet.crop((col*cell_w, row*cell_h, (col+1)*cell_w, (row+1)*cell_h))
            # Keep a common scale and grid registration for all six poses.
            cell = cell.resize((172,172), Image.Resampling.LANCZOS)
            # Tk color-key windows cannot blend partial alpha with the desktop.
            # Binary edge coverage prevents a magenta fringe; source RGBA is preserved.
            cell.putalpha(cell.getchannel('A').point(lambda a: 255 if a >= 128 else 0))
            sprites.append(ImageTk.PhotoImage(cell, master=self.root))
        self.sprites=sprites

    def change_outfit(self,key):
        previous=self.outfit
        self.outfit=key
        try:
            self.load_sprites()
            save_outfit(key)
        except (OSError,ValueError):
            self.outfit=previous
            self.load_sprites()
            raise
        self.react('happy','换上'+OUTFITS[key]['name']+'啦～',2.5)
        if key!=previous and key=='floral' and self.audio:
            self.audio.speak('outfit')

    def open_wardrobe(self):
        self.follow=False
        self.dragging=False
        self.drag_offset=None
        if self.wardrobe is not None and not self.wardrobe.closed:
            self.wardrobe.window.lift()
            return
        self.wardrobe=WardrobeDialog(self.root,self.change_outfit)

    def react(self, state, message='', duration=1.0):
        self.reaction_started = time.monotonic()
        self.last_activity = self.reaction_started
        super().react(state, message, duration)
        if self.audio and self.desktop_voice_ready and self.game is None:
            event={
                '你好呀！':'wave', '休息一下下…':'sleep',
                '双击我，一起去冒险！':'invite',
                '回来啦～ 双击可以再冒险':'return',
                '我在这里呀！右键打开菜单':'recall',
                '跟着你啦！右键我可停止':'follow',
                '我在这里陪你':'stay', '出发！':'hop',
                '看看你选了什么…':'file',
                '桌面上有什么新发现？':'desktop',
                '收到，出发！':'enter',
                '换上晴空水手服啦～':'sailor',
            }.get(message)
            if event:
                self.audio.speak(event)

    def draw(self, now, point):
        if not self.sprites:
            self.load_sprites()
        cursor = (point.x, point.y)
        inside=self.x<=point.x<self.x+220 and self.y<=point.y<self.y+230
        if inside and not self.cursor_inside and self.reactions and not self.follow and not self.dragging:
            if self.audio:
                self.audio.speak('touch')
        self.cursor_inside=inside
        if cursor != self.previous_cursor:
            self.last_activity = now
        self.previous_cursor = cursor
        idle_sleeping=not self.follow and not self.dragging and now-self.last_activity>50
        if idle_sleeping and not self.idle_sleeping and self.audio:
            self.audio.speak('sleep')
        self.idle_sleeping=idle_sleeping
        elapsed = now - self.reaction_started
        t = now - self.started
        pose = 1 if t % 4.5 < .17 else 0
        x, y = 110, 143 + math.sin(t*2.3)*1.3
        if self.state == 'happy':
            pose = 2
            x += math.sin(elapsed*10)*2
            y -= abs(math.sin(elapsed*7))*3
        elif self.state == 'wave':
            pose = 3 if elapsed % .8 < .65 else 0
            x += math.sin(elapsed*7)*1.5
        elif self.state == 'look':
            pose = 4
        elif self.state == 'jump':
            pose = 3
            duration = max(.1, self.until - self.reaction_started)
            y -= 23 * math.sin(math.pi * min(1, elapsed / duration))
        elif self.state == 'sleep' or (not self.follow and now-self.last_activity > 50):
            pose = 5
            y += math.sin(t*1.4)*2
        elif self.follow:
            pose = 3 if t % 2 < .3 else 0
            y += math.sin(t*9)*2
        if self.dragging:
            pose = 4
        c = self.canvas
        c.delete('all')
        c.create_image(round(x), round(y), image=self.sprites[pose])
        self.current_pose = pose
        subtitle=self.audio.subtitle if self.audio else ''
        if subtitle and self.message.startswith('选中了：') and now<self.message_until:
            subtitle=self.message
        if subtitle or now < self.message_until:
            c.create_rectangle(9,5,211,49,fill='#FFF7F2',outline='#BB9292',width=1)
            c.create_polygon(100,49,109,56,116,49,fill='#FFF7F2',outline='')
            c.create_text(110,27,text=subtitle or self.message,width=188,font=('Microsoft YaHei UI',9),fill='#63484D')


if __name__ == '__main__':
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel.CreateMutexW(None, False, 'Local\\CodexAnimeStandalonePet-'+DESKTOP_ID)
    if kernel.GetLastError() == 183:
        WAKE_REQUEST.write_text(str(time.time_ns()),encoding='ascii')
        if mutex:
            kernel.CloseHandle(ctypes.c_void_p(mutex))
    else:
        try:
            AnimePet().root.mainloop()
        finally:
            if mutex:
                kernel.CloseHandle(ctypes.c_void_p(mutex))
