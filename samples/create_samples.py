"""
Generates clean sample ID card images and text files for testing the verification pipeline.
"""

import os
from PIL import Image, ImageDraw, ImageFont


def create_id_image(filename: str, title: str, lines: list, bg_color=(245, 247, 250), border_color=(79, 70, 229)):
    width, height = 750, 480
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Outer decorative card border
    draw.rounded_rectangle([15, 15, width - 15, height - 15], radius=16, outline=border_color, width=3)
    # Header bar
    draw.rounded_rectangle([18, 18, width - 18, 80], radius=12, fill=border_color)

    # Text rendering
    # Header title
    draw.text((35, 35), title, fill=(255, 255, 255))

    # Photo placeholder
    draw.rounded_rectangle([45, 110, 195, 290], radius=8, outline=(156, 163, 175), width=2, fill=(229, 231, 235))
    draw.text((90, 190), "PHOTO", fill=(107, 114, 128))

    # Body lines
    y = 115
    for label, val in lines:
        draw.text((225, y), f"{label}:", fill=(75, 85, 99))
        draw.text((360, y), str(val), fill=(17, 24, 39))
        y += 42

    output_path = os.path.join(os.path.dirname(__file__), filename)
    img.save(output_path)
    print(f"Generated sample image: {output_path}")


def main():
    samples_dir = os.path.dirname(__file__)

    # 1. Aadhaar Card
    create_id_image(
        "aadhaar_sample.png",
        "GOVERNMENT OF INDIA - AADHAAR CARD",
        [
            ("Name", "Shriyansh Gupta"),
            ("DOB", "1998-05-14"),
            ("Gender", "M"),
            ("Aadhaar Number", "9841 2356 7192"),
            ("Address", "42 Silicon Enclave, Indiranagar, Bengaluru 560038"),
        ],
        border_color=(22, 101, 52),
    )

    # 2. PAN Card
    create_id_image(
        "pan_sample.png",
        "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
        [
            ("Name", "SHRIYANSH GUPTA"),
            ("Father's Name", "RAJESH GUPTA"),
            ("Date of Birth", "1998-05-14"),
            ("Permanent Account No", "ABCDE1234F"),
        ],
        border_color=(30, 64, 175),
    )

    # 3. Voter ID
    create_id_image(
        "voter_sample.png",
        "ELECTION COMMISSION OF INDIA - EPIC",
        [
            ("Elector's Name", "Shriyansh Gupta"),
            ("Father's Name", "Rajesh Gupta"),
            ("Date of Birth", "1998-05-14"),
            ("EPIC Number", "WXH1293847"),
            ("Constituency", "Bangalore South"),
        ],
        border_color=(124, 58, 237),
    )

    # 4. Driving Licence
    create_id_image(
        "driving_licence_sample.png",
        "UNION OF INDIA - DRIVING LICENCE",
        [
            ("Name", "Shriyansh Gupta"),
            ("DOB", "1998-05-14"),
            ("DL Number", "KA0320180012345"),
            ("Valid From", "2018-05-15"),
            ("Valid Until", "2038-05-14"),
            ("Vehicle Class", "LMV, MCWG"),
        ],
        border_color=(180, 83, 9),
    )


if __name__ == "__main__":
    main()
