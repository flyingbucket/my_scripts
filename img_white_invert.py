#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pip install pillow

import argparse, os, glob
from PIL import Image, ImageOps


def add_white_bg(img: Image.Image, force_opaque=False) -> Image.Image:
    """把图片放到白底上：透明区域→白色。
    force_opaque=True 时强制去掉透明通道，转成 RGB。
    """
    if img.mode in ("RGBA", "LA"):
        # 以白色作底，按 alpha 贴上去
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        out = bg
    else:
        # 非带透明图，先转 RGB，再画个白底以防万一
        out = img.convert("RGB")
    if force_opaque:
        return out.convert("RGB")
    return out


def invert_colors(img: Image.Image) -> Image.Image:
    """仅反转 RGB，不改变 alpha。"""
    if img.mode == "RGBA":
        r, g, b, a = img.split()
        inv = ImageOps.invert(Image.merge("RGB", (r, g, b)))
        r2, g2, b2 = inv.split()
        return Image.merge("RGBA", (r2, g2, b2, a))
    elif img.mode in ("RGB", "L"):
        return ImageOps.invert(img.convert("RGB"))
    else:
        # 统一转成 RGBA 再处理
        rgba = img.convert("RGBA")
        return invert_colors(rgba)


def process_one(
    path, outdir, suffix_white="_white", suffix_inv="_inverted", opaque=False
):
    base, _ = os.path.splitext(os.path.basename(path))
    img = Image.open(path)

    # 1) 加白底
    with_white = add_white_bg(img, force_opaque=opaque)
    out_white = os.path.join(outdir, f"{base}{suffix_white}.png")
    with_white.save(out_white)

    # 2) 取反色
    inverted = invert_colors(with_white)
    out_inv = os.path.join(outdir, f"{base}{suffix_inv}.png")
    inverted.save(out_inv)

    return out_white, out_inv


def main():
    ap = argparse.ArgumentParser(
        description="为图片添加白底并生成取反色版本（批量处理）"
    )
    ap.add_argument("inputs", nargs="+", help="输入文件或通配符（例如 imgs/*.png）")
    ap.add_argument("-o", "--outdir", default=".", help="输出目录（默认当前目录）")
    ap.add_argument(
        "--suffix-white", default="_white", help="白底图后缀（默认 _white）"
    )
    ap.add_argument(
        "--suffix-inv", default="_inverted", help="取反图后缀（默认 _inverted）"
    )
    ap.add_argument(
        "--opaque", action="store_true", help="强制去透明，输出纯 RGB（默认保留 RGBA）"
    )
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    files = []
    for p in args.inputs:
        files.extend(glob.glob(p))
    if not files:
        print("No matching files.")
        return

    exts = (".png", ".jpg", ".jpeg", ".webp")
    for f in files:
        if not f.lower().endswith(exts):
            continue
        w, inv = process_one(
            f,
            args.outdir,
            suffix_white=args.suffix_white,
            suffix_inv=args.suffix_inv,
            opaque=args.opaque,
        )
        print(f"OK: {f} -> {w} ; {inv}")


if __name__ == "__main__":
    main()
