# special-token-scan

[한국어](README.ko.md)

Check a training-data file for text that a tokenizer turns into **special or added token IDs** — before you fine-tune.

Some tokenizers encode registered strings such as `<|im_start|>` as real special token IDs even when they appear in ordinary text. special-token-scan tokenizes every string value in your file with the tokenizer you plan to use and reports where that happens: record number (from 0), field path, and character position.

A finding means "this text becomes this token ID with this tokenizer".

## Install

Python 3.12 or later.

```bash
git clone https://github.com/Akritai-Inc/special-token-scan
cd special-token-scan
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install .                    # with Parquet support: pip install ".[parquet]"
```

special-token-scan downloads only tokenizer files. No model weights or GPU are needed.

## Quick start

```bash
special-token-scan examples/boundary.jsonl \
  --tokenizer Qwen/Qwen2.5-7B-Instruct \
  --revision a09a35458c702b33eeacc393d103063234e8bc28 \
  --out out/example
```

```text
complete: 3 records with strings; 1 without strings; 0 record errors.
fields: literal records=1, encoded records=1, special IDs=1, non-special added IDs=1
concat: literal records=2, encoded records=2, special IDs=2, non-special added IDs=1
space: literal records=1, encoded records=1, special IDs=1, non-special added IDs=1
```

The example file has four records. Two of them show the two cases special-token-scan looks for:

- `{"messages":[{"role":"user","content":"Literal <|im_start|> and <tool_call>."}]}` — the text `<|im_start|>` inside one field becomes special token ID 151644, and `<tool_call>` becomes a non-special added token.
- `{"prompt":"<|im_","response":"start|>"}` — each field is clean on its own, but joining the two fields produces `<|im_start|>`. This shows up only in the `concat` view and is marked `crosses_fields: true`.

## Scan your own data

```bash
special-token-scan train.jsonl --tokenizer <model repo> --revision <commit> --out results
```

- **Input**: `.jsonl`, `.ndjson`, `.json` (each optionally `.gz`), or `.parquet` (needs the `parquet` extra). Every string value is checked, including roles, metadata, and unknown fields.
- **Tokenizer**: a Hugging Face model repository with `--revision` set to a full 40-character commit, so results stay reproducible. Find the commit on the model page under "Files and versions", or run:

  ```bash
  python -c "from huggingface_hub import HfApi; print(HfApi().model_info('Qwen/Qwen2.5-7B-Instruct').sha)"
  ```

  A local tokenizer folder also works: `--tokenizer ./my-tokenizer` (no revision needed). Add `--offline` to reuse a repository that is already downloaded.
- special-token-scan never uses your Hugging Face token. For a gated model, download its tokenizer files with your own account and pass the folder.
- **Not supported**: tokenizers whose `tokenizer_config.json` `auto_map` points to repository Python code (`E_TOKENIZER_REMOTE_CODE`) and slow (non-fast) tokenizers (`E_FAST_REQUIRED`).
- `--out` must be a new folder.

## Read the results

| File | Contents |
|---|---|
| `summary.txt` | The counts printed above |
| `records.jsonl` | One line per record: field paths, positions, and token IDs. The string for each ID is in `summary.json` under `tokenizer.catalogue`. |
| `summary.json` | Full run details: input file path and hash, tokenizer files and settings, library versions, limits, status |
| `share.json` | Counts and fingerprints (input file hash and size, tokenizer repository, revision and hashes), run times, settings, library versions. Meant for sharing. |

Each record is checked three ways:

- `fields` — every string value tokenized on its own
- `concat` — all string values of the record joined with nothing in between
- `space` — joined with one space in between

`literal` counts records where a registered string appears as text. `encoded` counts records where the tokenizer actually produced a special or added token ID. The two can differ, because tokenizers normalize text and some tokens absorb surrounding spaces. `special IDs` and `non-special added IDs` count how many times those token IDs appear.

special-token-scan does not send your data anywhere. `records.jsonl` contains field paths, which can reveal key names in your data; share `share.json` instead. `share.json` still includes the input file's hash and size and the tokenizer repository name.

## Use in a pipeline

| Exit code | Meaning |
|---|---|
| 0 | Scan completed |
| 1 | Scan completed and `--fail-on` matched |
| 2 | Error in the input, a record, the tokenizer, or the output (the error code is printed) |

`--fail-on encoded` returns 1 when any record produced a special or added token ID; `--fail-on literal` returns 1 when any registered string appears as text. Findings do not change the exit code unless you ask for it.

Other options:

| Option | Effect |
|---|---|
| `--limit N` | Check only the first N records |
| `--aggregate-only` | Skip `records.jsonl` |
| `--joins concat` / `--joins space` | Run only one of the two join views |
| `--split-special-tokens` | Tokenize with special-token splitting turned on, to compare |
| `--format json\|jsonl\|parquet` | Override the format detected from the file name |
| `--max-…` | Change size limits (defaults: 16 MiB per JSONL line, 64 MiB per JSON file, nesting depth 64) |

Error codes are listed in [docs/ERRORS.md](docs/ERRORS.md), and the output fields in [docs/OUTPUT.md](docs/OUTPUT.md).

## Tested tokenizers

Checked with transformers 5.19.0 using the tokenizers of the 22 models below, by inserting every registered string into synthetic records, inside a field and across a field boundary:

- Qwen: `Qwen/Qwen2.5-7B-Instruct`, `Qwen/Qwen3.6-27B`, `Qwen/Qwen3.8-27B`, `Qwen/Qwen3.8-Flash-Next`, `Qwen/Qwen3.8-2.4T-A95B`
- Llama: `meta-llama/Llama-3.1-8B-Instruct`, `meta-llama/Llama-3.2-1B-Instruct`, `meta-llama/Llama-3.3-70B-Instruct`, `meta-llama/Llama-4-Scout-17B-16E-Instruct`, `meta-llama/Llama-4-Maverick-17B-128E-Instruct`
- Gemma: `google/gemma-4-31B-it`, `google/gemma-4-E4B-it`
- Mistral: `mistralai/Mistral-Small-4-119B-2603`, `mistralai/Mistral-Medium-3.5-128B`
- DeepSeek: `deepseek-ai/DeepSeek-V4.1-Flash`, `deepseek-ai/DeepSeek-V4-Pro-0813`
- Others: `zai-org/GLM-5.3`, `XiaomiMiMo/MiMo-V2.6-Pro-RL`, `openai/gpt-oss-120b`, `LGAI-EXAONE/EXAONE-4.5-33B`, `LGAI-EXAONE/K-EXAONE-2.0-750B-A37B`, `microsoft/phi-4`

`moonshotai/Kimi-K3` is not supported.

## License

Apache-2.0. Copyright 2026 Akritai Inc.
