# 地图工坊（Map Studio）

一个离线的网页地图编辑器：以《Hearts of Iron IV》的世界地图为底图，**按省份 / 州 / 战略区给国家、阵营、势力范围涂色**，最后导出成一张大图。

单文件、零依赖、不联网：双击 HTML 就能用。

> ⚠️ 本仓库**不包含任何游戏素材**。你必须自己拥有正版《Hearts of Iron IV》，并按下面的步骤在本地生成底图数据。

---

## 功能

**开始页**

- 启动时选剧本：1936 / 1939 / 空白底图（无国家，从零画架空世界）
- 空白底图保留地形、省界与城市，只是没有任何国家归属
- 随时可以点左上角「剧本」重选（会清空当前编辑）

**涂色**

- 三档笔刷：省份 / 州 / 战略区，左键拖动连续涂
- 101 个 1936 年国家，可新建国家、改色、改名、迁都、删除
- 吸管（点地图取色 / 取国家）、橡皮、撤销重做（120 步）

**标注**

- 国名：按国家实际大小自动排布，避开首都星标，放不下就缩小或省略
- 城市与首都：1492 个有名字的城镇，首都用五角星，缩得再小也保留
- 字号可调（55%–175%），三个标注可单独开关

**阵营与势力范围**

- 阵营：整个国家归属于某个阵营
- **切到「阵营」页签时，地图切成阵营地图模式**（像游戏里的地图模式那样整张重新上色）：
  每个阵营一块颜色、未入阵营的国家统一灰色、阵营之间画粗分界线，阵营内部只留细国界
- 势力范围：独立图层，可以跨国、跨州地涂，半透明色块叠加

**外观**

- 五套主题：原版 / 低饱和 / 羊皮卷 / 夜间（TNO 风）/ 早期 Windows
- 主题会一并改变面板配色、按钮样式、字体、滚动条、国界颜色、海面颜色、城市与首都的标注样式
- 省界浓度、地形强度、国界粗细（1×–4×）可调，州界可开关

**存档**

- 自动暂存在浏览器（关掉再开接上次）
- 可导出 / 导入 `.json` 存档
- 导出 PNG：可选标题、图例、1×（5632×2048）或 2×（11264×4096）

---

## 自己构建

### 依赖

- Windows + Python 3.10 以上，`numpy`、`Pillow`
- 正版《Hearts of Iron IV》（本文用 1.19.3.0 验证）
- 一个原始的 `.pdxmap` 底图包（由配套的「悖论制图」工具从游戏导出，含 `provinces_id.bin` / `titlemap.bin` / `titles.json` / `meta.json`）

### 三步

```bat
:: 1. 生成数据包（把 --hoi4 换成你自己的游戏目录）
python build_pack.py --hoi4 "D:/Steam/steamapps/common/Hearts of Iron IV" --src pdx-hoi4-vanilla.pdxmap --out world-1936.pdxmap

:: 2. 内嵌成单文件
python build_single.py

:: 3. 打开
start map-studio.html
```

`build_single.py` 会读同目录的 `editor.html` 和 `world-1936.pdxmap`，输出 `map-studio.html`。

想打包给别人：`python build_release.py`，会生成 `dist/`（含 HTML、使用说明、数据来源声明和 zip）。

### 边界修正

`fixes.json` 里可以配置两件事：

- `states`：把一批省份单列成一个新州（例如给某个地区单独建州）
- `province_state`：把某个省并进已有的州

不需要就清空两个数组，重新跑 `build_pack.py`。这些只是数据层修改，工具本身不预设任何政治立场。

---

## 文件结构

```
editor.html        编辑器本体（约 110 KB，HTML + CSS + JS 全在里面）
build_pack.py      生成 .pdxmap 数据包（读游戏 + 烘焙地形 + 抽城市）
build_single.py    把数据包内嵌进 HTML，产出单文件
build_release.py   出发布包：去调试钩子、脱敏检查、附说明
fixes.json         边界修正配置
docs/              文档
```

数据包格式见 [`docs/pdxmap-format.md`](docs/pdxmap-format.md)。

---

## 已知限制

- 不能直接改州界，只能改归属（配置在 `fixes.json`）
- 地图分辨率固定 5632×2048
- 浏览器端渲染，集显笔电放大到 300% 以上会略卡
- 只在 Microsoft Edge / Chrome 上验证过；微信、QQ、搜狗等内置浏览器内核太旧，会白屏

---

## 许可

代码以 MIT 协议开源，见 [LICENSE](LICENSE)。

游戏素材的版权归 Paradox Interactive，不在本协议范围内，也**不在本仓库中**。详见 [NOTICE.md](NOTICE.md)。

## 致谢

由 DeepSeek Harness 协助编写。
