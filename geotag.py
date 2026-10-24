"""Stamp GPS coordinates into a photo's EXIF so the demo can show location-based ward detection.

Many photos lose GPS on the way to a laptop (WhatsApp, screenshots, downloads). Use this to
prepare demo photos:

    python geotag.py pothole.jpg --area "Vastrapur"           # uses that area's ward centroid
    python geotag.py garbage.jpg --lat 23.0225 --lon 72.5714  # exact coordinates
    python geotag.py photo.jpg --check                        # just print the GPS it has

Writes <name>_geo.jpg next to the original.
"""
import argparse
from fractions import Fraction
from pathlib import Path

from PIL import Image

import db
import tools


def _dms(value: float):
    value = abs(value)
    d = int(value)
    m = int((value - d) * 60)
    s = round((value - d - m / 60) * 3600, 2)
    return (Fraction(d), Fraction(m), Fraction(s).limit_denominator(100))


def geotag(src: Path, lat: float, lon: float) -> Path:
    img = Image.open(src)
    exif = img.getexif()
    exif[0x8825] = {1: "N" if lat >= 0 else "S", 2: _dms(lat), 3: "E" if lon >= 0 else "W", 4: _dms(lon)}
    dst = src.with_name(f"{src.stem}_geo.jpg")
    img.convert("RGB").save(dst, "JPEG", exif=exif, quality=92)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo", type=Path)
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--area", help="Area name, e.g. 'Maninagar'; uses its ward centroid")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    if a.check:
        gps = Image.open(a.photo).getexif().get_ifd(0x8825)
        print(dict(gps) if gps else "No GPS data in this photo.")
        return
    if a.area:
        db.init_db()
        w = tools.lookup_ward(area_name=a.area)
        if not w["found"]:
            raise SystemExit(w["reason"])
        conn = db.connect()
        row = conn.execute("SELECT lat, lon FROM wards WHERE id = ?", (w["ward_id"],)).fetchone()
        a.lat, a.lon = row["lat"], row["lon"]
        print(f"{a.area} -> {w['ward_name']} ward ({a.lat}, {a.lon})")
    if a.lat is None or a.lon is None:
        raise SystemExit("Give --area or both --lat and --lon")
    print("Wrote", geotag(a.photo, a.lat, a.lon))


if __name__ == "__main__":
    main()
