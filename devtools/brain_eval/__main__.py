"""Direct module entry delegates to the same Brain evaluation CLI."""

from __future__ import annotations

import argparse

from devtools.brain_eval.cli import configure_parser, run


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m devtools.brain_eval")
    configure_parser(parser)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
