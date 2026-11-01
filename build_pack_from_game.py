# -*- coding: utf-8 -*-
"""build_pack_from_game.py —— 直接从《Hearts of Iron IV》安装目录（或模组目录）生成 .pdxmap。

不再依赖「悖论制图」导出的中间包。

用法：
    python build_pack_from_game.py --game "D:/Steam/.../Hearts of Iron IV" --out vanilla.pdxmap
    python build_pack_from_game.py --game "<模组目录>" --base "D:/Steam/.../Hearts of Iron IV" \
                                   --label "千周之国" --id twr --out twr.pdxmap

    --game  优先读取的目录（模组）
    --base  基础游戏目录（模组里缺的文件回落到这里）
    --locale 优先语言，默认 simp_chinese，回落到 english
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile

import numpy as np
from PIL import Image, ImageFilter

NO = 65535
SEA_LEVEL = 89

# ---------------------------------------------------------------- 文件系统（模组覆盖）

class VFS:
    """先查 mod 目录，再查基础游戏目录。"""

    def __init__(self, roots):
        self.roots = [r for r in roots if r and os.path.isdir(r)]

    def find(self, rel):
        rel = rel.replace("/", os.sep)
        for r in self.roots:
            p = os.path.join(r, rel)
            if os.path.exists(p):
                return p
        return None

    def glob(self, rel_dir, ext=".txt"):
        """返回该目录下所有文件；同名文件以优先级高的为准。"""
        seen = {}
        for r in self.roots:
            d = os.path.join(r, rel_dir.replace("/", os.sep))
            if not os.path.isdir(d):
                continue
            for fn in os.listdir(d):
                if fn.lower().endswith(ext) and fn not in seen:
                    seen[fn] = os.path.join(d, fn)
        return list(seen.values())

    def glob_deep(self, rel_dir, ext=".yml"):
        seen = {}
        for r in self.roots:
            d = os.path.join(r, rel_dir.replace("/", os.sep))
            if not os.path.isdir(d):
                continue
            for cur, _dirs, files in os.walk(d):
                for fn in files:
                    if fn.lower().endswith(ext) and fn not in seen:
                        seen[fn] = os.path.join(cur, fn)
        return list(seen.values())


def read(path):
    with open(path, encoding="utf-8-sig", errors="ignore") as f:
        return f.read()


def strip_comments(s):
    """去掉 # 注释，但不动引号里的内容。"""
    out = []
    inq = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '"':
            inq = not inq
            out.append(c)
        elif c == "#" and not inq:
            while i < len(s) and s[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------- 本地化

def load_loc(vfs, prefer="simp_chinese"):
    """返回 key -> 文本。优先 prefer 语言，缺的用 english 补。"""
    order = [prefer, "english"]
    maps = {k: {} for k in order}
    files = vfs.glob_deep("localisation", ".yml")
    pat = re.compile(r'^\s*([A-Za-z0-9_.\-]+):\d*\s*"((?:[^"\\]|\\.)*)"', re.M)
    for f in files:
        low = f.replace("\\", "/").lower()
        lang = None
        for k in order:
            if k in low:
                lang = k
                break
        if lang is None:
            continue
        txt = read(f)
        for m in pat.finditer(txt):
            maps[lang].setdefault(m.group(1), m.group(2).replace("\\n", " "))
    out = dict(maps.get("english", {}))
    out.update(maps.get(prefer, {}))
    return out


# ---------------------------------------------------------------- 省份图

def load_provinces(vfs):
    defcsv = vfs.find("map/definition.csv")
    bmp = vfs.find("map/provinces.bmp")
    if not defcsv or not bmp:
        sys.exit("缺少 map/definition.csv 或 map/provinces.bmp")

    info = {}          # pid -> water?
    rgb2id = {}
    for line in read(defcsv).splitlines():
        parts = line.split(";")
        if len(parts) < 5:
            continue
        try:
            pid, r, g, b = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        except ValueError:
            continue
        kind = parts[4].strip().lower()
        info[pid] = (kind != "land")
        if pid > 0:
            rgb2id[(r << 16) | (g << 8) | b] = pid

    im = Image.open(bmp).convert("RGB")
    W, H = im.size
    a = np.asarray(im).astype(np.uint32)
    key = (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]
    uniq, inv = np.unique(key, return_inverse=True)
    lut = np.zeros(len(uniq), dtype=np.uint16)
    miss = 0
    for i, k in enumerate(uniq):
        v = rgb2id.get(int(k))
        if v is None:
            miss += 1
        else:
            lut[i] = v
    prov = lut[inv].reshape(H, W).astype(np.uint16)
    if miss:
        print("  警告：%d 种颜色在 definition.csv 里找不到（按 0 处理）" % miss)
    return prov, info, W, H


# ---------------------------------------------------------------- 州 / 战略区

def parse_states(vfs, loc):
    states = []
    for f in vfs.glob("history/states"):
        s = strip_comments(read(f))
        blocks = _split_blocks(s, "state") or [s]
        for blk in blocks:
          _parse_one_state(blk, loc, states)
    return states


def _parse_one_state(s, loc, states):
    m_id = re.search(r"\bid\s*=\s*(\d+)", s)
    if m_id:
        sid = int(m_id.group(1))
        m_name = re.search(r'\bname\s*=\s*"([^"]+)"', s)
        loc_key = m_name.group(1) if m_name else "STATE_%d" % sid
        m_prov = re.search(r"\bprovinces\s*=\s*\{([^}]*)\}", s)
        provs = [int(x) for x in re.findall(r"\d+", m_prov.group(1))] if m_prov else []
        m_owner = re.search(r"\bowner\s*=\s*([A-Za-z0-9_]+)", s)
        owner = m_owner.group(1) if m_owner else None
        vps = []
        for m in re.finditer(r"\bvictory_points\s*=\s*\{([^}]*)\}", s):
            nums = [int(x) for x in re.findall(r"\d+", m.group(1))]
            for i in range(0, len(nums) - 1, 2):
                vps.append((nums[i], nums[i + 1]))
        states.append({
            "id": sid, "loc": loc_key, "name": loc.get(loc_key, loc_key),
            "provinces": provs, "owner": owner, "vps": vps,
        })


def _split_blocks(s, head):
    """把文件按 "head = {" 切成若干块，返回每个块的文本。"""
    idx = [m.start() for m in re.finditer(head + r"\s*=\s*\{", s)]
    out = []
    for i, a in enumerate(idx):
        b = idx[i + 1] if i + 1 < len(idx) else len(s)
        out.append(s[a:b])
    return out


def parse_srs(vfs, loc):
    out = []
    for f in vfs.glob("map/strategicregions"):
        s = strip_comments(read(f))
        blocks = _split_blocks(s, "strategic_region") or [s]
        for b in blocks:
            m_id = re.search(r"\bid\s*=\s*(\d+)", b)
            if not m_id:
                continue
            m_name = re.search(r'\bname\s*=\s*"([^"]+)"', b)
            key = m_name.group(1) if m_name else ""
            m_prov = re.search(r"\bprovinces\s*=\s*\{([^}]*)\}", b)
            provs = [int(x) for x in re.findall(r"\d+", m_prov.group(1))] if m_prov else []
            out.append({"id": int(m_id.group(1)), "loc": key,
                        "name": loc.get(key, key or ("战略区 %d" % int(m_id.group(1)))),
                        "provinces": provs})
    return out


# ---------------------------------------------------------------- 国家

def parse_countries(vfs, loc):
    tag_file = {}
    for f in vfs.glob("common/country_tags"):
        for m in re.finditer(r'([A-Z0-9]{3})\s*=\s*"([^"]+)"', strip_comments(read(f))):
            tag_file.setdefault(m.group(1), m.group(2))

    caps = {}
    for f in vfs.glob("history/countries"):
        tag = os.path.basename(f)[:3].upper()
        s = strip_comments(read(f))
        m = re.search(r"\bcapital\s*=\s*(\d+)", s)
        if m:
            caps[tag] = int(m.group(1))

    # 颜色：先看 common/countries/colors.txt 里的 TAG = { color = rgb {...} }，
    # 再看每国自己文件里的顶层 color。两种写法游戏里都有。
    tag_color = {}
    file_color = {}
    rgb = lambda a, b, c: [max(0, min(255, int(round(float(x) if float(x) > 1.5 else float(x) * 255))))
                           for x in (a, b, c)]
    for f in vfs.glob("common/countries"):
        raw = strip_comments(read(f))
        for m in re.finditer(r"([A-Z0-9]{3})\s*=\s*\{[^}]*?\bcolor\s*=\s*(?:rgb\s*)?\{\s*"
                             r"([\d.]+)\s+([\d.]+)\s+([\d.]+)", raw, re.S):
            tag_color.setdefault(m.group(1), rgb(m.group(2), m.group(3), m.group(4)))
        if os.path.basename(f).lower() != "colors.txt":
            m = re.search(r"^[ \t]*color\s*=\s*(?:rgb\s*)?\{\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)",
                          raw, re.M)
            if m:
                file_color[os.path.basename(f)] = rgb(m.group(1), m.group(2), m.group(3))

    out = {}
    for tag, rel in tag_file.items():
        base_name = os.path.basename(rel.replace("\\", "/"))
        color = tag_color.get(tag) or file_color.get(base_name) or [120, 120, 120]
        out[tag] = {"tag": tag, "name": loc.get(tag, tag), "color": color, "capital": caps.get(tag)}
    print("  取到颜色 %d 个标签（colors.txt 优先）" % sum(1 for t in out if t in tag_color or
          os.path.basename(tag_file[t].replace("\\", "/")) in file_color))
    return out


# ---------------------------------------------------------------- 地形烘焙

def hillshade(hm):
    dzdx = (np.roll(hm, -1, 1) - np.roll(hm, 1, 1)) * 0.5
    dzdy = (np.roll(hm, -1, 0) - np.roll(hm, 1, 0)) * 0.5
    s = 2.2
    nx, ny, nz = -dzdx * s, -dzdy * s, np.ones_like(hm)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    d = (nx * inv) * -0.55 + (ny * inv) * -0.55 + (nz * inv) * 0.63
    return (0.72 + 0.55 * np.clip(d, 0, 1) ** 0.9).astype(np.float32)


def land_layer(hm, H, W):
    e = np.clip((hm - (SEA_LEVEL + 6)) / 55.0, 0, 1)[..., None]
    stops = [(0.00, (104, 126, 84)), (0.35, (134, 143, 99)),
             (0.65, (163, 155, 125)), (1.00, (188, 184, 172))]
    out = np.zeros((H, W, 3), np.float32)
    for i in range(len(stops) - 1):
        a, ca = stops[i]
        b, cb = stops[i + 1]
        m = (e[..., 0] >= a) & (e[..., 0] <= b)
        f = np.clip((e[..., 0] - a) / (b - a), 0, 1)[..., None]
        out[m] = np.array(ca, np.float32) * (1 - f[m]) + np.array(cb, np.float32) * f[m]
    return out


def bake_terrain(vfs, water_px, H, W):
    p = vfs.find("map/heightmap.bmp")
    if not p:
        print("  没有 heightmap.bmp，用纯色地形")
        terr = np.full((H, W, 3), 120, np.uint8)
    else:
        hm = np.array(Image.open(p).convert("L").resize((W, H), Image.BILINEAR), dtype=np.float32)
        land_px = ~water_px
        m = Image.fromarray((land_px * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(22))
        sh = (np.array(m, dtype=np.float32) / 255.0)[..., None]
        sea = np.array([32, 55, 86], np.float32) * (1 - sh) + np.array([74, 106, 136], np.float32) * sh
        land = land_layer(hm, H, W) * hillshade(hm)[..., None]
        terr = np.clip(np.where(water_px[..., None], sea, land), 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(terr).save(buf, "JPEG", quality=88, optimize=True, subsampling=1)
    return buf.getvalue()


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="从游戏/模组目录生成 .pdxmap")
    ap.add_argument("--game", required=True, help="模组目录（原版直接填游戏目录）")
    ap.add_argument("--base", default="", help="基础游戏目录（可选，模组缺文件时回落）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--id", default="custom")
    ap.add_argument("--label", default="自定义地图")
    ap.add_argument("--locale", default="simp_chinese")
    ap.add_argument("--scenario-name", default="")
    args = ap.parse_args()

    vfs = VFS([args.game, args.base])
    print("读取本地化…")
    loc = load_loc(vfs, args.locale)
    print("  %d 条" % len(loc))

    print("解析省份图…")
    prov, info, W, H = load_provinces(vfs)
    NT = int(prov.max()) + 1
    print("  %dx%d，%d 个省份" % (W, H, NT))

    water = np.zeros(NT, dtype=bool)
    for pid, is_w in info.items():
        if pid < NT:
            water[pid] = is_w
    water_px = water[prov]

    print("解析州 / 战略区 / 国家…")
    states = parse_states(vfs, loc)
    srs = parse_srs(vfs, loc)
    countries = parse_countries(vfs, loc)
    print("  州 %d / 战略区 %d / 国家 %d" % (len(states), len(srs), len(countries)))

    # ---- 归属
    owner_of = np.array([None] * NT, dtype=object)
    for st in states:
        if not st["owner"]:
            continue
        for p in st["provinces"]:
            if 0 < p < NT and owner_of[p] is None:
                owner_of[p] = st["owner"]

    # ---- 省份质心（给标注锚点用）
    ys, xs = np.nonzero(prov > 0)
    pids = prov[ys, xs]
    cnt = np.bincount(pids, minlength=NT)
    sx = np.bincount(pids, weights=xs, minlength=NT)
    sy = np.bincount(pids, weights=ys, minlength=NT)
    cx = np.where(cnt > 0, sx / np.maximum(cnt, 1), 0.0)
    cy = np.where(cnt > 0, sy / np.maximum(cnt, 1), 0.0)

    # ---- 头衔
    keys, tiers, parents, names, names_en, locs = [], [], [], [], [], []
    colors, pcount, area, block = [], [], [], []
    lx, ly, gx, gy = [], [], [], []

    def add(key, tier, parent, name, color, provs):
        i = len(keys)
        keys.append(key); tiers.append(tier); parents.append(parent)
        names.append(name); names_en.append(name); locs.append(key)
        colors.append(list(color)); pcount.append(len(provs))
        area.append(int(sum(int(cnt[p]) for p in provs if 0 < p < NT)))
        block.append(0)
        if provs:
            ax = float(np.mean([cx[p] for p in provs if 0 < p < NT])) if any(0 < p < NT for p in provs) else 0.0
            ay = float(np.mean([cy[p] for p in provs if 0 < p < NT])) if any(0 < p < NT for p in provs) else 0.0
        else:
            ax = ay = 0.0
        lx.append(ax); ly.append(ay); gx.append(ax); gy.append(ay)
        return i

    tm = np.full((6, NT), NO, dtype=np.uint16)

    # 水域
    water_id = add("#water", 2, -1, "水域", (60, 90, 120), list(np.nonzero(water)[0]))
    for p in np.nonzero(water)[0]:
        tm[2][p] = water_id

    # 战略区
    sr_ids = {}
    for sr in srs:
        i = add("SR_%d" % sr["id"], 3, -1, sr["name"], (110, 110, 110), sr["provinces"])
        sr_ids[sr["id"]] = i
        for p in sr["provinces"]:
            if 0 < p < NT:
                tm[3][p] = i

    # 州
    state_ids = {}
    for st in states:
        col = countries.get(st["owner"], {}).get("color", (120, 120, 120)) if st["owner"] else (120, 120, 120)
        i = add("STATE_%d" % st["id"], 4, -1, st["name"], col, st["provinces"])
        state_ids[st["id"]] = i
        for p in st["provinces"]:
            if 0 < p < NT:
                tm[4][p] = i

    # 国家
    used = {}
    for p in range(1, NT):
        t = owner_of[p]
        if t:
            used.setdefault(t, []).append(p)
    country_ids = {}
    for tag, provs in used.items():
        c = countries.get(tag, {"name": tag, "color": [120, 120, 120]})
        i = add("1936_" + tag, 0, -1, c["name"], c["color"], provs)
        country_ids[tag] = i
        for p in provs:
            tm[0][p] = i
            tm[1][p] = i          # 单剧本：第二档与第一档相同

    # 省份
    vp_map = {}
    for st in states:
        for p, v in st["vps"]:
            vp_map[p] = max(vp_map.get(p, 0), v)

    for p in range(1, NT):
        if water[p]:
            continue
        nm = loc.get("VICTORY_POINTS_%d" % p) or loc.get("PROV%d" % p) or ""
        i = add("PROV_%d" % p, 5, -1, nm, (110, 110, 110), [p])
        tm[5][p] = i

    titles = {
        "keys": keys, "tiers": tiers, "parents": parents,
        "names": names, "namesEn": names_en, "locKeys": locs,
        "colors": colors, "provCount": pcount, "area": area, "blockArea": block,
        "lx": lx, "ly": ly, "gx": gx, "gy": gy,
    }

    cities = {
        "cities": sorted([[p, v] for p, v in vp_map.items() if 0 < p < NT], key=lambda r: -r[1]),
        "capitals": sorted({c["capital"] for c in countries.values()
                            if c.get("capital") and 0 < c["capital"] < NT}),
    }

    print("烘焙地形…")
    terr = bake_terrain(vfs, water_px, H, W)

    name = args.scenario_name or args.label
    manifest = {
        "format": "pdxmap", "formatVersion": 3, "dataSchema": 1,
        "id": args.id, "game": "hoi4", "label": args.label,
        "note": "%d x %d" % (W, H), "version": "",
        "mapWidth": W, "mapHeight": H, "numProvinces": NT,
        "tiers": ["country", "country2", "water", "sr", "state", "province"],
        "waterTier": 2, "terrain": "terrain.jpg", "cities": "cities.json",
        "dataVersion": 1,
        "scenarios": [{"key": "default", "name": name, "tier": 0}],
        "stats": {"numProvinces": NT, "numTitles": len(keys),
                  "numStates": len(states), "numSR": len(srs), "numCountries": len(used)},
    }
    meta = {
        "gameVersion": "",
        "tiers": manifest["tiers"],
        "capitals": {t: c["capital"] for t, c in countries.items() if c.get("capital")},
    }

    print("写出 %s" % args.out)
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        z.writestr("meta.json", json.dumps(meta, ensure_ascii=False))
        z.writestr("titles.json", json.dumps(titles, ensure_ascii=False, separators=(",", ":")))
        z.writestr("provinces_id.bin", zlib_compress(prov.tobytes()), compress_type=zipfile.ZIP_STORED)
        z.writestr("titlemap.bin", zlib_compress(tm.tobytes()), compress_type=zipfile.ZIP_STORED)
        z.writestr("terrain.jpg", terr, compress_type=zipfile.ZIP_STORED)
        z.writestr("cities.json", json.dumps(cities, ensure_ascii=False, separators=(",", ":")))
    print("完成：%d KB，省份 %d，头衔 %d，城市 %d" % (
        os.path.getsize(args.out) // 1024, NT, len(keys), len(cities["cities"])))


def zlib_compress(b):
    import zlib
    return zlib.compress(b, 9)


if __name__ == "__main__":
    main()
