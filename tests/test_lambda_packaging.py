"""Guards on the Lambda packaging that unit tests of the app cannot catch.

These are deliberately static checks over source text rather than imports.
Importing `api.lambda_handler` runs its S3 fetch at module scope, which is the
whole point of the thing being tested — so the test would have to defeat the
behaviour it is verifying.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDLER = ROOT / "api" / "lambda_handler.py"
DOCKERFILE = ROOT / "Dockerfile.lambda"


def test_app_is_imported_after_the_snapshot_is_fetched():
    """The one ordering that breaks the function at cold start.

    `api.app` resolves DB_PATH at import time, so the snapshot must be on disk
    and TRADEWATCH_DB set before that import runs. A linter or an autoformatter
    that hoists imports to the top of the file — which is what they are for —
    silently reintroduces this. The failure mode is a confusing runtime error
    about a missing ./data/snapshot.db, not an import error.
    """
    src = HANDLER.read_text()
    fetch_call = src.index("\n_fetch_snapshot()")
    set_env = src.index('os.environ["TRADEWATCH_DB"]')
    import_app = src.index("from api.app import app")

    assert fetch_call < set_env < import_app, (
        "api.app must be imported only after _fetch_snapshot() has run and "
        "TRADEWATCH_DB has been set"
    )


def test_handler_writes_to_the_only_writable_path():
    """/tmp is the sole writable location in a Lambda execution environment."""
    src = HANDLER.read_text()
    assert 'Path("/tmp/' in src


def test_dockerfile_cmd_matches_the_real_handler_attribute():
    """A CMD typo is only discovered on first invocation, in the cloud."""
    cmd = re.search(r'^CMD\s+\[(.+)\]', DOCKERFILE.read_text(), re.M)
    assert cmd, "Dockerfile.lambda must declare a CMD"
    target = cmd.group(1).strip().strip('"')

    module, _, attribute = target.rpartition(".")
    assert module == "api.lambda_handler", target
    assert f"\n{attribute} = Mangum(" in HANDLER.read_text(), (
        f"Dockerfile CMD points at {target!r} but that attribute is not defined"
    )


def test_lambda_image_does_not_bake_in_the_snapshot():
    """If the image still carried data/snapshot.db, the S3 bucket and the
    least-privilege IAM policy around it would be decoration.

    Checks instructions only — the Dockerfile mentions the snapshot in a comment
    explaining precisely why it is absent, and that comment is worth keeping.
    """
    instructions = [
        line for line in DOCKERFILE.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    offenders = [l for l in instructions if "snapshot" in l.lower()]
    assert not offenders, f"Lambda image must not carry the snapshot: {offenders}"
