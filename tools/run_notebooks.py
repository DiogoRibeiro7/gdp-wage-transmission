"""Execute the notebooks in place so the committed copies carry their outputs.

Notebooks are committed with outputs on purpose: a reader should see what the estimators
actually produce without installing anything or waiting for a bootstrap to finish. That only
works if the outputs are current, so the notebooks are regenerated and re-executed together
rather than edited by hand.

Execution happens with the notebook directory as the working directory, which is what the
relative ``../data`` and ``../results`` paths inside them assume.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

NOTEBOOK_DIR = Path("notebooks")
DEFAULT_TIMEOUT = 900


def execute(path: Path, *, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """Execute one notebook in place. Returns True when every cell succeeded."""
    notebook = nbformat.read(path, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(path.parent)}},
    )
    try:
        client.execute()
    except CellExecutionError as error:
        print(f"FAILED  {path.name}: {error}".splitlines()[0])
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            nbformat.write(notebook, handle)
        return False
    # LF explicitly: notebook bytes are hashed into the release manifest.
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        nbformat.write(notebook, handle)
    executed = sum(1 for cell in notebook.cells if cell.cell_type == "code")
    print(f"ok      {path.name} ({executed} code cells)")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("notebooks", nargs="*", type=Path)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)

    paths = args.notebooks or sorted(NOTEBOOK_DIR.glob("*.ipynb"))
    if not paths:
        print("No notebooks found.")
        return 1

    failures = [path for path in paths if not execute(path, timeout=args.timeout)]
    if failures:
        print(f"\n{len(failures)} notebook(s) failed: {[p.name for p in failures]}")
        return 1
    print(f"\nAll {len(paths)} notebooks executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
