# Output contract, schema_version 1

`records.jsonl` has one row per processed record (including errors). `index` is
zero-based: JSONL physical line minus one; JSON array index; Parquet file row.
A single JSON value has index 0. This index is not a dataset-provided identifier.

| Field | Meaning |
|---|---|
| `status` | `scanned`, `no_strings`, or `error` |
| `reason` | Stable error code, only on error rows |
| `schemas` | Additive recognized shapes, or `unknown`; not schema validation |
| `pretokenized_paths` | Named ID/mask arrays; contents are not treated as IDs to audit |
| `fields` | All string values, including empty strings, in traversal order |
| `joins` | Requested concat/space results over those fields |

Each field has an RFC 6901 JSON Pointer `path` (root string: `""`), a `usage` hint,
`chars`, total encoded `tokens`, `literals`, and `hits`. The original field value
and surrounding text are omitted. JSON `~` and `/` in keys escape as `~0` and `~1`.

Each literal has `id`, `kind` (`special` or non-special `added`), exact decoded
`span`, per-field `sources`, and `encoded_indices` of same-ID encoded tokens whose
HF span contains it. An empty list means the literal was not associated with that
ID at that location. Literals can overlap; an ID alone does not prove how the
tokenizer's internal matching path reached it. Empty registered strings have no
literal occurrences by definition.

Each hit is an actual output ID and carries its `token_index`, `hf_span`, matching
`literal_indices`, `sources`, `hf_sources`, `literal_relation`, `crosses_fields`,
and `uses_separator`. With an exact literal match, `sources` describes its literal
span; otherwise it describes the HF span and `literal_relation=no_exact_literal`.
`hf_sources` always describes the possibly wider tokenizer span. All offsets are
Unicode code-point `[start,end)` positions, not UTF-8 bytes or escaped JSON offsets.
Normalized spans are tokenizer-provided alignments, not reconstructed spellings.
Zero-width offsets may have no source entries; special-token-scan does not invent provenance.

Join `segments` map the joined offsets to field paths, preserving empty segments.
Separators have `path: null`. A hit consuming only leading whitespace from another
field is not labeled as crossing fields if its matched literal is inside one
field. Without an exact literal the crossing flag is based on the HF span and
should be interpreted accordingly. Text transformations other than the specified
separator are not applied.

`uses_separator` is true exactly when a hit's **`sources`** contains an inserted
separator (`path: null`). With an exact literal match, it asks whether an inserted
separator contributes to the literal spelling. It does not ask whether the wider
HF offset touched a separator. If `lstrip` or `rstrip` consumes a separator only
as surrounding whitespace, `uses_separator` is **false** when the matched literal
itself stays inside data fields; that consumption is visible in `hf_sources`.
Without an exact literal match, `sources` falls back to the HF span, so the flag
instead reflects separator overlap of that alignment. `separator_ids` aggregates
this same flag. A space already present in an input field is data, not an inserted
separator, and cannot set the flag by itself.

`literal_state` and `encoded_state` independently describe whether any event was
observed in each view:

| Fields have an event | Joined has an event | State |
|---|---|---|
| no | no | `neither` |
| yes | no | `fields_only` |
| no | yes | `joined_only` |
| yes | yes | `both` |

`added_occurrences` / `removed_occurrences` compare **encoded** occurrence multisets,
identified by `(ID, ordered source paths and per-field spans)`. Thus `both` can
still have changes. Source spans, including explicit separator entries, determine
identity; this is not a semantic alignment of the entire token sequence.

`summary.json` and `share.json` contain aggregates for `fields`, `concat`, and/or
`space`. `literal_records` / `encoded_records` count records with at least one
event, while `literals`, `special_ids`, `added_ids` count occurrences. `encoded_tokens`
counts every output ID, including ordinary vocabulary. Fields are encoded and
counted once per record in `fields`; each join is a separate view and should not
be added to it as if representing distinct examples. State counts include
`no_strings` rows in `neither`. Error rows contribute only to `records_seen` and
`errors`, with no partially scanned field counts. Schema counts can overlap.

`summary.json` is initially `running`; final summary/share documents use a temporary
file and atomic rename. Process termination can leave partial row output and a
running summary. Abrupt power failure durability and transactions across multiple
output files are not guaranteed. Check both the process exit code and status.

Full reproducibility requires the original input, recorded tokenizer snapshot or
identical local files, settings, traversal order, dependency versions, tool version
and source digest. The input SHA-256 is of the complete on-disk file (compressed
bytes for gzip), even when only a prefix was scanned. Before/after hashes detect
persistent changes; they are not a lock against simultaneous edits. Keep inputs
stable during a run. `share.json` omits file names, field paths and token spellings but retains
input/backend/catalogue fingerprints, the Hugging Face tokenizer repository and
revision, run times, settings, versions and scope.

JSONL `--max-record-bytes` is the inclusive byte length of each decompressed
physical line, including its LF or both CRLF bytes. An unterminated final line
has no terminator bytes to count. UTF-8 bytes, JSON quotes, whitespace and escape
syntax all contribute; decoded character count is a separate limit. A line one
byte over the limit is `E_RECORD_BYTES`. This option does not apply to JSON
documents or Parquet. Gzip uses the same limit after decompression.

## File serialization

The four CLI artifacts use UTF-8 without BOM and LF line endings on every OS.
`records.jsonl` and `summary.txt` can be compared byte-for-byte for completed scans of equivalent
decoded records with the same tokenizer/settings and within the same limits. For identical input bytes, JSON comparisons exclude only
execution timestamps, input path, Python version and source fingerprint. Those
fields remain in the real artifacts. LF/CRLF input variants still have different
raw input hashes/sizes.
