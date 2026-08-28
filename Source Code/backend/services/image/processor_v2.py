"""
SIAR Digital Image Processor v4.5.2
Cross-Platform (Windows/macOS/Linux)
Advanced AI-Powered Image Resizing Engine

Features:
✓ Pose AI (SOTA) - YOLOv8m-pose skeleton detection
✓ Fashion Consistent - Fixed head/foot placement for e-commerce
✓ Smart Crop (AI) - Intelligent subject detection
✓ Mirror BG - Smart background fill
✓ AI Background Extend - Canvas extension
✓ Quality Guard - Auto-optimize to 3MB
✓ Batch processing with multi-threading
✓ Head/Foot space user adjustment (2-12% / 1-10%)
✓ Watermark removal via rembg
✓ Audit reporting (CSV + Excel)

Created by: Asif Nawaz | Siar Digital 2026
"""

import os
import sys
import gc
import platform
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
import io
import csv

try:
    from PIL import Image, ImageOps, ImageFilter, ImageDraw, ImageEnhance
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    cv2 = None
    np = None

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False
    YOLO = None

try:
    from rembg import remove as rembg_remove, new_session as rembg_new_session
    HAS_REMBG = True
except ImportError:
    HAS_REMBG = False
    rembg_remove = None

try:
    import openpyxl
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

log = logging.getLogger('siar.image.v2')

# ─────────────────────────────────────────────────────────────────────────────
#  Platform Detection & Resource Management
# ─────────────────────────────────────────────────────────────────────────────
_OS = platform.system()  # 'Windows', 'Darwin' (macOS), 'Linux'
_FONT_MONO = {
    'Darwin': 'Menlo',
    'Windows': 'Consolas',
    'Linux': 'DejaVu Sans Mono'
}.get(_OS, 'DejaVu Sans Mono')

log.info(f"Platform: {_OS} | Font: {_FONT_MONO}")

def _resource(relative_path):
    """Get bundled resource path (PyInstaller compatible)"""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)

# ─────────────────────────────────────────────────────────────────────────────
#  Model Caching (Thread-Safe)
# ─────────────────────────────────────────────────────────────────────────────
_model_cache = {}
_model_lock = threading.Lock()

def _get_yolo():
    """Thread-safe YOLO model loader (caches in memory)"""
    if 'yolov8n' not in _model_cache:
        with _model_lock:
            if 'yolov8n' not in _model_cache:
                if not HAS_YOLO:
                    return None
                try:
                    bundled = _resource('yolov8n.pt')
                    path = bundled if os.path.exists(bundled) else 'yolov8n.pt'
                    _model_cache['yolov8n'] = YOLO(path)
                    log.info(f"YOLOv8n loaded: {path}")
                except Exception as e:
                    log.warning(f"YOLOv8n load failed: {e}")
                    return None
    return _model_cache.get('yolov8n')

def _get_pose_model():
    """Thread-safe Pose model loader"""
    if 'yolov8m-pose' not in _model_cache:
        with _model_lock:
            if 'yolov8m-pose' not in _model_cache:
                if not HAS_YOLO:
                    return None
                try:
                    bundled = _resource('yolov8m-pose.pt')
                    path = bundled if os.path.exists(bundled) else 'yolov8m-pose.pt'
                    _model_cache['yolov8m-pose'] = YOLO(path)
                    log.info(f"YOLOv8m-pose loaded: {path}")
                except Exception as e:
                    log.warning(f"YOLOv8m-pose load failed: {e}")
                    return None
    return _model_cache.get('yolov8m-pose')

# ─────────────────────────────────────────────────────────────────────────────
#  rembg Session (Lazy-loaded)
# ─────────────────────────────────────────────────────────────────────────────
_rembg_session = None

def _get_rembg_session():
    """Lazy-load rembg session"""
    global _rembg_session
    if _rembg_session is None and HAS_REMBG:
        try:
            _rembg_session = rembg_new_session('u2net')
            log.info("rembg session initialized")
        except Exception as e:
            log.warning(f"rembg init failed: {e}")
    return _rembg_session

# ─────────────────────────────────────────────────────────────────────────────
#  File Scanner (macOS ._ file skip)
# ─────────────────────────────────────────────────────────────────────────────
SUPPORTED_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.tiff', '.tif', '.bmp', '.ppm')
QUALITY_LIMIT_KB = 3072

def scan_image_files(input_path):
    """Recursively find images, skip macOS hidden files"""
    input_path = os.path.normpath(os.path.abspath(input_path))
    results = []
    for root, dirs, files in os.walk(input_path):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            # Skip macOS ._* and .* files
            if fname.startswith('._') or fname.startswith('.'):
                continue
            if fname.lower().endswith(SUPPORTED_EXTS):
                abs_path = os.path.normpath(os.path.join(root, fname))
                rel_path = os.path.relpath(abs_path, input_path)
                results.append((abs_path, rel_path))
    return results

# ─────────────────────────────────────────────────────────────────────────────
#  Pose AI Detection (v4.6.1 - Head Space Default = 5%)
# ─────────────────────────────────────────────────────────────────────────────
_POSE_KP = {
    "nose": 0, "left_eye": 1, "right_eye": 2, "left_ear": 3, "right_ear": 4,
    "left_shoulder": 5, "right_shoulder": 6, "left_elbow": 7, "right_elbow": 8,
    "left_wrist": 9, "right_wrist": 10, "left_hip": 11, "right_hip": 12,
    "left_knee": 13, "right_knee": 14, "left_ankle": 15, "right_ankle": 16,
}
_POSE_KP_CONF = 0.30
_POSE_DARK_THR = 80
_POSE_HEAD_SPACE_DEFAULT = 0.05  # 5% (v4.6.1 changed from 10%)
_POSE_FOOT_SPACE_DEFAULT = 0.05  # 5%

def _slide_into_range(p1, p2, dim_max):
    """
    Slide window [p1, p2) to fit inside [0, dim_max] while preserving size.
    This is the v4.6 "FIX 12" fix for aspect ratio preservation.
    """
    size = p2 - p1
    if size >= dim_max:
        return 0.0, float(dim_max)
    if p1 < 0:
        p2 -= p1
        p1 = 0.0
    if p2 > dim_max:
        p1 -= (p2 - dim_max)
        p2 = dim_max
    p1 = max(0.0, p1)
    p2 = p1 + size
    return p1, p2

def _pose_kp_xy(kps, name):
    """Extract keypoint (x, y) if confidence is high"""
    idx = _POSE_KP[name]
    if kps.shape[0] <= idx:
        return None
    x, y, conf = kps[idx]
    return (float(x), float(y)) if conf >= _POSE_KP_CONF else None

def _pose_extract(kps, img_h, img_w, bbox=None):
    """Extract pose geometry from skeleton"""
    nose = _pose_kp_xy(kps, "nose")
    if nose is None:
        fallbacks = ["left_eye", "right_eye", "left_ear", "right_ear"]
        ys = [_pose_kp_xy(kps, n)[1] for n in fallbacks if _pose_kp_xy(kps, n)]
        if not ys:
            return None
        nose_y = float(np.mean(ys))
        nose_x = float(np.mean([_pose_kp_xy(kps, n)[0] for n in fallbacks
                                  if _pose_kp_xy(kps, n)]))
    else:
        nose_x, nose_y = nose

    bbox_by1 = float(bbox[1]) if bbox else None
    bbox_by2 = float(bbox[3]) if bbox else None

    if bbox_by1 is not None and bbox_by1 < nose_y:
        head_top_y, offset_frac = bbox_by1, 0.02
    else:
        head_top_y, offset_frac = nose_y, 0.10

    feet_y = None
    for name in ["left_ankle", "right_ankle", "left_knee", "right_knee"]:
        pt = _pose_kp_xy(kps, name)
        if pt and (feet_y is None or pt[1] > feet_y):
            feet_y = pt[1]
    if bbox_by2 is not None:
        feet_y = max(feet_y, bbox_by2) if feet_y else bbox_by2
    if feet_y is None:
        hip_pts = [_pose_kp_xy(kps, n) for n in ["left_hip", "right_hip"]
                   if _pose_kp_xy(kps, n)]
        if hip_pts:
            hip_y = float(np.mean([p[1] for p in hip_pts]))
            feet_y = min(nose_y + (hip_y - nose_y) * 2.1, float(img_h))
        else:
            valid_ys = [kps[i, 1] for i in range(kps.shape[0]) if kps[i, 2] >= _POSE_KP_CONF]
            if not valid_ys:
                return None
            feet_y = float(max(valid_ys))

    center_kps = ["left_shoulder", "right_shoulder", "left_hip", "right_hip"]
    cxs = [_pose_kp_xy(kps, n)[0] for n in center_kps if _pose_kp_xy(kps, n)]
    center_x = float(np.mean(cxs)) if cxs else nose_x

    valid_xs = [kps[i, 0] for i in range(kps.shape[0]) if kps[i, 2] >= _POSE_KP_CONF]
    if bbox:
        valid_xs = [float(bbox[0]), float(bbox[2])] + valid_xs
    body_left = float(min(valid_xs)) if valid_xs else max(0.0, center_x - 50)
    body_right = float(max(valid_xs)) if valid_xs else min(float(img_w), center_x + 50)

    return {
        "head_top_y": head_top_y,
        "feet_y": feet_y,
        "center_x": center_x,
        "body_left": body_left,
        "body_right": body_right,
        "offset_frac": offset_frac,
    }

def _bbox_mean_brightness(img_bgr, bx1, by1, bx2, by2):
    """Mean V-channel brightness for bbox (0-255)"""
    x1 = max(0, int(bx1)); y1 = max(0, int(by1))
    x2 = min(img_bgr.shape[1], int(bx2)); y2 = min(img_bgr.shape[0], int(by2))
    if x2 <= x1 or y2 <= y1:
        return 0.0
    roi = img_bgr[y1:y2, x1:x2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean())

def _pose_run_yolo(model, img_bgr, conf, img_h, img_w):
    """
    Run pose & score by brightness to reject shadows (FIX 10).
    Returns best pose or None.
    """
    _POSE_MIN_BRIGHTNESS = 45
    _BRIGHTNESS_WEIGHT = 2.0

    results = model(img_bgr, conf=conf, verbose=False, task="pose")
    candidates = []

    for r in results:
        if r.keypoints is None:
            continue
        kps_all = r.keypoints.data.cpu().numpy()
        boxes = r.boxes.xyxy.cpu().numpy() if r.boxes is not None else None
        for idx in range(kps_all.shape[0]):
            kps = kps_all[idx]
            bbox = None
            area = float(img_h * img_w)
            brightness = 128.0
            if boxes is not None and idx < len(boxes):
                bx1, by1, bx2, by2 = boxes[idx]
                area = (bx2 - bx1) * (by2 - by1)
                brightness = _bbox_mean_brightness(img_bgr, bx1, by1, bx2, by2)
                bbox = (float(bx1), float(by1), float(bx2), float(by2))
            pose = _pose_extract(kps, img_h, img_w, bbox)
            if pose is None:
                continue
            norm_area = area / max(img_h * img_w, 1)
            score = norm_area * (brightness / 255.0) ** _BRIGHTNESS_WEIGHT
            candidates.append((score, brightness, pose))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_brightness, best_pose = candidates[0]

    if best_brightness < _POSE_MIN_BRIGHTNESS:
        log.info(f"Pose: rejected dim detection (brightness={best_brightness:.1f})")
        return None

    return best_pose

# ─────────────────────────────────────────────────────────────────────────────
#  Placement Engines
# ─────────────────────────────────────────────────────────────────────────────
def engine_smart_crop(img, tw, th, category="General"):
    """Smart Crop with AI detection"""
    if not HAS_OPENCV or not HAS_YOLO:
        return ImageOps.fit(img, (tw, th), Image.Resampling.LANCZOS, centering=(0.5, 0.5))

    try:
        model = _get_yolo()
        if not model:
            return ImageOps.fit(img, (tw, th), Image.Resampling.LANCZOS, centering=(0.5, 0.5))

        iw, ih = img.size
        cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        results = model(cv_img, verbose=False)

        if not results or not results[0].boxes:
            return ImageOps.fit(img, (tw, th), Image.Resampling.LANCZOS, centering=(0.5, 0.5))

        # Pick largest box
        boxes = results[0].boxes.xyxy.cpu().numpy()
        if len(boxes) == 0:
            return ImageOps.fit(img, (tw, th), Image.Resampling.LANCZOS, centering=(0.5, 0.5))

        best_idx = np.argmax([(b[2]-b[0])*(b[3]-b[1]) for b in boxes])
        x1, y1, x2, y2 = boxes[best_idx]

        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        bw = x2 - x1
        bh = y2 - y1

        # Smart crop logic
        target_ratio = tw / th
        crop_h = bh * 1.5
        crop_w = crop_h * target_ratio

        if crop_w > iw:
            crop_w = iw
            crop_h = crop_w / target_ratio

        crop_left = cx - crop_w / 2
        crop_top = cy - crop_h / 2.5  # Head space

        crop_left = max(0, min(crop_left, iw - crop_w))
        crop_top = max(0, min(crop_top, ih - crop_h))

        cropped = img.crop((int(crop_left), int(crop_top),
                           int(crop_left + crop_w), int(crop_top + crop_h)))
        return cropped.resize((tw, th), Image.Resampling.LANCZOS)
    except Exception as e:
        log.warning(f"Smart crop error: {e}")
        return ImageOps.fit(img, (tw, th), Image.Resampling.LANCZOS, centering=(0.5, 0.5))

def engine_fashion_consistent(img, tw, th, category="General"):
    """Fashion Consistent v12 - Fixed head/foot placement"""
    if not HAS_OPENCV:
        return engine_smart_crop(img, tw, th, category)

    try:
        HEAD_TOP_PCT = 0.07
        FEET_BOT_PCT = 0.02
        iw, ih = img.size

        # Resize for detection
        small = img.convert("RGB").resize((800, 1200), Image.Resampling.LANCZOS)
        cv_small = cv2.cvtColor(np.array(small), cv2.COLOR_RGB2BGR)

        # Simple face detection fallback
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        gray = cv2.cvtColor(cv_small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 100))

        if len(faces) == 0:
            return engine_smart_crop(img, tw, th, category)

        fx, fy, fw, fh = faces[0]
        sx, sy = iw / 800.0, ih / 1200.0

        head_top = int((fy - fh * 0.45) * sy)
        head_top = max(0, head_top)
        person_h = ih - head_top

        target_h = int(th * (1.0 - HEAD_TOP_PCT - FEET_BOT_PCT))
        scale = target_h / max(person_h, 1)

        scaled_iw = int(iw * scale)
        scaled_ih = int(ih * scale)

        if scaled_iw < tw:
            scale = tw / iw
            scaled_iw = tw
            scaled_ih = int(ih * scale)

        scaled = img.resize((scaled_iw, scaled_ih), Image.Resampling.LANCZOS)

        crop_top = int(head_top * scale) - int(th * HEAD_TOP_PCT)
        crop_top = max(0, min(crop_top, scaled_ih - th))
        crop_left = max(0, min(scaled_iw // 2 - tw // 2, scaled_iw - tw))

        result = scaled.crop((crop_left, crop_top, crop_left + tw, crop_top + th))
        if result.size != (tw, th):
            result = result.resize((tw, th), Image.Resampling.LANCZOS)

        return result
    except Exception as e:
        log.warning(f"Fashion consistent error: {e}")
        return engine_smart_crop(img, tw, th, category)

def engine_mirror_bg(img, tw, th):
    """Mirror BG - Blur & blend"""
    bg = ImageOps.fit(img.copy(), (tw, th), Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=28))
    bg = Image.blend(bg, Image.new("RGB", (tw, th), (0, 0, 0)), alpha=0.35)
    thumb = img.copy()
    thumb.thumbnail((tw, th), Image.Resampling.LANCZOS)
    bg.paste(thumb, ((tw - thumb.width) // 2, (th - thumb.height) // 2))
    return bg

def engine_fill_crop(img, tw, th):
    """Fill Crop - Center crop"""
    return ImageOps.fit(img, (tw, th), Image.Resampling.LANCZOS, centering=(0.5, 0.5))

def engine_letterbox_dark(img, tw, th):
    """Letterbox with dark background"""
    canvas = Image.new("RGB", (tw, th), (12, 14, 20))
    thumb = img.copy()
    thumb.thumbnail((tw, th), Image.Resampling.LANCZOS)
    canvas.paste(thumb, ((tw - thumb.width) // 2, (th - thumb.height) // 2))
    return canvas

def engine_letterbox_white(img, tw, th):
    """Letterbox with white background"""
    canvas = Image.new("RGB", (tw, th), (255, 255, 255))
    thumb = img.copy()
    thumb.thumbnail((tw, th), Image.Resampling.LANCZOS)
    canvas.paste(thumb, ((tw - thumb.width) // 2, (th - thumb.height) // 2))
    return canvas

def engine_stretch(img, tw, th):
    """Stretch to exact dimensions"""
    return img.resize((tw, th), Image.Resampling.LANCZOS)

def engine_pose_ai(img, tw, th, head_space_pct=None, foot_space_pct=None):
    """
    Pose AI (SOTA) v4.6.1 - Head space default 5%
    Never pads/mirrors - uses only real pixels within image bounds.
    """
    if not HAS_YOLO or not HAS_OPENCV:
        return engine_fill_crop(img, tw, th)

    model = _get_pose_model()
    if not model:
        return engine_fill_crop(img, tw, th)

    try:
        head_space_pct = _POSE_HEAD_SPACE_DEFAULT if head_space_pct is None else head_space_pct
        foot_space_pct = _POSE_FOOT_SPACE_DEFAULT if foot_space_pct is None else foot_space_pct

        img_bgr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        img_h, img_w = img_bgr.shape[:2]

        # Run pose detection
        pose = _pose_run_yolo(model, img_bgr, 0.35, img_h, img_w)

        if pose is None:
            return engine_fill_crop(img, tw, th)

        # Compute crop
        target_aspect = tw / th
        person_h = max(pose["feet_y"] - pose["head_top_y"], 1.0)
        head_offset_px = pose["offset_frac"] * person_h
        adj_head_y = pose["head_top_y"] - head_offset_px
        person_display_h = pose["feet_y"] - adj_head_y

        content_frac = max(1.0 - head_space_pct - foot_space_pct, 0.20)
        crop_h = person_display_h / content_frac
        crop_w = crop_h * target_aspect

        # Body-width guarantee
        body_w = pose["body_right"] - pose["body_left"]
        min_crop_w = body_w * 1.20
        if crop_w < min_crop_w:
            candidate_w = min_crop_w
            candidate_h = candidate_w / target_aspect
            if candidate_h <= img_h:
                crop_w, crop_h = candidate_w, candidate_h

        # Never exceed image dimensions
        if crop_h > img_h or crop_w > img_w:
            scale = min(img_h / crop_h, img_w / crop_w, 1.0)
            crop_h *= scale
            crop_w *= scale

        # Slide into range (v4.6 FIX 12)
        crop_top = adj_head_y - head_space_pct * crop_h
        crop_bottom = crop_top + crop_h
        crop_top, crop_bottom = _slide_into_range(crop_top, crop_bottom, img_h)

        crop_left = pose["center_x"] - crop_w / 2.0
        crop_right = crop_left + crop_w
        crop_left, crop_right = _slide_into_range(crop_left, crop_right, img_w)

        # Crop & resize
        x1, y1 = int(round(crop_left)), int(round(crop_top))
        x2, y2 = int(round(crop_right)), int(round(crop_bottom))

        cropped = Image.fromarray(cv2.cvtColor(img_bgr[y1:y2, x1:x2], cv2.COLOR_BGR2RGB))
        return cropped.resize((tw, th), Image.Resampling.LANCZOS)
    except Exception as e:
        log.warning(f"Pose AI error: {e}")
        return engine_fill_crop(img, tw, th)

MODE_MAP = {
    "Smart Crop (AI)": engine_smart_crop,
    "Fashion Consistent (AI)": engine_fashion_consistent,
    "Mirror BG (Smart Fill)": engine_mirror_bg,
    "Fill & Crop (Center)": engine_fill_crop,
    "Letterbox (Dark BG)": engine_letterbox_dark,
    "Letterbox (White BG)": engine_letterbox_white,
    "Stretch to Fit": engine_stretch,
    "Pose AI (SOTA)": engine_pose_ai,
}

# ─────────────────────────────────────────────────────────────────────────────
#  Quality Guard (v4.5.2)
# ─────────────────────────────────────────────────────────────────────────────
def save_with_quality_guard(img, out_path, fmt, initial_quality, lossless):
    """Save with automatic quality optimization to 3MB limit"""
    ext = fmt.lower()
    if lossless or ext == 'png':
        img.save(out_path, format="PNG", compress_level=9, optimize=True)
        return

    quality = initial_quality
    while quality >= 50:
        buf = io.BytesIO()
        if ext == "webp":
            img.save(buf, format="WEBP", quality=quality, method=6, lossless=(quality >= 95))
        elif ext in ("jpg", "jpeg"):
            img.save(buf, format="JPEG", quality=quality, optimize=True,
                     progressive=True, subsampling="4:4:4")
        elif ext == "tiff":
            img.save(buf, format="TIFF", compression="lzw" if quality < 90 else "none")
        else:
            img.save(buf, format=ext.upper())

        size_kb = buf.tell() / 1024
        if size_kb <= QUALITY_LIMIT_KB or ext == "bmp":
            buf.seek(0)
            with open(out_path, "wb") as f:
                f.write(buf.read())
            return
        quality -= 5

    buf.seek(0)
    with open(out_path, "wb") as f:
        f.write(buf.read())

# ─────────────────────────────────────────────────────────────────────────────
#  Main Processor Class
# ─────────────────────────────────────────────────────────────────────────────
class ImageProcessor:
    """Core SIAR Digital Image Processor v4.5.2"""

    def __init__(self, max_workers=4):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        log.info(f"ImageProcessor v4.5.2 initialized | OS={_OS} | Workers={max_workers}")

    def process_single(self, input_path, output_path, tw, th, mode="Smart Crop (AI)",
                      fmt="JPEG", quality=85, lossless=False, category="General",
                      remove_watermark=False, head_space_pct=None, foot_space_pct=None):
        """Process single image with all advanced options"""
        try:
            if not os.path.isfile(input_path):
                return {
                    'status': 'error',
                    'file': os.path.basename(input_path),
                    'error': 'Source file not found'
                }

            # Load & prep
            with Image.open(input_path) as raw:
                try:
                    raw = ImageOps.exif_transpose(raw)
                except:
                    pass
                img = raw.copy()

            orig_w, orig_h = img.size
            orig_size_kb = os.path.getsize(input_path) / 1024

            # Convert to RGB
            if img.mode in ("P", "PA"):
                img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                try:
                    bg.paste(img, mask=img.split()[-1])
                except:
                    bg.paste(img)
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Remove watermark if requested
            if remove_watermark and HAS_REMBG:
                try:
                    session = _get_rembg_session()
                    cleaned = rembg_remove(img, session=session)
                    if cleaned.mode == "RGBA":
                        bg2 = Image.new("RGB", cleaned.size, (255, 255, 255))
                        bg2.paste(cleaned, mask=cleaned.split()[-1])
                        img = bg2
                    else:
                        img = cleaned.convert("RGB")
                except Exception as e:
                    log.warning(f"Watermark removal failed: {e}")

            # Apply engine
            engine_fn = MODE_MAP.get(mode, engine_fill_crop)
            if mode == "Pose AI (SOTA)":
                result = engine_fn(img, tw, th, head_space_pct=head_space_pct,
                                 foot_space_pct=foot_space_pct)
            else:
                result = engine_fn(img, tw, th, category=category)

            del img
            gc.collect()

            # Save with quality guard
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            save_with_quality_guard(result, output_path, fmt, quality, lossless)

            new_size_kb = os.path.getsize(output_path) / 1024

            log.info(f"✓ {os.path.basename(input_path)}: "
                    f"{orig_w}x{orig_h} → {tw}x{th} ({new_size_kb:.1f}KB)")

            return {
                'status': 'success',
                'file': os.path.basename(input_path),
                'original_dims': f"{orig_w}x{orig_h}",
                'original_size_kb': f"{orig_size_kb:.2f}",
                'resized_size_kb': f"{new_size_kb:.2f}",
                'error': ''
            }
        except Exception as e:
            log.error(f"✗ {os.path.basename(input_path)}: {e}")
            return {
                'status': 'error',
                'file': os.path.basename(input_path),
                'error': str(e)
            }

    def batch_process(self, input_dir, output_dir, tw, th, mode="Smart Crop (AI)",
                     fmt="JPEG", quality=85, lossless=False, turbo=False,
                     category="General", remove_watermark=False,
                     head_space_pct=None, foot_space_pct=None, progress_callback=None):
        """Batch process directory"""
        input_path = os.path.normpath(os.path.abspath(input_dir))
        output_path = os.path.normpath(os.path.abspath(output_dir))
        os.makedirs(output_path, exist_ok=True)

        files = scan_image_files(input_path)
        total = len(files)

        if total == 0:
            log.warning(f"No images found in {input_dir}")
            return {
                'status': 'no_images',
                'total': 0,
                'processed': 0,
                'failed': 0,
                'results': []
            }

        results = []
        processed = 0
        failed = 0
        start_time = datetime.now()

        def _process(abs_path, rel_path):
            out_dir = os.path.join(output_path, os.path.dirname(rel_path))
            os.makedirs(out_dir, exist_ok=True)
            basename = os.path.basename(rel_path)
            out_file = os.path.join(out_dir, basename)

            return self.process_single(abs_path, out_file, tw, th, mode,
                                      fmt, quality, lossless, category,
                                      remove_watermark, head_space_pct, foot_space_pct)

        if turbo:
            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futures = {pool.submit(_process, ap, rp): idx for idx, (ap, rp) in enumerate(files)}
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        res = future.result(timeout=120)
                    except Exception as e:
                        res = {
                            'status': 'error',
                            'file': files[idx][1],
                            'error': str(e)
                        }
                    results.append(res)
                    if res['status'] == 'success':
                        processed += 1
                    else:
                        failed += 1
                    if progress_callback:
                        progress_callback(idx + 1, total, processed, failed)
        else:
            for idx, (ap, rp) in enumerate(files):
                res = _process(ap, rp)
                results.append(res)
                if res['status'] == 'success':
                    processed += 1
                else:
                    failed += 1
                if progress_callback:
                    progress_callback(idx + 1, total, processed, failed)

        elapsed = (datetime.now() - start_time).total_seconds()

        return {
            'status': 'complete',
            'total': total,
            'processed': processed,
            'failed': failed,
            'elapsed_seconds': elapsed,
            'speed_per_second': processed / max(elapsed, 0.001),
            'results': results
        }

    def generate_audit_report(self, results, output_dir, tw, th, mode, category):
        """Generate CSV + Excel audit report"""
        out_path = Path(output_dir)
        headers = ["File Name", "Original Dimensions", "Original Size (KB)",
                   "Resized Size (KB)", "Status", "Error"]

        # CSV
        csv_path = out_path / "Resize_Audit_Report.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in results:
                writer.writerow([
                    r.get('file', ''),
                    r.get('original_dims', ''),
                    r.get('original_size_kb', ''),
                    r.get('resized_size_kb', ''),
                    r.get('status', ''),
                    r.get('error', '')
                ])

        log.info(f"Audit CSV: {csv_path}")

        # Excel (if available)
        if not HAS_OPENPYXL:
            return str(csv_path)

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Resize Audit"
            ws.merge_cells("A1:F1")

            title = ws["A1"]
            title.value = "IMAGE RESIZER BY SIAR DIGITAL — Audit Report"
            title.font = Font(name=_FONT_MONO, size=15, bold=True, color="00F5A0")
            title.fill = PatternFill("solid", fgColor="060910")
            title.alignment = Alignment(horizontal="center")
            ws.row_dimensions[1].height = 36

            ws.merge_cells("A2:F2")
            info = ws["A2"]
            info.value = (f"Asif Nawaz | Siar Digital 2026 | "
                         f"{datetime.now().strftime('%Y-%m-%d %H:%M')} | "
                         f"Target: {tw}x{th} | Mode: {mode} | Category: {category}")
            info.font = Font(name=_FONT_MONO, size=9, color="7A95C0")
            info.fill = PatternFill("solid", fgColor="0D1321")
            info.alignment = Alignment(horizontal="center")
            ws.row_dimensions[2].height = 20

            bdr = Border(
                left=Side(style="thin", color="1E2D45"),
                right=Side(style="thin", color="1E2D45"),
                top=Side(style="thin", color="1E2D45"),
                bottom=Side(style="thin", color="1E2D45"),
            )

            for ci, h in enumerate(headers, 1):
                c = ws.cell(row=3, column=ci, value=h)
                c.font = Font(name=_FONT_MONO, size=10, bold=True, color="E8F0FF")
                c.fill = PatternFill("solid", fgColor="1A2540")
                c.alignment = Alignment(horizontal="center")
                c.border = bdr

            for ri, r in enumerate(results, 4):
                fail = r.get('status') != 'success'
                row_data = [r.get(k, '') for k in ['file', 'original_dims', 'original_size_kb',
                                                     'resized_size_kb', 'status', 'error']]
                for ci, v in enumerate(row_data, 1):
                    c = ws.cell(row=ri, column=ci, value=v)
                    c.border = bdr
                    c.alignment = Alignment(horizontal="left")
                    c.fill = PatternFill("solid", fgColor="1A0910" if fail else "091A12")
                    c.font = Font(name=_FONT_MONO, size=9,
                                 color="FF4D6D" if fail else "00F5A0")

            sr = len(results) + 5
            sc = sum(1 for r in results if r.get('status') == 'success')
            ws.merge_cells(f"A{sr}:F{sr}")
            summary = ws.cell(row=sr, column=1,
                            value=f"TOTAL: {len(results)} | SUCCESS: {sc} | FAILED: {len(results)-sc}")
            summary.font = Font(name=_FONT_MONO, size=11, bold=True, color="FFD166")
            summary.fill = PatternFill("solid", fgColor="0D1321")
            summary.alignment = Alignment(horizontal="center")

            for col in ws.columns:
                ml = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(ml + 4, 60)

            excel_path = out_path / "Resize_Audit_Report.xlsx"
            wb.save(excel_path)
            log.info(f"Audit Excel: {excel_path}")

            return str(excel_path)
        except Exception as e:
            log.error(f"Excel report failed: {e}")
            return str(csv_path)

    def convert_format(self, input_path, output_path, format='JPEG', quality=85):
        """Convert image to different format (lossless preservation)"""
        try:
            img = Image.open(input_path)

            # Handle color mode conversion
            if img.mode == 'RGBA' and format.upper() in ['JPEG', 'BMP']:
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != 'RGB' and format.upper() in ['JPEG', 'BMP']:
                img = img.convert('RGB')
            elif img.mode == 'RGBA' and format.upper() in ['PNG', 'WEBP']:
                pass
            elif img.mode != 'RGB' and format.upper() in ['PNG', 'WEBP']:
                img = img.convert('RGB')

            # Save with appropriate format
            fmt = format.upper()
            save_kwargs = {'optimize': True}
            if fmt in ['JPEG', 'WEBP', 'BMP']:
                save_kwargs['quality'] = quality

            img.save(output_path, fmt, **save_kwargs)

            log.info(f"Format conversion: {Path(input_path).suffix} → {format}")
            return {'status': 'success', 'output': str(output_path)}
        except Exception as e:
            log.error(f"Format conversion error: {e}")
            return {'status': 'error', 'error': str(e)}


# Global instance
_processor = None

def get_processor(max_workers=4):
    global _processor
    if _processor is None:
        _processor = ImageProcessor(max_workers=max_workers)
    return _processor
