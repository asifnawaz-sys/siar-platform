"""
SIAR Digital Video Processor v5.4.1
Integrated Video Resizer for SIAR Digital Platform

Cross-Platform (Windows/macOS/Linux) video processing engine with:
- Smart crop & AI-powered placement
- YOLOv8 subject detection
- Advanced filtergraph support (mirror BG, blur fill, etc.)
- True A/V sync (explicit stream mapping)
- Quality Guard (2-pass size limiting)
- Real-time encoding with stop-event support
- Batch processing with progress tracking

Created by: Asif Nawaz | Siar Digital 2026
"""

import os
import sys
import json
import re
import time
import logging
import tempfile
import threading
import subprocess
import traceback
from pathlib import Path
from datetime import datetime

log = logging.getLogger('siar.video.v5')

# ─────────────────────────────────────────────────────────────────────────────
#  Platform Detection & Resource Management
# ─────────────────────────────────────────────────────────────────────────────
import platform as _platform_mod
_OS_NAME = _platform_mod.system()

def _resource(relative_path):
    """Get bundled resource path (PyInstaller compatible)"""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)

# ─────────────────────────────────────────────────────────────────────────────
#  Optional Dependencies (Lazy-loaded where needed)
# ─────────────────────────────────────────────────────────────────────────────
try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    cv2 = None

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False
    YOLO = None

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ─────────────────────────────────────────────────────────────────────────────
#  FFmpeg Detection (Critical for video processing)
# ─────────────────────────────────────────────────────────────────────────────
_COMMON_BIN_DIRS = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]

def _find_ffmpeg_exe():
    """Find ffmpeg binary with fallback paths"""
    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).exists():
            try:
                if not os.access(bundled, os.X_OK):
                    os.chmod(bundled, 0o755)
            except Exception:
                pass
            try:
                r = subprocess.run([bundled, "-version"],
                                   capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    log.info(f"Using bundled ffmpeg: {bundled}")
                    return bundled
            except Exception:
                pass
    except Exception:
        pass

    candidates = ["ffmpeg", "ffmpeg.exe"]
    for d in _COMMON_BIN_DIRS:
        candidates.append(str(Path(d) / "ffmpeg"))

    for candidate in candidates:
        try:
            r = subprocess.run([candidate, "-version"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                log.info(f"Using system ffmpeg: {candidate}")
                return candidate
        except Exception:
            pass
    return None

def _find_ffprobe_exe():
    """Find ffprobe binary"""
    candidates = ["ffprobe", "ffprobe.exe"]
    for d in _COMMON_BIN_DIRS:
        candidates.append(str(Path(d) / "ffprobe"))

    for candidate in candidates:
        try:
            r = subprocess.run([candidate, "-version"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return candidate
        except Exception:
            pass
    return "ffprobe"

try:
    FFMPEG_EXE = _find_ffmpeg_exe()
    HAS_FFMPEG = FFMPEG_EXE is not None
    FFPROBE_EXE = _find_ffprobe_exe()
    if HAS_FFMPEG:
        log.info("ffmpeg available for video processing")
except Exception as exc:
    log.warning(f"FFmpeg detection failed: {exc}")
    FFMPEG_EXE, HAS_FFMPEG, FFPROBE_EXE = None, False, "ffprobe"

# ─────────────────────────────────────────────────────────────────────────────
#  YOLO Model Caching (Thread-safe)
# ─────────────────────────────────────────────────────────────────────────────
_yolo_model = None
_yolo_lock = threading.Lock()

def _get_yolo():
    """Lazy-load YOLO model (torch is expensive)"""
    global _yolo_model
    if not HAS_YOLO:
        return None
    with _yolo_lock:
        if _yolo_model is None:
            try:
                _yolo_model = YOLO("yolov8n.pt")
                log.info("YOLOv8n model loaded for video processing")
            except Exception as exc:
                log.warning(f"YOLOv8 load failed: {exc}")
                _yolo_model = None
    return _yolo_model

# ─────────────────────────────────────────────────────────────────────────────
#  Video Information & Probing
# ─────────────────────────────────────────────────────────────────────────────
def _ffprobe_json(path, select_streams="v:0",
                  show_entries="stream=width,height,r_frame_rate"):
    """Run ffprobe and return JSON result"""
    try:
        cmd = [FFPROBE_EXE, "-v", "quiet", "-print_format", "json",
               "-select_streams", select_streams,
               "-show_entries", show_entries, str(path)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
    except Exception:
        pass
    return None

def _ffmpeg_probe_fallback(path):
    """Fallback video info extraction using ffmpeg itself"""
    info = {}
    try:
        r = subprocess.run([FFMPEG_EXE, "-hide_banner", "-i", str(path)],
                           capture_output=True, text=True, timeout=30)
        text = r.stderr or ""
        info["has_audio"] = bool(re.search(r"Stream #\d+:\d+.*?Audio:", text))
        m = re.search(r"Video:.*?(\d{2,6})x(\d{2,6})", text)
        if m:
            info["width"] = int(m.group(1))
            info["height"] = int(m.group(2))
        m = re.search(r"(\d+(?:\.\d+)?)\s*fps", text)
        if m:
            info["fps"] = float(m.group(1))
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
        if m:
            hh, mm, ss = m.groups()
            info["duration"] = int(hh) * 3600 + int(mm) * 60 + float(ss)
    except Exception as exc:
        log.debug(f"ffmpeg fallback probe failed: {exc}")
    return info

def get_video_info(path):
    """Get comprehensive video information"""
    info = {"width": 1920, "height": 1080, "fps": 30.0,
            "duration": 30.0, "has_audio": True,
            "audio_sample_rate": 44100, "audio_channels": 2}
    try:
        # Probe video stream
        jv = _ffprobe_json(path, select_streams="v:0",
                           show_entries="stream=width,height,r_frame_rate,duration")
        if jv:
            streams = jv.get("streams", [])
            if streams:
                s = streams[0]
                if s.get("width"):
                    info["width"] = int(s["width"])
                if s.get("height"):
                    info["height"] = int(s["height"])
                rfr = s.get("r_frame_rate", "30/1")
                try:
                    num, den = rfr.split("/")
                    info["fps"] = round(float(num) / max(float(den), 1), 3)
                except Exception:
                    pass

        # Probe audio stream
        ja = _ffprobe_json(path, select_streams="a:0",
                           show_entries="stream=codec_type,sample_rate,channels")
        if ja:
            astreams = ja.get("streams", [])
            info["has_audio"] = bool(astreams)
            if astreams:
                a0 = astreams[0]
                if a0.get("sample_rate"):
                    info["audio_sample_rate"] = int(a0["sample_rate"])
                if a0.get("channels"):
                    info["audio_channels"] = int(a0["channels"])
        else:
            # Fallback if ffprobe fails completely
            fb = _ffmpeg_probe_fallback(path)
            if "has_audio" in fb:
                info["has_audio"] = fb["has_audio"]
            if "width" in fb and "height" in fb:
                info["width"], info["height"] = fb["width"], fb["height"]
            if "fps" in fb:
                info["fps"] = fb["fps"]
    except Exception as exc:
        log.warning(f"get_video_info error: {exc}")

    info["width"] = max(info["width"], 1)
    info["height"] = max(info["height"], 1)
    info["fps"] = max(info["fps"], 1.0)
    info["duration"] = max(info["duration"], 0.1)
    return info

# ─────────────────────────────────────────────────────────────────────────────
#  Filter Graph Builder
# ─────────────────────────────────────────────────────────────────────────────
def build_vf(placement, w_in, h_in, tw, th, crop_bbox=None):
    """Build ffmpeg filtergraph for video placement"""
    tw_even = tw if (tw % 2 == 0) else tw + 1
    th_even = th if (th % 2 == 0) else th + 1

    try:
        if placement in ("smart_crop", "fill_crop"):
            return (f"[0:v]scale={tw_even}:{th_even}:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop={tw_even}:{th_even}:trunc((iw-{tw_even})/2):trunc((ih-{th_even})/2)[vout]"), True

        if placement == "yolo_crop" and crop_bbox:
            x1, y1, x2, y2 = crop_bbox
            cw = max(x2 - x1, 2)
            ch = max(y2 - y1, 2)
            cw = cw if (cw % 2 == 0) else cw + 1
            ch = ch if (ch % 2 == 0) else ch + 1
            return (f"crop={cw}:{ch}:{x1}:{y1},scale={tw_even}:{th_even}:flags=lanczos[vout]"), True

        if placement == "stretch":
            return (f"scale={tw_even}:{th_even}:flags=lanczos[vout]"), True

        if placement in ("letterbox_dark", "pad_custom"):
            return (f"[0:v]scale={tw_even}:{th_even}:force_original_aspect_ratio=decrease:flags=lanczos,"
                    f"pad={tw_even}:{th_even}:(ow-iw)/2:(oh-ih)/2:color=black[vout]"), True

        if placement == "letterbox_white":
            return (f"[0:v]scale={tw_even}:{th_even}:force_original_aspect_ratio=decrease:flags=lanczos,"
                    f"pad={tw_even}:{th_even}:(ow-iw)/2:(oh-ih)/2:color=white[vout]"), True

        if placement in ("letterbox_blur", "ai_bg_extend"):
            return (f"[0:v]split[fg][bg];"
                    f"[bg]scale={tw_even}:{th_even}:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop={tw_even}:{th_even},gblur=sigma=30[blurbg];"
                    f"[fg]scale={tw_even}:{th_even}:force_original_aspect_ratio=decrease:flags=lanczos[fgs];"
                    f"[blurbg][fgs]overlay=(W-w)/2:(H-h)/2,format=yuv420p[vout]"), True

        if placement == "mirror_bg":
            return (f"[0:v]scale={tw_even}:{th_even}:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop={tw_even}:{th_even},split=3[b1][b2][b3];"
                    f"[b1]hflip[bh];[b2]vflip[bv0];[bv0]split=2[bv][bv2];[bv]hflip[bhv];"
                    f"[b3][bh]hstack[top];[bv2][bhv]hstack[bot];[top][bot]vstack[mir];"
                    f"[mir]scale={tw_even}:{th_even}:flags=lanczos[bg];"
                    f"[0:v]scale={tw_even}:{th_even}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[vout]"), True

        # Default to smart crop
        return (f"[0:v]scale={tw_even}:{th_even}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={tw_even}:{th_even}:trunc((iw-{tw_even})/2):trunc((ih-{th_even})/2)[vout]"), True

    except Exception as exc:
        log.error(f"build_vf error: {exc}")
        return (f"scale={tw_even}:{th_even}:flags=lanczos[vout]"), True

# ─────────────────────────────────────────────────────────────────────────────
#  Main Video Processor Class
# ─────────────────────────────────────────────────────────────────────────────
class VideoProcessor:
    """Core SIAR Digital Video Processor v5.4"""

    def __init__(self, max_workers=4):
        self.max_workers = max_workers
        self.stop_flag = threading.Event()
        log.info(f"VideoProcessor initialized | Workers={max_workers}")

    def stop(self):
        """Signal stop to current operation"""
        self.stop_flag.set()

    def process_video(self, input_path, output_path, config,
                     progress_callback=None, log_callback=None):
        """
        Process single video with given configuration

        config: {
            'width': int,
            'height': int,
            'placement': str,  # 'smart_crop', 'letterbox_blur', etc
            'format': str,     # 'MP4', 'WEBM', 'MKV', 'MOV'
            'crf': str,        # Quality (0-51, lower=better)
            'speed': str,      # 'ultrafast', 'fast', 'medium', 'slow', etc
            'fps': str,        # 'Source FPS' or specific fps
            'audio_bitrate': str,  # '128k', '256k', or 'No Audio'
            'minimize_size': bool,
        }
        """
        self.stop_flag.clear()
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            return False, "Input file not found"

        try:
            vi = get_video_info(str(input_path))
            _log(f"Probe: {vi['width']}x{vi['height']} {vi['fps']:.1f}fps", log_callback)

            tw = int(config['width'])
            th = int(config['height'])
            placement = config['placement']
            fmt = config['format']
            crf = config['crf']
            speed = config['speed']
            fps_opt = config['fps']
            audio_br = config['audio_bitrate']

            vf, is_complex = build_vf(placement, vi['width'], vi['height'], tw, th)
            _log(f"Filter: {vf[:80]}...", log_callback)

            success, mb = self._encode_video(
                input_path, output_path, config, vf, is_complex, vi,
                log_callback, progress_callback)

            if success:
                _log(f"✓ Success: {mb:.2f} MB", log_callback)
            else:
                _log(f"✗ Failed", log_callback)

            return success, mb

        except Exception as exc:
            _log(f"✗ Exception: {exc}", log_callback)
            log.error(f"process_video: {traceback.format_exc()}")
            return False, 0.0

    def _encode_video(self, in_path, out_path, config, vf, is_complex, vi,
                     log_callback, progress_callback):
        """Internal video encoding with ffmpeg"""
        if not HAS_FFMPEG:
            _log("✗ ffmpeg not found", log_callback)
            return False, 0.0

        try:
            fmt = config['format']
            codec_map = {
                "MP4": ("libx264", "aac", ".mp4"),
                "MOV": ("libx264", "aac", ".mov"),
                "MKV": ("libx264", "aac", ".mkv"),
                "WEBM": ("libvpx-vp9", "libopus", ".webm"),
            }
            vcodec, acodec, _ = codec_map.get(fmt, ("libx264", "aac", ".mp4"))

            cmd = [FFMPEG_EXE, "-y", "-i", str(in_path)]

            # Video filter mapping (explicit to avoid audio bugs)
            if is_complex:
                cmd += ["-filter_complex", vf, "-map", "[vout]"]
            else:
                cmd += ["-vf", vf, "-map", "0:v:0"]

            # Audio mapping (explicit)
            want_audio = config['audio_bitrate'] != 'No Audio'
            if want_audio:
                cmd += ["-map", "0:a:0?"]
            else:
                cmd += ["-an"]

            # Video codec & quality
            cmd += ["-c:v", vcodec, "-crf", str(config['crf']),
                    "-preset", config['speed']]

            # Audio codec
            if want_audio:
                cmd += ["-c:a", acodec, "-b:a", config['audio_bitrate']]

            # Common options
            cmd += ["-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    "-max_muxing_queue_size", "9999",
                    "-avoid_negative_ts", "make_zero"]

            # FPS override
            if config['fps'] != 'Source FPS':
                cmd += ["-r", config['fps'], "-vsync", "cfr"]

            cmd += [str(out_path)]

            # Execute
            _log(f"Encoding: {' '.join(cmd[:5])}...", log_callback)
            success, stderr = _run_ffmpeg(cmd, stop_event=self.stop_flag)

            if success:
                mb = out_path.stat().st_size / (1024 * 1024)
                return True, mb
            else:
                return False, 0.0

        except Exception as exc:
            _log(f"Encode error: {exc}", log_callback)
            return False, 0.0

    def batch_process(self, file_list, config,
                     progress_callback=None, log_callback=None):
        """Process multiple videos"""
        self.stop_flag.clear()
        total = len(file_list)
        done = 0
        failed = 0

        _log(f"Batch: {total} file(s)", log_callback)

        for idx, item in enumerate(file_list):
            if self.stop_flag.is_set():
                _log("Stopped by user", log_callback)
                break

            in_path = Path(item['abs'])
            rel_path = Path(item['rel'])
            out_name = rel_path.stem + CODEC_MAP.get(config['format'], (".mp4",))[-1]
            out_path = Path(config['output_dir']) / out_name

            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                _log(f"mkdir error: {exc}", log_callback)
                failed += 1
                if progress_callback:
                    progress_callback(idx + 1, total, done, failed)
                continue

            _log(f"[{idx+1}/{total}] {rel_path.name}", log_callback)

            success, mb = self.process_video(
                in_path, out_path, config,
                progress_callback=progress_callback,
                log_callback=log_callback)

            if success:
                done += 1
            else:
                failed += 1

            if progress_callback:
                progress_callback(idx + 1, total, done, failed)

        _log(f"COMPLETE: {done} OK | {failed} FAILED", log_callback)
        return {"total": total, "done": done, "failed": failed}


def _run_ffmpeg(cmd, stop_event=None, timeout_sec=3600):
    """Run ffmpeg and manage execution"""
    log.debug(f"FFmpeg: {' '.join(str(c) for c in cmd[:5])}...")
    try:
        proc = subprocess.Popen([str(c) for c in cmd],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        start = time.time()
        while True:
            if stop_event is not None and stop_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return False, "Stopped by user"

            try:
                proc.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if time.time() - start > timeout_sec:
                    proc.kill()
                    return False, f"Timeout after {timeout_sec}s"

        return proc.returncode == 0, "" if proc.returncode == 0 else "Encoding failed"
    except Exception as exc:
        log.error(f"FFmpeg exception: {exc}")
        return False, str(exc)


def _log(msg, callback=None):
    """Log message with optional callback"""
    log.info(msg)
    if callback:
        try:
            callback(msg, "info")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Codec Map (for reference)
# ─────────────────────────────────────────────────────────────────────────────
CODEC_MAP = {
    "MP4": ("libx264", "aac", ".mp4"),
    "MOV": ("libx264", "aac", ".mov"),
    "MKV": ("libx264", "aac", ".mkv"),
    "WEBM": ("libvpx-vp9", "libopus", ".webm"),
}

# ─────────────────────────────────────────────────────────────────────────────
#  Module API
# ─────────────────────────────────────────────────────────────────────────────
_processor = None

def get_processor(max_workers=4):
    """Get or create global processor instance"""
    global _processor
    if _processor is None:
        _processor = VideoProcessor(max_workers=max_workers)
    return _processor
