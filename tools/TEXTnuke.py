import os
import subprocess
import sys

def run_json_sequence(folder_path):
    index = 0

    # Make sure we use the correct text.py path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    text_script = os.path.join(script_dir, "text.py")

    while True:
        filename = f"{index}.bin.TEXT.json"
        json_path = os.path.join(folder_path, filename)

        if not os.path.exists(json_path):
            print(f"Stopped at missing file: {filename}")
            break

        print(f"Running: text.py -i {json_path}")

        result = subprocess.run(
            [sys.executable, text_script, "-i", json_path]
        )

        if result.returncode != 0:
            print(f"Error on {filename}")
            break

        index += 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python runner.py <folder>")
        sys.exit(1)

    run_json_sequence(sys.argv[1])
