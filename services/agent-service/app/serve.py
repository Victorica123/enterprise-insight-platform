"""Container entry point; worker count is explicit because caches are per process."""

import uvicorn

from app.config import get_settings, load_local_env


def main() -> None:
    load_local_env()
    settings = get_settings()
    settings.validate()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, workers=settings.workers)


if __name__ == "__main__":
    main()
