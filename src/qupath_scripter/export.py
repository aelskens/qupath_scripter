import subprocess
from pathlib import Path

from tqdm import tqdm

from src.qupath_scripter.utils import (
    get_script_absolute_path,
)

if __name__ == "__main__":

    path = Path("/data/dataset_Marzahl/MSSC/images")

    # Collect all .tif files recursively (but not already-converted .ome.tif).
    images_path_list = [p for p in path.rglob("*.tif") if not p.name.endswith(".ome.tif")]

    if not images_path_list:
        print(f"No .tif files found under {path}")
        raise SystemExit(0)

    script_path = get_script_absolute_path("export_image_as_tiff.groovy")

    loop = tqdm(images_path_list, desc="Images", total=len(images_path_list))

    for image_path in loop:
        loop.set_postfix(file=image_path.name)

        # Build the safe output filename (whitespace → underscore) so that
        # log files match the actual output name.
        safe_stem = image_path.stem.replace(" ", "_")
        log_name = safe_stem + "_process.log"

        process = subprocess.Popen(
            f"QuPath script '{script_path}' -i '{str(image_path)}'",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True,
        )

        stdout, stderr = process.communicate()

        if process.returncode != 0:
            log_path = image_path.parent / log_name
            with open(log_path, "w", encoding="utf-8") as logfile:
                logfile.write("Command failed!\n")
                logfile.write(f"Return code: {process.returncode}\n\n")
                logfile.write(stderr)

            tqdm.write(f"[ERROR] {image_path.name} — see {log_path}")
