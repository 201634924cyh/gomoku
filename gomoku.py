# -*- coding: utf-8 -*-
"""
五子棋 Gomoku —— pygame 单文件实现

特性
  * 15x15 标准棋盘，木纹程序化生成，棋子为逐像素生成的立体圆石
  * 三种模式：人机(你执黑) / 人机(你执白) / 双人对战
  * 三档 AI 难度：简单 / 普通 / 困难（棋型评分 + 双威胁识别 + 2 层前瞻）
  * 悔棋、重开、鼠标悬停预览、最后一手标记、连五高亮动画
  * 音效全部由 numpy 实时合成，不依赖任何外部素材文件

运行：python gomoku.py
无窗口自检：python gomoku.py --headless --frames 600
版本：python gomoku.py --version
"""

import os
import sys
import math
import random
import argparse

import pygame

__version__ = "1.2"

# --------------------------------------------------------------------------
# 常量与布局
# --------------------------------------------------------------------------
N = 15                      # 棋盘路数
CELL = 40                   # 格距
MARGIN = 46                 # 棋盘内边距
GRID_PX = (N - 1) * CELL   # 560
BOARD_PX = GRID_PX + MARGIN * 2     # 652
HUD_TOP = 78
HUD_BOT = 84
W = BOARD_PX
H = HUD_TOP + BOARD_PX + HUD_BOT    # 814
BOARD_Y = HUD_TOP
STONE_R = 17
STONE_SIZE = STONE_R * 2 + 2

EMPTY, BLACK, WHITE = 0, 1, 2
DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))

# 配色
C_PANEL = (33, 38, 48)
C_PANEL_LINE = (52, 59, 73)
C_TEXT = (232, 236, 244)
C_MUTED = (146, 157, 175)
C_ACCENT = (255, 176, 59)
C_WIN = (232, 88, 74)
C_BTN = (48, 55, 68)
C_BTN_HOVER = (64, 74, 92)
C_BTN_DOWN = (36, 42, 53)
C_WOOD = (222, 179, 127)
C_WOOD_DARK = (212, 168, 115)
C_WOOD_LIGHT = (231, 191, 142)
C_LINE = (92, 62, 36)
C_COORD = (128, 94, 58)

# 跨平台中文界面字体：按「候选路径 → fontconfig 族名 → SysFont」逐级探测，
# 每一级都必须通过字形校验 —— 只有真的画得出汉字才会被采用。
#
# 为什么非要验字形：pygame 的 match_font 会给出「名字沾边、其实没有汉字」的
# 字体（本机实测 dejavusans / arial / liberationsans 一律命中 Arial Narrow），
# 一旦采用，界面中文就会静默变成一屏方框。
# 旧版本的候选末尾是 DejaVuSans.ttf、族名末尾是 arial —— 两者都不含汉字字形，
# 属于「最坏情况的兜底比不兜底还糟」。
FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\Deng.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux（Debian/Ubuntu · Fedora · Arch 的常见安装位置）
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]

# 路径未必覆盖所有发行版，再交给 fontconfig 按族名找一遍。
# 这里刻意不放 dejavusans / arial 这类没有汉字字形的通用族名。
FONT_FAMILIES = ("notosanscjksc,notosanscjk,sourcehansanssc,wqyzenhei,wqymicrohei,"
                 "microsoftyahei,microsoftyaheiui,msyh,simhei,simsun,dengxian,"
                 "pingfangsc,hiraginosansgb,stheiti,heitisc,arialunicodems")

_CJK_PROBE = "汉字测试"        # 探针：这几个字必须渲染出彼此不同的字形
_FONT_CACHE = {}
_warned_no_cjk = False

# ---------------- i18n: bilingual UI (v1.2) ----------------
# 界面文案中英双语：默认中文，`--lang en` 切换英文。
# 常量在模块加载时按 _LANG 求值，因此 --lang 在文件顶部立即解析。
_LANG = "zh"


def set_language(lang):
    global _LANG
    if lang in ("zh", "en"):
        _LANG = lang


def _t(zh, en):
    return en if _LANG == "en" else zh


def _bootstrap_lang():
    argv = sys.argv[1:]
    if "--lang" in argv:
        i = argv.index("--lang")
        if i + 1 < len(argv):
            set_language(argv[i + 1])


_bootstrap_lang()
# ------------------------------------------------------------


MODES = (
    (_t("人机 · 你执黑", "AI · You play Black"), 0),
    (_t("人机 · 你执白", "AI · You play White"), 1),
    (_t("双人对战", "Two Players"), 2),
)
LEVEL_NAMES = ("", _t("简单", "Easy"), _t("普通", "Normal"), _t("困难", "Hard"))

# --------------------------------------------------------------------------
# 棋型分值
# --------------------------------------------------------------------------
FIVE = 10_000_000
OPEN_FOUR = 500_000
RUSH_FOUR = 50_000
LIVE_THREE = 30_000
SLEEP_THREE = 2_000
LIVE_TWO = 1_000
SLEEP_TWO = 200

# (模式, 分值)  —— 按优先级排列，命中即返回
# '1'=自己  '0'=空  '2'=对方或棋盘外
PATTERNS = (
    ("11111", FIVE),
    ("011110", OPEN_FOUR),
    ("011112", RUSH_FOUR), ("211110", RUSH_FOUR),
    ("11011", RUSH_FOUR), ("10111", RUSH_FOUR), ("11101", RUSH_FOUR),
    ("011100", LIVE_THREE), ("001110", LIVE_THREE),
    ("010110", LIVE_THREE), ("011010", LIVE_THREE),
    ("01110", SLEEP_THREE),
    ("001112", SLEEP_THREE), ("211100", SLEEP_THREE),
    ("010112", SLEEP_THREE), ("211010", SLEEP_THREE),
    ("011012", SLEEP_THREE), ("210110", SLEEP_THREE),
    ("10011", SLEEP_THREE), ("11001", SLEEP_THREE), ("10101", SLEEP_THREE),
    ("001100", LIVE_TWO), ("011000", LIVE_TWO), ("000110", LIVE_TWO),
    ("010100", LIVE_TWO), ("001010", LIVE_TWO), ("010010", LIVE_TWO),
    ("01100", SLEEP_TWO), ("00110", SLEEP_TWO),
    ("01010", SLEEP_TWO), ("01000", SLEEP_TWO), ("00010", SLEEP_TWO),
)


# --------------------------------------------------------------------------
# AI —— 棋型扫描
# --------------------------------------------------------------------------
def _window(b, r, c, dr, dc, player):
    """以 (r,c) 为落点，沿 (dr,dc) 取长度 9 的窗口字符串，中心下标为 4。"""
    ch = []
    opp = 3 - player
    for k in range(-4, 5):
        if k == 0:
            ch.append("1")          # 落点视为己方子
            continue
        rr, cc = r + dr * k, c + dc * k
        if not (0 <= rr < N and 0 <= cc < N):
            ch.append("2")          # 棋盘外按被堵处理
            continue
        v = b[rr][cc]
        ch.append("1" if v == player else ("0" if v == EMPTY else "2"))
    return "".join(ch)


def dir_score(b, r, c, dr, dc, player):
    """单方向棋型分：要求匹配到的模式必须覆盖中心落点。"""
    s = _window(b, r, c, dr, dc, player)
    for pat, sc in PATTERNS:
        start = 0
        plen = len(pat)
        while True:
            i = s.find(pat, start)
            if i < 0:
                break
            if i <= 4 < i + plen:
                return sc
            start = i + 1
    return 0


def scan(b, r, c, player):
    return [dir_score(b, r, c, dr, dc, player) for dr, dc in DIRS]


def score_point(b, r, c, player):
    return sum(scan(b, r, c, player))


def makes_five(b, r, c, player):
    for dr, dc in DIRS:
        cnt = 1
        for sgn in (1, -1):
            rr, cc = r + dr * sgn, c + dc * sgn
            while 0 <= rr < N and 0 <= cc < N and b[rr][cc] == player:
                cnt += 1
                rr += dr * sgn
                cc += dc * sgn
        if cnt >= 5:
            return True
    return False


def candidates(b, radius=2):
    stones = [(r, c) for r in range(N) for c in range(N) if b[r][c]]
    if not stones:
        return [(N // 2, N // 2)]
    out, seen = [], set()
    for r, c in stones:
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                rr, cc = r + dr, c + dc
                if 0 <= rr < N and 0 <= cc < N and b[rr][cc] == EMPTY:
                    if (rr, cc) not in seen:
                        seen.add((rr, cc))
                        out.append((rr, cc))
    return out


def evaluate_move(b, r, c, me, threats=True):
    """返回 (综合分值, 我方落此点的攻击分, 对方落此点的攻击分)。"""
    opp = 3 - me
    md = scan(b, r, c, me)
    od = scan(b, r, c, opp)
    my_s = sum(md)
    op_s = sum(od)
    val = my_s * 1.15 + op_s
    if threats:
        n4 = sum(1 for s in md if s >= RUSH_FOUR)
        n3 = sum(1 for s in md if LIVE_THREE <= s < RUSH_FOUR)
        if n4 and n3:
            val += 400_000          # 我形成四三杀
        if n3 >= 2:
            val += 280_000          # 我形成双活三
        o4 = sum(1 for s in od if s >= RUSH_FOUR)
        o3 = sum(1 for s in od if LIVE_THREE <= s < RUSH_FOUR)
        if o4 and o3:
            val += 360_000          # 必须拆掉对手的四三
        if o3 >= 2:
            val += 260_000          # 必须拆掉对手的双活三
    return val, my_s, op_s


def ai_choose(b, me, level):
    cands = candidates(b)
    if not cands:
        return None
    if len(b) and all(b[r][c] == EMPTY for r in range(N) for c in range(N)):
        return (N // 2, N // 2)
    if len(cands) == 1:
        return cands[0]

    opp = 3 - me
    for p in cands:                                  # 能赢立刻赢
        if makes_five(b, p[0], p[1], me):
            return p
    blocks = [p for p in cands if makes_five(b, p[0], p[1], opp)]
    if blocks:                                       # 对手能赢必须堵
        return max(blocks, key=lambda p: score_point(b, p[0], p[1], me))

    scored = []
    for p in cands:
        v = evaluate_move(b, p[0], p[1], me, level >= 2)[0]
        scored.append((v, p))
    scored.sort(key=lambda x: -x[0])

    if level <= 1:
        top = scored[:min(5, len(scored))]
        return random.choice(top)[1]
    if level == 2:
        best = scored[0][0]
        top = [s for s in scored if s[0] >= best * 0.98][:4]
        return random.choice(top)[1]

    # 困难：对候选前 6 手做 2 层前瞻，扣掉对手最佳反击的价值
    refined = []
    for v, p in scored[:6]:
        b[p[0]][p[1]] = me
        opp_best = 0
        for q in candidates(b)[:70]:
            ov = evaluate_move(b, q[0], q[1], opp, False)[1]
            if ov > opp_best:
                opp_best = ov
        b[p[0]][p[1]] = EMPTY
        refined.append((v - opp_best * 0.92, p))
    refined.sort(key=lambda x: -x[0])
    return refined[0][1]


# --------------------------------------------------------------------------
# 资源生成
# --------------------------------------------------------------------------
def build_board_surface():
    surf = pygame.Surface((BOARD_PX, BOARD_PX))
    surf.fill(C_WOOD)
    rng = random.Random(20260918)
    for _ in range(170):                       # 木纹
        y = rng.uniform(-20, BOARD_PX + 20)
        amp = rng.uniform(1.5, 7.0)
        per = rng.uniform(140, 460)
        ph = rng.uniform(0, math.tau)
        col = C_WOOD_DARK if rng.random() < 0.55 else C_WOOD_LIGHT
        pts = [(x, y + amp * math.sin(math.tau * x / per + ph))
               for x in range(0, BOARD_PX + 1, 8)]
        pygame.draw.lines(surf, col, False, pts, 1)

    for i in range(N):                         # 网格
        p = MARGIN + i * CELL
        pygame.draw.line(surf, C_LINE, (MARGIN, p), (MARGIN + GRID_PX, p), 1)
        pygame.draw.line(surf, C_LINE, (p, MARGIN), (p, MARGIN + GRID_PX), 1)
    pygame.draw.rect(surf, C_LINE, (MARGIN, MARGIN, GRID_PX, GRID_PX), 2)

    for r, c in ((3, 3), (3, 11), (11, 3), (11, 11), (7, 7)):   # 星位
        pygame.draw.circle(surf, C_LINE,
                           (MARGIN + c * CELL, MARGIN + r * CELL), 4)

    f = get_font(14)                            # 坐标
    for i in range(N):
        img = f.render(chr(ord("A") + i), True, C_COORD)
        surf.blit(img, img.get_rect(center=(MARGIN + i * CELL, MARGIN - 24)))
        img = f.render(str(i + 1), True, C_COORD)
        surf.blit(img, img.get_rect(center=(MARGIN - 24, MARGIN + i * CELL)))
    return surf


def make_stone(radius, base_rgb):
    """逐像素生成带高光的立体棋子（纯 pygame，无 numpy 依赖）。"""
    size = radius * 2 + 2
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = (size - 1) / 2.0
    lx, ly, lz = -0.42, -0.60, 0.68
    nrm = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / nrm, ly / nrm, lz / nrm
    br, bg, bb = base_rgb
    set_at = surf.set_at
    for y in range(size):
        dy = (y - c) / radius
        for x in range(size):
            dx = (x - c) / radius
            d2 = dx * dx + dy * dy
            a = radius + 0.5 - math.sqrt(d2) * radius
            if a <= 0:
                continue
            if a > 1.0:
                a = 1.0
            z = math.sqrt(max(0.0, 1.0 - d2))
            lam = dx * lx + dy * ly + z * lz
            lam = 0.0 if lam < 0 else (1.0 if lam > 1 else lam)
            k = 0.28 + 0.92 * lam
            spec = (lam ** 16) * 235.0
            set_at((x, y), (
                min(255, int(br * k + spec)),
                min(255, int(bg * k + spec)),
                min(255, int(bb * k + spec)),
                int(a * 255)))
    return surf


def make_shadow(radius):
    size = radius * 2 + 6
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = (size - 1) // 2
    top = radius + 2
    for r in range(top, 0, -1):
        a = int(95 * (1 - r / top) ** 1.6)
        pygame.draw.circle(surf, (20, 12, 4, a), (cx, cy), r)
    return surf


def _img_bytes(surf):
    """取 Surface 的原始字节。pygame 2.1.3 起 tostring 改名 tobytes，两版都兼容。"""
    fn = getattr(pygame.image, "tobytes", None) or pygame.image.tostring
    return fn(surf, "RGBA")


def reset_font_cache():
    """清空字体缓存 —— 重新 pygame.init() 之后必须调用。

    为什么不能指望「取用时验活」：pygame.quit() 会释放底层的 TTF_Font，
    缓存里的 Font 对象随即失效，再拿它 render 会**直接崩在 C 层**（段错误），
    连 Python 异常都抓不住。所以只能在每次初始化之后主动清掉再重新探测。
    """
    _FONT_CACHE.clear()


def font_covers_cjk(font):
    """这个字体真的画得出汉字吗？

    字体缺字时 pygame 会把所有汉字都画成同一个 .notdef 方框（豆腐块），
    所以拿几个不同的汉字渲染出来比字节：只要有两张位图一模一样，就说明
    字体里根本没有汉字字形，绝不能拿它当界面字体。
    """
    try:
        digs = [_img_bytes(font.render(ch, True, (255, 255, 255)))
                for ch in _CJK_PROBE]
    except Exception:
        return False
    return len(set(digs)) == len(digs)


def _warn_no_cjk_font():
    """只提示一次：一个中文字体都没找到时界面会是方框。"""
    global _warned_no_cjk
    if _warned_no_cjk:
        return
    _warned_no_cjk = True
    print("[提示] 系统里没找到含汉字字形的字体，界面中文会显示成方框。\n"
          "       Linux 装一个即可： sudo apt install fonts-noto-cjk",
          file=sys.stderr)


def get_font(size, bold=False):
    """找一个真的能显示汉字的字体；全失败则退回默认字体并给出提示。"""
    key = (size, bold)
    f = _FONT_CACHE.get(key)
    if f is not None:
        return f

    for p in FONT_CANDIDATES:                         # ① 平台常见路径
        if not os.path.exists(p):
            continue
        try:
            cand = pygame.font.Font(p, size)
        except Exception:
            continue
        cand.set_bold(bold)
        if font_covers_cjk(cand):
            _FONT_CACHE[key] = cand
            return cand

    try:                                              # ② fontconfig 按族名
        path = pygame.font.match_font(FONT_FAMILIES, bold=bold)
        if path:
            cand = pygame.font.Font(path, size)
            cand.set_bold(bold)
            if font_covers_cjk(cand):
                _FONT_CACHE[key] = cand
                return cand
    except Exception:
        pass

    try:                                              # ③ SysFont 最后兜底
        cand = pygame.font.SysFont(FONT_FAMILIES, size, bold=bold)
        if font_covers_cjk(cand):
            _FONT_CACHE[key] = cand
            return cand
    except Exception:
        pass

    # 一个汉字都画不出来的字体不能用，宁可退回 pygame 自带字体并明确提示。
    _warn_no_cjk_font()
    f = pygame.font.Font(None, size)
    f.set_bold(bold)
    _FONT_CACHE[key] = f
    return f


def font_regression(bad_path):
    """反事实自检：把候选全换成「没有汉字的字体」，get_font 必须识别出来。

    返回 (bool, str)。旧写法「名字匹配成功就直接用」会让界面静默变成方框，
    这条断言就是防止那种写法复活。
    """
    global FONT_FAMILIES, _warned_no_cjk
    saved_cands = list(FONT_CANDIDATES)
    saved_fams = FONT_FAMILIES
    saved_cache = dict(_FONT_CACHE)
    saved_warned = _warned_no_cjk
    try:
        FONT_CANDIDATES[:] = [bad_path]
        FONT_FAMILIES = "dejavusans,arial,liberationsans"
        _FONT_CACHE.clear()
        # 这个场景注定找不到汉字字体，别刷出误导性的「你的系统没有中文字体」
        _warned_no_cjk = True
        got = get_font(24)
        ref = pygame.font.Font(None, 24)
        same = (_img_bytes(got.render("汉", True, (255, 255, 255)))
                == _img_bytes(ref.render("汉", True, (255, 255, 255))))
        return same, bad_path
    finally:
        FONT_CANDIDATES[:] = saved_cands
        FONT_FAMILIES = saved_fams
        _FONT_CACHE.clear()
        _FONT_CACHE.update(saved_cache)
        _warned_no_cjk = saved_warned


def draw_text(surf, text, size, color, pos, anchor="topleft", bold=False):
    img = get_font(size, bold).render(text, True, color)
    rect = img.get_rect(**{anchor: pos})
    surf.blit(img, rect)
    return rect


# --------------------------------------------------------------------------
# 音效（numpy 合成，缺失则静音）
# --------------------------------------------------------------------------
def _tone(f0, f1, dur, vol, wave="sine", lp=1):
    import numpy as np
    n = int(44100 * dur)
    freq = np.linspace(f0, f1, n)
    phase = np.cumsum(freq) * 2 * math.pi / 44100
    if wave == "square":
        sig = np.sign(np.sin(phase))
    elif wave == "saw":
        sig = 2 * ((phase / (2 * math.pi)) % 1) - 1
    elif wave == "noise":
        sig = np.random.uniform(-1, 1, n)
    else:
        sig = np.sin(phase)
    if lp > 1:
        sig = np.convolve(sig, np.ones(lp) / lp, mode="same")
    env = np.exp(-np.linspace(0, 4.6, n))
    data = np.int16(np.clip(sig * env * vol, -1, 1) * 32767)
    return pygame.sndarray.make_sound(
        np.ascontiguousarray(np.column_stack((data, data))))


def build_sounds():
    sfx = {}
    try:
        import numpy  # noqa: F401
        sfx["black"] = _tone(880, 520, 0.09, 0.32, "square")
        sfx["white"] = _tone(1046, 640, 0.09, 0.28, "square")
        sfx["bad"] = _tone(180, 120, 0.16, 0.30, "saw")
        seq = []
        for f0 in (523, 659, 784, 1046):
            seq.append(_tone(f0, f0 * 1.01, 0.14, 0.26, "sine"))
        sfx["win_seq"] = seq
        sfx["undo"] = _tone(600, 300, 0.08, 0.22, "sine")
    except Exception:
        sfx = {}
    return sfx


# --------------------------------------------------------------------------
# 游戏主体
# --------------------------------------------------------------------------
TRACKED_KEYS = ("K_u", "K_r", "K_m", "K_1", "K_2", "K_3", "K_z", "K_ESCAPE")


class Game:
    def __init__(self, level=2):
        self.level = max(1, min(3, level))
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption(_t("五子棋 Gomoku", "Gomoku"))
        self.clock = pygame.time.Clock()
        self.bg_board = build_board_surface()
        self.stone_black = make_stone(STONE_R, (58, 58, 66))
        self.stone_white = make_stone(STONE_R, (204, 204, 212))
        self.shadow = make_shadow(STONE_R)
        self.sfx = build_sounds()
        self._win_played = False
        self.mode = 0
        self.reset()
        self.running = True
        self.frame = 0
        self.t = 0.0
        self.keys_prev = {}
        self.mouse = (0, 0)
        self.buttons = []
        self.flash = None      # (r, c, 剩余秒数)

    # ---------------- 状态 ----------------
    def reset(self):
        self.board = [[EMPTY] * N for _ in range(N)]
        self.history = []
        self.current = BLACK
        self.state = "playing"
        self.winner = 0
        self.win_line = []
        self.win_t = 0.0
        self.last_move = None
        self.ai_timer = 0.0
        self.ai_thinking = False
        self.flash = None
        self._win_played = False

    @property
    def ai_color(self):
        return WHITE if self.mode == 0 else (BLACK if self.mode == 1 else 0)

    def is_ai_turn(self):
        return (self.mode in (0, 1) and self.state == "playing"
                and self.current == self.ai_color)

    @property
    def human_color(self):
        return BLACK if self.mode == 0 else (WHITE if self.mode == 1 else 0)

    # ---------------- 落子 ----------------
    def place(self, r, c):
        if self.state != "playing":
            return False
        if not (0 <= r < N and 0 <= c < N) or self.board[r][c] != EMPTY:
            self.play("bad")
            self.flash = (r, c, 0.35)
            return False
        p = self.current
        self.board[r][c] = p
        self.history.append((r, c, p))
        self.last_move = (r, c)
        self.play("black" if p == BLACK else "white")
        line = self.check_win(r, c, p)
        if line:
            self.state = "over"
            self.winner = p
            self.win_line = line
            self.win_t = 0.0
        elif len(self.history) == N * N:
            self.state = "over"
            self.winner = 0
        else:
            self.current = 3 - p
        return True

    def check_win(self, r, c, p):
        for dr, dc in DIRS:
            line = [(r, c)]
            for sgn in (1, -1):
                rr, cc = r + dr * sgn, c + dc * sgn
                while 0 <= rr < N and 0 <= cc < N and self.board[rr][cc] == p:
                    line.append((rr, cc))
                    rr += dr * sgn
                    cc += dc * sgn
            if len(line) >= 5:
                return sorted(line)
        return None

    def undo(self):
        if not self.history:
            self.play("bad")
            return
        # 人机模式下一直回退到轮到人类为止（即撤销一整轮）
        while self.history:
            r, c, _ = self.history.pop()
            self.board[r][c] = EMPTY
            nxt = self.history[-1][2] ^ 3 if self.history else BLACK
            if not (self.mode in (0, 1) and nxt == self.ai_color):
                break
        self.current = self.history[-1][2] ^ 3 if self.history else BLACK
        self.state = "playing"
        self.winner = 0
        self.win_line = []
        self.win_t = 0.0
        self.ai_timer = 0.0
        self.ai_thinking = False
        self._win_played = False
        self.last_move = ((self.history[-1][0], self.history[-1][1])
                          if self.history else None)
        self.play("undo")

    def cycle_mode(self):
        self.mode = (self.mode + 1) % len(MODES)
        self.reset()

    def cycle_level(self):
        self.level = self.level % 3 + 1

    def play(self, name):
        s = self.sfx.get(name)
        if s is None:
            return
        try:
            s.play()
        except Exception:
            pass

    # ---------------- 事件 ----------------
    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            self.running = False
        elif ev.type == pygame.MOUSEMOTION:
            self.mouse = ev.pos
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self.mouse = ev.pos
            if self.on_click(ev.pos):
                return
            r, c = self.pixel_to_cell(ev.pos)
            if r is not None and 0 <= r < N and 0 <= c < N:
                if self.mode in (0, 1) and self.current != self.human_color:
                    self.play("bad")
                    return
                self.place(r, c)

    def pixel_to_cell(self, pos):
        x, y = pos
        y -= BOARD_Y
        if not (0 <= x < BOARD_PX and 0 <= y < BOARD_PX):
            return None, None
        c = round((x - MARGIN) / CELL)
        r = round((y - MARGIN) / CELL)
        if not (0 <= r < N and 0 <= c < N):
            return None, None
        cx, cy = MARGIN + c * CELL, MARGIN + r * CELL
        if (x - cx) ** 2 + (y - cy) ** 2 > (CELL * 0.62) ** 2:
            return None, None
        return r, c

    def cell_rect(self, r, c):
        cx = MARGIN + c * CELL
        cy = BOARD_Y + MARGIN + r * CELL
        return pygame.Rect(cx - CELL // 2, cy - CELL // 2, CELL, CELL)

    def on_click(self, pos):
        for rect, key in self.buttons:
            if rect.collidepoint(pos):
                if key == "undo":
                    self.undo()
                elif key == "reset":
                    self.reset()
                elif key == "mode":
                    self.cycle_mode()
                elif key == "level":
                    self.cycle_level()
                return True
        return False

    # ---------------- 更新 ----------------
    def update(self, dt, keys):
        self.frame += 1
        self.t += dt
        if self.flash:
            r, c, t = self.flash
            t -= dt
            self.flash = (r, c, t) if t > 0 else None

        # 键盘（边沿触发，便于无窗口自检）
        for name in TRACKED_KEYS:
            code = getattr(pygame, name)
            down = bool(keys[code])
            if down and not self.keys_prev.get(name, False):
                self.on_key(name)
            self.keys_prev[name] = down

        if self.state == "over":
            self.win_t += dt
            if self.win_line and not self._win_played:
                self._win_played = True
                self.play_win()
            return

        if self.is_ai_turn():
            if not self.ai_thinking:
                self.ai_thinking = True
                self.ai_timer = 0.0
            self.ai_timer += dt
            if self.ai_timer >= (0.28 if self.history else 0.45):
                mv = ai_choose(self.board, self.current, self.level)
                self.ai_thinking = False
                if mv is None:
                    self.state = "over"
                    self.winner = 0
                else:
                    self.place(mv[0], mv[1])
        else:
            self.ai_thinking = False

    def on_key(self, name):
        if name == "K_ESCAPE":
            self.running = False
        elif name == "K_r":
            self.reset()
        elif name == "K_u":
            self.undo()
        elif name == "K_m":
            self.cycle_mode()
        elif name == "K_z":
            self.cycle_level()
        elif name in ("K_1", "K_2", "K_3"):
            self.level = int(name[-1])

    def play_win(self):
        try:
            seq = self.sfx.get("win_seq")
            if not seq:
                return
            for i, s in enumerate(seq):
                ch = pygame.mixer.Channel(i + 1)
                ch.play(s, loops=0)
                ch.set_volume(1.0)
        except Exception:
            pass

    # ---------------- 绘制 ----------------
    def draw(self):
        self.screen.fill(C_PANEL)
        self.screen.blit(self.bg_board, (0, BOARD_Y))
        self.draw_stones()
        if self.state == "over":
            self.draw_dim()          # 先压暗，再画连五高亮，最后盖结算面板
            self.draw_win_fx()
            self.draw_result_panel()
        self.draw_top()
        self.draw_bottom()

    def draw_stones(self):
        hover = None
        if (self.state == "playing" and not self.is_ai_turn()
                and self.mode in (0, 1, 2)):
            r, c = self.pixel_to_cell(self.mouse)
            if r is not None and self.board[r][c] == EMPTY:
                hover = (r, c)

        if self.flash:
            r, c, t = self.flash
            k = t / 0.35
            rad = int(STONE_R + 6 * (1 - k))
            pygame.draw.circle(self.screen, (200, 70, 60),
                               self._cell_center(r, c), rad, 3)

        for r in range(N):
            for c in range(N):
                v = self.board[r][c]
                if v == EMPTY:
                    continue
                cx, cy = self._cell_center(r, c)
                self.screen.blit(self.shadow,
                                 (cx - self.shadow.get_width() // 2 + 2,
                                  cy - self.shadow.get_height() // 2 + 3))
                img = self.stone_black if v == BLACK else self.stone_white
                self.screen.blit(img, (cx - STONE_SIZE // 2, cy - STONE_SIZE // 2))

        if self.last_move and self.state in ("playing", "over"):
            r, c = self.last_move
            cx, cy = self._cell_center(r, c)
            pygame.draw.circle(self.screen, C_WIN, (cx, cy), 4)

        if hover is not None:
            r, c = hover
            cx, cy = self._cell_center(r, c)
            img = (self.stone_black if self.current == BLACK else self.stone_white).copy()
            img.set_alpha(105)
            self.screen.blit(img, (cx - STONE_SIZE // 2, cy - STONE_SIZE // 2))
            pygame.draw.circle(self.screen, C_ACCENT, (cx, cy), STONE_R, 2)

    def draw_win_fx(self):
        if not self.win_line:
            return
        pulse = (math.sin(self.win_t * 5.0) + 1) / 2
        first = self._cell_center(*self.win_line[0])
        last = self._cell_center(*self.win_line[-1])
        width = int(4 + 6 * pulse)
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.line(overlay, (232, 88, 74, int(90 + 90 * pulse)),
                         first, last, width)
        for r, c in self.win_line:
            cx, cy = self._cell_center(r, c)
            rad = int(STONE_R + 4 + 5 * pulse)
            pygame.draw.circle(overlay, (255, 196, 80, int(120 + 100 * pulse)),
                               (cx, cy), rad, 3)
        self.screen.blit(overlay, (0, 0))

    def _cell_center(self, r, c):
        return (MARGIN + c * CELL, BOARD_Y + MARGIN + r * CELL)

    def draw_top(self):
        pygame.draw.rect(self.screen, C_PANEL, (0, 0, W, HUD_TOP))
        pygame.draw.line(self.screen, C_PANEL_LINE, (0, HUD_TOP - 1), (W, HUD_TOP - 1))
        r = draw_text(self.screen, _t("五子棋", "Gomoku"), 26, C_TEXT, (22, 12), bold=True)
        draw_text(self.screen, "GOMOKU", 12, C_MUTED,
                  (r.right + 10, r.centery + 5))

        label = MODES[self.mode][0]
        if self.mode != 2:
            label += " · " + LEVEL_NAMES[self.level]
        f = get_font(14)
        tw = f.size(label)[0]
        rect = pygame.Rect(22, 50, tw + 18, 22)
        pygame.draw.rect(self.screen, (48, 55, 68), rect, border_radius=8)
        draw_text(self.screen, label, 14, C_ACCENT, rect.center, anchor="center")

        # 右侧回合指示
        if self.state == "over":
            txt = _t("对局结束", "Game Over")
            col = C_ACCENT
        elif self.ai_thinking:
            dots = "." * (int(self.t * 3) % 4)
            txt = _t("AI 思考中", "AI thinking") + dots
            col = C_MUTED
        else:
            txt = _t("黑棋回合", "Black turn") if self.current == BLACK else _t("白棋回合", "White turn")
            col = C_TEXT
        f17 = get_font(17)
        tw = f17.size(txt)[0]
        tx = W - 22 - tw
        draw_text(self.screen, txt, 17, col, (W - 22, 27), anchor="midright")
        if self.state != "over":
            icon = self.stone_black if self.current == BLACK else self.stone_white
            shrink = pygame.transform.smoothscale(icon, (24, 24))
            self.screen.blit(shrink, (tx - 34, 27 - 12))

    def draw_bottom(self):
        y0 = BOARD_Y + BOARD_PX
        pygame.draw.rect(self.screen, C_PANEL, (0, y0, W, HUD_BOT))
        pygame.draw.line(self.screen, C_PANEL_LINE, (0, y0), (W, y0))
        self.buttons = []
        specs = ((_t("悔棋", "Undo"), "undo"), (_t("重开", "Restart"), "reset"),
                 (_t("模式", "Mode"), "mode"), (_t("难度", "Level"), "level"))
        bw, bh, gap, x = 96, 42, 10, 20
        y = y0 + 21
        for text, key in specs:
            rect = pygame.Rect(x, y, bw, bh)
            hov = self._in_board_mouse(rect)
            col = C_BTN_HOVER if hov else C_BTN
            pygame.draw.rect(self.screen, col, rect, border_radius=10)
            pygame.draw.rect(self.screen, (70, 80, 99), rect, 1, border_radius=10)
            sub = {"undo": "U", "reset": "R", "mode": "M", "level": "1/2/3"}[key]
            draw_text(self.screen, text, 16, C_TEXT, (rect.centerx, y + 13),
                      anchor="center", bold=True)
            draw_text(self.screen, sub, 11, C_MUTED, (rect.centerx, y + 31),
                      anchor="center")
            self.buttons.append((rect, key))
            x += bw + gap

        info = _t("第 %d 手", "Move %d") % len(self.history)
        draw_text(self.screen, info, 16, C_MUTED, (W - 22, y + 8), anchor="topright")
        draw_text(self.screen, _t("黑棋先行 · 连五为胜", "Black first · Five in a row wins"), 13, (100, 110, 128),
                  (W - 22, y + 27), anchor="topright")

    def _in_board_mouse(self, rect):
        try:
            return rect.collidepoint(pygame.mouse.get_pos())
        except Exception:
            return rect.collidepoint(self.mouse)

    def draw_dim(self):
        overlay = pygame.Surface((W, BOARD_PX), pygame.SRCALPHA)
        overlay.fill((18, 22, 30, 132))
        self.screen.blit(overlay, (0, BOARD_Y))

    def draw_result_panel(self):
        # 面板放到连五线的反方向，避免挡住获胜的五个子
        pw, ph = 404, 168
        if self.win_line:
            avg_r = sum(r for r, _ in self.win_line) / float(len(self.win_line))
        else:
            avg_r = (N - 1) / 2.0
        if avg_r < (N - 1) / 2.0:
            py = BOARD_Y + BOARD_PX - ph - 28
        else:
            py = BOARD_Y + 28
        panel = pygame.Rect((W - pw) // 2, py, pw, ph)

        psurf = pygame.Surface((pw, ph), pygame.SRCALPHA)
        pygame.draw.rect(psurf, (40, 47, 60, 238), psurf.get_rect(), border_radius=16)
        pygame.draw.rect(psurf, (88, 100, 124, 255), psurf.get_rect(), 1,
                         border_radius=16)
        self.screen.blit(psurf, panel.topleft)

        if self.winner == 0:
            title, col = _t("平局", "Draw"), C_TEXT
        else:
            who = _t("黑棋", "Black") if self.winner == BLACK else _t("白棋", "White")
            if self.mode in (0, 1):
                title = _t("你赢了！", "You win!") if self.winner == self.human_color else _t("AI 获胜", "AI wins")
            else:
                title = who + _t("获胜", " wins")
            col = (C_ACCENT if self.mode in (0, 1)
                   and self.winner == self.human_color else C_WIN)
        title_rect = draw_text(self.screen, title, 38, col,
                               (panel.centerx, panel.y + 52),
                               anchor="center", bold=True)
        if self.winner:
            icon = self.stone_black if self.winner == BLACK else self.stone_white
            shrink = pygame.transform.smoothscale(icon, (32, 32))
            self.screen.blit(shrink,
                             (title_rect.left - 44, panel.y + 52 - 16))
        sub = _t("共 %d 手 · %s", "Moves: %d · %s") % (len(self.history), MODES[self.mode][0])
        draw_text(self.screen, sub, 15, C_MUTED, (panel.centerx, panel.y + 92),
                  anchor="center")
        draw_text(self.screen, _t("按 R 重新开始 / U 悔棋", "R restart / U undo"), 14, (128, 140, 160),
                  (panel.centerx, panel.y + 128), anchor="center")

    # ---------------- 主循环 ----------------
    def step(self, dt, keys):
        self.update(dt, keys)
        self.draw()

    def run(self, max_frames=0):
        while self.running:
            for ev in pygame.event.get():
                self.handle_event(ev)
            keys = pygame.key.get_pressed()
            self.step(min(self.clock.tick(60) / 1000.0, 0.05), keys)
            pygame.display.flip()
            if max_frames and self.frame >= max_frames:
                self.running = False


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", action="version", version="gomoku %s" % __version__)
    ap.add_argument("--headless", action="store_true", help=_t("虚拟显示，不弹窗", "headless: no window"))
    ap.add_argument("--frames", type=int, default=0, help=_t("跑够 N 帧后自动退出", "exit after N frames"))
    ap.add_argument("--level", type=int, default=2, choices=(1, 2, 3))
    ap.add_argument("--lang", choices=("zh", "en"), default="zh", help="UI 语言 zh / en")
    args = ap.parse_args()

    if args.headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.init()

    # 重新初始化后旧 Font 已失效，必须清缓存（不清会在 render 时段错误）
    reset_font_cache()
    try:
        pygame.mixer.init()
    except Exception:
        pass
    try:
        pygame.font.init()
    except Exception:
        pass

    g = Game(level=args.level)
    g.run(max_frames=args.frames)

    if args.headless and args.frames:
        pygame.image.save(g.screen,
                          os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "shot_headless.png"))
    pygame.quit()


if __name__ == "__main__":
    main()
