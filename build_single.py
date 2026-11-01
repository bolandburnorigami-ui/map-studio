# -*- coding: utf-8 -*-
"""把 editor.html + world-1936.pdxmap 打成一个自包含的 HTML。

产物：map-studio.html —— 双击即开，不联网、不选文件、离线可用。
"""
import base64, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_HTML = os.path.join(HERE, "editor.html")
SRC_PACK = os.path.join(HERE, "world-1936.pdxmap")
OUT = os.path.join(HERE, "map-studio.html")

html = open(SRC_HTML, encoding="utf-8").read()
pack = open(SRC_PACK, "rb").read()
b64 = base64.b64encode(pack).decode("ascii")
print("数据包 %d KB -> base64 %d KB" % (len(pack) // 1024, len(b64) // 1024))

inject = (
    '<script id="embedded-pack" type="application/octet-stream">%s</script>\n' % b64
)
# 放在主脚本之前
marker = '<script>\n"use strict";'
if marker not in html:
    marker = '<script>\n"use strict";'
assert marker in html, "找不到主脚本入口"
html = html.replace(marker, inject + marker, 1)

# 主脚本里补一段：有内嵌包就直接载入
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
print("写出", OUT, os.path.getsize(OUT) // 1024, "KB")
