"""
Video Processing Service for SIAR Digital Platform
Video format conversion, compression, and optimization

Features:
- Format conversion (MP4, WebM, MOV, MKV)
- Bitrate/quality presets
- Batch processing
- Progress tracking
- Codec optimization
- Multi-threaded processing
"""

import os
import sys
import logging
import json
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import re

log = logging.getLogger('siar.video')

# Video quality presets (bitrate, resolution)
VIDEO_PRESETS = {
    'low': {'bitrate': '500k', 'height': 480, 'codec': 'libx264'},
    'medium': {'bitrate': '1500k', 'height': 720, 'codec': 'libx264'},
    'high': {'bitrate': '5000k', 'height': 1080, 'codec': 'libx264'},
    'ultra': {'bitrate': '10000k', 'height': 2160, 'codec': 'libx264'},
    'webm_low': {'bitrate': '400k', 'height': 480, 'codec': 'libvpx'},
    'webm_medium': {'bitrate': '1200k', 'height': 720, 'codec': 'libvpx'},
    'webm_high': {'bitrate': '4000k', 'height': 1080, 'codec': 'libvpx'},
}

class VideoProcessor:
    """Video processing engine using FFmpeg"""

    def __init__(self, max_workers=2, ffmpeg_path=None):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.ffmpeg_path = ffmpeg_path or self._find_ffmpeg()

        if not self.ffmpeg_path:
            log.warning("FFmpeg not found. Video processing will not work.")
        else:
            log.info(f"VideoProcessor initialized with FFmpeg at {self.ffmpeg_path}")

    def _find_ffmpeg(self):
        """Find FFmpeg executable in system PATH"""
        try:
            # Try common commands
            for cmd in ['ffmpeg', 'ffmpeg.exe']:
                try:
                    subprocess.run([cmd, '-version'],
                                 capture_output=True, timeout=5)
                    return cmd
                except FileNotFoundError:
                    continue
            return None
        except Exception as e:
            log.warning(f"FFmpeg detection failed: {e}")
            return None

    def _run_ffmpeg(self, args, timeout=3600):
        """Execute FFmpeg command"""
        if not self.ffmpeg_path:
            raise RuntimeError("FFmpeg not available")

        try:
            cmd = [self.ffmpeg_path, '-hide_banner', '-loglevel', 'error'] + args
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg error: {result.stderr}")

            return result.stdout
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Video processing timeout (>{timeout}s)")
        except Exception as e:
            log.error(f"FFmpeg execution failed: {e}")
            raise

    def get_video_info(self, video_path):
        """Get video metadata using ffprobe"""
        try:
            # Use ffmpeg to get duration
            args = ['-i', str(video_path)]

            try:
                subprocess.run([self.ffmpeg_path] + args,
                             capture_output=True, text=True, timeout=10)
            except:
                pass

            # Extract duration from stderr (ffmpeg outputs metadata to stderr)
            cmd = [self.ffmpeg_path, '-i', str(video_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)

            # Parse duration: Duration: HH:MM:SS.ms
            duration_match = re.search(r'Duration: (\d+):(\d+):(\d+\.?\d*)', result.stderr)
            if duration_match:
                hours = int(duration_match.group(1))
                minutes = int(duration_match.group(2))
                seconds = float(duration_match.group(3))
                duration = hours * 3600 + minutes * 60 + seconds
            else:
                duration = None

            # Get file size
            file_size = os.path.getsize(video_path)

            return {
                'path': str(video_path),
                'size': file_size,
                'size_mb': file_size / (1024 * 1024),
                'duration': duration,
                'duration_str': self._format_duration(duration) if duration else None
            }
        except Exception as e:
            log.error(f"Error getting video info: {e}")
            return {'error': str(e)}

    def convert_video(self, input_path, output_path, preset='medium', audio_codec='aac'):
        """
        Convert video to different format/quality

        Presets: low, medium, high, ultra, webm_low, webm_medium, webm_high
        """
        try:
            input_path = str(input_path)
            output_path = str(output_path)

            if preset not in VIDEO_PRESETS:
                preset = 'medium'

            preset_config = VIDEO_PRESETS[preset]

            # Get input info
            info = self.get_video_info(input_path)
            if 'error' in info:
                return {'status': 'error', 'error': info['error']}

            # Build FFmpeg command
            args = [
                '-i', input_path,
                '-c:v', preset_config['codec'],
                '-b:v', preset_config['bitrate'],
                '-vf', f"scale=-1:{preset_config['height']}",
                '-c:a', audio_codec,
                '-b:a', '128k',
                '-preset', 'medium',  # Encoding speed
                '-y',  # Overwrite output
                output_path
            ]

            log.info(f"Converting {input_path} → {output_path} ({preset})")
            self._run_ffmpeg(args)

            # Get output info
            output_size = os.path.getsize(output_path)
            compression = (1 - output_size / info['size']) * 100

            log.info(f"Conversion complete: {info['size_mb']:.1f}MB → "
                    f"{output_size / (1024*1024):.1f}MB ({compression:.1f}% reduction)")

            return {
                'status': 'success',
                'input': input_path,
                'output': output_path,
                'original_size_mb': info['size_mb'],
                'converted_size_mb': output_size / (1024 * 1024),
                'compression_percent': compression,
                'duration': info.get('duration'),
                'preset': preset
            }
        except Exception as e:
            log.error(f"Video conversion error: {e}")
            return {'status': 'error', 'error': str(e)}

    def extract_frames(self, video_path, output_dir, interval=1):
        """
        Extract frames from video at specified interval (seconds)
        """
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Extract 1 frame per N seconds
            args = [
                '-i', str(video_path),
                '-vf', f'fps=1/{interval}',
                str(output_dir / 'frame_%04d.jpg')
            ]

            log.info(f"Extracting frames from {video_path} (every {interval}s)")
            self._run_ffmpeg(args)

            frames = list(output_dir.glob('frame_*.jpg'))
            log.info(f"Extracted {len(frames)} frames")

            return {
                'status': 'success',
                'frames_extracted': len(frames),
                'output_dir': str(output_dir),
                'frames': [str(f) for f in sorted(frames)]
            }
        except Exception as e:
            log.error(f"Frame extraction error: {e}")
            return {'status': 'error', 'error': str(e)}

    def add_watermark(self, video_path, watermark_path, output_path, position='top-right'):
        """
        Add watermark image to video

        Positions: top-left, top-right, bottom-left, bottom-right, center
        """
        try:
            positions = {
                'top-left': '10:10',
                'top-right': 'W-w-10:10',
                'bottom-left': '10:H-h-10',
                'bottom-right': 'W-w-10:H-h-10',
                'center': '(W-w)/2:(H-h)/2'
            }

            pos = positions.get(position, positions['top-right'])

            args = [
                '-i', str(video_path),
                '-i', str(watermark_path),
                '-filter_complex', f'overlay={pos}',
                '-c:a', 'aac',
                '-y',
                str(output_path)
            ]

            log.info(f"Adding watermark to {video_path}")
            self._run_ffmpeg(args)

            output_size = os.path.getsize(output_path)

            return {
                'status': 'success',
                'output': str(output_path),
                'size_mb': output_size / (1024 * 1024),
                'watermark_position': position
            }
        except Exception as e:
            log.error(f"Watermark error: {e}")
            return {'status': 'error', 'error': str(e)}

    def batch_convert(self, input_dir, output_dir, preset='medium', audio_codec='aac'):
        """
        Batch convert all videos in directory
        """
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Find all videos
        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v'}
        videos = [f for f in input_path.rglob('*')
                 if f.suffix.lower() in video_extensions]

        if not videos:
            log.warning(f"No videos found in {input_dir}")
            return {
                'status': 'no_videos',
                'total': 0,
                'converted': 0,
                'failed': 0,
                'results': []
            }

        results = []
        converted = 0
        failed = 0
        total_original = 0
        total_converted = 0

        log.info(f"Starting batch conversion: {len(videos)} videos")

        for video_file in videos:
            # Determine output format based on preset
            out_ext = '.webm' if 'webm' in preset else '.mp4'
            rel_path = video_file.relative_to(input_path)
            out_file = output_path / rel_path.with_suffix(out_ext)
            out_file.parent.mkdir(parents=True, exist_ok=True)

            result = self.convert_video(str(video_file), str(out_file), preset, audio_codec)
            results.append(result)

            if result['status'] == 'success':
                converted += 1
                total_original += result.get('original_size_mb', 0)
                total_converted += result.get('converted_size_mb', 0)
            else:
                failed += 1

        compression_pct = (1 - total_converted / max(total_original, 1)) * 100 if total_original > 0 else 0

        stats = {
            'status': 'complete',
            'total': len(videos),
            'converted': converted,
            'failed': failed,
            'original_size_mb': total_original,
            'converted_size_mb': total_converted,
            'compression_percent': compression_pct,
            'results': results
        }

        log.info(f"Batch complete: {converted} OK, {failed} failed, "
                f"{compression_pct:.1f}% compression")

        return stats

    @staticmethod
    def _format_duration(seconds):
        """Format seconds to HH:MM:SS"""
        if not seconds:
            return None
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# Global processor instance
_processor = None

def get_processor():
    global _processor
    if _processor is None:
        _processor = VideoProcessor(max_workers=2)
    return _processor
