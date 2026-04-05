import os
import subprocess
import sys
import shutil

def run_command(command, description):
    """Run a subprocess command with error handling."""
    try:
        print(f"\n--- Running {description} ---")
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running {description}: {e}")
        sys.exit(1)

def main():
    print("=== File Injection Tool ===")

    # --- User inputs ---
    png_file = input("Enter the path of the PNG file to inject: ").strip()
    if not os.path.isfile(png_file) or not png_file.lower().endswith(".png"):
        print("Error: The input file must be a .png")
        return

    har_file = input("Enter the path of the base HAR file: ").strip()
    if not os.path.isfile(har_file) or not har_file.lower().endswith(".har"):
        print("Error: The base file must be a .har")
        return

    print("\n--- Input Summary ---")
    print(f"PNG file: {png_file}")
    print(f"HAR file: {har_file}")

    # --- Paths ---
    script_dir = os.path.dirname(os.path.abspath(__file__))
    palette_path = os.path.join(script_dir, "palette2.py")
    hgpt_path = os.path.join(script_dir, "hgpt.py")
    hgar_path = os.path.join(script_dir, "hgar.py")

    for path, name in [(palette_path, "palette2.py"), (hgpt_path, "hgpt.py"), (hgar_path, "hgar.py")]:
        if not os.path.isfile(path):
            print(f"Error: {name} not found in {script_dir}")
            return

    # --- Step 1: Run palette2.py ---
    run_command([sys.executable, palette_path, png_file], "palette2.py")

    # --- Step 2: Replace original PNG with palette output (_pal.png) ---
    base_name, _ = os.path.splitext(png_file)
    pal_file = f"{base_name}_pal.png"

    if not os.path.isfile(pal_file):
        print(f"Error: Expected palette output {pal_file} not found")
        return

    os.remove(png_file)  # delete old
    shutil.move(pal_file, png_file)  # rename back
    print(f"Replaced original with palette version: {png_file}")

    # --- Step 3: Prepare input for hgpt.py ---
    if png_file.endswith(".zpt.DECOMPRESSED.PICTURE.png"):
        hgpt_input = png_file
    else:
        hgpt_input = os.path.splitext(png_file)[0] + ".zpt.DECOMPRESSED.PICTURE.png"
        shutil.copy(png_file, hgpt_input)

    print(f"Prepared hgpt input: {hgpt_input}")

    # --- Step 4: Run hgpt.py ---
    run_command([sys.executable, hgpt_path, "-i", hgpt_input], "hgpt.py")

    # --- Step 5: Detect hgpt output ---
    folder = os.path.dirname(os.path.abspath(hgpt_input))
    base_name_no_ext = os.path.basename(hgpt_input).replace(".zpt.DECOMPRESSED.PICTURE.png", "")
    hgpt_output = os.path.join(folder, f"{base_name_no_ext}.zpt.DECOMPRESSED")

    if not os.path.isfile(hgpt_output):
        print(f"Error: Expected hgpt output not found: {hgpt_output}")
        return

    # --- Step 6: Prepare target paths for HAR injection ---
    final_name = f"{base_name_no_ext}.zpt"  # name used inside HAR
    target_path = hgpt_output  # full file path with .zpt.DECOMPRESSED

    print(f"HGPT output ready: {target_path}")
    print(f"Final name inside HAR: {final_name}")

    # --- Step 7: Run hgar.py to inject into HAR ---
    print("\n--- Injecting into HAR archive ---")
    run_command(
        [sys.executable, hgar_path, "--replace-raw", har_file, final_name, target_path],
        "hgar.py"
    )

    print("\n=== Process Complete ===")

if __name__ == "__main__":
    main()
