"""
Image Resolution Processor
Extract image resolution/dimensions from image URLs and files
"""

import logging
from typing import List, Dict
from pathlib import Path
import requests
from io import BytesIO

log = logging.getLogger('siar.resolution_processor')

class ResolutionProcessor:
    """Extract resolution information from images"""

    def __init__(self):
        self.session = requests.Session()
        log.info("ResolutionProcessor initialized")

    def get_resolution_from_url(self, image_url: str) -> Dict:
        """
        Get image resolution from URL

        Args:
            image_url: URL to image

        Returns:
            {
                'url': image_url,
                'width': 1920,
                'height': 1080,
                'format': 'jpeg',
                'size_bytes': 524288,
                'aspect_ratio': '16:9'
            }
        """
        try:
            from PIL import Image

            response = self.session.get(image_url, timeout=30, stream=True)
            response.raise_for_status()

            img_data = BytesIO(response.content)
            img = Image.open(img_data)

            width, height = img.size
            aspect_ratio = self._calculate_aspect_ratio(width, height)
            file_format = img.format or 'unknown'
            file_size = len(response.content)

            log.info(f"Extracted resolution from {image_url}: {width}x{height}")

            return {
                'url': image_url,
                'width': width,
                'height': height,
                'format': file_format.lower(),
                'size_bytes': file_size,
                'size_mb': round(file_size / (1024*1024), 2),
                'aspect_ratio': aspect_ratio,
                'megapixels': round((width * height) / 1000000, 2)
            }

        except Exception as e:
            log.error(f"Error getting resolution from {image_url}: {e}")
            return {
                'url': image_url,
                'error': str(e)
            }

    def get_resolution_from_file(self, file_path: str) -> Dict:
        """
        Get image resolution from local file

        Args:
            file_path: Path to image file

        Returns:
            Resolution information
        """
        try:
            from PIL import Image

            file_path = Path(file_path)
            if not file_path.exists():
                return {'error': f'File not found: {file_path}'}

            img = Image.open(file_path)
            width, height = img.size
            aspect_ratio = self._calculate_aspect_ratio(width, height)
            file_size = file_path.stat().st_size

            return {
                'path': str(file_path),
                'width': width,
                'height': height,
                'format': img.format.lower() if img.format else 'unknown',
                'size_bytes': file_size,
                'size_mb': round(file_size / (1024*1024), 2),
                'aspect_ratio': aspect_ratio,
                'megapixels': round((width * height) / 1000000, 2)
            }

        except Exception as e:
            log.error(f"Error getting resolution from {file_path}: {e}")
            return {'error': str(e)}

    def batch_get_resolutions(self, image_urls: List[str]) -> List[Dict]:
        """Get resolutions for multiple images"""
        results = []
        for url in image_urls:
            result = self.get_resolution_from_url(url)
            results.append(result)
        return results

    def _calculate_aspect_ratio(self, width: int, height: int) -> str:
        """Calculate aspect ratio string"""
        from math import gcd

        divisor = gcd(width, height)
        w = width // divisor
        h = height // divisor

        return f"{w}:{h}"
