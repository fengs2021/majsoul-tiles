# 🀄 majsoul-tiles

雀魂牌面本地识别 + AI 牌效分析工具。截图识别 + Akagi Bot 分析双引擎。

## 功能

- **本地牌面识别**：多尺度模板匹配 + dHash 特征，从截图中识别 34 种日麻牌面
- **Akagi Bot 牌效分析**：集成 mjai Bot 接口，向听数 + 进张数 + 和牌判定，给出最优切牌建议
- **远程 Mortal API**：可选接入远程 Mortal 服务器，使用神经网络模型分析
- **模板库管理**：从截图自动提取新牌面，增量扩充模板库

## 快速开始

```bash
# 截图识别 + Akagi Bot 分析（全流程）
python3 run.py screenshot.jpg

# 仅识别手牌
python3 local_match.py screenshot.jpg

# 直接分析手牌字符串
python3 run.py --hand "355889m 345s E W NN"

# 使用远程 Mortal API
python3 run.py screenshot.jpg --remote https://your-server:8080 --api-key KEY

# 从截图提取新牌面入库
python3 extract_tiles.py screenshot.jpg --save
```

## 文件结构

```
majsoul-tiles/
├── templates/           # 34 张牌面模板（PNG）
├── local_match.py       # 本地模板匹配识别
├── akagi_bot.py         # Akagi Bot 集成（mjai 接口 + 牌效引擎）
├── analyzer.py          # 基础牌效分析器（shanten + 进张）
├── run.py               # 全流程一条龙（识别 → Bot 分析 → 建议）
├── extract_tiles.py     # 截图提取 + 模板库扩充
└── gen_templates.py     # 生成标准牌面模板（备用）
```

## Akagi Bot 集成

`akagi_bot.py` 实现了与 [Akagi](https://github.com/shinkuan/Akagi) 的 `mjai_bot/` 兼容接口：

- **本地引擎**（默认）：纯 Python，无需 GPU，基于向听数 + 进张数计算
- **远程引擎**：调用 Mortal 神经网络 API，需要部署服务端
- **Bot 接口**：`bot.react(events_json)` / `bot.think()` 与 mjai 标准兼容

```python
from akagi_bot import AkagiTilesBot

bot = AkagiTilesBot()
result = bot.analyze(["三万","五万","五万","八万","八万","九万",
                       "三索","四索","五索","東","西","北","北"])
print(result["best_discard"])  # 八万
print(result["tooltip"])       # 简要建议（适合移动端展示）
```

## 原理

1. Canny 边缘检测定位手牌区域
2. 裁剪后与模板库做多尺度模板匹配 + dHash 特征比对
3. 识别结果送入 Akagi Bot → 向听数 + 进张数 + 和牌判定 → 最优切牌

## 许可证

MIT
