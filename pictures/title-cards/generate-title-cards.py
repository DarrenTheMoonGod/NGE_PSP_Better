#!/usr/bin/env python3
import json
import png
import sys

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "font.ttf"

class TitleImage:
    def __init__(self):
        self.width = 0
        self.height = 0
        self.palette = []
        self.content = []

    def load(self, input_path):
        pr = png.Reader(filename=input_path)
        pic = pr.read()

        self.width = pic[0]
        self.height = pic[1]

        # Load palette if present
        palette_raw = pic[3].get('palette', [])
        self.palette = [(c[0], c[1], c[2], (0xFF if len(c) == 3 else c[3])) for c in palette_raw]

        # Extend the palette if it doesn't fit into a 0, 16, 256 bucket
        if len(self.palette) != 0:
            if len(self.palette) < 16:
                self.palette.extend([(0, 0, 0, 0xFF)] * (16 - len(self.palette)))
            elif len(self.palette) > 16 and len(self.palette) < 256:
                self.palette.extend([(0, 0, 0, 0xFF)] * (256 - len(self.palette)))

        # Load content
        if len(self.palette) == 0:
            # RGBA mode
            self.content = []
            color_channel_buffer = [0] * 4
            color_channel_buffer[3] = 0xFF
            i = 0
            for row in pic[2]:
                for color_channel in row:
                    color_channel_buffer[i] = color_channel
                    i += 1

                    if (pic[3].get('alpha') and i == 4) or (not pic[3].get('alpha') and i == 3):
                        self.content.append((
                            color_channel_buffer[0],
                            color_channel_buffer[1],
                            color_channel_buffer[2],
                            color_channel_buffer[3]))
                        i = 0
        else:
            # Palette mode
            self.content = [c for row in pic[2] for c in row]

    def save(self, output_path):
        with open(output_path, 'wb') as f:
            if len(self.palette) == 0:
                # RGBA mode
                pw = png.Writer(self.width, self.height, alpha=True)
                flattened_image_data = [color_channel for pixel in self.content for color_channel in pixel]
                pw.write_array(f, flattened_image_data)
            else:
                # Palette mode
                pw = png.Writer(self.width, self.height, palette=self.palette)
                pw.write_array(f, self.content)

    def get_pixel(self, x, y):
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return None

        index = y * self.width + x
        if len(self.palette) == 0:
            return self.content[index]
        else:
            return self.content[index]

    def set_pixel(self, x, y, color):
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return

        index = y * self.width + x
        self.content[index] = color

    def find_closest_palette_color(self, target_color):
        if len(self.palette) == 0:
            return target_color

        # If target_color is already a palette index, return it
        if isinstance(target_color, int):
            return target_color

        # Find closest color
        min_distance = float('inf')
        closest_index = 0

        for i, pal_color in enumerate(self.palette):
            distance = (
                (target_color[0] - pal_color[0]) ** 2 +
                (target_color[1] - pal_color[1]) ** 2 +
                (target_color[2] - pal_color[2]) ** 2
            )
            if distance < min_distance:
                min_distance = distance
                closest_index = i

        return closest_index

    def clear(self, color):
        if len(self.palette) == 0:
            # RGBA
            self.content = [color for _ in range(self.width * self.height)]
        else:
            # Paletted
            color_index = self.find_closest_palette_color(color)
            self.content = [color_index for _ in range(self.width * self.height)]

    def blit_phrase_image(self, phrase_image, x, y, width, height):
        # Scale the phrase image to the target dimensions
        scaled_img = phrase_image.image.resize((width, height), Image.Resampling.LANCZOS)

        # Convert main image to PIL
        if len(self.palette) == 0:
            # RGBA
            pil_img = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
            for py in range(self.height):
                for px in range(self.width):
                    idx = py * self.width + px
                    pil_img.putpixel((px, py), self.content[idx])
        else:
            # Paletted
            pil_img = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
            for py in range(self.height):
                for px in range(self.width):
                    idx = py * self.width + px
                    pal_idx = self.content[idx]
                    if pal_idx < len(self.palette):
                        pil_img.putpixel((px, py), self.palette[pal_idx])

        # Paste the scaled phrase image
        pil_img.paste(scaled_img, (x, y), scaled_img)

        # Convert back to internal format
        if len(self.palette) == 0:
            # RGBA
            for py in range(self.height):
                for px in range(self.width):
                    idx = py * self.width + px
                    self.content[idx] = pil_img.getpixel((px, py))
        else:
            # Paletted
            for py in range(self.height):
                for px in range(self.width):
                    idx = py * self.width + px
                    rgba = pil_img.getpixel((px, py))
                    self.content[idx] = self.find_closest_palette_color(rgba)

class PhraseImage:
    def __init__(self, text, font, color=(255, 255, 255, 255), justify='left', line_pixel_skip=2):
        lines = text.split('\n')

        # Draw all text on a large canvas
        temp_canvas = Image.new('RGBA', (4000, 4000), (0, 0, 0, 0))
        temp_draw_handle = ImageDraw.Draw(temp_canvas)

        # Get line measurements
        line_info = []
        max_width = 0

        for line in lines:
            bbox = temp_draw_handle.textbbox((0, 0), line, font=font, anchor='lt')
            line_width = bbox[2] - bbox[0]
            line_height = bbox[3] - bbox[1]

            line_info.append({
                'width': line_width,
                'height': line_height
            })
            max_width = max(max_width, line_width)

        # Redraw lines with justification applied
        # Put drawing in middle of nowhere far from edges
        offset_x = 1000
        offset_y = 1000
        current_y = offset_y

        for i, line in enumerate(lines):
            # Calculate x position based on justification
            if justify == 'center':
                start_x = offset_x + (max_width - line_info[i]['width']) // 2
            
            elif justify == 'right':
                start_x = offset_x + max_width - line_info[i]['width']
            
            else:
                # Left justify
                start_x = offset_x

            temp_draw_handle.text((start_x, current_y), line, font=font, fill=color, anchor='lt')
            current_y += line_info[i]['height'] + line_pixel_skip

        # Get the actual bounding box of the drawn pixels
        bbox = temp_canvas.getbbox()

        if bbox is None:
            raise Exception("No text was drawn!")

        # Crop to the actual drawn area and use it as the final image
        self.image = temp_canvas.crop(bbox)
        self.width = self.image.width
        self.height = self.image.height
        self.aspect = self.width / self.height

    def save_debug(self, output_path):
        # Save the phrase image directly for debugging
        self.image.save(output_path)

def Font(font_path, size=16):
    try:
        return ImageFont.truetype(font_path, size)

    except (OSError, IOError):
        return None


def main():

    # Load font
    try:
        font = Font(FONT_PATH, size=200)

    except Exception as e:
        print(f"Error loading font: {e}")
        sys.exit(1)

    # Load ocr.json
    ocr = {}
    with open("ocr.json", "r", encoding="utf-8") as f:
        ocr = json.loads(f.read())

    # Iterate the ocr image names
    for ocr_filename in ocr.keys():

        ocr_metadata = ocr[ocr_filename]

        # Skip note block
        if not ocr_filename.strip():
            continue

        # DEBUG, skip those we're not focusing on
        if ocr_filename[0] != "!":
            continue
        ocr_filename = ocr_filename[1:]

        print(f"Processing {ocr_filename}...")

        # Load base image
        img = TitleImage()

        try:
            img.load(ocr_filename)

        except FileNotFoundError:
            print(f"Error: {ocr_filename} not found")
            sys.exit(1)

        # Clear to base color
        #img.clear((1, 1, 1, 255))

        # Draw text using PhraseImages
        phrases = ocr_metadata.get("phrases", [])
        phrase_images = [PhraseImage(phrase, font, color=(255, 0, 0, 0xFF), justify='left') for phrase in phrases]

        # Get positions based on the format
        phrase_positions = formatter(ocr_metadata.get("format", "valign"), 
            ocr_metadata.get("options", {}),
            img.width, img.height, phrase_images)

        # Blit the phrase images
        for ((target_x, target_y, target_width, target_height), phrase_image) in zip(phrase_positions, phrase_images):
            img.blit_phrase_image(phrase_image,
                x=target_x,
                y=target_y,
                width=target_width,
                height=target_height)

        # Save output
        img.save(ocr_filename.replace(".PICTURE.png", ".TRANSLATED.png"))

        del img

    print("Done!")


def formatter(name, options, canvas_width, canvas_height, phrase_images):
    # Assert there's at least 1 phrase image
    assert len(phrase_images) >= 1

    canvas_padding = 20

    default_skips = [10, 10, 10]
    default_lifts = [0, 0, 0, 0]
    default_shifts = [0, 0, 0, 0]

    default_aspect = 0.5
    default_height = 40
    default_lift = 0
    default_shift = 0

    default_aspect_list = [default_aspect, default_aspect, default_aspect, default_aspect]
    default_height_list = [default_height, default_height, default_height, default_height]

    # Print internal aspects, divided by height,
    # just needing target width
    for i, phrase_image in enumerate(phrase_images):
        height = None
        aspect = None
        if name == "valign":
            height = options.get("height", default_height)
            aspect = options.get("aspect", default_aspect)
        else:
            height = options.get("height", default_height_list)[i]
            aspect = options.get("aspect", default_aspect_list)[i]
        
        aspect_scalar_incomplete = (1/(phrase_image.aspect * height))

        # DEBUG
        # Hacky debug to not have to do manual calculations
        # Aspect in the JSON is not really aspect but the scalar on the aspect
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()

        target_width = "<target_width>"
        if aspect == 0.5: # If it's default aspect scalar then ask for image width
            target_width = simpledialog.askfloat("Input Required", f"Enter a target width for phrase {i}:")
            aspect = aspect_scalar_incomplete * target_width

        print(f"{i}: {aspect_scalar_incomplete:.8f} * {target_width} = {aspect:.3f}")

    match name:
        case "valign":
            # Load lifts
            # Lifts determine how many pixels to shift up each respective phrase
            phrase_lift = options.get("lifts", default_lift)

            # Load shifts
            row_shift = options.get("shifts", default_shift)

            # Adjust aspect ratio further
            phrase_aspect = phrase_images[0].aspect * options.get("aspect", default_aspect)

            # Calculate width based on aspect ratio
            adjusted_height = options.get("height", default_height)
            adjusted_width = int(phrase_aspect * adjusted_height)

            # If adjusted width surpasses canvas_width, then recalculate the height
            if adjusted_width > (canvas_width - canvas_padding):
                # Readjust aspect for wider phrases
                adjusted_width = canvas_width - canvas_padding
                adjusted_height = int(adjusted_width / phrase_aspect)

            return [(((canvas_width - adjusted_width) // 2) + row_shift, 
                    ((canvas_height - adjusted_height) // 2) + phrase_lift,
                    adjusted_width,
                    adjusted_height)]

        case "valign-1-1":
            # One on top, one on bottom
            assert len(phrase_images) >= 2

            # Load skips:
            #
            # [PHRASE0]
            #   ^
            #   | 
            #  Skip0
            #   |
            #   v
            # [PHRASE1]
            #
            line_pixel_skip = options.get("skips", default_skips)[0]

            # Load lifts
            # Lifts determine how many pixels to shift up each respective phrase
            phrase1_lift = options.get("lifts", default_lifts)[0]
            phrase2_lift = options.get("lifts", default_lifts)[1]

            # Load shifts
            row1_shift = options.get("shifts", default_shifts)[0]
            row2_shift = options.get("shifts", default_shifts)[1]

            # Adjust aspect ratio further
            phrase1_aspect = phrase_images[0].aspect * options.get("aspect", default_aspect_list)[0]
            phrase2_aspect = phrase_images[1].aspect * options.get("aspect", default_aspect_list)[1]

            # Calculate width based on aspect ratio
            adjusted1_height = options.get("height", default_height_list)[0]
            adjusted2_height = options.get("height", default_height_list)[1]

            adjusted1_width = int(phrase1_aspect * adjusted1_height)
            adjusted2_width = int(phrase2_aspect * adjusted2_height)

            # Recalculate widths and heights taking into account the dimensions of multiple phrases
            total_width = max(adjusted1_width, adjusted2_width)
            total_height = adjusted1_height + line_pixel_skip + adjusted2_height

            # If total width surpasses canvas_width, then recalculate the height
            if total_width > (canvas_width - canvas_padding):
                # Readjust aspect for wider phrases
                adjusted1_width = int((canvas_width - canvas_padding) * (adjusted1_width / total_width))
                adjusted1_height = int(adjusted1_width / phrase1_aspect)

                adjusted2_width = int((canvas_width - canvas_padding) * (adjusted2_width / total_width))
                adjusted2_height = int(adjusted2_width / phrase2_aspect)

                # Recalculate the new total width and height after the above readjustment
                total_width = max(adjusted1_width, adjusted2_width)
                total_height = adjusted1_height + line_pixel_skip + adjusted2_height

            # Calculate start x and start y
            origin_x = (canvas_width - total_width) // 2
            origin_y = (canvas_height - total_height) // 2

            start1_x = origin_x + row1_shift
            start1_y = origin_y + -phrase1_lift

            origin_y += line_pixel_skip + adjusted1_height

            start2_x = origin_x + row2_shift
            start2_y = origin_y + -phrase2_lift 

            return [(start1_x, 
                    start1_y,
                    adjusted1_width,
                    adjusted1_height),
                    
                    (start2_x, 
                    start2_y,
                    adjusted2_width,
                    adjusted2_height),
            ]

        case "valign-1-1-1":
            # One on top, one on middle, one on bottom
            assert len(phrase_images) >= 3

            # Load skips:
            #
            # [PHRASE0]
            #   ^
            #   | 
            #  Skip0
            #   |
            #   v
            # [PHRASE1]
            #   ^
            #   | 
            #  Skip1
            #   |
            #   v
            # [PHRASE2]
            #
            top_line_pixel_skip = options.get("skips", default_skips)[0]
            bottom_line_pixel_skip = options.get("skips", default_skips)[1]

            # Load lifts
            # Lifts determine how many pixels to shift up each respective phrase
            phrase1_lift = options.get("lifts", default_lifts)[0]
            phrase2_lift = options.get("lifts", default_lifts)[1]
            phrase3_lift = options.get("lifts", default_lifts)[2]

            # Load shifts
            row1_shift = options.get("shifts", default_shifts)[0]
            row2_shift = options.get("shifts", default_shifts)[1]
            row3_shift = options.get("shifts", default_shifts)[2]

            # Adjust aspect ratio further
            phrase1_aspect = phrase_images[0].aspect * options.get("aspect", default_aspect_list)[0]
            phrase2_aspect = phrase_images[1].aspect * options.get("aspect", default_aspect_list)[1]
            phrase3_aspect = phrase_images[2].aspect * options.get("aspect", default_aspect_list)[2]

            # Calculate width based on aspect ratio
            adjusted1_height = options.get("height", default_height_list)[0]
            adjusted2_height = options.get("height", default_height_list)[1]
            adjusted3_height = options.get("height", default_height_list)[2]

            adjusted1_width = int(phrase1_aspect * adjusted1_height)
            adjusted2_width = int(phrase2_aspect * adjusted2_height)
            adjusted3_width = int(phrase3_aspect * adjusted3_height)

            # Recalculate widths and heights taking into account the dimensions of multiple phrases
            total_width = max(adjusted1_width, adjusted2_width, adjusted3_width)
            total_height = adjusted1_height + top_line_pixel_skip + adjusted2_height + bottom_line_pixel_skip + adjusted3_height

            # If total width surpasses canvas_width, then recalculate the height
            if total_width > (canvas_width - canvas_padding):
                # Readjust aspect for wider phrases
                adjusted1_width = int((canvas_width - canvas_padding) * (adjusted1_width / total_width))
                adjusted1_height = int(adjusted1_width / phrase1_aspect)

                adjusted2_width = int((canvas_width - canvas_padding) * (adjusted2_width / total_width))
                adjusted2_height = int(adjusted2_width / phrase2_aspect)

                adjusted3_width = int((canvas_width - canvas_padding) * (adjusted3_width / total_width))
                adjusted3_height = int(adjusted3_width / phrase3_aspect)

                # Recalculate the new total width and height after the above readjustment
                total_width = max(adjusted1_width, adjusted2_width, adjusted3_width)
                total_height = adjusted1_height + top_line_pixel_skip + adjusted2_height + bottom_line_pixel_skip + adjusted3_height

            # Calculate start x and start y
            origin_x = (canvas_width - total_width) // 2
            origin_y = (canvas_height - total_height) // 2

            start1_x = origin_x + row1_shift
            start1_y = origin_y + -phrase1_lift

            origin_y += adjusted1_height + top_line_pixel_skip

            start2_x = origin_x + row2_shift
            start2_y = origin_y + -phrase2_lift 

            origin_y += adjusted2_height + bottom_line_pixel_skip

            start3_x = origin_x + row3_shift
            start3_y = origin_y + -phrase3_lift 

            return [(start1_x, 
                    start1_y,
                    adjusted1_width,
                    adjusted1_height),
                    
                    (start2_x, 
                    start2_y,
                    adjusted2_width,
                    adjusted2_height),

                    (start3_x, 
                    start3_y,
                    adjusted3_width,
                    adjusted3_height),
            ]

        case "valign-1-2":
            # One on top, two on bottom
            assert len(phrase_images) >= 3

            # Load skips:
            #
            # [PHRASE0]
            #   ^
            #   | 
            #  Skip0
            #   |
            #   v
            # [PHRASE1] <-- Skip1 --> [PHRASE2]
            #
            line_pixel_skip = options.get("skips", default_skips)[0]
            character_pixel_skip = options.get("skips", default_skips)[1]

            # Load lifts
            # Lifts determine how many pixels to shift up each respective phrase
            phrase1_lift = options.get("lifts", default_lifts)[0]
            phrase2_lift = options.get("lifts", default_lifts)[1]
            phrase3_lift = options.get("lifts", default_lifts)[2]

            # Load shifts
            row1_shift = options.get("shifts", default_shifts)[0]
            row2_shift = options.get("shifts", default_shifts)[1]

            # Adjust aspect ratio further
            phrase1_aspect = phrase_images[0].aspect * options.get("aspect", default_aspect_list)[0]
            phrase2_aspect = phrase_images[1].aspect * options.get("aspect", default_aspect_list)[1]
            phrase3_aspect = phrase_images[2].aspect * options.get("aspect", default_aspect_list)[2]

            # Calculate width based on aspect ratio
            adjusted1_height = options.get("height", default_height_list)[0]
            adjusted2_height = options.get("height", default_height_list)[1]
            adjusted3_height = options.get("height", default_height_list)[2]

            adjusted1_width = int(phrase1_aspect * adjusted1_height)
            adjusted2_width = int(phrase2_aspect * adjusted2_height)
            adjusted3_width = int(phrase3_aspect * adjusted3_height)

            # Recalculate widths and heights taking into account the dimensions of multiple phrases
            total_width = max(adjusted1_width, adjusted2_width + character_pixel_skip + adjusted3_width)
            total_height = adjusted1_height + line_pixel_skip + max(adjusted2_height, adjusted3_height)

            # If total width surpasses canvas_width, then recalculate the height
            if total_width > (canvas_width - canvas_padding):
                # Readjust aspect for wider phrases
                adjusted1_width = int((canvas_width - canvas_padding) * (adjusted1_width / total_width))
                adjusted1_height = int(adjusted1_width / phrase1_aspect)

                adjusted2_width = int((canvas_width - canvas_padding) * (adjusted2_width / total_width))
                adjusted2_height = int(adjusted2_width / phrase2_aspect)

                adjusted3_width = int((canvas_width - canvas_padding) * (adjusted3_width / total_width))
                adjusted3_height = int(adjusted3_width / phrase3_aspect)

                # Recalculate the new total width and height after the above readjustment
                total_width = max(adjusted1_width, adjusted2_width + character_pixel_skip + adjusted3_width)
                total_height = adjusted1_height + line_pixel_skip + max(adjusted2_height, adjusted3_height)

            # Calculate start x and start y
            origin_x = (canvas_width - total_width) // 2
            origin_y = (canvas_height - total_height) // 2

            max_bottom_line_height = max(adjusted2_height, adjusted3_height)

            start1_x = origin_x + row1_shift
            start1_y = origin_y + -phrase1_lift

            origin_y += line_pixel_skip + adjusted1_height

            start2_x = origin_x + row2_shift
            start2_y = origin_y + -phrase2_lift + (max_bottom_line_height - adjusted2_height)

            start3_x = origin_x + row2_shift + adjusted2_width + character_pixel_skip
            start3_y = origin_y + -phrase3_lift + (max_bottom_line_height - adjusted3_height)

            return [(start1_x, 
                    start1_y,
                    adjusted1_width,
                    adjusted1_height),
                    
                    (start2_x, 
                    start2_y,
                    adjusted2_width,
                    adjusted2_height),

                    (start3_x, 
                    start3_y,
                    adjusted3_width,
                    adjusted3_height),
            ]

        case "valign-1-3":
            # One on top, three on bottom
            assert len(phrase_images) >= 4

            # Load skips:
            #
            # [PHRASE0]
            #   ^
            #   | 
            #  Skip0
            #   |
            #   v
            # [PHRASE1] <-- Skip1 --> [PHRASE2] <-- Skip2 --> [PHRASE3]
            #
            line_pixel_skip = options.get("skips", default_skips)[0]
            left_character_pixel_skip = options.get("skips", default_skips)[1]
            right_character_pixel_skip = options.get("skips", default_skips)[2]

            # Load lifts
            # Lifts determine how many pixels to shift up each respective phrase
            phrase1_lift = options.get("lifts", default_lifts)[0]
            phrase2_lift = options.get("lifts", default_lifts)[1]
            phrase3_lift = options.get("lifts", default_lifts)[2]
            phrase4_lift = options.get("lifts", default_lifts)[3]

            # Load shifts
            row1_shift = options.get("shifts", default_shifts)[0]
            row2_shift = options.get("shifts", default_shifts)[1]

            # Adjust aspect ratio further
            phrase1_aspect = phrase_images[0].aspect * options.get("aspect", default_aspect_list)[0]
            phrase2_aspect = phrase_images[1].aspect * options.get("aspect", default_aspect_list)[1]
            phrase3_aspect = phrase_images[2].aspect * options.get("aspect", default_aspect_list)[2]
            phrase4_aspect = phrase_images[3].aspect * options.get("aspect", default_aspect_list)[3]

            # Calculate width based on aspect ratio
            adjusted1_height = options.get("height", default_height_list)[0]
            adjusted2_height = options.get("height", default_height_list)[1]
            adjusted3_height = options.get("height", default_height_list)[2]
            adjusted4_height = options.get("height", default_height_list)[3]

            adjusted1_width = int(phrase1_aspect * adjusted1_height)
            adjusted2_width = int(phrase2_aspect * adjusted2_height)
            adjusted3_width = int(phrase3_aspect * adjusted3_height)
            adjusted4_width = int(phrase4_aspect * adjusted4_height)

            # Recalculate widths and heights taking into account the dimensions of multiple phrases
            total_width = max(adjusted1_width, adjusted2_width + left_character_pixel_skip + adjusted3_width + right_character_pixel_skip + adjusted4_width)
            total_height = adjusted1_height + line_pixel_skip + max(adjusted2_height, adjusted3_height, adjusted4_height)

            # If total width surpasses canvas_width, then recalculate the height
            if total_width > (canvas_width - canvas_padding):
                # Readjust aspect for wider phrases
                adjusted1_width = int((canvas_width - canvas_padding) * (adjusted1_width / total_width))
                adjusted1_height = int(adjusted1_width / phrase1_aspect)

                adjusted2_width = int((canvas_width - canvas_padding) * (adjusted2_width / total_width))
                adjusted2_height = int(adjusted2_width / phrase2_aspect)

                adjusted3_width = int((canvas_width - canvas_padding) * (adjusted3_width / total_width))
                adjusted3_height = int(adjusted3_width / phrase3_aspect)

                adjusted4_width = int((canvas_width - canvas_padding) * (adjusted4_width / total_width))
                adjusted4_height = int(adjusted4_width / phrase4_aspect)

                # Recalculate widths and heights taking into account the dimensions of multiple phrases
                total_width = max(adjusted1_width, adjusted2_width + left_character_pixel_skip + adjusted3_width + right_character_pixel_skip + adjusted4_width)
                total_height = adjusted1_height + line_pixel_skip + max(adjusted2_height, adjusted3_height, adjusted4_height)

            # Calculate start x and start y
            origin_x = (canvas_width - total_width) // 2
            origin_y = (canvas_height - total_height) // 2

            max_bottom_line_height = max(adjusted2_height, adjusted3_height, adjusted4_height)

            start1_x = origin_x + row1_shift
            start1_y = origin_y + -phrase1_lift

            origin_y += line_pixel_skip + adjusted1_height

            start2_x = origin_x + row2_shift
            start2_y = origin_y + -phrase2_lift + (max_bottom_line_height - adjusted2_height)

            start3_x = origin_x + row2_shift + adjusted2_width + left_character_pixel_skip
            start3_y = origin_y + -phrase3_lift + (max_bottom_line_height - adjusted3_height)

            start4_x = origin_x + row2_shift + adjusted2_width + left_character_pixel_skip + adjusted3_width + right_character_pixel_skip
            start4_y = origin_y + -phrase4_lift + (max_bottom_line_height - adjusted4_height)

            return [(start1_x, 
                    start1_y,
                    adjusted1_width,
                    adjusted1_height),
                    
                    (start2_x, 
                    start2_y,
                    adjusted2_width,
                    adjusted2_height),

                    (start3_x, 
                    start3_y,
                    adjusted3_width,
                    adjusted3_height),

                    (start4_x, 
                    start4_y,
                    adjusted4_width,
                    adjusted4_height),
            ]

        case "valign-2":
            # Two on center line
            assert len(phrase_images) >= 2

            # Load skips:
            #
            # [PHRASE0] <-- Skip0 --> [PHRASE1]
            #
            
            character_pixel_skip = options.get("skips", default_skips)[0]

            # Load lifts
            # Lifts determine how many pixels to shift up each respective phrase
            phrase1_lift = options.get("lifts", default_lifts)[0]
            phrase2_lift = options.get("lifts", default_lifts)[1]

            # Load shifts
            row1_shift = options.get("shifts", default_shifts)[0]

            # Adjust aspect ratio further
            phrase1_aspect = phrase_images[0].aspect * options.get("aspect", default_aspect_list)[0]
            phrase2_aspect = phrase_images[1].aspect * options.get("aspect", default_aspect_list)[1]

            # Calculate width based on aspect ratio
            adjusted1_height = options.get("height", default_height_list)[0]
            adjusted2_height = options.get("height", default_height_list)[1]

            adjusted1_width = int(phrase1_aspect * adjusted1_height)
            adjusted2_width = int(phrase2_aspect * adjusted2_height)

            # Recalculate widths and heights taking into account the dimensions of multiple phrases
            total_width = adjusted1_width + character_pixel_skip + adjusted2_width 
            total_height = max(adjusted1_height, adjusted2_height)

            # If total width surpasses canvas_width, then recalculate the height
            if total_width > (canvas_width - canvas_padding):
                # Readjust aspect for wider phrases
                adjusted1_width = int((canvas_width - canvas_padding) * (adjusted1_width / total_width))
                adjusted1_height = int(adjusted1_width / phrase1_aspect)

                adjusted2_width = int((canvas_width - canvas_padding) * (adjusted2_width / total_width))
                adjusted2_height = int(adjusted2_width / phrase2_aspect)

                # Recalculate the new total width and height after the above readjustment
                total_width = adjusted1_width + character_pixel_skip + adjusted2_width
                total_height = max(adjusted1_height, adjusted2_height)

            # Calculate start x and start y
            origin_x = (canvas_width - total_width) // 2
            origin_y = (canvas_height - total_height) // 2

            max_line_height = total_height

            start1_x = origin_x + row1_shift
            start1_y = origin_y + -phrase1_lift + (max_line_height - adjusted1_height)

            start2_x = origin_x + row1_shift + adjusted1_width + character_pixel_skip
            start2_y = origin_y + -phrase2_lift + (max_line_height - adjusted2_height)

            return [(start1_x, 
                    start1_y,
                    adjusted1_width,
                    adjusted1_height),
                    
                    (start2_x, 
                    start2_y,
                    adjusted2_width,
                    adjusted2_height),
            ]

        case "valign-2-1":
            # Two on top, on on bottom
            assert len(phrase_images) >= 3

            # Load skips:
            #
            # [PHRASE0] <-- Skip0 --> [PHRASE1]
            #   ^
            #   | 
            #  Skip1
            #   |
            #   v
            # [PHRASE2]
            #
            
            top_character_pixel_skip = options.get("skips", default_skips)[0]
            line_pixel_skip = options.get("skips", default_skips)[1]
            
            # Load lifts
            # Lifts determine how many pixels to shift up each respective phrase
            phrase1_lift = options.get("lifts", default_lifts)[0]
            phrase2_lift = options.get("lifts", default_lifts)[1]
            phrase3_lift = options.get("lifts", default_lifts)[2]

            # Load shifts
            row1_shift = options.get("shifts", default_shifts)[0]
            row2_shift = options.get("shifts", default_shifts)[1]

            # Adjust aspect ratio further
            phrase1_aspect = phrase_images[0].aspect * options.get("aspect", default_aspect_list)[0]
            phrase2_aspect = phrase_images[1].aspect * options.get("aspect", default_aspect_list)[1]
            phrase3_aspect = phrase_images[2].aspect * options.get("aspect", default_aspect_list)[2]

            # Calculate width based on aspect ratio
            adjusted1_height = options.get("height", default_height_list)[0]
            adjusted2_height = options.get("height", default_height_list)[1]
            adjusted3_height = options.get("height", default_height_list)[2]

            adjusted1_width = int(phrase1_aspect * adjusted1_height)
            adjusted2_width = int(phrase2_aspect * adjusted2_height)
            adjusted3_width = int(phrase3_aspect * adjusted3_height)

            # Recalculate widths and heights taking into account the dimensions of multiple phrases
            total_width = max(adjusted1_width + top_character_pixel_skip + adjusted2_width, 
                              adjusted3_width)
            total_height = max(adjusted1_height, adjusted2_height) + line_pixel_skip + adjusted3_height

            # If total width surpasses canvas_width, then recalculate the height
            if total_width > (canvas_width - canvas_padding):
                # Readjust aspect for wider phrases
                adjusted1_width = int((canvas_width - canvas_padding) * (adjusted1_width / total_width))
                adjusted1_height = int(adjusted1_width / phrase1_aspect)

                adjusted2_width = int((canvas_width - canvas_padding) * (adjusted2_width / total_width))
                adjusted2_height = int(adjusted2_width / phrase2_aspect)

                adjusted3_width = int((canvas_width - canvas_padding) * (adjusted3_width / total_width))
                adjusted3_height = int(adjusted3_width / phrase3_aspect)

                # Recalculate widths and heights taking into account the dimensions of multiple phrases
                total_width = max(adjusted1_width + top_character_pixel_skip + adjusted2_width, 
                                  adjusted3_width)
                total_height = max(adjusted1_height, adjusted2_height) + line_pixel_skip + adjusted3_height

            # Calculate start x and start y
            origin_x = (canvas_width - total_width) // 2
            origin_y = (canvas_height - total_height) // 2

            max_top_line_height = max(adjusted1_height, adjusted2_height)
            max_bottom_line_height = adjusted3_height

            start1_x = origin_x + row1_shift
            start1_y = origin_y + -phrase1_lift + (max_top_line_height - adjusted1_height)

            start2_x = origin_x + row1_shift + adjusted1_width + top_character_pixel_skip
            start2_y = origin_y + -phrase2_lift + (max_top_line_height - adjusted2_height)

            origin_y += line_pixel_skip + adjusted1_height

            start3_x = origin_x + row2_shift
            start3_y = origin_y + -phrase3_lift + (max_bottom_line_height - adjusted3_height)

            return [(start1_x, 
                    start1_y,
                    adjusted1_width,
                    adjusted1_height),
                    
                    (start2_x, 
                    start2_y,
                    adjusted2_width,
                    adjusted2_height),

                    (start3_x, 
                    start3_y,
                    adjusted3_width,
                    adjusted3_height),
            ]

        case "valign-2-2":
            # Two on top, two on bottom
            assert len(phrase_images) >= 4

            # Load skips:
            #
            # [PHRASE0] <-- Skip0 --> [PHRASE1]
            #   ^
            #   | 
            #  Skip1
            #   |
            #   v
            # [PHRASE2] <-- Skip2 --> [PHRASE3]
            #
            
            top_character_pixel_skip = options.get("skips", default_skips)[0]
            line_pixel_skip = options.get("skips", default_skips)[1]
            bottom_character_pixel_skip = options.get("skips", default_skips)[2]
            
            # Load lifts
            # Lifts determine how many pixels to shift up each respective phrase
            phrase1_lift = options.get("lifts", default_lifts)[0]
            phrase2_lift = options.get("lifts", default_lifts)[1]
            phrase3_lift = options.get("lifts", default_lifts)[2]
            phrase4_lift = options.get("lifts", default_lifts)[3]

            # Load shifts
            row1_shift = options.get("shifts", default_shifts)[0]
            row2_shift = options.get("shifts", default_shifts)[1]

            # Adjust aspect ratio further
            phrase1_aspect = phrase_images[0].aspect * options.get("aspect", default_aspect_list)[0]
            phrase2_aspect = phrase_images[1].aspect * options.get("aspect", default_aspect_list)[1]
            phrase3_aspect = phrase_images[2].aspect * options.get("aspect", default_aspect_list)[2]
            phrase4_aspect = phrase_images[3].aspect * options.get("aspect", default_aspect_list)[3]

            # Calculate width based on aspect ratio
            adjusted1_height = options.get("height", default_height_list)[0]
            adjusted2_height = options.get("height", default_height_list)[1]
            adjusted3_height = options.get("height", default_height_list)[2]
            adjusted4_height = options.get("height", default_height_list)[3]

            adjusted1_width = int(phrase1_aspect * adjusted1_height)
            adjusted2_width = int(phrase2_aspect * adjusted2_height)
            adjusted3_width = int(phrase3_aspect * adjusted3_height)
            adjusted4_width = int(phrase4_aspect * adjusted4_height)

            # Recalculate widths and heights taking into account the dimensions of multiple phrases
            total_width = max(adjusted1_width + top_character_pixel_skip + adjusted2_width, 
                              adjusted3_width + bottom_character_pixel_skip + adjusted4_width)
            total_height = max(adjusted1_height, adjusted2_height) + line_pixel_skip + max(adjusted3_height, adjusted4_height)

            # If total width surpasses canvas_width, then recalculate the height
            if total_width > (canvas_width - canvas_padding):
                # Readjust aspect for wider phrases
                adjusted1_width = int((canvas_width - canvas_padding) * (adjusted1_width / total_width))
                adjusted1_height = int(adjusted1_width / phrase1_aspect)

                adjusted2_width = int((canvas_width - canvas_padding) * (adjusted2_width / total_width))
                adjusted2_height = int(adjusted2_width / phrase2_aspect)

                adjusted3_width = int((canvas_width - canvas_padding) * (adjusted3_width / total_width))
                adjusted3_height = int(adjusted3_width / phrase3_aspect)

                adjusted4_width = int((canvas_width - canvas_padding) * (adjusted4_width / total_width))
                adjusted4_height = int(adjusted4_width / phrase4_aspect)

                # Recalculate the new total width and height after the above readjustment
                total_width = max(adjusted1_width + top_character_pixel_skip + adjusted2_width, 
                                  adjusted3_width + bottom_character_pixel_skip + adjusted4_width)
                total_height = max(adjusted1_height, adjusted2_height) + line_pixel_skip + max(adjusted3_height, adjusted4_height)

            # Calculate start x and start y
            origin_x = (canvas_width - total_width) // 2
            origin_y = (canvas_height - total_height) // 2

            max_top_line_height = max(adjusted1_height, adjusted2_height)
            max_bottom_line_height = max(adjusted3_height, adjusted4_height)

            start1_x = origin_x + row1_shift
            start1_y = origin_y + -phrase1_lift + (max_top_line_height - adjusted1_height)

            start2_x = origin_x + row1_shift + adjusted1_width + top_character_pixel_skip
            start2_y = origin_y + -phrase2_lift + (max_top_line_height - adjusted2_height)

            origin_y += line_pixel_skip + adjusted1_height

            start3_x = origin_x + row2_shift
            start3_y = origin_y + -phrase3_lift + (max_bottom_line_height - adjusted3_height)

            start4_x = origin_x + row2_shift + adjusted3_width + bottom_character_pixel_skip
            start4_y = origin_y + -phrase4_lift + (max_bottom_line_height - adjusted4_height)

            return [(start1_x, 
                    start1_y,
                    adjusted1_width,
                    adjusted1_height),
                    
                    (start2_x, 
                    start2_y,
                    adjusted2_width,
                    adjusted2_height),

                    (start3_x, 
                    start3_y,
                    adjusted3_width,
                    adjusted3_height),

                    (start4_x, 
                    start4_y,
                    adjusted4_width,
                    adjusted4_height),
            ]

        case "valign-2-3":
            # Two on top, three on bottom
            assert len(phrase_images) >= 5

            # Load skips:
            #
            # [PHRASE0] <-- Skip0 --> [PHRASE1]
            #   ^
            #   | 
            #  Skip1
            #   |
            #   v
            # [PHRASE2] <-- Skip2 --> [PHRASE3] <-- Skip3 --> [PHRASE4]
            #
            
            top_character_pixel_skip = options.get("skips", default_skips)[0]
            line_pixel_skip = options.get("skips", default_skips)[1]
            bottom_left_character_pixel_skip = options.get("skips", default_skips)[2]
            bottom_right_character_pixel_skip = options.get("skips", default_skips)[3]
            
            # Load lifts
            # Lifts determine how many pixels to shift up each respective phrase
            phrase1_lift = options.get("lifts", default_lifts)[0]
            phrase2_lift = options.get("lifts", default_lifts)[1]
            phrase3_lift = options.get("lifts", default_lifts)[2]
            phrase4_lift = options.get("lifts", default_lifts)[3]
            phrase5_lift = options.get("lifts", default_lifts)[4]

            # Load shifts
            row1_shift = options.get("shifts", default_shifts)[0]
            row2_shift = options.get("shifts", default_shifts)[1]

            # Adjust aspect ratio further
            phrase1_aspect = phrase_images[0].aspect * options.get("aspect", default_aspect_list)[0]
            phrase2_aspect = phrase_images[1].aspect * options.get("aspect", default_aspect_list)[1]
            phrase3_aspect = phrase_images[2].aspect * options.get("aspect", default_aspect_list)[2]
            phrase4_aspect = phrase_images[3].aspect * options.get("aspect", default_aspect_list)[3]
            phrase5_aspect = phrase_images[4].aspect * options.get("aspect", default_aspect_list)[4]

            # Calculate width based on aspect ratio
            adjusted1_height = options.get("height", default_height_list)[0]
            adjusted2_height = options.get("height", default_height_list)[1]
            adjusted3_height = options.get("height", default_height_list)[2]
            adjusted4_height = options.get("height", default_height_list)[3]
            adjusted5_height = options.get("height", default_height_list)[4]

            adjusted1_width = int(phrase1_aspect * adjusted1_height)
            adjusted2_width = int(phrase2_aspect * adjusted2_height)
            adjusted3_width = int(phrase3_aspect * adjusted3_height)
            adjusted4_width = int(phrase4_aspect * adjusted4_height)
            adjusted5_width = int(phrase5_aspect * adjusted5_height)

            # Recalculate widths and heights taking into account the dimensions of multiple phrases
            total_width = max(adjusted1_width + top_character_pixel_skip + adjusted2_width, 
                              adjusted3_width + bottom_left_character_pixel_skip + adjusted4_width + bottom_right_character_pixel_skip + adjusted5_width)
            total_height = max(adjusted1_height, adjusted2_height) + line_pixel_skip + max(adjusted3_height, adjusted4_height, adjusted5_height)

            # If total width surpasses canvas_width, then recalculate the height
            if total_width > (canvas_width - canvas_padding):
                # Readjust aspect for wider phrases
                adjusted1_width = int((canvas_width - canvas_padding) * (adjusted1_width / total_width))
                adjusted1_height = int(adjusted1_width / phrase1_aspect)

                adjusted2_width = int((canvas_width - canvas_padding) * (adjusted2_width / total_width))
                adjusted2_height = int(adjusted2_width / phrase2_aspect)

                adjusted3_width = int((canvas_width - canvas_padding) * (adjusted3_width / total_width))
                adjusted3_height = int(adjusted3_width / phrase3_aspect)

                adjusted4_width = int((canvas_width - canvas_padding) * (adjusted4_width / total_width))
                adjusted4_height = int(adjusted4_width / phrase4_aspect)

                adjusted5_width = int((canvas_width - canvas_padding) * (adjusted5_width / total_width))
                adjusted5_height = int(adjusted5_width / phrase5_aspect)

                # Recalculate widths and heights taking into account the dimensions of multiple phrases
                total_width = max(adjusted1_width + top_character_pixel_skip + adjusted2_width, 
                                  adjusted3_width + bottom_left_character_pixel_skip + adjusted4_width + bottom_right_character_pixel_skip + adjusted5_width)
                total_height = max(adjusted1_height, adjusted2_height) + line_pixel_skip + max(adjusted3_height, adjusted4_height, adjusted5_height)

            # Calculate start x and start y
            origin_x = (canvas_width - total_width) // 2
            origin_y = (canvas_height - total_height) // 2

            max_top_line_height = max(adjusted1_height, adjusted2_height)
            max_bottom_line_height = max(adjusted3_height, adjusted4_height, adjusted5_height)

            start1_x = origin_x + row1_shift
            start1_y = origin_y + -phrase1_lift + (max_top_line_height - adjusted1_height)

            start2_x = origin_x + row1_shift + adjusted1_width + top_character_pixel_skip
            start2_y = origin_y + -phrase2_lift + (max_top_line_height - adjusted2_height)

            origin_y += line_pixel_skip + adjusted1_height

            start3_x = origin_x + row2_shift
            start3_y = origin_y + -phrase3_lift + (max_bottom_line_height - adjusted3_height)

            start4_x = origin_x + row2_shift + adjusted3_width + bottom_left_character_pixel_skip
            start4_y = origin_y + -phrase4_lift + (max_bottom_line_height - adjusted4_height)

            start5_x = origin_x + row2_shift + adjusted3_width + bottom_left_character_pixel_skip + adjusted4_width + bottom_right_character_pixel_skip
            start5_y = origin_y + -phrase5_lift + (max_bottom_line_height - adjusted5_height)

            return [(start1_x, 
                    start1_y,
                    adjusted1_width,
                    adjusted1_height),
                    
                    (start2_x, 
                    start2_y,
                    adjusted2_width,
                    adjusted2_height),

                    (start3_x, 
                    start3_y,
                    adjusted3_width,
                    adjusted3_height),

                    (start4_x, 
                    start4_y,
                    adjusted4_width,
                    adjusted4_height),

                    (start5_x, 
                    start5_y,
                    adjusted5_width,
                    adjusted5_height),
            ]

        case "valign-3":
            # Three on center line
            assert len(phrase_images) >= 3

            # Load skips:
            #
            # [PHRASE0] <-- Skip0 --> [PHRASE1] <-- Skip1 --> [PHRASE2]
            #
            
            left_character_pixel_skip = options.get("skips", default_skips)[0]
            right_character_pixel_skip = options.get("skips", default_skips)[1]
            
            # Load lifts
            # Lifts determine how many pixels to shift up each respective phrase
            phrase1_lift = options.get("lifts", default_lifts)[0]
            phrase2_lift = options.get("lifts", default_lifts)[1]
            phrase3_lift = options.get("lifts", default_lifts)[2]

            # Load shifts
            row1_shift = options.get("shifts", default_shifts)[0]

            # Adjust aspect ratio further
            phrase1_aspect = phrase_images[0].aspect * options.get("aspect", default_aspect_list)[0]
            phrase2_aspect = phrase_images[1].aspect * options.get("aspect", default_aspect_list)[1]
            phrase3_aspect = phrase_images[2].aspect * options.get("aspect", default_aspect_list)[2]

            # Calculate width based on aspect ratio
            adjusted1_height = options.get("height", default_height_list)[0]
            adjusted2_height = options.get("height", default_height_list)[1]
            adjusted3_height = options.get("height", default_height_list)[2]

            adjusted1_width = int(phrase1_aspect * adjusted1_height)
            adjusted2_width = int(phrase2_aspect * adjusted2_height)
            adjusted3_width = int(phrase3_aspect * adjusted3_height)

            # Recalculate widths and heights taking into account the dimensions of multiple phrases
            total_width = adjusted1_width + left_character_pixel_skip + adjusted2_width + right_character_pixel_skip + adjusted3_width
            total_height = max(adjusted1_height, adjusted2_height, adjusted3_height)

            # If total width surpasses canvas_width, then recalculate the height
            if total_width > (canvas_width - canvas_padding):
                # Readjust aspect for wider phrases
                adjusted1_width = int((canvas_width - canvas_padding) * (adjusted1_width / total_width))
                adjusted1_height = int(adjusted1_width / phrase1_aspect)

                adjusted2_width = int((canvas_width - canvas_padding) * (adjusted2_width / total_width))
                adjusted2_height = int(adjusted2_width / phrase2_aspect)

                adjusted3_width = int((canvas_width - canvas_padding) * (adjusted3_width / total_width))
                adjusted3_height = int(adjusted3_width / phrase3_aspect)

                # Recalculate the new total width and height after the above readjustment
                total_width = adjusted1_width + left_character_pixel_skip + adjusted2_width + right_character_pixel_skip + adjusted3_width
                total_height = max(adjusted1_height, adjusted2_height, adjusted3_height)

            # Calculate start x and start y
            origin_x = (canvas_width - total_width) // 2
            origin_y = (canvas_height - total_height) // 2

            max_line_height = total_height

            start1_x = origin_x + row1_shift
            start1_y = origin_y + -phrase1_lift + (max_line_height - adjusted1_height)

            start2_x = origin_x + row1_shift + adjusted1_width + left_character_pixel_skip
            start2_y = origin_y + -phrase2_lift + (max_line_height - adjusted2_height)

            start3_x = origin_x + row1_shift + adjusted1_width + left_character_pixel_skip + adjusted2_width + right_character_pixel_skip
            start3_y = origin_y + -phrase3_lift + (max_line_height - adjusted3_height)

            return [(start1_x, 
                    start1_y,
                    adjusted1_width,
                    adjusted1_height),
                    
                    (start2_x, 
                    start2_y,
                    adjusted2_width,
                    adjusted2_height),

                    (start3_x, 
                    start3_y,
                    adjusted3_width,
                    adjusted3_height),
            ]

        case "valign-3-1":
            # Three on top, one on bottom
            assert len(phrase_images) >= 4

            # Load skips:
            #
            # [PHRASE0] <-- Skip0 --> [PHRASE1] <-- Skip1 --> [PHRASE2]
            #   ^
            #   | 
            #  Skip2
            #   |
            #   v
            # [PHRASE3]
            #
            
            left_character_pixel_skip = options.get("skips", default_skips)[0]
            right_character_pixel_skip = options.get("skips", default_skips)[1]
            line_pixel_skip = options.get("skips", default_skips)[2]
            
            # Load lifts
            # Lifts determine how many pixels to shift up each respective phrase
            phrase1_lift = options.get("lifts", default_lifts)[0]
            phrase2_lift = options.get("lifts", default_lifts)[1]
            phrase3_lift = options.get("lifts", default_lifts)[2]
            phrase4_lift = options.get("lifts", default_lifts)[3]

            # Load shifts
            row1_shift = options.get("shifts", default_shifts)[0]
            row2_shift = options.get("shifts", default_shifts)[1]

            # Adjust aspect ratio further
            phrase1_aspect = phrase_images[0].aspect * options.get("aspect", default_aspect_list)[0]
            phrase2_aspect = phrase_images[1].aspect * options.get("aspect", default_aspect_list)[1]
            phrase3_aspect = phrase_images[2].aspect * options.get("aspect", default_aspect_list)[2]
            phrase4_aspect = phrase_images[3].aspect * options.get("aspect", default_aspect_list)[3]

            # Calculate width based on aspect ratio
            adjusted1_height = options.get("height", default_height_list)[0]
            adjusted2_height = options.get("height", default_height_list)[1]
            adjusted3_height = options.get("height", default_height_list)[2]
            adjusted4_height = options.get("height", default_height_list)[3]

            adjusted1_width = int(phrase1_aspect * adjusted1_height)
            adjusted2_width = int(phrase2_aspect * adjusted2_height)
            adjusted3_width = int(phrase3_aspect * adjusted3_height)
            adjusted4_width = int(phrase4_aspect * adjusted4_height)

            # Recalculate widths and heights taking into account the dimensions of multiple phrases
            total_width = max(adjusted1_width + left_character_pixel_skip + adjusted2_width + right_character_pixel_skip + adjusted3_width,
                              adjusted4_width)
            total_height = max(adjusted1_height, adjusted2_height, adjusted3_height) + line_pixel_skip + adjusted4_height

            # If total width surpasses canvas_width, then recalculate the height
            if total_width > (canvas_width - canvas_padding):
                # Readjust aspect for wider phrases
                adjusted1_width = int((canvas_width - canvas_padding) * (adjusted1_width / total_width))
                adjusted1_height = int(adjusted1_width / phrase1_aspect)

                adjusted2_width = int((canvas_width - canvas_padding) * (adjusted2_width / total_width))
                adjusted2_height = int(adjusted2_width / phrase2_aspect)

                adjusted3_width = int((canvas_width - canvas_padding) * (adjusted3_width / total_width))
                adjusted3_height = int(adjusted3_width / phrase3_aspect)

                adjusted4_width = int((canvas_width - canvas_padding) * (adjusted4_width / total_width))
                adjusted4_height = int(adjusted4_width / phrase4_aspect)

                # Recalculate the new total width and height after the above readjustment
                total_width = max(adjusted1_width + left_character_pixel_skip + adjusted2_width + right_character_pixel_skip + adjusted3_width,
                                  adjusted4_width)
                total_height = max(adjusted1_height, adjusted2_height, adjusted3_height) + line_pixel_skip + adjusted4_height

            # Calculate start x and start y
            origin_x = (canvas_width - total_width) // 2
            origin_y = (canvas_height - total_height) // 2

            max_top_line_height = max(adjusted1_height, adjusted2_height, adjusted3_height)
            max_bottom_line_height = adjusted4_height

            start1_x = origin_x + row1_shift
            start1_y = origin_y + -phrase1_lift + (max_top_line_height - adjusted1_height)

            start2_x = origin_x + row1_shift + adjusted1_width + left_character_pixel_skip
            start2_y = origin_y + -phrase2_lift + (max_top_line_height - adjusted2_height)

            start3_x = origin_x + row1_shift + adjusted1_width + left_character_pixel_skip + adjusted2_width + right_character_pixel_skip
            start3_y = origin_y + -phrase3_lift + (max_top_line_height - adjusted3_height)

            origin_y += line_pixel_skip + adjusted1_height

            start4_x = origin_x + row2_shift
            start4_y = origin_y + -phrase4_lift + (max_bottom_line_height - adjusted4_height)

            return [(start1_x, 
                    start1_y,
                    adjusted1_width,
                    adjusted1_height),
                    
                    (start2_x, 
                    start2_y,
                    adjusted2_width,
                    adjusted2_height),

                    (start3_x, 
                    start3_y,
                    adjusted3_width,
                    adjusted3_height),

                    (start4_x, 
                    start4_y,
                    adjusted4_width,
                    adjusted4_height),
            ]

if __name__ == '__main__':
    main()
