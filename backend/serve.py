# Console entry point: `subwatch` starts the local server.
import os

import uvicorn

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def main() -> None:
    host = os.environ.get("SUBWATCH_HOST", DEFAULT_HOST)
    port = int(os.environ.get("SUBWATCH_PORT", str(DEFAULT_PORT)))
    uvicorn.run("backend.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
