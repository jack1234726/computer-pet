"""Asynchronous Windows PCM playback: music and effects can overlap."""
from array import array
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import time
import wave
import json

VOLUME_SETTINGS = Path(__file__).with_name("sound-settings.json")

def read_volume():
    try:
        value=float(json.loads(VOLUME_SETTINGS.read_text(encoding="utf-8"))["volume"])
        return max(0.,min(1.,value)) if value==value else 1.
    except (OSError,ValueError,TypeError,KeyError):
        return 1.



class Format(C.Structure):
    _pack_=1
    _fields_=[('tag',W.WORD),('channels',W.WORD),('rate',W.DWORD),('bytes_per_sec',W.DWORD),
              ('align',W.WORD),('bits',W.WORD),('extra',W.WORD)]


class Header(C.Structure):
    _fields_=[('data',C.c_void_p),('length',W.DWORD),('recorded',W.DWORD),('user',C.c_size_t),
              ('flags',W.DWORD),('loops',W.DWORD),('next',C.c_void_p),('reserved',C.c_size_t)]


def driver():
    lib=C.WinDLL('winmm')
    lib.waveOutOpen.argtypes=[C.POINTER(C.c_void_p),W.UINT,C.POINTER(Format),C.c_size_t,C.c_size_t,W.DWORD]
    lib.waveOutOpen.restype=W.UINT
    for name in ('waveOutPrepareHeader','waveOutWrite','waveOutUnprepareHeader'):
        fn=getattr(lib,name)
        fn.argtypes=[C.c_void_p,C.POINTER(Header),W.UINT]
        fn.restype=W.UINT
    for name in ('waveOutReset','waveOutClose'):
        fn=getattr(lib,name)
        fn.argtypes=[C.c_void_p]
        fn.restype=W.UINT
    lib.waveOutSetVolume.argtypes=[C.c_void_p,W.DWORD]
    lib.waveOutSetVolume.restype=W.UINT
    return lib


class Voice:
    def __init__(self,lib,pcm,rate,loop=False,volume=1.):
        self.lib=lib
        self.handle=C.c_void_p()
        self.buffer=C.create_string_buffer(pcm)
        self.header=Header(C.cast(self.buffer,C.c_void_p),len(pcm),0,0,12 if loop else 0,0xFFFFFFFF if loop else 0,None,0)
        fmt=Format(1,1,rate,rate*2,2,16,0)
        code=lib.waveOutOpen(C.byref(self.handle),0xFFFFFFFF,C.byref(fmt),0,0,0)
        if code:
            raise OSError(f'waveOutOpen: {code}')
        try:
            self.set_volume(volume)
        except OSError:
            lib.waveOutClose(self.handle)
            self.handle=None
            raise
        code=lib.waveOutPrepareHeader(self.handle,C.byref(self.header),C.sizeof(Header))
        if code:
            lib.waveOutClose(self.handle)
            self.handle=None
            raise OSError(f'waveOutPrepareHeader: {code}')
        code=lib.waveOutWrite(self.handle,C.byref(self.header),C.sizeof(Header))
        if code:
            self.close()
            raise OSError(f'waveOutWrite: {code}')

    def set_volume(self,value):
        level=round(max(0.,min(1.,value))*65535)
        code=self.lib.waveOutSetVolume(self.handle,level | (level << 16))
        if code:
            raise OSError(f"waveOutSetVolume: {code}")

    @property
    def done(self):
        return bool(self.header.flags&1)

    def close(self):
        if self.handle:
            self.lib.waveOutReset(self.handle)
            self.lib.waveOutUnprepareHeader(self.handle,C.byref(self.header),C.sizeof(Header))
            self.lib.waveOutClose(self.handle)
            self.handle=None


class Audio:
    def __init__(self,folder=None):
        self.volume=read_volume()
        self.next_volume_check=0.
        self.muted=False
        self.available=True
        self.error=''
        self.background=None
        self.voices=[]
        self.recent={}
        self.bank={}
        self.voice_muted=False
        self.speech_available=False
        self.dialogue=None
        self.dialogue_priority=0
        self.dialogue_until=0.
        self.subtitle=''
        self.speech_recent={}
        self.speech_indices={}
        self.speech_bank={}
        try:
            self.lib=driver()
            folder=folder or Path(__file__).parent/'assets'/'audio'
            for path in folder.glob('*.wav'):
                with wave.open(str(path),'rb') as sound:
                    if sound.getnchannels()!=1 or sound.getsampwidth()!=2:
                        raise ValueError('Audio must be mono PCM16')
                    rate=sound.getframerate()
                    samples=array('h',sound.readframes(sound.getnframes()))
                volume=.42 if path.stem=='star-island-theme' else .65
                self.bank[path.stem]=(array('h',(int(x*volume) for x in samples)).tobytes(),rate)
            if 'star-island-theme' not in self.bank:
                raise OSError('Missing background music')
        except (OSError,ValueError,AttributeError) as exc:
            self.available=False
            self.error=str(exc)
        try:
            assets=Path(__file__).parent/'assets'
            manifest=json.loads((assets/'voice-lines.json').read_text(encoding='utf-8'))
            for line in manifest['lines']:
                with wave.open(str(assets/'voice'/(line['id']+'.wav')),'rb') as sound:
                    if sound.getnchannels()!=1 or sound.getsampwidth()!=2:
                        raise ValueError('Voice must be mono PCM16')
                    rate=sound.getframerate()
                    samples=array('h',sound.readframes(sound.getnframes()))
                pcm=array('h',(int(x*.9) for x in samples)).tobytes()
                self.speech_bank.setdefault(line['event'],[]).append((pcm,rate,line['text'],len(samples)/rate))
            self.speech_available=True
        except (OSError,ValueError,KeyError):
            self.speech_bank={}

    def speak(self,event):
        if self.muted or self.voice_muted or not self.available or not self.speech_available:
            return False
        lines=self.speech_bank.get(event)
        if not lines:
            return False
        now=time.monotonic()
        cooldown={'start':0,'jump':9,'shoot':12,'dash':10,'burst':6,'pickup':14,
                  'hurt':5,'chest':2,'checkpoint':2,'respawn':2,'win':0,
                  'welcome':0,'touch':12,'drag':10,'outfit':3,
                  'wave':4,'sleep':30,'invite':30,'return':3,'recall':4,
                  'follow':3,'stay':3,'hop':6,'file':15,'desktop':20,'enter':15,'sailor':3}.get(event,8)
        if now-self.speech_recent.get(event,-1000)<cooldown:
            return False
        priority={'win':100,'respawn':90,'start':80,'hurt':70,'checkpoint':60,'chest':60,
                  'burst':40,'dash':30,'welcome':80,'drag':45,'outfit':60,
                  'wave':60,'sleep':65,'invite':25,'return':80,'recall':85,
                  'follow':55,'stay':56,'hop':50,'file':10,'desktop':10,'enter':10,'sailor':60}.get(event,20)
        self.collect()
        if self.dialogue is not None and priority<=self.dialogue_priority:
            return False
        if self.dialogue is None and now<self.dialogue_until+1.4 and priority<60:
            return False
        self.stop_speech()
        index=self.speech_indices.get(event,0)%len(lines)
        pcm,rate,text,duration=lines[index]
        try:
            self.dialogue=Voice(self.lib,pcm,rate,volume=self.volume)
        except OSError:
            self.speech_available=False
            return False
        self.speech_indices[event]=index+1
        self.speech_recent[event]=now
        self.dialogue_priority=priority
        self.dialogue_until=now+duration
        self.subtitle=text
        return True

    def stop_speech(self):
        if self.dialogue:
            self.dialogue.close()
            self.dialogue=None
        self.subtitle=''

    def toggle_voice(self):
        self.voice_muted=not self.voice_muted
        if self.voice_muted:
            self.stop_speech()

    def play(self,name):
        if self.muted or not self.available or name not in self.bank:
            return
        now=time.monotonic()
        if now-self.recent.get(name,0)<.065:
            return
        self.recent[name]=now
        self.collect()
        if len(self.voices)>=8:
            self.voices.pop(0).close()
        try:
            self.voices.append(Voice(self.lib,*self.bank[name],volume=self.volume))
        except OSError as exc:
            self.available=False
            self.error=str(exc)
            self.stop()

    def set_volume(self,value,persist=True):
        self.volume=max(0.,min(1.,float(value)))
        for voice in [self.dialogue,self.background,*self.voices]:
            if voice is not None:
                try:
                    voice.set_volume(self.volume)
                except OSError as exc:
                    self.error=str(exc)
        if persist:
            temp=VOLUME_SETTINGS.with_suffix(".tmp")
            temp.write_text(json.dumps({"volume":self.volume}),encoding="utf-8")
            temp.replace(VOLUME_SETTINGS)

    def collect(self):
        now=time.monotonic()
        if now>=self.next_volume_check:
            self.next_volume_check=now+.5
            volume=read_volume()
            if volume!=self.volume:
                self.set_volume(volume,persist=False)
        if self.dialogue is not None and self.dialogue.done:
            self.stop_speech()
        for voice in self.voices[:]:
            if voice.done:
                voice.close()
                self.voices.remove(voice)

    def update(self,active):
        self.collect()
        if active and not self.muted and self.available:
            if self.background is None:
                try:
                    self.background=Voice(self.lib,*self.bank['star-island-theme'],loop=True,volume=self.volume)
                except OSError as exc:
                    self.available=False
                    self.error=str(exc)
        elif self.background is not None:
            self.background.close()
            self.background=None

    def toggle(self):
        self.muted=not self.muted
        if self.muted:
            self.stop()

    def stop(self):
        self.stop_speech()
        if self.background:
            self.background.close()
            self.background=None
        for voice in self.voices:
            voice.close()
        self.voices=[]

    close=stop
