#!/usr/bin/env python3
"""
Akagi mjai_bot 集成 — 为 majsoul-tiles 提供 AI 牌效分析

架构参照 Akagi 的 mjai_bot/ 模式，实现 mjai Bot 兼容接口。
支持本地引擎（analyzer.py）和远程 Mortal 服务两种后端。

用法:
  from akagi_bot import AkagiTilesBot

  bot = AkagiTilesBot()
  result = bot.analyze(["三万","五万","五万","八万","八万","九万","三筒","四筒","五筒","東","西","北","北"])
  print(result["best_discard"])   # 推荐切牌
  print(result["reason"])         # 推荐理由
  print(result["candidates"])     # 所有候选项
"""

import json
import gzip
from typing import Optional
from collections import Counter

# --- 内部编码：0-33（与 mjai 的 vec34 编码一致） ---
#  0- 8: 1m-9m (万)
#  9-17: 1p-9p (筒)
# 18-26: 1s-9s (索)
# 27-33: 東南西北白發中

TILE_NAME_MAP: dict[int, str] = {}
_chars = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
          6: "六", 7: "七", 8: "八", 9: "九"}
for i in range(1, 10):
    TILE_NAME_MAP[i - 1] = f"{_chars[i]}万"
    TILE_NAME_MAP[8 + i] = f"{_chars[i]}筒"
    TILE_NAME_MAP[17 + i] = f"{_chars[i]}索"
for i, n in enumerate(["東", "南", "西", "北", "白", "發", "中"]):
    TILE_NAME_MAP[27 + i] = n

NAME_TO_INT: dict[str, int] = {v: k for k, v in TILE_NAME_MAP.items()}

# mjai 字符串 ↔ 整数
MJAI_TO_INT: dict[str, int] = {}
for i in range(1, 10):
    MJAI_TO_INT[f"{i}m"] = i - 1
    MJAI_TO_INT[f"{i}p"] = 8 + i
    MJAI_TO_INT[f"{i}s"] = 17 + i
MJAI_TO_INT.update({"E": 27, "S": 28, "W": 29, "N": 30, "P": 31, "F": 32, "C": 33})
# 赤牌
MJAI_TO_INT["0m"] = 4
MJAI_TO_INT["0p"] = 13
MJAI_TO_INT["0s"] = 22

INT_TO_MJAI: dict[int, str] = {v: k for k, v in MJAI_TO_INT.items() if not k.startswith("0")}
# 补充赤牌映射
INT_TO_MJAI[4] = "5mr"
INT_TO_MJAI[13] = "5pr"
INT_TO_MJAI[22] = "5sr"

# 宝牌推牌规则
DORA_NEXT: dict[int, int] = {}
for suit_base in [0, 9, 18]:
    for i in range(8):
        DORA_NEXT[suit_base + i] = suit_base + i + 1
    DORA_NEXT[suit_base + 8] = suit_base  # 9 → 1
# 字牌: 東→南→西→北→白→發→中→東
DORA_NEXT[27] = 28
DORA_NEXT[28] = 29
DORA_NEXT[29] = 30
DORA_NEXT[30] = 31
DORA_NEXT[31] = 32
DORA_NEXT[32] = 33
DORA_NEXT[33] = 27


def tile_name_to_int(name: str) -> int:
    """牌名 → 0-33"""
    return NAME_TO_INT.get(name, -1)


def tiles_to_ints(names: list[str]) -> list[int]:
    """牌名列表 → 整数列表"""
    return sorted([tile_name_to_int(n) for n in names if tile_name_to_int(n) >= 0])


def int_to_tile_name(n: int) -> str:
    """0-33 → 牌名"""
    return TILE_NAME_MAP.get(n, "?")


# ============================================================
# 牌效分析核心（从 analyzer.py 移植增强版）
# ============================================================

def calc_shanten(hand: list[int]) -> tuple[int, dict]:
    """
    计算向听数 (0=听牌, 1=1向听 ...)
    算法：遍历雀头 + 贪心面子拆分
    """
    counts = Counter(hand)
    best_shanten = 99
    best_parts = {}

    pair_candidates = [t for t, c in counts.items() if c >= 2]
    pair_candidates.append(None)

    for pair in pair_candidates:
        remaining = Counter(counts)
        if pair is not None:
            remaining[pair] -= 2
            if remaining[pair] <= 0:
                del remaining[pair]

        mentsu, remaining2 = _count_mentsu(remaining)
        tatsu, _ = _count_tatsu_greedy(remaining2)

        max_tatsu = min(tatsu, 4 - mentsu)
        shanten = 4 - mentsu - max_tatsu
        if pair is None:
            shanten += 1

        if shanten < best_shanten:
            best_shanten = shanten
            best_parts = {"mentsu": mentsu, "tatsu": max_tatsu, "pair": pair is not None}

    return best_shanten, best_parts


def _count_mentsu(counts: Counter) -> tuple[int, Counter]:
    """贪心面子计数：先刻子后顺子"""
    remaining = Counter(counts)
    mentsu = 0

    for t, c in list(remaining.items()):
        while remaining.get(t, 0) >= 3:
            remaining[t] -= 3
            if remaining[t] <= 0:
                del remaining[t]
            mentsu += 1

    for suit_offset in [0, 9, 18]:
        for start in range(7):
            while (remaining.get(suit_offset + start, 0) >= 1 and
                   remaining.get(suit_offset + start + 1, 0) >= 1 and
                   remaining.get(suit_offset + start + 2, 0) >= 1):
                for k in range(3):
                    remaining[suit_offset + start + k] -= 1
                    if remaining[suit_offset + start + k] <= 0:
                        del remaining[suit_offset + start + k]
                mentsu += 1

    return mentsu, remaining


def _count_tatsu_greedy(counts: Counter) -> tuple[int, Counter]:
    """搭子计数"""
    remaining = Counter(counts)
    tatsu = 0

    pairs = [t for t, c in remaining.items() if c >= 2]
    tatsu += len(pairs)
    for t in pairs:
        remaining[t] -= 2
        if remaining[t] <= 0:
            del remaining[t]

    for suit_offset in [0, 9, 18]:
        tiles_in_suit = sorted([t - suit_offset for t in remaining
                                if suit_offset <= t < suit_offset + 9])
        i = 0
        while i < len(tiles_in_suit) - 1:
            a, b = tiles_in_suit[i], tiles_in_suit[i + 1]
            if b - a <= 2:
                remaining[suit_offset + a] -= 1
                remaining[suit_offset + b] -= 1
                for k in [suit_offset + a, suit_offset + b]:
                    if remaining[k] <= 0:
                        del remaining[k]
                tatsu += 1
                tiles_in_suit = sorted([t - suit_offset for t in remaining
                                        if suit_offset <= t < suit_offset + 9])
                i = 0
            else:
                i += 1

    return tatsu, remaining


def calc_ukeire(hand: list[int], discard: int,
                 dora_indicators: list[int] = None) -> tuple[int, int, list[int]]:
    """
    计算打掉 discard 后的有效进张

    14张手牌 → 打出1张剩13张 → 模拟摸1张变14张
    - 听牌（shanten=0）时：找能完成和牌型的进张
    - 非听牌时：找能降低向听数的进张

    返回: (进张种类数, 进张总枚数, 进张牌列表)
    """
    remaining = list(hand)
    remaining.remove(discard)

    shanten_before = calc_shanten(hand)[0]
    shanten_after, _ = calc_shanten(remaining)

    ukeire_tiles = []
    ukeire_count = 0

    for tile in range(34):
        test_hand = remaining + [tile]
        test_shanten, _ = calc_shanten(test_hand)

        # 听牌时：找能让向听数降到 -1（即和牌）的牌
        # 非听牌时：找能降低向听数的牌
        if shanten_before == 0:
            # 听牌 → 判断是否和了（4面子+1雀头完整）
            if _is_agari(test_hand):
                used = hand.count(tile)
                available = 4 - used
                if available > 0:
                    ukeire_tiles.append(tile)
                    ukeire_count += available
        else:
            if test_shanten < shanten_after:
                used = hand.count(tile)
                available = 4 - used
                if available > 0:
                    ukeire_tiles.append(tile)
                    ukeire_count += available

    ukeire_tiles.sort(key=lambda t: (
        -(4 - hand.count(t)),
        t
    ))

    return len(ukeire_tiles), ukeire_count, ukeire_tiles


def _is_agari(hand: list[int]) -> bool:
    """
    判断 14 张手牌是否构成和牌型（4面子+1雀头）
    算法：遍历所有可能的雀头，然后检查剩余能否拆成 4 面子
    """
    if len(hand) % 3 != 2:
        return False
    counts = Counter(hand)

    for t, c in counts.items():
        if c >= 2:
            new_counts = Counter(counts)
            new_counts[t] -= 2
            if new_counts[t] <= 0:
                del new_counts[t]
            if _all_mentsu(new_counts, 4):
                return True

    return False


def _all_mentsu(counts: Counter, need: int) -> bool:
    """
    递归检查剩余牌能否拆成 need 个面子（标准雀头先拆法）
    每次取最小的牌，必须用它起头一个面子
    """
    if need == 0:
        return sum(counts.values()) == 0

    tiles = sorted(counts.keys())
    if not tiles:
        return False

    t = tiles[0]
    c = counts[t]

    # 尝试刻子
    if c >= 3:
        new_counts = Counter(counts)
        new_counts[t] -= 3
        if new_counts[t] <= 0:
            del new_counts[t]
        if _all_mentsu(new_counts, need - 1):
            return True

    # 尝试顺子（仅数牌且 t 为 1-7）
    if t < 27 and t % 9 <= 6:
        if (counts.get(t, 0) >= 1 and
            counts.get(t + 1, 0) >= 1 and
            counts.get(t + 2, 0) >= 1):
            new_counts = Counter(counts)
            for k in [t, t + 1, t + 2]:
                new_counts[k] -= 1
                if new_counts[k] <= 0:
                    del new_counts[k]
            if _all_mentsu(new_counts, need - 1):
                return True

    return False


# ============================================================
# 宝牌 / 役评估
# ============================================================

def calc_dora_count(hand: list[int], dora_indicators: list[int]) -> int:
    """计算手牌中的宝牌数量"""
    if not dora_indicators:
        return 0
    dora_tiles = set()
    for d in dora_indicators:
        dora_tiles.add(DORA_NEXT.get(d, -1))
    return sum(1 for t in hand if t in dora_tiles)


def calc_aka_count(hand: list[int]) -> int:
    """计算赤牌数量（5mr, 5pr, 5sr 在内部编码中与普通5相同，这里用 heuristic）"""
    # 赤牌在 mjai 内部编码中与普通牌相同，此处仅做占位
    return 0


# ============================================================
# AkagiTilesBot — mjai 兼容 bot 接口
# ============================================================

class AkagiTilesBot:
    """
    与 Akagi mjai_bot 接口兼容的牌效分析机器人。

    两种后端:
      - "local": 使用本地 analyzer 引擎（纯 Python，无需额外依赖）
      - "remote": 调用远程 Mortal API（需要服务器）
    """

    def __init__(self, backend: str = "local",
                 remote_server: str = None, remote_api_key: str = None):
        self.backend = backend
        self.remote_server = remote_server
        self.remote_api_key = remote_api_key

        # 内部状态（模拟 mjai.Bot 的属性）
        self.player_id: int = 0
        self.tehai: list[int] = []          # 0-33 整数编码
        self.tehai_mjai: list[str] = []     # mjai 字符串格式
        self.dora_indicators: list[int] = []
        self.bakaze: int = 27               # 默认东
        self.jikaze: int = 27
        self.is_oya: bool = False
        self.can_discard: bool = True

    # ---- 设置牌局状态 ----

    def set_hand(self, tehai_labels: list[str]):
        """设置手牌（中文牌名列表）"""
        self.tehai = tiles_to_ints(tehai_labels)
        self.tehai_mjai = [INT_TO_MJAI[t] for t in self.tehai]

    def set_dora(self, dora_labels: list[str]):
        """设置宝牌指示牌"""
        self.dora_indicators = tiles_to_ints(dora_labels)

    def set_wind(self, bakaze: str = "東", jikaze: str = "東", is_oya: bool = False):
        """设置场风/自风"""
        self.bakaze = tile_name_to_int(bakaze)
        self.jikaze = tile_name_to_int(jikaze)
        self.is_oya = is_oya

    # ---- 核心分析接口 ----

    def analyze(self, hand_labels: list[str] = None,
                dora_labels: list[str] = None) -> dict:
        """
        分析手牌，返回最佳切牌建议。

        参数:
          hand_labels: 中文牌名列表，如 ["三万","五万",...]
          dora_labels: 宝牌指示牌名列表（可选）

        返回:
          {
            "best_discard": str,      # 推荐切牌（中文牌名）
            "best_discard_mjai": str, # 推荐切牌（mjai 格式）
            "reason": str,            # 推荐理由
            "shanten": int,           # 当前向听数
            "candidates": [           # 所有候选项
              {
                "tile": str,
                "tile_mjai": str,
                "shanten_after": int,
                "ukeire_types": int,
                "ukeire_count": int,
                "ukeire_tiles": [str, ...],
                "is_best": bool,
              },
              ...
            ],
            "tooltip": str,           # 简要提示（适合界面展示）
          }
        """
        if hand_labels:
            self.set_hand(hand_labels)
        if dora_labels:
            self.set_dora(dora_labels)

        if not self.tehai or len(self.tehai) == 0:
            return {"error": "未设置手牌", "best_discard": None}

        if self.backend == "remote" and self.remote_server:
            return self._analyze_remote()
        else:
            return self._analyze_local()

    def _analyze_local(self) -> dict:
        """本地分析（使用 analyzer 引擎）"""
        shanten, parts = calc_shanten(self.tehai)

        candidates = []
        analyzed_tiles = set()

        for tile in sorted(set(self.tehai)):
            if tile in analyzed_tiles:
                continue
            analyzed_tiles.add(tile)

            remaining = list(self.tehai)
            remaining.remove(tile)
            new_shanten, _ = calc_shanten(remaining)

            n_ukeire, total_ukeire, ukeire_list = calc_ukeire(
                self.tehai, tile, self.dora_indicators
            )

            dora_count = calc_dora_count(self.tehai, self.dora_indicators)

            candidates.append({
                "tile": int_to_tile_name(tile),
                "tile_mjai": INT_TO_MJAI.get(tile, "?"),
                "shanten_after": new_shanten,
                "ukeire_types": n_ukeire,
                "ukeire_count": total_ukeire,
                "ukeire_tiles": [int_to_tile_name(t) for t in ukeire_list[:10]],
                "is_best": False,
            })

        # 排序：向听数低 > 进张种类多 > 进张枚数多
        candidates.sort(key=lambda r: (
            r["shanten_after"],
            -r["ukeire_types"],
            -r["ukeire_count"]
        ))

        if candidates:
            candidates[0]["is_best"] = True

        best = candidates[0] if candidates else None
        shanten_str = "听牌！" if shanten == 0 else f"{shanten}向听"

        # 构建理由
        reason_parts = [f"当前{shanten_str}"]
        if parts.get("pair"):
            reason_parts.append("有雀头")
        else:
            reason_parts.append("无雀头")
        reason_parts.append(f"面子×{parts['mentsu']} 搭子×{parts['tatsu']}")

        if best:
            uke_names = best["ukeire_tiles"][:6]
            uke_str = " ".join(uke_names)
            reason_parts.append(f"→ 打{best['tile']} 进张{best['ukeire_types']}种{best['ukeire_count']}枚")

        return {
            "best_discard": best["tile"] if best else None,
            "best_discard_mjai": best["tile_mjai"] if best else None,
            "reason": "，".join(reason_parts),
            "shanten": shanten,
            "shanten_detail": parts,
            "candidates": candidates,
            "tooltip": self._format_tooltip(best, shanten, candidates),
        }

    def _analyze_remote(self) -> dict:
        """调用远程 Mortal API"""
        import requests

        # 构造 mjai 事件序列
        events = self._build_mjai_events()
        payload = json.dumps(events, separators=(",", ":"))

        try:
            compressed = gzip.compress(payload.encode("utf-8"))
            headers = {
                "Authorization": self.remote_api_key or "",
                "Content-Encoding": "gzip",
                "Content-Type": "application/json",
            }
            r = requests.post(
                f"{self.remote_server}/react",
                headers=headers,
                data=compressed,
                timeout=5,
            )
            if r.status_code == 200:
                result = r.json()
                return self._parse_remote_result(result)
        except Exception as e:
            # 远程失败，回退本地
            return self._analyze_local()

        # 回退
        return self._analyze_local()

    def _build_mjai_events(self) -> list[dict]:
        """从手牌构造 mjai 事件序列"""
        events = [
            {
                "type": "start_game",
                "names": ["0", "1", "2", "3"],
                "id": self.player_id,
            },
            {
                "type": "start_kyoku",
                "bakaze": "E",
                "dora_marker": INT_TO_MJAI.get(self.dora_indicators[0], "1p")
                if self.dora_indicators else "1p",
                "kyoku": 1,
                "honba": 0,
                "kyotaku": 0,
                "oya": 0,
                "scores": [25000, 25000, 25000, 25000],
                "tehais": [
                    self.tehai_mjai,
                    ["?"] * 13, ["?"] * 13, ["?"] * 13,
                ],
            },
        ]
        return events

    def _parse_remote_result(self, result: dict) -> dict:
        """解析远程 API 返回"""
        # 远程 API 返回 mjai action 格式
        action_type = result.get("type", "none")
        if action_type == "dahai":
            tile_mjai = result.get("pai", "?")
            tile_name = int_to_tile_name(MJAI_TO_INT.get(tile_mjai, -1))
            return {
                "best_discard": tile_name,
                "best_discard_mjai": tile_mjai,
                "reason": f"远程 Mortal 推荐: 打{tile_name}",
                "shanten": -1,
                "candidates": [],
                "tooltip": f"🏆 远程 AI: 打 {tile_name}",
            }
        return self._analyze_local()

    # ---- mjai 兼容接口 ----

    def react(self, events_json: str) -> str:
        """
        mjai Bot 标准接口: react(events_json) -> action_json

        用于接入 Akagi Controller 框架。
        """
        try:
            events = json.loads(events_json)
        except json.JSONDecodeError:
            return json.dumps({"type": "none"}, separators=(",", ":"))

        for event in events:
            etype = event.get("type")

            if etype == "start_game":
                self.player_id = event.get("id", 0)
                continue

            if etype == "start_kyoku":
                tehai_mjai = event.get("tehais", [[], [], [], []])[self.player_id]
                self.tehai_mjai = tehai_mjai
                self.tehai = [MJAI_TO_INT.get(t, -1) for t in tehai_mjai
                              if MJAI_TO_INT.get(t, -1) >= 0]
                if "dora_marker" in event:
                    d = MJAI_TO_INT.get(event["dora_marker"], -1)
                    if d >= 0:
                        self.dora_indicators = [d]
                continue

            if etype == "dora":
                d = MJAI_TO_INT.get(event.get("dora_marker", ""), -1)
                if d >= 0 and d not in self.dora_indicators:
                    self.dora_indicators.append(d)
                continue

            if etype == "tsumo" and event.get("actor") == self.player_id:
                tile = MJAI_TO_INT.get(event.get("pai", ""), -1)
                if tile >= 0:
                    self.tehai.append(tile)
                    self.tehai = sorted(self.tehai)
                    self.tehai_mjai = [INT_TO_MJAI[t] for t in self.tehai]
                    # 做决策
                    result = self.analyze()
                    if result.get("best_discard_mjai"):
                        return json.dumps({
                            "type": "dahai",
                            "pai": result["best_discard_mjai"],
                            "actor": self.player_id,
                            "tsumogiri": False,
                        }, separators=(",", ":"))
                continue

        return json.dumps({"type": "none"}, separators=(",", ":"))

    def think(self) -> str:
        """mjai Bot 决策方法"""
        result = self.analyze()
        if result.get("best_discard_mjai"):
            return json.dumps({
                "type": "dahai",
                "pai": result["best_discard_mjai"],
                "actor": self.player_id,
                "tsumogiri": False,
            }, separators=(",", ":"))
        return json.dumps({"type": "none"}, separators=(",", ":"))

    # ---- 格式化输出 ----

    def _format_tooltip(self, best: dict, shanten: int,
                        candidates: list[dict]) -> str:
        """生成界面友好的提示文本"""
        if best is None:
            return "⚠️ 无法分析"

        emoji_map = {0: "🎯", 1: "⏳", 2: "⏳", 3: "🔍"}
        emoji = emoji_map.get(shanten, "🔍")
        shanten_str = "听牌！" if shanten == 0 else f"{shanten}向听"

        lines = [
            f"{emoji} {shanten_str} → 打 {best['tile']}",
            f"   进张 {best['ukeire_types']} 种 / {best['ukeire_count']} 枚",
        ]

        # 显示前3个进张
        if best["ukeire_tiles"]:
            top_uke = best["ukeire_tiles"][:5]
            lines.append(f"   {' '.join(top_uke)}")

        # 如果有宝牌信息
        if self.dora_indicators:
            dora_list = [DORA_NEXT.get(d, -1) for d in self.dora_indicators]
            dora_names = [int_to_tile_name(d) for d in dora_list if d >= 0]
            if dora_names:
                lines.append(f"   🀄 宝牌: {' '.join(dora_names)}")

        return "\n".join(lines)


# ============================================================
# CLI 测试
# ============================================================

if __name__ == "__main__":
    # 测试手牌
    test_hands = [
        # 基本听牌判断
        ["三万", "四万", "五万", "七筒", "八筒", "九筒", "二索", "二索", "五索", "六索", "七索", "東", "東", "北"],
        # 缺雀头
        ["三万", "四万", "五万", "一筒", "二筒", "三筒", "五索", "六索", "七索", "白", "白", "發", "中"],
    ]

    bot = AkagiTilesBot(backend="local")

    for hand in test_hands:
        print(f"\n{'='*60}")
        print(f"手牌: {' '.join(hand)}")
        print(f"{'='*60}")

        result = bot.analyze(hand)
        print(f"\n{result['reason']}")
        print()
        print(f"{'牌':<6} {'打后向听':<8} {'进张种类':<8} {'进张枚数':<8} {'推荐'}")
        print("-" * 50)

        for c in result["candidates"][:8]:
            star = "★" if c["is_best"] else ""
            shanten_str = str(c["shanten_after"])
            if c["shanten_after"] < result["shanten"]:
                shanten_str += "↓"
            elif c["shanten_after"] > result["shanten"]:
                shanten_str += "↑"
            print(f"{c['tile']:<6} {shanten_str:<8} {c['ukeire_types']:<8} {c['ukeire_count']:<8} {star}")

        print(f"\n💡 {result['tooltip']}")
