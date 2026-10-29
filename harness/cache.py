"""Content-addressed response cache: one JSON file per (model, prompt version, input, repeat)."""

import hashlib
import json
from pathlib import Path


def cache_key(model, prompt_version, input_hash, repeat):
    raw = f"{model}|{prompt_version}|{input_hash}|{repeat}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class Cache:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, key):
        return self.root / key[:2] / f"{key}.json"

    def get(self, key):
        p = self.path(key)
        return json.loads(p.read_text()) if p.exists() else None

    def put(self, key, record):
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        tmp.replace(p)
