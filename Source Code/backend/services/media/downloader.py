"""
Universal media downloader with CDN optimization, deduplication, and retry logic.
Supports images, videos, and multiple CDN patterns.
"""

import logging
import re
from pathlib import Path
from urllib.parse import urlparse, urljoin
import hashlib
import mimetypes
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

log = logging.getLogger("siar.media")


class CDNOptimizer:
    """Enhance media URLs for highest possible resolution across all CDN platforms."""

    @staticmethod
    def enhance(url: str, platform: str = "generic") -> str:
        """
        Upgrade image URL to highest resolution for each platform.
        """
        if not url:
            return url

        url = url.strip()

        # Shopify CDN
        if "cdn.shopify.com" in url or platform == "shopify":
            url = re.sub(r'_(?:pico|icon|thumb|small|compact|medium|large|grande|master|original|\d{2,4}x\d{0,4}|x\d{2,4})(?=\.[a-zA-Z])', '', url)
            url = re.sub(r'_(crop|fill|contain|fit)_[a-z]+(?=\.[a-zA-Z])', '', url)
            url = re.sub(r'[?&]v=\d+', '', url)
            return url.rstrip('?&')

        # WooCommerce / WordPress
        if platform in ("woocommerce", "wordpress") or "wp-content" in url:
            url = re.sub(r'-\d{2,4}x\d{2,4}(?=\.[a-zA-Z])', '', url)
            url = re.sub(r'[?&](?:resize|w|quality)=\d+[^&]*', '', url)
            return url.rstrip('?&')

        # Magento
        if platform in ("magento", "magento2") or "/media/catalog/" in url:
            url = re.sub(r'/cache/[a-f0-9]{32}/', '/', url)
            url = re.sub(r'/\d+x\d+/', '/', url)
            return url

        # BigCommerce
        if platform == "bigcommerce" or "bigcommerce.com" in url:
            url = re.sub(r'/[a-z](?=/[^/]+\.[a-zA-Z]+$)', '/original', url)
            return url

        # Cloudinary
        if "cloudinary.com" in url or "res.cloudinary.com" in url:
            url = re.sub(r'(/upload/)([^/]*/)?', r'\1w_3000,q_100,f_auto/\2', url, count=1)
            url = re.sub(r'w_\d+,', 'w_3000,', url)
            url = re.sub(r'q_[a-z:]+', 'q_100', url)
            return url

        # imgix
        if ".imgix.net" in url:
            url = re.sub(r'[?&](?:w|h)=\d+', '', url)
            sep = '&' if '?' in url else '?'
            return f"{url}{sep}w=3000&q=100&fm=jpg&fit=max&auto=compress,format"

        # WixStatic
        if "wixstatic.com" in url or "static.wixstatic.com" in url:
            url = re.sub(r'[?&]quality=\d+', '', url)
            url = re.sub(r'[?&](?:w|h|width|height)=\d+', '', url)
            url = re.sub(r'/v\d+/fill/[^/]+/', '/v1/', url)
            sep = '&' if '?' in url else '?'
            return f"{url}{sep}quality=100"

        # Generic CDN
        url = re.sub(r'[?&](?:width|height|w|h|size|q|quality|resize|scale|thumb)=\d+[^&]*', '', url)
        url = re.sub(r'-\d{2,4}x\d{2,4}(?=\.[a-zA-Z])', '', url)
        return url.rstrip('?&')

    @staticmethod
    def best_from_srcset(srcset: str) -> str:
        """Pick highest-resolution URL from srcset."""
        if not srcset:
            return ""

        entries = []
        for part in srcset.split(","):
            part = part.strip()
            bits = part.split()
            if bits:
                url = bits[0]
                width = 0
                if len(bits) > 1 and bits[1].endswith("w"):
                    try:
                        width = int(bits[1].rstrip("w"))
                    except ValueError:
                        pass
                entries.append((width, url))

        if entries:
            entries.sort(reverse=True)
            return entries[0][1]

        return ""


class MediaDownloader:
    """Download media files with retry, dedup, and multi-threading support."""

    def __init__(self, timeout: int = 30, max_workers: int = 4):
        self.timeout = timeout
        self.max_workers = max_workers
        self.optimizer = CDNOptimizer()

    def _canonical_url(self, url: str) -> str:
        """Normalize URL for deduplication."""
        try:
            u = url.strip().lower().split('#')[0].rstrip('/')
            u = re.sub(r'\?.*$', '', u)
            return u
        except Exception:
            return url.lower().strip()

    def _download_file(self, url: str, output_dir: Path, platform: str = "generic", max_retries: int = 3) -> dict:
        """Download a single file with retry logic."""

        if not url or not url.strip():
            return {"url": url, "path": "", "status": "skipped", "reason": "Empty URL"}

        url = url.strip()

        # Enhance URL for better resolution
        try:
            enhanced_url = self.optimizer.enhance(url, platform)
        except Exception:
            enhanced_url = url

        for attempt in range(max_retries):
            try:
                r = requests.get(enhanced_url, timeout=self.timeout, stream=True, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                r.raise_for_status()

                # Determine file extension
                suffix = Path(urlparse(enhanced_url).path).suffix.lower()
                if not suffix or len(suffix) > 5:
                    content_type = r.headers.get("content-type", "").split(";")[0]
                    suffix = mimetypes.guess_extension(content_type) or ".bin"

                # Generate filename from URL hash
                filename = hashlib.sha256(url.encode()).hexdigest()[:16] + suffix
                filepath = output_dir / filename

                # Write file
                with filepath.open("wb") as fh:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            fh.write(chunk)

                file_size = filepath.stat().st_size

                return {
                    "url": url,
                    "enhanced_url": enhanced_url,
                    "path": str(filepath),
                    "filename": filename,
                    "size_bytes": file_size,
                    "status": "success",
                    "http_status": r.status_code,
                    "content_type": r.headers.get("content-type", "unknown"),
                }

            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    return {
                        "url": url,
                        "path": "",
                        "status": "failed",
                        "error": str(e),
                        "attempt": attempt + 1,
                    }
                log.warning(f"Download attempt {attempt + 1}/{max_retries} failed for {url}: {e}")

        return {
            "url": url,
            "path": "",
            "status": "failed",
            "error": f"Max retries ({max_retries}) exceeded",
        }

    def download(self, urls: list, output_dir, platform: str = "generic", skip_duplicates: bool = True) -> list:
        """
        Download multiple media files.

        Args:
            urls: List of URLs to download
            output_dir: Output directory
            platform: Platform for CDN optimization
            skip_duplicates: Skip duplicate URLs by canonical form

        Returns:
            List of download results
        """

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Deduplicate URLs
        unique_urls = []
        seen = set()

        for url in urls:
            if not url:
                continue
            canonical = self._canonical_url(url)
            if skip_duplicates and canonical in seen:
                continue
            seen.add(canonical)
            unique_urls.append(url)

        log.info(f"Downloading {len(unique_urls)} unique media files to {output_dir}")

        # Download in parallel
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._download_file, url, output_dir, platform): url
                for url in unique_urls
            }

            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                    if result["status"] == "success":
                        log.info(f"✓ Downloaded: {result['filename']} ({result['size_bytes']} bytes)")
                    else:
                        log.warning(f"✗ Failed: {result['url']} - {result.get('error', 'Unknown error')}")
                except Exception as e:
                    log.error(f"Thread execution failed: {e}")
                    results.append({
                        "url": futures[future],
                        "status": "failed",
                        "error": str(e),
                    })

        # Summary
        successful = sum(1 for r in results if r["status"] == "success")
        failed = sum(1 for r in results if r["status"] == "failed")
        log.info(f"Media download complete: {successful} success, {failed} failed")

        return results
