"""
Color Detector Service
Detect dominant colors in product images
Professional wrapper for color analysis
"""

import logging
from typing import List, Dict
from pathlib import Path
import json
import requests

log = logging.getLogger('siar.color_detector')

class ColorDetector:
    """Detect and analyze colors in product images"""

    # Color name mapping for common hex values
    COLOR_NAMES = {
        'red': ['#FF0000', '#FF1744', '#D32F2F'],
        'navy': ['#000080', '#0D1B7B', '#1A237E'],
        'maroon': ['#800000', '#6D1E1E'],
        'cream': ['#FFFDD0', '#F5F5DC', '#FFFACD'],
        'white': ['#FFFFFF', '#F5F5F5'],
        'black': ['#000000', '#1A1A1A'],
        'blue': ['#0000FF', '#0066CC', '#1976D2'],
        'green': ['#008000', '#388E3C', '#66BB6A'],
        'gold': ['#FFD700', '#FFC107', '#FDD835'],
        'silver': ['#C0C0C0', '#E8E8E8'],
        'pink': ['#FFC0CB', '#FF1493', '#E91E63'],
        'purple': ['#800080', '#6A1B9A', '#9C27B0'],
        'orange': ['#FFA500', '#FF9800', '#FB8C00'],
        'yellow': ['#FFFF00', '#FFD700', '#FBC02D'],
        'brown': ['#A52A2A', '#795548', '#5D4037'],
        'grey': ['#808080', '#9E9E9E', '#757575'],
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        log.info("ColorDetector initialized")

    def detect_single(self, image_path: str, num_colors: int = 5) -> Dict:
        """
        Detect dominant colors in single image

        Args:
            image_path: Path to image file or URL
            num_colors: Number of colors to detect (default 5)

        Returns:
            {
                'colors': [
                    {'hex': '#FF0000', 'name': 'Red', 'percent': 45.2},
                    ...
                ],
                'dominant': 'Red',
                'palette': 'warm|cool|neutral'
            }
        """
        try:
            from PIL import Image
            import numpy as np
            from collections import Counter

            # Handle both URLs and file paths
            if isinstance(image_path, str) and image_path.startswith('http'):
                try:
                    response = self.session.get(image_path, timeout=10)
                    response.raise_for_status()
                    from io import BytesIO
                    img = Image.open(BytesIO(response.content))
                except Exception as e:
                    log.error(f"Failed to download image from {image_path}: {e}")
                    return {'colors': [], 'dominant': 'Unknown', 'palette': 'unknown', 'error': str(e)}
            else:
                # Open local image
                if isinstance(image_path, str):
                    image_path = Path(image_path)
                img = Image.open(image_path)
            img = img.convert('RGB')

            # Resize for performance
            img.thumbnail((200, 200))

            # Get colors
            pixels = np.array(img)
            pixels = pixels.reshape((-1, 3))

            # Find unique colors
            unique_colors, counts = np.unique(pixels, axis=0, return_counts=True)
            color_counts = dict(zip(map(tuple, unique_colors), counts))

            # Sort by frequency
            sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:num_colors]

            # Convert to hex and get names
            colors = []
            for rgb, count in sorted_colors:
                hex_color = '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])
                color_name = self._get_color_name(hex_color)
                percent = (count / len(pixels)) * 100

                colors.append({
                    'hex': hex_color,
                    'name': color_name,
                    'percent': round(percent, 1),
                    'rgb': f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
                })

            # Determine palette type
            palette_type = self._determine_palette_type(colors)

            return {
                'colors': colors,
                'dominant': colors[0]['name'] if colors else 'Unknown',
                'palette': palette_type,
                'image': str(image_path)
            }

        except Exception as e:
            log.error(f"Error detecting colors in {image_path}: {e}")
            return {
                'colors': [],
                'dominant': 'Unknown',
                'palette': 'unknown',
                'error': str(e)
            }

    def detect_batch(self, image_paths: List[str]) -> List[Dict]:
        """Detect colors for multiple images"""
        results = []
        for image_path in image_paths:
            result = self.detect_single(image_path)
            results.append(result)
        return results

    def _get_color_name(self, hex_color: str) -> str:
        """Get human-friendly name for hex color"""
        hex_color = hex_color.upper()

        # Check exact matches first
        for name, hex_values in self.COLOR_NAMES.items():
            if hex_color in [h.upper() for h in hex_values]:
                return name.capitalize()

        # Try to find closest color
        for name, hex_values in self.COLOR_NAMES.items():
            for hex_val in hex_values:
                if self._hex_distance(hex_color, hex_val) < 30:
                    return name.capitalize()

        return "Custom"

    def _hex_distance(self, hex1: str, hex2: str) -> int:
        """Calculate distance between two hex colors"""
        try:
            r1, g1, b1 = int(hex1[1:3], 16), int(hex1[3:5], 16), int(hex1[5:7], 16)
            r2, g2, b2 = int(hex2[1:3], 16), int(hex2[3:5], 16), int(hex2[5:7], 16)
            return int(((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2) ** 0.5)
        except:
            return 999

    def _determine_palette_type(self, colors: List[Dict]) -> str:
        """Determine if palette is warm, cool, or neutral"""
        if not colors:
            return 'neutral'

        warm_colors = {'red', 'orange', 'yellow', 'pink', 'maroon', 'gold'}
        cool_colors = {'blue', 'green', 'purple', 'navy', 'cyan'}

        palette_score = 0
        for color in colors:
            name = color['name'].lower()
            if name in warm_colors:
                palette_score += 1
            elif name in cool_colors:
                palette_score -= 1

        if palette_score > 1:
            return 'warm'
        elif palette_score < -1:
            return 'cool'
        else:
            return 'neutral'
