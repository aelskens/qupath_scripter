import json
import re
import subprocess
from pathlib import Path

from tqdm import tqdm

from src.qupath_scripter.utils import (
    get_script_absolute_path,
    get_template_from_file,
    render_template,
    save_rendered_template,
)

TISSUES_METADATA = {
    "breast": {
        "magnification": 40.0,
        "x_resolution": 0.2528,
        "y_resolution": 0.2528,
    },
    "COAD": {
        "magnification": 20.0,
        "x_resolution": 0.468,
        "y_resolution": 0.468,
    },
    "gastric": {
        "magnification": 40.0,
        "x_resolution": 0.2528,
        "y_resolution": 0.2528,
    },
    "kidney": {
        "magnification": 40.0,
        "x_resolution": 0.2528,
        "y_resolution": 0.2528,
    },
    "lung-lesion": {
        "magnification": 40.0,
        "x_resolution": 0.174,
        "y_resolution": 0.174,
    },
    "lung-lobes": {
        "magnification": 10.0,
        "x_resolution": 1.274,
        "y_resolution": 1.274,
    },
    "mammary-gland": {
        "magnification": 20.0,
        "x_resolution": 0.2528,
        "y_resolution": 0.2528,
    },
    "mice-kidney": {
        "magnification": 40.0,
        "x_resolution": 0.227,
        "y_resolution": 0.227,
    },
}


def get_biggest_scale(tissue_dir: Path) -> tuple[Path, float]:
    biggest_scale = 0
    path_to_biggest = tissue_dir
    for scale_dir in tissue_dir.iterdir():
        if not scale_dir.is_dir():
            continue

        _tmp = re.search(r"scale-\d\.?\d{,2}", str(scale_dir))
        assert _tmp is not None
        _scale_pc = float(_tmp[0].split("-")[-1])
        if biggest_scale < _scale_pc:
            biggest_scale = _scale_pc
            path_to_biggest = scale_dir

    return path_to_biggest, biggest_scale


def generate_script(tissue: str, mpp_x: float, mpp_y: float | None = None) -> str:
    name = "export_image_as_tiff.groovy.jinja2"
    rendered_template_name = f"{tissue}_{name.replace('.jinja2', '')}"

    try:
        return str(get_script_absolute_path(rendered_template_name))
    except FileNotFoundError:
        template = get_template_from_file(name)
        rendered_template = render_template(template, mpp_x=mpp_x, mpp_y=mpp_y if mpp_y is not None else mpp_x)

        save_rendered_template(rendered_template, rendered_template_name)

        return str(get_script_absolute_path(rendered_template_name))


if __name__ == "__main__":

    path = Path("/data/dataset_ANHIR/images")
    tissues_path_list = [t for t in path.iterdir() if t.is_dir()]

    outer_loop = tqdm(range(len(tissues_path_list)), desc="Tissues", total=len(tissues_path_list))
    inner_loop = tqdm(total=0, desc="Images")
    for tissue_dir_path in tissues_path_list:
        if tissue_dir_path.joinpath("README.md").exists():
            outer_loop.update()
            continue

        _tmp = re.search(r"/([A-Za-z-]*)_\d+/?", str(tissue_dir_path))
        assert _tmp is not None
        tissue_name = _tmp[1]
        tissue_info = TISSUES_METADATA[tissue_name]

        biggest_scale_dir, scale_pc = get_biggest_scale(tissue_dir_path)
        mag = scale_pc * (tissue_info["magnification"] / 100)

        script_path = generate_script(
            tissue=tissue_name, mpp_x=tissue_info["x_resolution"] * tissue_info["magnification"] / mag
        )

        images_path_list = [i for i in biggest_scale_dir.iterdir() if i.is_file()]
        inner_loop.reset(total=len(images_path_list))

        for image_path in images_path_list:
            if not image_path.is_file():
                continue

            process = subprocess.Popen(
                f"QuPath script '{script_path}' -i '{str(image_path)}'",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True,
            )

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                with open(
                    tissue_dir_path.joinpath(image_path.name.split(".")[0] + "_process.log"), "w", encoding="utf-8"
                ) as logfile:
                    logfile.write("Command failed!\n")
                    logfile.write(f"Return code: {process.returncode}\n\n")
                    logfile.write(stderr)

            inner_loop.update()

        # Create REAMDE.md to explain what is inside
        readme_txt = f"# {tissue_name.upper()}\n"
        readme_txt += "\n"
        readme_txt += "## ANHIR specifications\n"
        readme_txt += "\n"
        readme_txt += f"- Magnification: {tissue_info['magnification']}\n"
        readme_txt += f"- Pixel Width [µm]: {tissue_info['x_resolution']}\n"
        readme_txt += f"- Pixel Height [µm]: {tissue_info['y_resolution']}\n"
        readme_txt += "\n"
        readme_txt += "## Real values (for the full resolution)\n"
        readme_txt += "\n"
        readme_txt += f"- Magnification ({scale_pc:=} * {tissue_info['magnification']:=} / 100): {mag}\n"
        readme_txt += f"- Pixel Width [µm]: ({tissue_info['x_resolution']:=} * {tissue_info['magnification']:=} / {mag:=}): {tissue_info['x_resolution']*tissue_info['magnification']/mag:=}\n"
        readme_txt += f"- Pixel Height [µm]: ({tissue_info['y_resolution']:=} * {tissue_info['magnification']:=} / {mag:=}): {tissue_info['y_resolution']*tissue_info['magnification']/mag:=}"
        with open(tissue_dir_path.joinpath("README.md"), mode="w", encoding="utf-8") as fp:
            fp.write(readme_txt)

        # Create additional_metadata.json that will be used when loading the whole-slide
        with open(tissue_dir_path.joinpath("additional_metadata.json"), "w", encoding="utf-8") as fp:
            json.dump({"mag": mag}, fp)

        outer_loop.update()
