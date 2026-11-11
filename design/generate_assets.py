from pathlib import Path
from PIL import Image, ImageOps


def main():
    root = Path(__file__).resolve().parent / "assets"
    with Image.open(root / "shu-campus-lake-source.webp") as source:
        desktop = ImageOps.fit(source, (1368, 430), method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))
        mobile = ImageOps.fit(source, (724, 600), method=Image.Resampling.LANCZOS, centering=(0.6, 0.5))
        desktop.save(root / "shu-campus-desktop.webp", quality=88, method=6)
        mobile.save(root / "shu-campus-mobile.webp", quality=88, method=6)


if __name__ == "__main__":
    main()
