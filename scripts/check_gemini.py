"""Verify that the configured Gemini API key and model are usable."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google import genai

DEFAULT_MODEL = "gemini-3.5-flash"


def main() -> None:
    load_dotenv()
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is missing. Copy .env.example to .env and set it.")

    client = genai.Client()
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents="Reply with exactly: RiskMesh Gemini ready",
    )
    print(response.text.strip())


if __name__ == "__main__":
    main()
