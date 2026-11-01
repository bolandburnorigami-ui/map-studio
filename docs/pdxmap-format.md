# .pdxmap 数据包格式

`.pdxmap` 就是一个 ZIP，里面装着一张「每像素属于哪个省」的索引图，以及配套的名字、颜色、城市等信息。编辑器只认这个格式，不直接读游戏文件。

## 目录

| 文件 | 压缩 | 内容 |
|---|---|---|
| `manifest.json` | deflate | 格式声明：尺寸、是否带地形、分层定义 |
| `meta.json` | deflate | 剧本、首都、国家标签配色（从游戏数据整理） |
| `titles.json` | deflate | 所有「头衔」的名字 / 颜色 / 层级 |
| `provinces_id.bin` | 原样（内层 zlib） | 每个像素的省份号 |
| `titlemap.bin` | 原样（内层 zlib） | 每个省的 6 档头衔号 |
| `terrain.jpg` | 原样 | 烘焙好的地形底图 |
| `cities.json` | deflate | 城市（胜利点）与首都省份 |

## manifest.json

```json
{
  "format": "pdxmap",
  "formatVersion": 3,
  "mapWidth": 5632,
  "mapHeight": 2048,
  "numProvinces": 13414,
  "tiers": ["1936", "1939", "blank", "sr", "st", "pr"],
  "waterTier": 2,
  "terrain": "terrain.jpg",
  "cities": "cities.json",
  "dataVersion": 2
}
```

`dataVersion` 一变，旧存档会被忽略（避免地图数据改了还用旧存档）。

## provinces_id.bin

zlib 压缩（不是 zip 的 deflate），解压后是 `mapWidth × mapHeight` 个小端 `uint16`，按行优先排列。

```
byte 0..1   = (0, 0) 这个像素的省份号
byte 2..3   = (1, 0)
...
```

`0` 号省是「无效区」，编辑器会画成深色底。

## titlemap.bin

同样是 zlib + `uint16`，但布局是**按档位分块**的：6 行 × `numProvinces` 列。

```
行 0 = 1936 剧本    行 3 = 战略区
行 1 = 1939 剧本    行 4 = 州
行 2 = 空白（水域）  行 5 = 省份
```

`65535` 表示「无」。第 2 行只在**水域**省份上有值，编辑器靠它一眼分出陆地和水。

## titles.json

一堆长度相同的平行数组，下标就是头衔号：

| 字段 | 含义 |
|---|---|
| `keys` | 唯一键，如 `1936_GER`、`#fix_藏南` |
| `tiers` | 所属层级（对应 titlemap 的行） |
| `parents` | 父级头衔号，`-1` 为无 |
| `names` / `namesEn` | 中文名 / 英文名 |
| `colors` | `[r, g, b]`，国家色或地图配色 |
| `provCount` / `area` / `blockArea` | 省份数、像素面积等（生成时算的） |
| `lx` / `ly` / `gx` / `gy` | 标注锚点 |

## cities.json

```json
{
  "cities": [[3838, 1], [11506, 50]],
  "capitals": [11506, 3838]
}
```

- `cities`：`[省份号, 胜利点]`，胜利点越高城市越大
- `capitals`：所有国家的首都省份

## terrain.jpg

一张和地图同尺寸的底图，已经烘焙好海面、高程色带和晕渲。浏览器只做混合，不做地形计算，所以加载很快。

## 自己造一个包

`build_pack.py` 需要两样东西：

1. `--hoi4`：游戏安装目录（读 `map/heightmap.bmp` 和 `history/states/`）
2. `--src`：一个含 `provinces_id.bin` / `titlemap.bin` / `titles.json` / `meta.json` 的原始包（由「悖论制图」导出）

然后它会重算地形、抽城市、按 `fixes.json` 调整州界，重新打包。

如果你想做架空地图，只要生成同样结构的包即可：一张自己的省份索引图、一张自己的地形图、一套自己的名字，工具本身不关心底下是不是现实世界。
