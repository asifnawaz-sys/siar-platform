#!/usr/bin/env python3
"""
SIAR Digital Platform - PyWebView Launcher
Cross-platform desktop application wrapper
Launches Flask backend + native desktop window
Works on Windows, macOS, and Linux
"""

import os
import sys
import subprocess
import time
import socket
import threading
from pathlib import Path
import platform

try:
    import webview
except ImportError:
    print("PyWebView not installed. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pywebview"])
    import webview


class SIARPlatformApp:
    def __init__(self):
        self.platform = platform.system()
        self.port = 8765
        self.host = '127.0.0.1'
        self.base_url = f'http://{self.host}:{self.port}'
        self.root_dir = Path(__file__).parent.resolve()
        self.backend_dir = self.root_dir / 'Source Code' / 'backend'
        self.server_process = None
        self.window = None

    def print_header(self):
        """Display welcome message"""
        print("\n" + "="*70)
        print("  SIAR DIGITAL PLATFORM")
        print("  Cross-Platform Desktop Application")
        print("  Version 5.0 (PyWebView Edition)")
        print("="*70 + "\n")

    def check_python(self):
        """Verify Python version"""
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 9):
            print(f"ERROR: Python 3.9+ required (found {version.major}.{version.minor})")
            sys.exit(1)
        print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
        return True

    def check_dependencies(self):
        """Check required packages"""
        required = [
            'flask', 'flask_cors', 'sqlalchemy', 'pillow',
            'opencv-python', 'requests', 'pyjwt', 'webview'
        ]
        missing = []

        for package in required:
            try:
                __import__(package.replace('-', '_').replace('opencv', 'cv2'))
            except ImportError:
                missing.append(package)

        if missing:
            print(f"Installing missing packages: {', '.join(missing)}...")
            for package in missing:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print("✓ Dependencies installed")
        else:
            print("✓ All dependencies available")
        return True

    def is_port_available(self):
        """Check if port is free"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            return result != 0
        except:
            return True

    def start_backend(self):
        """Start Flask server in background"""
        if not self.is_port_available():
            print(f"ERROR: Port {self.port} already in use")
            sys.exit(1)

        print(f"\n▶ Starting SIAR Platform backend...")

        env = os.environ.copy()
        env['PYTHONPATH'] = str(self.backend_dir)
        env['FLASK_ENV'] = 'production'
        env['PORT'] = str(self.port)

        try:
            app_file = self.backend_dir / 'app.py'
            if not app_file.exists():
                print(f"ERROR: app.py not found at {app_file}")
                sys.exit(1)

            self.server_process = subprocess.Popen(
                [sys.executable, str(app_file)],
                cwd=str(self.backend_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            print("✓ Backend server started")
            return True
        except Exception as e:
            print(f"ERROR: Failed to start server: {e}")
            return False

    def wait_for_server(self, timeout=30):
        """Wait for Flask to be ready"""
        print("⏳ Waiting for server to be ready...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex((self.host, self.port))
                sock.close()
                if result == 0:
                    print("✓ Server is ready")
                    return True
            except:
                pass
            time.sleep(0.5)

        print("ERROR: Server did not start in time")
        return False

    def start_desktop_window(self):
        """Create native desktop window"""
        print(f"\n▶ Creating SIAR Platform window...")

        try:
            # Configure window based on platform
            if self.platform == 'Darwin':  # macOS
                min_size = (900, 700)
                size = (1400, 900)
            else:  # Windows, Linux
                min_size = (800, 600)
                size = (1400, 900)

            # Create native window
            self.window = webview.create_window(
                title='SIAR Digital Platform',
                url=self.base_url,
                width=size[0],
                height=size[1],
                min_size=min_size,
                resizable=True,
                fullscreen=False,
                background_color='#ffffff'
            )

            print("✓ Application window created")
            return self.window
        except Exception as e:
            print(f"ERROR: Failed to create window: {e}")
            return None

    def run(self):
        """Main application flow"""
        self.print_header()

        # Step 1: Check Python
        if not self.check_python():
            return False

        # Step 2: Check dependencies
        if not self.check_dependencies():
            return False

        # Step 3: Start backend
        if not self.start_backend():
            return False

        # Step 4: Wait for backend
        if not self.wait_for_server():
            if self.server_process:
                self.server_process.terminate()
            return False

        # Step 5: Create desktop window
        if not self.start_desktop_window():
            if self.server_process:
                self.server_process.terminate()
            return False

        # Step 6: Start webview (blocks until window closed)
        try:
            print("\n✓ SIAR Platform is running")
            print("  Click menu items to access different modules\n")
            webview.start(debug=False)
        except KeyboardInterrupt:
            print("\n⏹ Shutting down...")
        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            # Cleanup
            if self.server_process:
                self.server_process.terminate()
                try:
                    self.server_process.wait(timeout=5)
                except:
                    self.server_process.kill()
            print("✓ SIAR Platform closed")

        return True


def main():
    """Entry point"""
    app = SIARPlatformApp()
    success = app.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
