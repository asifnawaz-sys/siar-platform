"""
Application Launcher Service
Manage and launch standalone applications from SIAR Digital Platform
"""

import logging
import subprocess
import os
from pathlib import Path
from typing import Dict, List, Optional
import json

log = logging.getLogger('siar.app_launcher')

class ApplicationLauncher:
    """Launch and manage standalone applications"""

    APPS_FOLDER = Path("E:/asif/Desktop/MY APPs/Apps")

    # Application registry with metadata
    REGISTERED_APPS = {
        'image_resizer_latest': {
            'name': 'Image Resizer (Latest)',
            'executable': 'Image Resizer For Windows/image_resizer_siar (1).exe',
            'size_mb': 481.8,
            'type': 'gui',
            'platform': 'windows',
            'description': 'Advanced image resizer with multiple modes and presets',
            'features': ['Batch processing', 'Format conversion', 'Quality control'],
            'status': 'available'
        },
        'image_resizer_basic': {
            'name': 'Image Resizer (Basic)',
            'executable': 'EXE DEcoder/ImageResizerBySiarDigital.exe',
            'size_mb': 76.5,
            'type': 'gui',
            'platform': 'windows',
            'description': 'Basic image resizer',
            'features': ['Resize', 'Convert formats'],
            'status': 'available'
        },
        'media_downloader': {
            'name': 'Media Downloader',
            'executable': 'Media Scraper By Asif Nawaz/MediaDownloader 1.2.exe',
            'size_mb': 40.5,
            'type': 'gui',
            'platform': 'windows',
            'description': 'Download media and images from websites',
            'features': ['Bulk download', 'Format selection', 'Auto-naming'],
            'status': 'available'
        },
        'media_extractor': {
            'name': 'Media Extractor',
            'executable': 'Media Scraper By Asif Nawaz/media_extractor 1.1.exe',
            'size_mb': 40.5,
            'type': 'gui',
            'platform': 'windows',
            'description': 'Extract media from various sources',
            'features': ['Extract metadata', 'Organize files', 'Batch operations'],
            'status': 'available'
        },
        'size_chart_generator': {
            'name': 'Size Chart Generator',
            'executable': 'SizeChartGenerator.exe',
            'size_mb': 35.9,
            'type': 'gui',
            'platform': 'windows',
            'description': 'Generate product size charts for e-commerce',
            'features': ['Custom sizes', 'Excel export', 'Multiple formats'],
            'status': 'available'
        },
        'video_resizer': {
            'name': 'Video Resizer',
            'executable': 'video_resizer_siar/video_resizer 1.1.exe',
            'size_mb': 475.5,
            'type': 'gui',
            'platform': 'windows',
            'description': 'Advanced video converter with quality presets',
            'features': ['Multiple formats', 'Quality presets', 'Batch conversion'],
            'status': 'available'
        },
        'shopify_analytics_full': {
            'name': 'Shopify Analytics (Full)',
            'executable': 'ShopifyAnalyticsApp/Run App (Analytics + Reconciliation).bat',
            'size_mb': 0.001,
            'type': 'batch',
            'platform': 'windows',
            'description': 'Full Shopify analytics with reconciliation',
            'features': ['Analytics', 'Reconciliation', 'Reports', 'Export'],
            'status': 'available'
        },
        'shopify_analytics_picker': {
            'name': 'Shopify Analytics (File Picker)',
            'executable': 'ShopifyAnalyticsApp/Run (pick files).bat',
            'size_mb': 0.001,
            'type': 'batch',
            'platform': 'windows',
            'description': 'Shopify analytics with file selection',
            'features': ['Pick files', 'Process selected', 'Quick analysis'],
            'status': 'available'
        }
    }

    def __init__(self):
        log.info("ApplicationLauncher initialized")
        self._verify_apps()

    def _verify_apps(self):
        """Verify which apps are available"""
        for app_id, config in self.REGISTERED_APPS.items():
            exe_path = self.APPS_FOLDER / config['executable']
            if exe_path.exists():
                log.info(f"[OK] {config['name']} found")
            else:
                log.warning(f"[MISSING] {config['name']} not found at {exe_path}")
                config['status'] = 'missing'

    def list_available_apps(self) -> List[Dict]:
        """List all registered applications"""
        apps = []
        for app_id, config in self.REGISTERED_APPS.items():
            apps.append({
                'id': app_id,
                'name': config['name'],
                'type': config['type'],
                'size_mb': config['size_mb'],
                'description': config['description'],
                'features': config['features'],
                'status': config['status']
            })
        return apps

    def get_app_info(self, app_id: str) -> Optional[Dict]:
        """Get detailed information about an app"""
        if app_id not in self.REGISTERED_APPS:
            log.warning(f"App not found: {app_id}")
            return None

        config = self.REGISTERED_APPS[app_id]
        exe_path = self.APPS_FOLDER / config['executable']

        return {
            'id': app_id,
            'name': config['name'],
            'executable': config['executable'],
            'full_path': str(exe_path),
            'exists': exe_path.exists(),
            'size_mb': config['size_mb'],
            'type': config['type'],
            'platform': config['platform'],
            'description': config['description'],
            'features': config['features'],
            'status': config['status']
        }

    def launch_app(self, app_id: str) -> Dict:
        """
        Launch a registered application

        Args:
            app_id: Application ID

        Returns:
            {
                'success': bool,
                'pid': process_id or None,
                'message': status message,
                'app': application name
            }
        """
        if app_id not in self.REGISTERED_APPS:
            return {
                'success': False,
                'message': f'Application not found: {app_id}'
            }

        config = self.REGISTERED_APPS[app_id]
        exe_path = self.APPS_FOLDER / config['executable']

        log.info(f"Launching: {config['name']} from {exe_path}")

        if not exe_path.exists():
            return {
                'success': False,
                'message': f'Application file not found: {exe_path}',
                'app': config['name']
            }

        try:
            # Launch application
            if config['type'] == 'batch':
                # For batch files, use cmd.exe
                process = subprocess.Popen(
                    ['cmd.exe', '/c', str(exe_path)],
                    cwd=str(exe_path.parent),
                    creationflags=subprocess.CREATE_NEW_WINDOW
                )
            else:
                # For .exe files
                process = subprocess.Popen(
                    [str(exe_path)],
                    cwd=str(exe_path.parent),
                    creationflags=subprocess.CREATE_NEW_WINDOW
                )

            log.info(f"✓ Launched {config['name']} (PID: {process.pid})")

            return {
                'success': True,
                'pid': process.pid,
                'message': f'Successfully launched {config["name"]}',
                'app': config['name']
            }

        except Exception as e:
            log.error(f"Failed to launch {config['name']}: {e}")
            return {
                'success': False,
                'message': f'Error launching application: {str(e)}',
                'app': config['name']
            }

    def get_app_status(self, app_id: str) -> Dict:
        """Get status of application"""
        if app_id not in self.REGISTERED_APPS:
            return {'status': 'unknown', 'message': 'App not found'}

        config = self.REGISTERED_APPS[app_id]
        exe_path = self.APPS_FOLDER / config['executable']

        return {
            'app': config['name'],
            'app_id': app_id,
            'status': 'available' if exe_path.exists() else 'missing',
            'executable': config['executable'],
            'exists': exe_path.exists(),
            'type': config['type']
        }

    def get_all_app_status(self) -> Dict:
        """Get status of all applications"""
        status = {}
        for app_id in self.REGISTERED_APPS.keys():
            status[app_id] = self.get_app_status(app_id)
        return status
