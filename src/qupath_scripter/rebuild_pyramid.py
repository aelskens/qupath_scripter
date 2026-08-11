import os
from pathlib import Path

import numpy as np
import pyvips
import tifffile


def rebuild_pyramids_with_tifffile(
    path: Path, pattern="*_rewritten.ome.tif", compression="jpeg", quality=90, tile_size=512
):
    import re
    import tempfile
    from xml.dom.minidom import parseString

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
            # Read page 0 for metadata
            image_meta = pyvips.Image.new_from_file(str(input_path), access="sequential", page=0)
            fields = image_meta.get_fields()
            n_pages = int(image_meta.get("n-pages")) if "n-pages" in fields else 1
            print(f"  Size: {image_meta.width} x {image_meta.height}, n_pages={n_pages}, format={image_meta.format}")

            # Extract pixel size and channel names from OME-XML
            pixel_size_um = None
            channel_names = None
            if "image-description" in fields:
                xml = image_meta.get("image-description")
                m = re.search(r'PhysicalSizeX="([0-9.]+)"', xml)
                if m:
                    pixel_size_um = float(m.group(1))
                try:
                    channels = parseString(xml).getElementsByTagName("Channel")
                    names = [c.attributes["Name"].value for c in channels if c.attributes.get("Name")]
                    channel_names = names if names else None
                except Exception:
                    pass

            print(f"  Pixel size: {pixel_size_um} µm")
            print(f"  Channels: {channel_names}")

            # Extract resolution
            xres = image_meta.get("xres") if "xres" in fields else None
            yres = image_meta.get("yres") if "yres" in fields else None
            resolution = (xres * 10, yres * 10) if xres and yres else None

            # Compute level dimensions using strict floor(prev/2) chain
            levels_dims = []
            w, h = image_meta.width, image_meta.height
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
                write_options["resolutionunit"] = 3

            ome_metadata = {}
            if pixel_size_um:
                ome_metadata["PhysicalSizeX"] = pixel_size_um
                ome_metadata["PhysicalSizeXUnit"] = "µm"
                ome_metadata["PhysicalSizeY"] = pixel_size_um
                ome_metadata["PhysicalSizeYUnit"] = "µm"
            if channel_names:
                ome_metadata["Channel"] = {"Name": channel_names}

            with tifffile.TiffWriter(str(output_path), bigtiff=True, ome=True) as tif:
                for j, (lw, lh) in enumerate(levels_dims):
                    print(f"  Writing level {j}: {lw} x {lh}...")

                    # Collect all pages for this level then stack into single array
                    # so tifffile writes them as one multi-page entry in the same series
                    level_pages = []
                    for page_idx in range(n_pages):
                        image = pyvips.Image.new_from_file(str(input_path), access="sequential", page=page_idx, n=1)

                        if lw == image.width and lh == image.height:
                            resized = image
                        else:
                            xscale = lw / image.width
                            yscale = lh / image.height
                            resized = image.resize(xscale, vscale=yscale, kernel="lanczos3")
                            resized = resized.crop(0, 0, min(resized.width, lw), min(resized.height, lh))

                        with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
                            tmp_path = tmp.name
                        try:
                            tiffsave_args = dict(
                                tile=True,
                                tile_width=tile_size,
                                tile_height=tile_size,
                                compression=compression,
                                bigtiff=True,
                            )
                            if compression == "jpeg":
                                tiffsave_args["Q"] = quality

                            resized.tiffsave(tmp_path, **tiffsave_args)
                            with tifffile.TiffFile(tmp_path) as tmp_tif:
                                level_pages.append(tmp_tif.pages[0].asarray())
                        finally:
                            Path(tmp_path).unlink(missing_ok=True)

                    # Stack channels on axis 0: (n_pages, h, w) or (n_pages, h, w, bands)
                    arr = np.stack(level_pages, axis=0)

                    write_kwargs = {**write_options}
                    if j == 0:
                        write_kwargs["subifds"] = len(levels_dims) - 1
                        write_kwargs["metadata"] = ome_metadata if ome_metadata else None
                    else:
                        write_kwargs["subfiletype"] = 1

                    tif.write(arr, **write_kwargs)
                    del arr
                    del level_pages

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
