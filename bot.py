#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BuildAI Telegram Bot
====================
ИИ (TokenHarbor) строит постройки для Minecraft Bedrock 1.21.50.
Игрок:  /build <что построить>  ->  фото-предпросмотр  ->  кнопка «Беру»  ->  .mcworld
Админ:  /admin  (ключи API, выключить сервис, режим обновления, лимиты, рассылка ...)

Один файл. Зависимости: requests, numpy, Pillow  (см. requirements.txt)
Запуск: BOT_TOKEN=123:ABC python bot.py
"""
import os, sys, io, re, json, math, time, gzip, zlib, struct, threading, hashlib, hmac, zipfile, logging, secrets, traceback
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import numpy as np
import requests
from PIL import Image, ImageDraw

log = logging.getLogger("buildai")

# ═════════════════════════════════════════════════════════════════════════════
#  1. НАСТРОЙКИ (всё меняется переменными окружения)
# ═════════════════════════════════════════════════════════════════════════════
def _env(name, default=""):
    v = os.environ.get(name)
    return default if v is None or v.strip() == "" else v.strip()

BOT_TOKEN      = _env("BOT_TOKEN")
ADMIN_IDS      = [int(x) for x in re.findall(r"-?\d+", _env("ADMIN_IDS", "8859393468"))]
ADMIN_NAME     = _env("ADMIN_USERNAME", "cleanminder").lstrip("@")      # только для показа, доступ — по ID
TG_API         = _env("TG_API", "https://api.telegram.org").rstrip("/")
TH_URL         = _env("TH_URL", "https://tokenharbor.ai/v1/chat/completions")
BOT_VERSION = "2.7-counters"
TASK_CHANNEL = _env("TASK_CHANNEL", "BuildMineAiBot").replace("https://t.me/", "").lstrip("@").strip("/")   # канал для задания
TASK_BONUS = int(_env("TASK_BONUS", "2"))                 # награда за подписку
REF_BONUS = int(_env("REF_BONUS", "1"))                   # награда за одного приглашённого
REF_MAX = int(_env("REF_MAX", "0"))                       # сколько приглашённых засчитывать максимум (0 = без потолка)
PREM_LIMIT_DEFAULT = int(_env("PREMIUM_LIMIT", "15"))     # построек в сутки у Premium
PREM_COOLDOWN = int(_env("PREMIUM_COOLDOWN", "5"))        # пауза между построками у Premium, сек
PREM_CAP = (384, 192, 384)                                # максимальный размер постройки у Premium (X, Y, Z)
FREE_CAP = (128, 128, 128)

# Только эти бесплатные модели TokenHarbor. Игрок выбирает любую через /model.
MODELS = [
    ("deepseek-v4-flash:free",     "DeepSeek V4 Flash"),
    ("deepseek-v4.1-flash:free",   "DeepSeek V4.1 Flash"),
    ("mimo-v2.5:free",             "MiMo V2.5"),
    ("mimo-v2.6-flash:free",       "MiMo V2.6 Flash"),
]
MODEL_IDS = [m[0] for m in MODELS]
MODEL_NAME = dict(MODELS)
TH_MODEL       = _env("TH_MODEL", MODEL_IDS[0])
if TH_MODEL not in MODEL_NAME:
    TH_MODEL = MODEL_IDS[0]
TH_KEYS_ENV    = [k.strip() for k in re.split(r"[,\s]+", _env("TH_KEYS", "")) if k.strip()]
DATA_DIR       = _env("DATA_DIR", "./data")
DAILY_LIMIT    = int(_env("DAILY_LIMIT", "5"))        # построек на человека в сутки (0 = без лимита)
COOLDOWN_SEC   = int(_env("COOLDOWN_SEC", "20"))      # пауза между запросами одного человека
WORKERS        = int(_env("WORKERS", "2"))            # сколько построек одновременно
MAX_QUEUE      = int(_env("MAX_QUEUE", "8"))          # сколько ждёт в очереди максимум
GEN_TIMEOUT    = max(600, int(_env("GEN_TIMEOUT", "720")))      # потолок ожидания ответа ИИ, сек
MAX_TOKENS     = int(_env("MAX_TOKENS", "0"))         # 0 = не передавать
PORT           = int(_env("PORT", "7860"))
WEBHOOK_BASE   = _env("WEBHOOK_URL") or _env("RENDER_EXTERNAL_URL") or (("https://" + _env("SPACE_HOST")) if _env("SPACE_HOST") else "")
TG_BACKUP      = _env("TG_BACKUP", "1") != "0"        # копия состояния закреплённым файлом в чате админа
UTC_OFFSET_H   = int(_env("UTC_OFFSET_H", "5"))       # «сутки» для лимита считаются по этому поясу (Алматы = +5)

# ═════════════════════════════════════════════════════════════════════════════
#  2. БЛОКИ И ПОДСКАЗКА ДЛЯ ИИ (перенесено из BuildAI_v9.html)
# ═════════════════════════════════════════════════════════════════════════════
# блок цвет_бока цвет_верха флаг: n шум, c грубый, s гладкий, w шерсть, b кирпич, p доски, l бревно, g стекло, e свет, t вода
BL = """stone 7d7d7d - n
cobblestone 797979 - c
mossy_cobblestone 6f8a62 - c
stone_bricks 7a7a7a - b
mossy_stone_bricks 6e8266 - b
cracked_stone_bricks 777777 - b
smooth_stone a0a0a0 - s
andesite 888888 - n
diorite bdbdbd - n
granite 956b58 - n
deepslate 4a4a50 - n
deepslate_bricks 3f3f45 - b
polished_deepslate 48484e - s
tuff 6b6c62 - n
bricks 96553f - b
mud_bricks 8a6a52 - b
sandstone dbd3a0 - s
smooth_sandstone e0d8a8 - s
red_sandstone b5602c - s
sand dbd3a0 - n
gravel 857f7d - c
dirt 866043 - n
grass_block 7a5b3a 5f9e3e n
snow f6fafa - s
oak_planks b8945f - p
spruce_planks 7b5a33 - p
birch_planks d5c98c - p
dark_oak_planks 4a2f18 - p
acacia_planks a85a32 - p
bamboo_planks c4b04f - p
crimson_planks 6a3550 - p
oak_log 6b5232 a68a58 l
spruce_log 3e2a14 7b5a33 l
birch_log d8d8d0 d5c98c l
dark_oak_log 3a2a14 4a2f18 l
oak_leaves 4a8a2a - n
spruce_leaves 3b5e3b - n
glass bfe3ee - g
white_concrete cfd5d6 - s
light_gray_concrete 7d7d73 - s
gray_concrete 36393d - s
black_concrete 080a0f - s
red_concrete 8e2121 - s
orange_concrete e06101 - s
yellow_concrete f1af15 - s
lime_concrete 5ea918 - s
green_concrete 495b24 - s
cyan_concrete 157788 - s
light_blue_concrete 2389c6 - s
blue_concrete 2c2e8f - s
purple_concrete 64209c - s
pink_concrete d5658f - s
brown_concrete 60341e - s
white_wool e9ecec - w
red_wool a12722 - w
blue_wool 35399d - w
black_wool 15191d - w
terracotta 985e43 - s
white_terracotta d1b2a1 - s
glowstone f0c070 - e
sea_lantern c9dfd8 - e
lava e8600f - e
water 2f6fe0 - t
quartz_block ece6df - s
obsidian 140c20 - n
netherrack 6f3433 - n
nether_bricks 2c1519 - b
iron_block dcdcdc - s
gold_block f6d03d - s
diamond_block 62d8d0 - s
emerald_block 2ac55a - s
coal_block 101010 - n
hay_block c2a130 - w
copper_block c06c4a - s
prismarine_bricks 63ab9a - b"""


def _hex(h):
    n = int(h, 16)
    return (n >> 16 & 255, n >> 8 & 255, n & 255)


D = {}   # имя -> (цвет бока, цвет верха или None, флаг)
for _ln in BL.strip().split("\n"):
    _n, _s, _u, _f = _ln.split()
    D[_n] = (_hex(_s), None if _u == "-" else _hex(_u), _f)

SYS_PROMPT = """You are a master builder for Minecraft Bedrock 1.21.50. First think the build through in your head: write a plan in Russian, no markdown (size, materials, roof, windows, lights, details). Then output the final build in ONE ```json block:
{"name":"castle","ops":[{"t":"fill","b":"stone_bricks","a":[0,0,0],"c":[20,0,20]},{"t":"hollow","b":"oak_planks","a":[2,1,2],"c":[18,6,18]},{"t":"set","b":"glass","a":[5,3,2]}]}
Rules: x=east, y=up, z=south; integers; start near 0; any size up to 128 per axis. Ops apply in order, later ones overwrite; use b:"air" to carve doors and windows. No stairs, slabs or doors: only full blocks.
Ops:
- "fill": solid box a..c. "hollow": box walls only (interior becomes air). "set": one block at a. "line": straight 3D line of blocks from a to c.
- "cylinder": {"t":"cylinder","b":"stone_bricks","a":[cx,y,cz],"r":5,"h":8,"hollow":false}. Vertical round column; a = centre of the bottom layer, r = radius, h = height; hollow = walls only, open top and bottom.
- "sphere": {"t":"sphere","b":"glass","a":[cx,cy,cz],"r":6,"hollow":true,"half":"top"}. Ball or dome; r may be [rx,ry,rz] for an ellipsoid; half "top" or "bottom" cuts at the centre height (top = dome).
- "mirror": {"t":"mirror","axis":"x","at":10}. Copies everything built so far across the plane axis=at. Use it for symmetric builds: make one half, then mirror.
- "repeat": {"t":"repeat","n":4,"d":[6,0,0],"ops":[...]}. Repeats the nested ops n times, each copy shifted by d (rows of columns, windows, battlements).
First decide what the object is and what makes its silhouette recognizable (a hat = wide flat round brim + narrower taller round crown + a band of another colour; a tree = trunk + round crown; a tower = round or square shaft + roof), and build exactly what was asked, never a generic tower on a platform. If the user attached a photo, reproduce the object from it. Use ONLY these blocks: @@BLOCKS@@. Make it detailed: foundation, pillars, roof (stepped layers or a dome), windows, lights, interior. Prefer fill/hollow/cylinder/sphere over many set ops. Keep the Russian plan short (3-5 lines, no long reasoning). Keep the JSON compact: use repeat, mirror, fill, hollow, cylinder and sphere instead of many set ops, normally at most about 300 ops. Output only the plan and the JSON block, nothing after it. When asked to edit, output the full updated JSON.""".replace("@@BLOCKS@@", ", ".join(D.keys()))

# ═════════════════════════════════════════════════════════════════════════════
#  3. ДВИЖОК ПОСТРОЕК: cylinder/sphere/line/mirror/repeat -> fill/hollow/set -> сетка блоков
# ═════════════════════════════════════════════════════════════════════════════
def rd(v):                       # Math.round из JS (половинки вверх)
    return int(math.floor(v + 0.5))


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) <= 20000


def _fnum(v):                    # аналог унарного плюса в JS
    try:
        f = float(v)
        return f if math.isfinite(f) else float("nan")
    except Exception:
        return float("nan")


class _Budget(Exception):
    pass


def expand(lst, off=None, depth=0, budget=None, cap=30000):
    """Раскрывает сложные операции в простые fill/hollow/set. Возвращает (список, bad)."""
    out = []
    bad = 0
    off = off or [0, 0, 0]
    CAP = cap
    BLIM = 400000 * cap // 30000
    if budget is None:
        budget = [0]

    def okp(p):
        return isinstance(p, (list, tuple)) and len(p) == 3 and all(_num(v) for v in p)

    def push(t, b, a, c):
        budget[0] += 1
        if budget[0] > BLIM:
            raise _Budget()
        if len(out) < CAP:
            out.append({"t": t, "b": b, "a": [rd(v + off[i]) for i, v in enumerate(a)],
                        "c": [rd(v + off[i]) for i, v in enumerate(c)]})

    def spans(f, n, cb):
        s0 = None
        for k in range(-n, n + 2):
            on = k <= n and f(k)
            if on and s0 is None:
                s0 = k
            if not on and s0 is not None:
                cb(s0, k - 1)
                s0 = None

    for o in (lst if isinstance(lst, list) else []):
        if not isinstance(o, dict):
            bad += 1
            continue
        t = o.get("t")
        a = o.get("a") or o.get("from") or o.get("center") or o.get("at")
        c = o.get("c") or o.get("to") or a
        b = str(o.get("b") or o.get("block") or "").replace("minecraft:", "")
        if t in ("fill", "hollow", "set"):
            if not okp(a) or not okp(c):
                bad += 1
                continue
            push(t, b, a, a if t == "set" else c)
        elif t == "line":
            if not okp(a) or not okp(c):
                bad += 1
                continue
            n = max(1, *[abs(c[i] - a[i]) for i in range(3)])
            if n > 1500:
                bad += 1
                continue
            for i in range(int(math.ceil(n)) + 1):
                p = [v + (c[j] - v) * i / n for j, v in enumerate(a)]
                push("set", b, p, p)
        elif t == "cylinder":
            r = _fnum(o.get("r"))
            h = max(1, rd(_fnum(o.get("h")) if o.get("h") else 1))
            if not okp(a) or not (r >= 0) or r > 150 or h > 400:
                bad += 1
                continue
            q, qi, n = (r + .5) ** 2, (r - .5) ** 2, rd(r) + 1
            hl = bool(o.get("hollow")) and r >= 1.5
            for dx in range(-n, n + 1):
                spans(lambda dz: (dx * dx + dz * dz) <= q and (not hl or (dx * dx + dz * dz) > qi), n,
                      lambda z0, z1: push("fill", b, [a[0] + dx, a[1], a[2] + z0], [a[0] + dx, a[1] + h - 1, a[2] + z1]))
        elif t == "sphere":
            rv = o.get("r")
            rr = [_fnum(v) for v in rv] if isinstance(rv, list) else [_fnum(rv)] * 3
            if not okp(a) or len(rr) != 3 or not all(v >= 0 and v <= 120 for v in rr):
                bad += 1
                continue
            rx, ry, rz = [v + .5 for v in rr]
            hl = bool(o.get("hollow")) and all(v >= 1.5 for v in rr)
            half = str(o.get("half") or "")

            def ins(dx, dy, dz, x, y, z):
                return (dx / x) ** 2 + (dy / y) ** 2 + (dz / z) ** 2 <= 1

            n = rd(rz) + 1
            for dx in range(-rd(rx) - 1, rd(rx) + 2):
                for dy in range(-rd(ry) - 1, rd(ry) + 2):
                    if (half == "top" and dy < 0) or (half == "bottom" and dy > 0):
                        continue
                    spans(lambda dz: ins(dx, dy, dz, rx, ry, rz) and not (hl and ins(dx, dy, dz, rx - 1, ry - 1, rz - 1)), n,
                          lambda z0, z1: push("fill", b, [a[0] + dx, a[1] + dy, a[2] + z0], [a[0] + dx, a[1] + dy, a[2] + z1]))
        elif t == "mirror":
            ax = "xyz".find(str(o.get("axis") or "x").lower())
            at = o.get("at")
            if ax < 0 or not _num(at):
                bad += 1
                continue
            pl = at + off[ax]
            for e in list(out):
                a2, c2 = list(e["a"]), list(e["c"])
                a2[ax] = rd(2 * pl - e["a"][ax])
                c2[ax] = rd(2 * pl - e["c"][ax])
                budget[0] += 1
                if budget[0] > BLIM:
                    raise _Budget()
                if len(out) < CAP:
                    out.append({"t": e["t"], "b": e["b"], "a": a2, "c": c2})
        elif t == "repeat":
            nn = _fnum(o.get("n"))
            d = o.get("d") or o.get("step")
            n = min(rd(nn), 100) if nn == nn else 0
            if not (n >= 1) or not okp(d) or not isinstance(o.get("ops"), list) or depth > 3:
                bad += 1
                continue
            for i in range(n):
                sub, sb = expand(o["ops"], [off[0] + d[0] * i, off[1] + d[1] * i, off[2] + d[2] * i], depth + 1, budget, cap)
                bad += sb
                for e in sub:
                    if len(out) < CAP:
                        out.append(e)
        else:
            bad += 1
    return out, bad


def run_spec(spec, prem=False):
    """Превращает JSON ИИ в сетку блоков. Результат: ops, pal, g[x,y,z], d=(X,Y,Z), n, unk, bad."""
    if not isinstance(spec, dict):
        raise ValueError("ИИ вернул не JSON-объект")
    cap = PREM_CAP if prem else FREE_CAP
    unk, ops = set(), []
    try:
        ex, bad = expand(spec.get("ops") or [], cap=(150000 if prem else 30000))
    except _Budget:
        raise ValueError("Постройка слишком сложная (слишком много операций)")
    for o in ex:
        t, a, c = o["t"], o["a"], o["c"]
        b = o["b"]
        if t not in ("fill", "hollow", "set"):
            bad += 1
            continue
        if b != "air" and b not in D:
            unk.add(b)
            b = "stone"
        ops.append({"t": t, "b": b, "a": a, "c": c})
    mn = [10 ** 9] * 3
    for o in ops:
        if o["b"] != "air":
            for i in range(3):
                mn[i] = min(mn[i], o["a"][i], o["c"][i])
    if mn[0] == 10 ** 9:
        raise ValueError("ИИ не вернул ни одного блока")
    for o in ops:
        a, c = [], []
        for i in range(3):
            p, q = o["a"][i] - mn[i], o["c"][i] - mn[i]
            a.append(max(0, min(cap[i] - 1, min(p, q))))
            c.append(max(0, min(cap[i] - 1, max(p, q))))
        o["a"], o["c"] = a, (a if o["t"] == "set" else c)
    T = np.zeros(cap, dtype=np.uint16)
    pal, pi = ["air"], {"air": 0}
    for o in ops:
        v = pi.get(o["b"])
        if v is None:
            v = pi[o["b"]] = len(pal)
            pal.append(o["b"])
        (x1, y1, z1), (x2, y2, z2) = o["a"], o["c"]
        sub = T[x1:x2 + 1, y1:y2 + 1, z1:z2 + 1]
        sub[...] = v
        if o["t"] == "hollow" and min(x2 - x1, y2 - y1, z2 - z1) >= 2:
            sub[1:-1, 1:-1, 1:-1] = 0
    nzx, nzy, nzz = T.any(axis=(1, 2)), T.any(axis=(0, 2)), T.any(axis=(0, 1))
    if not nzx.any():
        raise ValueError("Постройка пустая")
    X, Y, Z = (int(np.nonzero(v)[0].max()) + 1 for v in (nzx, nzy, nzz))
    g = np.ascontiguousarray(T[:X, :Y, :Z])
    return SimpleNamespace(ops=ops, pal=pal, g=g, d=(X, Y, Z), n=int(np.count_nonzero(g)), unk=sorted(unk), bad=bad)


def parse_spec(t):
    f = [m.group(1) for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", t)]
    cands = [f[-1]] if f else []
    i, j = t.find("{"), t.rfind("}")
    if i >= 0 and j > i:
        cands.append(t[i:j + 1])
    for s in cands:
        try:
            v = json.loads(s)
            if isinstance(v, dict):
                return v
        except Exception:
            pass
    raise ValueError("JSON от ИИ оборвался или битый" if ("```" in t or "{" in t) else "ответ оборвался на плане, до постройки модель не дошла")


def salvage_spec(t):
    k = t.rfind("```json")
    b = t[k + 7:] if k >= 0 else t[max(0, t.find("{")):]
    a = b.find('"ops"')
    if a < 0:
        return None
    ops = []
    for m in re.finditer(r"\{[^{}]*\}", b[a:]):
        try:
            o = json.loads(m.group(0))
            if isinstance(o, dict) and o.get("t") and (o.get("a") or o.get("from") or o.get("at")):
                ops.append(o)
        except Exception:
            pass
    if not ops:
        return None
    nm = re.search(r'"name"\s*:\s*"([^"]*)"', b)
    return {"name": nm.group(1) if nm else "build", "ops": ops}


# ===FASTBUILD-BLOCK===
def partial_ops(t):
    """Достаёт все ПОЛНЫЕ операции из недописанного JSON (в том числе repeat с вложенными ops)."""
    k = t.rfind("```json")
    b = t[k + 7:] if k >= 0 else t
    a = b.find('"ops"')
    if a < 0:
        return None
    i = b.find("[", a)
    if i < 0:
        return None
    ops, depth, start, instr, esc = [], 0, -1, False, False
    for j in range(i + 1, len(b)):
        ch = b[j]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                instr = False
            continue
        if ch == '"':
            instr = True
        elif ch == "{":
            if depth == 0:
                start = j
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        o = json.loads(b[start:j + 1])
                        if isinstance(o, dict) and o.get("t"):
                            ops.append(o)
                    except Exception:
                        pass
                    start = -1
        elif ch == "]" and depth == 0:
            break
    if not ops:
        return None
    nm = re.search(r'"name"\s*:\s*"([^"]*)"', b)
    return {"name": nm.group(1) if nm else "build", "ops": ops}


def fmt_int(n):
    return "{:,}".format(int(n)).replace(",", " ")


def progress_text(blocks, elapsed, note="", chars=0):
    t = "🧱 Строю… Это может занять от 5-10 минут…\n\n[Построено %s блоков\nНаписано %s символов]\n⏱ Прошло %d:%02d" % (fmt_int(blocks), fmt_int(chars), elapsed // 60, elapsed % 60)
    if not blocks:
        t += "\n" + ("🧠 ИИ обдумывает постройку, блоки появятся, когда он начнёт писать код…" if chars else "⏳ Жду ответ ИИ…")
    if note:
        t += "\n" + note
    return t + "\n\n🛑 Остановить: /cancel"


# ─── .mcstructure (как в BuildAI_v9.html) ───────────────────────────────────
BLOCK_VERSION = 18168865


def mcstructure_bytes(r):
    o = bytearray()
    w8 = lambda v: o.append(v & 255)
    w16 = lambda v: o.extend(struct.pack("<H", v & 0xFFFF))
    w32 = lambda v: o.extend(struct.pack("<i", v))

    def ws(s):
        e = s.encode("utf-8")
        w16(len(e))
        o.extend(e)

    def hd(t, n):
        w8(t)
        ws(n)

    X, Y, Z = r.d
    N = X * Y * Z
    hd(10, "")
    hd(3, "format_version"); w32(1)
    hd(9, "size"); w8(3); w32(3); w32(X); w32(Y); w32(Z)
    hd(10, "structure")
    hd(9, "block_indices"); w8(9); w32(2)
    w8(3); w32(N)
    o.extend(r.g.astype("<i4").tobytes())          # порядок (x*Y+y)*Z+z — как у numpy C-порядка
    w8(3); w32(N)
    o.extend(np.full(N, -1, dtype="<i4").tobytes())
    hd(9, "entities"); w8(10); w32(0)
    hd(10, "palette"); hd(10, "default"); hd(9, "block_palette"); w8(10); w32(len(r.pal))
    for n in r.pal:
        hd(8, "name"); ws("minecraft:" + n)
        hd(10, "states")
        if n.endswith("_leaves"):
            hd(1, "persistent_bit"); w8(1)
            hd(1, "update_bit"); w8(0)
        w8(0)
        hd(3, "version"); w32(BLOCK_VERSION)
        w8(0)
    hd(10, "block_position_data"); w8(0); w8(0); w8(0); w8(0)
    hd(9, "structure_world_origin"); w8(3); w32(3); w32(0); w32(0); w32(0)
    w8(0)
    return bytes(o)

# ═════════════════════════════════════════════════════════════════════════════
#  4. ФОТО-ПРЕДПРОСМОТР: изометрия на Pillow, два ракурса (с противоположных сторон)
# ═════════════════════════════════════════════════════════════════════════════
def _shade(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))), max(0, min(255, int(c[2] * f))))


def _iso_view(g, pal, k, W, H, ss):
    a = np.ascontiguousarray(np.rot90(g, k, axes=(0, 2)))
    X, Y, Z = a.shape
    n_pal = len(pal)
    trans = np.zeros(n_pal, dtype=bool)
    for i, nm in enumerate(pal):
        if i and D[nm][2] in ("g", "t"):
            trans[i] = True

    def nb(axis):
        n = np.zeros_like(a)
        to, fr = [slice(None)] * 3, [slice(None)] * 3
        to[axis], fr[axis] = slice(0, -1), slice(1, None)
        n[tuple(to)] = a[tuple(fr)]
        return n

    def vis(n):
        return (a != 0) & ((n == 0) | (trans[n] & (n != a)))

    vx, vy, vz = vis(nb(0)), vis(nb(1)), vis(nb(2))
    anyv = vx | vy | vz
    idx = np.argwhere(anyv)
    if len(idx) == 0:
        return Image.new("RGB", (W // ss, H // ss), (156, 196, 238))
    key = (idx[:, 0].astype(np.int64) * Z + idx[:, 2]) * Y + idx[:, 1]
    idx = idx[np.argsort(key, kind="stable")]

    m = 2                                            # поля земли вокруг
    s = min((W * 0.94) / ((X + Z + 2 * m) * 0.8660254), (H * 0.94) / ((X + Z + 2 * m) * 0.5 + Y))
    s = max(2.0, min(s, 60.0 * ss))
    w, h = 0.8660254 * s, 0.5 * s
    cx = (X - Z) * w / 2
    sy_min, sy_max = -2 * m * h - Y * s, (X + Z + 2 * m) * h
    ox, oy = W / 2 - cx, H / 2 - (sy_min + sy_max) / 2

    # небо
    t = np.linspace(0, 1, H)[:, None, None]
    top, bot = np.array([128, 178, 235]), np.array([214, 235, 250])
    sky = (top * (1 - t) + bot * t) * np.ones((1, W, 1))
    img = Image.fromarray(sky.astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img, "RGBA")

    def P(x, y, z):
        return (ox + (x - z) * w, oy + (x + z) * h - y * s)

    # земля: плита с травой и «землёй» по бокам
    fl = [P(-m, 0, -m), P(X + m, 0, -m), P(X + m, 0, Z + m), P(-m, 0, Z + m)]
    d.polygon([P(X + m, 0, -m), P(X + m, 0, Z + m), P(X + m, -1.6, Z + m), P(X + m, -1.6, -m)], fill=(120, 88, 58))
    d.polygon([P(-m, 0, Z + m), P(X + m, 0, Z + m), P(X + m, -1.6, Z + m), P(-m, -1.6, Z + m)], fill=(140, 102, 68))
    d.polygon(fl, fill=(104, 160, 76))
    step = 4 if max(X, Z) <= 48 else 8
    for gx in range(-m, X + m + 1, step):
        d.line([P(gx, 0, -m), P(gx, 0, Z + m)], fill=(90, 142, 66, 255), width=1)
    for gz in range(-m, Z + m + 1, step):
        d.line([P(-m, 0, gz), P(X + m, 0, gz)], fill=(90, 142, 66, 255), width=1)

    colors = {}
    sides = [_hex_free(D[nm][0]) if i else None for i, nm in enumerate(pal)]
    tops = [(_hex_free(D[nm][1]) if D[nm][1] else _hex_free(D[nm][0])) if i else None for i, nm in enumerate(pal)]
    flags = [D[nm][2] if i else "" for i, nm in enumerate(pal)]
    FACE = {"t": 1.0, "l": 0.80, "r": 0.62}
    outline = s >= 3 * ss

    def col(v, face, nz):
        kk = (v, face, nz)
        c = colors.get(kk)
        if c is None:
            base = tops[v] if face == "t" else sides[v]
            f = FACE[face] if flags[v] != "e" else 1.0
            f *= 0.95 + 0.0167 * nz
            c = _shade(base, f)
            fg = flags[v]
            fill = c + ((110,) if fg == "g" else (150,) if fg == "t" else (255,))
            edge = (255, 255, 255, 70) if fg == "g" else (fill[0] * 4 // 5, fill[1] * 4 // 5, fill[2] * 4 // 5, 255)
            c = colors[kk] = (fill, edge)
        return c

    xs, ys, zs = idx[:, 0], idx[:, 1], idx[:, 2]
    nzs = ((xs * 73856093) ^ (ys * 19349663) ^ (zs * 83492791)) % 7
    vals = a[xs, ys, zs]
    FX, FY, FZ = vx[xs, ys, zs], vy[xs, ys, zs], vz[xs, ys, zs]
    sx0 = ox + (xs - zs) * w
    sy0 = oy + (xs + zs) * h - ys * s
    poly = d.polygon
    for i in range(len(xs)):
        x0, y0 = float(sx0[i]), float(sy0[i])
        v, nz = int(vals[i]), int(nzs[i])
        if FY[i]:
            f, e = col(v, "t", nz)
            poly([(x0, y0 - s), (x0 + w, y0 - s + h), (x0, y0 - s + 2 * h), (x0 - w, y0 - s + h)], fill=f, outline=e if outline else None)
        if FZ[i]:
            f, e = col(v, "l", nz)
            poly([(x0 - w, y0 + h), (x0, y0 + 2 * h), (x0, y0 + 2 * h - s), (x0 - w, y0 + h - s)], fill=f, outline=e if outline else None)
        if FX[i]:
            f, e = col(v, "r", nz)
            poly([(x0 + w, y0 + h), (x0, y0 + 2 * h), (x0, y0 + 2 * h - s), (x0 + w, y0 + h - s)], fill=f, outline=e if outline else None)
    return img.resize((W // ss, H // ss), Image.LANCZOS) if ss > 1 else img


def _hex_free(c):
    return c


def render_preview(r, vw=820, vh=720):
    """PNG из двух ракурсов. Возвращает bytes."""
    faces_est = r.n * 2
    ss = 2 if faces_est < 120000 else 1
    img = Image.new("RGB", (vw * 2 + 6, vh), (30, 34, 32))
    for i, k in enumerate((0, 2)):
        v = _iso_view(r.g, r.pal, k, vw * ss, vh * ss, ss)
        img.paste(v, (i * (vw + 6), 0))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=False)
    return buf.getvalue()

# ═════════════════════════════════════════════════════════════════════════════
#  5. .MCWORLD: плоский мир Bedrock с одной постройкой у спавна
#     (чистый Python: свой писатель LevelDB, NBT little-endian, level.dat)
# ═════════════════════════════════════════════════════════════════════════════
# ─── CRC32C (нужен LevelDB) ──────────────────────────────────────────────────
def _crc_table():
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0x82F63B78 if c & 1 else c >> 1
        t.append(c)
    return t


_CRC_T = _crc_table()
try:                                           # если есть быстрый модуль — используем
    import crc32c as _fast_crc

    def crc32c(data, crc=0):
        return _fast_crc.crc32c(data, crc)
except Exception:
    def crc32c(data, crc=0):
        c = crc ^ 0xFFFFFFFF
        T = _CRC_T
        for b in data:
            c = T[(c ^ b) & 0xFF] ^ (c >> 8)
        return c ^ 0xFFFFFFFF


def _mask(c):
    return ((((c >> 15) | (c << 17)) & 0xFFFFFFFF) + 0xA282EAD8) & 0xFFFFFFFF


def _varint(v):
    o = bytearray()
    while v >= 0x80:
        o.append((v & 0x7F) | 0x80)
        v >>= 7
    o.append(v)
    return bytes(o)


# ─── Минимальный писатель LevelDB (один .ldb без сжатия, MANIFEST, CURRENT, пустой .log) ──────────
def _block(entries):
    """Блок LevelDB; каждая запись — точка перезапуска (без префиксного сжатия)."""
    buf, restarts = bytearray(), []
    for k, v in entries:
        restarts.append(len(buf))
        buf += _varint(0) + _varint(len(k)) + _varint(len(v)) + k + v
    for r in restarts or [0]:
        buf += struct.pack("<I", r)
    buf += struct.pack("<I", len(restarts) or 1)
    return bytes(buf)


def _with_trailer(block):
    t = b"\x00"                                  # без сжатия
    return block + t + struct.pack("<I", _mask(crc32c(block + t)))


def leveldb_files(items):
    """items: {ключ(bytes): значение(bytes)} -> {имя файла: bytes} для папки db/."""
    keys = sorted(items)
    seq, ikeys = 0, []
    for k in keys:
        seq += 1
        ikeys.append(k + struct.pack("<Q", (seq << 8) | 1))
    table, index, cur, cur_size, off = bytearray(), [], [], 0, 0

    def flush():
        nonlocal off, cur, cur_size
        if not cur:
            return
        blk = _with_trailer(_block(cur))
        index.append((cur[-1][0], off, len(blk) - 5))
        table.extend(blk)
        off += len(blk)
        cur, cur_size = [], 0

    for ik, k in zip(ikeys, keys):
        v = items[k]
        cur.append((ik, v))
        cur_size += len(ik) + len(v) + 8
        if cur_size >= 4096:
            flush()
    flush()
    meta = _with_trailer(_block([]))
    meta_h = (off, len(meta) - 5)
    table.extend(meta)
    off += len(meta)
    idx = _with_trailer(_block([(k, _varint(o) + _varint(sz)) for k, o, sz in index]))
    idx_h = (off, len(idx) - 5)
    table.extend(idx)
    handles = _varint(meta_h[0]) + _varint(meta_h[1]) + _varint(idx_h[0]) + _varint(idx_h[1])
    table.extend(handles + b"\x00" * (40 - len(handles)) + struct.pack("<Q", 0xDB4775248B80FB57))

    TABLE_NO, MANIFEST_NO, LOG_NO = 3, 2, 4
    edit = (_varint(1) + _varint(len(b"leveldb.BytewiseComparator")) + b"leveldb.BytewiseComparator"
            + _varint(2) + _varint(LOG_NO)
            + _varint(3) + _varint(LOG_NO + 1)
            + _varint(4) + _varint(seq)
            + _varint(7) + _varint(0) + _varint(TABLE_NO) + _varint(len(table))
            + _varint(len(ikeys[0])) + ikeys[0] + _varint(len(ikeys[-1])) + ikeys[-1])
    rec = b"\x01" + edit                         # тип записи FULL + данные
    manifest = struct.pack("<I", _mask(crc32c(rec))) + struct.pack("<H", len(edit)) + rec
    return {
        "CURRENT": ("MANIFEST-%06d\n" % MANIFEST_NO).encode(),
        "MANIFEST-%06d" % MANIFEST_NO: manifest,
        "%06d.ldb" % TABLE_NO: bytes(table),
        "%06d.log" % LOG_NO: b"",
    }


# ─── NBT little-endian ───────────────────────────────────────────────────────
def _ns(s):
    b = s.encode("utf-8")
    return struct.pack("<H", len(b)) + b


def n_byte(n, v): return b"\x01" + _ns(n) + struct.pack("<b", v)
def n_int(n, v): return b"\x03" + _ns(n) + struct.pack("<i", v)
def n_long(n, v): return b"\x04" + _ns(n) + struct.pack("<q", v)
def n_float(n, v): return b"\x05" + _ns(n) + struct.pack("<f", v)
def n_str(n, v): return b"\x08" + _ns(n) + _ns(v)
def n_comp(n, children): return b"\x0a" + _ns(n) + b"".join(children) + b"\x00"
def n_ints(n, vals): return b"\x09" + _ns(n) + b"\x03" + struct.pack("<i", len(vals)) + b"".join(struct.pack("<i", v) for v in vals)


def _block_nbt(name):
    states = []
    if name.endswith("_leaves"):
        states = [n_byte("persistent_bit", 1), n_byte("update_bit", 0)]
    return n_comp("", [n_str("name", "minecraft:" + name), n_comp("states", states), n_int("version", BLOCK_VERSION)])


# ─── Подчанки ────────────────────────────────────────────────────────────────
def _pack_indices(arr):
    """arr: 4096 индексов в порядке x*256+z*16+y  ->  (bits, байты слов)."""
    n = int(arr.max()) + 1
    bits = max(1, (n - 1).bit_length())
    if bits == 7:
        bits = 8
    elif 9 <= bits <= 15:
        bits = 16
    bpw = 32 // bits
    words = -(-4096 // bpw)
    v = np.zeros(words * bpw, dtype=np.uint32)
    v[:4096] = arr
    v = v.reshape(words, bpw) << (np.arange(bpw, dtype=np.uint32) * bits)
    return bits, np.bitwise_or.reduce(v, axis=1).astype("<u4").tobytes()


def _subchunk(block, names, cy):
    """block: [x,y,z] uint16 (16x16x16) с глобальными id; names: id -> имя блока."""
    uniq, inv = np.unique(block, return_inverse=True)
    arr = inv.reshape(block.shape).transpose(0, 2, 1).reshape(-1)
    bits, words = _pack_indices(arr)
    out = bytes([9, 1, cy & 0xFF, bits << 1]) + words + struct.pack("<I", len(uniq))
    return out + b"".join(_block_nbt(names[int(u)]) for u in uniq)


WORLD_MIN_Y = -64
SPAWN = (0, -60, 0)             # игрок появляется здесь (поверхность травы на y=-61)


def build_world_files(r, title, opts=None):
    """Возвращает {путь внутри архива: bytes} для .mcworld."""
    X, Y, Z = r.d
    BX, BY, BZ = 8, -60, -(Z // 2)                       # угол постройки в мире
    # палитра мира
    ground = (opts or {}).get("g") or "grass_block"
    names = ["air", "bedrock", "dirt", ground]
    wp = {n: i for i, n in enumerate(names)}
    lut = np.zeros(len(r.pal), dtype=np.uint16)
    for i, n in enumerate(r.pal):
        if i == 0:
            continue
        if n not in wp:
            wp[n] = len(names)
            names.append(n)
        lut[i] = wp[n]
    G = lut[r.g]                                         # [x,y,z] с id мира
    top_cy = (BY + Y - 1) // 16                          # индекс верхнего подчанка (floor-деление)
    nsub = top_cy - (WORLD_MIN_Y // 16) + 1
    cx0, cx1 = (min(0, BX) - 16) // 16, (BX + X + 16) // 16
    cz0, cz1 = (min(0, BZ) - 16) // 16, (max(0, BZ + Z) + 16) // 16
    items = {}
    for cx in range(cx0, cx1 + 1):
        for cz in range(cz0, cz1 + 1):
            col = np.zeros((16, nsub * 16, 16), dtype=np.uint16)
            col[:, 0, :] = 1
            col[:, 1:3, :] = 2
            col[:, 3, :] = 3
            wx0, wz0 = cx * 16, cz * 16
            x0, x1 = max(wx0, BX), min(wx0 + 16, BX + X)
            z0, z1 = max(wz0, BZ), min(wz0 + 16, BZ + Z)
            if x0 < x1 and z0 < z1:
                y0 = BY - WORLD_MIN_Y
                col[x0 - wx0:x1 - wx0, y0:y0 + Y, z0 - wz0:z1 - wz0] = G[x0 - BX:x1 - BX, :, z0 - BZ:z1 - BZ]
            key = struct.pack("<ii", cx, cz)
            ytop = int(np.nonzero(col.any(axis=(0, 2)))[0].max()) + 1
            items[key + b"\x2c"] = bytes([41])                                    # версия чанка (1.21.40+)
            items[key + b"\x36"] = struct.pack("<i", 2)                           # чанк полностью создан
            items[key + b"\x2b"] = (struct.pack("<256h", *([ytop] * 256))         # карта высот (с запасом)
                                    + (b"\x01" + struct.pack("<I", 1)) * 25)      # биом «равнины» на все 25 секций
            for s in range(nsub):
                blk = col[:, s * 16:(s + 1) * 16, :]
                if s == 0 or blk.any():
                    items[key + b"\x2f" + bytes([(s - 4) & 0xFF])] = _subchunk(blk, names, s - 4)
    # level.dat
    layers = json.dumps({"biome_id": 1, "block_layers": [{"block_name": "minecraft:bedrock", "count": 1},
                                                          {"block_name": "minecraft:dirt", "count": 2},
                                                          {"block_name": "minecraft:" + ground, "count": 1}],
                         "encoding_version": 6, "structure_options": None, "world_version": "version.post_1_18"},
                        separators=(",", ":"))
    now = int(time.time())
    B = n_byte
    root = n_comp("", [
        n_str("BiomeOverride", ""), B("CenterMapsToOrigin", 0), B("ConfirmedPlatformLockedContent", 0),
        n_int("Difficulty", 1), n_str("FlatWorldLayers", layers), B("ForceGameType", 0), n_int("GameType", 1),
        n_int("Generator", 2), n_str("InventoryVersion", "1.21.50"), B("LANBroadcast", 1), B("LANBroadcastIntent", 1),
        n_long("LastPlayed", now), n_str("LevelName", title), B("MultiplayerGame", 1), B("MultiplayerGameIntent", 1),
        n_int("NetherScale", 8), n_int("NetworkVersion", 766), n_int("Platform", 2), n_int("PlatformBroadcastIntent", 3),
        n_long("RandomSeed", 20261121), B("SpawnV1Villagers", 0),
        n_int("SpawnX", SPAWN[0]), n_int("SpawnY", SPAWN[1]), n_int("SpawnZ", SPAWN[2]),
        n_int("StorageVersion", 10), n_long("Time", int((opts or {}).get("t", 6000))), n_int("XBLBroadcastIntent", 3),
        n_str("baseGameVersion", "*"), B("bonusChestEnabled", 0), B("bonusChestSpawned", 0),
        B("commandblockoutput", 1), B("commandblocksenabled", 1), B("commandsEnabled", 1), n_long("currentTick", 0),
        B("dodaylightcycle", 0), B("doentitydrops", 1), B("dofiretick", 0), B("doimmediaterespawn", 0), B("doinsomnia", 0),
        B("domobloot", 1), B("domobspawning", 0), B("dotiledrops", 1), B("doweathercycle", 0), B("drowningdamage", 1),
        n_int("eduOffer", 0), B("educationFeaturesEnabled", 0),
        n_comp("experiments", [B("experiments_ever_used", 0), B("saved_with_toggled_experiments", 0)]),
        B("falldamage", 1), B("firedamage", 1), B("freezedamage", 1), n_int("functioncommandlimit", 10000),
        B("hasBeenLoadedInCreative", 1), B("hasLockedBehaviorPack", 0), B("hasLockedResourcePack", 0),
        B("immutableWorld", 0), B("isCreatedInEditor", 0), B("isExportedFromEditor", 0), B("isFromLockedTemplate", 0),
        B("isFromWorldTemplate", 0), B("isSingleUseWorld", 0), B("isWorldTemplateOptionLocked", 0), B("keepinventory", 1),
        n_ints("lastOpenedWithVersion", [1, 21, 50, 0, 0]), n_float("lightningLevel", 0.0), n_int("lightningTime", 0),
        n_int("limitedWorldDepth", 16), n_int("limitedWorldWidth", 16), n_int("maxcommandchainlength", 65535),
        B("mobgriefing", 0), B("naturalregeneration", 1), n_int("permissionsLevel", 0), n_int("playerPermissionsLevel", 1),
        n_str("prid", ""), B("pvp", 1), n_float("rainLevel", 0.0), n_int("rainTime", 0), n_int("randomtickspeed", 1),
        B("recipesunlock", 0), B("requiresCopiedPackRemovalCheck", 0), B("respawnblocksexplode", 1),
        B("sendcommandfeedback", 1), n_int("serverChunkTickRange", 6), B("showbordereffect", 1), B("showcoordinates", 1),
        B("showdeathmessages", 1), B("showtags", 1), B("spawnMobs", 0), n_int("spawnradius", 10),
        B("startWithMapEnabled", 0), B("texturePacksRequired", 0), B("tntexplodes", 1), B("useMsaGamertagsOnly", 0),
        n_long("worldStartCount", 1), n_comp("worldPolicies", []),
    ])
    files = {"level.dat": struct.pack("<ii", 10, len(root)) + root, "levelname.txt": title.encode("utf-8")}
    for fn, data in leveldb_files(items).items():
        files["db/" + fn] = data
    return files


def build_mcworld_bytes(r, title, opts=None):
    files = build_world_files(r, title, opts)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def safe_name(s, default="build"):
    s = re.sub(r"[^a-z0-9_]+", "_", str(s or "").lower()).strip("_")
    return s[:40] or default

# ═════════════════════════════════════════════════════════════════════════════
#  6. СОСТОЯНИЕ БОТА (файл + копия закреплённым файлом в чате админа)
# ═════════════════════════════════════════════════════════════════════════════
BK_NAME = "buildai_state.json.gz"
START_TS = time.time()


def default_state():
    return {"v": 1, "mode": "on", "mode_msg": "", "model": TH_MODEL, "keys": [], "limit": DAILY_LIMIT,
            "banned": [], "users": {}, "builds": {}, "last": {}, "seq": 0, "bk_msg": 0,
            "prem": {}, "prem_limit": PREM_LIMIT_DEFAULT, "prem_wait": {}, "pay": {}, "prices": {},
            "stats": {"builds": 0, "ok": 0, "fail": 0, "worlds": 0, "structs": 0}}


class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.path = os.path.join(DATA_DIR, "state.json")
        self.d = default_state()
        self.dirty = False
        self.rev = 0

    def load_blob(self, data):
        with self.lock:
            d = default_state()
            d.update({k: v for k, v in data.items() if k in d})
            d["stats"] = {**default_state()["stats"], **(d.get("stats") or {})}
            if d.get("model") not in MODEL_NAME:        # старая/чужая модель из копии → разрешённая
                d["model"] = TH_MODEL
            for u in (d.get("users") or {}).values():
                if u.get("model") and u["model"] not in MODEL_NAME:
                    u.pop("model", None)
            self.d = d
            self._write()

    def load_file(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.load_blob(json.load(f))
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            log.warning("state.json повреждён: %s", e)
            return False

    def _write(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.d, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception as e:
            log.warning("не смог записать state.json: %s", e)

    def save(self):
        with self.lock:
            self._write()
            self.dirty = True
            self.rev += 1


S = State()


def now_ts():
    return int(time.time())


def today():
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + UTC_OFFSET_H * 3600))


def is_admin(uid):
    return uid in ADMIN_IDS


def mask(k):
    return k[:6] + "…" + k[-4:] if len(k) > 12 else k[:2] + "…"


# ═════════════════════════════════════════════════════════════════════════════
#  7. TELEGRAM API
# ═════════════════════════════════════════════════════════════════════════════
class TGError(Exception):
    def __init__(self, desc, code=0, retry_after=0):
        super().__init__(desc)
        self.code, self.retry_after = code, retry_after


class TG:
    def __init__(self):
        self.s = requests.Session()
        self.base = "%s/bot%s/" % (TG_API, BOT_TOKEN)

    def call(self, method, params=None, files=None, timeout=40, tries=3):
        data = {}
        for k, v in (params or {}).items():
            if v is None:
                continue
            data[k] = json.dumps(v) if isinstance(v, (dict, list)) else ("true" if v is True else "false" if v is False else v)
        for i in range(tries):
            try:
                r = self.s.post(self.base + method, data=data, files=files, timeout=timeout)
                try:
                    j = r.json()
                except ValueError:
                    raise TGError("HTTP %s" % r.status_code, r.status_code)
            except requests.RequestException as e:
                if i == tries - 1:
                    raise TGError(str(e))
                time.sleep(1 + i)
                continue
            if j.get("ok"):
                return j.get("result")
            code, ra = j.get("error_code", 0), (j.get("parameters") or {}).get("retry_after", 0)
            if code == 429 and i < tries - 1:
                time.sleep(min(ra + 1, 30))
                continue
            raise TGError(j.get("description", "?"), code, ra)

    # удобные обёртки
    def send(self, chat, text, markup=None, reply_to=None):
        res = None
        text = text or "…"
        chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or ["…"]
        for n, part in enumerate(chunks):
            res = self.call("sendMessage", {"chat_id": chat, "text": part, "reply_markup": markup if n == len(chunks) - 1 else None,
                                            "reply_parameters": {"message_id": reply_to, "allow_sending_without_reply": True} if reply_to and n == 0 else None,
                                            "disable_web_page_preview": True})
        return res

    def edit(self, chat, mid, text, markup=None):
        try:
            return self.call("editMessageText", {"chat_id": chat, "message_id": mid, "text": text[:4000], "reply_markup": markup}, tries=1)
        except TGError as e:
            if "not modified" in str(e):
                return None
            raise

    def safe_edit(self, chat, mid, text, markup=None):
        try:
            return self.edit(chat, mid, text, markup)
        except Exception:
            return None

    def safe_delete(self, chat, mid):
        try:
            self.call("deleteMessage", {"chat_id": chat, "message_id": mid}, tries=1)
        except Exception:
            pass

    def photo(self, chat, png, caption, markup=None):
        return self.call("sendPhoto", {"chat_id": chat, "caption": caption[:1000], "reply_markup": markup},
                         files={"photo": ("preview.png", png, "image/png")}, timeout=90)

    def doc(self, chat, data, filename, caption="", markup=None):
        return self.call("sendDocument", {"chat_id": chat, "caption": caption[:1000], "reply_markup": markup},
                         files={"document": (filename, data, "application/octet-stream")}, timeout=120)


tg = TG()
BOT_USERNAME = ""


def notify_admins(text):
    for a in ADMIN_IDS:
        try:
            tg.send(a, text)
        except Exception:
            pass


_NOTIFIED = {}


def notify_admins_once(kind, text, every=1800):
    if time.time() - _NOTIFIED.get(kind, 0) >= every:
        _NOTIFIED[kind] = time.time()
        notify_admins(text)


# ─── копия состояния в Telegram (на бесплатных хостингах диск стирается при каждом перезапуске) ───────────
BK = {"last": 0.0, "blocked": False}


def backup_now():
    admin = ADMIN_IDS[0]
    with S.lock:
        blob = gzip.compress(json.dumps(S.d, ensure_ascii=False).encode("utf-8"), 6)
        mid = S.d.get("bk_msg")
    if mid:
        try:
            tg.call("editMessageMedia", {"chat_id": admin, "message_id": mid, "media": {"type": "document", "media": "attach://f"}},
                    files={"f": (BK_NAME, blob, "application/gzip")}, timeout=60, tries=2)
            return
        except TGError as e:
            if "not modified" in str(e):
                return
            log.info("правка бэкапа не удалась (%s), шлю новый", e)
    res = tg.call("sendDocument", {"chat_id": admin, "disable_notification": True,
                                   "caption": "🗄 Служебная копия состояния бота (ключи, режим, пользователи). Не удаляйте и не пересылайте."},
                  files={"document": (BK_NAME, blob, "application/gzip")}, timeout=60)
    with S.lock:
        S.d["bk_msg"] = res["message_id"]
    try:
        tg.call("pinChatMessage", {"chat_id": admin, "message_id": res["message_id"], "disable_notification": True}, tries=1)
    except TGError as e:
        log.warning("не смог закрепить копию: %s", e)
    S.save()


def restore_from_tg():
    """'ok' — восстановили, 'none' — копии нет, 'error' — не удалось связаться (бэкап не трогаем)."""
    err = False
    for admin in ADMIN_IDS:
        try:
            chat = tg.call("getChat", {"chat_id": admin}, tries=2)
        except TGError as e:
            log.info("getChat(%s): %s", admin, e)
            err = err or ("chat not found" not in str(e).lower())
            continue
        pm = chat.get("pinned_message") or {}
        doc = pm.get("document") or {}
        if doc.get("file_name") == BK_NAME:
            try:
                f = tg.call("getFile", {"file_id": doc["file_id"]}, tries=2)
                r = requests.get("%s/file/bot%s/%s" % (TG_API, BOT_TOKEN, f["file_path"]), timeout=60)
                r.raise_for_status()
                S.load_blob(json.loads(gzip.decompress(r.content)))
                with S.lock:
                    S.d["bk_msg"] = pm.get("message_id", 0)
                S.save()
                log.info("состояние восстановлено из Telegram")
                return "ok"
            except Exception as e:
                log.warning("восстановление не удалось: %s", e)
                err = True
    return "error" if err else "none"


def backup_loop():
    while True:
        time.sleep(4)
        try:
            if not TG_BACKUP:
                continue
            if BK["blocked"]:
                st = restore_from_tg()
                if st != "error":
                    BK["blocked"] = False
                continue
            with S.lock:
                dirty, rev = S.dirty, S.rev
            if dirty and time.time() - BK["last"] >= 15:
                BK["last"] = time.time()
                backup_now()
                with S.lock:
                    if S.rev == rev:
                        S.dirty = False
        except Exception as e:
            log.warning("бэкап: %s", e)


# ═════════════════════════════════════════════════════════════════════════════
#  8. TOKENHARBOR: ключи, ротация, потоковый запрос
# ═════════════════════════════════════════════════════════════════════════════
class LLMError(Exception):
    def __init__(self, msg, kind="error"):
        super().__init__(msg)
        self.kind = kind


class LLMTimeout(LLMError):
    def __init__(self, msg, partial=""):
        super().__init__(msg, "timeout")
        self.partial = partial


class Cancelled(Exception):
    pass


class HTTPFail(Exception):
    def __init__(self, code, body):
        super().__init__("HTTP %s" % code)
        self.code, self.body = code, body


def add_key(k, note=""):
    with S.lock:
        if any(x["k"] == k for x in S.d["keys"]):
            return False
        S.d["keys"].append({"k": k, "added": now_ts(), "note": note, "off": False, "why": "", "cool": 0, "last": 0, "ok": 0, "err": 0})
    S.save()
    return True


def pick_key(exclude):
    with S.lock:
        t = time.time()
        c = [x for x in S.d["keys"] if not x["off"] and x["cool"] <= t and x["k"] not in exclude]
        if not c:
            return None
        k = min(c, key=lambda x: x["last"])
        k["last"] = t
        return dict(k)


def key_mark(k, **kw):
    with S.lock:
        for x in S.d["keys"]:
            if x["k"] == k["k"]:
                x.update(kw)
    S.save()


def _llm_headers(key):
    return {"Authorization": "Bearer " + key, "Content-Type": "application/json"}


def llm_stream(key, messages, model, on_chunk, cancel, deadline=None, nothink=False):
    body = {"model": model, "messages": messages, "stream": True}
    if nothink and not NOTHINK_BAD[0]:
        body["reasoning"] = {"enabled": False}      # просим шлюз не включать режим рассуждений модели
    if MAX_TOKENS:
        body["max_tokens"] = MAX_TOKENS
    t0 = time.time()
    limit = deadline or (t0 + GEN_TIMEOUT)
    r = requests.post(TH_URL, headers=_llm_headers(key), json=body, stream=True, timeout=(15, 180))
    if r.status_code in (400, 422) and "reasoning" in body:      # шлюз не знает такой параметр: запоминаем и повторяем без него
        NOTHINK_BAD[0] = True
        r.close()
        body.pop("reasoning", None)
        r = requests.post(TH_URL, headers=_llm_headers(key), json=body, stream=True, timeout=(15, 180))
    try:
        if r.status_code != 200:
            raise HTTPFail(r.status_code, r.text[:300])
        if "event-stream" not in r.headers.get("content-type", "").lower():
            j = r.json()
            txt0 = (j.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            if txt0:
                on_chunk(len(txt0), [txt0])
            return txt0
        full, n, rn = [], 0, 0      # n — символы ответа, rn — символы рассуждения модели
        for raw in r.iter_lines(chunk_size=1024):
            if cancel.is_set():
                raise Cancelled()
            if time.time() > limit:
                raise LLMTimeout("ИИ не успел ответить за %d мин. Попробуй запрос попроще или другую модель: /model" % (GEN_TIMEOUT // 60), "".join(full))
            if not raw:
                continue
            line = raw.decode("utf-8", "replace")
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"]
            except Exception:
                continue
            c = delta.get("content")
            if isinstance(delta, dict):
                for k_, v_ in delta.items():
                    if k_ not in ("content", "role") and isinstance(v_, str) and v_:
                        rn += len(v_)
                        if not c:
                            on_chunk(n + rn, full)
            if c:
                full.append(c)
                n += len(c)
                on_chunk(n + rn, full)
        return "".join(full)
    finally:
        r.close()


MODEL_COOL = {}               # модель -> до какого времени считаем её недоступной (в памяти)


def mname(model):
    return MODEL_NAME.get(model, model)


def user_model(uid):
    m = (S.d["users"].get(str(uid)) or {}).get("model")
    return m if m in MODEL_NAME else S.d["model"]


def llm_complete(messages, on_chunk, cancel, model=None, deadline=None, nothink=False):
    model = model if model in MODEL_NAME else S.d["model"]
    if MODEL_COOL.get(model, 0) > time.time():
        raise LLMError("модель «%s» сейчас недоступна. Выбери другую: /model" % mname(model), "model")
    tried, last = set(), ""
    while True:
        k = pick_key(tried)
        if not k:
            raise LLMError(last or "нет рабочих API-ключей TokenHarbor", "nokeys")
        tried.add(k["k"])
        try:
            txt = llm_stream(k["k"], messages, model, on_chunk, cancel, deadline, nothink)
            key_mark(k, ok=k["ok"] + 1)
            return txt
        except (Cancelled, LLMError):
            raise
        except HTTPFail as e:
            last = "TokenHarbor ответил HTTP %s" % e.code
            if e.code == 401:
                key_mark(k, off=True, why="HTTP 401: ключ не принят", err=k["err"] + 1)
                notify_admins_once("keyoff" + mask(k["k"]), "🔑 Ключ %s отключён: TokenHarbor его не принял (HTTP 401).\nПроверь /keys и добавь новый: /addkey <ключ>" % mask(k["k"]))
            elif e.code in (402, 403, 404):
                # у TokenHarbor так отвечает «модель платная / недоступна на тарифе ключа» (как в BuildAI v9):
                # гасим не ключ, а саму модель на 10 минут; остальные модели продолжают работать
                MODEL_COOL[model] = time.time() + 600
                notify_admins_once("model%s%s" % (e.code, model), "💸 TokenHarbor ответил HTTP %s на модель %s: она недоступна для ключа или закончился лимит. Пауза для неё 10 минут, остальные модели работают." % (e.code, model))
                raise LLMError("модель «%s» сейчас недоступна. Выбери другую: /model" % mname(model), "model")
            elif e.code == 429:
                key_mark(k, cool=time.time() + 90, why="HTTP 429, пауза 90 с", err=k["err"] + 1)
            elif e.code >= 500:
                key_mark(k, cool=time.time() + 30, why="HTTP %s, пауза 30 с" % e.code, err=k["err"] + 1)
            else:
                notify_admins_once("badreq" + model, "⚠️ TokenHarbor отклонил запрос (HTTP %s): %s\nМодель: %s" % (e.code, e.body[:200], model))
                raise LLMError("Сервис ИИ отклонил запрос (HTTP %s). Админ уже уведомлён." % e.code, "bad")
        except requests.RequestException as e:
            last = "нет связи с TokenHarbor"
            key_mark(k, cool=time.time() + 15, why="сеть: %s" % str(e)[:60])


def test_key(key, model=None):
    """Проверка ключа одним крошечным запросом. -> (ok, текст)"""
    try:
        r = requests.post(TH_URL, headers=_llm_headers(key), timeout=30,
                          json={"model": model or S.d["model"], "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1})
        if r.status_code == 200:
            return True, "работает"
        return False, "HTTP %s %s" % (r.status_code, r.text[:100].replace("\n", " "))
    except Exception as e:
        return False, "сеть: %s" % str(e)[:80]


# ===SETTINGS-BLOCK===
NOTHINK_BAD = [False]          # шлюз ответил 400/422 на параметр reasoning: дальше не шлём его


def sys_prompt(prem, think=True):
    p = SYS_PROMPT_PREM if prem else SYS_PROMPT
    if think:
        return p
    p = p.replace("First think the build through in your head: write a plan in Russian, no markdown (size, materials, roof, windows, lights, details). Then output the final build in ONE ```json block:",
                  "Do not write any plan, reasoning or explanation. Output ONLY the final build in ONE ```json block, nothing before it:")
    p = p.replace("Keep the Russian plan short (3-5 lines, no long reasoning). ", "")
    p = p.replace("Output only the plan and the JSON block, nothing after it.", "Output only the JSON block, nothing after it.")
    return p + " IMPORTANT: no plan and no thinking text. Start your reply directly with ```json."


def generate_spec(q, history, on_chunk, cancel, status, model=None, prem=False, think=True):
    base = [{"role": "system", "content": sys_prompt(prem, think)}] + list(history or [])
    err, best = None, None
    deadline = time.time() + GEN_TIMEOUT          # общий потолок на все попытки вместе
    for i in range(3):
        if i:
            if deadline - time.time() < 90:       # на ещё одну попытку времени не осталось
                break
            status("🔁 Ответ оборвался, пробую ещё раз (%d/2)…" % i)
        if not i:
            user = q
        elif think:
            user = q + "\n\n(Прошлый ответ оборвался. Теперь без длинного плана: одна строка плана и сразу один компактный ```json блок. Используй fill/hollow, не больше 120 операций.)"
        else:
            user = q + "\n\n(Прошлый ответ оборвался. Теперь сразу один компактный ```json блок, без плана. Используй fill/hollow, не больше 120 операций.)"
        try:
            text = llm_complete(base + [{"role": "user", "content": user}], on_chunk, cancel, model, deadline, not think)
        except LLMTimeout as e:
            text = e.partial or ""
            try:
                return parse_spec(text), False
            except ValueError:
                pass
            sp = partial_ops(text) or salvage_spec(text)
            if sp and (not best or len(sp["ops"]) > len(best["ops"])):
                best = sp
            if not best:
                raise
            break
        try:
            return parse_spec(text), False
        except ValueError as e:
            err = e
            sp = partial_ops(text) or salvage_spec(text)
            if sp and (not best or len(sp["ops"]) > len(best["ops"])):
                best = sp
    if best:
        return best, True
    raise LLMError("%s. Попробуй ещё раз." % err, "bad")


# ═════════════════════════════════════════════════════════════════════════════
#  9. ПОЛЬЗОВАТЕЛИ, ЛИМИТЫ, ОЧЕРЕДЬ
# ═════════════════════════════════════════════════════════════════════════════
FAST = ThreadPoolExecutor(max_workers=8, thread_name_prefix="fast")
BUILD = ThreadPoolExecutor(max_workers=max(1, WORKERS), thread_name_prefix="build")
_plock = threading.Lock()
PENDING = [0]                 # сколько построек в очереди + в работе
ACTIVE = {}                   # uid -> threading.Event (отмена)
_seen = []                    # дедупликация update_id


def touch_user(u):
    uid = str(u["id"])
    with S.lock:
        us = S.d["users"].get(uid)
        changed = False
        if us is None:
            us = S.d["users"][uid] = {"u": "", "n": "", "first": now_ts(), "day": "", "cnt": 0, "tot": 0}
            changed = True
        un, nm = (u.get("username") or ""), (u.get("first_name") or "")
        if us["u"] != un or us["n"] != nm:
            us["u"], us["n"] = un, nm
            changed = True
        us["last"] = now_ts()
        _apply_prem_wait(uid, un)
        if us["day"] != today():
            us["day"], us["cnt"] = today(), 0
    if changed:
        S.save()


def used_today(uid):
    us = S.d["users"].get(str(uid))
    return us["cnt"] if us and us["day"] == today() else 0


def bump(uid, delta):
    with S.lock:
        us = S.d["users"].setdefault(str(uid), {"u": "", "n": "", "first": now_ts(), "day": today(), "cnt": 0, "tot": 0})
        if us["day"] != today():
            us["day"], us["cnt"] = today(), 0
        us["cnt"] = max(0, us["cnt"] + delta)
        us["tot"] = max(0, us.get("tot", 0) + delta)
    S.save()


def service_block(uid):
    if is_admin(uid):
        return None
    m, why = S.d["mode"], S.d.get("mode_msg") or ""
    if m == "off":
        return "⛔ Сервис сейчас выключен." + ("\n" + why if why else "") + "\nЗагляни позже."
    if m == "update":
        return "🔧 Сервис на обновлении." + ("\n" + why if why else "") + "\nСкоро вернёмся, попробуй чуть позже."
    return None


def clean_text(s):
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()[:400]


def build_markup(bid, prem=False):
    rows = [[{"text": "✅ Беру — пришли мир (.mcworld)", "callback_data": "ok:" + bid}]]
    if prem:
        rows.append([{"text": "🏠 Вид изнутри", "callback_data": "in:" + bid}, {"text": "🗺 Вид сверху", "callback_data": "td:" + bid}])
        rows.append([{"text": "🔎 ×2", "callback_data": "zm:%s:2" % bid}, {"text": "🔎 ×3", "callback_data": "zm:%s:3" % bid},
                     {"text": "✨ Улучшить", "callback_data": "up:" + bid}])
    else:
        rows.append([{"text": "🔒 Вид изнутри", "callback_data": "pl:in"}, {"text": "🔒 Вид сверху", "callback_data": "pl:td"}])
        rows.append([{"text": "⭐ Premium: карты до 384×384, 15 в день", "callback_data": "pl:pm"}])
    rows.append([{"text": "🔁 Заново", "callback_data": "re:" + bid}, {"text": "📦 .mcstructure", "callback_data": "st:" + bid}])
    return {"inline_keyboard": rows}


def new_build_id():
    with S.lock:
        S.d["seq"] += 1
        return format(S.d["seq"], "x") + secrets.token_hex(2)


def store_build(uid, q, spec, hist, prem=False, zoom=1):
    bid = new_build_id()
    with S.lock:
        S.d["builds"][bid] = {"uid": uid, "q": q, "ts": now_ts(), "spec": {"name": spec.get("name", "build"), "ops": spec.get("ops", [])},
                              "h": hist, "prem": bool(prem), "zoom": int(zoom)}
        S.d["last"][str(uid)] = bid
        if len(S.d["builds"]) > 60:
            for old in sorted(S.d["builds"], key=lambda b: S.d["builds"][b]["ts"])[:len(S.d["builds"]) - 60]:
                S.d["builds"].pop(old, None)
    S.save()
    return bid


def try_start_build(chat, uid, q, history=None, reply_to=None):
    """Проверки и постановка в очередь. history — список сообщений для /edit."""
    blk = service_block(uid)
    if blk:
        return tg.send(chat, blk)
    if uid in S.d["banned"]:
        return tg.send(chat, "🚫 Доступ закрыт.")
    if uid in ACTIVE:
        return tg.send(chat, "⏳ Твоя прошлая постройка ещё делается. Дождись её или /cancel.")
    prem = is_prem(uid)
    charge = not is_admin(uid) and not (prem and bool(history))      # у Premium правки бесплатны
    if not is_admin(uid):
        lim = eff_limit(uid)
        if charge and lim and used_today(uid) >= lim and bonus_of(uid) <= 0:
            tail = "" if prem else "\n⭐ С Premium — %d построек в день, огромные карты и виды сверху/изнутри: /premium" % S.d["prem_limit"]
            return tg.send(chat, "📅 На сегодня лимит построек исчерпан (%d). Завтра будет новый.%s\n🎁 Бесплатные запросы: пригласи друга или выполни задание → /free" % (lim, tail))
        us = S.d["users"].get(str(uid), {})
        wait = (PREM_COOLDOWN if prem else COOLDOWN_SEC) - (time.time() - us.get("lastbuild", 0))
        if wait > 0:
            return tg.send(chat, "⏱ Подожди ещё %d с перед следующей постройкой.%s" % (math.ceil(wait), "" if prem else "\n⭐ У Premium пауза всего %d с: /premium" % PREM_COOLDOWN))
    pos = 0
    if not prem:
        with _plock:
            if PENDING[0] >= WORKERS + MAX_QUEUE:
                return tg.send(chat, "🚦 Сейчас много желающих, очередь заполнена. Попробуй через пару минут.\n⭐ У Premium своя очередь без ожидания: /premium")
            PENDING[0] += 1
            pos = PENDING[0]
    ev = threading.Event()
    ACTIVE[uid] = ev
    if charge:
        charge_build(uid)
    if not is_admin(uid):
        with S.lock:
            if str(uid) in S.d["users"]:
                S.d["users"][str(uid)]["lastbuild"] = time.time()
    if pos > WORKERS:
        tg.send(chat, "🚦 Ты в очереди (впереди %d). Начну, как только освободится место." % (pos - WORKERS))
    (BUILD_PREM if prem else BUILD).submit(job_build, chat, uid, q, history or [], ev, charge, "prem" if prem else "free")


def job_build(chat, uid, q, history, cancel, charge=True, slot="free"):
    t0 = time.time()
    mid = None
    refund = True
    prem = is_prem(uid)
    stop_pulse = threading.Event()
    pth = None
    try:
        prog = {"blocks": 0, "ops": 0, "chars": 0, "parts": None, "note": ""}
        mid = tg.send(chat, progress_text(0, 0))["message_id"]

        def status(t):
            prog["note"] = t
            tg.safe_edit(chat, mid, progress_text(prog["blocks"], int(time.time() - t0), t, prog["chars"]))

        def on_chunk(n, parts=None):
            prog["chars"] = max(prog["chars"], n)
            if parts is not None:
                prog["parts"] = parts

        def pulse():
            shown = ""
            while not stop_pulse.wait(5):
                try:
                    parts = prog["parts"]
                    if parts is not None:
                        sp = partial_ops("".join(parts))
                        if sp and len(sp["ops"]) != prog["ops"]:
                            prog["ops"] = len(sp["ops"])
                            rr = run_spec(sp, prem)
                            prog["blocks"] = max(prog["blocks"], rr.n)
                except Exception:
                    pass
                txt = progress_text(prog["blocks"], int(time.time() - t0), prog["note"], prog["chars"])
                if txt != shown:
                    shown = txt
                    tg.safe_edit(chat, mid, txt)

        with S.lock:
            S.d["stats"]["builds"] += 1
        model = user_model(uid)
        pth = threading.Thread(target=pulse, daemon=True, name="pulse")
        pth.start()
        try:
            spec, part = generate_spec(q, history, on_chunk, cancel, status, model, prem, user_think(uid))
        finally:
            stop_pulse.set()
            pth.join(timeout=20)
        r = run_spec(spec, prem)
        tg.safe_edit(chat, mid, "🎨 Построено %s блоков. Рисую предпросмотр…" % fmt_int(r.n))
        png = render_preview_any(r)
        hist = [{"role": "user", "content": q}, {"role": "assistant", "content": json.dumps({"name": spec.get("name", "build"), "ops": spec.get("ops", [])}, ensure_ascii=False)}]
        bid = store_build(uid, q, spec, hist, prem)
        cap = "✅ %s\n🧱 %d блоков · %d×%d×%d\n🤖 %s (сменить: /model)" % (spec.get("name") or "Постройка", r.n, *r.d, mname(model))
        if max(r.d) > 128:
            cap += "\n🔍 Превью уменьшено, в мире будет полный размер."
        if part:
            cap += "\n⚠ Ответ ИИ оборвался, показана собранная часть. Нажми «Заново» или попроси достроить: /edit …"
        if r.unk:
            cap += "\n⚠ Неизвестные блоки заменены камнем: " + ", ".join(r.unk[:6])
        cap += "\n\nНравится? Жми «Беру» — пришлю мир с постройкой у спавна.\nХочешь поменять — напиши /edit что изменить."
        if not prem:
            if CITY_RE.search(q) or max(r.d[0], r.d[2]) >= 120:
                cap += "\n\n💡 Для большой карты (город, РП) нужен Premium: до 384×384 и вид сверху → /premium"
            else:
                cap += "\n\n⭐ Premium: вид изнутри, карты 384×384, 15 в день → /premium"
        send_previews(chat, r, cap, bid, prem, png)
        tg.safe_delete(chat, mid)
        refund = False
        with S.lock:
            S.d["stats"]["ok"] += 1
        S.save()
    except Cancelled:
        if mid:
            tg.safe_edit(chat, mid, "🛑 Остановлено. Попытка не списана.")
    except (LLMError, ValueError) as e:
        with S.lock:
            S.d["stats"]["fail"] += 1
        msg = "😕 Не получилось: %s\nПопытка не списана." % e
        if mid:
            tg.safe_edit(chat, mid, msg)
        else:
            tg.send(chat, msg)
        if isinstance(e, LLMError) and e.kind == "nokeys":
            notify_admins_once("nokeys", "🚨 Нет рабочих ключей TokenHarbor — игроки получают ошибки.\n/keys — посмотреть, /addkey <ключ> — добавить, /off — выключить сервис.")
    except Exception as e:
        log.error("job_build: %s", traceback.format_exc())
        with S.lock:
            S.d["stats"]["fail"] += 1
        msg = "⚠️ Внутренняя ошибка, попытка не списана. Попробуй ещё раз."
        if mid:
            tg.safe_edit(chat, mid, msg)
        else:
            try:
                tg.send(chat, msg)
            except Exception:
                pass
        notify_admins_once("crash", "🐞 Ошибка в боте: %s: %s" % (type(e).__name__, str(e)[:200]), every=600)
    finally:
        stop_pulse.set()
        if refund and charge and not is_admin(uid):
            refund_charge(uid)
        ACTIVE.pop(uid, None)
        if slot == "free":
            with _plock:
                PENDING[0] = max(0, PENDING[0] - 1)


# ═════════════════════════════════════════════════════════════════════════════
#  10. КОМАНДЫ ИГРОКОВ
# ═════════════════════════════════════════════════════════════════════════════
HELP = ("👋 Я строю постройки для Minecraft Bedrock с помощью ИИ.\n\n"
        "🧱 /build <что построить> — например:\n/build средневековый замок с башнями и рвом\n\n"
        "✏️ /edit <что поменять> — доработать последнюю постройку\n"
        "🤖 /model — выбрать ИИ (4 бесплатные модели)\n"
        "⚙️ /settings — настройки: режим «Размышления»\n"
        "🛑 /cancel — остановить текущую\n"
        "📊 /me — лимит, статус и твой Premium\n🎁 /free — бесплатные запросы: пригласи друга или выполни задание\n⭐ /premium — Premium: огромные карты, вид изнутри и сверху, 15 в день\n🌍 /world — тема мира (Premium)\n\n"
        "Как это работает: ИИ строит → я присылаю фото-предпросмотр → если нравится, жмёшь «Беру» и получаешь .mcworld "
        "(мир для Minecraft Bedrock 1.21.50) с единственной этой постройкой у спавна.")


def cmd_build(chat, uid, arg, reply_to):
    q = clean_text(arg)
    if len(q) < 3:
        return tg.send(chat, "Напиши, что построить. Например:\n/build уютный дом с садом и забором")
    try_start_build(chat, uid, q, None, reply_to)


def cmd_edit(chat, uid, arg, reply_to):
    q = clean_text(arg)
    if len(q) < 3:
        return tg.send(chat, "Напиши, что изменить. Например:\n/edit сделай крышу красной и добавь башню")
    bid = S.d["last"].get(str(uid))
    b = S.d["builds"].get(bid) if bid else None
    if not b:
        return tg.send(chat, "Сначала построй что-нибудь: /build <описание>")
    try_start_build(chat, uid, q, b["h"], reply_to)


def model_markup(cur):
    rows = [[{"text": ("✅ " if mid == cur else "") + title, "callback_data": "md:%d" % i}] for i, (mid, title) in enumerate(MODELS)]
    return {"inline_keyboard": rows}


def model_text(uid):
    return "🤖 Выбери ИИ, который будет строить. Все модели бесплатные; если одна строит плохо или занята — попробуй другую.\n\nСейчас: %s" % mname(user_model(uid))


def cmd_model(chat, uid):
    tg.send(chat, model_text(uid), model_markup(user_model(uid)))


def on_callback_model(cq, data):
    uid, chat = cq["from"]["id"], cq["message"]["chat"]["id"]
    try:
        mid = MODEL_IDS[int(data[3:])]
    except (ValueError, IndexError):
        return tg.call("answerCallbackQuery", {"callback_query_id": cq["id"]})
    with S.lock:
        us = S.d["users"].setdefault(str(uid), {"u": "", "n": "", "first": now_ts(), "day": today(), "cnt": 0, "tot": 0})
        us["model"] = mid
    S.save()
    tg.call("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "ИИ: " + mname(mid)})
    tg.safe_edit(chat, cq["message"]["message_id"], model_text(uid), model_markup(mid))


def user_think(uid):
    return bool((S.d["users"].get(str(uid)) or {}).get("think", True))


def settings_text(uid):
    on = user_think(uid)
    return ("⚙️ Настройки\n\n🧠 Размышления: %s\n\n"
            "Включены: ИИ сначала пишет короткий план, потом строит. Обычно аккуратнее, но дольше.\n"
            "Выключены: ИИ сразу строит, без плана. Быстрее, но постройка может получиться проще.") % ("включены ✅" if on else "выключены ❌")


def settings_markup(uid):
    on = user_think(uid)
    return {"inline_keyboard": [[{"text": "🧠 Отключить размышления" if on else "🧠 Включить размышления", "callback_data": "sg:think"}]]}


def cmd_settings(chat, uid):
    tg.send(chat, settings_text(uid), settings_markup(uid))


def on_callback_settings(cq, data):
    uid, chat = cq["from"]["id"], cq["message"]["chat"]["id"]
    if data == "sg:think":
        with S.lock:
            us = S.d["users"].setdefault(str(uid), {"u": "", "n": "", "first": now_ts(), "day": today(), "cnt": 0, "tot": 0})
            us["think"] = not us.get("think", True)
        S.save()
    tg.call("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Размышления: " + ("включены" if user_think(uid) else "выключены")})
    tg.safe_edit(chat, cq["message"]["message_id"], settings_text(uid), settings_markup(uid))


def cmd_me(chat, uid):
    lim = eff_limit(uid)
    if is_admin(uid) or not lim:
        t = "Для тебя без лимита."
    else:
        t = "Сегодня использовано %d из %d построек." % (used_today(uid), lim)
    m = {"on": "🟢 работает", "off": "⛔ выключен", "update": "🔧 на обновлении"}[S.d["mode"]]
    if is_prem(uid):
        pr = "👑 Premium: " + left_text(uid)
    else:
        pr = "⭐ Premium нет. Карты до 384×384, вид изнутри и сверху, %d построек в день → /premium" % S.d["prem_limit"]
    if bonus_of(uid):
        t += "\n🎁 Бонусных запросов: %d (тратятся после дневного лимита)" % bonus_of(uid)
    tg.send(chat, "%s\n%s\nСервис: %s\nИИ: %s (сменить: /model)" % (t, pr, m, mname(user_model(uid))))


def on_callback_user(cq, data):
    uid, chat = cq["from"]["id"], cq["message"]["chat"]["id"]
    act, _, bid = data.partition(":")
    b = S.d["builds"].get(bid)
    cbid = cq["id"]
    if not b:
        return tg.call("answerCallbackQuery", {"callback_query_id": cbid, "text": "Эта постройка уже недоступна. Сделай новую: /build", "show_alert": True})
    if b["uid"] != uid and not is_admin(uid):
        return tg.call("answerCallbackQuery", {"callback_query_id": cbid, "text": "Это чужая постройка.", "show_alert": True})
    if act == "no":
        tg.call("answerCallbackQuery", {"callback_query_id": cbid})
        return tg.call("editMessageReplyMarkup", {"chat_id": chat, "message_id": cq["message"]["message_id"], "reply_markup": {"inline_keyboard": []}})
    if act == "re":
        tg.call("answerCallbackQuery", {"callback_query_id": cbid, "text": "Строю заново…"})
        return try_start_build(chat, uid, b["q"], None)
    if act in ("ok", "st"):
        if S.d["mode"] == "off" and not is_admin(uid):
            return tg.call("answerCallbackQuery", {"callback_query_id": cbid, "text": "Сервис выключен, попробуй позже.", "show_alert": True})
        lk = ACTIVE_FILES
        if time.time() - lk.get((uid, bid, act), 0) < 8:
            return tg.call("answerCallbackQuery", {"callback_query_id": cbid, "text": "Файл уже отправляется…"})
        lk[(uid, bid, act)] = time.time()
        tg.call("answerCallbackQuery", {"callback_query_id": cbid, "text": "Собираю файл…"})
        r = run_spec_for_build(b)
        name = b["spec"].get("name") or "build"
        if act == "st" and r.g.size > 4000000:
            return tg.send(chat, "📦 Эта постройка слишком большая для .mcstructure (структурный блок держит ~64 блока). Жми «Беру» — мир откроется без проблем.")
        if act == "ok":
            title = ("BuildAI " + name)[:40]
            data_b = build_mcworld_bytes(r, title, world_opts(uid))
            tg.doc(chat, data_b, safe_name(name) + ".mcworld",
                   "🌍 %s — мир для Minecraft Bedrock 1.21.50.\n\nОткрой файл в Minecraft (на телефоне: «Поделиться» → Minecraft). "
                   "Мир плоский, творческий; постройка стоит в 8 блоках на восток от места появления. "
                   "День без смены суток, мобы выключены." % name)
            with S.lock:
                S.d["stats"]["worlds"] += 1
        else:
            tg.doc(chat, mcstructure_bytes(r), safe_name(name) + ".mcstructure",
                   "📦 %s — структура Bedrock. В игре: Блок структуры → Загрузка/Импорт." % name)
            with S.lock:
                S.d["stats"]["structs"] += 1
        S.save()


ACTIVE_FILES = {}


# ═════════════════════════════════════════════════════════════════════════════
#  11. АДМИН-КОМАНДЫ (только в личке и только для ADMIN_IDS)
# ═════════════════════════════════════════════════════════════════════════════
ADMIN_HELP = (
    "🛠 Админ-панель BuildAI\n\n"
    "Сервис:\n"
    "/off [причина] — выключить сервис\n"
    "/on — включить\n"
    "/update [текст] — режим обновления (новые постройки не принимаются)\n\n"
    "Ключи TokenHarbor:\n"
    "/addkey <ключ> [заметка] — добавить (сообщение с ключом я удалю)\n"
    "/keys — список\n"
    "/delkey <номер или последние 4 символа>\n"
    "/testkeys — проверить все ключи (рабочие вернутся в строй)\n"
    "/setmodel <номер> — модель по умолчанию (сейчас: %s). Игроки выбирают сами через /model\n\n"
    "Люди:\n"
    "/limit <число> — построек на человека в сутки (0 = без лимита)\n"
    "/ban <id|@ник> · /unban <id|@ник> · /banned\n"
    "/broadcast <текст> — рассылка всем\n\n"
    "Premium:\n"
    "/givesubscription <@ник|id> [срок] — выдать Premium (15m, 3h, 1d, 7d, 30d, 1y, forever; без срока = 30 дней)\n"
    "/removesubscription <@ник|id> — снять · /premiumlist — у кого есть\n"
    "/requests — заявки на проверке (приходят и сами, с кнопками «Выдать»)\n"
    "/prices · /setprice <код> <звёзды> · /setpremlimit <число> — цены и лимит Premium\n\n"
    "Прочее:\n"
    "/stats — статистика · /status — состояние · /backup — копия состояния · /id — твой ID")


def admin_panel_markup():
    return {"inline_keyboard": [[{"text": "🟢 Включить", "callback_data": "ad:on"}, {"text": "🔧 Обновление", "callback_data": "ad:update"}, {"text": "⛔ Выключить", "callback_data": "ad:off"}],
                                [{"text": "🔑 Ключи", "callback_data": "ad:keys"}, {"text": "📊 Статистика", "callback_data": "ad:stats"}]]}


def fmt_status():
    m = {"on": "🟢 работает", "off": "⛔ выключен", "update": "🔧 на обновлении"}[S.d["mode"]]
    ks = S.d["keys"]
    good = sum(1 for k in ks if not k["off"] and k["cool"] <= time.time())
    extra = ("\nСообщение: " + S.d["mode_msg"]) if S.d.get("mode_msg") else ""
    return "Сервис: %s%s\nМодель: %s\nКлючи: %d рабочих из %d\nЛимит: %s в сутки\nОчередь: %d (одновременно %d)\nБэкап в Telegram: %s" % (
        m, extra, S.d["model"], good, len(ks), S.d["limit"] or "∞", PENDING[0], WORKERS, "вкл" if TG_BACKUP and not BK["blocked"] else ("ждёт связи" if TG_BACKUP else "выкл"))


def fmt_stats():
    st, us = S.d["stats"], S.d["users"]
    td = sum(1 for u in us.values() if u.get("day") == today() and u.get("cnt", 0) > 0)
    up = int(time.time() - START_TS)
    return ("📊 Статистика\nЛюдей всего: %d (строили сегодня: %d)\nПостроек: %d · удачных: %d · ошибок: %d\nМиров выдано: %d · .mcstructure: %d\nАптайм: %d ч %d мин"
            % (len(us), td, st["builds"], st["ok"], st["fail"], st["worlds"], st["structs"], up // 3600, up % 3600 // 60))


def fmt_keys():
    ks = S.d["keys"]
    if not ks:
        return "Ключей нет. Добавь: /addkey <ключ>"
    out = []
    for i, k in enumerate(ks, 1):
        if k["off"]:
            s = "🔴 отключён (%s)" % k["why"]
        elif k["cool"] > time.time():
            s = "🟡 пауза до %s (%s)" % (time.strftime("%H:%M", time.gmtime(k["cool"] + UTC_OFFSET_H * 3600)), k["why"])
        else:
            s = "🟢 ок"
        out.append("%d. %s — %s · запросов %d, ошибок %d%s" % (i, mask(k["k"]), s, k["ok"], k["err"], (" · " + k["note"]) if k["note"] else ""))
    return "🔑 Ключи TokenHarbor\n" + "\n".join(out)


def find_user(tok):
    tok = tok.strip().lstrip("@")
    if re.fullmatch(r"-?\d+", tok):
        return int(tok)
    for uid, u in S.d["users"].items():
        if u.get("u", "").lower() == tok.lower():
            return int(uid)
    return None


PENDING_BC = {}


def do_broadcast(admin_chat, text):
    ok = fail = 0
    for uid in list(S.d["users"].keys()):
        try:
            tg.call("sendMessage", {"chat_id": int(uid), "text": text}, tries=1)
            ok += 1
        except TGError:
            fail += 1
        time.sleep(0.05)
    tg.send(admin_chat, "📣 Рассылка завершена: доставлено %d, не доставлено %d." % (ok, fail))


def admin_command(chat, uid, cmd, arg, msg):
    A = arg.strip()
    if cmd in ("admin", "adm", "panel"):
        return tg.send(chat, ADMIN_HELP % S.d["model"] + "\n\n" + fmt_status(), admin_panel_markup())
    if cmd == "status":
        return tg.send(chat, fmt_status(), admin_panel_markup())
    if cmd == "stats":
        return tg.send(chat, fmt_stats())
    if cmd == "off":
        S.d["mode"], S.d["mode_msg"] = "off", A[:300]
        S.save()
        return tg.send(chat, "⛔ Сервис выключен.%s\nВключить: /on" % ((" Причина: " + A) if A else ""))
    if cmd == "on":
        S.d["mode"], S.d["mode_msg"] = "on", ""
        S.save()
        return tg.send(chat, "🟢 Сервис включён.")
    if cmd == "update":
        S.d["mode"], S.d["mode_msg"] = "update", A[:300]
        S.save()
        return tg.send(chat, "🔧 Режим обновления: новые постройки не принимаются (ты как админ можешь тестировать).\nВернуть работу: /on")
    if cmd == "addkey":
        parts = A.split(None, 1)
        if not parts:
            return tg.send(chat, "Использование: /addkey <ключ> [заметка]")
        key, note = parts[0], (parts[1] if len(parts) > 1 else "")
        tg.safe_delete(chat, msg["message_id"])
        if len(key) < 10:
            return tg.send(chat, "Это не похоже на ключ (слишком короткий).")
        if not add_key(key, note[:40]):
            return tg.send(chat, "Такой ключ уже есть: " + mask(key))
        ok, info = test_key(key)
        if not ok:
            with S.lock:
                for x in S.d["keys"]:
                    if x["k"] == key:
                        x["why"] = "проверка: " + info
            S.save()
        return tg.send(chat, "✅ Ключ %s добавлен (всего: %d). Проверка: %s %s\n(сообщение с ключом удалено из чата)" % (mask(key), len(S.d["keys"]), "🟢" if ok else "🔴", info))
    if cmd == "keys":
        return tg.send(chat, fmt_keys())
    if cmd == "delkey":
        if not A:
            return tg.send(chat, "Использование: /delkey <номер из /keys или последние 4 символа>")
        with S.lock:
            ks = S.d["keys"]
            idx = int(A) - 1 if A.isdigit() and 1 <= int(A) <= len(ks) else next((i for i, k in enumerate(ks) if k["k"].endswith(A)), None)
            if idx is None:
                return tg.send(chat, "Не нашёл такой ключ. Смотри /keys")
            k = ks.pop(idx)
        S.save()
        return tg.send(chat, "🗑 Ключ %s удалён. Осталось: %d" % (mask(k["k"]), len(S.d["keys"])))
    if cmd == "testkeys":
        if not S.d["keys"]:
            return tg.send(chat, "Ключей нет.")
        lines = []
        for i, k in enumerate(list(S.d["keys"]), 1):
            ok, info = test_key(k["k"])
            with S.lock:
                for x in S.d["keys"]:
                    if x["k"] == k["k"]:
                        x["off"] = False if ok else x["off"]
                        x["cool"] = 0 if ok else x["cool"]
                        x["why"] = "" if ok else x["why"]
            lines.append("%d. %s — %s %s" % (i, mask(k["k"]), "🟢" if ok else "🔴", info))
        S.save()
        return tg.send(chat, "Проверка ключей:\n" + "\n".join(lines))
    if cmd == "setmodel":
        lst = "\n".join("%d. %s — %s" % (i + 1, mid, t) for i, (mid, t) in enumerate(MODELS))
        pick = None
        if A.split():
            w = A.split()[0]
            pick = MODEL_IDS[int(w) - 1] if w.isdigit() and 1 <= int(w) <= len(MODELS) else (w if w in MODEL_NAME else None)
        if not pick:
            return tg.send(chat, "Модель по умолчанию (для тех, кто не выбрал свою): %s\n\nДоступные:\n%s\n\nСменить: /setmodel <номер>\nИгроки выбирают сами: /model" % (S.d["model"], lst))
        with S.lock:
            S.d["model"] = pick
            MODEL_COOL.clear()
            for x in S.d["keys"]:
                x["cool"] = 0
        S.save()
        return tg.send(chat, "✅ Модель по умолчанию: %s\nПроверить ключи: /testkeys" % pick)
    if cmd == "limit":
        if not A.isdigit():
            return tg.send(chat, "Сейчас: %s в сутки. Изменить: /limit <число> (0 = без лимита)" % (S.d["limit"] or "без лимита"))
        S.d["limit"] = int(A)
        S.save()
        return tg.send(chat, "✅ Лимит: %s построек на человека в сутки." % (S.d["limit"] or "без лимита"))
    if cmd in ("ban", "unban"):
        t = find_user(A) if A else None
        if t is None:
            return tg.send(chat, "Использование: /%s <id или @ник> (ник работает, если человек уже писал боту)" % cmd)
        if is_admin(t):
            return tg.send(chat, "Админа банить нельзя.")
        with S.lock:
            b = S.d["banned"]
            if cmd == "ban" and t not in b:
                b.append(t)
            if cmd == "unban" and t in b:
                b.remove(t)
        S.save()
        return tg.send(chat, ("🚫 Забанен %s" if cmd == "ban" else "✅ Разбанен %s") % t)
    if cmd == "banned":
        return tg.send(chat, "Забанены: " + (", ".join(map(str, S.d["banned"])) or "никто"))
    if cmd == "broadcast":
        if len(A) < 2:
            return tg.send(chat, "Использование: /broadcast <текст>")
        PENDING_BC[uid] = A
        return tg.send(chat, "Отправить всем (%d человек) это сообщение?\n\n%s" % (len(S.d["users"]), A),
                       {"inline_keyboard": [[{"text": "✅ Отправить", "callback_data": "bc:yes"}, {"text": "❌ Отмена", "callback_data": "bc:no"}]]})
    if cmd == "backup":
        if not TG_BACKUP:
            return tg.send(chat, "Бэкап в Telegram выключен (TG_BACKUP=0).")
        backup_now()
        return tg.send(chat, "🗄 Копия состояния обновлена (закреплена в этом чате).")
    return None


def on_callback_admin(cq, data):
    uid, chat = cq["from"]["id"], cq["message"]["chat"]["id"]
    cbid = cq["id"]
    if not is_admin(uid):
        return tg.call("answerCallbackQuery", {"callback_query_id": cbid, "text": "Только для админа.", "show_alert": True})
    act = data.split(":", 1)[1]
    if act in ("on", "off", "update"):
        S.d["mode"], S.d["mode_msg"] = act, "" if act == "on" else S.d.get("mode_msg", "")
        S.save()
        tg.call("answerCallbackQuery", {"callback_query_id": cbid, "text": {"on": "🟢 Включено", "off": "⛔ Выключено", "update": "🔧 Режим обновления"}[act]})
        return tg.safe_edit(chat, cq["message"]["message_id"], ADMIN_HELP % S.d["model"] + "\n\n" + fmt_status(), admin_panel_markup())
    tg.call("answerCallbackQuery", {"callback_query_id": cbid})
    if act == "keys":
        return tg.send(chat, fmt_keys())
    if act == "stats":
        return tg.send(chat, fmt_stats())


def on_callback_broadcast(cq, data):
    uid, chat = cq["from"]["id"], cq["message"]["chat"]["id"]
    if not is_admin(uid):
        return tg.call("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Только для админа.", "show_alert": True})
    tg.call("answerCallbackQuery", {"callback_query_id": cq["id"]})
    text = PENDING_BC.pop(uid, None)
    tg.safe_edit(chat, cq["message"]["message_id"], "📣 Рассылка " + ("запущена…" if data.endswith("yes") and text else "отменена."))
    if data.endswith("yes") and text:
        FAST.submit(do_broadcast, chat, text)


# ═════════════════════════════════════════════════════════════════════════════
#  12. РАЗБОР ОБНОВЛЕНИЙ TELEGRAM
# ═════════════════════════════════════════════════════════════════════════════
# ===PREMIUM-BLOCK===
# ═════════════════════════════════════════════════════════════════════════════
#  11b. PREMIUM: подписка, оплата подарками ⭐ (вручную), виды сверху/изнутри, масштаб, тема мира
# ═════════════════════════════════════════════════════════════════════════════
FOREVER = 4102444800
PLANS = [   # код, название, секунд, звёзд по умолчанию, значок
    ("15m", "15 минут", 900, 15, "🧪"),
    ("3h", "3 часа", 10800, 25, "⏳"),
    ("10h", "10 часов", 36000, 50, "⌛"),
    ("1d", "1 день", 86400, 75, "☀️"),
    ("3d", "3 дня", 259200, 150, "🌤"),
    ("7d", "7 дней", 604800, 300, "🔥"),
    ("30d", "30 дней", 2592000, 750, "💎"),
    ("1y", "1 год", 31536000, 5000, "👑"),
    ("forever", "Навсегда", FOREVER, 12000, "🌟"),
]
PREM_CMDS = ("premium", "vip", "donate", "buy", "prem", "subscribe", "world")
PREM_ADMIN_CMDS = ("givesubscription", "givesub", "givevip", "removesubscription", "delsub", "takesub",
                   "premiumlist", "vips", "setpremlimit", "setprice", "prices", "requests", "payments")
GROUNDS = [("grass_block", "🌱 Трава"), ("sand", "🏜 Песок"), ("snow", "❄️ Снег"), ("stone", "⛰ Камень")]
TIMES = [(6000, "☀️ День"), (12000, "🌅 Закат"), (18000, "🌙 Ночь")]
VIEW_SEM = threading.Semaphore(2)
BUILD_PREM = ThreadPoolExecutor(max_workers=2, thread_name_prefix="prem")
_lock_ts = {}
CITY_RE = re.compile(r"город|city|town|деревн|village|карт|\bmap\b|\bрп\b|\brp\b|остров|island|королевств|kingdom|страна|мегаполис", re.I)
IMPROVE_Q = ("Улучши эту постройку: добавь больше деталей — интерьер с мебелью, освещение, декор, акценты другими блоками, "
             "окружение (деревья, дорожки, забор). Сохрани общий вид и размер.")
LOCKS = {"in": "🏠 Вид изнутри: разрезы со всех сторон и планы этажей", "td": "🗺 Вид сверху с сеткой чанков",
         "zm": "🔎 Масштаб ×2/×3 без трат попыток", "up": "✨ Авто-улучшение в один клик", "wo": "🌍 Тема мира и время суток"}
SYS_PROMPT_PREM = SYS_PROMPT.replace("any size up to 128 per axis", "any size up to 384 wide, 192 high and 384 deep") + (
    " PREMIUM MAP MODE: this player may build HUGE scenes. For a city, town, village, island, castle with surroundings or any map: "
    "first lay out the ground plan seen from above (road grid, plots, parks, water, walls), then build the houses with repeat ops, "
    "vary heights and roofs, add street lights and trees. The player also sees a top-down map, so roads, rivers, plazas and plots "
    "must read clearly from above. Keep the JSON compact (repeat/mirror/fill/hollow, at most about 600 ops). "
    "For a single object (a house, a tree, a car) keep its natural size but make it richly detailed with a furnished interior.")


def plan_by(code):
    return next((p for p in PLANS if p[0] == code), None)


def plan_stars(code):
    p = plan_by(code)
    try:
        v = int((S.d.get("prices") or {}).get(code) or 0)
    except (TypeError, ValueError):
        v = 0
    return v if v > 0 else p[3]


def is_prem(uid):
    return is_admin(uid) or S.d["prem"].get(str(uid), 0) > time.time()


def eff_limit(uid):
    if is_admin(uid):
        return 0
    return S.d["prem_limit"] if is_prem(uid) else S.d["limit"]


def fdate(ts):
    if ts >= FOREVER - 86400:
        return "навсегда"
    return time.strftime("%d.%m.%Y %H:%M", time.gmtime(ts + UTC_OFFSET_H * 3600))


def fdur(sec):
    sec = int(max(0, sec))
    d, r_ = divmod(sec, 86400)
    h, r_ = divmod(r_, 3600)
    m = r_ // 60
    parts = []
    if d:
        parts.append("%d дн" % d)
    if h:
        parts.append("%d ч" % h)
    if m and not d:
        parts.append("%d мин" % m)
    return " ".join(parts) or "меньше минуты"


def left_text(uid):
    exp = S.d["prem"].get(str(uid), 0)
    if exp >= FOREVER - 86400 or (is_admin(uid) and not exp):
        return "навсегда" + (" (админ)" if is_admin(uid) and not exp else "")
    return "до %s (осталось %s)" % (fdate(exp), fdur(exp - time.time()))


def grant(uid, sec):
    with S.lock:
        now = time.time()
        cur = S.d["prem"].get(str(uid), 0)
        new = FOREVER if (sec >= 10 ** 9 or cur >= FOREVER - 86400) else max(cur, now) + sec
        S.d["prem"][str(uid)] = new
    S.save()
    return new


def parse_dur(t):
    t = (t or "").strip().lower().replace(" ", "")
    if t in ("forever", "навсегда", "вечно", "inf", "lifetime", "∞"):
        return 10 ** 10
    p = plan_by(t)
    if p:
        return p[2] if p[2] < 10 ** 9 else 10 ** 10
    m = re.fullmatch(r"(\d+)(mo|мес|min|мин|нед|год|m|м|h|ч|d|д|w|н|y|г)", t)
    if not m:
        return None
    k = {"m": 60, "м": 60, "min": 60, "мин": 60, "h": 3600, "ч": 3600, "d": 86400, "д": 86400, "w": 604800, "н": 604800,
         "нед": 604800, "mo": 2592000, "мес": 2592000, "y": 31536000, "г": 31536000, "год": 31536000}[m.group(2)]
    n = int(m.group(1))
    return n * k if 0 < n <= 100000 else None


def plans_text():
    out = []
    for code, name, sec, _st, ic in PLANS:
        st = plan_stars(code)
        per = "  (≈ %d⭐/день)" % round(st / (sec / 86400.0)) if 86400 < sec < 10 ** 9 else ""
        out.append("%s %s — %d⭐%s" % (ic, name, st, per))
    return "\n".join(out)


def premium_text(uid):
    head = "👑 BuildAI Premium\n"
    if is_prem(uid):
        head += "✅ У тебя Premium: %s\n" % left_text(uid)
    perks = (
        "🗺 Огромные карты — до 384×192×384 блоков (в 9 раз больше площади, чем обычные 128×128): город для РП, деревня, "
        "замок с округой. Плюс вид сверху с сеткой чанков\n"
        "🏗 %d построек в день вместо %d\n"
        "🏠 Вид изнутри — отдельная кнопка: разрезы со всех сторон и планы этажей\n"
        "🔎 Масштаб ×2 / ×3 в один клик: маленький дом → особняк, попытки не тратятся\n"
        "✨ Авто-улучшение одной кнопкой, правки /edit бесплатны\n"
        "⚡ Без очереди и пауза 5 с вместо %d\n"
        "🌍 Тема мира и время суток: снег, песок, ночь с огнями (/world)\n"
        "👑 Значок Premium в /me") % (S.d["prem_limit"], S.d["limit"] or 5, COOLDOWN_SEC)
    return "%s\n%s\n\n💳 Тарифы (оплата подарком в Telegram, цена в ⭐):\n%s\n\nВыбери срок кнопкой 👇" % (head, perks, plans_text())


def premium_markup():
    btns = [{"text": "%s %s · %d⭐" % (ic, name, plan_stars(code)), "callback_data": "pm:p:" + code} for code, name, _s, _st, ic in PLANS]
    return {"inline_keyboard": [btns[i:i + 2] for i in range(0, len(btns), 2)]}


def pay_text(code):
    p = plan_by(code)
    st = plan_stars(code)
    return ("%s Premium на %s — %d⭐\n\nКак оплатить:\n1️⃣ Открой профиль @%s\n2️⃣ Нажми «Отправить подарок» и выбери подарок(и) "
            "на сумму от %d⭐\n3️⃣ Вернись сюда и нажми «✅ Я отправил(а)»\n\n"
            "Владелец проверит подарок и вручную выдаст Premium — обычно за несколько минут. Я напишу тебе сюда, как только он выдаст."
            % (p[4], p[1], st, ADMIN_NAME, st))


def pay_markup(code):
    return {"inline_keyboard": [[{"text": "✅ Я отправил(а) подарок", "callback_data": "pm:s:" + code}],
                                [{"text": "👤 Открыть @" + ADMIN_NAME, "url": "https://t.me/" + ADMIN_NAME}],
                                [{"text": "⬅️ Все тарифы", "callback_data": "pm:menu"}]]}


def uname_of(uid):
    us = S.d["users"].get(str(uid), {})
    return ("@" + us["u"]) if us.get("u") else (us.get("n") or "без ника")


def admin_req_text(rid, x, tail=""):
    p = plan_by(x["plan"])
    return ("💳 Заявка на Premium #%s\n👤 %s · id %d\n📦 %s — %d⭐\n🕒 %s\n\nПроверь, пришёл ли подарок на @%s.%s"
            % (rid, uname_of(x["uid"]), x["uid"], p[1], x["stars"], fdate(x["ts"]), ADMIN_NAME, tail))


def admin_req_markup(rid):
    return {"inline_keyboard": [[{"text": "✅ Выдать", "callback_data": "pay:ok:" + rid}, {"text": "❌ Отклонить", "callback_data": "pay:no:" + rid}]]}


def make_request(uid, code):
    p = plan_by(code)
    if not p:
        return False, "Тариф не найден."
    now = time.time()
    with S.lock:
        pay = S.d["pay"]
        for rid, x in pay.items():
            if x["uid"] == uid and x["st"] == "wait" and now - x["ts"] < 6 * 3600:
                return False, "⏳ Твоя заявка #%s уже ждёт проверки. Владелец @%s скоро её посмотрит." % (rid, ADMIN_NAME)
        if now - max([x["ts"] for x in pay.values() if x["uid"] == uid] or [0]) < 45:
            return False, "Подожди минутку перед новой заявкой."
        rid = secrets.token_hex(3)
        pay[rid] = {"uid": uid, "plan": code, "stars": plan_stars(code), "ts": now, "st": "wait"}
        for old in sorted(pay, key=lambda k: pay[k]["ts"])[:max(0, len(pay) - 80)]:
            pay.pop(old, None)
        x = dict(pay[rid])
    S.save()
    for a in ADMIN_IDS:
        try:
            tg.send(a, admin_req_text(rid, x), admin_req_markup(rid))
        except Exception:
            pass
    return True, ("📨 Заявка #%s отправлена владельцу!\nТариф: %s — %d⭐\n\nКак только он увидит подарок, Premium включится "
                  "автоматически и я напишу тебе здесь. Если долго тишина — напиши @%s." % (rid, p[1], x["stars"], ADMIN_NAME))


def notify_grant(uid, label=""):
    try:
        tg.send(uid, "🎉 Тебе выдан Premium%s!\nДействует: %s\n\nПопробуй сразу: /build город для РП с дорогами, парком и рекой — "
                     "и жми «Вид сверху» и «Вид изнутри».\nНастройки мира: /world · все возможности: /premium"
                % ((" (" + label + ")") if label else "", left_text(uid)))
    except Exception:
        pass


def _apply_prem_wait(uid, uname):
    w = S.d.get("prem_wait") or {}
    sec = w.pop((uname or "").lower(), None) if uname else None
    if sec:
        grant(int(uid), sec)
        FAST.submit(notify_grant, int(uid))


def prem_watch():
    while True:
        time.sleep(60)
        try:
            now, gone = time.time(), []
            with S.lock:
                for u, exp in list(S.d["prem"].items()):
                    if exp <= now:
                        gone.append(u)
                        S.d["prem"].pop(u, None)
            if gone:
                S.save()
                for u in gone:
                    try:
                        tg.send(int(u), "⌛ Твой Premium закончился.\nВсе твои миры и постройки остались у тебя. "
                                        "Продлить: /premium", premium_markup())
                    except Exception:
                        pass
        except Exception:
            log.error("prem_watch: %s", traceback.format_exc())


# ─── Настройки мира ──────────────────────────────────────────────────────────
def _wo(uid):
    o = (S.d["users"].get(str(uid)) or {}).get("wo") or {}
    return {"g": o.get("g") if o.get("g") in dict(GROUNDS) else "grass_block", "t": o.get("t") if o.get("t") in dict(TIMES) else 6000}


def world_opts(uid):
    return _wo(uid) if is_prem(uid) else None


def world_text(uid):
    o = _wo(uid)
    return "🌍 Настройки мира (Premium)\nЗемля и время суток для всех твоих следующих миров.\n\nСейчас: %s · %s" % (dict(GROUNDS)[o["g"]], dict(TIMES)[o["t"]])


def world_markup(uid):
    o = _wo(uid)
    g = [{"text": ("✅ " if k == o["g"] else "") + t, "callback_data": "wo:g:" + k} for k, t in GROUNDS]
    tm = [{"text": ("✅ " if v == o["t"] else "") + t, "callback_data": "wo:t:%d" % v} for v, t in TIMES]
    return {"inline_keyboard": [g[:2], g[2:], tm]}


# ─── Картинки: вид сверху, разрезы, планы этажей ─────────────────────────────
def _png(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def render_topdown(r, maxpx=1100, grid=True):
    g, pal = r.g, r.pal
    X, Y, Z = g.shape
    nz = g != 0
    has = nz.any(axis=1)
    topy = (Y - 1) - np.argmax(nz[:, ::-1, :], axis=1)
    vals = np.take_along_axis(g, topy[:, None, :], axis=1)[:, 0, :]
    lut = np.zeros((len(pal), 3), dtype=np.float32)
    for i, nm in enumerate(pal):
        if i:
            c = D[nm]
            lut[i] = c[1] if c[1] else c[0]
    ground = np.array([104, 160, 76], dtype=np.float32)
    img = np.where(has[..., None], lut[vals], ground)
    h = np.where(has, topy + 1, 0).astype(np.float32)
    dx, dz = np.zeros_like(h), np.zeros_like(h)
    dx[1:, :] = h[1:, :] - h[:-1, :]
    dz[:, 1:] = h[:, 1:] - h[:, :-1]
    shade = 1.0 + np.clip((dx + dz) * 0.06, -0.3, 0.3)
    base = 0.82 + 0.18 * (h / max(1.0, float(h.max())))
    img = np.clip(img * (shade * base)[..., None], 0, 255).astype(np.uint8)
    arr = np.ascontiguousarray(np.transpose(img, (1, 0, 2)))
    s = max(1, min(24, maxpx // max(X, Z)))
    im = Image.fromarray(arr, "RGB").resize((X * s, Z * s), Image.NEAREST).convert("RGBA")
    d = ImageDraw.Draw(im, "RGBA")
    gridon = grid and max(X, Z) >= 48
    if gridon:
        for x in range(8, X + 1, 16):
            d.line([(x * s, 0), (x * s, Z * s)], fill=(255, 255, 255, 55), width=1)
        for z in range((Z // 2) % 16, Z + 1, 16):
            d.line([(0, z * s), (X * s, z * s)], fill=(255, 255, 255, 55), width=1)
    try:
        from PIL import ImageFont
        try:
            f = ImageFont.load_default(size=18)
        except TypeError:
            f = ImageFont.load_default()
    except Exception:
        f = None
    W, H = im.size
    canvas = Image.new("RGB", (max(W, 420), H + 30), (30, 34, 32))
    canvas.paste(im.convert("RGB"), (0, 30))
    ImageDraw.Draw(canvas).text((8, 5), "N up | top view %dx%d%s" % (X, Z, " | grid = 16-block chunks" if gridon else ""), fill=(235, 240, 235), font=f)
    return _png(canvas)


def _downsample(g, f):
    # каждая ячейка f×f×f -> один блок (если заполнена хотя бы на 1/5), чтобы тонкие стены не пропадали
    X, Y, Z = g.shape
    px, py, pz = (-X) % f, (-Y) % f, (-Z) % f
    if px or py or pz:
        g = np.pad(g, ((0, px), (0, py), (0, pz)))
    nx, ny, nz = g.shape[0] // f, g.shape[1] // f, g.shape[2] // f
    c = g.reshape(nx, f, ny, f, nz, f).transpose(0, 2, 4, 1, 3, 5).reshape(nx, ny, nz, f ** 3)
    cnt = (c != 0).sum(axis=3)
    return np.ascontiguousarray(np.where(cnt >= max(1, f ** 3 // 5), c.max(axis=3), 0).astype(g.dtype))


def render_preview_any(r):
    m = max(r.d)
    if m <= 128:
        return render_preview(r)
    g = _downsample(r.g, -(-m // 128))
    rr = SimpleNamespace(ops=r.ops, pal=r.pal, g=g, d=tuple(int(v) for v in g.shape), n=int(np.count_nonzero(g)), unk=r.unk, bad=r.bad)
    return render_preview(rr)


def _floor_cuts(g):
    X, Y, Z = g.shape
    cnt = (g != 0).sum(axis=(0, 2)).astype(np.float64)
    cuts = []
    if cnt.max() > 0:
        slab = cnt >= 0.5 * cnt.max()
        y = 0
        while y < Y:
            if slab[y]:
                y2 = y
                while y2 + 1 < Y and slab[y2 + 1]:
                    y2 += 1
                cut = min(Y - 1, y2 + 4)
                if y2 < Y * 0.8 and cut >= 2 and (not cuts or cut - cuts[-1] >= 4):
                    cuts.append(cut)
                y = y2 + 1
            else:
                y += 1
    return cuts[:2] or [max(2, int(Y * 0.45))]


def render_interior(r, W=900, H=720):
    g, pal = r.g, r.pal
    note = ""
    X, Y, Z = g.shape
    grid = True
    if max(X, Z) > 140:
        x0, z0 = max(0, X // 2 - 70), max(0, Z // 2 - 70)
        g = np.ascontiguousarray(g[x0:x0 + 140, :, z0:z0 + 140])
        note = " · центральный участок 140×140"
        grid = False
    out = []
    ss = 2 if np.count_nonzero(g) < 120000 else 1
    for k in range(4):
        try:
            a = np.ascontiguousarray(np.rot90(g, k, axes=(0, 2)))
            a[a.shape[0] // 2:, :, a.shape[2] // 2:] = 0
            out.append((_png(_iso_view(a, pal, 0, W * ss, H * ss, ss)), "🏠 Разрез %d/4 — вид изнутри с нового ракурса%s" % (k + 1, note)))
        except Exception:
            log.warning("interior view %d: %s", k, traceback.format_exc())
    for n, cut in enumerate(_floor_cuts(g), 1):
        try:
            sub = SimpleNamespace(g=np.ascontiguousarray(g[:, :cut + 1, :]), pal=pal)
            out.append((render_topdown(sub, 900, grid), "📐 План этажа %d — крыша снята (срез на высоте %d)%s" % (n, cut, note)))
        except Exception:
            log.warning("plan view %d: %s", n, traceback.format_exc())
    return out


def send_album(chat, items):
    try:
        media, files = [], {}
        for i, (png, cap) in enumerate(items[:10]):
            files["f%d" % i] = ("v%d.png" % i, png, "image/png")
            media.append({"type": "photo", "media": "attach://f%d" % i, "caption": cap[:200]})
        tg.call("sendMediaGroup", {"chat_id": chat, "media": media}, files=files, timeout=180)
    except Exception as e:
        log.warning("album: %s", e)
        for png, cap in items[:10]:
            tg.photo(chat, png, cap)


def zoom_result(r, k):
    g = np.ascontiguousarray(np.repeat(np.repeat(np.repeat(r.g, k, 0), k, 1), k, 2))
    return SimpleNamespace(ops=r.ops, pal=r.pal, g=g, d=tuple(int(v) for v in g.shape), n=int(np.count_nonzero(g)), unk=r.unk, bad=r.bad)


def run_spec_for_build(b):
    r = run_spec(b["spec"], bool(b.get("prem")))
    z = int(b.get("zoom") or 1)
    return zoom_result(r, z) if z > 1 else r


def send_previews(chat, r, cap, bid, prem, png=None):
    if prem and max(r.d[0], r.d[2]) >= 48:
        try:
            tg.photo(chat, render_topdown(r), "🗺 Вид сверху · %d×%d блоков" % (r.d[0], r.d[2]))
        except Exception as e:
            log.warning("topdown: %s", e)
    tg.photo(chat, png or render_preview_any(r), cap, build_markup(bid, prem))


def job_view(chat, uid, bid, kind, k=1):
    b = S.d["builds"].get(bid)
    if not b:
        return
    mid = None
    try:
        with VIEW_SEM:
            if kind == "in":
                mid = tg.send(chat, "🏠 Рисую разрезы и планы этажей… (до минуты)")["message_id"]
            r = run_spec_for_build(b)
            X, Y, Z = r.d
            if kind == "td":
                tg.photo(chat, render_topdown(r), "🗺 Вид сверху · %d×%d блоков" % (X, Z))
            elif kind == "in":
                items = render_interior(r)
                if not items:
                    raise ValueError("нечего показать")
                send_album(chat, items)
            else:
                if X * k > PREM_CAP[0] or Y * k > PREM_CAP[1] or Z * k > PREM_CAP[2]:
                    tg.send(chat, "🔎 ×%d не поместится: получилось бы %d×%d×%d, а максимум %d×%d×%d. Попробуй меньший масштаб." % (k, X * k, Y * k, Z * k, *PREM_CAP))
                    return
                r2 = zoom_result(r, k)
                nb = store_build(uid, b["q"], b["spec"], b["h"], True, int(b.get("zoom") or 1) * k)
                send_previews(chat, r2, "🔎 Масштаб ×%d\n🧱 %d блоков · %d×%d×%d\n\nЖми «Беру» — пришлю мир." % (k, r2.n, *r2.d), nb, True)
    except Exception:
        log.error("job_view: %s", traceback.format_exc())
        try:
            tg.send(chat, "⚠️ Не получилось нарисовать, попробуй ещё раз.")
        except Exception:
            pass
    finally:
        if mid:
            tg.safe_delete(chat, mid)


# ─── Команды игрока ──────────────────────────────────────────────────────────
def premium_user_cmd(cid, uid, cmd, arg, msg):
    if msg["chat"]["type"] != "private":
        return tg.send(cid, "👑 Premium и настройки мира — в личке с ботом. Напиши мне туда: /premium")
    if cmd == "world":
        if not is_prem(uid):
            return tg.send(cid, "🌍 Тема мира (снег, песок, ночь с огнями) — часть Premium.\n\n" + premium_text(uid), premium_markup())
        return tg.send(cid, world_text(uid), world_markup(uid))
    return tg.send(cid, premium_text(uid), premium_markup())


def _ans(cq, text=None, alert=False):
    try:
        tg.call("answerCallbackQuery", {"callback_query_id": cq["id"], "text": text, "show_alert": True if alert else None}, tries=1)
    except Exception:
        pass


def premium_callback(cq, data):
    key = data.split(":", 1)[0]
    if key not in ("pm", "pay", "pl", "in", "td", "zm", "up", "wo"):
        return False
    uid, chat, mid = cq["from"]["id"], cq["message"]["chat"]["id"], cq["message"]["message_id"]
    parts = data.split(":")

    def lock(what):
        _ans(cq, "🔒 %s\nЭто часть Premium — открой /premium" % LOCKS.get(what, "Premium"), True)
        if time.time() - _lock_ts.get(uid, 0) > 90:
            _lock_ts[uid] = time.time()
            tg.send(chat, premium_text(uid), premium_markup())

    if key == "pm":
        act = parts[1] if len(parts) > 1 else "menu"
        code = parts[2] if len(parts) > 2 else ""
        if act == "menu":
            _ans(cq)
            tg.safe_edit(chat, mid, premium_text(uid), premium_markup())
        elif act == "p" and plan_by(code):
            _ans(cq)
            tg.safe_edit(chat, mid, pay_text(code), pay_markup(code))
        elif act == "s" and plan_by(code):
            ok, text = make_request(uid, code)
            if ok:
                _ans(cq, "Заявка отправлена ✅")
                tg.safe_edit(chat, mid, text, {"inline_keyboard": [[{"text": "⬅️ К тарифам", "callback_data": "pm:menu"}]]})
            else:
                _ans(cq, text, True)
        else:
            _ans(cq)
        return True
    if key == "pl":
        what = parts[1] if len(parts) > 1 else "pm"
        if what == "pm":
            _ans(cq)
            tg.send(chat, premium_text(uid), premium_markup())
        else:
            lock(what)
        return True
    if key == "pay":
        if not is_admin(uid):
            _ans(cq, "Только для админа.", True)
            return True
        act, rid = (parts + ["", ""])[1], (parts + ["", ""])[2]
        with S.lock:
            x = S.d["pay"].get(rid)
            st = x["st"] if x else None
            if x and st == "wait":
                x["st"] = "ok" if act == "ok" else "no"
        if not x:
            _ans(cq, "Заявка не найдена.", True)
        elif st != "wait":
            _ans(cq, "Уже обработана: %s" % ("выдано" if st == "ok" else "отклонена"), True)
        else:
            S.save()
            p = plan_by(x["plan"])
            if act == "ok":
                grant(x["uid"], p[2])
                _ans(cq, "Выдано ✅")
                tg.safe_edit(chat, mid, admin_req_text(rid, x, "\n\n✅ ВЫДАНО"))
                notify_grant(x["uid"], p[1])
            else:
                _ans(cq, "Отклонено")
                tg.safe_edit(chat, mid, admin_req_text(rid, x, "\n\n❌ ОТКЛОНЕНО"))
                try:
                    tg.send(x["uid"], "❌ Заявка #%s отклонена: подарок не найден. Если это ошибка — напиши @%s." % (rid, ADMIN_NAME))
                except Exception:
                    pass
        return True
    if key == "wo":
        if not is_prem(uid):
            lock("wo")
            return True
        kind, val = (parts + ["", ""])[1], (parts + ["", ""])[2]
        with S.lock:
            us = S.d["users"].get(str(uid))
            if us is not None:
                wo = us.setdefault("wo", {})
                if kind == "g" and val in dict(GROUNDS):
                    wo["g"] = val
                elif kind == "t" and val.isdigit() and int(val) in dict(TIMES):
                    wo["t"] = int(val)
        S.save()
        _ans(cq, "Сохранено")
        tg.safe_edit(chat, mid, world_text(uid), world_markup(uid))
        return True
    # in / td / zm / up — действия над постройкой
    if not is_prem(uid):
        lock(key)
        return True
    bid = parts[1] if len(parts) > 1 else ""
    b = S.d["builds"].get(bid)
    if not b:
        _ans(cq, "Эта постройка уже недоступна. Сделай новую: /build", True)
        return True
    if b["uid"] != uid and not is_admin(uid):
        _ans(cq, "Это чужая постройка.", True)
        return True
    if key == "up":
        _ans(cq, "Улучшаю…")
        try_start_build(chat, uid, IMPROVE_Q, b["h"])
        return True
    k = int(parts[2]) if key == "zm" and len(parts) > 2 and parts[2] in ("2", "3") else 1
    kk = (uid, bid, key, k)
    if time.time() - ACTIVE_FILES.get(kk, 0) < 10:
        _ans(cq, "Уже делаю…")
        return True
    ACTIVE_FILES[kk] = time.time()
    _ans(cq, {"in": "Рисую разрезы…", "td": "Рисую вид сверху…", "zm": "Увеличиваю ×%d…" % k}.get(key, "…"))
    FAST.submit(job_view, chat, uid, bid, key, k)
    return True


# ─── Админ: выдача и управление ─────────────────────────────────────────────
def premium_admin_cmd(chat, uid, cmd, arg, msg):
    if cmd not in PREM_ADMIN_CMDS:
        return False
    A = arg.strip()
    if cmd in ("givesubscription", "givesub", "givevip"):
        parts = A.split()
        if not parts:
            tg.send(chat, "Использование: /givesubscription @ник [срок]\nСрок: 15m, 3h, 1d, 7d, 30d, 1y, forever (или 2w, 6mo). Без срока — 30 дней.\n"
                          "Если у человека уже есть Premium — срок прибавится. Работает и по ID: /givesubscription 123456789 7d")
            return True
        dur = parse_dur("".join(parts[1:])) if len(parts) > 1 else 2592000
        if dur is None:
            tg.send(chat, "Не понял срок «%s». Примеры: 15m, 3h, 1d, 7d, 30d, 1y, forever." % " ".join(parts[1:]))
            return True
        who = parts[0]
        t = find_user(who)
        label = "навсегда" if dur >= 10 ** 9 else fdur(dur)
        if t is None:
            uname = who.lstrip("@").lower()
            if not re.fullmatch(r"[a-z0-9_]{4,32}", uname):
                tg.send(chat, "Не похоже на ник. Пример: /givesubscription @username 30d")
                return True
            with S.lock:
                w = S.d.setdefault("prem_wait", {})
                w[uname] = (10 ** 10 if dur >= 10 ** 9 else min(10 ** 9, w.get(uname, 0) + dur))
            S.save()
            tg.send(chat, "📝 @%s ещё не писал боту, поэтому не знаю его ID. Premium (%s) выдам автоматически, как только он напишет боту (/start)." % (uname, label))
            return True
        exp = grant(t, dur)
        sent = True
        try:
            tg.send(t, "🎉 Тебе выдан Premium (%s)!\nДействует: %s\n\nПопробуй: /build город для РП — и жми «Вид сверху» и «Вид изнутри».\nНастройки мира: /world · все возможности: /premium" % (label, left_text(t)))
        except Exception:
            sent = False
        tg.send(chat, "👑 Premium выдан: %s (id %d) на %s.\nДействует: %s%s" % (uname_of(t), t, label, fdate(exp), "" if sent else "\n⚠️ Написать ему не смог (он не запускал бота или заблокировал его)."))
        return True
    if cmd in ("removesubscription", "delsub", "takesub"):
        t = find_user(A.split()[0]) if A.split() else None
        if t is None:
            tg.send(chat, "Использование: /removesubscription @ник")
            return True
        with S.lock:
            had = S.d["prem"].pop(str(t), None)
        S.save()
        tg.send(chat, ("🗑 Premium снят у %s (id %d)." if had else "У %s (id %d) и не было Premium.") % (uname_of(t), t))
        return True
    if cmd in ("premiumlist", "vips"):
        now = time.time()
        rows = sorted(((e, u) for u, e in S.d["prem"].items() if e > now))
        if not rows:
            tg.send(chat, "Сейчас Premium ни у кого нет. Выдать: /givesubscription @ник 30d")
            return True
        tg.send(chat, "👑 Premium сейчас (%d):\n" % len(rows) + "\n".join("%s (id %s) — %s" % (uname_of(u), u, left_text(int(u))) for e, u in rows[:60]))
        return True
    if cmd == "setpremlimit":
        if not A.isdigit():
            tg.send(chat, "Сейчас у Premium: %d построек в сутки. Изменить: /setpremlimit <число>" % S.d["prem_limit"])
            return True
        S.d["prem_limit"] = int(A)
        S.save()
        tg.send(chat, "✅ Лимит Premium: %d построек в сутки." % S.d["prem_limit"])
        return True
    if cmd in ("setprice", "prices"):
        w = A.split()
        if len(w) == 2 and plan_by(w[0]) and w[1].isdigit() and int(w[1]) > 0:
            S.d["prices"][w[0]] = int(w[1])
            S.save()
            tg.send(chat, "✅ Цена «%s» теперь %s⭐" % (plan_by(w[0])[1], w[1]))
            return True
        tg.send(chat, "Цены (⭐):\n" + "\n".join("%s — %s: %d" % (c, n, plan_stars(c)) for c, n, _s, _st, _i in PLANS) + "\n\nИзменить: /setprice <код> <звёзды>, например /setprice 1d 100")
        return True
    if cmd in ("requests", "payments"):
        wait = [(rid, x) for rid, x in S.d["pay"].items() if x["st"] == "wait"]
        if not wait:
            tg.send(chat, "Заявок на проверке нет.")
            return True
        for rid, x in sorted(wait, key=lambda t: t[1]["ts"]):
            tg.send(chat, admin_req_text(rid, x), admin_req_markup(rid))
        return True
    return False


# ===REFERRAL-BLOCK===
# ═════════════════════════════════════════════════════════════════════════════
#  11c. БЕСПЛАТНЫЕ ЗАПРОСЫ: рефералы (1 новый человек = +1) и задание «подпишись на канал» (+2)
# ═════════════════════════════════════════════════════════════════════════════
FREE_CMDS = ("free", "bonus", "bonuses", "tasks", "task", "ref", "invite", "referral", "gift")
BONUS_PAID = set()            # uid, у которых текущая постройка оплачена бонусным запросом (для возврата при ошибке)
_chk_t = {}                   # uid -> время последней проверки подписки (антиспам)


def bonus_of(uid):
    return max(0, int((S.d["users"].get(str(uid)) or {}).get("bonus", 0) or 0))


def add_bonus(uid, n):
    with S.lock:
        us = S.d["users"].get(str(uid))
        if us is None:
            return False
        us["bonus"] = max(0, int(us.get("bonus", 0) or 0) + n)
    S.save()
    return True


def charge_build(uid):
    """Списывает попытку: сначала дневной лимит, а когда он кончился, — бонусный запрос."""
    lim = eff_limit(uid)
    if lim and used_today(uid) >= lim and bonus_of(uid) > 0:
        add_bonus(uid, -1)
        BONUS_PAID.add(uid)
    else:
        bump(uid, +1)


def refund_charge(uid):
    if uid in BONUS_PAID:
        BONUS_PAID.discard(uid)
        add_bonus(uid, +1)
    else:
        bump(uid, -1)


def ref_link(uid):
    return "https://t.me/%s?start=ref_%d" % (BOT_USERNAME, uid) if BOT_USERNAME else ""


def task_done(uid):
    return bool((S.d["users"].get(str(uid)) or {}).get("task_sub"))


def ref_count(uid):
    return int((S.d["users"].get(str(uid)) or {}).get("refs", 0) or 0)


def free_text(uid):
    us = S.d["users"].get(str(uid)) or {}
    link = ref_link(uid)
    t = "🎁 Бесплатные запросы\n\nСейчас у тебя: %d бонусных. Они тратятся, когда дневной лимит построек закончился.\n\n" % bonus_of(uid)
    t += "1️⃣ Пригласи друга: +%d бесплатный запрос за каждого нового человека, который запустит бота по твоей ссылке.\n" % REF_BONUS
    t += "Твоя ссылка:\n%s\nПриглашено: %d\n" % (link, ref_count(uid))
    if REF_MAX:
        t += "(засчитывается до %d приглашённых)\n" % REF_MAX
    t += "\n2️⃣ Задание: подпишись на канал https://t.me/%s и получи +%d бесплатных запроса.\n" % (TASK_CHANNEL, TASK_BONUS)
    t += "Статус: " + ("✅ выполнено" if us.get("task_sub") else "⬜ не выполнено. Подпишись и нажми «Проверить».")
    return t


def free_markup(uid):
    rows = []
    link = ref_link(uid)
    if link:
        share = "https://t.me/share/url?url=%s&text=%s" % (requests.utils.quote(link, safe=""), requests.utils.quote("Строю постройки для Minecraft с помощью ИИ. Заходи!", safe=""))
        rows.append([{"text": "👥 Отправить ссылку другу", "url": share}])
    if not task_done(uid):
        rows.append([{"text": "📢 Подписаться на канал", "url": "https://t.me/" + TASK_CHANNEL}])
        rows.append([{"text": "✅ Проверить подписку", "callback_data": "fr:chk"}])
    return {"inline_keyboard": rows}


def cmd_free(chat, uid):
    tg.send(chat, free_text(uid), free_markup(uid))


def ref_on_start(uid, arg, existed):
    """Реферал засчитывается только за человека, которого бот раньше не видел, и только один раз."""
    if existed or not (arg or "").startswith("ref_"):
        return
    try:
        inv = int(arg[4:])
    except ValueError:
        return
    if inv == uid or inv in S.d["banned"]:
        return
    give = 0
    with S.lock:
        us, iu = S.d["users"].get(str(uid)), S.d["users"].get(str(inv))
        if us is None or iu is None or us.get("ref_by"):
            return
        us["ref_by"] = inv
        iu["refs"] = int(iu.get("refs", 0) or 0) + 1
        if not REF_MAX or iu["refs"] <= REF_MAX:
            give = REF_BONUS
            iu["bonus"] = int(iu.get("bonus", 0) or 0) + give
        total, nm = int(iu.get("bonus", 0) or 0), (us.get("n") or us.get("u") or "новый игрок")
    S.save()
    try:
        if give:
            tg.send(inv, "🎉 По твоей ссылке пришёл новый человек (%s)!\n+%d бесплатный запрос. Бонусных сейчас: %d.\nВсе способы: /free" % (nm, give, total))
        else:
            tg.send(inv, "🎉 По твоей ссылке пришёл новый человек (%s)! Лимит наград за приглашения (%d) уже исчерпан." % (nm, REF_MAX))
    except Exception:
        pass


def check_subscription(uid):
    """(True, '') — подписан; (False, '') — не подписан; (None, причина) — проверить не удалось."""
    try:
        m = tg.call("getChatMember", {"chat_id": "@" + TASK_CHANNEL, "user_id": uid}, tries=2)
    except TGError as e:
        d = str(e).lower()
        if "user not found" in d or "participant_id_invalid" in d:
            return False, ""
        return None, str(e)
    st = (m or {}).get("status")
    if st in ("creator", "administrator", "member"):
        return True, ""
    if st == "restricted":
        return bool(m.get("is_member")), ""
    return False, ""


def on_callback_free(cq, data):
    uid, chat, mid = cq["from"]["id"], cq["message"]["chat"]["id"], cq["message"]["message_id"]
    if data != "fr:chk":
        return _ans(cq)
    if task_done(uid):
        _ans(cq, "Задание уже выполнено ✅")
        return tg.safe_edit(chat, mid, free_text(uid), free_markup(uid))
    if time.time() - _chk_t.get(uid, 0) < 3:
        return _ans(cq, "Секунду…")
    _chk_t[uid] = time.time()
    ok, why = check_subscription(uid)
    if ok is None:
        log.warning("проверка подписки на @%s не удалась: %s", TASK_CHANNEL, why)
        notify_admins_once("taskchan", "⚠️ Не могу проверить подписку на @%s: %s\nЧтобы проверка работала, @%s должен быть каналом/группой, а бот — его администратором (Telegram не даёт боту видеть подписчиков иначе). "
                                       "Если это не канал, а бот, задание не сработает: смени канал переменной TASK_CHANNEL." % (TASK_CHANNEL, why[:150], TASK_CHANNEL), every=3600)
        return _ans(cq, "Не получилось проверить подписку. Попробуй позже, админ уже в курсе.", True)
    if not ok:
        return _ans(cq, "Подписки пока не вижу. Подпишись на канал и нажми «Проверить» ещё раз.", True)
    with S.lock:
        us = S.d["users"].get(str(uid))
        first = us is not None and not us.get("task_sub")
        if first:
            us["task_sub"] = now_ts()
            us["bonus"] = int(us.get("bonus", 0) or 0) + TASK_BONUS
    if not first:
        return _ans(cq, "Задание уже выполнено ✅")
    S.save()
    _ans(cq, "Готово! +%d бесплатных запроса 🎉" % TASK_BONUS, True)
    tg.safe_edit(chat, mid, free_text(uid), free_markup(uid))


def on_message(msg):
    u, chat = msg.get("from"), msg["chat"]
    if not u or u.get("is_bot"):
        return
    uid, cid = u["id"], chat["id"]
    existed = str(uid) in S.d["users"]
    touch_user(u)
    text = (msg.get("text") or "").strip()
    if not text.startswith("/"):
        if chat["type"] == "private" and text:
            if uid in S.d["banned"]:
                return
            tg.send(cid, "Чтобы построить, напиши: /build <что построить>\nНапример: /build маяк на скале\nВсе команды: /help")
        return
    tok, _, rest = text.partition(" ")
    cmd, _, tgt = tok[1:].partition("@")
    if tgt and BOT_USERNAME and tgt.lower() != BOT_USERNAME.lower():
        return
    cmd = cmd.lower()
    arg = rest.strip()
    if uid in S.d["banned"] and not is_admin(uid):
        return
    if cmd == "start":
        if chat["type"] == "private":
            ref_on_start(uid, arg, existed)
        return tg.send(cid, HELP)
    if cmd == "help":
        return tg.send(cid, HELP)
    if cmd in FREE_CMDS:
        return cmd_free(cid, uid)
    if cmd == "id":
        return tg.send(cid, "Твой Telegram ID: %d" % uid)
    if cmd == "build":
        return cmd_build(cid, uid, arg, msg.get("message_id"))
    if cmd == "edit":
        return cmd_edit(cid, uid, arg, msg.get("message_id"))
    if cmd == "me":
        return cmd_me(cid, uid)
    if cmd in ("settings", "setting", "config"):
        return cmd_settings(cid, uid)
    if cmd in ("model", "models", "ai"):
        return cmd_model(cid, uid)
    if cmd in PREM_CMDS:
        return premium_user_cmd(cid, uid, cmd, arg, msg)
    if cmd == "cancel":
        ev = ACTIVE.get(uid)
        if ev:
            ev.set()
            return tg.send(cid, "🛑 Останавливаю…")
        return tg.send(cid, "Сейчас ничего не строится.")
    if is_admin(uid):
        if chat["type"] != "private":
            if cmd in ("admin", "adm", "panel", "off", "on", "update", "addkey", "keys", "delkey", "testkeys", "setmodel", "limit", "ban", "unban", "banned", "broadcast", "backup", "stats", "status") + PREM_ADMIN_CMDS:
                return tg.send(cid, "🔒 Админ-команды работают только в личке с ботом.")
            return
        if not premium_admin_cmd(cid, uid, cmd, arg, msg):
            admin_command(cid, uid, cmd, arg, msg)


def on_callback(cq):
    data = cq.get("data") or ""
    msg = cq.get("message")
    if not msg:
        return
    touch_user(cq["from"])
    if data.startswith("ad:"):
        return on_callback_admin(cq, data)
    if data.startswith("bc:"):
        return on_callback_broadcast(cq, data)
    if cq["from"]["id"] in S.d["banned"] and not is_admin(cq["from"]["id"]):
        return tg.call("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Доступ закрыт.", "show_alert": True})
    if data.startswith("fr:"):
        return on_callback_free(cq, data)
    if premium_callback(cq, data):
        return
    if data.startswith("sg:"):
        return on_callback_settings(cq, data)
    if data.startswith("md:"):
        return on_callback_model(cq, data)
    on_callback_user(cq, data)


def handle_update(upd):
    try:
        uid_ = upd.get("update_id")
        if uid_ is not None:
            if uid_ in _seen:
                return
            _seen.append(uid_)
            del _seen[:-500]
        if "message" in upd:
            on_message(upd["message"])
        elif "callback_query" in upd:
            on_callback(upd["callback_query"])
    except TGError as e:
        log.warning("Telegram: %s", e)
    except Exception:
        log.error("handle_update: %s", traceback.format_exc())


# ═════════════════════════════════════════════════════════════════════════════
#  13. ЗАПУСК: webhook (Render и т.п.) или long polling (свой ПК/сервер)
# ═════════════════════════════════════════════════════════════════════════════
SECRET = _env("WEBHOOK_SECRET") or hashlib.sha256(("wh" + BOT_TOKEN).encode()).hexdigest()[:32]


class Hook(BaseHTTPRequestHandler):
    def _ok(self, body=None):
        body = body or ("BuildAI bot is running v%s" % BOT_VERSION).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        self._ok()

    do_HEAD = do_GET

    def do_POST(self):
        if self.path != "/tg/" + SECRET or not hmac.compare_digest(self.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), SECRET):
            self.send_response(403)
            self.end_headers()
            return
        try:
            n = min(int(self.headers.get("Content-Length", "0")), 2_000_000)
            upd = json.loads(self.rfile.read(n))
            FAST.submit(handle_update, upd)
        except Exception as e:
            log.warning("webhook: %s", e)
        self._ok(b"ok")

    def log_message(self, *a):
        pass


def run_webhook():
    url = "%s/tg/%s" % (WEBHOOK_BASE.rstrip("/"), SECRET)
    tg.call("setWebhook", {"url": url, "secret_token": SECRET, "allowed_updates": ["message", "callback_query"], "max_connections": 20})
    log.info("webhook: %s/tg/***  порт %d", WEBHOOK_BASE, PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Hook).serve_forever()


def run_polling():
    tg.call("deleteWebhook", {"drop_pending_updates": False})
    log.info("long polling")
    off = 0
    while True:
        try:
            ups = tg.call("getUpdates", {"offset": off, "timeout": 50, "allowed_updates": ["message", "callback_query"]}, timeout=65, tries=1)
        except TGError as e:
            log.warning("getUpdates: %s", e)
            time.sleep(3)
            continue
        for u in ups or []:
            off = u["update_id"] + 1
            FAST.submit(handle_update, u)


def selftest():
    spec = {"name": "selftest", "ops": [{"t": "fill", "b": "stone_bricks", "a": [0, 0, 0], "c": [12, 0, 12]},
                                         {"t": "hollow", "b": "oak_planks", "a": [2, 1, 2], "c": [10, 6, 10]},
                                         {"t": "sphere", "b": "glass", "a": [6, 7, 6], "r": 4, "hollow": True, "half": "top"},
                                         {"t": "set", "b": "glowstone", "a": [6, 3, 6]}]}
    r = run_spec(spec)
    open("selftest_preview.png", "wb").write(render_preview(r))
    open("selftest.mcworld", "wb").write(build_mcworld_bytes(r, "BuildAI selftest"))
    print("OK: selftest_preview.png и selftest.mcworld созданы (%d блоков)" % r.n)


def main():
    global BOT_USERNAME
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if "--selftest" in sys.argv:
        return selftest()
    if not BOT_TOKEN:
        sys.exit("Не задан BOT_TOKEN (токен от @BotFather). Пример: BOT_TOKEN=123:ABC python bot.py")
    os.makedirs(DATA_DIR, exist_ok=True)
    me = tg.call("getMe")
    BOT_USERNAME = me.get("username", "")
    log.info("бот @%s, админы: %s", BOT_USERNAME, ADMIN_IDS)
    if not S.load_file() and TG_BACKUP:
        st = restore_from_tg()
        if st == "error":
            BK["blocked"] = True
            log.warning("копию в Telegram прочитать не удалось — резервное копирование приостановлено до успеха")
    for k in TH_KEYS_ENV:
        add_key(k, "из TH_KEYS")
    threading.Thread(target=backup_loop, daemon=True).start()
    threading.Thread(target=prem_watch, daemon=True).start()
    if WEBHOOK_BASE:
        run_webhook()
    else:
        run_polling()


if __name__ == "__main__":
    main()
