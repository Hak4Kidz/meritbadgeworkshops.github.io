import io
import os
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

PAGE_URL = "https://www.scouting.org/merit-badges/cybersecurity/"
ROOT_DIR = "/workspace"
ASSETS_IMG_DIR = os.path.join(ROOT_DIR, "assets", "img")
FAVICON_PATH = os.path.join(ROOT_DIR, "favicon.ico")
DOWNLOADED_BASENAME = "cybersecurity-badge-source"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".svg")
RASTER_PREF = (".png", ".jpg", ".jpeg", ".webp")


def parse_srcset(srcset_value: str):
    candidates = []
    for part in srcset_value.split(","):
        url = part.strip().split(" ")[0]
        if url:
            candidates.append(url)
    return candidates


def score_url(url: str) -> int:
    l = url.lower()
    score = 0
    # Prefer cybersecurity-specific and badge-related assets
    for kw, pts in [("cybersecurity", 12), ("cyber", 10), ("badge", 8), ("merit", 6), ("emblem", 6)]:
        if kw in l:
            score += pts
    # Penalize known non-badge assets
    for kw, pts in [("fondo", -20), ("blanco", -10), ("liso", -8), ("background", -12), ("hero", -8), ("logo", -15), ("desktop@2x", -10)]:
        if kw in l:
            score += pts
    # Prefer uploads/CDNs
    for kw, pts in [("wp-content", 2), ("uploads", 2), ("cdn", 2), ("scouting.org", 1)]:
        if kw in l:
            score += pts
    # Prefer raster formats over svg for icon generation
    for idx, ext in enumerate(RASTER_PREF[::-1], start=1):
        if l.endswith(ext):
            score += 10 + idx
    if l.endswith(".svg"):
        score += 5
    # Prefer larger hints in filename
    for sz in ["2048", "1536", "1024", "768", "512", "256", "128"]:
        if sz in l:
            score += int(int(sz) / 128)
            break
    return score


def find_candidate_image_urls(soup: BeautifulSoup, base_url: str):
    urls = []
    # <img src>, srcset
    for img in soup.find_all("img"):
        if img.get("src"):
            urls.append(urljoin(base_url, img["src"]))
        if img.get("srcset"):
            urls.extend(urljoin(base_url, u) for u in parse_srcset(img["srcset"]))
    # <source srcset>
    for source in soup.find_all("source"):
        if source.get("srcset"):
            urls.extend(urljoin(base_url, u) for u in parse_srcset(source["srcset"]))
    # <a href> likely full-size images
    for a in soup.find_all("a"):
        href = a.get("href")
        if href and any(href.lower().endswith(ext) for ext in IMG_EXTS):
            urls.append(urljoin(base_url, href))
    # Uniquify and filter
    dedup = []
    seen = set()
    for u in urls:
        if not any(u.lower().endswith(ext) for ext in IMG_EXTS):
            continue
        if u not in seen:
            seen.add(u)
            dedup.append(u)
    # Sort by heuristic score descending
    dedup.sort(key=score_url, reverse=True)
    return dedup


def download_bytes(url: str) -> bytes:
    r = requests.get(url, headers={**HEADERS, "Referer": PAGE_URL}, timeout=30)
    r.raise_for_status()
    return r.content


def to_square_rgba(img: Image.Image) -> Image.Image:
    # Ensure RGBA
    if img.mode not in ("RGBA", "LA"):
        img = img.convert("RGBA")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img_cropped = img.crop((left, top, left + side, top + side))
    # Add a circular mask to emphasize the round badge
    mask = Image.new("L", (side, side), 0)
    draw = Image.new("L", (side, side), 0)
    # Use ImageOps to create circular mask via fit + expand technique
    # Create a white circle mask
    mask = Image.new("L", (side, side), 0)
    mask_draw = Image.new("L", (side, side), 0)
    # Draw circle by putting ellipse via ImageDraw kept minimal to avoid extra deps
    from PIL import ImageDraw

    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, side - 1, side - 1), fill=255)

    base = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    base.paste(img_cropped, (0, 0), mask)

    # Optionally add subtle outer ring to make it pop on dark tabs
    ring = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring)
    ring_draw.ellipse((1, 1, side - 2, side - 2), outline=(255, 215, 0, 180), width=max(1, side // 32))
    base = Image.alpha_composite(base, ring)

    return base


def main():
    print("Fetching page:", PAGE_URL)
    html = requests.get(PAGE_URL, headers=HEADERS, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")

    candidates = find_candidate_image_urls(soup, PAGE_URL)
    if not candidates:
        raise SystemExit("No candidate images found on page")

    print("Candidates (top 8):")
    for u in candidates[:8]:
        print(" -", u)

    # Selection: prefer raster with 'cyber' or 'badge' in URL; avoid background/logo assets
    bad_keywords = ("fondo", "blanco", "liso", "background", "hero", "logo", "scouting-america-logo")
    chosen = None
    # 1) Raster + contains 'cyber'
    for u in candidates:
        lu = u.lower()
        if any(b in lu for b in bad_keywords):
            continue
        if "cyber" in lu and any(lu.endswith(ext) for ext in RASTER_PREF):
            chosen = u
            break
    # 2) Raster + contains 'badge' or 'merit'
    if not chosen:
        for u in candidates:
            lu = u.lower()
            if any(b in lu for b in bad_keywords):
                continue
            if ("badge" in lu or "merit" in lu) and any(lu.endswith(ext) for ext in RASTER_PREF):
                chosen = u
                break
    # 3) Fallback: first raster not in bad keywords
    if not chosen:
        for u in candidates:
            lu = u.lower()
            if any(b in lu for b in bad_keywords):
                continue
            if any(lu.endswith(ext) for ext in RASTER_PREF):
                chosen = u
                break
    # 4) Final fallback: first candidate
    if not chosen:
        chosen = candidates[0]
    if not chosen:
        chosen = candidates[0]

    print("Chosen image:", chosen)
    data = download_bytes(chosen)

    # Save original
    parsed = urlparse(chosen)
    ext = os.path.splitext(parsed.path)[1] or ".img"
    out_src = os.path.join(ASSETS_IMG_DIR, DOWNLOADED_BASENAME + ext)
    with open(out_src, "wb") as f:
        f.write(data)
    print("Saved source image:", out_src)

    # If svg, we currently skip conversion and bail; try to find next raster candidate
    if ext.lower() == ".svg":
        # Try next raster candidate
        for u in candidates:
            if any(u.lower().endswith(e) for e in RASTER_PREF):
                print("Switching to raster candidate:", u)
                chosen = u
                data = download_bytes(chosen)
                parsed = urlparse(chosen)
                ext = os.path.splitext(parsed.path)[1] or ".img"
                out_src = os.path.join(ASSETS_IMG_DIR, DOWNLOADED_BASENAME + ext)
                with open(out_src, "wb") as f:
                    f.write(data)
                print("Saved source image:", out_src)
                break

    # Open with PIL
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as e:
        raise SystemExit(f"Failed to open image from {chosen}: {e}")

    square = to_square_rgba(img)

    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (96, 96), (128, 128), (256, 256)]
    # Use a high-resolution base for better downscaling
    base_side = max(s[0] for s in sizes)
    hi = square
    if square.size[0] < base_side:
        hi = square.resize((base_side, base_side), Image.LANCZOS)

    hi.save(FAVICON_PATH, format="ICO", sizes=sizes)
    print("Wrote", FAVICON_PATH)


if __name__ == "__main__":
    main()
