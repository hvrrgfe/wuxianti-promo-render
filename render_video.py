#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无限题 B站宣传片视频渲染器
1280x720 @30fps, 约74秒, 8幕。粒子/打字机/数字滚动/光晕/转场等特效。
输出逐帧 PNG 到 /tmp/frames/，再用 ffmpeg 合成 mp4。
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math, random, os

W, H = 1280, 720
FPS = 20
FONT_DIR = '/usr/share/fonts/noto/'

def F(name, size):
    path = os.path.join(FONT_DIR, name)
    try: return ImageFont.truetype(path, size)
    except Exception: return ImageFont.load_default()

# 字体缓存
fb_xl  = F('NotoSansCJK-Black.ttc', 150)   # 超大标题
fb_l   = F('NotoSansCJK-Bold.ttc', 96)
fb_m   = F('NotoSansCJK-Bold.ttc', 54)
fb_s   = F('NotoSansCJK-Medium.ttc', 40)
fb_ss  = F('NotoSansCJK-Regular.ttc', 30)
fb_xs  = F('NotoSansCJK-Light.ttc', 24)

# ---- 配色 ----
BG      = (12, 15, 30)
BG2     = (20, 24, 48)
C1      = (110, 231, 255)   # 青
C2      = (167, 139, 250)   # 紫
C3      = (52, 211, 153)    # 绿
C4      = (251, 191, 36)    # 黄
C5      = (244, 114, 182)   # 粉
C6      = (96, 165, 250)    # 蓝
WHITE   = (238, 241, 250)
MUTED   = (139, 146, 173)
DARK    = (4, 19, 28)

# ---- 全局粒子系统（静态预生成，逐帧更新）----
random.seed(7)
NP = 90
particles = []
for _ in range(NP):
    particles.append({
        'x': random.uniform(0, W), 'y': random.uniform(0, H),
        'r': random.uniform(0.8, 2.6),
        'vx': random.uniform(-0.4, 0.4), 'vy': random.uniform(-0.9, -0.15),
        'c': random.choice([C1, C2, C6, C3, WHITE]),
        'tw': random.uniform(0, 6.28)
    })

# ---- 工具 ----
def lerp(a, b, t): return a + (b - a) * t
def clamp01(t): return max(0.0, min(1.0, t))
def ease(t):   # easeInOutCubic
    t = clamp01(t)
    return t*t*(3-2*t) if t < 0.5 else 1 - (1-t)*(1-t)*(1-t)
def ease_out(t):
    t = clamp01(t); return 1-math.pow(1-t,3)
def ease_in(t):
    t = clamp01(t); return t*t*t

def text_w(draw, txt, font):
    b = draw.textbbox((0,0), txt, font=font); return b[2]-b[0]

def draw_particles(img, t):
    """粒子漂移 + 微弱缓动光晕"""
    d = ImageDraw.Draw(img)
    for p in particles:
        p['x'] += p['vx']; p['y'] += p['vy']
        if p['y'] < -10: p['y'] = H+10; p['x'] = random.uniform(0,W)
        if p['x'] < -10: p['x'] = W+10
        twinkle = 0.5 + 0.5*math.sin(p['tw'] + t*2.2)
        a = int(120 + 120*twinkle)
        c = tuple(int(lerp(p['c'][i], 255, twinkle*0.4)) for i in range(3))
        d.ellipse([p['x']-p['r'], p['y']-p['r'], p['x']+p['r'], p['y']+p['r']], fill=c+(a,))

def radial_glow(img, cx, cy, rad, color, alpha):
    """中心径向光晕"""
    layer = Image.new('RGBA', (W,H), (0,0,0,0))
    ld = ImageDraw.Draw(layer)
    for i in range(rad, 0, -6):
        a = int(alpha * (1 - i/rad))
        ld.ellipse([cx-i, cy-i*0.6, cx+i, cy+i*0.6], fill=color+(a,))
    img.paste(Image.alpha_composite(img.convert('RGBA'), layer).convert('RGBA') if False else Image.alpha_composite(img.convert('RGBA'), layer), (0,0), mask=None)
    return img

def vgrad(img, c_top, c_bot):
    """垂直渐变叠加"""
    grad = Image.new('RGB', (1,H)); gd = ImageDraw.Draw(grad)
    for y in range(H):
        t = y/H
        gd.point((0,y), fill=(int(lerp(c_top[0],c_bot[0],t)), int(lerp(c_top[1],c_bot[1],t)), int(lerp(c_top[2],c_bot[2],t))))
    grad = grad.resize((W,H))
    return Image.blend(img, grad, 0.45)

def chunk_fade_in(draw, text, cx, cy, font, t, color=WHITE, size_f=1.0):
    """打字机逐字 + 淡入"""
    n = len(text)
    chars = int(clamp01(t)*n)
    if chars <= 0: return
    shown = text[:chars]
    alpha = clamp01(t*3)
    d = int(lerp(-40,0,ease_out(t)))
    draw.text((cx - text_w(draw, shown, font)/2 + d, cy - font.size/2), shown, font=font, fill=color)

def scroll_number(draw, value, cx, cy, font, t, color=C1, decimals=0):
    """数字滚动：从0滚到value"""
    need = t*2.5
    cur = min(value, int(need*value/1.0)) if t<0.4 else value
    # 简单滚动
    shown = min(value, int(value * clamp01((t-0.2)/0.9)))
    s = f"{shown:,.0f}"
    alpha = clamp01(t*4)
    d = int(lerp(50,0,ease_out(t)))
    draw.text((cx - text_w(draw,s,font)/2 + d, cy-font.size/2), s, font=font, fill=color)

def transparent_text(img, text, cx, cy, font, t, color, glow=False):
    """整句淡入滑入(可带光晕文字)"""
    if t<=0: return
    a = ease_out(clamp01(t*3))
    d = int(lerp(60, 0, a)) if t<0.5 else int(lerp(60,0,ease_out(clamp01((t-0.2)/0.8))))
    d = int(lerp(80,0,ease_out(clamp01(t*1.5))))
    layer = img.convert('RGBA')
    ld = ImageDraw.Draw(layer)
    if glow:
        for off in range(1,5):
            ld.text((cx-text_w(ld,text,font)/2+off, cy-font.size/2), text, font=font, fill=color+(30,))
    ld.text((cx-text_w(ld,text,font)/2+d, cy-font.size/2), text, font=font, fill=color+(int(255*a),))
    img.paste(layer, (0,0), layer)

# ========== 幕函数：每个返回一帧背景+内容，传入全局时间线 ==========

def scene_open(draw, t):
    """幕1 开场：粒子+大标题打字机+slogan+slogan2"""
    draw_particles_direct(draw, t)
    # 大标题 打字机
    title="无限题"
    n=int(clamp01(t)*len(title)) if t<1.0 else len(title)
    shown=title[:n]
    if shown:
        tw = text_w(draw, shown, fb_l)
        draw.text((W/2-tw/2, 200), shown, font=fb_l, fill=WHITE)
    # 渐变 underline
    if t>1.0:
        a=ease_out(clamp01((t-1.0)/0.5))
        draw.rectangle([W/2-200, 200+fb_l.size/2+10, W/2-200+400*a, 200+fb_l.size/2+16], fill=C1+(int(200*a),))
    # 副title
    if t>1.2:
        transparent_text_scene(draw,"不是题库，是题厂", W/2, 360, fb_m, t-1.2, C3, glow=True)
    if t>2.2:
        transparent_text_scene(draw,"每个考点 → 源源不断的新题", W/2, 470, fb_ss, t-2.2, MUTED)
    if t>3.0:
        transparent_text_scene(draw,"福建高考 · 6科全覆盖 · 全免费离线", W/2, 540, fb_xs, t-3.0, MUTED)

def draw_particles_direct(draw, t):
    for p in particles:
        p['x']+=p['vx']; p['y']+=p['vy']
        if p['y']<-10: p['y']=H+10; p['x']=random.uniform(0,W)
        if p['x']<-10: p['x']=W+10
        tw=0.5+0.5*math.sin(p['tw']+t*2.2); a=int(100+120*tw)
        c=tuple(int(lerp(p['c'][i],255,tw*0.4)) for i in range(3))
        draw.ellipse([p['x']-p['r'],p['y']-p['r'],p['x']+p['r'],p['y']+p['r']], fill=c+(a,))

def transparent_text_scene(draw,text,cx,cy,font,t,color,glow=False):
    if t<=0: return
    a=ease_out(clamp01(t/0.8)); d=int(lerp(80,0,ease_out(clamp01(t/1.2))))
    if glow:
        for off in range(1,4): draw.text((cx-text_w(draw,text,font)/2+off, cy-font.size/2), text, font=font, fill=color+(40,))
    draw.text((cx-text_w(draw,text,font)/2+d, cy-font.size/2), text, font=font, fill=(color[0],color[1],color[2],int(255*a)))

def scene_pain(draw,t):
    draw_particles_direct(draw,t)
    transparent_text_scene(draw,"刷题遇到这些，是不是很熟？", W/2, 180, fb_s, t-0.2, WHITE)
    rows=[
        ("背过的题，换个数字就不会", C5, 0.8),
        ("刷完1000道，考点还是模糊", C5, 1.6),
        ("答案对了，却不知道“为什么”", C4, 2.4),
    ]
    y0=330
    for txt,c,tt in rows:
        ts=clamp01((t-tt)/0.5)
        if ts>0:
            a=ease_out(ts); d=int(lerp(-50,0,a))
            # 叉号
            draw.text((W/2-300+d, y0), "✗", font=fb_ss, fill=c+(int(220*a),))
            draw.text((W/2-230+d, y0), txt, font=fb_m, fill=WHITE+(int(255*a),))
        y0+=90
    if t>3.6:
        transparent_text_scene(draw,"—— 刷题，不该这样 ——", W/2, 620, fb_ss, t-3.6, C3)

def scene_data(draw,t):
    draw_particles_direct(draw,t)
    transparent_text_scene(draw,"无限题 · 题厂量级", W/2, 160, fb_l, t-0.2, WHITE)
    stats=[
        ("6","学科全覆盖",C1,1.0),("100+","参数化模板",C2,1.8),
        ("3120","高考英语词汇",C3,2.6),("83","知识点讲解",C4,3.4),
        ("59章·134节","按教材出题",C6,4.2),("60篇","语文必背篇目",C5,5.0),
    ]
    cols=3; sw=380; sh=150; x0=W/2-(cols*sw)/2+sw/2; y0=300
    for i,(num,lbl,c,tt) in enumerate(stats):
        cx= x0 + (i%cols)*sw
        cy= y0 + (i//cols)*sh
        ts=clamp01((t-tt)/0.5)
        if ts<=0: continue
        a=ease_out(ts)
        # 卡片
        draw.rounded_rectangle([cx-sw/2+70, cy-70, cx+sw/2+70, cy+70], radius=18, outline=(255,255,255,30), width=2)
        # 数字滚动
        shown=scroll_count(num,ts)
        tw=text_w(draw,shown,fb_m)
        draw.text((cx-tw/2, cy-45), shown, font=fb_m, fill=c)
        draw.text((cx-text_w(draw,lbl,fb_xs)/2, cy+15), lbl, font=fb_xs, fill=MUTED)

def scroll_count(num,t):
    if "·" in num: return num
    try:
        v=int(num.replace(",",""))
        return f"{min(v, int(v*clamp01(t/0.9))):,}"
    except: return num

def scene_feature(draw,t):
    draw_particles_direct(draw,t)
    transparent_text_scene(draw,"每次，都是全新题", W/2, 150, fb_l, t-0.2, WHITE)
    feats=[
        ("🎯","智能出题","6科各考点参数化秒出",C1,0.8),
        ("📖","按教材出题","册→章→节，学哪练哪",C2,1.6),
        ("🧮","数学键盘","√ x² π 分式精确录入",C5,2.4),
        ("🗓️","重复避免","近7天新题自动避错",C3,3.2),
        ("🤖","AI讲解","未配Key自动离线解析",C6,4.0),
        ("🔄","答题闭环","判分·草稿·计时·闭环",C4,4.8),
    ]
    cols=3; cw=330; ch=140; x0=W/2-(cols*cw)/2+cw/2; y0=270
    for i,(ic,title,desc,c,tt) in enumerate(feats):
        cx=x0+(i%cols)*cw; cy=y0+(i//cols)*ch
        ts=clamp01((t-tt)/0.5)
        if ts<=0: continue
        a=ease_out(ts); scale=1.2-0.2*a
        # 旋转切入近似(用位置滑动)
        dx=int(lerp(120,0,a))
        draw.rounded_rectangle([cx-cw/2+40, cy-68, cx+cw/2+40, cy+68], radius=16, outline=(255,255,255,24), width=2)
        draw.text((cx-cw/2+58+dx, cy-45), ic, font=fb_ss, fill=WHITE+(int(255*a),))
        draw.text((cx-cw/2+150+dx, cy-45), title, font=fb_m, fill=c+(int(255*a),))
        draw.text((cx-cw/2+58+dx, cy+8), desc, font=fb_xs, fill=MUTED+(int(220*a),))

def scene_know(draw,t):
    draw_particles_direct(draw,t)
    transparent_text_scene(draw,"不只要答案，更要你懂", W/2, 155, fb_l, t-0.2, WHITE)
    blocks=[
        ("📖 考点讲解","这道题，考的是什么？给你点破本质",C1,1.0),
        ("💡 解题套路","一类题的思路模板，一题懂一类会",C3,1.8),
        ("⚠️ 易错提醒","最容易埋伏笔的坑，提前帮你拆掉",C4,2.6),
    ]
    y0=300; bh=130
    for i,(title,desc,c,tt) in enumerate(blocks):
        y=y0+i*(bh+30)
        ts=clamp01((t-tt)/0.5)
        if ts<=0: continue
        a=ease_out(ts); w=clamp01((t-tt)/0.8)
        # 三色块从左展开
        x2=lerp(W/2-300, W/2+300, w)
        draw.rounded_rectangle([W/2-300, y, x2, y+bh], radius=18, outline=c+(int(120*a),), width=0,
                               fill=(c[0]//6, c[1]//6, c[2]//6, int(60*a)))
        draw.text((W/2-260, y+22), title, font=fb_m, fill=c+(int(255*a),))
        draw.text((W/2-260, y+80), desc, font=fb_ss, fill=WHITE+(int(230*a),))
    if t>4.0:
        transparent_text_scene(draw,"考点 · 套路 · 易错 —— 真正刷透", W/2, 660, fb_s, t-4.0, C3)

def scene_loop(draw,t):
    draw_particles_direct(draw,t)
    transparent_text_scene(draw,"刷题 → 复盘 → 提升 闭环", W/2, 150, fb_l, t-0.2, WHITE)
    loop4=[
        ("🎲","智能刷题",C1,0.8),("❌","错题本",C5,1.6),
        ("📊","学情洞察",C6,2.4),("🗺️","知识图谱",C3,3.2),
    ]
    # 四方块 + 环形箭头文字
    cx0,cy0=W/2,H/2+20
    R=210
    for i,(ic,title,c,tt) in enumerate(loop4):
        ang=math.radians(-90+i*90)
        bx=cx0+R*math.cos(ang); by=cy0+R*math.sin(ang)
        ts=clamp01((t-tt)/0.5)
        if ts<=0: continue
        a=ease_out(ts)
        draw.rounded_rectangle([bx-65,by-65,bx+65,by+65],radius=18,outline=c+(int(160*a),),width=2)
        draw.text((bx-26,by-40),ic,font=fb_ss,fill=WHITE+(int(255*a),))
        draw.text((bx-text_w(draw,title,fb_xs)/2,by+10),title,font=fb_xs,fill=c+(int(255*a),))
    # 中心
    transparent_text_scene(draw,"薄弱点自动强化", W/2, H/2-20, fb_m, t-1.0, C4)

def scene_road(draw,t):
    draw_particles_direct(draw,t)
    transparent_text_scene(draw,"正在路上 · 即将上线", W/2, 160, fb_l, t-0.2, WHITE)
    roads=[
        ("✅ 海量考场模板",C3,0.8,"已上线 · 100+ 参数化模板"),
        ("✅ 知识讲解",C3,1.6,"已上线 · 83 知识点"),
        ("🎯 试卷训练模式",C4,2.6,"即将上线 · 按福建卷/新课标Ⅰ卷整卷模拟"),
        ("🎯 真题变式精练",C4,3.5,"即将上线 · 一题多变，拆穿套路"),
        ("🎯 薄弱点智能强化",C4,4.4,"即将上线 · AI 个性化巩固推送"),
    ]
    y0=300
    for i,(txt,c,tt,desc) in enumerate(roads):
        ys=clamp01((t-tt)/0.5)
        if ys<=0: continue
        a=ease_out(ys); d=int(lerp(90,0,a))
        draw.text((W/2-460+d, y0), txt, font=fb_m, fill=c+(int(255*a),))
        draw.text((W/2+150, y0+12), desc, font=fb_xs, fill=MUTED+(int(230*a),))
        y0+=70

def scene_end(draw,t):
    draw_particles_direct(draw,t)
    if t>0.5:
        a=ease_out(clamp01((t-0.5)/0.8))
        # 光晕
        r=int(lerp(80,320,ease_out(clamp01(t/3))))
        draw.ellipse([W/2-r*3, H/2-60-r*1.6, W/2+r*3, H/2+60+r*1.6], fill=C2+(int(20*a),))
    transparent_text_scene(draw,"你的", W/2, 250, fb_m, t-0.8, WHITE, glow=True)
    title="高考题厂"
    n=int(clamp01((t-1.2)/0.8)*len(title))
    if t>1.2:
        tw=text_w(draw,title[:n],fb_xl)
        draw.text((W/2-tw/2, 330), title[:n], font=fb_xl, fill=C2)
        # 渐变遮罩效果移除外
    transparent_text_scene(draw,"全免费 · 离线可用 · 每题都讲透", W/2, 540, fb_s, t-2.6, C3, glow=True)
    if t>3.6:
        a=ease_out(clamp01((t-3.6)/0.6))
        # 按钮
        bw, bh = 460, 76
        draw.rounded_rectangle([W/2-bw/2,600,W/2+bw/2,600+bh], radius=38, fill=C3+(int(255*a),))
        draw.text((W/2-text_w(draw,"🚀 立即开始刷题",fb_m)/2, 614), "🚀 立即开始刷题", font=fb_m, fill=DARK)

# ---- 主循环 ----
# 各幕时间线(秒)：开头, 时长
SCENES=[
    scene_open,    # 0
    scene_pain,    # 8
    scene_data,    # 20
    scene_feature, # 32
    scene_know,    # 42
    scene_loop,    # 52
    scene_road,    # 62
    scene_end,     # 73
]
DURATIONS=[8, 12, 10, 10, 10, 10, 11, 9]  # 合计 80s
TOTAL = sum(DURATIONS)
print("总时长:", TOTAL, "秒, 帧数:", TOTAL*FPS)

_bg_cache = None      # 城市图底
_base_cache = {}      # 幕idx -> 静态底图(城市+遮罩+角色预合成)

def _build_base(idx):
    """一次性预合成：城市图 + 深色遮罩 + 二次元角色(静态)。返回RGB底图"""
    global _bg_cache
    if _bg_cache is None:
        try:
            bg = Image.open('assets/city_day.jpg').convert('RGB')
            bw,bh = bg.size; tr = W/H; sr = bw/bh
            if sr > tr:
                nw = int(bh*tr); x0=(bw-nw)//2; bg=bg.crop((x0,0,x0+nw,bh))
            else:
                nh = int(bw/tr); y0=(bh-nh)//2; bg=bg.crop((0,y0,bw,y0+nh))
            _bg_cache = bg.resize((W,H))
        except Exception as e:
            print('背景失败',e); _bg_cache=Image.new('RGB',(W,H),BG)
    base = _bg_cache.copy()
    # 深色遮罩
    mask = Image.new('RGBA',(W,H),(0,0,0,0)); md=ImageDraw.Draw(mask)
    md.rectangle([0,0,W,H], fill=(8,10,22,150))
    md.rectangle([0,int(H*0.42),W,H], fill=(8,10,22,30))
    base = Image.alpha_composite(base.convert('RGBA'), mask).convert('RGB')
    # 角色(二次元)预粘贴
    try:
        ch=Image.open('assets/character.png').convert('RGBA')
        big = idx in (0,7)
        chh = int(H*(0.58 if big else 0.50)); chw=int(chh*ch.width/ch.height)
        ch=ch.resize((chw,chh), Image.LANCZOS)
        if base.mode!='RGBA': base=base.convert('RGBA')
        px,py = W-chw-24, H-chh-16
        base.paste(ch, (px,py), ch)
        base=base.convert('RGB')
    except Exception as e:
        print('角色失败',e)
    return base

def make_frame(t, idx):
    base = _base_cache.get(idx)
    if base is None:
        base = _build_base(idx); _base_cache[idx]=base
    img = base.copy()
    d = ImageDraw.Draw(img, 'RGBA')
    draw_particles_direct(d, t)
    local_t = t - sum(DURATIONS[:idx])
    SCENES[idx](d, local_t)
    return img

import sys
start = int(sys.argv[1]) if len(sys.argv)>1 else 0
end   = int(sys.argv[2]) if len(sys.argv)>2 else TOTAL*FPS
outdir= sys.argv[3] if len(sys.argv)>3 else 'frames'

for fi in range(start, end):
    t = fi / FPS
    # 找当前幕
    acc=0; idx=0
    for i,dur in enumerate(DURATIONS):
        if t < acc+dur: idx=i; break
        acc+=dur
    if t>=TOTAL: idx=len(DURATIONS)-1
    img = make_frame(t, idx)
    # 幕间转场(结尾1.2s alpha出 + 开头alpha进)
    # 淡入：每幕前0.8s从黑
    acc=0
    for i,dur in enumerate(DURATIONS):
        if t>=acc and t<acc+0.8 and i>0:
            a=clamp01((t-acc)/0.8)
            black=Image.new('RGB',(W,H),(8,10,20))
            img=Image.blend(black,img,1-ease_out(1-a))
        if t>=acc and t<acc+dur-0.8 and i<len(DURATIONS)-1 and t-(acc+dur-0.8+0.0)<0:
            pass
        acc+=dur
    # 结尾淡出
    if t>=TOTAL-1.0:
        a=clamp01((t-(TOTAL-1.0))/1.0)
        black=Image.new('RGB',(W,H),(8,10,20))
        img=Image.blend(img,black,a)
    img.save(os.path.join(outdir, f"f{fi+1:05d}.png"))
    if (fi-start)%120==0:
        print(f"  帧 {fi}/{end}  t={t:.1f}s", flush=True)
print("渲染完成", start, "→", end)
