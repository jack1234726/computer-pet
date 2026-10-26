"""Deterministic platformer simulation, independent of the desktop UI."""
from dataclasses import dataclass
from collections import deque
import math
import random

WORLD_WIDTH = 6200
GRAVITY = 1650


@dataclass
class Platform:
    x: float
    y: float
    w: float
    h: float = 26
    ground: bool = False


@dataclass
class Enemy:
    x: float
    y: float
    low: float
    high: float
    hp: int = 2
    direction: int = 1
    boss: bool = False
    hurt: float = 0
    timer: float = 1.5


@dataclass
class Shot:
    x: float
    y: float
    vx: float
    life: float = 1.25
    hostile: bool = False


@dataclass
class Pickup:
    x: float
    y: float
    kind: str = 'star'
    taken: bool = False


class World:
    def __init__(self):
        self.platforms = [Platform(x,530,w,160,True) for x,w in
                          [(0,1050),(1190,1210),(2580,1090),(3820,1000),(4970,1230)]]
        self.platforms += [Platform(x,y,w) for x,y,w in [
            (330,428,180),(600,340,150),(850,420,140),(1090,390,115),
            (1390,430,180),(1630,340,170),(1880,410,150),(2130,320,150),
            (2430,405,130),(2690,430,160),(2950,340,150),(3200,420,180),
            (3490,330,170),(3710,395,140),(4030,420,170),(4290,330,150),
            (4550,410,160),(4860,400,130),(5170,420,160),(5440,340,170)]]
        self.enemies = [Enemy(x,y,lo,hi) for x,y,lo,hi in [
            (710,530,620,960),(1450,530,1290,1570),(1750,340,1655,1770),
            (2050,530,1920,2340),(2830,530,2670,2910),(3320,420,3230,3350),
            (3530,530,3370,3620),(4150,530,3960,4250),(4620,410,4580,4675),
            (5240,530,5070,5380)]]
        self.enemies.append(Enemy(5710,530,5580,5880,14,boss=True,timer=1.5))
        self.pickups = []
        for p in self.platforms:
            spacing = 110 if p.ground else 48
            for x in range(int(p.x+40), int(p.x+p.w-24), spacing):
                self.pickups.append(Pickup(x,p.y-55))
        self.pickups += [Pickup(2000,485,'heart'),Pickup(4380,485,'heart')]
        self.chests = [{'x':770,'y':530,'open':False},{'x':3510,'y':330,'open':False},
                       {'x':5450,'y':340,'open':False}]
        self.checkpoints = [120,2230,4350]
        self.checkpoint = 0
        self.x,self.y = 120.,530.
        self.vx,self.vy = 0.,0.
        self.facing = 1
        self.grounded = True
        self.jumps = 0
        self.coyote = .1
        self.hp = 5
        self.stars = 0
        self.defeated = 0
        self.deaths = 0
        self.time = 0.
        self.invincible = 0.
        self.attack_cd = 0.
        self.attack_pose = 0.
        self.dash_cd = 0.
        self.dash_time = 0.
        self.burst_cd = 0.
        self.burst_time = 0.
        self.hurt_time = 0.
        self.shots = []
        self.particles = []
        self.won = False
        self.notice = '去收集星星吧！空格可以二段跳'
        self.notice_time = 4.
        self.rng = random.Random(7)
        self.sounds = deque(maxlen=128)

    def tell(self, text, duration=3):
        self.notice,self.notice_time = text,duration

    def spark(self,x,y,color,count=10):
        for _ in range(count):
            self.particles.append([x,y,self.rng.uniform(-100,100),self.rng.uniform(-150,30),.6,color])

    def jump(self):
        if self.won:
            return False
        if self.grounded or self.coyote > 0:
            self.jumps = 1
        elif self.jumps < 2:
            self.jumps = 2
        else:
            return False
        self.vy = -640 if self.jumps == 1 else -580
        self.grounded = False
        self.coyote = 0
        self.spark(self.x,self.y,'#FFE29A',7)
        self.sounds.append('jump')
        return True

    def attack(self):
        if self.attack_cd > 0 or self.won:
            return False
        self.attack_cd = .28
        self.attack_pose = .22
        self.shots.append(Shot(self.x+self.facing*22,self.y-38,self.facing*650))
        self.sounds.append('shoot')
        return True

    def dash(self):
        if self.dash_cd > 0 or self.won:
            return False
        self.dash_cd = 1.35
        self.dash_time = .18
        self.invincible = max(self.invincible,.25)
        self.sounds.append('dash')
        return True

    def burst(self):
        if self.burst_cd > 0 or self.won:
            return False
        self.burst_cd = 5.
        self.burst_time = .45
        for e in self.enemies:
            if e.hp > 0 and math.hypot(e.x-self.x,e.y-self.y)<190:
                self.hit_enemy(e,3)
        self.shots = [s for s in self.shots if not s.hostile or math.hypot(s.x-self.x,s.y-(self.y-35))>200]
        self.spark(self.x,self.y-35,'#B9A7FF',25)
        self.sounds.append('burst')
        return True

    def hit_enemy(self,e,damage=1):
        if e.hp <= 0:
            return
        e.hp -= damage
        e.hurt = .18
        self.spark(e.x,e.y-20,'#D7B9FF')
        self.sounds.append('hit')
        if e.hp <= 0:
            self.defeated += 1
            self.stars += 8 if e.boss else 2
            if e.boss:
                self.tell('史莱姆王被击败了！去右边的星门吧！',5)

    def damage(self):
        if self.invincible > 0 or self.won:
            return
        self.hp -= 1
        self.invincible = 1.3
        self.hurt_time = .3
        self.vy = -230
        self.spark(self.x,self.y-35,'#FFA7B7')
        self.sounds.append('hurt')
        if self.hp <= 0:
            self.respawn()

    def respawn(self):
        self.deaths += 1
        self.x,self.y = float(self.checkpoints[self.checkpoint]),530.
        self.hp = 5
        self.vx,self.vy = 0.,0.
        self.dash_time = 0
        self.grounded = True
        self.jumps = 0
        self.invincible = 2.
        self.shots.clear()
        self.tell('回到检查点啦，收集的星星都还在！')
        self.sounds.append('respawn')

    def step(self,dt,axis=0,shoot=False):
        # Fixed-size internal steps prevent tunneling after a slow frame.
        remaining = max(0,min(dt,.1))
        while remaining > 1e-8:
            h = min(remaining,1/120)
            self._step(h,axis,shoot)
            remaining -= h

    def _step(self,dt,axis,shoot):
        if self.won:
            return
        self.time += dt
        for attr in ('invincible','attack_cd','attack_pose','dash_cd','dash_time',
                     'burst_cd','burst_time','hurt_time','notice_time','coyote'):
            setattr(self,attr,max(0,getattr(self,attr)-dt))
        if shoot:
            self.attack()
        if axis and self.dash_time <= 0:
            self.facing = 1 if axis>0 else -1
        self.vx = self.facing*850 if self.dash_time>0 else axis*280
        previous_y = self.y
        self.x = max(20,min(WORLD_WIDTH-25,self.x+self.vx*dt))
        if self.dash_time > 0:
            self.vy = 0
        else:
            self.vy = min(1100,self.vy+GRAVITY*dt)
        self.y += self.vy*dt
        was_grounded = self.grounded
        self.grounded = False
        # Platforms are one-way: pass upward through them and land on top.
        if self.vy >= 0:
            candidates = [p for p in self.platforms if self.x+14>p.x and self.x-14<p.x+p.w
                          and previous_y<=p.y+.5 and self.y>=p.y]
            if candidates:
                self.y = min(p.y for p in candidates)
                self.vy = 0
                self.grounded = True
                self.jumps = 0
                self.coyote = .1
        if was_grounded and not self.grounded:
            self.coyote = .1
        if self.y>740:
            self.respawn()
        for i,x in enumerate(self.checkpoints):
            if i>self.checkpoint and abs(self.x-x)<45 and abs(self.y-530)<10:
                self.checkpoint = i
                self.hp = 5
                self.tell('检查点已点亮 · 生命恢复')
                self.spark(x,475,'#9EF0D4',20)
                self.sounds.append('checkpoint')
        for item in self.pickups:
            if not item.taken and abs(item.x-self.x)<30 and self.y-79<item.y<self.y+10:
                item.taken = True
                if item.kind=='heart':
                    self.hp = min(5,self.hp+2)
                else:
                    self.stars += 1
                self.spark(item.x,item.y,'#FFDB77',6)
                self.sounds.append('pickup')
        for chest in self.chests:
            if not chest['open'] and abs(chest['x']-self.x)<42 and abs(chest['y']-self.y)<35:
                chest['open'] = True
                self.stars += 5
                self.hp = min(5,self.hp+1)
                self.tell('发现宝箱！星星 +5，生命 +1')
                self.spark(chest['x'],chest['y']-20,'#FFDF89',20)
                self.sounds.append('chest')
        for e in self.enemies:
            if e.hp<=0:
                continue
            e.hurt = max(0,e.hurt-dt)
            e.x += e.direction*(55 if e.boss else 48)*dt
            if e.x>e.high:
                e.x,e.direction = e.high,-1
            if e.x<e.low:
                e.x,e.direction = e.low,1
            radius = 40 if e.boss else 24
            if abs(e.x-self.x)<radius+14 and self.y>e.y-radius*1.7 and self.y-66<e.y:
                if self.dash_time>0:
                    if e.hurt<=0:
                        self.hit_enemy(e,2)
                elif self.vy>100 and previous_y<e.y-radius:
                    self.hit_enemy(e)
                    self.vy = -400
                    self.grounded = False
                else:
                    self.damage()
            if e.boss and abs(e.x-self.x)<660:
                e.timer -= dt
                if e.timer<=0:
                    e.timer = 1.6
                    self.shots.append(Shot(e.x,e.y-26,(-1 if self.x<e.x else 1)*220,3,True))
        for s in self.shots:
            s.x += s.vx*dt
            s.life -= dt
            if s.hostile:
                if abs(s.x-self.x)<23 and self.y-70<s.y<self.y:
                    self.damage()
                    s.life = 0
            else:
                for e in self.enemies:
                    radius = 40 if e.boss else 24
                    if e.hp>0 and abs(s.x-e.x)<radius+8 and e.y-radius*1.8<s.y<e.y+5:
                        self.hit_enemy(e)
                        s.life = 0
                        break
        self.shots = [s for s in self.shots if s.life>0]
        for p in self.particles:
            p[0] += p[2]*dt
            p[1] += p[3]*dt
            p[3] += 230*dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4]>0]
        if self.x>6050 and self.y>450:
            if self.enemies[-1].hp>0:
                self.tell('星门被封印了，先击败史莱姆王！',1)
            elif self.stars<18:
                self.tell('星门需要 18 颗星星，回头再找找吧！',1)
            else:
                self.won = True
                self.sounds.append('win')
