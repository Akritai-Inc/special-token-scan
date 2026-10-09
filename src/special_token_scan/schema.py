"""Conservative, additive schema hints; these never select what gets scanned."""

import re
from dataclasses import dataclass

from .errors import ScanError


@dataclass(frozen=True)
class Limits:
    record_bytes: int = 16 * 1024 * 1024
    json_bytes: int = 64 * 1024 * 1024
    chars: int = 2_000_000
    fields: int = 100_000
    depth: int = 64
    findings: int = 100_000


def pointer(parts):
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def recognize(row):
    if not isinstance(row, dict):
        return ["unknown"]
    names = []
    for key, name in [
        ("messages", "messages"),
        ("conversations", "sharegpt"),
        ("conversation", "wildchat"),
        ("contents", "gemini"),
    ]:
        if isinstance(row.get(key), list):
            names.append(name)
    if row.get("schemaVersion") == "bedrock-conversation-2024":
        names.append("bedrock")
    for keys, name in [
        (("instruction", "input", "output"), "alpaca"),
        (("instruction", "context", "response"), "dolly"),
        (("prompt", "completion"), "prompt_completion"),
        (("prompt", "response"), "prompt_response"),
        (("instruction", "response"), "instruction_response"),
        (("inputs", "targets"), "inputs_targets"),
        (("text",), "text"),
        (("chosen", "rejected"), "preference"),
    ]:
        if all(k in row for k in keys):
            names.append(name)
    return names or ["unknown"]


def usage(path, schemas):
    # A hint that a field commonly reaches a training renderer, not a service contract.
    flat = {
        "alpaca": {"/instruction", "/input", "/output"},
        "dolly": {"/instruction", "/context", "/response"},
        "prompt_completion": {"/prompt", "/completion"},
        "prompt_response": {"/prompt", "/response"},
        "instruction_response": {"/instruction", "/response"},
        "inputs_targets": {"/inputs", "/targets"},
        "text": {"/text"},
        "preference": {"/prompt", "/chosen", "/rejected"},
    }
    if any(path in flat.get(s, set()) for s in schemas):
        return "training_text_candidate"
    if re.fullmatch(
        r"/(messages|conversation|conversations|chosen|rejected)/\d+/(content|reasoning_content)",
        path,
    ):
        return "training_text_candidate"
    if re.fullmatch(r"/conversations/\d+/value", path):
        return "training_text_candidate"
    if re.fullmatch(r"/messages/\d+/content/\d+/text", path):
        return "training_text_candidate"
    if re.fullmatch(
        r"/(system/\d+/text|system|systemInstruction/parts/\d+/text|contents/\d+/parts/\d+/text)",
        path,
    ):
        return "training_text_candidate"
    if re.fullmatch(
        r"/(messages|conversation|conversations|contents|chosen|rejected)/\d+/(role|from)", path
    ):
        return "training_structure_candidate"
    if path.startswith("/tools/") or re.match(r"/messages/\d+/(tool_calls|function_call)/", path):
        return "training_structure_candidate"
    return "unknown"


def extract(row, limits=Limits()):
    """All decoded string values, including empty strings; no key or scalar coercion."""
    fields, ids = [], []
    total = 0
    schemas = recognize(row)

    def walk(value, parts, depth):
        nonlocal total
        if depth > limits.depth:
            raise ScanError("E_DEPTH")
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeError:
                raise ScanError("E_UNICODE") from None
            total += len(value)
            if total > limits.chars:
                raise ScanError("E_CHARS")
            if len(fields) >= limits.fields:
                raise ScanError("E_FIELDS")
            p = pointer(parts)
            fields.append({"path": p, "text": value, "usage": usage(p, schemas)})
        elif isinstance(value, dict):
            for k, v in value.items():
                # JSON object keys are strings. Parquet maps are deliberately unsupported.
                walk(v, (*parts, k), depth + 1)
        elif isinstance(value, list):
            if parts and parts[-1] in ("input_ids", "labels", "attention_mask", "position_ids"):
                ids.append(pointer(parts))
            for i, v in enumerate(value):
                walk(v, (*parts, i), depth + 1)

    try:
        walk(row, (), 0)
    except RecursionError:
        raise ScanError("E_DEPTH") from None
    return fields, schemas, ids
