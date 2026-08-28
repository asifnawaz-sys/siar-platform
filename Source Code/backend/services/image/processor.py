"""
Image Processing Service for SIAR Digital Platform
Wraps image_resizer.py core logic (AI-powered batch processing)

Features:
- AI Pose Detection (YOLOv8)
- Fashion Consistent cropping
- Multiple processing modes
- Batch processing with progress tracking
- Quality preservation
- Multi-threaded processing
"""

import os
import sys
import logging
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import traceback

try:
    from PIL import Image, ImageOps, ImageFilter, ImageDraw, ImageEnhance
except ImportError:
    raise ImportError("Pillow required for image processing")

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

log = logging.getLogger('siar.image')

# Detection model constants
_DETECT_W, _DETECT_H = 320, 320
_POSE_MODEL_NAME = "yolov8m-pose.pt"
_BBOX_MODEL_NAME = "yolov8n.pt"

class ImageProcessor:
    """Core image processing engine (no UI)"""

    def __init__(self, max_workers=4):
        self.max_workers = max_workers
        self.processing_jobs = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        log.info(f"ImageProcessor initialized with {max_workers} workers")

    def get_resource_path(self, relative_path):
        """Get path to bundled resource (handles PyInstaller)"""
        base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, relative_path)

    def resize_image(self, input_path, output_path,
                    width=None, height=None, mode='fill', quality=85):
        """
        Resize single image

        Modes:
        - fill: Center crop + resize (default)
        - fit: Letterbox (preserve aspect ratio)
        - stretch: Force dimensions
        - smart: AI-powered (uses pose detection if available)
        """
        try:
            img = Image.open(input_path)

            # Convert RGBA to RGB if needed
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Determine target dimensions
            if not width and not height:
                width, height = img.size
            elif width and not height:
                height = int(width * img.height / img.width)
            elif height and not width:
                width = int(height * img.width / img.height)

            # Apply resizing mode
            if mode == 'fill':
                resized = self._resize_fill(img, width, height)
            elif mode == 'fit':
                resized = self._resize_fit(img, width, height)
            elif mode == 'stretch':
                resized = img.resize((width, height), Image.Resampling.LANCZOS)
            elif mode == 'smart' and YOLO:
                resized = self._resize_smart(img, width, height)
            else:
                resized = self._resize_fill(img, width, height)

            # Save with quality
            resized.save(output_path, 'JPEG', quality=quality, optimize=True)

            orig_size = os.path.getsize(input_path)
            new_size = os.path.getsize(output_path)

            log.info(f"Resized {input_path}: {img.size} → {resized.size}, "
                    f"{orig_size/1024:.1f}KB → {new_size/1024:.1f}KB")

            return {
                'status': 'success',
                'input': str(input_path),
                'output': str(output_path),
                'original_size': orig_size,
                'resized_size': new_size,
                'dimensions': f"{resized.size[0]}x{resized.size[1]}",
                'compression': f"{(1 - new_size/orig_size)*100:.1f}%"
            }
        except Exception as e:
            log.error(f"Error processing {input_path}: {e}")
            return {
                'status': 'error',
                'input': str(input_path),
                'error': str(e)
            }

    def _resize_fill(self, img, target_w, target_h):
        """Center crop + resize (fill entire frame)"""
        aspect_img = img.width / img.height
        aspect_target = target_w / target_h

        if aspect_img > aspect_target:
            # Image is too wide, crop width
            new_width = int(img.height * aspect_target)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            # Image is too tall, crop height
            new_height = int(img.width / aspect_target)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))

        return img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    def _resize_fit(self, img, target_w, target_h):
        """Letterbox - preserve aspect ratio, add borders"""
        img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)

        # Create background and paste image
        background = Image.new('RGB', (target_w, target_h), (255, 255, 255))
        x = (target_w - img.width) // 2
        y = (target_h - img.height) // 2
        background.paste(img, (x, y))

        return background

    def _resize_smart(self, img, target_w, target_h):
        """AI-powered resize using pose detection (if available)"""
        try:
            if YOLO is None:
                log.warning("YOLO not available, falling back to fill mode")
                return self._resize_fill(img, target_w, target_h)

            # Try pose detection for people-centric composition
            model = YOLO(self.get_resource_path(_POSE_MODEL_NAME))
            results = model(img, conf=0.5, verbose=False)

            if results and len(results[0].keypoints) > 0:
                # Use pose-based cropping
                return self._crop_by_pose(img, results[0], target_w, target_h)
            else:
                # Fall back to center crop
                return self._resize_fill(img, target_w, target_h)
        except Exception as e:
            log.warning(f"Smart resize failed: {e}, using fill mode")
            return self._resize_fill(img, target_w, target_h)

    def _crop_by_pose(self, img, result, target_w, target_h):
        """Crop image based on detected pose keypoints"""
        try:
            keypoints = result.keypoints.xy[0]

            if len(keypoints) == 0:
                return self._resize_fill(img, target_w, target_h)

            # Get bounding box of all keypoints
            valid_points = keypoints[keypoints[:, 0] > 0]
            if len(valid_points) == 0:
                return self._resize_fill(img, target_w, target_h)

            x_min, y_min = valid_points.min(axis=0)
            x_max, y_max = valid_points.max(axis=0)

            # Add headspace and footspace margins
            margin_top = int((y_max - y_min) * 0.1)
            margin_bottom = int((y_max - y_min) * 0.15)
            margin_lr = int((x_max - x_min) * 0.1)

            crop_box = (
                max(0, int(x_min - margin_lr)),
                max(0, int(y_min - margin_top)),
                min(img.width, int(x_max + margin_lr)),
                min(img.height, int(y_max + margin_bottom))
            )

            cropped = img.crop(crop_box)
            return cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
        except Exception as e:
            log.warning(f"Pose crop failed: {e}")
            return self._resize_fill(img, target_w, target_h)

    def batch_process(self, input_dir, output_dir,
                     width=None, height=None, mode='fill', quality=85):
        """
        Process all images in directory
        Returns list of results and stats
        """
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Find all images
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        images = [f for f in input_path.rglob('*')
                 if f.suffix.lower() in image_extensions and not f.name.startswith('._')]

        if not images:
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
        total_saved = 0
        total_original = 0

        log.info(f"Starting batch processing: {len(images)} images")

        for img_file in images:
            # Maintain directory structure
            rel_path = img_file.relative_to(input_path)
            out_file = output_path / rel_path.with_suffix('.jpg')
            out_file.parent.mkdir(parents=True, exist_ok=True)

            result = self.resize_image(str(img_file), str(out_file),
                                      width, height, mode, quality)
            results.append(result)

            if result['status'] == 'success':
                processed += 1
                total_original += result['original_size']
                total_saved += result['resized_size']
            else:
                failed += 1

        compression_pct = (1 - total_saved / max(total_original, 1)) * 100

        stats = {
            'status': 'complete',
            'total': len(images),
            'processed': processed,
            'failed': failed,
            'original_size_mb': total_original / (1024 * 1024),
            'compressed_size_mb': total_saved / (1024 * 1024),
            'compression_percent': compression_pct,
            'results': results
        }

        log.info(f"Batch complete: {processed} OK, {failed} failed, "
                f"{compression_pct:.1f}% compression")

        return stats

    def convert_format(self, input_path, output_path, format='JPEG', quality=85):
        """Convert image to different format"""
        try:
            img = Image.open(input_path)
            if img.mode == 'RGBA' and format == 'JPEG':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != 'RGB' and format == 'JPEG':
                img = img.convert('RGB')

            img.save(output_path, format, quality=quality, optimize=True)
            return {'status': 'success', 'output': str(output_path)}
        except Exception as e:
            log.error(f"Format conversion error: {e}")
            return {'status': 'error', 'error': str(e)}


# Global processor instance
_processor = None

def get_processor():
    global _processor
    if _processor is None:
        _processor = ImageProcessor(max_workers=4)
    return _processor
