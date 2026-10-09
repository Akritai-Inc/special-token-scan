import json
from collections import Counter


def write_json(path, value):
    # A complete JSON document appears only after replace; the output directory is new.
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    temp.replace(path)


def fresh_view():
    return {
        "literal_records": 0,
        "encoded_records": 0,
        "literals": 0,
        "special_ids": 0,
        "added_ids": 0,
        "no_exact_literal_ids": 0,
        "cross_field_ids": 0,
        "separator_ids": 0,
        "encoded_tokens": 0,
        "added_occurrences": 0,
        "removed_occurrences": 0,
        "literal_states": Counter(),
        "encoded_states": Counter(),
    }


class Aggregate:
    def __init__(self, joins):
        self.data = {
            "records_seen": 0,
            "records_scanned": 0,
            "records_no_strings": 0,
            "records_with_pretokenized_arrays": 0,
            "errors": Counter(),
            "string_fields": 0,
            "string_chars": 0,
            "schemas": Counter(),
            "field_usage": Counter(),
            "views": {"fields": fresh_view(), **{j: fresh_view() for j in joins}},
        }

    def add(self, row):
        d = self.data
        d["records_seen"] += 1
        if row["status"] == "error":
            d["errors"][row["reason"]] += 1
            return
        d["records_scanned"] += row["status"] == "scanned"
        d["records_no_strings"] += row["status"] == "no_strings"
        d["records_with_pretokenized_arrays"] += bool(row["pretokenized_paths"])
        d["schemas"].update(row["schemas"])
        d["string_fields"] += len(row["fields"])
        d["string_chars"] += sum(f["chars"] for f in row["fields"])
        d["field_usage"].update(f["usage"] for f in row["fields"])
        for name, view in d["views"].items():
            units = row["fields"] if name == "fields" else [row["joins"][name]]
            literals = [x for u in units for x in u["literals"]]
            hits = [x for u in units for x in u["hits"]]
            view["literal_records"] += bool(literals)
            view["encoded_records"] += bool(hits)
            view["literals"] += len(literals)
            view["encoded_tokens"] += sum(u["tokens"] for u in units)
            for hit in hits:
                view[hit["kind"] + "_ids"] += 1
                view["no_exact_literal_ids"] += hit["literal_relation"] == "no_exact_literal"
                view["cross_field_ids"] += hit["crosses_fields"]
                view["separator_ids"] += hit["uses_separator"]
            if name != "fields":
                for key in ("added_occurrences", "removed_occurrences"):
                    view[key] += units[0][key]
                for key in ("literal_state", "encoded_state"):
                    view[key + "s"][units[0][key]] += 1


def shareable(summary):
    """Allowlist only. Do not copy filenames, field paths, text or token strings."""
    t = summary["tokenizer"]
    tokenizer = {
        k: t[k]
        for k in (
            "source_kind",
            "revision",
            "backend_sha256",
            "catalogue_sha256",
            "class",
            "settings",
            "libraries",
        )
    }
    if t["source_kind"] == "huggingface":
        tokenizer["source"] = t["source"]
    return {
        "schema_version": summary["schema_version"],
        "tool": summary["tool"],
        "status": summary["status"],
        "failure": summary["failure"],
        "started_utc": summary["started_utc"],
        "ended_utc": summary["ended_utc"],
        "input": {k: summary["input"][k] for k in ("sha256", "bytes", "format")},
        "tokenizer": tokenizer,
        "scan": summary["scan"],
        "counts": summary["counts"],
    }
