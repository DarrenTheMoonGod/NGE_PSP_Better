from PIL import Image
import sys
import os

def make_paletted(input_file, colors=256):
    # Open the image
    img = Image.open(input_file)

    # Convert to paletted mode (P), adaptive quantization
    pal_img = img.convert("P", palette=Image.ADAPTIVE, colors=colors)

    # Build output filename
    base, ext = os.path.splitext(input_file)
    output_file = base + "_pal.png"

    # Save as PNG-8 format with no optimization (simpler, more compatible)
    pal_img.save(output_file, format="PNG", optimize=False)

    print("Converted %s -> %s with %d colors in palette" % (input_file, output_file, colors))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python palette2.py input.png [colors]")
    else:
        input_file = sys.argv[1]
        colors = int(sys.argv[2]) if len(sys.argv) > 2 else 256
        make_paletted(input_file, colors)

