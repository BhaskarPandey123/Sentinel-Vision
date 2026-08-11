#!/usr/bin/env python3
import os
import sys
import argparse
import datetime
from pathlib import Path

try:
    from PIL import Image, ExifTags
except ImportError:
    Image = None

try:
    import exifread
except ImportError:
    exifread = None

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def human_size(num_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"


def human_duration(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def section(title):
    line = "-" * len(title)
    return f"\n{title}\n{line}\n"


def analyze_image(path: Path) -> str:
    out = []
    out.append(section(f"IMAGE: {path.name}"))

    file_stat = path.stat()
    out.append(f"File path      : {path.resolve()}")
    out.append(f"File size      : {human_size(file_stat.st_size)}")
    out.append(f"Last modified  : {datetime.datetime.fromtimestamp(file_stat.st_mtime)}")

    if Image is None:
        out.append("\n[Pillow not installed - cannot read image contents]")
        return "\n".join(out)

    try:
        with Image.open(path) as img:
            out.append(f"Format         : {img.format}")
            out.append(f"Dimensions     : {img.width} x {img.height} px")
            out.append(f"Color mode     : {img.mode}")
            out.append(f"Megapixels     : {(img.width * img.height) / 1_000_000:.2f} MP")

            aspect = img.width / img.height if img.height else 0
            out.append(f"Aspect ratio   : {aspect:.3f} (~{approximate_ratio(img.width, img.height)})")

            rgb_img = img.convert("RGB")
            small = rgb_img.resize((100, 100))
            pixels = list(small.getdata()) if hasattr(small, "getdata") else []
            avg_r = sum(p[0] for p in pixels) / len(pixels)
            avg_g = sum(p[1] for p in pixels) / len(pixels)
            avg_b = sum(p[2] for p in pixels) / len(pixels)
            brightness = (avg_r + avg_g + avg_b) / 3

            out.append(section("Color Analysis"))
            out.append(f"Average color  : RGB({avg_r:.0f}, {avg_g:.0f}, {avg_b:.0f})")
            out.append(f"Brightness     : {brightness:.0f}/255 "
                        f"({'dark' if brightness < 85 else 'medium' if brightness < 170 else 'bright'})")

            dominant = get_dominant_colors(small, n=3)
            out.append("Dominant colors: " + (", ".join(f"RGB{c}" for c in dominant) if dominant else "N/A"))

            out.append(section("EXIF / Camera Metadata"))
            exif_text = extract_exif_pillow(img)
            if exif_text:
                out.extend(exif_text)
            else:
                out.append("No EXIF metadata found (image may be a screenshot, edited, or stripped of metadata).")

            if OCR_AVAILABLE:
                out.append(section("Detected Text (OCR)"))
                try:
                    text = pytesseract.image_to_string(rgb_img).strip()
                    out.append(text if text else "No readable text detected in the image.")
                except Exception:
                    out.append("OCR engine not installed on server environment.")

    except Exception as e:
        out.append(f"\n[ERROR reading image: {e}]")

    return "\n".join(out)


def approximate_ratio(w, h):
    def gcd(a, b):
        while b:
            a, b = b, a % b
        return a
    g = gcd(w, h) or 1
    return f"{w // g}:{h // g}"


def get_dominant_colors(img, n=3):
    colors = img.getcolors(maxcolors=100 * 100)
    if not colors:
        return []
    colors.sort(reverse=True, key=lambda c: c[0])
    return [c[1] for c in colors[:n]]


def extract_exif_pillow(img) -> list:
    lines = []
    try:
        exif_data = img._getexif() if hasattr(img, "_getexif") else None
        if not exif_data:
            return lines
        readable = {}
        for tag_id, value in exif_data.items():
            tag = ExifTags.TAGS.get(tag_id, tag_id)
            readable[tag] = value

        interesting = [
            "Make", "Model", "DateTime", "DateTimeOriginal", "ExposureTime",
            "FNumber", "ISOSpeedRatings", "FocalLength", "Flash",
            "Software", "Orientation", "GPSInfo",
        ]
        for key in interesting:
            if key in readable:
                val = readable[key]
                if key == "GPSInfo":
                    lines.append("GPS data       : present (location metadata embedded)")
                else:
                    lines.append(f"{key:<15}: {val}")
    except Exception:
        pass
    return lines


def analyze_video(path: Path) -> str:
    out = []
    out.append(section(f"VIDEO: {path.name}"))

    file_stat = path.stat()
    out.append(f"File path      : {path.resolve()}")
    out.append(f"File size      : {human_size(file_stat.st_size)}")
    out.append(f"Last modified  : {datetime.datetime.fromtimestamp(file_stat.st_mtime)}")

    if cv2 is None:
        out.append("\n[opencv-python not installed - cannot read video contents]")
        return "\n".join(out)

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        out.append("\n[ERROR: could not open video file - possibly unsupported codec]")
        return "\n".join(out)

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc = "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)]).strip()
        duration = frame_count / fps if fps else 0

        out.append(section("Technical Details"))
        out.append(f"Resolution     : {width} x {height} px")
        out.append(f"Aspect ratio   : ~{approximate_ratio(width, height) if width and height else 'unknown'}")
        out.append(f"Frame rate     : {fps:.2f} fps")
        out.append(f"Frame count    : {frame_count}")
        out.append(f"Duration       : {human_duration(duration)}")
        out.append(f"Codec (fourcc) : {fourcc if fourcc.strip() else 'unknown'}")

        out.append(section("Content Sampling (brightness across timeline)"))
        samples = 5
        brightness_readings = []
        if frame_count > 0:
            for i in range(samples):
                frame_idx = int((i / max(samples - 1, 1)) * (frame_count - 1))
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                avg_brightness = float(np.mean(gray))
                timestamp = frame_idx / fps if fps else 0
                brightness_readings.append((timestamp, avg_brightness))
                out.append(f"  t={human_duration(timestamp):<10} brightness={avg_brightness:5.1f}/255")

            if brightness_readings:
                overall_avg = sum(b for _, b in brightness_readings) / len(brightness_readings)
                out.append(f"\nOverall average brightness: {overall_avg:.1f}/255 "
                            f"({'dark scene' if overall_avg < 85 else 'medium' if overall_avg < 170 else 'bright scene'})")
        else:
            out.append("Could not sample frames (frame count unavailable).")

    except Exception as e:
        out.append(f"\n[ERROR analyzing video: {e}]")
    finally:
        cap.release()

    return "\n".join(out)


def gather_files(paths):
    files = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.suffix.lower() in IMAGE_EXTS | VIDEO_EXTS:
                    files.append(f)
        elif p.is_file():
            files.append(p)
        else:
            print(f"Warning: path not found -> {p}", file=sys.stderr)
    return files


def build_report(files) -> str:
    header = [
        "=" * 60,
        "MEDIA ANALYSIS REPORT",
        f"Generated : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Files analyzed : {len(files)}",
        "=" * 60,
    ]
    body = []
    for f in files:
        ext = f.suffix.lower()
        if ext in IMAGE_EXTS:
            body.append(analyze_image(f))
        elif ext in VIDEO_EXTS:
            body.append(analyze_video(f))
        else:
            body.append(section(f"SKIPPED: {f.name}") + "Unsupported file type.")
        body.append("\n" + "=" * 60)

    return "\n".join(header) + "\n" + "\n".join(body)


def main():
    parser = argparse.ArgumentParser(description="Analyze image/video files and write a human-readable report.")
    parser.add_argument("paths", nargs="+", help="Image/video file(s) or folder(s) to analyze")
    parser.add_argument("-o", "--output", default="media_report.txt", help="Output report file path")
    args = parser.parse_args()

    files = gather_files(args.paths)
    if not files:
        print("No supported media files found.", file=sys.stderr)
        sys.exit(1)

    report = build_report(files)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report written to: {args.output}")
    print(f"Analyzed {len(files)} file(s).")


if __name__ == "__main__":
    main()
