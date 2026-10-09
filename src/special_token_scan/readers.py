import gzip
import json
import math
import zlib
from pathlib import Path

from .errors import ScanError
from .schema import Limits


def _pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ScanError("E_DUPLICATE_KEY")
        result[k] = v
    return result


def _constant(_):
    raise ScanError("E_JSON_NONFINITE")


def _float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ScanError("E_JSON_NONFINITE")
    return value


def parse(data):
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        raise ScanError("E_UTF8") from None
    try:
        return json.loads(
            text, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float
        )
    except RecursionError:
        raise ScanError("E_DEPTH") from None
    except (ValueError, OverflowError):
        raise ScanError("E_JSON") from None


def infer_format(path, requested="auto"):
    if requested != "auto":
        return requested
    name = str(path).lower().removesuffix(".gz")
    if name.endswith((".jsonl", ".ndjson")):
        return "jsonl"
    if name.endswith(".json"):
        return "json"
    if name.endswith(".parquet") and not str(path).lower().endswith(".gz"):
        return "parquet"
    raise ScanError("E_FORMAT")


def detect_format(path, requested="auto", limits=Limits()):
    """Disambiguate .json using a bounded probe; explicit formats never probe."""
    fmt = infer_format(path, requested)
    if requested != "auto" or fmt != "json":
        return fmt
    opener = gzip.open if str(path).lower().endswith(".gz") else open
    try:
        with opener(path, "rb") as stream:
            remaining = limits.json_bytes + 1
            while remaining:
                line = stream.readline(remaining)
                remaining -= len(line)
                if not line:
                    return "json"
                if line.strip(b" \t\r\n"):
                    break
            else:
                return "json"
            while remaining:
                chunk = stream.read(min(remaining, 8192))
                remaining -= len(chunk)
                if not chunk:
                    break
                if chunk.strip(b" \t\r\n"):
                    # Parse only when another value could follow. Single JSON
                    # documents without further content are parsed by the reader.
                    try:
                        parse(line)
                    except ScanError:
                        return "json"
                    return "jsonl"
    except (OSError, EOFError, zlib.error):
        raise ScanError("E_READ") from None
    return "json"


def _check_arrow_type(t, pa):
    if pa.types.is_map(t) or pa.types.is_union(t):
        raise ScanError("E_PARQUET_TYPE")
    if pa.types.is_struct(t):
        if len({f.name for f in t}) != len(t):
            raise ScanError("E_DUPLICATE_KEY")
        for f in t:
            _check_arrow_type(f.type, pa)
    elif pa.types.is_list(t) or pa.types.is_large_list(t) or pa.types.is_fixed_size_list(t):
        _check_arrow_type(t.value_type, pa)
    elif pa.types.is_dictionary(t):
        _check_arrow_type(t.value_type, pa)


def records(path, fmt="auto", limits=Limits()):
    """Yield (zero-based record index, row or ScanError). File errors are fatal."""
    path = Path(path)
    fmt = detect_format(path, fmt, limits)
    try:
        if fmt == "parquet":
            try:
                import pyarrow as pa
                import pyarrow.parquet as pq
            except ImportError:
                raise ScanError("E_PARQUET_DEPENDENCY") from None
            try:
                parquet = pq.ParquetFile(path)
                with parquet:
                    if len(set(parquet.schema_arrow.names)) != len(parquet.schema_arrow.names):
                        raise ScanError("E_DUPLICATE_KEY")
                    for field in parquet.schema_arrow:
                        _check_arrow_type(field.type, pa)
                    index = 0
                    for batch in parquet.iter_batches(batch_size=64):
                        for row in batch.to_pylist():
                            yield index, row
                            index += 1
            except ScanError:
                raise
            except Exception:
                raise ScanError("E_PARQUET_READ") from None
            return
        opener = gzip.open if str(path).lower().endswith(".gz") else open
        with opener(path, "rb") as f:
            if fmt == "json":
                data = f.read(limits.json_bytes + 1)
                if len(data) > limits.json_bytes:
                    raise ScanError("E_JSON_BYTES")
                value = parse(data)
                for index, row in enumerate(value if isinstance(value, list) else [value]):
                    yield index, row
            else:
                index = 0
                while True:
                    data = f.readline(limits.record_bytes + 1)
                    if not data:
                        break
                    try:
                        if len(data) > limits.record_bytes:
                            while data and not data.endswith(b"\n"):
                                data = f.readline(limits.record_bytes + 1)
                            raise ScanError("E_RECORD_BYTES")
                        if not data.strip():
                            raise ScanError("E_EMPTY_LINE")
                        row = parse(data)
                    except ScanError as error:
                        row = error
                    yield index, row
                    index += 1
    except (OSError, EOFError, zlib.error):
        raise ScanError("E_READ") from None
