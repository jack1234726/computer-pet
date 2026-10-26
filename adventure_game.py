"""Star Island: a small illustrated platformer launched by the desktop pet."""
import json
import ctypes
import math
from pathlib import Path
import time
import tkinter as tk
from PIL import Image, ImageTk, ImageOps
from adventure_model import World, WORLD_WIDTH
from adventure_audio import Audio
from wardrobe import OUTFITS, get_outfit, save_outfit, WardrobeDialog
from game_viewport import GameCanvas

BASE = Path(__file__).parent
W,H = 1060,640
INK = '#35515B'
FONT = 'Microsoft YaHei UI'
try:
    ctypes.windll.user32.SetProcessDPIAware()
except (AttributeError,OSError):
    pass


class Adventure:
    def __init__(self,parent=None,on_close=None):
        self.window = tk.Toplevel(parent) if parent else tk.Tk()
        self.window.title('星屿小冒险 · 和她一起收集星光')
        self.window.resizable(True,True)
        self.window.minsize(640,386)
        self.fullscreen=False
        self.windowed_geometry=f'{W}x{H}'
        self.windowed_state='normal'
        self.window.geometry(f'{W}x{H}')
        self.window.configure(bg='#EBF6E8')
        self.canvas = GameCanvas(self.window,W,H,width=W,height=H,highlightthickness=0,bg='#29434A')
        self.canvas.pack(fill='both',expand=True)
        self.on_close = on_close
        self.world = World()
        self.keys = set()
        self.camera = 0
        self.mode = 'title'
        self.last = time.perf_counter()
        self.closed = False
        self.after_id = None
        self.best = 0
        self.saved = False
        self.buttons = []
        self.volume_dialog = None
        self.audio = Audio()
        self.outfit = get_outfit()
        self.wardrobe = None
        self.next_outfit_check = 0.
        try:
            self.best = int(json.loads((BASE/'adventure-save.json').read_text(encoding='utf-8')).get('best_stars',0))
        except (OSError,ValueError,TypeError):
            pass
        self.load_art()
        self.window.bind('<KeyPress>',self.key_down)
        self.window.bind('<KeyRelease>',self.key_up)
        self.window.bind('<FocusOut>',self.focus_out)
        self.canvas.bind('<Button-1>',self.click)
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        self.window.after(120,self.canvas.focus_set)
        self.window.lift()
        self.loop()

    def load_art(self):
        self.canvas.scaled_images.clear()
        self.frames = {}
        outfit=OUTFITS[self.outfit]
        sheet = Image.open(outfit['game']).convert('RGBA')
        split=outfit['split']
        cell_width=sheet.width//4
        for idx in range(8):
            col,row = idx%4,idx//4
            image = sheet.crop((col*cell_width,0 if row==0 else split,(col+1)*cell_width,split if row==0 else sheet.height))
            image = image.resize((64,round(image.height/6)),Image.Resampling.LANCZOS)
            for direction in (1,-1):
                self.frames[idx,direction] = ImageTk.PhotoImage(image if direction==1 else ImageOps.mirror(image),master=self.window)
        poses = Image.open(outfit['pet']).convert('RGBA')
        idle = poses.crop((0,0,512,512))
        blink = poses.crop((512,0,1024,512))
        for name,img in [('idle',idle),('blink',blink)]:
            for direction in (1,-1):
                scaled = img.resize((86,86),Image.Resampling.LANCZOS)
                self.frames[name,direction] = ImageTk.PhotoImage(scaled if direction==1 else ImageOps.mirror(scaled),master=self.window)
        self.portrait = ImageTk.PhotoImage(idle.resize((355,355),Image.Resampling.LANCZOS),master=self.window)

    def change_outfit(self,key):
        previous=self.outfit
        self.outfit=key
        try:
            self.load_art()
            save_outfit(key)
        except (OSError,ValueError):
            self.outfit=previous
            self.load_art()
            raise
        if key!=previous and key=='floral':
            self.audio.speak('outfit')
        self.render()

    def open_wardrobe(self):
        if self.wardrobe is not None and not self.wardrobe.closed:
            self.wardrobe.window.lift()
            return
        if self.mode=='play':
            self.mode='pause'
        self.keys.clear()
        self.audio.stop_speech()
        self.audio.update(False)
        self.wardrobe=WardrobeDialog(self.window,self.change_outfit,self.wardrobe_closed)

    def wardrobe_closed(self):
        self.wardrobe=None
        if not self.closed:
            self.window.lift()
            self.canvas.focus_set()

    def start(self):
        self.audio.stop()
        self.world = World()
        self.camera = 0
        self.saved = False
        self.mode = 'play'
        self.keys.clear()
        self.canvas.focus_set()
        self.audio.speech_recent.clear()
        self.audio.speak('start')

    def toggle_fullscreen(self):
        self.keys.intersection_update({'f11','f10','escape'})
        if not self.fullscreen:
            self.windowed_geometry=self.window.geometry()
            self.windowed_state=self.window.state()
            self.fullscreen=True
            self.window.attributes('-fullscreen',True)
        else:
            self.fullscreen=False
            self.window.attributes('-fullscreen',False)
            self.window.state('normal')
            self.window.geometry(self.windowed_geometry)
            if self.windowed_state=='zoomed':
                self.window.state('zoomed')
        self.canvas.focus_set()

    def small_window(self):
        if self.fullscreen:
            self.toggle_fullscreen()
        self.window.state('normal')
        self.window.geometry('848x512')
        self.keys.intersection_update({'f11','f10','escape'})
        self.canvas.focus_set()

    def open_volume(self):
        if self.volume_dialog is not None and not self.volume_dialog.closed:
            self.volume_dialog.window.lift()
            return
        from volume_dialog import VolumeDialog
        if self.mode=="play":
            self.mode="pause"
        self.keys.clear()
        self.audio.update(False)
        self.volume_dialog=VolumeDialog(self.window,self.audio)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.volume_dialog is not None and not self.volume_dialog.closed:
            self.volume_dialog.close()
        if self.after_id:
            self.window.after_cancel(self.after_id)
        self.audio.close()
        self.window.destroy()
        if self.on_close:
            self.on_close()

    def focus_out(self,event):
        self.window.after_idle(self.check_focus)

    def check_focus(self):
        if self.closed:
            return
        focused = self.window.focus_displayof()
        if focused is None or focused.winfo_toplevel() != self.window:
            self.keys.clear()
            if self.mode=='play':
                self.mode = 'pause'
                self.audio.stop_speech()

    def key_down(self,event):
        key = event.keysym.lower()
        new = key not in self.keys
        self.keys.add(key)
        if not new:
            return
        if key=='f11':
            self.toggle_fullscreen()
            return
        if key=='f10':
            self.small_window()
            return
        if key=='o':
            self.open_volume()
            return
        if key=='m':
            self.audio.toggle()
            return
        if key=='v':
            self.audio.toggle_voice()
            return
        if key=='c':
            self.open_wardrobe()
            return
        if key=='escape':
            if self.fullscreen:
                self.toggle_fullscreen()
                return
            if self.mode=='play':
                self.mode='pause'
                self.audio.stop_speech()
            elif self.mode=='pause':
                self.mode='play'
            else:
                self.close()
            self.keys.clear()
            return
        if self.mode in ('title','win'):
            if key in ('return','space'):
                self.start()
            return
        if self.mode=='pause':
            if key=='return':
                self.mode='play'
            return
        if key in ('space','w','up'):
            self.world.jump()
        elif key in ('shift_l','shift_r','l'):
            self.world.dash()
        elif key=='k':
            self.world.burst()
        elif key=='r':
            self.world.respawn()

    def key_up(self,event):
        self.keys.discard(event.keysym.lower())

    def click(self,event):
        point=self.canvas.logical_point(event.x,event.y)
        if point is None:
            return
        x,y=point
        for x1,y1,x2,y2,callback in self.buttons:
            if x1<=x<=x2 and y1<=y<=y2:
                callback()
                break
        if not self.closed:
            self.canvas.focus_set()

    def loop(self):
        if self.closed:
            return
        now = time.perf_counter()
        dt = min(now-self.last,.05)
        self.last = now
        if now>=self.next_outfit_check:
            self.next_outfit_check=now+1
            chosen=get_outfit()
            if chosen!=self.outfit:
                self.outfit=chosen
                self.load_art()
                if self.wardrobe is not None and not self.wardrobe.closed:
                    self.wardrobe.current=chosen
                    self.wardrobe.draw()
        if self.mode=='play':
            axis = int(bool(self.keys & {'d','right'}))-int(bool(self.keys & {'a','left'}))
            self.world.step(dt,axis,'j' in self.keys)
            target = max(0,min(WORLD_WIDTH-W,self.world.x-W*.35))
            self.camera += (target-self.camera)*min(1,dt*8)
            if self.world.won:
                self.mode='win'
                self.save_result()
        while self.world.sounds:
            event=self.world.sounds.popleft()
            if self.mode in ('play','win'):
                self.audio.play(event)
                self.audio.speak(event)
        self.audio.update(self.mode=='play')
        self.render()
        self.after_id = self.window.after(16,self.loop)

    def save_result(self):
        if self.saved:
            return
        self.saved = True
        self.best = max(self.best,self.world.stars)
        try:
            (BASE/'adventure-save.json').write_text(json.dumps({'best_stars':self.best},ensure_ascii=False),encoding='utf-8')
        except OSError:
            pass

    def text(self,x,y,text,size=12,color=INK,anchor='center',bold=False,**kwargs):
        kwargs.pop('spacing',None)
        return self.canvas.create_text(x,y,text=text,font=(FONT,-round(size*1.35),'bold' if bold else 'normal'),fill=color,anchor=anchor,**kwargs)

    def roundbox(self,x1,y1,x2,y2,fill,outline='',r=18):
        return self.canvas.create_polygon(x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,
                                          x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1,fill=fill,outline=outline,smooth=True)

    def star(self,x,y,r=10,color='#FFCD66',outline='#E4A84D'):
        pts=[]
        for i in range(10):
            a=-math.pi/2+i*math.pi/5
            radius=r if i%2==0 else r*.46
            pts.extend((x+math.cos(a)*radius,y+math.sin(a)*radius))
        self.canvas.create_polygon(pts,fill=color,outline=outline,width=1)

    def cloud(self,x,y,scale=1):
        c=self.canvas
        for dx,dy,rx,ry in [(-30,3,32,16),(0,-7,35,24),(35,4,32,16)]:
            c.create_oval(x+(dx-rx)*scale,y+(dy-ry)*scale,x+(dx+rx)*scale,y+(dy+ry)*scale,fill='#F7FCF1',outline='')

    def background(self):
        c=self.canvas
        cam=self.camera
        # Painted-looking layers are native vector scenery, with parallax scrolling.
        for y in range(0,540,18):
            f=y/540
            a=(172,222,232); b=(239,247,210)
            color='#%02x%02x%02x'%tuple(round(a[i]*(1-f)+b[i]*f) for i in range(3))
            c.create_rectangle(0,y,W,y+19,fill=color,outline='')
        c.create_oval(795,64,889,158,fill='#FFF3BC',outline='')
        c.create_oval(806,75,878,147,fill='#FFF9D7',outline='')
        for i in range(-1,7):
            self.cloud(i*245-(cam*.12)%245,115+math.sin(i*2.2)*35,.8+(i%2)*.2)
        for i in range(-1,7):
            x=i*300-(cam*.2)%300
            c.create_polygon(x-120,460,x+50,220+(i%3)*33,x+230,460,fill='#AFD6C7',smooth=True,outline='')
            c.create_polygon(x+5,300+(i%3)*33,x+50,220+(i%3)*33,x+104,307+(i%3)*33,fill='#DAEBDD',smooth=True,outline='')
        for i in range(-1,6):
            x=i*330-(cam*.35)%330
            c.create_oval(x-100,350+(i%2)*35,x+380,700,fill='#96CBB6',outline='')
        for i in range(-1,9):
            x=i*170-(cam*.55)%170
            self.tree(x,482,.63+(i%3)*.12,'#79BAA0')
        c.create_rectangle(0,530,W,H,fill='#91D9DB',outline='')
        for i in range(8):
            yy=555+i*14
            c.create_line(0,yy,W,yy,fill='#A8E3DF',width=2)

    def tree(self,x,y,s=1,leaf='#70B69A'):
        c=self.canvas
        c.create_rectangle(x-6*s,y-82*s,x+6*s,y,fill='#BFA581',outline='')
        for dx,dy,r in [(-26,-88,36),(24,-95,40),(0,-125,40)]:
            c.create_oval(x+(dx-r)*s,y+(dy-r)*s,x+(dx+r)*s,y+(dy+r)*s,fill=leaf,outline='')
        c.create_oval(x-20*s,y-150*s,x+6*s,y-130*s,fill='#A9D8AD',outline='')

    def platform(self,p):
        x,y=p.x-self.camera,p.y
        c=self.canvas
        if x+p.w<-30 or x>W+30:
            return
        bottom=H+10 if p.ground else y+p.h
        self.roundbox(x,y,x+p.w,bottom,'#BD936D',r=12)
        c.create_rectangle(x+4,y+12,x+p.w-4,min(bottom,y+23),fill='#D8B58B',outline='')
        for xx in range(int(x+25),int(x+p.w-10),70):
            c.create_oval(xx,y+36,xx+14,y+43,fill='#AB805F',outline='') if p.ground else None
        self.roundbox(x-3,y-8,x+p.w+3,y+11,'#66AE84',r=10)
        c.create_line(x+8,y-5,x+p.w-8,y-5,fill='#A4DB92',width=3)
        for xx in range(int(x+18),int(x+p.w-10),58):
            c.create_line(xx,y-8,xx-3,y-15,xx+1,y-10,xx+6,y-17,fill='#75BA89',width=2)
            if p.ground:
                c.create_line(xx+19,y-7,xx+19,y-18,fill='#4E9877',width=2)
                c.create_oval(xx+15,y-24,xx+23,y-16,fill='#FFF2C9',outline='')
                c.create_oval(xx+18,y-21,xx+21,y-18,fill='#E9BD6A',outline='')

    def draw_slime(self,e):
        x,y=e.x-self.camera,e.y
        c=self.canvas
        r=40 if e.boss else 24
        bob=math.sin(self.world.time*5+e.x*.01)*2
        color='#DBA4E3' if e.boss else '#88D4B0'
        if e.hurt>0:
            color='#FFF4CB'
        c.create_oval(x-r,y-8,x+r,y+3,fill='#73A98B',outline='')
        c.create_oval(x-r,y-r*1.5+bob,x+r,y,fill=color,outline='#658E87' if not e.boss else '#A271AE',width=2)
        c.create_oval(x-r*.6,y-r*1.2+bob,x-r*.12,y-r*.9+bob,fill='#CCF1C8' if not e.boss else '#F0D2F4',outline='')
        for eye in (-.32,.32):
            c.create_oval(x+r*eye-2,y-r*.66,x+r*eye+2,y-r*.44,fill='#3E6269',outline='')
        c.create_arc(x-5,y-r*.48,x+5,y-r*.18,start=190,extent=160,style='arc',outline='#3E6269',width=2)
        if e.boss:
            c.create_polygon(x-24,y-r*1.4,x-27,y-r*1.9,x-10,y-r*1.72,x,y-r*2.03,x+12,y-r*1.72,x+27,y-r*1.9,x+24,y-r*1.4,fill='#FFDA83',outline='#C79A5C',width=2)
            self.star(x,y-r*1.65,6,'#FFF4CE')
            self.roundbox(x-45,y-103,x+45,y-96,'#CDB9D7',r=3)
            if e.hp>0:
                self.roundbox(x-45,y-103,x-45+90*e.hp/14,y-96,'#B67BCB',r=3)

    def scenery_objects(self):
        c=self.canvas
        w=self.world
        for i,checkpoint in enumerate(w.checkpoints):
            x=checkpoint-self.camera
            if -80<x<W+80:
                c.create_line(x,530,x,440,fill='#8F8270',width=4)
                c.create_polygon(x,440,x+47,448,x+40,465,x,461,fill='#73CBB4' if i<=w.checkpoint else '#D4DCD1',outline='')
                self.star(x+19,452,7,'#FFF7C8')
        for chest in w.chests:
            x,y=chest['x']-self.camera,chest['y']
            if -50<x<W+50:
                self.roundbox(x-18,y-26,x+18,y-2,'#B78A63',outline='#83634F',r=5)
                if not chest['open']:
                    self.roundbox(x-19,y-32,x+19,y-15,'#E4BC76',outline='#83634F',r=6)
                else:
                    c.create_polygon(x-19,y-26,x-23,y-44,x+14,y-48,x+18,y-29,fill='#D6A76B',outline='#83634F')
                c.create_rectangle(x-3,y-22,x+3,y-13,fill='#FFF1AF',outline='')
        x=6100-self.camera
        if -100<x<W+100:
            c.create_oval(x-42,414,x+42,534,fill='#B3A1D8',outline='#8D85BF',width=5)
            c.create_oval(x-30,426,x+30,528,fill='#E6E3F6' if w.enemies[-1].hp>0 else '#C2F2EB',outline='')
            self.star(x,475,22,'#FFF1B2')
            self.text(x,390,'星门',13,bold=True)
        for x,y,label in [(235,478,'向右出发 →'),(1000,340,'二段跳！'),(2500,353,'Shift 冲刺'),(5510,459,'史莱姆王')]:
            sx=x-self.camera
            if -100<sx<W+100:
                self.roundbox(sx-52,y-25,sx+52,y,'#FFF3D7',r=6)
                self.text(sx,y-13,label,10)

    def draw_player(self):
        w=self.world
        if w.invincible>0 and w.dash_time<=0 and int(w.time*15)%2:
            return
        pose='blink' if w.time%4.6<.12 else 'idle'
        if w.won:
            pose=7
        elif w.hurt_time>0:
            pose=6
        elif w.attack_pose>0:
            pose=5
        elif not w.grounded:
            pose=4
        elif abs(w.vx)>1:
            pose=int(w.time*11)%4
        x=w.x-self.camera
        if w.dash_time>0:
            for i in range(1,4):
                self.canvas.create_line(x-w.facing*(25+i*15),w.y-30,x-w.facing*(40+i*15),w.y-30,fill='#B4FFF1',width=7-i)
        self.canvas.create_image(x,w.y+2,image=self.frames[pose,w.facing],anchor='s')
        if w.burst_time>0:
            radius=190*(1-w.burst_time/.45)
            self.canvas.create_oval(x-radius,w.y-35-radius,x+radius,w.y-35+radius,outline='#B99AF0',width=5)

    def hud(self):
        w=self.world
        self.roundbox(20,18,305,86,'#FFFBEC',r=15)
        self.text(37,37,'星屿小冒险',11,anchor='w',bold=True)
        for i in range(5):
            self.text(45+i*24,64,'♥',19,'#DF8C96' if i<w.hp else '#D6DCD4')
        self.star(194,62,10)
        self.text(213,62,str(w.stars),16,anchor='w',bold=True)
        self.roundbox(W-300,18,W-20,86,'#FFFBEC',r=15)
        zone=['晨风草地','浮岛花园','云间小径','星门山谷'][min(3,int(w.x/1600))]
        self.text(W-280,38,zone,11,anchor='w',bold=True)
        self.text(W-37,38,'ESC 暂停',9,anchor='e',color='#7D928D')
        self.roundbox(W-280,61,W-42,68,'#DCEBDD',r=3)
        self.roundbox(W-280,61,W-280+238*w.x/WORLD_WIDTH,68,'#80C4AC',r=3)
        self.canvas.create_oval(W-284+238*w.x/WORLD_WIDTH,58,W-274+238*w.x/WORLD_WIDTH,71,fill='#EAB77E',outline='')
        self.roundbox(20,588,W-20,628,'#FFFBEC',r=12)
        self.text(39,608,'A / D  移动    空格  二段跳',10,anchor='w')
        for x,key,label,cd,total in [(410,'J','星光弹',w.attack_cd,.28),(610,'K','星环爆发',w.burst_cd,5),(830,'Shift','流星冲刺',w.dash_cd,1.35)]:
            self.roundbox(x-30,596,x+19,620,'#E1EDE4' if cd>0 else '#D9EFE5',r=6)
            self.text(x-6,608,key,9,bold=True)
            self.text(x+30,608,label if cd<=0 else f'{label} {cd:.1f}s',10,anchor='w',color=INK if cd<=0 else '#8A9C94')
        if w.notice_time>0:
            self.roundbox(W/2-220,100,W/2+220,137,'#FFFAE5',r=12)
            self.text(W/2,118,w.notice,11)

    def button(self,x,y,width,label,callback,primary=True):
        self.roundbox(x,y,x+width,y+46,'#4D9C87' if primary else '#E6EEDC',r=14)
        self.text(x+width/2,y+23,label,12,'#FFFFFF' if primary else INK,bold=True)
        self.buttons.append((x,y,x+width,y+46,callback))

    def title(self):
        self.roundbox(62,73,623,561,'#FFFBEE',r=32)
        self.text(103,115,'A LITTLE STAR JOURNEY',10,'#8CA498',anchor='w',bold=True)
        self.text(99,181,'星屿小冒险',34,anchor='w',bold=True)
        self.text(103,236,'和她一起，捡起散落的小星光。',14,anchor='w',color='#788F83')
        self.text(103,285,'跑过草地与浮岛，打开宝箱，打败软乎乎的史莱姆。\n收集 18 颗星星并击败史莱姆王，点亮终点星门。',11,anchor='nw',width=460,spacing=8)
        for x,y,key,label in [(104,365,'A D','左右移动'),(327,365,'空格','二段跳'),(104,407,'J / K','星光弹 / 星环'),(327,407,'Shift','无敌冲刺')]:
            self.roundbox(x,y,x+64,y+28,'#E4EFE3',r=8)
            self.text(x+32,y+14,key,10,bold=True)
            self.text(x+77,y+14,label,11,anchor='w')
        self.button(103,476,205,'开始冒险  →',self.start)
        self.button(326,476,230,'回到桌面宠物',self.close,False)
        self.canvas.create_oval(681,155,1000,482,fill='#DCECD5',outline='#EBF4DD',width=7)
        self.canvas.create_image(837,325,image=self.portrait)
        for x,y,r in [(723,177,17),(975,256,13),(731,428,11),(951,454,20)]:
            self.star(x,y,r)
        self.roundbox(682,505,995,572,'#FFFBEE',r=15)
        self.text(836,524,'小小的勇气，也会发光',13,'#5A8474',bold=True)
        self.text(836,552,f'最好收集：{self.best} 颗星星' if self.best else '按 Enter 也可以开始',10,'#729082')

    def overlay(self,win=False):
        self.canvas.create_rectangle(0,0,W,H,fill='#405A64',stipple='gray50',outline='')
        self.roundbox(290,127,770,519,'#FFFBEE',r=25)
        self.star(530,181,28)
        self.text(530,241,'星门点亮啦！' if win else '休息一下',26,bold=True)
        if win:
            w=self.world
            self.text(530,297,f'星星 {w.stars}   ·   打败怪物 {w.defeated}\n用时 {int(w.time)//60}:{int(w.time)%60:02d}   ·   重返检查点 {w.deaths} 次',12,spacing=12)
            self.button(345,363,370,'再冒险一次',self.start)
        else:
            self.text(530,294,'进度还在。准备好了就继续吧。\nR 可回到最近检查点；切出窗口会自动暂停。',11,spacing=12)
            self.button(345,363,370,'继续冒险  /  ESC',lambda:setattr(self,'mode','play'))
        self.button(345,425,370,'回到桌面宠物',self.close,False)

    def render(self):
        self.render_scene()
        self.roundbox(900,226,1040,260,"#FFFBEC",r=10)
        self.text(970,243,f"O  音量 {round(self.audio.volume*100)}%",10,color="#67877C")
        self.buttons.append((900,226,1040,260,self.open_volume))
        self.canvas.finish_frame()

    def render_scene(self):
        c=self.canvas
        c.delete('all')
        self.buttons=[]
        self.background()
        for p in self.world.platforms:
            self.platform(p)
        if self.mode=='title':
            self.title()
            self.sound_control()
            return
        self.scenery_objects()
        for item in self.world.pickups:
            if item.taken:
                continue
            x=item.x-self.camera
            if -20<x<W+20:
                y=item.y+math.sin(self.world.time*3+item.x*.02)*4
                if item.kind=='heart':
                    self.text(x,y,'♥',23,'#E98C9D')
                else:
                    self.star(x,y,9)
        for e in self.world.enemies:
            if e.hp>0 and -80<e.x-self.camera<W+80:
                self.draw_slime(e)
        for shot in self.world.shots:
            x=shot.x-self.camera
            if -20<x<W+20:
                self.star(x,shot.y,9,'#CD9AE6' if shot.hostile else '#FFF6AB',outline='#A780C8' if shot.hostile else '#E3BD68')
        self.draw_player()
        for x,y,vx,vy,life,color in self.world.particles:
            sx=x-self.camera
            if -10<sx<W+10:
                r=max(1,life*5)
                c.create_oval(sx-r,y-r,sx+r,y+r,fill=color,outline='')
        self.hud()
        if self.mode=='pause':
            self.overlay()
        elif self.mode=='win':
            self.overlay(True)
        self.sound_control()

    def sound_control(self):
        label='M  全部声音：开'
        if self.audio.muted:
            label='M  全部声音：关'
        if not self.audio.available:
            label='声音设备不可用'
        self.roundbox(345,22,531,58,'#FFFBEC',r=10)
        self.text(438,40,label,10,color='#67877C')
        self.buttons.append((345,22,531,58,self.audio.toggle))
        self.roundbox(541,22,727,58,'#FFFBEC',r=10)
        voice_label='V  人物配音：关' if self.audio.voice_muted else 'V  人物配音：开'
        if not self.audio.speech_available:
            voice_label='人物配音不可用'
        self.text(634,40,voice_label,10,color='#67877C')
        self.buttons.append((541,22,727,58,self.audio.toggle_voice))
        self.roundbox(900,100,1040,134,'#FFFBEC',r=10)
        self.text(970,117,'C  换装衣橱',10,color='#916F86')
        self.buttons.append((900,100,1040,134,self.open_wardrobe))
        self.roundbox(900,142,1040,176,'#FFFBEC',r=10)
        self.text(970,159,'F11  退出全屏' if self.fullscreen else 'F11  全屏',10,color='#67877C')
        self.buttons.append((900,142,1040,176,self.toggle_fullscreen))
        self.roundbox(900,184,1040,218,'#FFFBEC',r=10)
        self.text(970,201,'F10  小窗口',10,color='#67877C')
        self.buttons.append((900,184,1040,218,self.small_window))
        if self.audio.subtitle:
            self.roundbox(310,544,750,579,'#FFF7EF',r=12)
            self.text(530,561,self.audio.subtitle,12,color='#80616E')


if __name__=='__main__':
    game=Adventure()
    game.window.mainloop()
