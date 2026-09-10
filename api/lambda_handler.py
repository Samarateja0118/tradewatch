"""Lambda entrypoint: fetch the snapshot from S3, then serve the FastAPI app.

ORDER MATTERS IN THIS FILE, and not in a way that is obvious from reading it
top to bottom. `api.app` resolves `DB_PATH` at *import* time, and its lifespan
raises if the file is missing. So the snapshot has to be on disk and
`TRADEWATCH_DB` has to be set BEFORE `api.app` is imported. The import sits
below the fetch on purpose; moving it to the top of the file, where a linter
will want to put it, breaks the function at cold start with a confusing
"No database at ./data/snapshot.db".

/tmp is the only writable path in a Lambda execution environment, which is why
the local path is hardcoded rather than configurable.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import boto3

log = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)

BUCKET = os.environ["TRADEWATCH_SNAPSHOT_BUCKET"]
KEY = os.environ.get("TRADEWATCH_SNAPSHOT_KEY", "snapshot.db")
LOCAL_DB = Path("/tmp/tradewatch.db")


def _fetch_snapshot() -> None:
    """Download the snapshot once per execution environment.

    Warm containers keep /tmp, so this runs on cold start only. The tradeoff is
    that a warm container serves the snapshot it started with: after the
    pipeline uploads fresher data, already-warm environments stay stale until
    AWS recycles them (minutes to hours). For a dashboard over documents that
    are published daily that is acceptable, and it is far cheaper than a HEAD
    request against S3 on every invocation. If it ever stops being acceptable,
    compare ETags here rather than re-downloading blind.
    """
    if LOCAL_DB.exists():
        return
    log.info("cold start: downloading s3://%s/%s", BUCKET, KEY)
    boto3.client("s3").download_file(BUCKET, KEY, str(LOCAL_DB))
    log.info("snapshot ready: %d bytes", LOCAL_DB.stat().st_size)


_fetch_snapshot()
os.environ["TRADEWATCH_DB"] = str(LOCAL_DB)

from mangum import Mangum  # noqa: E402  (see module docstring)

from api.app import app  # noqa: E402  (must follow _fetch_snapshot)

# Function URLs deliver payload format 2.0; Mangum detects it. `lifespan="auto"`
# runs the app's startup hook, which is what opens the SQLite connection.
handler = Mangum(app, lifespan="auto")
