# special-token-scan

[English](README.md)

미세조정 전에 학습 데이터 파일에서 토크나이저가 **special token ID나 added token ID로 변환하는 텍스트**가 있는지 확인합니다.

일부 토크나이저는 `<|im_start|>` 같은 등록 문자열이 일반 텍스트에 포함되어 있어도 실제 special token ID로 인코딩합니다. special-token-scan은 사용할 토크나이저로 파일의 모든 문자열 값을 토큰화하고, 해당 현상이 발생하는 위치를 레코드 번호(0부터), 필드 경로, 글자 위치로 알려줍니다.

검출 결과는 "이 텍스트가 해당 토크나이저에서 이 토큰 ID로 변환된다"는 의미입니다.

## 설치

Python 3.12 이상이 필요합니다.

```bash
git clone https://github.com/Akritai-Inc/special-token-scan
cd special-token-scan
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install .                    # Parquet도 쓰려면: pip install ".[parquet]"
```

special-token-scan은 토크나이저 파일만 다운로드합니다. 모델 가중치나 GPU는 필요하지 않습니다.

## 빠른 시작

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

예시 파일에는 4개의 레코드가 있습니다. 그중 2개는 special-token-scan이 찾는 두 가지 경우를 보여줍니다.

- `{"messages":[{"role":"user","content":"Literal <|im_start|> and <tool_call>."}]}` — 단일 필드 내의 `<|im_start|>`가 special token ID 151644로 변환되고, `<tool_call>`은 non-special added token이 됩니다.
- `{"prompt":"<|im_","response":"start|>"}` — 개별 필드로 보면 문제가 없지만, 두 필드를 이어 붙이면 `<|im_start|>`가 됩니다. 이 경우는 `concat` 결과에만 나타나며 `crosses_fields: true`로 표시됩니다.

## 내 데이터 검사하기

```bash
special-token-scan train.jsonl --tokenizer <모델 저장소> --revision <커밋> --out results
```

- **입력**: `.jsonl`, `.ndjson`, `.json`(각각 `.gz` 지원), `.parquet`(`parquet` 추가 설치 필요). 각 줄에 JSON 값이 하나씩 있는 `.json` 파일은 JSON Lines로 읽습니다. 역할, 메타데이터, 알 수 없는 필드를 포함한 모든 문자열 값을 검사합니다.
- **토크나이저**: Hugging Face 모델 저장소를 지정하며, 결과를 재현할 수 있도록 `--revision`에 40자리 커밋을 입력합니다. 커밋은 모델 페이지의 "Files and versions"에서 찾거나 아래 명령어로 확인할 수 있습니다.

  ```bash
  python -c "from huggingface_hub import HfApi; print(HfApi().model_info('Qwen/Qwen2.5-7B-Instruct').sha)"
  ```

  로컬 토크나이저 폴더도 사용할 수 있습니다: `--tokenizer ./my-tokenizer`(revision 불필요). 이미 다운로드한 저장소를 재사용하려면 `--offline`을 추가합니다.
- special-token-scan은 Hugging Face 토큰을 사용하지 않습니다. 접근 승인이 필요한 모델은 본인 계정으로 토크나이저 파일을 다운로드한 후 해당 폴더를 지정합니다.
- **지원하지 않는 항목**: `tokenizer_config.json`의 `auto_map`이 저장소의 Python 코드를 지정한 토크나이저(`E_TOKENIZER_REMOTE_CODE`), fast 토크나이저가 아닌 경우(`E_FAST_REQUIRED`).
- `--out`은 새로운 폴더여야 합니다.

## 결과 읽기

| 파일 | 내용 |
|---|---|
| `summary.txt` | 위에서 출력된 집계 |
| `records.jsonl` | 레코드당 한 줄: 필드 경로, 위치, 토큰 ID. 각 ID에 해당하는 문자열은 `summary.json`의 `tokenizer.catalogue`에 있습니다. |
| `summary.json` | 전체 실행 정보: 입력 파일 경로와 해시, 토크나이저 파일 및 설정, 라이브러리 버전, 제한값, 상태 |
| `share.json` | 집계와 지문(입력 파일 해시와 크기, 토크나이저 저장소 이름·revision·해시), 실행 시각, 설정, 라이브러리 버전. 공유용 파일입니다. |

각 레코드에 대해 세 가지 방식으로 검사합니다.

- `fields` — 문자열 값을 개별적으로 토큰화
- `concat` — 레코드 내 모든 문자열 값을 구분자 없이 이어 붙임
- `space` — 공백 하나를 사이에 두고 이어 붙임

`literal`은 등록 문자열이 텍스트로 들어 있는 레코드 수입니다. `encoded`는 토크나이저가 실제로 special 또는 added token ID를 만든 레코드 수입니다. 토크나이저가 텍스트를 정규화하거나 일부 토큰이 주변 공백을 흡수하기 때문에 두 값은 다를 수 있습니다. `special IDs`와 `non-special added IDs`는 해당 토큰 ID가 나온 횟수입니다.

special-token-scan은 외부로 데이터를 전송하지 않습니다. `records.jsonl`에는 필드 경로가 포함되어 데이터의 키 이름이 노출될 수 있으므로, 공유할 때는 `share.json`을 사용하세요. `share.json`에도 입력 파일의 해시와 크기, 사용한 토크나이저 저장소 이름은 포함되어 있습니다.

## 파이프라인에서 쓰기

| 종료 코드 | 의미 |
|---|---|
| 0 | 검사 완료 |
| 1 | 검사 완료, `--fail-on` 조건 충족 |
| 2 | 입력, 레코드, 토크나이저 또는 출력 관련 오류 발생(오류 코드 출력) |

`--fail-on encoded`는 special 또는 added token ID가 나온 레코드가 하나라도 있으면 1을 반환합니다. `--fail-on literal`은 등록 문자열이 텍스트로 하나라도 있으면 1을 반환합니다. 이 옵션을 주지 않으면 검출 결과는 종료 코드를 바꾸지 않습니다.

기타 옵션:

| 옵션 | 효과 |
|---|---|
| `--limit N` | 처음 N개의 레코드만 검사 |
| `--aggregate-only` | `records.jsonl` 파일을 생성하지 않음 |
| `--joins concat` / `--joins space` | 두 가지 이어 붙이기 방식 중 하나만 실행 |
| `--split-special-tokens` | special token 분리 옵션을 활성화하여 토큰화 후 비교 |
| `--format json\|jsonl\|parquet` | 자동으로 판별된 형식 대신 직접 지정 |
| `--max-…` | 크기 제한 변경(기본값: JSONL 한 줄 16 MiB, JSON 파일 64 MiB, 중첩 깊이 64) |

오류 코드는 [docs/ERRORS.md](docs/ERRORS.md), 출력 필드는 [docs/OUTPUT.md](docs/OUTPUT.md)를 참고하세요.

## 확인한 토크나이저

아래 22개 모델의 토크나이저로, transformers 5.19.0에서 등록 문자열 전부를 합성 레코드의 필드 안과 필드 경계에 넣어 확인했습니다.

- Qwen: `Qwen/Qwen2.5-7B-Instruct`, `Qwen/Qwen3.6-27B`, `Qwen/Qwen3.8-27B`, `Qwen/Qwen3.8-Flash-Next`, `Qwen/Qwen3.8-2.4T-A95B`
- Llama: `meta-llama/Llama-3.1-8B-Instruct`, `meta-llama/Llama-3.2-1B-Instruct`, `meta-llama/Llama-3.3-70B-Instruct`, `meta-llama/Llama-4-Scout-17B-16E-Instruct`, `meta-llama/Llama-4-Maverick-17B-128E-Instruct`
- Gemma: `google/gemma-4-31B-it`, `google/gemma-4-E4B-it`
- Mistral: `mistralai/Mistral-Small-4-119B-2603`, `mistralai/Mistral-Medium-3.5-128B`
- DeepSeek: `deepseek-ai/DeepSeek-V4.1-Flash`, `deepseek-ai/DeepSeek-V4-Pro-0813`
- 그 밖: `zai-org/GLM-5.3`, `XiaomiMiMo/MiMo-V2.6-Pro-RL`, `openai/gpt-oss-120b`, `LGAI-EXAONE/EXAONE-4.5-33B`, `LGAI-EXAONE/K-EXAONE-2.0-750B-A37B`, `microsoft/phi-4`

`moonshotai/Kimi-K3`는 지원하지 않습니다.

## 라이선스

Apache-2.0. Copyright 2026 Akritai Inc.
