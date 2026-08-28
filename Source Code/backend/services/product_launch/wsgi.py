"""Production WSGI entrypoint.

Linux:   gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app
Windows: waitress-serve --listen=0.0.0.0:8000 wsgi:app
"""
from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402

app = create_app()
