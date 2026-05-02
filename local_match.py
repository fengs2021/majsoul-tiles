#!/usr/bin/env python3
"""
纯本地雀魂牌面识别：多尺度模板匹配 + dHash 特征 + 手动修正

用法:
  python3 local_match.py screenshot.jpg           # 识别+显示结果
  python3 local_match.py screenshot.jpg --json     # JSON 输出
  python3 local_match.py screenshot.jpg --annotate # 输出标注图
  python3 local_match.py --extract screenshot.jpg  # 从截图提取新牌面入库
"""

import cv2
import numpy as np
from pathlib import Path
from collections import defaultdict
import argparse
import json
import sys

TEMPLATE_DIR = Path(__file__).parent / "templates"


def detect_hand_tiles(img: np.ndarray) -> list[tuple[int,int,int,int]]:
    """Canny + 轮廓检测手牌区域"""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    tiles = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if y > h * 0.7 and 65 < cw < 130 and 110 < ch < 200:
            ratio = cw / ch
            if 0.4 < ratio < 0.85:
                tiles.append((x, y, cw, ch))

    tiles.sort(key=lambda t: t[0])
    deduped = []
    for t in tiles:
        if not deduped or t[0] - deduped[-1][0] > 35:
            deduped.append(t)
    return deduped


def dhash_feature(img: np.ndarray, size=(94, 148)) -> np.ndarray:
    """归一化差异哈希 + HSV直方图"""
    img = cv2.resize(img, (size[0] + 1, size[1]))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    dhash = (gray[:, 1:] > gray[:, :-1]).flatten().astype(np.float32)
    
    hsv = cv2.cvtColor(cv2.resize(img, size), cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [8, 8], [0, 180, 0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    
    return np.concatenate([dhash * 2.0, hist])  # dhash 加权


def template_match_score(crop: np.ndarray, template: np.ndarray) -> float:
    """多尺度模板匹配 + dHash 综合打分"""
    # 归一化尺寸
    t_h, t_w = template.shape[:2]
    c_h, c_w = crop.shape[:2]
    
    if max(t_h, t_w) == 0 or max(c_h, c_w) == 0:
        return 0.0

    # 尺寸自适应：crop resize 到接近 template 尺寸
    scale = t_h / c_h if c_h > 0 else 1.0
    new_w = int(c_w * scale)
    new_h = t_h
    if new_w > 5 and new_h > 5:
        crop_rs = cv2.resize(crop, (new_w, new_h))
    else:
        crop_rs = crop

    # TM_CCOEFF_NORMED 模板匹配
    if crop_rs.shape[0] < template.shape[0] or crop_rs.shape[1] < template.shape[1]:
        # crop 比 template 小，缩放 template 到 crop
        template_rs = cv2.resize(template, (crop_rs.shape[1], crop_rs.shape[0]))
        result = cv2.matchTemplate(crop_rs, template_rs, cv2.TM_CCOEFF_NORMED)
    else:
        result = cv2.matchTemplate(crop_rs, template, cv2.TM_CCOEFF_NORMED)
    tm_score = np.max(result)

    # dHash 特征相似度
    feat_crop = dhash_feature(crop_rs, (94, 148))
    feat_tmpl = dhash_feature(template, (94, 148))
    cosine = np.dot(feat_crop, feat_tmpl) / (
        np.linalg.norm(feat_crop) * np.linalg.norm(feat_tmpl) + 1e-8
    )

    # 综合打分（模板匹配权重 0.4，特征相似度权重 0.6）
    # 这样既关注像素级匹配也关注整体特征
    combined = 0.4 * max(0, tm_score) + 0.6 * cosine
    return combined


class LocalMatcher:
    def __init__(self, template_dir: Path = TEMPLATE_DIR):
        self.templates = {}
        self.labels = {}
        self.load_templates(template_dir)

    def load_templates(self, template_dir: Path):
        """加载模板库"""
        self.templates.clear()
        self.labels.clear()
        for f in sorted(template_dir.glob("*.png")):
            img = cv2.imread(str(f))
            if img is not None:
                label = f.stem
                self.templates[label] = img
                self.labels[label] = f

    def match(self, crop: np.ndarray) -> tuple[str | None, float, dict]:
        """
        匹配单张牌面
        返回: (最佳标签, 置信度, 所有候选的 {标签: 分数})
        """
        scores = {}
        for label, tmpl in self.templates.items():
            score = template_match_score(crop, tmpl)
            scores[label] = score

        # 排序
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        best_label, best_score = ranked[0]

        # 计算置信度指标
        gap = best_score - ranked[1][1] if len(ranked) > 1 else 0
        return best_label, best_score, {"top3": ranked[:3], "gap": gap}

    def match_hand(self, img: np.ndarray) -> list[dict]:
        """识别整手牌"""
        tiles = detect_hand_tiles(img)
        results = []
        for i, (x, y, cw, ch) in enumerate(tiles):
            crop = img[max(0, y-5):y+ch+5, max(0, x-5):x+cw+5]
            if crop.size == 0:
                results.append({"index": i, "x": x, "y": y, "label": None, "score": 0, "status": "empty"})
                continue

            label, score, detail = self.match(crop)
            gap = detail["gap"]
            top3 = detail["top3"]

            # 置信度判定
            if score > 0.78 and gap > 0.05:
                status = "high"
            elif score > 0.65:
                status = "medium"
            else:
                status = "low"

            results.append({
                "index": i, "x": x, "y": y, "width": cw, "height": ch,
                "label": label, "score": round(score, 3), "status": status,
                "gap": round(gap, 3),
                "candidates": [(l, round(s, 3)) for l, s in top3],
            })
        return results

    def annotate(self, img: np.ndarray, results: list[dict]) -> np.ndarray:
        """标注识别结果到图片上"""
        annotated = img.copy()
        colors = {"high": (0, 255, 0), "medium": (0, 255, 255), "low": (0, 0, 255), "empty": (128, 128, 128)}
        for r in results:
            color = colors.get(r["status"], (128, 128, 128))
            x, y, cw, ch = r["x"], r["y"], r["width"], r["height"]
            cv2.rectangle(annotated, (x-3, y-3), (x+cw+3, y+ch+3), color, 2)
            label = r["label"] or "?"
            score = r["score"]
            text = f"{label} {score:.0%}"
            cv2.putText(annotated, text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        return annotated

    def list_templates(self) -> list[str]:
        return sorted(self.templates.keys())


def main():
    parser = argparse.ArgumentParser(description="本地雀魂牌面识别")
    parser.add_argument("screenshot", nargs="?", help="截图路径")
    parser.add_argument("--templates", default=str(TEMPLATE_DIR), help="模板目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--annotate", action="store_true", help="输出标注图")
    parser.add_argument("--list", action="store_true", help="列出已有模板")
    parser.add_argument("--extract", action="store_true", help="从截图中提取新牌面")
    parser.add_argument("--label", help="手动标注模板名（配合 --extract 使用）")
    parser.add_argument("--threshold", type=float, default=0.65, help="低置信度阈值")
    args = parser.parse_args()

    matcher = LocalMatcher(Path(args.templates))

    if args.list:
        labels = matcher.list_templates()
        ALL_34 = ["一万","二万","三万","四万","五万","六万","七万","八万","九万",
            "一筒","二筒","三筒","四筒","五筒","六筒","七筒","八筒","九筒",
            "一索","二索","三索","四索","五索","六索","七索","八索","九索",
            "东","南","西","北","白","发","中"]
        missing = [t for t in ALL_34 if t not in labels]
        print(f"模板库: {len(labels)}/34")
        print(f"已有: {', '.join(labels)}")
        print(f"缺口: {', '.join(missing)}")
        return 0

    if not args.screenshot:
        parser.print_help()
        return 1

    img = cv2.imread(args.screenshot)
    if img is None:
        print(f"错误: 无法读取 {args.screenshot}")
        return 1

    if args.extract:
        # 提取模式：检测手牌->匹配现有模板->标记未知牌面
        tiles = detect_hand_tiles(img)
        print(f"检测到 {len(tiles)} 张手牌")
        new_count = 0
        for i, (x, y, cw, ch) in enumerate(tiles):
            crop = img[max(0,y-5):y+ch+5, max(0,x-5):x+cw+5]
            label, score, detail = matcher.match(crop)
            if score < 0.60:
                # 新牌面！保存
                fname = f"new_{i:02d}.png"
                cv2.imwrite(str(Path(args.templates) / fname), crop)
                print(f"  [{i}] 新牌面! (最佳: {label} {score:.0%}) -> {fname}")
                print(f"      请手动标注: python3 local_match.py --label {fname} 八索")
                new_count += 1
            else:
                print(f"  [{i}] {label} ({score:.0%}) ✓")
        if new_count == 0:
            print("没有新牌面")
        return 0

    # 识别模式
    results = matcher.match_hand(img)

    if args.json:
        output = {
            "hand_count": len(results),
            "tiles": results,
            "templates_available": len(matcher.templates),
            "low_confidence": [r for r in results if r["status"] == "low"],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for r in results:
            icon = {"high": "✓", "medium": "~", "low": "✗", "empty": "-"}[r["status"]]
            candidates = r.get("candidates", [])
            cand_str = ""
            if len(candidates) > 1 and candidates[1][1] > 0.4:
                cand_str = f" (次选: {candidates[1][0]} {candidates[1][1]:.0%})"
            print(f"  [{r['index']:2d}] {icon} {r['label'] or '?'} ({r['score']:.0%}){cand_str}")

        low = [r for r in results if r["status"] == "low"]
        if low:
            print(f"\n⚠ 低置信度牌: {len(low)} 张，建议手动检查")
            for r in low:
                print(f"  [{r['index']}] 候选: {r.get('candidates', [])}")

    if args.annotate:
        annotated = matcher.annotate(img, results)
        out_path = Path(args.screenshot).parent / f"match_{Path(args.screenshot).name}"
        cv2.imwrite(str(out_path), annotated)
        print(f"\n标注图: {out_path}")

    return 0


if __name__ == "__main__":
    exit(main())
