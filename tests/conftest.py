"""Test session setup.

Loads the project's ``dialectica/.env`` so the ``e2e`` skip guard can see
``GOOGLE_API_KEY`` (whether it comes from the real environment or ``.env``).
The library itself does not load ``.env`` — that is a test/app concern.

Mock helpers live in ``tests/helpers.py``.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "dialectica" / ".env", override=True)
