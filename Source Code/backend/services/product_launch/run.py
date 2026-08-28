"""Development entrypoint:  python run.py  (http://127.0.0.1:5000)"""
from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    import os

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))

    # When launched from the one-click .bat (OPEN_BROWSER=1), pop the browser
    # open a moment after the server starts listening.
    if os.environ.get("OPEN_BROWSER") == "1":
        import threading
        import webbrowser

        url = f"http://127.0.0.1:{port}/admin"
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    app.run(
        host=host,
        port=port,
        debug=os.environ.get("FLASK_DEBUG", "1") == "1",
    )
