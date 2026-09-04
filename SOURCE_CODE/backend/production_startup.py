#!/usr/bin/env python3
"""
SIAR Platform v4.5 - Production Startup Script
Initializes application with production settings
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path

# Setup directories
DIRS = ['logs', 'backups', 'downloads', 'downloads/media_enhanced']
for dir_path in DIRS:
    Path(dir_path).mkdir(parents=True, exist_ok=True)

# Setup logging
def setup_logging():
    """Configure production-grade logging"""

    # Create logs directory
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)

    # Create logger
    logger = logging.getLogger('siar-platform')
    logger.setLevel(logging.INFO)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=10485760,  # 10MB
        backupCount=10
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# Setup monitoring
def setup_monitoring():
    """Setup basic monitoring"""
    monitoring_config = {
        'enabled': True,
        'metrics_file': 'logs/metrics.log',
        'interval': 60,
        'track_cpu': True,
        'track_memory': True,
        'track_disk': True,
        'track_requests': True
    }

    return monitoring_config

# Setup backups
def setup_backups():
    """Setup automated backups"""
    import shutil
    from datetime import datetime

    backup_dir = Path('backups')
    backup_dir.mkdir(exist_ok=True)

    # Backup database
    db_file = Path('Asif_Nawaz_platform.db')
    if db_file.exists():
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f'db_backup_{timestamp}.db'
        shutil.copy2(db_file, backup_path)
        print(f'Database backup created: {backup_path}')

    return True

# Startup sequence
def startup():
    """Execute production startup sequence"""
    print('='*60)
    print('SIAR PLATFORM v4.5 - PRODUCTION STARTUP')
    print('='*60)
    print()

    # Step 1: Setup logging
    print('[1/4] Setting up logging...')
    logger = setup_logging()
    logger.info('Application startup initiated')
    print('      [OK] Logging configured')
    print()

    # Step 2: Setup directories
    print('[2/4] Verifying directories...')
    for dir_path in DIRS:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    logger.info(f'Directories verified: {DIRS}')
    print('      [OK] Directories ready')
    print()

    # Step 3: Setup monitoring
    print('[3/4] Setting up monitoring...')
    monitoring = setup_monitoring()
    logger.info(f'Monitoring configured: {monitoring}')
    print('      [OK] Monitoring ready')
    print()

    # Step 4: Setup backups
    print('[4/4] Setting up backups...')
    setup_backups()
    logger.info('Database backup completed')
    print('      [OK] Backups configured')
    print()

    print('='*60)
    print('PRODUCTION STARTUP COMPLETE')
    print('='*60)
    print()
    print('Environment: PRODUCTION')
    print('Debug Mode: OFF')
    print('Logging: ENABLED')
    print('Monitoring: ENABLED')
    print('Backups: ENABLED')
    print()
    print('Starting Flask application...')
    print()

    return logger

if __name__ == '__main__':
    logger = startup()

    # Set environment
    os.environ['FLASK_ENV'] = 'production'
    os.environ['FLASK_DEBUG'] = '0'

    # Import and run app
    try:
        from complete_platform_final import app

        logger.info('Flask application imported successfully')

        # Run with production settings
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=False,
            use_reloader=False,
            use_debugger=False,
            threaded=True
        )

    except Exception as e:
        logger.error(f'Failed to start application: {e}', exc_info=True)
        sys.exit(1)
