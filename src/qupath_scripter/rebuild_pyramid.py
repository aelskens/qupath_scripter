import os
from pathlib import Path

import pyvips
import tifffile


def rebuild_pyramids_with_tifffile(
    path: Path, pattern="*_rewritten.ome.tif", compression="jpeg", quality=90, tile_size=512
):
    import re
    import tempfile

    files = list(path.rglob(pattern))
    if not files:
        print(f"No files matching '{pattern}' found.")
        return

    print(f"Found {len(files)} file(s) to process.")

    for i, input_path in enumerate(files):
        stem = str(input_path).replace("_rewritten.ome.tif", "")
        output_path = Path(stem + ".ome.tif")

        print(f"\n[{i+1}/{len(files)}] {input_path}")
        print(f"  -> {output_path}")

        if output_path.exists():
            print("  Skipping, output already exists.")
            continue

        try:
            image = pyvips.Image.new_from_file(str(input_path), access="sequential")
            print(f"  Size: {image.width} x {image.height}, bands={image.bands}, format={image.format}")

            # Extract pixel size from OME-XML
            pixel_size_um = None
            fields = image.get_fields()
            if "image-description" in fields:
                xml = image.get("image-description")
                m = re.search(r'PhysicalSizeX="([0-9.]+)"', xml)
                if m:
                    pixel_size_um = float(m.group(1))
            print(f"  Pixel size: {pixel_size_um} µm")

            # Extract resolution
            xres = image.get("xres") if "xres" in fields else None
            yres = image.get("yres") if "yres" in fields else None
            resolution = (xres * 10, yres * 10) if xres and yres else None

            # Compute level dimensions using strict floor(prev/2) chain
            levels_dims = []
            w, h = image.width, image.height
            while max(w, h) >= tile_size:
                levels_dims.append((w, h))
                nw, nh = int(w / 2), int(h / 2)
                if max(nw, nh) < tile_size:
                    break
                w, h = nw, nh

            print(f"  Levels ({len(levels_dims)}):")
            for j, (lw, lh) in enumerate(levels_dims):
                print(f"    Level {j}: {lw} x {lh}")

            write_options = dict(tile=(tile_size, tile_size), compression=compression)
            if compression == "jpeg":
                write_options["compressionargs"] = {"level": quality}
            if resolution:
                write_options["resolution"] = resolution
                write_options["resolutionunit"] = 3  # cm

            ome_metadata = {}
            if pixel_size_um:
                ome_metadata = {
                    "PhysicalSizeX": pixel_size_um,
                    "PhysicalSizeXUnit": "µm",
                    "PhysicalSizeY": pixel_size_um,
                    "PhysicalSizeYUnit": "µm",
                }

            with tifffile.TiffWriter(str(output_path), bigtiff=True, ome=True) as tif:
                for j, (lw, lh) in enumerate(levels_dims):
                    print(f"  Writing level {j}: {lw} x {lh}...")

                    if lw == image.width and lh == image.height:
                        resized = image
                    else:
                        # Independent x/y scale factors to hit exact floor(prev/2) targets
                        xscale = lw / image.width
                        yscale = lh / image.height
                        resized = image.resize(xscale, vscale=yscale, kernel="lanczos3")
                        # Crop as safety net for any residual 1-pixel overshoot
                        resized = resized.crop(0, 0, min(resized.width, lw), min(resized.height, lh))

                    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
                        tmp_path = tmp.name

                    try:
                        resized.tiffsave(
                            tmp_path,
                            tile=True,
                            tile_width=tile_size,
                            tile_height=tile_size,
                            compression=compression,
                            Q=quality if compression == "jpeg" else None,
                            bigtiff=True,
                        )

                        with tifffile.TiffFile(tmp_path) as tmp_tif:
                            arr = tmp_tif.pages[0].asarray()

                        write_kwargs = {**write_options}
                        if j == 0:
                            write_kwargs["subifds"] = len(levels_dims) - 1
                            write_kwargs["metadata"] = ome_metadata if ome_metadata else None
                        else:
                            write_kwargs["subfiletype"] = 1

                        tif.write(arr, **write_kwargs)
                        del arr

                    finally:
                        Path(tmp_path).unlink(missing_ok=True)

            size_gb = output_path.stat().st_size / 1024**3
            print(f"  Done, {size_gb:.2f} GB")

        except Exception as e:
            print(f"  ERROR: {e}")
            if output_path.exists():
                output_path.unlink()
                print("  Removed partial output.")


def rebuild_pyramids_with_pyvips(path: Path, pattern="*_rewritten.ome.tif", compression="jpeg", quality=90):
    files = [p for p in path.rglob(pattern)]

    if not files:
        print(f"No files matching '{pattern}' found.")
        return

    print(f"Found {len(files)} file(s) to process.")

    for i, input_path in enumerate(files):
        stem = str(input_path).replace("_rewritten.ome.tif", "")
        output_path = stem + ".ome.tif"

        print(f"\n[{i}/{len(files)}] {input_path}")
        print(f"  -> {output_path}")

        if os.path.exists(output_path):
            print("  Skipping, output already exists.")
            continue

        try:
            image: pyvips.Image = pyvips.Image.new_from_file(input_path, access="sequential")
            print(f"  Size: {image.width} x {image.height}, bands={image.bands}, format={image.format}")

            save_args = dict(
                tile=True,
                tile_width=512,
                tile_height=512,
                pyramid=True,
                bigtiff=True,
                compression=compression,
                subifd=True,
            )
            if compression == "jpeg":
                save_args["Q"] = quality

            image.tiffsave(output_path, **save_args)

            size_gb = os.path.getsize(output_path) / 1024**3
            print(f"  Done, {size_gb:.2f} GB")

        except Exception as e:
            print(f"  ERROR: {e}")
            if os.path.exists(output_path):
                os.remove(output_path)
                print("  Removed partial output.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rebuild OME-TIFF pyramids using pyvips.")
    parser.add_argument(
        "--library",
        default="tifffile",
        type=str,
        help="The library to use to write the output. Available choices are: tifffile or pyvips.",
    )
    parser.add_argument("--pattern", default="*_rewritten.ome.tif", help="Glob pattern to find input files")
    parser.add_argument(
        "--compression", default="jpeg", choices=["jpeg", "deflate", "lzw", "none"], help="Compression type"
    )
    parser.add_argument("--quality", default=100, type=int, help="JPEG quality (ignored for lossless compression)")
    args = parser.parse_args()

    path = Path("/data/dataset_Marzahl/ISC/images/IHC")

    writing_func = rebuild_pyramids_with_pyvips if args.library == "pyvips" else rebuild_pyramids_with_tifffile

    writing_func(
        path=path,
        pattern=args.pattern,
        compression=args.compression,
        quality=args.quality,
    )
