from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)
random.seed(352)


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(name, size)


def make_garden():
    width, height = 1280, 900
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        t = y / height
        color = (int(205 - t * 34), int(226 - t * 25), int(229 - t * 20))
        for x in range(width):
            pixels[x, y] = color
    draw = ImageDraw.Draw(image)
    draw.ellipse((72, 48, 202, 178), fill=(246, 227, 174))
    draw.polygon([(0, 470), (180, 355), (350, 472), (550, 350), (780, 470), (1030, 344), (1280, 464), (1280, 900), (0, 900)], fill=(146, 179, 132))
    draw.polygon([(0, 603), (290, 500), (580, 577), (940, 472), (1280, 566), (1280, 900), (0, 900)], fill=(110, 151, 105))
    draw.polygon([(0, 786), (1280, 690), (1280, 900), (0, 900)], fill=(174, 166, 143))
    draw.polygon([(448, 900), (590, 568), (735, 568), (892, 900)], fill=(206, 199, 179))
    draw.polygon([(496, 900), (620, 579), (701, 579), (829, 900)], fill=(218, 212, 195))

    for x, y, scale in [(258, 455, 1.0), (1008, 443, 0.82), (1160, 531, 0.68)]:
        draw.line((x, y + 22, x - 8 * scale, y + 230 * scale), fill=(111, 79, 51), width=int(16 * scale))
        draw.ellipse((x - 94 * scale, y - 72 * scale, x + 83 * scale, y + 87 * scale), fill=(108, 150, 92))
        draw.ellipse((x - 72 * scale, y - 115 * scale, x + 104 * scale, y + 54 * scale), fill=(128, 164, 101))
        draw.ellipse((x - 119 * scale, y - 32 * scale, x + 44 * scale, y + 127 * scale), fill=(119, 157, 94))

    def bed(points, soil_points, plant_area, shade):
        draw.polygon([(x + 12, y + 24) for x, y in points], fill=(58, 68, 48))
        draw.polygon(points, fill=(160, 113, 76))
        draw.polygon(soil_points, fill=(91, 78, 56))
        left, top, right, bottom = plant_area
        for _ in range(60):
            x = random.randint(left, right)
            y = random.randint(top, bottom)
            if y < top + (x - left) * 0.06:
                continue
            leaf = random.choice(shade)
            radius = random.randint(6, 14)
            draw.ellipse((x - radius, y - radius * 0.7, x + radius, y + radius * 0.7), fill=leaf)
            draw.line((x, y + radius // 2, x + random.randint(-5, 5), y + radius + 8), fill=(80, 111, 63), width=2)
        draw.line(points + [points[0]], fill=(193, 148, 102), width=13, joint="curve")
        draw.line(soil_points + [soil_points[0]], fill=(72, 68, 50), width=5, joint="curve")

    greens = [(97, 139, 78), (133, 165, 91), (165, 174, 102), (91, 126, 79), (178, 181, 112)]
    bed([(202, 609), (457, 568), (526, 635), (262, 686)], [(219, 615), (450, 578), (503, 631), (269, 674)], (236, 594, 482, 653), greens)
    bed([(774, 583), (1037, 619), (1003, 702), (724, 663)], [(788, 592), (1022, 624), (991, 687), (741, 653)], (760, 606, 1007, 675), greens)
    bed([(437, 713), (689, 665), (766, 737), (507, 795)], [(453, 719), (680, 677), (744, 732), (518, 781)], (475, 695, 719, 762), greens)

    draw.rounded_rectangle((1047, 605, 1184, 797), radius=27, fill=(83, 137, 145), outline=(60, 105, 116), width=8)
    draw.ellipse((1047, 590, 1184, 637), fill=(130, 174, 174), outline=(60, 105, 116), width=7)
    draw.arc((1062, 601, 1168, 661), start=0, end=180, fill=(222, 228, 207), width=6)
    draw.line((1182, 733, 1228, 733, 1228, 798), fill=(74, 115, 117), width=13, joint="curve")

    draw.line((116, 614, 149, 614, 144, 741, 117, 741, 116, 614), fill=(226, 219, 192), width=7)
    draw.line((132, 624, 132, 733), fill=(247, 242, 222), width=3)
    for y in (646, 669, 692, 715):
        draw.line((124, y, 140, y), fill=(105, 127, 105), width=3)
    image.save(ASSETS / "garden-observation.png", optimize=True)
    return image


def make_pdf(garden):
    width, height = 1240, 1754
    paper = (250, 249, 245)
    ink = (39, 48, 43)
    muted = (104, 115, 106)
    green = (62, 113, 83)
    rust = (172, 91, 63)

    page1 = Image.new("RGB", (width, height), paper)
    d = ImageDraw.Draw(page1)
    d.text((112, 90), "NORTHBANK FIELD NOTES     /     04", font=font(21, True), fill=green)
    d.line((112, 142, 1128, 142), fill=(211, 217, 205), width=3)
    d.text((112, 218), "Small garden water, slowly", font=font(62, True), fill=ink)
    d.text((114, 315), "A short observation guide for community learning", font=font(28), fill=muted)
    d.rounded_rectangle((112, 416, 1128, 710), radius=24, fill=(235, 241, 230))
    d.text((153, 458), "FIELD QUESTION", font=font(19, True), fill=green)
    d.text((153, 505), "What changes after a light rain?", font=font(36, True), fill=ink)
    d.text((153, 570), "Follow water from the garden path to one planting bed.", font=font(25), fill=ink)
    d.text((112, 805), "01   Notice the ground", font=font(31, True), fill=ink)
    d.text((112, 864), "Look for darker soil, shallow channels, and places where water", font=font(25), fill=ink)
    d.text((112, 904), "rests. Record what you can see before drawing an explanation.", font=font(25), fill=ink)
    d.text((112, 1028), "02   Compare two small areas", font=font(31, True), fill=ink)
    d.text((112, 1087), "Choose one planted bed and one path edge. Use the same", font=font(25), fill=ink)
    d.text((112, 1127), "observation interval for both locations.", font=font(25), fill=ink)
    d.rounded_rectangle((112, 1261, 1128, 1454), radius=18, fill=(247, 239, 225))
    d.text((151, 1302), "KEEP THE RECORD", font=font(18, True), fill=rust)
    d.text((151, 1350), "Describe a visible pattern first; mark interpretation separately.", font=font(24), fill=ink)
    d.text((112, 1642), "Synthetic teaching sample  ·  Fictional source and publication edition", font=font(18), fill=muted)
    d.text((1094, 1640), "01", font=font(23, True), fill=green)

    page2 = Image.new("RGB", (width, height), paper)
    d = ImageDraw.Draw(page2)
    d.text((112, 90), "NORTHBANK FIELD NOTES     /     04", font=font(21, True), fill=green)
    d.line((112, 142, 1128, 142), fill=(211, 217, 205), width=3)
    d.text((112, 208), "03   Map a simple route", font=font(36, True), fill=ink)
    d.text((112, 265), "Trace one path with three stops: edge, bed, and barrel.", font=font(24), fill=muted)
    garden_thumb = garden.resize((842, 592))
    page2.paste(garden_thumb, (199, 354))
    d.rounded_rectangle((176, 331, 1065, 970), radius=12, outline=(211, 217, 205), width=3)
    d.text((112, 1044), "04   Write what the picture cannot tell you", font=font(31, True), fill=ink)
    d.text((112, 1104), "Note when and where the observation was made. A photograph", font=font(24), fill=ink)
    d.text((112, 1144), "can show a surface, but not the amount or direction of flow.", font=font(24), fill=ink)
    d.rounded_rectangle((112, 1262, 1128, 1456), radius=18, fill=(235, 241, 230))
    d.text((150, 1301), "SAMPLE RECORD", font=font(18, True), fill=green)
    d.text((150, 1350), "“The path edge is darker than the bed after the shower.”", font=font(22), fill=ink)
    d.text((112, 1642), "Synthetic teaching sample  ·  Fictional source and publication edition", font=font(18), fill=muted)
    d.text((1094, 1640), "02", font=font(23, True), fill=green)

    page1.save(ASSETS / "field-observation-guide.pdf", "PDF", save_all=True, append_images=[page2], resolution=150.0)


make_pdf(make_garden())
