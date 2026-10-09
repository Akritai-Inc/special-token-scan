import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

from .errors import ScanError

PATTERNS = [
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "added_tokens.json",
    "vocab.json",
    "vocab.txt",
    "merges.txt",
    "config.json",
    "*.model",
    "chat_template.jinja",
]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def catalogue(tok):
    vocab = tok.get_added_vocab()
    special = set(tok.all_special_ids)
    special.update(i for i, a in tok.added_tokens_decoder.items() if a.special)
    ids = set(vocab.values()) | special
    items = {}
    for i in sorted(ids):
        a = tok.added_tokens_decoder.get(i)
        text = a.content if a else tok.convert_ids_to_tokens(i)
        items[i] = {
            "id": i,
            "text": text,
            "kind": "special" if i in special else "added",
            "added": i in vocab.values(),
            "properties": {
                k: getattr(a, k, None)
                for k in ("single_word", "lstrip", "rstrip", "normalized", "special")
            },
        }
    return items


def load_tokenizer(name, revision=None, offline=False, cache_dir=None, split=False):
    from huggingface_hub import snapshot_download

    local = Path(name).is_dir()
    if not local and not re.fullmatch(r"[0-9a-f]{40}", revision or ""):
        raise ScanError("E_REVISION_REQUIRED")
    try:
        folder = (
            Path(name)
            if local
            else Path(
                snapshot_download(
                    repo_id=name,
                    revision=revision,
                    allow_patterns=PATTERNS,
                    local_files_only=offline,
                    cache_dir=cache_dir,
                    token=False,
                )
            )
        )
        config_path = folder / "tokenizer_config.json"
        if config_path.is_file():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            # Explicit policy: do not resolve a repository's custom tokenizer mapping,
            # even when it also supplies a tokenizer.json or a built-in fallback.
            if (config.get("auto_map") or {}).get("AutoTokenizer"):
                raise ScanError("E_TOKENIZER_REMOTE_CODE")
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(
            str(folder),
            use_fast=True,
            trust_remote_code=False,
            local_files_only=True,
            split_special_tokens=split,
        )
    except ScanError:
        raise
    except Exception:
        raise ScanError("E_TOKENIZER_LOAD") from None
    if not tok.is_fast:
        raise ScanError("E_FAST_REQUIRED")
    files = {
        p.name: sha256(p)
        for p in sorted(folder.iterdir())
        if p.is_file() and any(p.match(pattern) for pattern in PATTERNS)
    }
    backend = json.loads(tok.backend_tokenizer.to_str())
    meta = {
        "source": name,
        "source_kind": "local" if local else "huggingface",
        "revision": None if local else revision,
        "files_sha256": files,
        "backend_sha256": digest(backend),
        "class": type(tok).__name__,
        "catalogue": list(catalogue(tok).values()),
        "settings": {
            "split_special_tokens": split,
            "add_special_tokens": False,
            "truncation": False,
            "padding": False,
            "chat_template": False,
            "trust_remote_code": False,
            "use_fast": True,
        },
        "libraries": {
            p: importlib.metadata.version(p)
            for p in ("transformers", "tokenizers", "huggingface-hub")
        },
    }
    meta["catalogue_sha256"] = digest(meta["catalogue"])
    return tok, meta
