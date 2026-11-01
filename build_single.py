# -*- coding: utf-8 -*-
"""把 editor.html + 一个 .pdxmap 打成自包含的 HTML。

用法：
    python build_single.py                         # 默认用 world-1936.pdxmap
    python build_single.py --pack twr-1936.pdxmap --out 千周之国.html
"""
import argparse
import base64
import os

HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser(description="打包单文件版")
ap.add_argument("--pack", default="world-1936.pdxmap", help="数据包路径")
ap.add_argument("--out", default="地图工坊.html", help="输出 HTML")
args = ap.parse_args()

SRC_HTML = os.path.join(HERE, "editor.html")
SRC_PACK = args.pack if os.path.isabs(args.pack) else os.path.join(HERE, args.pack)
OUT = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)

html = open(SRC_HTML, encoding="utf-8").read()
pack = open(SRC_PACK, "rb").read()
b64 = base64.b64encode(pack).decode("ascii")
print("数据包 %s %d KB -> base64 %d KB" % (os.path.basename(SRC_PACK), len(pack) // 1024, len(b64) // 1024))

inject = '<script id="embedded-pack" type="application/octet-stream">%s</script>\n' % b64
marker = '<script>\n"use strict";'
assert marker in html, "找不到主脚本入口"
html = html.replace(marker, inject + marker, 1)

boot = """
/* 内嵌数据包：单文件版直接载入，不需要选文件 */
(function () {
  const el = document.getElementById("embedded-pack");
  if (!el) return;
  const s = el.textContent.trim();
  if (!s) return;
  const bin = atob(s);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  const qs2 = new URLSearchParams(location.search);
  if (!qs2.has("pack")) {
    loadPack({arrayBuffer: () => Promise.resolve(u8.buffer)}).catch(e => {
      document.getElementById("packName").textContent = "载入失败：" + e.message;
    });
  }
})();
"""
html = html.replace("/* ---------- 启动 ---------- */", boot + "\n/* ---------- 启动 ---------- */", 1)

open(OUT, "w", encoding="utf-8").write(html)
print("写出 %s %d KB" % (os.path.basename(OUT), os.path.getsize(OUT) // 1024))
