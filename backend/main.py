"""Entry point for the retail assistant backend."""

import logging

import uvicorn

from backend.app import create_app
from backend.config import get_settings

logging.basicConfig(level=logging.INFO)

app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
