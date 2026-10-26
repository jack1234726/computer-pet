"""Shared outfit selection and a visual closet for the pet and game."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

BASE=Path(__file__).parent
SETTINGS=BASE/'outfit-settings.json'
OUTFITS={
    'sailor':{'name':'晴空水手服','description':'红领结 · 海军蓝百褶裙',
              'pet':BASE/'assets/anime-sprites.png','game':BASE/'assets/game-hero.png','split':525},
    'floral':{'name':'花间小裙子','description':'浅蓝碎花 · 蝴蝶结 · 花朵发饰',
              'pet':BASE/'assets/outfits/floral/pet.png','game':BASE/'assets/outfits/floral/game.png','split':525},
}


def get_outfit():
    try:
        key=json.loads(SETTINGS.read_text(encoding='utf-8'))['outfit']
        if key in OUTFITS and all(OUTFITS[key][kind].is_file() for kind in ('pet','game')):
            return key
    except (OSError,ValueError,TypeError,KeyError):
        pass
    return 'sailor'


def save_outfit(key):
    if key not in OUTFITS:
        raise ValueError('Unknown outfit')
    if not all(OUTFITS[key][kind].is_file() for kind in ('pet','game')):
        raise OSError('Outfit artwork is missing')
    temp=SETTINGS.with_suffix('.tmp')
    temp.write_text(json.dumps({'outfit':key},ensure_ascii=False),encoding='utf-8')
    temp.replace(SETTINGS)


class WardrobeDialog:
    def __init__(self,parent,on_change,on_close=None):
        self.window=tk.Toplevel(parent)
        self.window.title('她的小衣橱')
        self.window.geometry('680x485')
        self.window.resizable(False,False)
        self.window.configure(bg='#FFF9F2')
        self.on_change=on_change
        self.on_close=on_close
        self.closed=False
        self.current=get_outfit()
        self.images={}
        self.cards=[]
        self.canvas=tk.Canvas(self.window,width=680,height=485,bg='#FFF9F2',highlightthickness=0)
        self.canvas.pack()
        for key,data in OUTFITS.items():
            with Image.open(data['pet']) as sheet:
                cell=sheet.convert('RGBA').crop((0,0,sheet.width//3,sheet.height//2))
                self.images[key]=ImageTk.PhotoImage(cell.resize((245,245),Image.Resampling.LANCZOS),master=self.window)
        self.canvas.bind('<Button-1>',self.click)
        self.window.bind('<Escape>',lambda event:self.close())
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        self.window.lift()
        self.draw()

    def text(self,x,y,text,size=15,color='#65545F',bold=False):
        self.canvas.create_text(x,y,text=text,fill=color,font=('Microsoft YaHei UI',-size,'bold' if bold else 'normal'))

    def draw(self):
        c=self.canvas
        c.delete('all')
        self.cards=[]
        self.text(340,35,'她的小衣橱',27,bold=True)
        self.text(340,68,'选择一套喜欢的衣服，桌面和冒险一起换装',14,'#9A8290')
        for i,(key,data) in enumerate(OUTFITS.items()):
            x=32+i*325
            selected=key==self.current
            c.create_rectangle(x,96,x+291,429,fill='#F3EDF5' if selected else '#FFFFFF',outline='#C6A3B9' if selected else '#EBE2DE',width=3 if selected else 1)
            c.create_image(x+145,224,image=self.images[key])
            self.text(x+145,358,data['name'],18,bold=True)
            self.text(x+145,384,data['description'],12,'#947D87')
            self.text(x+145,411,'✓ 正在穿' if selected else '点击换上这套',14,'#9D6E8B' if selected else '#5C9A8A',True)
            self.cards.append((x,96,x+291,429,key))
        self.text(340,458,'选择会自动保存；关闭衣橱即可继续',13,'#9A8290')

    def choose(self,key):
        if key==self.current:
            return
        try:
            self.on_change(key)
        except (OSError,ValueError) as exc:
            messagebox.showerror('暂时无法换装',str(exc),parent=self.window)
            return
        self.current=key
        self.draw()

    def click(self,event):
        for x1,y1,x2,y2,key in self.cards:
            if x1<=event.x<=x2 and y1<=event.y<=y2:
                self.choose(key)
                break

    def close(self):
        if self.closed:
            return
        self.closed=True
        self.window.destroy()
        if self.on_close:
            self.on_close()
