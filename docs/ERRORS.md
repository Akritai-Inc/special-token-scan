# Error codes

| Code | Trigger |
|---|---|
| `E_POSITIVE_INTEGER` | Noninteger/zero/negative option |
| `E_INPUT_NOT_FILE` | Missing input or directory |
| `E_FORMAT` | Unrecognized extension without explicit format |
| `E_OUTPUT_EXISTS` | Existing output, including a creation race |
| `E_REVISION_REQUIRED` | Remote revision missing, symbolic, or wrong length |
| `E_TOKENIZER_LOAD` | Cannot load tokenizer locally/at the requested revision |
| `E_TOKENIZER_REMOTE_CODE` | Conservative classification of nonempty `tokenizer_config.json` `auto_map.AutoTokenizer`; includes usable built-in fallbacks, excludes `config.json` preflight |
| `E_FAST_REQUIRED` | Loaded tokenizer has no fast offsets |
| `E_IO` | Input/output filesystem error outside the reader |
| `E_INTERNAL` | Otherwise unhandled exception at the CLI boundary |
| `E_READ` | Missing stream file, corrupt/truncated gzip, including invalid compressed data |
| `E_UTF8` | Invalid UTF-8 |
| `E_JSON` | JSON syntax error or BOM |
| `E_JSON_NONFINITE` | NaN, Infinity, or float overflow |
| `E_DUPLICATE_KEY` | Duplicate JSON key or Parquet field name |
| `E_EMPTY_LINE` | Blank JSONL line |
| `E_RECORD_BYTES` | Oversized decompressed JSONL line |
| `E_JSON_BYTES` | Oversized decompressed JSON document |
| `E_PARQUET_DEPENDENCY` | Optional pyarrow missing |
| `E_PARQUET_READ` | Invalid/unreadable Parquet |
| `E_PARQUET_TYPE` | Map or union, including nested types |
| `E_DEPTH` | Configured or Python parser/traversal depth limit |
| `E_UNICODE` | Lone surrogate in decoded value |
| `E_CHARS`, `E_FIELDS` | Record character/field budget exceeded |
| `E_FINDINGS` | Literal or encoded occurrence budget exceeded |
| `E_ENCODE`, `E_OFFSETS` | Encoder exception, length mismatch, invalid range |
| `E_EMPTY_INPUT` | No records |
| `E_INPUT_CHANGED` | Before/after file hash mismatch |
| `E_INTERRUPTED` | Keyboard interrupt during processing |
| `E_RECORD_ERRORS` | Final CLI reason when row-level errors exist |

The CLI reports otherwise unhandled `Exception` instances as `E_INTERNAL` and
exits 2 without printing exception details or a traceback. Failures during record
processing finalize the summary as `failed` when output remains writable. A failure
before output creation may leave no summary; a failure during finalization may
leave `running` or partial output. Always check the exit code. Exit 1 is reserved
for a completed scan matching `--fail-on`.

A process killed before finalization leaves `running`, not a completed success.
CLI option grammar errors use argparse's usual exit 2; only positive integer
options add the stable reason above.
