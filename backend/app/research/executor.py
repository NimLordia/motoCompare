import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from sqlalchemy.orm import Session

from app.research.provider import SearchProvider
from app.research.runner import run_bike_research

logger = logging.getLogger(__name__)


class BackgroundResearchExecutor:
    """In-process research execution on a small thread pool.

    One job per bike, deduplicated while in flight. Web polls task state while a
    job runs; chat awaits the same job inline through wait_for_bike. Restart
    safety comes from research_tasks itself — anything interrupted is re-run the
    next time the bike's tasks are dispatched.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        provider: SearchProvider,
        *,
        max_attempts: int = 3,
        conflict_tolerance: float = 0.15,
        max_workers: int = 2,
    ):
        self._session_factory = session_factory
        self._provider = provider
        self._max_attempts = max_attempts
        self._conflict_tolerance = conflict_tolerance
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="research")
        self._lock = threading.Lock()
        self._jobs: dict[int, Future] = {}

    def submit_bike(self, bike_id: int) -> None:
        with self._lock:
            job = self._jobs.get(bike_id)
            if job is not None and not job.done():
                return
            self._jobs[bike_id] = self._pool.submit(self._run, bike_id)

    def wait_for_bike(self, bike_id: int, timeout: float) -> bool:
        """Block until the bike's in-flight job settles; False means still running."""
        with self._lock:
            job = self._jobs.get(bike_id)
        if job is None:
            return True
        try:
            job.result(timeout=timeout)
        except FutureTimeoutError:
            return False
        return True

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _run(self, bike_id: int) -> None:
        try:
            with self._session_factory() as db:
                run_bike_research(
                    db,
                    self._provider,
                    bike_id,
                    max_attempts=self._max_attempts,
                    conflict_tolerance=self._conflict_tolerance,
                )
        except Exception:
            # run_bike_research memoizes provider failures itself; anything that
            # reaches here is a bug or an infrastructure error worth the log.
            logger.exception("research run for bike %s crashed", bike_id)
