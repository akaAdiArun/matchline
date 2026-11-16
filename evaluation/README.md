# Invoice extraction benchmark

On this small synthetic benchmark, Qwen3-VL-2B read more fields correctly and produced more correct matching decisions than Tesseract plus the existing parser. Both approaches recorded zero incorrect matches on seven cases that should not match. These results describe 12 fictional invoices and three layouts.

| Metric | Tesseract + parser | Qwen3-VL-2B |
| --- | ---: | ---: |
| Correct fields | 25/48 | 46/48 |
| Correct fields among readable fields | 23/46 | 44/46 |
| Exact matching decisions | 7/12 | 11/12 |
| Incorrect matches among cases that should not match | 0/7 | 0/7 |
| Sent to review | 7/12 (58.3%) | 3/12 (25.0%) |
| Median scan-to-decision latency | 136.5 ms | 616.8 ms |

The biggest difference was layout. Tesseract plus the parser got all 24 fields on the six familiar label layouts, counting the correct abstention on the covered quantity. On the six unfamiliar table and card layouts, the parser required labels it could use, such as `Quantity:` and `Unit price:`. It returned only one correct field there, the abstention on a covered price. Qwen recognized both unfamiliar layouts and resolved four cases that the baseline sent to review.

- **Tesseract pipeline failure.** Tesseract's raw word output for the [clean table invoice](images/07.png) correctly read `RB-5372`, `HINGE-564`, 53, and `$6.29`. The parser reported four missing labels and sent a valid match to review. Qwen extracted all four fields and returned `matched`. This example isolates the layout parser as the source of the failure.
- **Vision failure.** On the [skewed card invoice](images/11.png), Qwen returned `"$19.38"` for the correct price. The response schema allowed a string, and the validator required that string to contain only the decimal amount. Matchline left the price unresolved and sent a valid match to review. The same formatting failure occurred on [the covered-quantity invoice](images/06.png), which already required review. Both runs and their outcomes are in [the raw results](results.json).

## Evaluation protocol

The [answer key](cases.json) contains 12 invoices with field truth verified against the PNGs. It also contains fictional orders and receipts and independent decision labels for five matches, five discrepancies, and two reviews. Cases cover clean scans, unfamiliar layouts, reduced resolution and contrast, skew and blur, short deliveries, a billed quantity different from the order, incorrect prices, and covered fields. Covered fields are labeled `null`. The scan examples in `examples/scans` are the separate development set. Both extractors warm up on its clean invoice before the held-out run.

Each extractor receives the same PNG bytes. The vision server also receives a fixed transcription prompt and a JSON schema. Neither extractor receives the order, receipt, or answer key. The runner applies the same matching function and requires an invoice number for both scan paths. The model adapter leaves invalid, missing, and unresolved fields empty, and retains the verbatim response for inspection. Schema and value checks cannot establish whether plausible text is visible in the scan, so the benchmark also checks whether the extractor abstained on both covered fields.

Field accuracy counts exact values on invoice number, item ID, quantity, and unit price, with numerically equal decimal prices treated as equal. It includes a correct abstention for an unreadable field. Both approaches abstained correctly on 2/2 covered fields. An incorrect match is a `matched` decision on a case labeled `mismatch` or `needs_review`. Review rate uses all 12 cases. Latency is elapsed time from the extraction call through validation and matching, including OCR process startup or local HTTP overhead. Server startup, the development warm-up, and loading the manifest are outside the clock.

## Reproduce on Windows

The recorded run used Python 3.12, Tesseract 5.5.0.20241111 with English data, and llama.cpp b12327 on a GeForce RTX 4070 Laptop GPU via Vulkan. Qwen used Q4_K_M language weights and a Q8_0 vision projector. The request used temperature zero, seed 42, a 192-token response cap, and prompt caching disabled. Latency depends on the machine.

Set up Tesseract as described in the [project README](../README.md). Download the Windows Vulkan archive from the [llama.cpp b12327 release](https://github.com/ggml-org/llama.cpp/releases/tag/b12327) and the two files from the pinned [Qwen model revision](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/tree/52d6c8ffea26cc873ac5ad116f8631268d7eb503). These PowerShell commands put all three downloads outside the repository.

```powershell
$runtime = Join-Path $env:TEMP 'matchline-benchmark-runtime'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$model = 'https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/52d6c8ffea26cc873ac5ad116f8631268d7eb503'
curl.exe --fail --location --output "$runtime\llama.zip" 'https://github.com/ggml-org/llama.cpp/releases/download/b12327/llama-b12327-bin-win-vulkan-x64.zip'
curl.exe --fail --location --output "$runtime\model.gguf" "$model/Qwen3VL-2B-Instruct-Q4_K_M.gguf"
curl.exe --fail --location --output "$runtime\mmproj.gguf" "$model/mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"
Expand-Archive -LiteralPath "$runtime\llama.zip" -DestinationPath "$runtime\llama"
& "$runtime\llama\llama-server.exe" --list-devices
```

Use the NVIDIA device name reported by `--list-devices` in place of `Vulkan1` if it differs. Start the server in that PowerShell window.

```powershell
& "$runtime\llama\llama-server.exe" --model "$runtime\model.gguf" --mmproj "$runtime\mmproj.gguf" --alias matchline-qwen3-vl-2b --host 127.0.0.1 --port 18973 --no-ui --ctx-size 4096 --parallel 1 --device Vulkan1 --n-gpu-layers 99
```

From the repository root in a second PowerShell window with Tesseract configured, run the benchmark.

```powershell
python -m benchmark --vision --output "$env:TEMP\matchline-benchmark.json"
```

For the OCR-only fallback, omit `--vision`. If the local model server fails during a comparison, the runner reports the error, writes the completed Tesseract results, and exits with an error. Stop the local server with Ctrl+C when finished.
