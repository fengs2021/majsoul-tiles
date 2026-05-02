#!/usr/bin/env python3
"""
纯 Python 日本麻将牌效分析器
基于 shanten 数 + 进张数计算，无需 ML 模型

用法:
  python3 analyzer.py "123m 456p 789s EE W"         # 分析手牌
  python3 analyzer.py --from-match match_result.json  # 从识别结果分析
"""

import sys
from itertools import combinations, product
from collections import Counter

# 牌面编码: m=万 p=筒 s=索 z=字  (0-9 for m/p/s, 1-7 for 东南西北白发中)
TILE_STR = {
    "m": ["一", "二", "三", "四", "五", "六", "七", "八", "九"],
    "p": ["一", "二", "三", "四", "五", "六", "七", "八", "九"],
    "s": ["一", "二", "三", "四", "五", "六", "七", "八", "九"],
    "z": ["東", "南", "西", "北", "白", "發", "中"],
}

# 牌面 → 内部编码 (0-33)
# 中文牌名 → 整数编码
TILE_MAP = {}
_chars = {1:"一",2:"二",3:"三",4:"四",5:"五",6:"六",7:"七",8:"八",9:"九"}
for _i in range(1, 10):
    TILE_MAP[f"{_chars[_i]}万"] = _i - 1
    TILE_MAP[f"{_chars[_i]}筒"] = 9 + _i - 1
    TILE_MAP[f"{_chars[_i]}索"] = 18 + _i - 1
for _i, _n in enumerate(["東","南","西","北","白","發","中"]):
    TILE_MAP[_n] = 27 + _i

def tile_to_int(name: str) -> int:
    """牌名 → 0-33 整数编码"""
    return TILE_MAP.get(name, -1)

def int_to_tile(n: int) -> str:
    """0-33 → 牌名"""
    if n < 9:
        return f"{n+1}万"
    elif n < 18:
        return f"{n-8}筒"
    elif n < 27:
        return f"{n-17}索"
    else:
        return ["東","南","西","北","白","發","中"][n-27]

def parse_hand(hand_str: str) -> list[int]:
    """解析手牌字符串，如 "123m 456p EE W" → [0,1,2, 9,10,11, 27,27, 28]"""
    tiles = []
    for part in hand_str.strip().split():
        if not part:
            continue
        # 检查最后字符是否为花色
        if part[-1] in "mpsz":
            suit = part[-1]
            nums = part[:-1]
            offset = {"m": 0, "p": 9, "s": 18, "z": 27}[suit]
            for c in nums:
                if c.isdigit():
                    tiles.append(offset + int(c) - 1)
                elif c == "E":
                    tiles.append(27)
                elif c == "S":
                    tiles.append(28)
                elif c == "W":
                    tiles.append(29)
                elif c == "N":
                    tiles.append(30)
                elif c == "P":
                    tiles.append(31)  # 白
                elif c == "F":
                    tiles.append(32)  # 发
                elif c == "C":
                    tiles.append(33)  # 中
    return sorted(tiles)


def hand_from_labels(labels: list[str]) -> list[int]:
    """从牌名列表转换为整数编码"""
    return sorted([tile_to_int(n) for n in labels if tile_to_int(n) >= 0])


def calc_shanten(hand: list[int]) -> tuple[int, dict]:
    """
    计算向听数 (0=听牌, 1=1向听, ...)
    返回 (向听数, 详细信息)
    
    算法: 遍历所有可能的 4 面子 + 1 雀头 组合，找最小余牌数
    """
    counts = Counter(hand)
    if len(hand) not in [13, 14, 11, 10, 8, 7, 5, 4, 2, 1]:
        # 调整到标准大小计算
        pass
    
    # 标准方法：14张牌 → 4面子+1雀头 = 13张，余1张打出
    # 简化：对 13 张牌，找 4面子+1雀头 最优拆分
    total = len(hand)
    if total > 14:
        return 99, {"error": "手牌太多"}
    
    # 如果少于13张且有碰/吃，需要从面子上减
    # 这里只处理完整的13张手牌
    
    best_shanten = 99
    best_parts = {}
    
    # 尝试所有可能的雀头
    pair_candidates = [t for t, c in counts.items() if c >= 2]
    # 也考虑没有雀头的情况（单骑）
    pair_candidates.append(None)  # None = 无雀头
    
    for pair in pair_candidates:
        remaining = Counter(counts)
        
        if pair is not None:
            remaining[pair] -= 2
            if remaining[pair] == 0:
                del remaining[pair]
        
        # 贪心找面子（先刻子后顺子）
        mentsu, remaining2 = count_mentsu(remaining)
        
        # 再找搭子
        tatsu, _ = count_tatsu(remaining2)
        
        # 向听数 = 4 - 面子数 - min(搭子数, 4-面子数)
        mentsu_count = mentsu
        max_tatsu = min(tatsu, 4 - mentsu_count)
        shanten = 4 - mentsu_count - max_tatsu
        if pair is None:
            shanten += 1  # 没有雀头多1向听
        
        if shanten < best_shanten:
            best_shanten = shanten
            best_parts = {"mentsu": mentsu_count, "tatsu": max_tatsu, "pair": pair is not None}
    
    return best_shanten, best_parts


def count_mentsu(counts: Counter) -> tuple[int, Counter]:
    """贪心计算面子数（先刻子后顺子）"""
    remaining = Counter(counts)
    mentsu = 0
    
    # 先找刻子
    for t, c in list(remaining.items()):
        while remaining.get(t, 0) >= 3:
            remaining[t] -= 3
            if remaining[t] == 0:
                del remaining[t]
            mentsu += 1
    
    # 再找顺子（只对 m/p/s 花色）
    for suit_offset in [0, 9, 18]:
        for start in range(7):
            while (remaining.get(suit_offset + start, 0) >= 1 and
                   remaining.get(suit_offset + start + 1, 0) >= 1 and
                   remaining.get(suit_offset + start + 2, 0) >= 1):
                remaining[suit_offset + start] -= 1
                remaining[suit_offset + start + 1] -= 1
                remaining[suit_offset + start + 2] -= 1
                for k in [suit_offset + start, suit_offset + start + 1, suit_offset + start + 2]:
                    if remaining[k] == 0:
                        del remaining[k]
                mentsu += 1
    
    return mentsu, remaining


def count_tatsu(counts: Counter) -> tuple[int, Counter]:
    """计算搭子数"""
    remaining = Counter(counts)
    tatsu = 0
    
    # 对子（可作为雀头候补或搭子）
    pairs = [t for t, c in remaining.items() if c >= 2]
    tatsu += len(pairs)
    for t in pairs:
        remaining[t] -= 2
        if remaining[t] == 0:
            del remaining[t]
    
    # 两面搭子 / 嵌张 / 边张（按优先级：两面 > 嵌张 > 边张）
    for suit_offset in [0, 9, 18]:
        tiles_in_suit = sorted([t - suit_offset for t in remaining if suit_offset <= t < suit_offset + 9])
        
        # 找搭子
        i = 0
        while i < len(tiles_in_suit) - 1:
            a, b = tiles_in_suit[i], tiles_in_suit[i+1]
            if b - a <= 2:  # 边张/嵌张/两面
                # 消耗这两张
                remaining[suit_offset + a] -= 1
                remaining[suit_offset + b] -= 1
                for k in [suit_offset + a, suit_offset + b]:
                    if remaining[k] == 0:
                        del remaining[k]
                i = 0  # 重新开始找
                tatsu += 1
                tiles_in_suit = sorted([t - suit_offset for t in remaining if suit_offset <= t < suit_offset + 9])
            else:
                i += 1
    
    return tatsu, remaining


def calc_ukeire(hand: list[int], discard: int) -> tuple[int, int, list[int]]:
    """
    计算打掉 discard 后的进张数
    返回: (有效进张种类, 有效进张总枚数, 进张列表)
    """
    remaining = [t for t in hand if t != discard]  # 模拟打牌
    if len(remaining) != 13 - 1:
        # 补一张摸牌
        pass
    
    # 对于13张牌，打出1张后剩12张
    # 需要摸进1张才能听牌（1向听）或和牌（听牌）
    # 先判定当前状态：打完牌后12张，摸1张后13张
    
    # 简化：对1向听的手牌，计算听牌所需的进张
    # 对听牌的手牌，计算和牌所需的进张
    
    shanten_before, _ = calc_shanten(hand)
    shanten_after, _ = calc_shanten(remaining)
    
    # 摸进牌后的分析
    ukeire_tiles = []
    ukeire_count = 0
    
    for tile in range(34):
        # 模拟摸进 tile
        test_hand = remaining + [tile]
        test_shanten, _ = calc_shanten(test_hand)
        
        if test_shanten < shanten_after:
            # 这个摸牌能推进向听
            # 计算这枚牌还剩多少张
            used = hand.count(tile)
            available = 4 - used
            if available > 0:
                ukeire_tiles.append(tile)
                ukeire_count += available
    
    return len(ukeire_tiles), ukeire_count, ukeire_tiles


def analyze_hand(hand: list[int]) -> list[dict]:
    """
    分析手牌，给出每张牌的切牌建议
    返回: 排序后的切牌建议列表
    """
    shanten, parts = calc_shanten(hand)
    
    results = []
    analyzed = set()
    
    for i, tile in enumerate(hand):
        if tile in analyzed:
            continue
        analyzed.add(tile)
        
        # 计算打掉这张牌后的影响
        remaining = [hand[j] for j in range(len(hand)) if j != i]
        new_shanten, _ = calc_shanten(remaining)
        
        # 计算进张数
        n_ukeire, total_ukeire, ukeire_list = calc_ukeire(hand, tile)
        
        results.append({
            "tile": tile,
            "name": int_to_tile(tile),
            "shanten_after": new_shanten,
            "ukeire_types": n_ukeire,
            "ukeire_count": total_ukeire,
            "ukeire_tiles": ukeire_list,
        })
    
    # 排序：向听数小 > 进张多
    results.sort(key=lambda r: (r["shanten_after"], -r["ukeire_count"], -r["ukeire_types"]))
    
    return results


def print_analysis(hand: list[int]):
    """打印手牌分析结果"""
    shanten, parts = calc_shanten(hand)
    
    print(f"手牌: {' '.join(int_to_tile(t) for t in hand)}")
    print(f"向听数: {shanten}  (面子:{parts.get('mentsu',0)} 搭子:{parts.get('tatsu',0)} 雀头:{'有' if parts.get('pair') else '无'})")
    print()
    
    results = analyze_hand(hand)
    
    print(f"{'牌':<4} {'打后向听':<8} {'进张种类':<8} {'进张枚数':<8} {'推荐'}")
    print("-" * 50)
    
    for i, r in enumerate(results[:8]):  # 最多显示8张候选
        star = "★" if i == 0 else ""
        shanten_str = str(r["shanten_after"])
        if r["shanten_after"] < shanten:
            shanten_str += "↓"
        elif r["shanten_after"] > shanten:
            shanten_str += "↑"
        
        # 显示进张牌
        uke_names = [int_to_tile(t) for t in r["ukeire_tiles"][:8]]
        uke_str = ", ".join(uke_names)
        if len(r["ukeire_tiles"]) > 8:
            uke_str += f" +{len(r['ukeire_tiles'])-8}"
        
        print(f"{r['name']:<4} {shanten_str:<8} {r['ukeire_types']:<8} {r['ukeire_count']:<8} {star}")
        if i == 0:
            print(f"      进张: {uke_str}")
    
    print()
    if results:
        best = results[0]
        print(f"推荐: 打 {best['name']} (进张 {best['ukeire_types']} 种 / {best['ukeire_count']} 枚)")
        print(f"      进张牌: {', '.join(int_to_tile(t) for t in best['ukeire_tiles'])}")


if __name__ == "__main__":
    # 测试
    # 手牌示例: 355889m 345s E W NN
    test_hand_str = "355889m 345s E W NN"
    print(f"输入: {test_hand_str}")
    print()
    
    hand = parse_hand(test_hand_str)
    print_analysis(hand)
    
    print("\n" + "="*60 + "\n")
    
    # 也测试从截图识别结果
    test_labels = ["三万", "三万", "五万", "一筒", "三筒", "六筒", "七筒", "八筒", "四索", "五索", "六索", "六万"]
    print(f"输入: {' '.join(test_labels)}")
    print()
    hand2 = hand_from_labels(test_labels)
    print_analysis(hand2)
