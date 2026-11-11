import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps


def main():
    root = Path(__file__).resolve().parent
    boards = json.loads((root / "board-index.json").read_text(encoding="utf-8"))["boards"]
    loaded = []
    errors = []
    for board in boards:
        path = root / "previews" / f"{board['flow']}-{board['flowIndex']:02d}.png"
        if not path.is_file():
            errors.append(f"缺少预览：{path.name}")
            continue
        expected = tuple(map(int, board["viewport"].split("x")))
        with Image.open(path) as image:
            if image.size != expected:
                errors.append(f"{path.name}：预期 {expected}，实际 {image.size}")
                continue
            loaded.append((board, image.convert("RGB")))
    if errors or len(loaded) != 57:
        raise RuntimeError("\n".join([*errors, f"有效预览数量：{len(loaded)}"]))
    font_path = subprocess.run(
        ["fc-match", "-f", "%{file}", "Noto Sans CJK SC"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    label_font = ImageFont.truetype(font_path, 16)
    small_font = ImageFont.truetype(font_path, 14)
    meta_font = ImageFont.truetype(font_path, 11)
    files = []
    for start in range(0, len(loaded), 9):
        sheet = Image.new("RGB", (1504, 1150), "#F4F6F8")
        draw = ImageDraw.Draw(sheet)
        for offset, (board, image) in enumerate(loaded[start:start + 9]):
            column, row = offset % 3, offset // 3
            x, y = 16 + column * 496, 16 + row * 378
            draw.rectangle((x, y, x + 480, y + 362), fill="#FFFFFF", outline="#DCE1E7")
            label = f"{board['flowTitle']} · {board['name']}"
            font = label_font if draw.textlength(label, font=label_font) <= 456 else small_font
            draw.text((x + 12, y + 8), label, fill="#202B3C", font=font)
            exploratory = board["status"] == "exploratory"
            meta = f"{board['flow']} · {'探索稿' if exploratory else '候选稿'}"
            draw.text((x + 12, y + 30), meta, fill="#9C6508" if exploratory else "#626D7A", font=meta_font)
            draw.rectangle((x + 12, y + 48, x + 468, y + 350), fill="#F4F6F8")
            thumbnail = ImageOps.contain(image, (448, 294), method=Image.Resampling.LANCZOS)
            sheet.paste(thumbnail, (x + 12 + (456 - thumbnail.width) // 2, y + 48 + (302 - thumbnail.height) // 2))
        path = root / "previews" / f"overview-{start // 9 + 1:02d}.png"
        sheet.save(path)
        files.append(path.name)
    print(json.dumps({"previewCount": len(loaded), "overviewCount": len(files), "files": files}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
