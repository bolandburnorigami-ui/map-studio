# -*- coding: utf-8 -*-
"""把 editor.html + 一个或多个 .pdxmap 打成自包含 HTML。

用法：
    python build_single.py                                   # 默认 world-1936.pdxmap
    python build_single.py --pack a.pdxmap --pack b.pdxmap --out 合集.html
    python build_single.py --pack twr.pdxmap --out 千周之国.html
"""
import argparse
import base64
import json
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser(description="打包单文件版")
ap.add_argument("--pack", action="append", default=None, help="数据包路径，可重复")
ap.add_argument("--out", default="地图工坊.html", help="输出 HTML")
args = ap.parse_args()

packs = args.pack or ["world-1936.pdxmap"]
SRC_HTML = os.path.join(HERE, "editor.html")
OUT = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)

html = open(SRC_HTML, encoding="utf-8").read()

scripts = []
metas = []
for idx, rel in enumerate(packs):
    path = rel if os.path.isabs(rel) else os.path.join(HERE, rel)
    raw = open(path, "rb").read()
    try:
        with zipfile.ZipFile(path) as z:
            mf = json.loads(z.read("manifest.json").decode("utf-8"))
            tj = json.loads(z.read("titles.json").decode("utf-8"))
            nstate = sum(1 for t in tj["tiers"] if t == 4)
    except Exception:
        mf, nstate = {}, 0
    b64 = base64.b64encode(raw).decode("ascii")
    label = mf.get("label") or os.path.splitext(os.path.basename(path))[0]
    scen = ""
    if mf.get("scenarios"):
        scen = mf["scenarios"][0].get("name", "")
    metas.append({"label": label, "scenario": scen,
                  "provinces": mf.get("numProvinces", 0), "states": nstate})
    scripts.append('<script class="embedded-pack" type="application/octet-stream" data-idx="%d">%s</script>'
                   % (idx, b64))
    print("包 %d：%s %d KB（%s，%d 省）" % (idx, os.path.basename(path), len(raw) // 1024,
                                        label, mf.get("numProvinces", 0)))

inject = ('<script id="embedded-meta" type="application/json">%s</script>\n'
          % json.dumps(metas, ensure_ascii=False)) + "\n".join(scripts) + "\n"

marker = '<script>\n"use strict";'
assert marker in html, "找不到主脚本入口"
html = html.replace(marker, inject + marker, 1)

boot = """
/* 内嵌数据包：单文件版直接载入；多个包时先选底图 */
(function () {
  const metaEl = document.getElementById("embedded-meta");
  const metas = metaEl ? JSON.parse(metaEl.textContent) : [];
  const nodes = Array.from(document.querySelectorAll("script.embedded-pack"));
  const list = nodes.map((el, i) => {
    const bin = atob(el.textContent.trim());
    const u8 = new Uint8Array(bin.length);
    for (let k = 0; k < bin.length; k++) u8[k] = bin.charCodeAt(k);
    const m = metas[i] || {};
    return {label: m.label, meta: m, bytes: u8.buffer};
  }).filter(x => x.bytes);
  if (!list.length) return;
  const qs2 = new URLSearchParams(location.search);
  if (qs2.has("pack")) return;

  const go = item => loadPack({arrayBuffer: () => Promise.resolve(item.bytes)}).catch(e => {
    const el = document.getElementById("packName");
    if (el) el.textContent = "载入失败：" + e.message;
  });

  const pk = qs2.get("pk");
  if (pk != null) { go(list[Math.min(list.length - 1, Math.max(0, +pk || 0))]); return; }
  if (list.length === 1) {
    go(list[0]);
  } else {
    showPackChooser(list.map(x => ({label: x.label, meta: x.meta, bytes: x.bytes})));
  }
})();
"""
html = html.replace("/* ---------- 启动 ---------- */", boot + "\n/* ---------- 启动 ---------- */", 1)

open(OUT, "w", encoding="utf-8").write(html)
print("写出 %s %d KB" % (os.path.basename(OUT), os.path.getsize(OUT) // 1024))
