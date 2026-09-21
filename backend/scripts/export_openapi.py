"""Dump the API's OpenAPI document to stdout or a file — input for the FE type generator.

python scripts/export_openapi.py [out.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from emap.api import create_app

doc = create_app().openapi()
text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
if len(sys.argv) > 1:
    Path(sys.argv[1]).write_text(text, encoding="utf-8")
    print(f"wrote {sys.argv[1]}")
else:
    sys.stdout.write(text)
