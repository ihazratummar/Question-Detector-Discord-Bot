import logging
import asyncio
import random
from typing import Callable, TypeVar, Any

T = TypeVar("T")

def setup_logging(level=logging.INFO):
    """Configures the logging for the application."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler("exporter.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

async def exponential_backoff(
    func: Callable[..., Any],
    *args,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    **kwargs
) -> Any:
    """
    Retries an async function with exponential backoff.
    """
    retries = 0
    while True:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # You might want to catch specific exceptions here based on usage
            if retries >= max_retries:
                raise e
            
            delay = min(base_delay * (2 ** retries), max_delay)
            # Add jitter
            delay = delay * (0.5 + random.random())
            
            logging.warning(f"Error in {func.__name__}: {e}. Retrying in {delay:.2f}s...")
            await asyncio.sleep(delay)
            retries += 1
