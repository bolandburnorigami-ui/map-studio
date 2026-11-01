# -*- coding: utf-8 -*-
"""打发布包：去掉开发钩子、做脱敏检查、内嵌地图数据，输出到 dist/。

用法：python build_release.py
产物：
  dist/map-studio.html     —— 双击即用的单文件
  dist/使用说明.txt
  dist/数据来源与声明.txt
"""
import base64, os, re, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_HTML = os.path.join(HERE, "editor.html")
SRC_PACK = os.path.join(HERE, "world-1936.pdxmap")
DIST = os.path.join(HERE, "dist")
VERSION = "1.44"

# 发布版里不该出现的东西（在本机路径、账号名、内网地址）
FORBIDDEN = [
    r"C:\\Users\\",
    r"AppData",
    r"SteamLibrary",
    r"127\.0\.0\.1",
    r"localhost",
    r"file:///",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
]

README = """地图工坊 v{ver}
==============================

这是什么
  一个离线的地图编辑器：以钢铁雄心 4 的原版世界地图为底图，
  按省份 / 州 / 战略区给国家、阵营、势力范围上色，最后导出成图片。

怎么用
  1. 双击「地图工坊.html」，用 Microsoft Edge 或 Chrome 打开
     （不要用微信、QQ、搜狗等内置浏览器，它们的内核太旧，会白屏）
     首次打开会弹一个「注意与声明」，勾选「不再提示」后不再出现；
     之后想再看，点左下角的「声明」链接
  2. 左边三个页签：
       国家 —— 选一个国家和颜色，在地图上涂抹
       阵营 —— 新建阵营，再回「国家」页给国家选所属阵营
       范围 —— 新建势力范围，选中后直接涂（可以跨国、跨州）
  3. 顶部「笔刷粒度」决定一次涂多大：省份 / 州 / 战略区
  4. 「导出 PNG」出图：可选标题、国名、城市、阵营与范围、1× 或 2× 分辨率
  5. 工具栏的「吸管」：点一下它，再点地图上的任意省份，
     就直接选中那个省所属的国家（在「范围」页签里则是拾取那一块范围）
  6. 列表上方的搜索框：输入名字片段就能过滤，回车无关，Esc 清空

快捷键
  滚轮            缩放
  右键拖动        平移
  Alt + 左键      吸色（等价于「吸管」按钮）
  Ctrl + Z        撤销（Shift+Ctrl+Z 重做）
  1 / 2 / 3       切换笔刷粒度
  双击空白处      复位视图（或用「复位」按钮）

外观
  主题      原版 / 低饱和 / 羊皮卷 / 夜间（TNO）/ 早期 Windows
            整套界面跟着换：面板配色、按钮样式、字体、海面颜色，
            连国界线颜色、城市与首都的标注样式也一起换
  省界      滑杆调浓淡，拉到最左就是纯色块
  地形      滑杆调地形明暗，拉到最左是平涂
  显示州界  勾上会在国家内部画出州的边界
  国名 / 城市 / 首都   三个开关，决定地图上要显示哪些标注
  这些设置都会记住，也会一起写进出图的 PNG

存档
  · 每次改动 1 秒后自动暂存在浏览器里，关掉再打开会接上次
  · 「保存」导出 .json 存档，可以备份或发给别人
  · 「读取」载入 .json 存档
  · 「清空」恢复到 1936 年原图

数据
  底图：钢铁雄心 4 原版（1.19.3.0）的省份图与地名
  地形：由原版高程图烘焙
  边界：藏南划归中国并单列成州；5042 号省划入和阗
  城市：1442 个胜利点城市 + 全部有名字的陆地省份，共 1492 个

已知限制
  · 目前不能改州界（州是数据里定好的），只能改归属
  · 地图分辨率固定 5632×2048，2× 导出为 11264×4096
  · 浏览器端渲染，集显笔记本放大到 300% 以上可能略卡
"""

NOTICE = """数据来源与使用声明
==============================

本工具内含的地图数据来自《Hearts of Iron IV》原版游戏文件
（版本 1.19.3.0），包括：

  · 省份图（provinces.bmp 转换成的省份编号索引）
  · 省份 / 州 / 战略区名称与层级关系
  · 国家名称与颜色
  · 由原版 heightmap.bmp 烘焙出的地形底图
  · 由州文件里的 victory_points 提取的城市位置

这些素材的版权归 Paradox Interactive 所有。
本工具仅用于个人学习、地图创作与同好交流，请勿用于商业用途，
也不要将其中的地图素材单独提取后二次分发。

地图上对藏南、阿克赛钦（5042 号省）的归属处理，
是按使用者要求做的自定义修改，不代表游戏原版设定，
也不代表对现实国际边界的主张。

工具本身的代码由 DeepSeek Harness 协助编写，随包自由使用。
"""


def strip_dev(html):
    a = html.find("/* ==DEV-START== */")
    b = html.find("/* ==DEV-END== */")
    if a < 0 or b < 0:
        raise SystemExit("找不到开发块标记，先检查 editor.html")
    return html[:a] + html[b + len("/* ==DEV-END== */"):]


def check_sensitive(html):
    """在把 base64 塞进去之前检查源码，避免误报。"""
    bad = []
    for pat in FORBIDDEN:
        for m in re.finditer(pat, html):
            bad.append((pat, m.group(0)))
    if bad:
        for pat, hit in bad[:10]:
            print("  !! 命中敏感串 %s -> %s" % (pat, hit))
        raise SystemExit("发布包里有敏感信息，已中止")
    print("脱敏检查: 通过（无本机路径 / 账号 / 内网地址 / 邮箱）")


def main():
    html = open(SRC_HTML, encoding="utf-8").read()
    pack = open(SRC_PACK, "rb").read()

    html = strip_dev(html)
    check_sensitive(html)

    b64 = base64.b64encode(pack).decode("ascii")
    inject = '<script id="embedded-pack" type="application/octet-stream">%s</script>\n' % b64
    marker = '<script>\n"use strict";'
    assert marker in html
    html = html.replace(marker, inject + marker, 1)

    boot = """
/* 内嵌数据包：单文件版直接载入 */
(function () {
  const el = document.getElementById("embedded-pack");
  if (!el) return;
  const s = el.textContent.trim();
  if (!s) return;
  const bin = atob(s);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  if (!new URLSearchParams(location.search).has("pack")) {
    loadPack({arrayBuffer: () => Promise.resolve(u8.buffer)}).catch(e => {
      document.getElementById("packName").textContent = "载入失败：" + e.message;
    });
  }
})();
"""
    html = html.replace("/* ---------- 启动 ---------- */", boot + "\n/* ---------- 启动 ---------- */", 1)
    html = html.replace("<title>地图工坊</title>", "<title>地图工坊 v%s</title>" % VERSION)

    os.makedirs(DIST, exist_ok=True)
    out_html = os.path.join(DIST, "map-studio.html")
    open(out_html, "w", encoding="utf-8").write(html)
    open(os.path.join(DIST, "使用说明.txt"), "w", encoding="utf-8-sig").write(README.format(ver=VERSION))
    open(os.path.join(DIST, "数据来源与声明.txt"), "w", encoding="utf-8-sig").write(NOTICE)

    zp = os.path.join(DIST, "map-studio-v%s.zip" % VERSION)
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for fn in (os.path.basename(out_html), "使用说明.txt", "数据来源与声明.txt"):
            z.write(os.path.join(DIST, fn), fn)

    print("发布包:")
    for fn in sorted(os.listdir(DIST)):
        p = os.path.join(DIST, fn)
        print("  %-28s %6d KB" % (fn, os.path.getsize(p) // 1024))


if __name__ == "__main__":
    main()
