#!/usr/bin/env python3
"""
生成 34 种标准日本麻将牌面模板
匹配雀魂牌面风格：白底、黑/红图案、标准牌面比例
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import os

OUTDIR = Path(__file__).parent / "templates_gen"
W, H = 94, 148
FONT_DIR = Path("/usr/share/fonts")

# 所有 34 种牌
TILES = {
    # 万子 (Man) 1-9
    "m1": "一万", "m2": "二万", "m3": "三万", "m4": "四万", "m5": "五万",
    "m6": "六万", "m7": "七万", "m8": "八万", "m9": "九万",
    # 筒子 (Pin) 1-9
    "p1": "一筒", "p2": "二筒", "p3": "三筒", "p4": "四筒", "p5": "五筒",
    "p6": "六筒", "p7": "七筒", "p8": "八筒", "p9": "九筒",
    # 索子 (Sou) 1-9
    "s1": "一索", "s2": "二索", "s3": "三索", "s4": "四索", "s5": "五索",
    "s6": "六索", "s7": "七索", "s8": "八索", "s9": "九索",
    # 字牌 (Jihai) 东南西北白发中
    "z1": "東", "z2": "南", "z3": "西", "z4": "北",
    "z5": "白", "z6": "發", "z7": "中",
}

# 万子数字
MAN_NUMS = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
            6: "六", 7: "七", 8: "八", 9: "九"}

# 索子图案（简化为竖条）
SOU_BARS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9}


def find_font(size=36):
    """找到可用的中文字体"""
    for path in [
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()


def draw_man_tile(draw, num, font_big, font_small, w, h):
    """万子：左上数字 + 中心"X万" """
    # 左上角数字
    n = MAN_NUMS[num]
    draw.text((8, 4), n, fill="black", font=font_small)
    # 中心大字
    text = f"{n}万"
    bbox = draw.textbbox((0, 0), text, font=font_big)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((w - tw) // 2, (h - th) // 2 - 5), text, fill="black", font=font_big)
    # "万"字用红色
    wan_bbox = draw.textbbox((0, 0), "万", font=font_big)
    wan_w = wan_bbox[2] - wan_bbox[0]
    draw.text(((w - tw) // 2 + tw - wan_w, (h - th) // 2 - 5), "万", fill="red", font=font_big)


def draw_pin_tile(draw, num, font_big, font_small, w, h):
    """筒子：左上数字 + 中心圆点矩阵"""
    n = MAN_NUMS[num]
    draw.text((8, 4), n, fill="black", font=font_small)

    # 圆点排列
    radius = 8
    cx, cy = w // 2, h // 2 - 5

    # 各数字的圆点坐标（相对中心偏移）
    positions = {
        1: [(0, 0)],
        2: [(0, -16), (0, 16)],
        3: [(-16, -16), (0, 0), (16, 16)],
        4: [(-16, -16), (16, -16), (-16, 16), (16, 16)],
        5: [(-16, -16), (16, -16), (0, 0), (-16, 16), (16, 16)],
        6: [(-16, -16), (16, -16), (-16, 2), (16, 2), (-16, 20), (16, 20)],
        7: [(-20, -18), (0, -14), (20, -10), (-16, 4), (16, 4), (-20, 20), (20, 20)],
        8: [(-20, -20), (0, -16), (20, -12), (-16, 4), (16, 4), (-20, 12), (0, 16), (20, 20)],
        9: [(-16, -20), (0, -20), (16, -20), (-16, 0), (0, 0), (16, 0), (-16, 20), (0, 20), (16, 20)],
    }

    for dx, dy in positions.get(num, [(0, 0)]):
        x = cx + dx
        y = cy + dy
        draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                     outline="black", fill="white", width=2)


def draw_sou_tile(draw, num, font_big, font_small, w, h):
    """索子：左上数字 + 简化竹条图案"""
    n = MAN_NUMS[num]
    draw.text((8, 4), n, fill="black", font=font_small)

    if num == 1:
        # 一索：鸟/孔雀图案（简化为菱形）
        cx, cy = w // 2, h // 2 - 10
        draw.ellipse([cx - 20, cy - 25, cx + 20, cy + 15], outline="black", width=2)
        draw.polygon([(cx, cy - 28), (cx - 8, cy - 10), (cx + 8, cy - 10)], fill="black")
        draw.ellipse([cx - 4, cy - 5, cx + 4, cy + 5], fill="black")
    else:
        # 竹条图案
        bar_h = 18
        bar_w = 16
        gap = 3
        total_h = num * bar_h + (num - 1) * gap
        start_y = (h - total_h) // 2 + 5

        for i in range(num):
            y = start_y + i * (bar_h + gap)
            # 每根竹条：窄矩形 + 水平线
            draw.rectangle([(w - bar_w) // 2, y, (w + bar_w) // 2, y + bar_h],
                          outline="black", fill="white", width=1)
            # 画竹节
            draw.line([(w - bar_w) // 2 - 4, y + bar_h // 2,
                       (w + bar_w) // 2 + 4, y + bar_h // 2],
                      fill="black", width=1)

            # 红色数字标记
            if num == 5 and (i == 0 or i == 4):
                draw.ellipse([(w - 3) // 2, y + 3, (w + 3) // 2, y + bar_h - 3],
                            outline="red", width=1)


def draw_jihai_tile(draw, char, font_big, w, h):
    """字牌：单一大字居中"""
    color = "black"
    if char == "發":
        color = "green"
    elif char == "中":
        color = "red"

    bbox = draw.textbbox((0, 0), char, font=font_big)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((w - tw) // 2, (h - th) // 2 - 5), char, fill=color, font=font_big)


def create_tile_image(key, outdir):
    """创建单张牌面模板"""
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # 边框（蓝灰色，模仿雀魂）
    draw.rectangle([2, 2, W - 3, H - 3], outline="#6688aa", width=2)
    # 内边框
    draw.rectangle([5, 5, W - 6, H - 6], outline="#99aabb", width=1)

    font_big = find_font(40)
    font_small = find_font(18)

    # 根据牌种渲染
    if key.startswith("m"):  # 万子
        num = int(key[1:])
        draw_man_tile(draw, num, font_big, font_small, W, H)
    elif key.startswith("p"):  # 筒子
        num = int(key[1:])
        draw_pin_tile(draw, num, font_big, font_small, W, H)
    elif key.startswith("s"):  # 索子
        num = int(key[1:])
        draw_sou_tile(draw, num, font_big, font_small, W, H)
    elif key.startswith("z"):  # 字牌
        num = int(key[1:])
        chars = {1: "東", 2: "南", 3: "西", 4: "北", 5: "白", 6: "發", 7: "中"}
        draw_jihai_tile(draw, chars[num], font_big, W, H)

    path = outdir / f"{key}.png"
    img.save(str(path))
    return path


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print(f"生成 {len(TILES)} 种牌面模板...")
    for key, label in TILES.items():
        path = create_tile_image(key, OUTDIR)
        print(f"  {key}: {label} -> {path.name}")

    # 生成预览图：全部 34 张拼成网格
    preview = Image.new("RGB", (W * 9 + 18, H * 4 + 8), "#333333")
    tile_order = (
        ["m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9"] +
        ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9"] +
        ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9"] +
        ["z1", "z2", "z3", "z4", "z5", "z6", "z7"]
    )
    for i, key in enumerate(tile_order):
        row, col = i // 9, i % 9
        tile_path = OUTDIR / f"{key}.png"
        if tile_path.exists():
            tile_img = Image.open(tile_path)
            preview.paste(tile_img, (col * (W + 2) + 2, row * (H + 2) + 2))

    preview_path = OUTDIR.parent / "templates_gen_preview.jpg"
    preview.save(str(preview_path), quality=90)
    print(f"\n预览图: {preview_path}")

    return 0


if __name__ == "__main__":
    exit(main())
