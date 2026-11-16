"""Write the OpenAPI document deterministically (ADR-0004).

    uv run python -m scripts.export_openapi ../packages/api-client/openapi.json

Builds the app object without starting a server or connecting to the database.
"""

import json
import sys
from pathlib import Path

from app.config import Settings
from app.main import create_app


def export_openapi() -> str:
    app = create_app(Settings(_env_file=None, environment="test"))
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m scripts.export_openapi <output.json>", file=sys.stderr)
        return 2
    output = Path(argv[0])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(export_openapi(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
