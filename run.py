#!/usr/bin/env python3
"""
识别+分析全流程：截图 → 牌面识别 → Akagi bot 分析 → 切牌建议

支持两种分析引擎:
  --local    本地 analyzer 引擎（默认，纯 Python）
  --remote   远程 Mortal API（需配置服务器地址和 API Key）

用法:
  python3 run.py screenshot.jpg
  python3 run.py screenshot.jpg --remote https://your-server:8080 --api-key KEY
  python3 run.py --hand "355889m 345s E W NN"    # 直接分析手牌字符串
"""

import os
import cv2
import sys
from pathlib import Path
from local_match import LocalMatcher
from akagi_bot import AkagiTilesBot, int_to_tile_name

TEMPLATE_DIR = Path(__file__).parent / "templates"


def analyze_from_hand_str(hand_str: str, bot: AkagiTilesBot):
    """从 mjai 手牌字符串分析"""
    from analyzer import parse_hand
    hand = parse_hand(hand_str)
    labels = [int_to_tile_name(t) for t in hand]
    result = bot.analyze(labels)
    _print_result(result, bot, labels)
    return 0


def analyze_from_screenshot(img_path: str, bot: AkagiTilesBot):
    """从截图识别 → bot 分析"""
    img = cv2.imread(img_path)
    if img is None:
        print(f"无法读取: {img_path}")
        return 1

    # 1. 识别手牌
    matcher = LocalMatcher(TEMPLATE_DIR)
    results = matcher.match_hand(img)

    print(f"模板库: {len(matcher.templates)}/34")
    print()

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

    if len(labels) < 5:
        print(f"\n❌ 识别到的牌太少 ({len(labels)}张)")
        return 1

    print(f"\n手牌: {' '.join(labels)}")

    # 2. Akagi Bot 分析
    result = bot.analyze(labels)
    _print_result(result, bot, labels)

    # 3. 标注图
    annotated = matcher.annotate(img, results)
    out_path = Path(img_path).parent / f"result_{Path(img_path).name}"
    cv2.imwrite(str(out_path), annotated)
    print(f"\n标注图: {out_path}")

    return 0


def _print_result(result: dict, bot: AkagiTilesBot, labels: list[str]):
    """打印分析结果"""
    if result.get("error"):
        print(f"\n❌ {result['error']}")
        return

    engine_name = "Mortal 远程" if bot.backend == "remote" else "Akagi Bot"
    shanten = result["shanten"]
    parts = result.get("shanten_detail", {})

    shanten_emoji = {0: "🎯", 1: "⏳", 2: "⏳", 3: "🔍"}.get(shanten, "🔍")
    shanten_str = "听牌！" if shanten == 0 else f"{shanten}向听"

    print(f"\n══ {engine_name} 分析 ══")
    print(f"向听数: {shanten_emoji} {shanten_str}")
    print(f"  面子×{parts.get('mentsu', '?')}  搭子×{parts.get('tatsu', '?')}  "
          f"雀头: {'有' if parts.get('pair') else '无'}")

    if not result["candidates"]:
        return

    print(f"\n{'牌':<6} {'打后':<6} {'进张种':<6} {'进张枚':<6} {'推荐'}")
    print("-" * 45)
    for c in result["candidates"][:8]:
        star = "★" if c["is_best"] else ""
        sh_str = str(c["shanten_after"])
        if c["shanten_after"] < shanten:
            sh_str += "↓"
        elif c["shanten_after"] > shanten:
            sh_str += "↑"
        print(f"{c['tile']:<6} {sh_str:<6} {c['ukeire_types']:<6} {c['ukeire_count']:<6} {star}")

    best = result["candidates"][0] if result["candidates"] else None
    if best:
        uke_names = best["ukeire_tiles"]
        print(f"\n推荐: 打 {best['tile']}")
        print(f"进张: {best['ukeire_types']} 种 / {best['ukeire_count']} 枚")
        if uke_names:
            print(f"等牌: {', '.join(uke_names[:15])}")

    # tooltip（适合 Android Termux 小屏）
    print(f"\n{result['tooltip']}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="majsoul-tiles + Akagi Bot 牌效分析")
    parser.add_argument("image", nargs="?", help="截图路径")
    parser.add_argument("--hand", type=str, help="手牌字符串 (如 '355889m 345s E W NN')")
    parser.add_argument("--remote", type=str, help="远程 Mortal 服务器地址")
    parser.add_argument("--api-key", type=str, help="远程 API Key")
    parser.add_argument("--local", action="store_true", default=True,
                        help="使用本地引擎（默认）")

    args = parser.parse_args()

    # 初始化 Bot
    backend = "remote" if args.remote else "local"
    bot = AkagiTilesBot(
        backend=backend,
        remote_server=args.remote,
        remote_api_key=args.api_key,
    )

    if args.hand:
        return analyze_from_hand_str(args.hand, bot)

    if not args.image:
        parser.print_help()
        return 1

    return analyze_from_screenshot(args.image, bot)


if __name__ == "__main__":
    exit(main())
