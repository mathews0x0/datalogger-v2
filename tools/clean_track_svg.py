import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def luminance(hex_color):
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return 0.299 * r + 0.587 * g + 0.114 * b


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="input_path", type=Path, required=True)
    parser.add_argument("--out", dest="output_path", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=145.0)
    parser.add_argument("--remove-scale-bar", action="store_true")
    args = parser.parse_args()

    tree = ET.parse(args.input_path)
    root = tree.getroot()

    width = root.attrib.get("width", "1000")
    height = root.attrib.get("height", "1000")
    if "viewBox" not in root.attrib:
        root.set("viewBox", f"0 0 {float(width):g} {float(height):g}")

    kept = 0
    removed = 0

    for parent in list(root.iter()):
        children = list(parent)
        for child in children:
            tag = child.tag.split("}")[-1]
            if tag != "path":
                continue

            fill = child.attrib.get("fill")
            if not (fill and fill.startswith("#") and len(fill) == 7):
                parent.remove(child)
                removed += 1
                continue

            if luminance(fill) > args.threshold:
                parent.remove(child)
                removed += 1
                continue

            if args.remove_scale_bar:
                d = child.attrib.get("d", "")
                if d.startswith("M0 0 C644.16 0"):
                    parent.remove(child)
                    removed += 1
                    continue

            child.set("fill", "#111111")
            child.attrib.pop("stroke", None)
            child.attrib.pop("style", None)
            kept += 1

    root.attrib.pop("version", None)

    args.output_path.write_text(
        ET.tostring(root, encoding="unicode", xml_declaration=True)
    )

    print(f"output={args.output_path}")
    print(f"kept_paths={kept}")
    print(f"removed_paths={removed}")
    print(f"threshold={args.threshold}")


if __name__ == "__main__":
    main()
