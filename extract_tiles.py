#!/usr/bin/env python3
"""
雀魂牌面素材提取工具
从截图中提取手牌区域的牌面，与现有模板库比对去重，自动扩充模板库。

用法:
  python3 extract_tiles.py screenshot.jpg
  python3 extract_tiles.py screenshot.jpg --templates ./templates --save
"""

import cv2
import numpy as np
from pathlib import Path
import argparse
import hashlib
from collections import defaultdict

TEMPLATE_DIR = Path(__file__).parent / "templates"

# === 牌面检测 ===

def detect_hand_tiles(img: np.ndarray) -> list[tuple[int, int, int, int]]:
    """用 Canny 边缘检测 + 轮廓分析找到手牌区域，返回 [(x,y,w,h)]"""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    tiles = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        # 手牌竖立区域：画面下半部，标准牌面尺寸
        if y > h * 0.7 and 65 < cw < 120 and 110 < ch < 180:
            # 过滤掉明显的非牌区域（比如牌面形状太奇怪）
            ratio = cw / ch
            if 0.4 < ratio < 0.85:
                tiles.append((x, y, cw, ch))

    # 按 x 坐标排序，去重（同一张牌可能被检测多次）
    tiles.sort(key=lambda t: t[0])
    deduped = []
    for t in tiles:
        if not deduped or t[0] - deduped[-1][0] > 40:
            deduped.append(t)
    return deduped


# === 牌面特征 ===

def tile_hash(img: np.ndarray) -> np.ndarray:
    """计算牌面的组合特征（dHash + HSV直方图）"""
    # 统一尺寸
    img = cv2.resize(img, (94, 148))
    
    # dHash (64位)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (9, 8))
    dhash = (resized[:, 1:] > resized[:, :-1]).flatten().astype(np.float32)
    
    # HSV 颜色直方图 (64维)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [8, 8], [0, 180, 0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    
    return np.concatenate([dhash, hist])


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)


# === 模板匹配 ===

def load_templates(template_dir: Path) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """加载模板库，返回 {name: (image, feature)}"""
    templates = {}
    for f in sorted(template_dir.glob("template_??.png")):
        img = cv2.imread(str(f))
        if img is not None:
            feat = tile_hash(img)
            templates[f.stem] = (img, feat)
    return templates


def match_best_template(tile_img: np.ndarray, templates: dict) -> tuple[str | None, float]:
    """找到最匹配的模板，返回 (模板名, 相似度)"""
    feat = tile_hash(tile_img)
    best_name, best_sim = None, 0
    for name, (_, t_feat) in templates.items():
        sim = cosine_similarity(feat, t_feat)
        if sim > best_sim:
            best_sim = sim
            best_name = name
    return best_name, best_sim


# === 主流程 ===

def main():
    parser = argparse.ArgumentParser(description="雀魂牌面素材提取工具")
    parser.add_argument("screenshot", help="截图文件路径")
    parser.add_argument("--templates", default=str(TEMPLATE_DIR), help="模板目录")
    parser.add_argument("--save", action="store_true", help="自动保存新牌面到模板库")
    parser.add_argument("--threshold", type=float, default=0.85, help="去重相似度阈值")
    parser.add_argument("--annotate", action="store_true", help="输出标注后的截图")
    args = parser.parse_args()

    template_dir = Path(args.templates)
    template_dir.mkdir(parents=True, exist_ok=True)

    img = cv2.imread(args.screenshot)
    if img is None:
        print(f"❌ 无法读取图片: {args.screenshot}")
        return 1

    # 检测手牌
    tiles = detect_hand_tiles(img)
    print(f"🔍 检测到 {len(tiles)} 张手牌")

    # 加载模板
    templates = load_templates(template_dir)
    print(f"📚 已有模板: {len(templates)} 个")

    # 匹配并识别
    results = []
    new_tiles = []
    annotated = img.copy()

    for i, (x, y, cw, ch) in enumerate(tiles):
        crop = img[y-3:y+ch+3, x-3:x+cw+3]
        if crop.size == 0:
            continue

        name, sim = match_best_template(crop, templates)

        if sim >= args.threshold and name:
            label = f"{name} ({sim:.0%})"
            color = (0, 255, 0)  # 绿色=已识别
        elif sim >= 0.65:
            label = f"疑似 {name} ({sim:.0%})"
            color = (0, 255, 255)  # 黄色=不确定
        else:
            label = "NEW!"
            color = (0, 0, 255)  # 红色=新牌面
            if args.save:
                new_tiles.append((crop, sim))

        results.append((x, y, cw, ch, name, sim))
        cv2.rectangle(annotated, (x-3, y-3), (x+cw+3, y+ch+3), color, 2)
        cv2.putText(annotated, label, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    # 打印结果
    print(f"\n{'序号':<4} {'x':<6} {'y':<6} {'宽':<4} {'高':<4} {'匹配':<15} {'相似度':<8}")
    print("-" * 55)
    for i, (x, y, cw, ch, name, sim) in enumerate(results):
        match_str = name if name else "未识别"
        print(f"{i:<4} {x:<6} {y:<6} {cw:<4} {ch:<4} {match_str:<15} {sim:.1%}")

    # 保存新牌面
    if new_tiles and args.save:
        existing_count = len(templates)
        for crop, sim in new_tiles:
            # 去重检查
            feat = tile_hash(crop)
            is_new = True
            for name, (_, t_feat) in templates.items():
                if cosine_similarity(feat, t_feat) > args.threshold:
                    is_new = False
                    break
            if is_new:
                new_id = existing_count + len(templates)
                fname = template_dir / f"template_{new_id:02d}.png"
                cv2.imwrite(str(fname), crop)
                templates[f"template_{new_id:02d}"] = (crop, feat)
                print(f"  ✅ 新增模板: {fname.name}")

        new_count = len(templates) - existing_count
        print(f"\n📈 模板库: {existing_count} → {len(templates)} (+{new_count})")
        print(f"   还需收集: {34 - len(templates)} 种牌面")

    # 保存标注图
    if args.annotate:
        out_path = Path(args.screenshot).parent / f"annotated_{Path(args.screenshot).name}"
        cv2.imwrite(str(out_path), annotated)
        print(f"📸 标注图: {out_path}")

    return 0


if __name__ == "__main__":
    exit(main())
