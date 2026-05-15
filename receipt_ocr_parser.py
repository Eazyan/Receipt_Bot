#!/usr/bin/env python3
"""
Best-effort receipt OCR parser focused on extracting item-price pairs from photographed receipts.

What it does
------------
1. Builds multiple preprocessed variants of the input image.
2. Runs PaddleOCR on each variant.
3. Merges OCR lines across variants.
4. Extracts item-price pairs with receipt-specific heuristics.
5. Outputs JSON and a readable text summary.

This is not "perfect for any receipt". No OCR pipeline is. It is designed to be robust on noisy phone photos,
Russian receipts, and similar grocery/retail layouts with a rightmost price column.

Dependencies
------------
pip install "paddleocr[all]" opencv-python numpy

Usage
-----
python receipt_ocr_parser.py /path/to/receipt.jpg
python receipt_ocr_parser.py /path/to/receipt.jpg --lang ru --json-out result.json --debug-dir debug

Notes
-----
- The first run downloads PaddleOCR models.
- Russian receipts: use --lang ru
- If recognition is weak, try a larger image or stronger lighting/crop before OCR.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from paddleocr import PaddleOCR


# -----------------------------
# Data structures
# -----------------------------

@dataclass
class OCRWord:
    text: str
    conf: float
    x1: float
    y1: float
    x2: float
    y2: float
    source: str

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def w(self) -> float:
        return self.x2 - self.x1

    @property
    def h(self) -> float:
        return self.y2 - self.y1


@dataclass
class OCRLine:
    text: str
    conf: float
    x1: float
    y1: float
    x2: float
    y2: float
    source: str

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def w(self) -> float:
        return self.x2 - self.x1

    @property
    def h(self) -> float:
        return self.y2 - self.y1


@dataclass
class ReceiptItem:
    name: str
    price: float
    qty: Optional[float]
    unit_price: Optional[float]
    line_text: str
    confidence: float
    y: float


# -----------------------------
# Image preprocessing
# -----------------------------


def order_points(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect



def maybe_warp_receipt(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.dilate(edges, kernel, iterations=2)
    edges = cv2.erode(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img

    h, w = gray.shape
    img_area = h * w
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for cnt in contours[:10]:
        area = cv2.contourArea(cnt)
        if area < img_area * 0.15:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
        if len(approx) != 4:
            continue

        pts = approx.reshape(4, 2).astype("float32")
        rect = order_points(pts)
        (tl, tr, br, bl) = rect

        width_a = np.linalg.norm(br - bl)
        width_b = np.linalg.norm(tr - tl)
        height_a = np.linalg.norm(tr - br)
        height_b = np.linalg.norm(tl - bl)

        max_w = int(max(width_a, width_b))
        max_h = int(max(height_a, height_b))
        if max_w < 100 or max_h < 100:
            continue

        dst = np.array(
            [[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]],
            dtype="float32",
        )
        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(img, M, (max_w, max_h))

        # Keep only plausible tall receipt-like warps.
        ratio = max_h / max(max_w, 1)
        if ratio >= 1.1:
            return warped

    return img



def upscale_if_small(img: np.ndarray, min_width: int = 1400) -> np.ndarray:
    h, w = img.shape[:2]
    if w >= min_width:
        return img
    scale = min_width / max(w, 1)
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)



def deskew(gray: np.ndarray) -> np.ndarray:
    bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(bw > 0))
    if len(coords) < 100:
        return gray
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    if angle < -45:
        angle = 90 + angle
    angle = -angle
    if abs(angle) < 0.2:
        return gray
    h, w = gray.shape
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)



def variants_from_image(img: np.ndarray) -> Dict[str, np.ndarray]:
    base = maybe_warp_receipt(img)
    base = upscale_if_small(base)

    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    gray = deskew(gray)

    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)

    den = cv2.fastNlMeansDenoising(gray, None, 12, 7, 21)
    den_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(den)

    th_otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    th_adapt = cv2.adaptiveThreshold(
        den_clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )

    sharp = cv2.GaussianBlur(gray, (0, 0), 3)
    sharp = cv2.addWeighted(gray, 1.7, sharp, -0.7, 0)

    color_clean = cv2.cvtColor(den_clahe, cv2.COLOR_GRAY2BGR)

    return {
        "color": base,
        "gray": gray,
        "clahe": clahe,
        "denoise": den_clahe,
        "th_otsu": th_otsu,
        "th_adapt": th_adapt,
        "sharp": sharp,
        "color_clean": color_clean,
    }


# -----------------------------
# OCR
# -----------------------------


def make_ocr(lang: str = "ru") -> PaddleOCR:
    # PaddleOCR general OCR pipeline supports multilingual models and lang codes such as ru.
    return PaddleOCR(
        use_angle_cls=True,
        lang=lang,
        show_log=False,
    )



def normalize_text(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = s.replace("₽", "Р")
    s = s.replace("O", "0") if re.fullmatch(r"[0-9O.,]+", s) else s
    s = re.sub(r"\s+", " ", s).strip()
    return s



def run_ocr_on_variant(ocr: PaddleOCR, img: np.ndarray, source: str) -> List[OCRLine]:
    result = ocr.ocr(img, cls=True)
    lines: List[OCRLine] = []

    if not result:
        return lines

    for block in result:
        if not block:
            continue
        for entry in block:
            box, rec = entry
            text, conf = rec
            text = normalize_text(str(text))
            if not text:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            lines.append(
                OCRLine(
                    text=text,
                    conf=float(conf),
                    x1=float(min(xs)),
                    y1=float(min(ys)),
                    x2=float(max(xs)),
                    y2=float(max(ys)),
                    source=source,
                )
            )
    return lines


# -----------------------------
# Merging OCR results across variants
# -----------------------------


def text_similarity(a: str, b: str) -> float:
    a = re.sub(r"\s+", " ", a.lower()).strip()
    b = re.sub(r"\s+", " ", b.lower()).strip()
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    sa = set(a.split())
    sb = set(b.split())
    j = len(sa & sb) / max(1, len(sa | sb))
    prefix = 1.0 if a[: min(12, len(a), len(b))] == b[: min(12, len(a), len(b))] else 0.0
    return max(j, prefix * 0.8)



def merge_lines(all_lines: List[OCRLine]) -> List[OCRLine]:
    if not all_lines:
        return []
    all_lines = sorted(all_lines, key=lambda x: (x.cy, x.cx))
    groups: List[List[OCRLine]] = []

    median_h = statistics.median([max(8.0, x.h) for x in all_lines])
    y_tol = max(12.0, median_h * 0.6)

    for line in all_lines:
        placed = False
        for g in groups:
            gy = statistics.mean([z.cy for z in g])
            gx = statistics.mean([z.cx for z in g])
            if abs(line.cy - gy) <= y_tol and abs(line.cx - gx) <= max(70.0, line.w * 0.5):
                if text_similarity(line.text, g[0].text) >= 0.45:
                    g.append(line)
                    placed = True
                    break
        if not placed:
            groups.append([line])

    merged: List[OCRLine] = []
    for g in groups:
        # pick the best representative, but reward agreement.
        candidates = []
        for line in g:
            agreement = sum(1 for other in g if text_similarity(line.text, other.text) >= 0.7)
            score = line.conf + 0.04 * agreement
            candidates.append((score, line))
        _, best = max(candidates, key=lambda t: t[0])
        merged.append(
            OCRLine(
                text=best.text,
                conf=min(0.999, max(x.conf for x in g) + 0.02 * (len(g) - 1)),
                x1=min(x.x1 for x in g),
                y1=min(x.y1 for x in g),
                x2=max(x.x2 for x in g),
                y2=max(x.y2 for x in g),
                source="+".join(sorted({x.source for x in g})),
            )
        )

    merged.sort(key=lambda x: (x.cy, x.x1))
    return merged


# -----------------------------
# Receipt parsing heuristics
# -----------------------------

PRICE_RE = re.compile(r"(?<!\d)(\d{1,5}[.,]\d{2})(?!\d)")
QTY_RE = re.compile(r"(?<!\d)(\d+[.,]?\d*)\s*(?:шт|шТ|kg|кг|l|л|x|х)(?!\w)", re.IGNORECASE)
WEIGHT_PRICE_RE = re.compile(r"(?<!\d)(\d+[.,]\d{3})\s*(?:кг|kg)(?!\w)", re.IGNORECASE)

HEADER_WORDS = {
    "итог", "сумма", "скидка", "баланс", "бонус", "кассир", "кассовый", "чек", "приход",
    "безналичными", "электронными", "получено", "плат.картой", "плат", "карта", "ндс",
    "место", "расчетов", "магазин", "инн", "сайт", "офд", "фн", "фд", "рн", "зн", "смена",
}

STOP_LINE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"^итог",
        r"^скидк",
        r"^ндс",
        r"^безнал",
        r"^электрон",
        r"^получено",
        r"^плат",
        r"^кассир",
        r"^кассовый чек",
        r"^инн",
        r"^офд",
        r"^фн",
        r"^фд",
        r"^рн",
        r"^зн",
        r"^сайт",
        r"^место расчет",
        r"^карта",
        r"^начислено",
        r"^баланс",
        r"qr",
    ]
]


def parse_num(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None



def looks_like_service_line(text: str) -> bool:
    t = text.lower().strip()
    if len(t) <= 1:
        return True
    if sum(ch.isdigit() for ch in t) >= max(8, len(t) * 0.7):
        return True
    for rx in STOP_LINE_PATTERNS:
        if rx.search(t):
            return True
    return False



def likely_item_name(name: str) -> bool:
    if not name:
        return False
    t = name.lower().strip(" -_.,:;")
    if len(t) < 2:
        return False
    if any(w in t.split() for w in HEADER_WORDS):
        return False
    digits = sum(ch.isdigit() for ch in t)
    letters = sum(ch.isalpha() for ch in t)
    return letters >= 2 and letters >= digits * 0.5



def split_name_and_price(line_text: str) -> Tuple[str, Optional[float], Optional[float], Optional[float]]:
    """
    Returns: name, final_price, qty, unit_price
    """
    text = normalize_text(line_text)

    # Find all price-like numbers and use the rightmost one as final line price.
    prices = list(PRICE_RE.finditer(text))
    if not prices:
        return text, None, None, None

    final_match = prices[-1]
    final_price = parse_num(final_match.group(1))
    left = text[: final_match.start()].rstrip(" .,-:;")

    # Optional quantity.
    qty = None
    unit_price = None

    q = QTY_RE.search(left)
    if q:
        qty = parse_num(q.group(1))
        left = (left[: q.start()] + " " + left[q.end():]).strip()

    # Optional weighted quantity like 0.480кг just before the total.
    w = WEIGHT_PRICE_RE.search(left)
    if w:
        qty = parse_num(w.group(1))
        left = (left[: w.start()] + " " + left[w.end():]).strip()

    # Unit price: previous price-like token before final price.
    if len(prices) >= 2:
        unit_price = parse_num(prices[-2].group(1))
        # Remove only if it is near the end and likely metadata.
        prev = prices[-2]
        if prev.end() >= max(0, final_match.start() - 18):
            left = (text[: prev.start()] + text[prev.end(): final_match.start()]).strip()

    name = re.sub(r"\s+", " ", left).strip(" .,-:;")
    return name, final_price, qty, unit_price



def merge_multiline_items(lines: List[OCRLine]) -> List[OCRLine]:
    if not lines:
        return []
    out: List[OCRLine] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        cur_has_price = bool(PRICE_RE.search(cur.text))
        cur_service = looks_like_service_line(cur.text)

        if not cur_has_price and not cur_service and i + 1 < len(lines):
            nxt = lines[i + 1]
            # Continuation when next line is very close vertically and contains a price.
            if abs(nxt.cy - cur.cy) <= max(cur.h, nxt.h) * 1.8 and PRICE_RE.search(nxt.text):
                merged_text = f"{cur.text} {nxt.text}"
                out.append(
                    OCRLine(
                        text=merged_text,
                        conf=min(cur.conf, nxt.conf),
                        x1=min(cur.x1, nxt.x1),
                        y1=min(cur.y1, nxt.y1),
                        x2=max(cur.x2, nxt.x2),
                        y2=max(cur.y2, nxt.y2),
                        source=cur.source + "+" + nxt.source,
                    )
                )
                i += 2
                continue

        out.append(cur)
        i += 1
    return out



def extract_items(lines: List[OCRLine]) -> List[ReceiptItem]:
    lines = merge_multiline_items(lines)
    items: List[ReceiptItem] = []

    for line in lines:
        text = normalize_text(line.text)
        if looks_like_service_line(text):
            continue
        if not PRICE_RE.search(text):
            continue

        name, price, qty, unit_price = split_name_and_price(text)
        if price is None:
            continue
        if not likely_item_name(name):
            continue

        # Filter obvious non-item totals.
        if name.lower() in HEADER_WORDS:
            continue

        items.append(
            ReceiptItem(
                name=name,
                price=price,
                qty=qty,
                unit_price=unit_price,
                line_text=text,
                confidence=float(line.conf),
                y=float(line.cy),
            )
        )

    # Deduplicate near-identical lines.
    deduped: List[ReceiptItem] = []
    for item in sorted(items, key=lambda x: (x.y, x.name.lower(), x.price)):
        duplicate = False
        for prev in deduped[-3:]:
            same_name = text_similarity(item.name, prev.name) >= 0.85
            same_price = abs(item.price - prev.price) < 0.011
            same_y = abs(item.y - prev.y) < 10
            if same_name and same_price and same_y:
                duplicate = True
                break
        if not duplicate:
            deduped.append(item)

    return deduped



def extract_totals(lines: List[OCRLine]) -> Dict[str, Any]:
    totals: Dict[str, Any] = {}
    for line in lines:
        t = line.text.lower()
        prices = [parse_num(m.group(1)) for m in PRICE_RE.finditer(line.text)]
        prices = [p for p in prices if p is not None]
        if not prices:
            continue
        if "итог" in t and "скид" not in t:
            totals.setdefault("total", prices[-1])
        if "скид" in t:
            totals.setdefault("discount", prices[-1])
        if ("электрон" in t or "карт" in t or "безнал" in t) and "paid" not in totals:
            totals["paid"] = prices[-1]
    return totals


# -----------------------------
# Main pipeline
# -----------------------------


def save_debug_variants(debug_dir: str, variants: Dict[str, np.ndarray]) -> None:
    os.makedirs(debug_dir, exist_ok=True)
    for name, img in variants.items():
        cv2.imwrite(os.path.join(debug_dir, f"{name}.png"), img)



def draw_lines(img: np.ndarray, lines: List[OCRLine], out_path: str) -> None:
    vis = img.copy()
    if len(vis.shape) == 2:
        vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
    for line in lines:
        p1 = (int(line.x1), int(line.y1))
        p2 = (int(line.x2), int(line.y2))
        cv2.rectangle(vis, p1, p2, (0, 255, 0), 2)
        cv2.putText(vis, line.text[:80], (p1[0], max(20, p1[1] - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)
    cv2.imwrite(out_path, vis)



def parse_receipt(image_path: str, lang: str = "ru", debug_dir: Optional[str] = None) -> Dict[str, Any]:
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot open image: {image_path}")

    variants = variants_from_image(img)
    if debug_dir:
        save_debug_variants(debug_dir, variants)

    ocr = make_ocr(lang=lang)

    all_lines: List[OCRLine] = []
    for name, variant in variants.items():
        try:
            lines = run_ocr_on_variant(ocr, variant, source=name)
            all_lines.extend(lines)
        except Exception as e:
            # Continue with other variants.
            print(f"[WARN] OCR failed on variant '{name}': {e}")

    merged = merge_lines(all_lines)
    items = extract_items(merged)
    totals = extract_totals(merged)

    if debug_dir:
        draw_lines(variants["color"], merged, os.path.join(debug_dir, "merged_lines.png"))

    result = {
        "image_path": image_path,
        "items": [asdict(x) for x in items],
        "totals": totals,
        "raw_lines": [asdict(x) for x in merged],
    }
    return result


# -----------------------------
# CLI
# -----------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Robust receipt OCR parser for extracting item-price pairs.")
    parser.add_argument("image", help="Path to receipt image")
    parser.add_argument("--lang", default="ru", help="PaddleOCR language code, e.g. ru, en")
    parser.add_argument("--json-out", default="", help="Where to save JSON output")
    parser.add_argument("--debug-dir", default="", help="Directory for debug images")
    args = parser.parse_args()

    result = parse_receipt(
        args.image,
        lang=args.lang,
        debug_dir=args.debug_dir or None,
    )

    print("=" * 80)
    print("ITEMS")
    print("=" * 80)
    for idx, item in enumerate(result["items"], 1):
        qty = item["qty"] if item["qty"] is not None else "-"
        unit_price = item["unit_price"] if item["unit_price"] is not None else "-"
        print(f"{idx:02d}. {item['name']}")
        print(f"    price={item['price']:.2f}  qty={qty}  unit_price={unit_price}  conf={item['confidence']:.3f}")
        print(f"    raw: {item['line_text']}")

    if result["totals"]:
        print("\n" + "=" * 80)
        print("TOTALS")
        print("=" * 80)
        for k, v in result["totals"].items():
            print(f"{k}: {v}")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nSaved JSON to: {args.json_out}")


if __name__ == "__main__":
    main()
