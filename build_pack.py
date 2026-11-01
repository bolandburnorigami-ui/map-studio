# -*- coding: utf-8 -*-
"""build_pack.py —— 用本机的《Hearts of Iron IV》安装，生成编辑器要用的 .pdxmap 数据包。

用法：
    python build_pack.py --hoi4 "D:/Steam/steamapps/common/Hearts of Iron IV" \
                         --src  pdx-hoi4-vanilla.pdxmap \
                         --out  world-1936.pdxmap

参数说明：
    --hoi4  游戏安装目录（要求里面有 map/heightmap.bmp 与 history/states/）
    --src   输入包：含省份图与头衔树的原始 .pdxmap，由「悖论制图」导出
    --out   输出包路径
    --fixes 边界修正配置（默认读同目录的 fixes.json，可省略）

注意：--src 需要由配套的「悖论制图」工具从游戏导出，仓库里不附带任何游戏素材。
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile
import zlib

import numpy as np
from PIL import Image, ImageFilter

W, H, NT = 5632, 2048, 13414
SEA_LEVEL = 89
NO = 65535


# ---------------------------------------------------------------- 边界修正

def load_fixes(path):
    """读取 fixes.json；没有就返回空表。"""
    if not path or not os.path.exists(path):
        return {"states": [], "province_state": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("states", [])
    data.setdefault("province_state", [])
    return data


def apply_fixes(tm, titles, fixes):
    """按配置调整州界与归属，便于把某些地区单列成州或并入别的州。"""
    keys = titles["keys"]
    chi = keys.index("1936_CHI") if "1936_CHI" in keys else -1
    chi39 = keys.index("1939_CHI") if "1939_CHI" in keys else -1

    for item in fixes["states"]:
        name = item["name"]
        provs = item["provinces"]
        tid = len(keys)
        keys.append("#fix_" + name)
        for field, value in (
            ("tiers", 4), ("parents", -1), ("names", name), ("namesEn", name),
            ("locKeys", ""), ("colors", item.get("color", [122, 96, 64])),
            ("provCount", len(provs)), ("area", 0), ("blockArea", 0),
            ("lx", item.get("x", 0.0)), ("ly", item.get("y", 0.0)),
            ("gx", item.get("x", 0.0)), ("gy", item.get("y", 0.0)),
        ):
            titles[field].append(value)
        for p in provs:
            tm[4][p] = tid
            if chi >= 0:
                tm[0][p] = chi
            if chi39 >= 0:
                tm[1][p] = chi39
        print("单列成州:", name, provs, "-> 州号", tid)

    for item in fixes["province_state"]:
        pid = item["province"]
        sname = item["state"]
        sid = next((i for i, n in enumerate(titles["names"])
                    if n == sname and titles["tiers"][i] == 4), -1)
        if sid < 0:
            print("  !! 找不到州:", sname)
            continue
        donor = next((q for q in range(1, len(tm[4])) if tm[4][q] == sid), -1)
        if donor < 0:
            continue
        for tier in (0, 1, 3, 4):
            tm[tier][pid] = tm[tier][donor]
        print("并入已有的州: 省", pid, "->", sname)
    return titles


# ---------------------------------------------------------------- 地形烘焙

def hillshade(hm, land):
    dzdx = (np.roll(hm, -1, 1) - np.roll(hm, 1, 1)) * 0.5
    dzdy = (np.roll(hm, -1, 0) - np.roll(hm, 1, 0)) * 0.5
    s = 2.2
    nx, ny, nz = -dzdx * s, -dzdy * s, np.ones_like(hm)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    d = (nx * inv) * -0.55 + (ny * inv) * -0.55 + (nz * inv) * 0.63
    return (0.72 + 0.55 * np.clip(d, 0, 1) ** 0.9).astype(np.float32)


def land_layer(hm):
    e = np.clip((hm - (SEA_LEVEL + 6)) / 55.0, 0, 1)[..., None]
    stops = [(0.00, (104, 126, 84)),
             (0.35, (134, 143, 99)),
             (0.65, (163, 155, 125)),
             (1.00, (188, 184, 172))]
    out = np.zeros((H, W, 3), np.float32)
    for i in range(len(stops) - 1):
        a, ca = stops[i]
        b, cb = stops[i + 1]
        m = (e[..., 0] >= a) & (e[..., 0] <= b)
        f = np.clip((e[..., 0] - a) / (b - a), 0, 1)[..., None]
        out[m] = np.array(ca, np.float32) * (1 - f[m]) + np.array(cb, np.float32) * f[m]
    return out


# ---------------------------------------------------------------- 城市

def build_cities(states_dir, meta):
    """从州文件里抽胜利点，得到 [省号, 点数]；首都来自 meta.capitals。"""
    vp = {}
    if os.path.isdir(states_dir):
        for fn in os.listdir(states_dir):
            if not fn.endswith(".txt"):
                continue
            try:
                s = open(os.path.join(states_dir, fn), encoding="utf-8-sig", errors="ignore").read()
            except OSError:
                continue
            for m in re.finditer(r"victory_points\s*=\s*\{([^}]*)\}", s):
                nums = m.group(1).split()
                for i in range(0, len(nums) - 1, 2):
                    try:
                        p, v = int(nums[i]), int(nums[i + 1])
                    except ValueError:
                        continue
                    if 0 < p < NT:
                        vp[p] = max(vp.get(p, 0), v)
    caps = sorted({int(p) for p in (meta.get("capitals") or {}).values() if 0 < int(p) < NT})
    return {"cities": sorted([[p, v] for p, v in vp.items()], key=lambda r: -r[1]),
            "capitals": caps}


def main():
    ap = argparse.ArgumentParser(description="生成 .pdxmap 数据包")
    ap.add_argument("--hoi4", required=True, help="HOI4 安装目录")
    ap.add_argument("--src", required=True, help="输入 .pdxmap")
    ap.add_argument("--out", default="world-1936.pdxmap", help="输出路径")
    ap.add_argument("--fixes", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixes.json"),
                    help="边界修正配置")
    args = ap.parse_args()

    map_dir = os.path.join(args.hoi4, "map")
    states_dir = os.path.join(args.hoi4, "history", "states")
    for p in (map_dir, states_dir):
        if not os.path.isdir(p):
            sys.exit("找不到目录：%s（--hoi4 指到游戏根目录）" % p)

    z = zipfile.ZipFile(args.src)
    prov = np.frombuffer(zlib.decompress(z.read("provinces_id.bin")), dtype="<u2").reshape(H, W)
    tm = np.frombuffer(zlib.decompress(z.read("titlemap.bin")), dtype="<u2").reshape(6, NT).copy()
    titles = json.loads(z.read("titles.json").decode("utf-8"))
    meta = json.loads(z.read("meta.json").decode("utf-8"))

    hm = np.array(Image.open(os.path.join(map_dir, "heightmap.bmp")), dtype=np.float32)
    water_px = (tm[2] != NO)[prov]
    land_px = ~water_px

    # 海：近岸浅、远海深（heightmap 没有海深，用离岸距离近似）
    m = Image.fromarray((land_px * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(22))
    sh = (np.array(m, dtype=np.float32) / 255.0)[..., None]
    sea = np.array([32, 55, 86], np.float32) * (1 - sh) + np.array([74, 106, 136], np.float32) * sh

    land = land_layer(hm) * hillshade(hm, land_px)[..., None]
    terr = np.clip(np.where(water_px[..., None], sea, land), 0, 255).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(terr).save(buf, "JPEG", quality=88, optimize=True, subsampling=1)
    jpg = buf.getvalue()
    print("terrain.jpg %d KB" % (len(jpg) // 1024))

    titles = apply_fixes(tm, titles, load_fixes(args.fixes))
    tm_bin = zlib.compress(tm.tobytes(), 9)

    manifest = {
        "format": "pdxmap", "formatVersion": 3, "dataSchema": 1,
        "id": "hoi4-vanilla-1936", "game": "hoi4",
        "label": "HOI4 原版", "note": "5632 x 2048",
        "version": meta.get("gameVersion", ""),
        "mapWidth": W, "mapHeight": H, "numProvinces": NT,
        "tiers": meta["tiers"], "waterTier": 2,
        "terrain": "terrain.jpg", "cities": "cities.json",
        "dataVersion": 2,
        "stats": {"numProvinces": NT, "numTitles": len(titles["keys"])},
    }

    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        out.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        out.writestr("meta.json", z.read("meta.json"))
        out.writestr("titles.json", json.dumps(titles, ensure_ascii=False, separators=(",", ":")))
        # 这两份已经是 zlib 流，再压一次没意义，直接存储
        out.writestr("provinces_id.bin", z.read("provinces_id.bin"), compress_type=zipfile.ZIP_STORED)
        out.writestr("titlemap.bin", tm_bin, compress_type=zipfile.ZIP_STORED)
        out.writestr("terrain.jpg", jpg, compress_type=zipfile.ZIP_STORED)
        cities = build_cities(states_dir, meta)
        out.writestr("cities.json", json.dumps(cities, ensure_ascii=False, separators=(",", ":")))
        print("cities %d / capitals %d" % (len(cities["cities"]), len(cities["capitals"])))

    print("写出 %s（%d KB）" % (args.out, os.path.getsize(args.out) // 1024))


if __name__ == "__main__":
    main()
