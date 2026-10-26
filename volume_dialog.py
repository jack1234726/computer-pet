"""Live app-volume slider, independent of Windows system volume."""
import tkinter as tk

class VolumeDialog:
    def __init__(self,parent,audio):
        self.audio=audio
        self.closed=False
        self.window=tk.Toplevel(parent)
        self.window.title('宠物音量')
        self.window.geometry('380x235')
        self.window.resizable(False,False)
        self.window.configure(bg='#FFF7F1')
        tk.Label(self.window,text='宠物音量',font=('Microsoft YaHei UI',17),bg='#FFF7F1',fg='#63484D').pack(pady=(18,3))
        tk.Label(self.window,text='桌面配音与冒险声音共用此音量',bg='#FFF7F1',fg='#866F79').pack()
        self.label=tk.StringVar(value=f'{round(audio.volume*100)}%')
        tk.Label(self.window,textvariable=self.label,bg='#FFF7F1',fg='#63484D').pack(pady=(9,0))
        self.slider=tk.Scale(self.window,from_=0,to=100,orient='horizontal',length=310,
            showvalue=False,resolution=1,bg='#FFF7F1',highlightthickness=0,troughcolor='#E1CDD7')
        self.slider.set(round(audio.volume*100))
        self.slider.configure(command=self.changed)
        self.slider.pack()
        self.status=tk.StringVar(value='0% 为无声；音量会自动保存。')
        tk.Label(self.window,textvariable=self.status,bg='#FFF7F1',fg='#866F79').pack(pady=5)
        tk.Button(self.window,text='试听一句',command=self.preview,width=13).pack()
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        self.window.bind('<Escape>',lambda e:self.close())
        self.window.lift()

    def changed(self,value):
        percent=int(float(value))
        self.label.set(f'{percent}%')
        try:
            self.audio.set_volume(percent/100)
            self.status.set('已保存；0% 为无声。')
        except OSError:
            self.status.set('音量已调整，但设置暂时无法保存。')

    def preview(self):
        if self.audio.voice_muted or self.audio.muted:
            self.status.set('配音已关闭，请先开启人物配音。')
            return
        if not self.audio.available or not self.audio.speech_available:
            self.status.set('声音设备或配音文件不可用。')
            return
        self.audio.stop_speech()
        self.audio.speech_recent.pop('welcome',None)
        self.audio.speak('welcome')
        if self.audio.volume==0:
            self.status.set('当前为 0%，调高滑块后即可听到。')

    def close(self):
        if not self.closed:
            self.closed=True
            self.window.destroy()
