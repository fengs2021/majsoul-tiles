#!/usr/bin/env python3
"""
纯 Python 日本麻将牌效分析器 — 改良版
基于标准公式法 + DFS最优分解 + 七对/国士支持

用法:
  python3 analyzer.py "123m 456p 789s EE W"
  python3 analyzer.py --from-match match_result.json
"""

import sys
from itertools import combinations
from collections import Counter

# ============================================================
# 牌面编码 — 保持与原版兼容
# ============================================================

TILE_STR = {
    "m": ["一", "二", "三", "四", "五", "六", "七", "八", "九"],
    "p": ["一", "二", "三", "四", "五", "六", "七", "八", "九"],
    "s": ["一", "二", "三", "四", "五", "六", "七", "八", "九"],
    "z": ["東", "南", "西", "北", "白", "發", "中"],
}

TILE_MAP = {}
_chars = {1:"一",2:"二",3:"三",4:"四",5:"五",6:"六",7:"七",8:"八",9:"九"}
for _i in range(1, 10):
    TILE_MAP[f"{_chars[_i]}万"] = _i - 1
    TILE_MAP[f"{_chars[_i]}筒"] = 9 + _i - 1
    TILE_MAP[f"{_chars[_i]}索"] = 18 + _i - 1
for _i, _n in enumerate(["東","南","西","北","白","發","中"]):
    TILE_MAP[_n] = 27 + _i

def tile_to_int(name: str) -> int:
    return TILE_MAP.get(name, -1)

def int_to_tile(n: int) -> str:
    if n < 9:
        return f"{n+1}万"
    elif n < 18:
        return f"{n-8}筒"
    elif n < 27:
        return f"{n-17}索"
    else:
        return ["東","南","西","北","白","發","中"][n-27]

def parse_hand(hand_str: str) -> list[int]:
    """解析手牌字符串，如 '123m 456p EE W' → [0,1,2, 9,10,11, 27,27, 28]"""
    tiles = []
    for part in hand_str.strip().split():
        if not part:
            continue
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
                    tiles.append(31)
                elif c == "F":
                    tiles.append(32)
                elif c == "C":
                    tiles.append(33)
    return sorted(tiles)

def hand_from_labels(labels: list[str]) -> list[int]:
    return sorted([tile_to_int(n) for n in labels if tile_to_int(n) >= 0])

# ============================================================
# 核心引擎 — 向听数计算
# ============================================================

def calc_shanten(hand: list[int]) -> tuple[int, dict]:
    """
    计算向听数。
    返回: (向听数, 详细信息)
      向听数: -1=和了(14张), 0=听牌, 1=1向听 ...
      info: {'type': 'normal'|'chiitoi'|'kokushi', 'mentsu': int, 'tatsu': int, 'pair': bool}
    """
    counts = [0] * 34
    for t in hand:
        counts[t] += 1

    normal_s, normal_info = _normal_shanten(counts)
    chiitoi_s = _chiitoi_shanten(counts)
    kokushi_s, kokushi_info = _kokushi_shanten(counts)

    results = [
        (normal_s, "normal", normal_info),
        (chiitoi_s, "chiitoi", {"mentsu": 0, "tatsu": 0, "pair": False}),
        (kokushi_s, "kokushi", kokushi_info),
    ]
    results.sort(key=lambda x: x[0])
    best = results[0]
    return best[0], {"type": best[1], "mentsu": best[2].get("mentsu", 0),
                     "tatsu": best[2].get("tatsu", 0), "pair": best[2].get("pair", False)}


def _normal_shanten(counts: list[int]) -> tuple[int, dict]:
    """
    一般形向听数。
    公式: shanten = 8 - 2*complete - partial - has_pair
    """
    best_shanten = 8
    best_info = {"mentsu": 0, "tatsu": 0, "pair": False}

    for pair_tile in range(34):
        if counts[pair_tile] >= 2:
            c = counts.copy()
            c[pair_tile] -= 2
            complete, partial = _optimal_decomposition(c)
            s = 8 - 2 * complete - partial - 1
            if s < best_shanten:
                best_shanten = s
                best_info = {"mentsu": complete, "tatsu": partial, "pair": True}
        elif counts[pair_tile] == 1:
            c = counts.copy()
            c[pair_tile] -= 1
            complete, partial = _optimal_decomposition(c)
            s = 8 - 2 * complete - partial
            if s < best_shanten:
                best_shanten = s
                best_info = {"mentsu": complete, "tatsu": partial, "pair": False}

    return max(-1, best_shanten), best_info


def _enumerate_blocks(counts: list[int]) -> list[tuple[str, tuple, int]]:
    blocks = []
    for i in range(34):
        if counts[i] >= 3:
            blocks.append(("complete", (i, i, i), 2))
    for suit_start in (0, 9, 18):
        for i in range(suit_start, suit_start + 7):
            if counts[i] >= 1 and counts[i + 1] >= 1 and counts[i + 2] >= 1:
                blocks.append(("complete", (i, i + 1, i + 2), 2))
    for i in range(34):
        if counts[i] >= 2:
            blocks.append(("pair", (i, i), 1))
    for suit_start in (0, 9, 18):
        for i in range(suit_start, suit_start + 8):
            if i + 1 < suit_start + 9 and counts[i] >= 1 and counts[i + 1] >= 1:
                blocks.append(("ryanmen", (i, i + 1), 1))
            if i + 2 < suit_start + 9 and counts[i] >= 1 and counts[i + 2] >= 1:
                blocks.append(("kanchan", (i, i + 2), 1))
    return blocks


def _optimal_decomposition(counts: list[int]) -> tuple[int, int]:
    blocks = _enumerate_blocks(counts)
    if not blocks:
        return (0, 0)

    best_complete = 0
    best_partial = 0
    best_total = 0

    def dfs(idx: int, complete: int, partial: int, used: set):
        nonlocal best_complete, best_partial, best_total
        total = 2 * complete + partial
        if total > best_total:
            best_total = total
            best_complete = complete
            best_partial = partial
        if idx >= len(blocks):
            return
        btype, tiles, _ = blocks[idx]
        can_use = all(t not in used for t in tiles)
        if can_use:
            new_used = used | set(tiles)
            if btype == "complete":
                dfs(idx + 1, complete + 1, partial, new_used)
            else:
                dfs(idx + 1, complete, partial + 1, new_used)
        dfs(idx + 1, complete, partial, used)

    dfs(0, 0, 0, set())
    return (best_complete, best_partial)


def _chiitoi_shanten(counts: list[int]) -> int:
    pairs = sum(c // 2 for c in counts)
    if pairs >= 7:
        return -1  # 和了
    return max(0, 6 - pairs)


def _kokushi_shanten(counts: list[int]) -> tuple[int, dict]:
    yaochu = [0, 8, 9, 17, 18, 26] + list(range(27, 34))
    has_pair = False
    missing = 0
    for t in yaochu:
        if counts[t] >= 2:
            has_pair = True
        elif counts[t] == 0:
            missing += 1
    shanten = missing if has_pair else missing + 1
    return shanten, {"mentsu": 0, "tatsu": 0, "pair": has_pair}


# ============================================================
# 进张计算
# ============================================================

def calc_ukeire(hand: list[int], discard: int,
                dora_indicators: list[int] = None) -> tuple[int, int, list[int]]:
    remaining = [t for t in hand if t != discard]
    after_s, _ = calc_shanten(remaining)

    visible = list(hand)
    if dora_indicators:
        visible.extend(dora_indicators)

    available = [4] * 34
    for t in visible:
        available[t] -= 1

    ukeire_tiles = []
    ukeire_count = 0

    for tile in range(34):
        if available[tile] <= 0:
            continue
        test_hand = remaining + [tile]
        new_s, _ = calc_shanten(test_hand)

        if after_s > 0:
            if new_s < after_s:
                ukeire_tiles.append(tile)
                ukeire_count += available[tile]
        else:
            if new_s <= -1:
                ukeire_tiles.append(tile)
                ukeire_count += available[tile]

    return len(ukeire_tiles), ukeire_count, ukeire_tiles


# ============================================================
# 手牌分析
# ============================================================

def analyze_hand(hand: list[int]) -> list[dict]:
    shanten, parts = calc_shanten(hand)
    results = []
    analyzed = set()

    for i, tile in enumerate(hand):
        if tile in analyzed:
            continue
        analyzed.add(tile)

        remaining = [hand[j] for j in range(len(hand)) if j != i]
        new_shanten, _ = calc_shanten(remaining)

        n_ukeire, total_ukeire, ukeire_list = calc_ukeire(hand, tile)

        results.append({
            "tile": tile,
            "name": int_to_tile(tile),
            "shanten_after": new_shanten,
            "ukeire_types": n_ukeire,
            "ukeire_count": total_ukeire,
            "ukeire_tiles": ukeire_list,
        })

    results.sort(key=lambda r: (
        r["shanten_after"] - shanten,
        -r["ukeire_count"],
        -r["ukeire_types"],
    ))
    return results


def print_analysis(hand: list[int]):
    shanten, parts = calc_shanten(hand)
    hand_type = parts.get("type", "normal")

    print(f"手牌: {' '.join(int_to_tile(t) for t in hand)}")
    type_str = {"normal": "一般形", "chiitoi": "七对子", "kokushi": "国士无双"}.get(hand_type, hand_type)
    print(f"向听数: {shanten} [{type_str}]  (面子:{parts.get('mentsu',0)} 搭子:{parts.get('tatsu',0)} 雀头:{'有' if parts.get('pair') else '无'})")
    print()

    results = analyze_hand(hand)
    print(f"{'牌':<4} {'打后向听':<8} {'进张种类':<8} {'进张枚数':<8} {'推荐'}")
    print("-" * 50)

    for i, r in enumerate(results[:8]):
        star = "★" if i == 0 else ""
        shanten_str = str(r["shanten_after"])
        if r["shanten_after"] < shanten:
            shanten_str += "↓"
        elif r["shanten_after"] > shanten:
            shanten_str += "↑"

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
        if best["ukeire_tiles"]:
            print(f"      进张牌: {', '.join(int_to_tile(t) for t in best['ukeire_tiles'][:12])}")


if __name__ == "__main__":
    test_hand_str = "355889m 345s E W NN"
    print(f"输入: {test_hand_str}")
    print()
    hand = parse_hand(test_hand_str)
    print_analysis(hand)

    print("\n" + "="*60 + "\n")

    test_labels = ["三万", "三万", "五万", "一筒", "三筒", "六筒", "七筒", "八筒", "四索", "五索", "六索", "六万"]
    print(f"输入: {' '.join(test_labels)}")
    print()
    hand2 = hand_from_labels(test_labels)
    print_analysis(hand2)
