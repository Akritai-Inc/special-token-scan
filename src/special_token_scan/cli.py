import argparse
import importlib.metadata
import itertools
import json
import os
import platform
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .core import Scanner
from .errors import ScanError
from .output import Aggregate, shareable, write_json
from .readers import infer_format, records
from .schema import Limits
from .tokenizer import digest, load_tokenizer, sha256


def now():
    return datetime.now(timezone.utc).isoformat()


def positive(text):
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("E_POSITIVE_INTEGER") from None
    if n <= 0:
        raise argparse.ArgumentTypeError("E_POSITIVE_INTEGER")
    return n


def parser():
    p = argparse.ArgumentParser(
        prog="special-token-scan",
        description="Inspect local data strings and registered tokenizer IDs.",
    )
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("input", type=Path)
    p.add_argument("--tokenizer", required=True)
    p.add_argument("--revision", help="Required immutable 40-character commit for HF repositories")
    p.add_argument("--out", type=Path, required=True, help="A NEW output directory")
    p.add_argument("--format", choices=("auto", "json", "jsonl", "parquet"), default="auto")
    p.add_argument("--joins", choices=("both", "concat", "space"), default="both")
    p.add_argument("--split-special-tokens", action="store_true")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--cache-dir")
    p.add_argument(
        "--aggregate-only", action="store_true", help="Do not write record-level results"
    )
    p.add_argument(
        "--limit", type=positive, help="Inspect only the first N records; report partial coverage"
    )
    p.add_argument("--fail-on", choices=("never", "literal", "encoded"), default="never")
    for name, default in asdict(Limits()).items():
        p.add_argument("--max-" + name.replace("_", "-"), type=positive, default=default)
    return p


def run(args):
    # Disable optional Hub telemetry and implicit authentication; only public downloads.
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    if not args.input.is_file():
        raise ScanError("E_INPUT_NOT_FILE")
    fmt = infer_format(args.input, args.format)
    if args.out.exists() or args.out.is_symlink():
        raise ScanError("E_OUTPUT_EXISTS")
    tok, tokenizer_meta = load_tokenizer(
        args.tokenizer, args.revision, args.offline, args.cache_dir, args.split_special_tokens
    )
    limits = Limits(**{k: getattr(args, "max_" + k) for k in asdict(Limits())})
    joins = ("concat", "space") if args.joins == "both" else (args.joins,)
    scanner = Scanner(tok, args.split_special_tokens, joins, limits)
    aggregate = Aggregate(joins)
    initial_hash = sha256(args.input)
    summary = {
        "schema_version": 1,
        "tool": {
            "name": "special-token-scan",
            "version": __version__,
            "python": platform.python_version(),
            "source_sha256": digest(
                {p.name: sha256(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
            ),
        },
        "status": "running",
        "failure": None,
        "started_utc": now(),
        "ended_utc": None,
        "input": {
            "path": str(args.input.resolve()),
            "sha256": initial_hash,
            "bytes": args.input.stat().st_size,
            "format": fmt,
        },
        "tokenizer": tokenizer_meta,
        "scan": {
            "joins": list(joins),
            "join_scope": "all_string_values",
            "order": "depth_first_stored_order",
            "offset_unit": "unicode_code_points",
            "limits": asdict(limits),
            "record_limit": args.limit,
            "coverage": "prefix_requested" if args.limit else "whole_file",
            "reached_eof": False,
            "fail_on": args.fail_on,
        },
        "counts": aggregate.data,
    }
    if fmt == "parquet":
        try:
            summary["tool"]["pyarrow"] = importlib.metadata.version("pyarrow")
        except importlib.metadata.PackageNotFoundError:
            pass  # The reader emits E_PARQUET_DEPENDENCY.
    try:
        args.out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ScanError("E_OUTPUT_EXISTS") from None
    write_json(args.out / "summary.json", summary)
    output = None
    try:
        if not args.aggregate_only:
            output = (args.out / "records.jsonl").open("w", encoding="utf-8", newline="\n")
        iterator = records(args.input, fmt, limits)
        selected = itertools.islice(iterator, args.limit) if args.limit else iterator
        try:
            for index, row in selected:
                try:
                    if isinstance(row, ScanError):
                        raise row
                    result = scanner.record(row, index)
                except ScanError as error:
                    result = {
                        "type": "record",
                        "index": index,
                        "status": "error",
                        "reason": error.code,
                    }
                aggregate.add(result)
                if output:
                    output.write(json.dumps(result, ensure_ascii=True) + "\n")
            # With a limit, do not consume even one record outside the requested prefix.
            summary["scan"]["reached_eof"] = (
                args.limit is None or aggregate.data["records_seen"] < args.limit
            )
        finally:
            iterator.close()
        if sha256(args.input) != initial_hash:
            raise ScanError("E_INPUT_CHANGED")
        if not aggregate.data["records_seen"]:
            raise ScanError("E_EMPTY_INPUT")
        summary["status"] = "complete" if not aggregate.data["errors"] else "incomplete"
    except ScanError as error:
        summary["status"], summary["failure"] = "failed", error.code
    except OSError:
        summary["status"], summary["failure"] = "failed", "E_IO"
    except Exception:
        summary["status"], summary["failure"] = "failed", "E_INTERNAL"
    except KeyboardInterrupt:
        summary["status"], summary["failure"] = "failed", "E_INTERRUPTED"
    finally:
        if output:
            output.close()
    summary["ended_utc"] = now()
    write_json(args.out / "summary.json", summary)
    write_json(args.out / "share.json", shareable(summary))
    d = aggregate.data
    line = (
        f"{summary['status']}: {d['records_scanned']} records with strings; "
        f"{d['records_no_strings']} without strings; {sum(d['errors'].values())} record errors.\n"
    )
    for name, view in d["views"].items():
        line += (
            f"{name}: literal records={view['literal_records']}, "
            f"encoded records={view['encoded_records']}, special IDs={view['special_ids']}, "
            f"non-special added IDs={view['added_ids']}\n"
        )
    (args.out / "summary.txt").write_text(line, encoding="utf-8", newline="\n")
    print(line, end="")
    if summary["status"] != "complete":
        print(summary["failure"] or "E_RECORD_ERRORS", file=sys.stderr)
        return 2
    metric = args.fail_on + "_records"
    return int(args.fail_on != "never" and any(v.get(metric, 0) for v in d["views"].values()))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return run(args)
    except ScanError as error:
        print(error.code, file=sys.stderr)
        return 2
    except OSError:
        print("E_IO", file=sys.stderr)
        return 2
    except Exception:
        print("E_INTERNAL", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
