# 🀄 majsoul-tiles

雀魂牌面本地识别 + 牌效分析工具。纯 Python，不依赖外部 API。

## 功能

- **本地牌面识别**：多尺度模板匹配 + dHash 特征，从截图中识别 34 种日麻牌面
- **牌效分析**：基于向听数 + 进张数计算，给出切牌建议
- **模板库管理**：从截图自动提取新牌面，增量扩充模板库

## 快速开始

```bash
# 识别 + 分析 + 建议（全流程）
python3 run.py screenshot.jpg

# 仅识别手牌
python3 local_match.py screenshot.jpg

# 牌效分析（从手牌标签）
python3 analyzer.py "355889m 345s E W NN"

# 从截图提取新牌面入库
python3 extract_tiles.py screenshot.jpg --save
```

## 文件结构

```
majsoul-tiles/
├── templates/           # 34 张牌面模板（PNG）
├── local_match.py       # 本地模板匹配识别
├── analyzer.py          # 牌效分析器（shanten + 进张）
├── run.py               # 全流程一条龙
├── extract_tiles.py     # 截图提取 + 模板库扩充
└── gen_templates.py     # 生成标准牌面模板（备用）
```

## 原理

1. Canny 边缘检测定位手牌区域
2. 裁剪后与模板库做多尺度模板匹配 + dHash 特征比对
3. 识别结果送入牌效分析器，计算向听数 + 最优切牌

## 许可证

MIT
