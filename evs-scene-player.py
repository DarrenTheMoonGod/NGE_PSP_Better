#!/usr/bin/env python3

import os
import sys
import tkinter as tk
import time
import threading

from tkinter import filedialog
from pathlib import Path
from PIL import Image as PILImage, ImageTk

sys.path.append(os.path.abspath("tools"))
import evs

PSP_SCREEN_WIDTH = 480
PSP_SCREEN_HEIGHT = 272

# Directory containing the ISO image that's been extracted to a folder
# and then had tools/unpack-all.py run on it
UNPACKED_DIRECTORY_NAME = "unpacked.unmodified"

# Name of EVS to view
# They're located in UNPACKED_DIRECTORY_NAME / "PSP_GAME" / "USRDIR" / "event" 
EVS_NAME = "cev0109"

eva_dir = Path(UNPACKED_DIRECTORY_NAME)

def best_fit_path(path):
    # HGAR files have an extra id that gets exported in the file name
    # that some lookup methods don't use
    # So this function will look up a path and use the best match
    if '*' not in str(path):
        return path

    print(path)
    return next(Path().glob(str(path)), None)

def Image(path):
    try:
        return ImageTk.PhotoImage(PILImage.open(path))

    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None

class Window:
    def __init__(self, title, width, height):
        self.root = tk.Tk()
        self.root.title(title)

        self.canvas = tk.Canvas(self.root, width=width, height=height, bg='white')
        self.canvas.pack()

        self.layers = {}

    def display_image(self, layer_name, image, x, y):
        if image is None:
            print("Error: Invalid image")
            return

        if layer_name in self.layers:
            self.layers[layer_name] = (self.layers[layer_name][0], image)
            self.canvas.itemconfig(self.layers[layer_name][0], image=image)

        else:
            # We store the layer as an (id, image) because otherwise python will garbage collect it
            self.layers[layer_name] = (self.canvas.create_image(x, y, image=image, anchor='nw'), image)

    def draw_char(self, char, x, y, font_name="MS Gothic", font_size=10, color="white", tag=None):
        text_id = self.canvas.create_text(
            x, y,
            text=char,
            font=(font_name, font_size),
            fill=color,
            anchor='nw',  # Top-left anchor
            tags=tag
        )

    def clear_char(self, tag):
        self.canvas.delete(tag)

    def clear(self):
        self.canvas.delete("all")
        self.layers = {}

    def run(self):
        self.root.mainloop()

class EvangelionScriptingEngine:
    def __init__(self, window):
        global EVS_NAME

        self.window = window

        self.evs_workdir = eva_dir / "PSP_GAME" / "USRDIR" / "event" / f"{EVS_NAME}.har.HGARPACK"

        self.evs_wrapper = evs.EvsWrapper()
        self.evs_wrapper.import_evs(best_fit_path(self.evs_workdir / f"{EVS_NAME}#*.evs.EVS.json"))

        path = eva_dir / "PSP_GAME" / "USRDIR" / "game" / "system.har.HGARPACK" / "sys09#id38.hpt.DECOMPRESSED.PICTURE.png"
        self.dialog_box_image = Image(path)

    def run(self):
        for entry in self.evs_wrapper.entries:
            print(entry) 

            function = entry[0]
            params = entry[1]
            content = entry[2]

            match function:
                case 1:
                    # Say
                    if params[0] == 0 or (params[1] & evs.FUNCTION_SAY_FLAG_PARAMS["NO_AVATAR"]):
                        continue

                    else:
                        # Load face
                        path = eva_dir / "PSP_GAME" / "USRDIR" / "face" / f"f{params[0]:02d}_{params[1]:02d}.har.HGARPACK" / f"f{params[0]:02d}_{params[1]:02d}_1#id15.hpt.DECOMPRESSED.PICTURE.png"

                        if not path.exists():
                            continue

                        img = Image(path)
                        if not img:
                            continue

                        # Draw speaker
                        self.window.display_image('face', img, -32, 0)
                    
                    # Draw dialog text
                    self.window.display_image('dialog_box', self.dialog_box_image, 0, PSP_SCREEN_HEIGHT - 57)
                    self.window.clear_char("dialog")

                    start_y = 220
                    start_x = 152
                    char_width = 18
                    char_height = 16
                    new_page_char = "▽"

                    y = start_y
                    x = start_x

                    for line in content.split("\n"):
                        for ch in line:
                            self.window.draw_char(ch, x, y, tag="dialog")
                            x += char_width
                            time.sleep(0.1)

                            if ch == new_page_char:
                                # Sleep a bit more
                                time.sleep(0.5)

                                # Then clear and reset
                                self.window.clear_char("dialog")
                                y = start_y - char_height # Subtract a line to cancel out the unnecessary linebreak's affect after the new_page_char
                                x = start_x

                        y += char_height
                        x = start_x

                    time.sleep(1)

                case 140:
                    # Load Background
                    if content == "":
                        # Blank
                        continue

                    path = best_fit_path(self.evs_workdir / f"{content.replace('.', '#*.')}.DECOMPRESSED.PICTURE.png")

                    if not path.exists():
                        print(f"Error: Could not load background image: {path}")
                        continue

                    img = Image(path)
                    if not img:
                        continue

                    self.window.display_image('background', img, 0, 0)

                case 144:
                    # Wait
                    time.sleep(params[0]/1000.0)

if __name__ == "__main__":

    window = Window("Evangelion Another Cases EVS Scene Player", PSP_SCREEN_WIDTH, PSP_SCREEN_HEIGHT)

    script_engine = EvangelionScriptingEngine(window)

    thread = threading.Thread(target=script_engine.run, daemon=True)
    thread.start()

    window.run()

    sys.exit(0)
