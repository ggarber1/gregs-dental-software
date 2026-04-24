import asyncio
import logging
import sys


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    from app.workers.reminder_worker import run

    asyncio.run(run())


if __name__ == "__main__":
    main()
