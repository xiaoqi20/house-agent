"""把设计稿（方形、浅底）转成项目要用的图标资产。

用法：
    server/.venv/bin/python web/scripts/make-icon-exports.py <源图.png>

做三件事：去掉浅色底（转透明）、裁到内容边界 + 统一留白、导出各尺寸到 web/public/。
- icon-1024 / 512 / 192 / apple-touch-icon：直接用原稿（5 行，细节完整）
- favicon / favicon-32 / mark-96：按原稿实测比例**重画 3 行简化版**（5 行缩到 16px 会糊）

ponytail: 只在换图标时跑一次；不引入构建期依赖，PIL 已随后端环境存在。
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

PUBLIC = Path(__file__).resolve().parent.parent / "public"
DETAILED_EXPORTS = {"icon-1024.png": 1024, "icon-512.png": 512,
                    "icon-192.png": 192, "apple-touch-icon.png": 180}
SMALL_EXPORTS = {"mark-96.png": 96, "favicon.png": 48, "favicon-32.png": 32}
PADDING = 0.08  # 裁切/画布四周留白比例

# 以下为原稿实测值（1254×1254 源图，内容 683×625）：两根"柱子" 184×91，连接条 263 宽，
# 行距 133（行间空隙 42），柱与连接条间距 26，圆角接近全圆，琥珀点直径 47。
BLUE, AMBER = (14, 165, 233, 255), (245, 158, 11, 255)
TILE_W, TILE_H, LINK_W, LINK_H, DOT_D, INNER_GAP = 184, 91, 263, 38, 47, 26
PITCH = 133
MARK_W = TILE_W * 2 + LINK_W + INNER_GAP * 2


def remove_light_background(image: Image.Image) -> Image.Image:
    """浅底转透明：按"最小通道"估计背景权重，再反解原色，避免边缘留白灰边"""

    image = image.convert("RGBA")
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            r, g, b, _ = pixels[x, y]
            alpha = 1.0 - min(r, g, b) / 255.0  # 纯白=0，饱和色≈1
            if alpha < 0.06:
                pixels[x, y] = (0, 0, 0, 0)
                continue
            if alpha < 1.0:  # 边缘像素：反解被白底冲淡的颜色
                r = max(0, min(255, round((r - 255 * (1 - alpha)) / alpha)))
                g = max(0, min(255, round((g - 255 * (1 - alpha)) / alpha)))
                b = max(0, min(255, round((b - 255 * (1 - alpha)) / alpha)))
            pixels[x, y] = (r, g, b, round(alpha * 255))
    return image


def square_with_padding(image: Image.Image) -> Image.Image:
    """裁到内容边界，再放进正方形画布居中（留白由 PADDING 控制）"""

    box = image.getbbox()
    if box is None:
        raise SystemExit("源图看起来是纯色，没有可裁切的内容")
    content = image.crop(box)
    side = round(max(content.size) * (1 + PADDING * 2))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(content, ((side - content.width) // 2, (side - content.height) // 2))
    return canvas


def draw_simplified(scale: int = 8) -> Image.Image:
    """3 行简化版：行数从 5 减到 3，笔画同宽同色，保证 16px 仍能读出"两栏对齐 + 一个异常点"""

    rows = 3
    height = TILE_H + (rows - 1) * PITCH
    canvas = Image.new("RGBA", (MARK_W * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for row in range(rows):
        top = row * PITCH
        for left in (0, TILE_W + INNER_GAP + LINK_W + INNER_GAP):
            draw.rounded_rectangle([left * scale, top * scale,
                                    (left + TILE_W) * scale, (top + TILE_H) * scale],
                                   radius=TILE_H // 2 * scale, fill=BLUE)
        link_left = TILE_W + INNER_GAP
        link_top = top + (TILE_H - LINK_H) // 2
        if row == 1:  # 中间行断开，用琥珀点标出"对不上"
            half = (LINK_W - DOT_D) // 2 - 8
            draw.rounded_rectangle([link_left * scale, link_top * scale,
                                    (link_left + half) * scale, (link_top + LINK_H) * scale],
                                   radius=LINK_H // 2 * scale, fill=BLUE)
            draw.rounded_rectangle([(link_left + LINK_W - half) * scale, link_top * scale,
                                    (link_left + LINK_W) * scale, (link_top + LINK_H) * scale],
                                   radius=LINK_H // 2 * scale, fill=BLUE)
            cx = (link_left + LINK_W // 2) * scale
            cy = (top + TILE_H // 2) * scale
            draw.ellipse([cx - DOT_D // 2 * scale, cy - DOT_D // 2 * scale,
                          cx + DOT_D // 2 * scale, cy + DOT_D // 2 * scale], fill=AMBER)
        else:
            draw.rounded_rectangle([link_left * scale, link_top * scale,
                                    (link_left + LINK_W) * scale, (link_top + LINK_H) * scale],
                                   radius=LINK_H // 2 * scale, fill=BLUE)
    return canvas.resize((MARK_W, height), Image.LANCZOS)


def to_square(mark: Image.Image, size: int) -> Image.Image:
    """把宽幅标记放进 size×size 的透明正方形里（保持比例、居中、留白）"""

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inner_w = round(size * (1 - PADDING * 2))
    inner_h = round(inner_w * mark.height / mark.width)
    scaled = mark.resize((inner_w, inner_h), Image.LANCZOS)
    canvas.paste(scaled, ((size - inner_w) // 2, (size - inner_h) // 2), scaled)
    return canvas


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    PUBLIC.mkdir(parents=True, exist_ok=True)

    detailed = square_with_padding(remove_light_background(Image.open(sys.argv[1])))
    for name, size in DETAILED_EXPORTS.items():
        detailed.resize((size, size), Image.LANCZOS).save(PUBLIC / name, optimize=True)
        print(f"✓ web/public/{name} ({size}×{size}，原稿)")

    small = draw_simplified()
    for name, size in SMALL_EXPORTS.items():
        to_square(small, size).save(PUBLIC / name, optimize=True)
        print(f"✓ web/public/{name} ({size}×{size}，3 行简化版)")


if __name__ == "__main__":
    main()
