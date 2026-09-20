# -*- coding: utf-8 -*-
"""五子棋无窗口自检：覆盖状态机 / AI 逻辑 / 渲染像素。"""

import os
import sys
import time
import random

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pygame  # noqa: E402

pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()
try:
    pygame.mixer.init()
except Exception:
    pass

import gomoku as G  # noqa: E402

# 重新初始化后旧 Font 已失效，必须清缓存（不清会在 render 时段错误）
G.reset_font_cache()

FAILS = []
OKS = []


def check(name, cond, extra=""):
    if cond:
        OKS.append(name)
    else:
        FAILS.append("%s %s" % (name, extra))
        print("  [FAIL] %s %s" % (name, extra))


class FakeKeys:
    def __init__(self, down=()):
        self.down = set(down)

    def __getitem__(self, k):
        return k in self.down


def frame_keys(*names):
    return FakeKeys([getattr(pygame, n) for n in names])


BLANK = FakeKeys()


def spin(g, frames=1, dt=1 / 60.0, keys=None):
    for _ in range(frames):
        g.step(dt, keys if keys is not None else BLANK)


print("=" * 62)
print("五子棋自检")
print("=" * 62)

# ---------------------------------------------------------------- 1. 棋型扫描
print("\n[1] 棋型评分")

# 活三：已有 3、4 两子，落在 5 位形成活三
b = [[0] * G.N for _ in range(G.N)]
b[7][3] = b[7][4] = G.BLACK
check("活三识别", G.dir_score(b, 7, 5, 0, 1, G.BLACK) == G.LIVE_THREE,
      "got %s" % G.dir_score(b, 7, 5, 0, 1, G.BLACK))
# 活四：已有 3、4、5 三子，落在 6 位形成活四
b[7][5] = G.BLACK
check("活四识别", G.dir_score(b, 7, 6, 0, 1, G.BLACK) == G.OPEN_FOUR,
      "got %s" % G.dir_score(b, 7, 6, 0, 1, G.BLACK))
# 冲四：一端被白子堵死
b[7][2] = G.WHITE
check("冲四识别", G.dir_score(b, 7, 6, 0, 1, G.BLACK) == G.RUSH_FOUR,
      "got %s" % G.dir_score(b, 7, 6, 0, 1, G.BLACK))
# 连五
for c in range(3, 7):
    b[7][c] = G.BLACK
check("连五识别", G.dir_score(b, 7, 7, 0, 1, G.BLACK) == G.FIVE,
      "got %s" % G.dir_score(b, 7, 7, 0, 1, G.BLACK))

b3 = [[0] * G.N for _ in range(G.N)]
for i in range(5):
    b3[5 + i][5 + i] = G.WHITE
check("斜向五连", G.makes_five(b3, 7, 7, G.WHITE))
b4 = [[0] * G.N for _ in range(G.N)]
for i in range(4):
    b4[5 + i][5 + i] = G.WHITE
check("四子不判连五", not G.makes_five(b4, 7, 7, G.WHITE))
check("被堵不算连五", not G.makes_five(b4, 7, 7, G.BLACK))

# ---------------------------------------------------------------- 2. AI 决策
print("\n[2] AI 决策")
# 2.1 空盘走天元
e = [[0] * G.N for _ in range(G.N)]
mv = G.ai_choose(e, G.BLACK, 3)
check("空盘走天元", mv == (7, 7), "got %s" % (mv,))

# 2.2 能连五就连五（白棋 7,3~7,6 四连）
w = [[0] * G.N for _ in range(G.N)]
for c in range(3, 7):
    w[7][c] = G.WHITE
w[6][6] = G.BLACK
w[8][8] = G.BLACK
mv = G.ai_choose(w, G.WHITE, 3)
check("AI 直接连五", mv in ((7, 2), (7, 7)), "got %s" % (mv,))
check("AI 连五有效", mv is not None and G.makes_five(w, mv[0], mv[1], G.WHITE))

# 2.3 冲四必堵：黑 7,3~7,6 四连，7,2 已被白堵，只能堵 7,7
d = [[0] * G.N for _ in range(G.N)]
for c in range(3, 7):
    d[7][c] = G.BLACK
d[7][2] = G.WHITE
d[5][5] = G.WHITE
mv = G.ai_choose(d, G.WHITE, 3)
check("AI 必堵冲四", mv == (7, 7), "got %s" % (mv,))

# 2.4 必须拆活三
t = [[0] * G.N for _ in range(G.N)]
for c in (4, 5, 6):
    t[7][c] = G.BLACK
t[6][6] = G.WHITE
t[8][8] = G.WHITE
mv = G.ai_choose(t, G.WHITE, 3)
check("AI 拆活三", mv in ((7, 3), (7, 7)), "got %s" % (mv,))

# 2.5 只落在空位
rnd = random.Random(7)
b5 = [[0] * G.N for _ in range(G.N)]
for _ in range(16):
    r, c = rnd.randrange(G.N), rnd.randrange(G.N)
    if b5[r][c] == 0:
        b5[r][c] = rnd.choice((G.BLACK, G.WHITE))
mv = G.ai_choose(b5, G.WHITE, 3)
check("AI 落点合法", mv is not None and b5[mv[0]][mv[1]] == 0, "got %s" % (mv,))

# ---------------------------------------------------------------- 3. 超时
print("\n[3] AI 性能")
mid = [[0] * G.N for _ in range(G.N)]
rnd = random.Random(3)
for _ in range(24):
    r, c = rnd.randrange(2, 13), rnd.randrange(2, 13)
    if mid[r][c] == 0:
        mid[r][c] = rnd.choice((G.BLACK, G.WHITE))
for lv in (1, 2, 3):
    t0 = time.perf_counter()
    for _ in range(3):
        G.ai_choose(mid, G.WHITE, lv)
    el = (time.perf_counter() - t0) / 3 * 1000
    check("难度 %d 单步 %.0fms" % (lv, el), el < 1500)
    print("    难度 %d：%.1f ms/步" % (lv, el))

# ---------------------------------------------------------------- 4. 状态机
print("\n[4] 状态机（虚拟显示驱动）")
g = G.Game(level=2)
check("初始状态", g.state == "playing" and len(g.history) == 0)

# 4.1 双人模式：黑连五
g.mode = 2
g.reset()
for c in range(4):
    g.place(7, c, )       # 黑
    g.place(8, c)         # 白
check("未连五不结束", g.state == "playing")
g.place(7, 4)
check("连五判胜", g.state == "over" and g.winner == G.BLACK, "%s/%s" % (g.state, g.winner))
check("连五高亮 5 子", len(g.win_line) == 5, "got %d" % len(g.win_line))
spin(g, 5)
check("结束后仍可渲染", g.frame == 5)
g.place(7, 5)
check("结束后禁止落子", len(g.history) == 9, "got %d" % len(g.history))

# 4.2 悔棋后恢复
g.undo()
check("悔棋恢复对局", g.state == "playing" and g.winner == 0)
check("悔棋退回一手", len(g.history) == 8, "got %d" % len(g.history))

# 4.3 重开
g.reset()
check("重开清空", len(g.history) == 0 and g.state == "playing")

# 4.4 人机模式：AI 自动应手（覆盖 AI 回合分支）
g.mode = 0
g.reset()
g.place(7, 7)                       # 人类执黑
check("人类落子后轮到 AI", g.is_ai_turn())
spin(g, 30, dt=1 / 60.0)            # 0.5 秒足够 AI 出手
check("AI 自动应手", len(g.history) == 2, "got %d" % len(g.history))
check("应手后轮到人类", not g.is_ai_turn())

# 4.5 人机 AI 无子可动时不应卡死：连按悔棋
for _ in range(6):
    g.undo()
check("多次悔棋不崩", isinstance(g.history, list))
spin(g, 3)

# 4.6 模式切换
seen = []
for _ in range(3):
    g.cycle_mode()
    seen.append(g.mode)
check("模式循环", seen == [1, 2, 0], "got %s" % seen)
g.mode = 1
g.reset()
spin(g, 40)                          # 人执白时 AI 执黑先行
check("AI 执黑先行", len(g.history) >= 1, "got %d" % len(g.history))

# 4.7 键盘边沿触发
g.mode = 2
g.reset()
g.place(0, 0)
g.step(1 / 60.0, frame_keys("K_u"))
check("U 键悔棋", len(g.history) == 0, "got %d" % len(g.history))
g.place(0, 0)
g.step(1 / 60.0, frame_keys("K_r"))
check("R 键重开", len(g.history) == 0)
g.step(1 / 60.0, frame_keys("K_m"))
check("M 键换模式", g.mode == 0)
g.step(1 / 60.0, frame_keys("K_1"))
check("1 键设难度", g.level == 1, "got %s" % g.level)
g.step(1 / 60.0, frame_keys("K_2"))
g.step(1 / 60.0, frame_keys("K_3"))
check("3 键设难度", g.level == 3, "got %s" % g.level)
# 按住不放只触发一次
g.mode = 2
g.reset()
g.place(0, 0)
g.step(1 / 60.0, frame_keys("K_u"))
n1 = len(g.history)
g.step(1 / 60.0, frame_keys("K_u"))
check("按键不重复触发", len(g.history) == n1, "%d -> %d" % (n1, len(g.history)))

# 4.8 平局：构造一张无连五的满盘，最后一手落下即平局
g.mode = 2
g.reset()
pat = lambda r, c: G.BLACK if (r + 2 * c) % 4 < 2 else G.WHITE   # noqa: E731
full = [[pat(r, c) for c in range(G.N)] for r in range(G.N)]
no_win = not any(g.check_win(r, c, full[r][c])
                 for r in range(G.N) for c in range(G.N))
check("满盘图案无连五", no_win)
g.board = [[pat(r, c) for c in range(G.N)] for r in range(G.N)]
g.board[0][0] = G.EMPTY
g.history = [(r, c, pat(r, c)) for r in range(G.N) for c in range(G.N)
             if (r, c) != (0, 0)]
g.current = pat(0, 0)
g.state = "playing"
g.place(0, 0)
check("满盘判平局", g.state == "over" and g.winner == 0,
      "%s/%s" % (g.state, g.winner))
spin(g, 3)
check("平局可渲染", g.frame > 0)

# ---------------------------------------------------------------- 5. 渲染
print("\n[5] 渲染与像素")
g = G.Game(level=2)
g.mode = 2
g.reset()
for i in range(4):
    g.place(7, 3 + i)
    g.place(9, 3 + i)
spin(g, 1)
scr = g.screen
check("木纹底色", scr.get_at((6, G.BOARD_Y + 6))[0] > 170,
      str(scr.get_at((6, G.BOARD_Y + 6))))
cx, cy = g._cell_center(7, 3)
px = scr.get_at((cx, cy))
check("黑子像素偏暗", px[0] < 140, str(px))
cx, cy = g._cell_center(9, 3)
px = scr.get_at((cx, cy))
check("白子像素偏亮", px[0] > 160, str(px))

# 顶栏文字不越界
bad = [(x, y) for y in range(0, G.HUD_TOP - 1)
       for x in range(G.W - 6, G.W)
       if tuple(scr.get_at((x, y)))[:3] != G.C_PANEL]
check("顶栏右侧无溢出", not bad, "溢出 %d 点" % len(bad))

# 底栏按钮在窗口内
g.draw_bottom()
for rect, key in g.buttons:
    check("按钮 %s 在窗口内" % key,
          rect.right <= G.W - 2 and rect.bottom <= G.H - 2, str(rect))
last = g.buttons[-1][0]
check("按钮与右侧文字不重叠", last.right < G.W - 150, str(last))

# 深色像素扫描（下棋态，棋盘区不应有大片意外暗斑）
dark = 0
for y in range(G.BOARD_Y, G.BOARD_Y + G.BOARD_PX, 3):
    for x in range(0, G.W, 3):
        p = scr.get_at((x, y))
        if p[0] < 60 and p[1] < 60 and p[2] < 60:
            dark += 1
check("下棋态无异常暗斑", dark < 400, "暗点数 %d" % dark)
print("    下棋态棋盘区采样暗点数：%d" % dark)
pygame.image.save(g.screen, os.path.join(HERE, "shot_play.png"))

# 结果遮罩（走一盘真实的连五胜利，验证高亮动画叠加层级）
g.state = "playing"
g.win_line = []
g.reset()
for i in range(4):
    g.place(7, 3 + i)
    g.place(9, 3 + i)
g.place(7, 7)                       # 黑棋连五
check("真实对局判胜", g.state == "over" and g.winner == G.BLACK)
spin(g, 12)                          # 推进动画到高亮帧
# 面板避让到上半区，取面板内非文字处采样
panel_px = scr.get_at((G.W // 2 - 182, G.BOARD_Y + 48))
check("结果面板着色", panel_px[2] > panel_px[0], str(panel_px))
# 连五高亮环必须亮于被压暗的棋盘底色
ring = scr.get_at(g._cell_center(7, 3))
check("连五高亮未被遮罩压掉", ring[0] > 110, str(ring))
# 面板不能压住获胜的五个子（面板高 168，从 BOARD_Y+28 起）
check("面板避开连五线",
      min(g._cell_center(r, c)[1] for r, c in g.win_line) > G.BOARD_Y + 196,
      "连五线 y=%s" % min(g._cell_center(r, c)[1] for r, c in g.win_line))
pygame.image.save(scr, os.path.join(HERE, "shot_result.png"))

# 空盘
g.state = "playing"
g.win_line = []
g.reset()
spin(g, 1)
pygame.image.save(g.screen, os.path.join(HERE, "shot_empty.png"))
print("    截图：shot_empty.png / shot_play.png / shot_result.png")

# ---------------------------------------------------------------- 6. 长跑
print("\n[6] 连续对局压力")
g = G.Game(level=3)
g.mode = 2
g.reset()
rnd = random.Random(11)
t0 = time.perf_counter()
frames = 0
games = 0
while games < 3 and frames < 4000:
    if g.state == "over":
        games += 1
        g.reset()
    cands = G.candidates(g.board)
    if cands:
        r, c = rnd.choice(cands)
        g.place(r, c)
    spin(g, 1)
    frames += 1
el = time.perf_counter() - t0
check("长跑未死锁", frames < 4000, "用了 %d 帧" % frames)
check("长跑帧率余量", el / max(frames, 1) < 0.05,
      "%.2f ms/帧" % (el / max(frames, 1) * 1000))
print("    %d 帧 / %.1f ms 每帧" % (frames, el / max(frames, 1) * 1000))

# ---------------------------------------------------------------- 7. AI 强度
print("\n[7] AI 实际对局强度")


def playout(black_level, white_level, seed):
    """black_level/white_level 为 None 表示随机乱下。返回 1/2/0。"""
    rnd = random.Random(seed)
    bd = [[0] * G.N for _ in range(G.N)]
    cur = G.BLACK
    while True:
        cands = G.candidates(bd)
        if not cands:
            return 0
        lv = black_level if cur == G.BLACK else white_level
        if lv is None:
            mv = rnd.choice(cands)
        else:
            mv = G.ai_choose(bd, cur, lv)
        bd[mv[0]][mv[1]] = cur
        line = False
        for dr, dc in G.DIRS:
            cnt = 1
            for sgn in (1, -1):
                rr, cc = mv[0] + dr * sgn, mv[1] + dc * sgn
                while 0 <= rr < G.N and 0 <= cc < G.N and bd[rr][cc] == cur:
                    cnt += 1
                    rr += dr * sgn
                    cc += dc * sgn
            if cnt >= 5:
                line = True
        if line:
            return cur
        cur = 3 - cur


wins = [playout(3, None, s) for s in range(4)]
check("困难 AI 全胜随机手", wins.count(G.BLACK) == 4, "战绩 %s" % wins)
wins2 = [playout(3, 1, s) for s in range(3)]
check("困难 AI 压制简单 AI", wins2.count(G.BLACK) >= 2, "战绩 %s" % wins2)
print("    困难 vs 随机：%s 手；困难 vs 简单：%s 手" % (wins, wins2))

# ---------------------------------------------------------------- 8. 鼠标端到端
print("\n[8] 鼠标事件端到端")
g = G.Game(level=1)
g.mode = 0
g.reset()


def click(pos):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    for ev in pygame.event.get():
        g.handle_event(ev)


turns = 0
while g.state == "playing" and turns < 120:
    if not g.is_ai_turn():
        mv = G.ai_choose(g.board, g.human_color, 1)
        click(g._cell_center(mv[0], mv[1]))
    spin(g, 20)
    turns += 1
check("鼠标对局能跑完", g.state == "over", "state=%s turns=%d" % (g.state, turns))
# 弱 AI 对局可能是某一方连五，也可能一路下到满盘平局 —— 两者都算正常结束，
# 不要断言"必须有胜者"，否则这个测试会随机挂。
stones = sum(1 for r in range(G.N) for c in range(G.N) if g.board[r][c])
check("棋盘与手数一致", stones == len(g.history),
      "%d vs %d" % (stones, len(g.history)))
check("终局形态自洽",
      (len(g.win_line) >= 5) if g.winner else (stones == G.N * G.N),
      "winner=%s win_line=%d stones=%d" % (g.winner, len(g.win_line), stones))
print("    %d 回合结束，结果 %s，共 %d 手" % (
    turns, ("胜者 %s" % g.winner) if g.winner else "平局", len(g.history)))

# 点已有棋子的位置应被拒绝
g = G.Game(level=1)
g.mode = 2
g.reset()
click(g._cell_center(7, 7))
n = len(g.history)
click(g._cell_center(7, 7))
check("重复落子被拒绝", len(g.history) == n, "%d -> %d" % (n, len(g.history)))
click((10, 10))
check("点在棋盘外无副作用", len(g.history) == n)

# 点按钮
g.draw_bottom()
undo_btn = [r for r, k in g.buttons if k == "undo"][0]
click(undo_btn.center)
check("点击悔棋按钮", len(g.history) == 0, "got %d" % len(g.history))
mode_btn = [r for r, k in g.buttons if k == "mode"][0]
click(mode_btn.center)
check("点击模式按钮", g.mode == 0, "got %s" % g.mode)
lvl_btn = [r for r, k in g.buttons if k == "level"][0]
l0 = g.level
click(lvl_btn.center)
check("点击难度按钮", g.level != l0 or l0 == 3, "%s -> %s" % (l0, g.level))

# ------------------------------------------------- 中文字体字形校验
bad_path = pygame.font.match_font("dejavusans,arial,liberationsans")
bad_font = None
if bad_path and os.path.exists(bad_path):
    try:
        bad_font = pygame.font.Font(bad_path, 24)
    except Exception:
        bad_font = None
check("反面样本：本机能取到一个「名字沾边但没有汉字字形」的字体",
      bad_font is not None and not G.font_covers_cjk(bad_font),
      "path=%s" % bad_path)
check("探针：默认字体 Font(None) 被正确判定为画不出汉字",
      not G.font_covers_cjk(pygame.font.Font(None, 24)))

usable = None
for _p in G.FONT_CANDIDATES:
    if not os.path.exists(_p):
        continue
    try:
        _pf = pygame.font.Font(_p, 24)
    except Exception:
        continue
    if G.font_covers_cjk(_pf):
        usable = _p
        break
if usable:
    check("正向：系统装了中文字体时，get_font 选中的字体能画出汉字",
          G.font_covers_cjk(G.get_font(24)), "可用候选 %s" % usable)
else:
    print("  [skip] 本机没有任何候选中文字体，正向断言跳过")

if bad_font is not None:
    _same, _src = G.font_regression(bad_path)
    check("反事实：候选全是无汉字字体时退回默认字体，而不是拿来就用",
          _same, "采用了 %s" % _src)
else:
    print("  [skip] 取不到无汉字反面样本，反事实断言跳过")

# ---------------------------------------------------------------- 汇总
print("\n" + "=" * 62)
print("通过 %d 项，失败 %d 项" % (len(OKS), len(FAILS)))
for f in FAILS:
    print("  FAIL: " + f)
print("=" * 62)
pygame.quit()
sys.exit(1 if FAILS else 0)
