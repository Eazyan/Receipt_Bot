#!/usr/bin/env python3
"""
Receipt OCR parser focused on extracting item -> price pairs from photographed receipts.

Design goals
------------
- Work with PaddleOCR 2.x and 3.x as far as practical.
- Survive API differences in constructor args and OCR output format.
- Extract deterministic item-price pairs from noisy retail receipts.
- Keep everything in one file.

This is best-effort software. It will not perfectly parse every receipt photo.
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import os
import re
import statistics
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

# Speed up startup for newer PaddleOCR/PaddleX stacks that try to probe model hosts.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from paddleocr import PaddleOCR


# -----------------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# Image preprocessing
# -----------------------------------------------------------------------------


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

    for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:15]:
        area = cv2.contourArea(cnt)
        if area < img_area * 0.12:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
        if len(approx) != 4:
            continue

        rect = order_points(approx.reshape(4, 2).astype("float32"))
        tl, tr, br, bl = rect
        max_w = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
        max_h = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
        if max_w < 100 or max_h < 100:
            continue

        dst = np.array([[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]], dtype="float32")
        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(img, M, (max_w, max_h))
        if max_h / max(max_w, 1) >= 1.05:
            return warped

    return img



def resize_for_ocr(img: np.ndarray, target_width: int = 900, max_width: int = 1100) -> np.ndarray:
    h, w = img.shape[:2]
    if w < target_width:
        scale = target_width / max(w, 1)
        return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    if w > max_width:
        scale = max_width / max(w, 1)
        return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img



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
    if abs(angle) < 0.15:
        return gray

    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)



def variants_from_image(img: np.ndarray) -> Dict[str, np.ndarray]:
    base = maybe_warp_receipt(img)
    base = resize_for_ocr(base)

    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    gray = deskew(gray)

    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    th_otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    return {
        "color": base,
        "gray": cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR),
        "clahe": cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR),
        "th_otsu": cv2.cvtColor(th_otsu, cv2.COLOR_GRAY2BGR),
    }


# -----------------------------------------------------------------------------
# PaddleOCR compatibility layer
# -----------------------------------------------------------------------------


def filter_kwargs_for_callable(func: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    try:
        sig = inspect.signature(func)
    except Exception:
        return kwargs

    accepted = {}
    for k, v in kwargs.items():
        if k in sig.parameters:
            accepted[k] = v
    return accepted



def make_ocr(lang: str = "ru") -> PaddleOCR:
    # PaddleOCR 3.x does not provide PP-OCRv4 models for many non-en/ch languages.
    # Russian is supported by PP-OCRv5 (and historically by PP-OCRv3), so choose version explicitly.
    v5_langs = {
        "ch", "en", "fr", "de", "japan", "korean", "chinese_cht", "af", "it", "es", "bs", "pt",
        "cs", "cy", "da", "et", "ga", "hr", "hu", "rslatin", "id", "oc", "is", "lt", "mi",
        "ms", "nl", "no", "pl", "sk", "sl", "sq", "sv", "sw", "tl", "tr", "uz", "la", "ru",
        "be", "uk"
    }
    ocr_version = "PP-OCRv5" if lang in v5_langs else "PP-OCRv3"

    init_kwargs = {
        "lang": lang,
        # We already deskew and warp the receipt ourselves; keeping these stages off
        # avoids extra CPU-heavy passes in PaddleOCR 3.x.
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        # PaddleOCR 2.x fallback.
        "use_angle_cls": False,
        # Explicitly choose a model family that actually supports the requested language.
        "ocr_version": ocr_version,
        "text_det_limit_side_len": 768,
        "det_limit_side_len": 768,
        "device": "cpu",
    }
    filtered = filter_kwargs_for_callable(PaddleOCR, init_kwargs)
    return PaddleOCR(**filtered)



def normalize_text(s: str) -> str:
    s = str(s).replace("\u00a0", " ")
    s = s.replace("₽", "Р")
    s = s.replace("|", "1") if re.fullmatch(r"[0-9|.,]+", s) else s
    s = s.replace("O", "0") if re.fullmatch(r"[0-9O.,]+", s) else s
    s = re.sub(r"\s+", " ", s).strip()
    return s



def flatten_maybe_nested(obj: Any) -> Iterable[Any]:
    if obj is None:
        return
    if isinstance(obj, (list, tuple)):
        for x in obj:
            yield from flatten_maybe_nested(x)
    else:
        yield obj



def maybe_extract_line_entry(entry: Any, source: str) -> Optional[OCRLine]:
    """
    Handles several PaddleOCR output shapes seen across versions:
    - [box, (text, conf)]
    - [[x,y]...], [text, conf]
    - dict-like structures with keys for text/score/box points
    """
    if entry is None:
        return None

    box = None
    text = None
    conf = None

    if isinstance(entry, dict):
        # Newer pipeline outputs can be dict-like.
        for key in ("text", "rec_text", "transcription"):
            if key in entry:
                text = entry[key]
                break
        for key in ("score", "rec_score", "confidence"):
            if key in entry:
                conf = entry[key]
                break
        for key in ("dt_polys", "box", "bbox", "points", "poly"):
            if key in entry:
                box = entry[key]
                break
    elif isinstance(entry, (list, tuple)) and len(entry) == 2:
        left, right = entry
        # classic [box, (text, conf)]
        if isinstance(left, (list, tuple, np.ndarray)):
            box = left
        if isinstance(right, (list, tuple)) and len(right) >= 2:
            text, conf = right[0], right[1]
        elif isinstance(right, dict):
            text = right.get("text") or right.get("rec_text")
            conf = right.get("score") or right.get("rec_score")
    elif isinstance(entry, (list, tuple)) and len(entry) >= 3:
        # possible [text, score, box] shapes
        maybe_text, maybe_conf, maybe_box = entry[0], entry[1], entry[2]
        if isinstance(maybe_text, str) and isinstance(maybe_box, (list, tuple, np.ndarray)):
            text, conf, box = maybe_text, maybe_conf, maybe_box

    if text is None or box is None:
        return None

    text = normalize_text(text)
    if not text:
        return None

    try:
        pts = np.array(box, dtype=float).reshape(-1, 2)
    except Exception:
        return None
    if len(pts) < 2:
        return None

    x1 = float(np.min(pts[:, 0]))
    y1 = float(np.min(pts[:, 1]))
    x2 = float(np.max(pts[:, 0]))
    y2 = float(np.max(pts[:, 1]))
    conf_f = float(conf) if conf is not None else 0.5

    return OCRLine(text=text, conf=conf_f, x1=x1, y1=y1, x2=x2, y2=y2, source=source)


def extract_lines_from_ocr_result(result: Any, source: str) -> List[OCRLine]:
    if not isinstance(result, dict):
        return []

    texts = result.get("rec_texts")
    scores = result.get("rec_scores")
    polys = result.get("dt_polys") or result.get("rec_polys") or result.get("rec_boxes")
    if not isinstance(texts, list) or not isinstance(scores, list) or not isinstance(polys, list):
        return []

    out: List[OCRLine] = []
    for text, score, poly in zip(texts, scores, polys):
        line = maybe_extract_line_entry({"text": text, "score": score, "dt_polys": poly}, source)
        if line is not None:
            out.append(line)
    return out



def call_ocr_compat(ocr: PaddleOCR, img: np.ndarray) -> Any:
    """Try several calling conventions across PaddleOCR versions."""
    try:
        return ocr.predict(img)
    except TypeError:
        pass
    try:
        return ocr.ocr(img)
    except TypeError:
        return ocr.ocr(img, cls=False)



def run_ocr_on_variant(ocr: PaddleOCR, img: np.ndarray, source: str) -> List[OCRLine]:
    result = call_ocr_compat(ocr, img)
    lines: List[OCRLine] = []
    if result is None:
        return lines

    if isinstance(result, (list, tuple)):
        for entry in result:
            lines.extend(extract_lines_from_ocr_result(entry, source))
    else:
        lines.extend(extract_lines_from_ocr_result(result, source))

    # Flatten and extract any recognizable line entries.
    for entry in flatten_maybe_nested(result):
        line = maybe_extract_line_entry(entry, source)
        if line is not None:
            lines.append(line)

    # Deduplicate raw lines from one variant.
    dedup: List[OCRLine] = []
    for line in sorted(lines, key=lambda x: (round(x.cy, 1), round(x.cx, 1), -x.conf)):
        is_dup = False
        for prev in dedup[-5:]:
            if abs(line.cy - prev.cy) < 4 and abs(line.cx - prev.cx) < 10 and normalize_text(line.text).lower() == normalize_text(prev.text).lower():
                is_dup = True
                break
        if not is_dup:
            dedup.append(line)
    return dedup


# -----------------------------------------------------------------------------
# OCR merging and row grouping
# -----------------------------------------------------------------------------


def text_similarity(a: str, b: str) -> float:
    a = re.sub(r"\s+", " ", a.lower()).strip()
    b = re.sub(r"\s+", " ", b.lower()).strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sa = set(a.split())
    sb = set(b.split())
    j = len(sa & sb) / max(1, len(sa | sb))
    prefix_len = min(12, len(a), len(b))
    prefix = 1.0 if prefix_len and a[:prefix_len] == b[:prefix_len] else 0.0
    return max(j, prefix * 0.8)



def merge_lines(all_lines: List[OCRLine]) -> List[OCRLine]:
    if not all_lines:
        return []

    all_lines = sorted(all_lines, key=lambda x: (x.cy, x.cx))
    median_h = statistics.median(max(8.0, x.h) for x in all_lines)
    y_tol = max(10.0, median_h * 0.7)
    x_tol = max(50.0, statistics.median(max(30.0, x.w * 0.35) for x in all_lines))

    groups: List[List[OCRLine]] = []
    for line in all_lines:
        placed = False
        for g in groups:
            gy = statistics.mean(z.cy for z in g)
            gx = statistics.mean(z.cx for z in g)
            if abs(line.cy - gy) <= y_tol and abs(line.cx - gx) <= x_tol:
                if text_similarity(line.text, g[0].text) >= 0.42:
                    g.append(line)
                    placed = True
                    break
        if not placed:
            groups.append([line])

    merged: List[OCRLine] = []
    for g in groups:
        best = max(g, key=lambda line: line.conf + 0.04 * sum(1 for other in g if text_similarity(line.text, other.text) >= 0.7))
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


def collapse_to_rows(lines: List[OCRLine]) -> List[OCRLine]:
    if not lines:
        return []

    lines = sorted(lines, key=lambda x: (x.cy, x.x1))
    median_h = statistics.median(max(8.0, line.h) for line in lines)
    y_tol = max(8.0, median_h * 0.7)

    rows: List[List[OCRLine]] = []
    for line in lines:
        placed = False
        for row in rows:
            row_y = statistics.mean(x.cy for x in row)
            if abs(line.cy - row_y) <= y_tol:
                row.append(line)
                placed = True
                break
        if not placed:
            rows.append([line])

    collapsed: List[OCRLine] = []
    for row in rows:
        tokens = sorted(row, key=lambda x: x.x1)
        parts: List[str] = []
        prev_x2: Optional[float] = None
        for token in tokens:
            token_text = normalize_text(token.text)
            if not token_text:
                continue
            if parts and prev_x2 is not None and token.x1 - prev_x2 > max(14.0, token.h * 0.7):
                parts.append(" ")
            parts.append(token_text)
            prev_x2 = token.x2

        text = "".join(parts).strip()
        if not text:
            continue

        collapsed.append(
            OCRLine(
                text=text,
                conf=float(statistics.mean(x.conf for x in tokens)),
                x1=min(x.x1 for x in tokens),
                y1=min(x.y1 for x in tokens),
                x2=max(x.x2 for x in tokens),
                y2=max(x.y2 for x in tokens),
                source="+".join(sorted({x.source for x in tokens})),
            )
        )

    collapsed.sort(key=lambda x: (x.cy, x.x1))
    return collapsed


# -----------------------------------------------------------------------------
# Receipt heuristics
# -----------------------------------------------------------------------------

PRICE_RE = re.compile(r"(?<!\d)(\d{1,5}[.,]\d{2})(?!\d)")
WEIGHT_RE = re.compile(r"(?<!\d)(\d+[.,]\d{3})\s*(?:кг|kg)(?!\w)", re.IGNORECASE)
QTY_RE = re.compile(r"(?<!\d)(\d+[.,]?\d*)\s*(?:шт|шТ|kg|кг|l|л|x|х)(?!\w)", re.IGNORECASE)

HEADER_WORDS = {
    "итог", "сумма", "скидка", "баланс", "бонус", "кассир", "кассовый", "чек", "приход",
    "безналичными", "электронными", "получено", "плат", "карта", "ндс", "место", "расчетов",
    "магазин", "инн", "сайт", "офд", "фн", "фд", "рн", "зн", "смена", "карта", "начислено",
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
        r"^qr",
        r"^www\.",
        r"^http",
    ]
]



def parse_num(s: str) -> Optional[float]:
    try:
        return float(str(s).replace(",", "."))
    except Exception:
        return None



def looks_like_service_line(text: str) -> bool:
    t = normalize_text(text).lower().strip()
    if len(t) <= 1:
        return True
    if sum(ch.isdigit() for ch in t) >= max(8, len(t) * 0.72):
        return True
    for rx in STOP_LINE_PATTERNS:
        if rx.search(t):
            return True
    return False



def likely_item_name(name: str) -> bool:
    t = normalize_text(name).lower().strip(" -_.,:;")
    if len(t) < 2:
        return False
    if any(w in t.split() for w in HEADER_WORDS):
        return False
    letters = sum(ch.isalpha() for ch in t)
    digits = sum(ch.isdigit() for ch in t)
    return letters >= 2 and letters >= digits * 0.5



def split_name_and_price(line_text: str) -> Tuple[str, Optional[float], Optional[float], Optional[float]]:
    text = normalize_text(line_text)
    prices = list(PRICE_RE.finditer(text))
    if not prices:
        return text, None, None, None

    final_match = prices[-1]
    final_price = parse_num(final_match.group(1))
    left = text[:final_match.start()].rstrip(" .,-:;")

    qty = None
    unit_price = None

    q = QTY_RE.search(left)
    if q:
        qty = parse_num(q.group(1))
        left = (left[:q.start()] + " " + left[q.end():]).strip()

    w = WEIGHT_RE.search(left)
    if w:
        qty = parse_num(w.group(1))
        left = (left[:w.start()] + " " + left[w.end():]).strip()

    if len(prices) >= 2:
        prev = prices[-2]
        unit_price = parse_num(prev.group(1))
        if prev.end() >= max(0, final_match.start() - 20):
            left = (text[:prev.start()] + text[prev.end():final_match.start()]).strip()

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
            same_block = abs(nxt.cy - cur.cy) <= max(cur.h, nxt.h) * 1.9
            if same_block and PRICE_RE.search(nxt.text):
                out.append(
                    OCRLine(
                        text=f"{cur.text} {nxt.text}",
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
        if price is None or not likely_item_name(name):
            continue
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

    deduped: List[ReceiptItem] = []
    for item in sorted(items, key=lambda x: (x.y, x.name.lower(), x.price)):
        duplicate = False
        for prev in deduped[-5:]:
            same_name = text_similarity(item.name, prev.name) >= 0.85
            same_price = abs(item.price - prev.price) < 0.011
            same_y = abs(item.y - prev.y) < 12
            if same_name and same_price and same_y:
                duplicate = True
                break
        if not duplicate:
            deduped.append(item)

    return deduped



def extract_totals(lines: List[OCRLine]) -> Dict[str, Any]:
    totals: Dict[str, Any] = {}
    for line in lines:
        t = normalize_text(line.text).lower()
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


# -----------------------------------------------------------------------------
# Debug helpers
# -----------------------------------------------------------------------------


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


# -----------------------------------------------------------------------------
# Pipeline
# -----------------------------------------------------------------------------


def parse_receipt(image_path: str, lang: str = "ru", debug_dir: Optional[str] = None) -> Dict[str, Any]:
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot open image: {image_path}")

    variants = variants_from_image(img)
    if debug_dir:
        save_debug_variants(debug_dir, variants)

    ocr = make_ocr(lang=lang)

    all_lines: List[OCRLine] = []
    errors: List[str] = []
    preferred_variant_order = ("color", "gray", "clahe", "th_otsu")
    for name in preferred_variant_order:
        variant = variants[name]
        try:
            all_lines.extend(run_ocr_on_variant(ocr, variant, source=name))
        except Exception as e:
            errors.append(f"variant={name}: {e}")
            print(f"[WARN] OCR failed on variant '{name}': {e}")

    merged = merge_lines(all_lines)
    row_lines = collapse_to_rows(merged)
    items = extract_items(row_lines)
    totals = extract_totals(row_lines)

    if debug_dir:
        draw_lines(variants["color"], row_lines, os.path.join(debug_dir, "merged_lines.png"))

    return {
        "image_path": image_path,
        "items": [asdict(x) for x in items],
        "totals": totals,
        "raw_lines": [asdict(x) for x in row_lines],
        "warnings": errors,
    }


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Receipt OCR parser for item-price extraction.")
    parser.add_argument("image", help="Path to receipt image")
    parser.add_argument("--lang", default="ru", help="PaddleOCR language code, e.g. ru, en")
    parser.add_argument("--json-out", default="", help="Where to save JSON output")
    parser.add_argument("--debug-dir", default="", help="Directory for debug images")
    args = parser.parse_args()

    result = parse_receipt(args.image, lang=args.lang, debug_dir=args.debug_dir or None)

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

    if result["warnings"]:
        print("\n" + "=" * 80)
        print("WARNINGS")
        print("=" * 80)
        for w in result["warnings"]:
            print(w)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nSaved JSON to: {args.json_out}")


if __name__ == "__main__":
    main()
