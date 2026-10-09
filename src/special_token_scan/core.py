"""Always encode the full input unit; literal searches never gate encoding."""

from collections import Counter
from bisect import bisect_left, bisect_right

from .errors import ScanError
from .schema import Limits, extract
from .tokenizer import catalogue


def state(field, joined):
    return (
        ("both" if joined else "fields_only") if field else ("joined_only" if joined else "neither")
    )


class Segments(list):
    def __init__(self, values):
        super().__init__(values)
        self.starts = [s["start"] for s in self]
        self.ends = [s["end"] for s in self]


def origins(span, segments):
    start, end = span
    return [
        {
            "path": s["path"],
            "span": [max(start, s["start"]) - s["start"], min(end, s["end"]) - s["start"]],
        }
        for s in segments[bisect_right(segments.ends, start) : bisect_left(segments.starts, end)]
        if max(start, s["start"]) < min(end, s["end"])
    ]


def signature(event):
    return (event["id"], tuple((s["path"], *s["span"]) for s in event["sources"]))


class Scanner:
    def __init__(self, tokenizer, split=False, joins=("concat", "space"), limits=Limits()):
        self.tok = tokenizer
        self.split = split
        self.joins = joins
        self.limits = limits
        self.tokens = catalogue(tokenizer)

    def unit(self, text, segments):
        segments = Segments(segments)
        literals = []
        for i, token in self.tokens.items():
            marker = token["text"]
            if not marker:
                continue
            pos = text.find(marker)
            while pos >= 0:
                if len(literals) >= self.limits.findings:
                    raise ScanError("E_FINDINGS")
                span = [pos, pos + len(marker)]
                literals.append(
                    {
                        "id": i,
                        "kind": token["kind"],
                        "span": span,
                        "sources": origins(span, segments),
                        "encoded_indices": [],
                    }
                )
                pos = text.find(marker, pos + 1)
        literals.sort(key=lambda x: (x["span"], x["id"]))
        try:
            encoded = self.tok(
                text,
                add_special_tokens=False,
                truncation=False,
                padding=False,
                return_offsets_mapping=True,
                split_special_tokens=self.split,
                verbose=False,
            )
        except Exception:
            raise ScanError("E_ENCODE") from None
        ids, offsets = encoded["input_ids"], encoded["offset_mapping"]
        if len(ids) != len(offsets):
            raise ScanError("E_OFFSETS")
        hits = []
        by_id = {}
        for n, literal in enumerate(literals):
            by_id.setdefault(literal["id"], []).append(n)
        starts = {i: [literals[n]["span"][0] for n in indices] for i, indices in by_id.items()}
        for index, (i, offset) in enumerate(zip(ids, offsets)):
            if i not in self.tokens:
                continue
            a, b = offset
            if not 0 <= a <= b <= len(text):
                raise ScanError("E_OFFSETS")
            if len(hits) >= self.limits.findings:
                raise ScanError("E_FINDINGS")
            positions = starts.get(i, [])
            candidates = by_id.get(i, [])[bisect_left(positions, a) : bisect_right(positions, b)]
            matched = [n for n in candidates if literals[n]["span"][1] <= b]
            for n in matched:
                literals[n]["encoded_indices"].append(index)
            spans = [literals[n]["span"] for n in matched] or [[a, b]]
            sources = [s for span in spans for s in origins(span, segments)]
            hits.append(
                {
                    "id": i,
                    "kind": self.tokens[i]["kind"],
                    "token_index": index,
                    "hf_span": [a, b],
                    "literal_indices": matched,
                    "sources": sources,
                    "hf_sources": origins([a, b], segments),
                    "crosses_fields": len({s["path"] for s in sources if s["path"] is not None})
                    > 1,
                    "uses_separator": any(s["path"] is None for s in sources),
                    "literal_relation": "exact" if matched else "no_exact_literal",
                }
            )
        return {"chars": len(text), "tokens": len(ids), "literals": literals, "hits": hits}

    def record(self, row, index):
        fields, schemas, ids = extract(row, self.limits)
        reports = []
        for f in fields:
            result = self.unit(f["text"], [{"path": f["path"], "start": 0, "end": len(f["text"])}])
            reports.append({"path": f["path"], "usage": f["usage"], **result})
        all_hits = [h for f in reports for h in f["hits"]]
        literal_present = any(f["literals"] for f in reports)
        field_counts = Counter(signature(h) for h in all_hits)
        joins = {}
        for mode in self.joins:
            separator = "" if mode == "concat" else " "
            pieces, segments, pos = [], [], 0
            for n, f in enumerate(fields):
                if n and separator:
                    pieces.append(separator)
                    segments.append({"path": None, "start": pos, "end": pos + 1})
                    pos += 1
                pieces.append(f["text"])
                segments.append({"path": f["path"], "start": pos, "end": pos + len(f["text"])})
                pos += len(f["text"])
            result = self.unit("".join(pieces), segments)
            joined_counts = Counter(signature(h) for h in result["hits"])
            joins[mode] = {
                **result,
                "segments": segments,
                "literal_state": state(literal_present, bool(result["literals"])),
                "encoded_state": state(bool(all_hits), bool(result["hits"])),
                "added_occurrences": sum((joined_counts - field_counts).values()),
                "removed_occurrences": sum((field_counts - joined_counts).values()),
            }
        return {
            "type": "record",
            "index": index,
            "status": "scanned" if fields else "no_strings",
            "schemas": schemas,
            "pretokenized_paths": ids,
            "fields": reports,
            "joins": joins,
        }
