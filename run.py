#!/usr/bin/env python3
"""
识别+分析全流程：截图 → 牌面识别 → 牌效分析 → 切牌建议

用法:
  python3 run.py screenshot.jpg
"""

import cv2
import sys
from pathlib import Path
from local_match import LocalMatcher
from analyzer import hand_from_labels, analyze_hand, calc_shanten, int_to_tile

TEMPLATE_DIR = Path(__file__).parent / "templates"


def main():
    if len(sys.argv) < 2:
        print("用法: python3 run.py screenshot.jpg")
        return 1

    img_path = sys.argv[1]
    img = cv2.imread(img_path)
    if img is None:
        print(f"无法读取: {img_path}")
        return 1

    # 1. 识别手牌
    matcher = LocalMatcher(TEMPLATE_DIR)
    results = matcher.match_hand(img)

    print(f"模板库: {len(matcher.templates)}/34")
    print()

    # 手牌标签列表
    labels = [r["label"] for r in results if r["label"]]
    low_conf = [r for r in results if r["status"] == "low"]

    print("手牌识别:")
    for r in results:
        icon = {"high": "✓", "medium": "~", "low": "✗"}[r["status"]]
        print(f"  [{r['index']:2d}] {icon} {r['label']} ({r['score']:.0%})")

    if low_conf:
        print(f"\n⚠ 低置信度: {len(low_conf)} 张")
        for r in low_conf:
            cands = r.get("candidates", [])
            print(f"  [{r['index']}] 候选: {[(c[0], f'{c[1]:.0%}') for c in cands]}")

    # 2. 转换为整数编码
    hand = hand_from_labels(labels)
    if len(hand) < 5:
        print(f"\n❌ 识别到的牌太少 ({len(hand)}张)")
        return 1

    print(f"\n手牌: {' '.join(int_to_tile(t) for t in sorted(hand))}")
    print(f"牌数: {len(hand)}")

    # 3. 牌效分析
    shanten, parts = calc_shanten(hand)
    print(f"\n向听数: {shanten}  (面子:{parts.get('mentsu',0)} 搭子:{parts.get('tatsu',0)} 雀头:{'有' if parts.get('pair') else '无'})")
    print()

    analysis = analyze_hand(hand)

    print(f"{'牌':<4} {'打后':<6} {'进张':<5} {'枚数':<5} {'推荐'}")
    print("-" * 40)
    for i, r in enumerate(analysis[:8]):
        star = "★" if i == 0 else ""
        sh_str = str(r["shanten_after"])
        if r["shanten_after"] < shanten:
            sh_str += "↓"
        elif r["shanten_after"] > shanten:
            sh_str += "↑"
        print(f"{r['name']:<4} {sh_str:<6} {r['ukeire_types']:<5} {r['ukeire_count']:<5} {star}")

    if analysis:
        best = analysis[0]
        uke_names = [int_to_tile(t) for t in best["ukeire_tiles"]]
        print(f"\n推荐: 打 {best['name']}")
        print(f"进张: {len(uke_names)} 种 / {best['ukeire_count']} 枚")
        if uke_names:
            print(f"等牌: {', '.join(uke_names)}")

    # 4. 输出标注图
    annotated = matcher.annotate(img, results)
    out_path = Path(img_path).parent / f"result_{Path(img_path).name}"
    cv2.imwrite(str(out_path), annotated)
    print(f"\n标注图: {out_path}")

    return 0


if __name__ == "__main__":
    exit(main())
