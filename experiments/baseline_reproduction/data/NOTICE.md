# Data notice

`population.parquet` contains commands derived from third-party corpora, redistributed under their licenses:

| Source | License | Attribution |
|---|---|---|
| Atomic Red Team (`atomics/*/*.yaml`, commit a0e3f9b) | MIT | Copyright (c) 2018 Red Canary, Inc. |
| RedCode-Exec bash (`dataset/RedCode-Exec/bash2text_dataset_json`, commit 664e479) | CC BY 4.0 | Copyright (c) 2024 RedCode Authors — Guo et al., *RedCode: Risky Code Execution and Generation Benchmark for Code Agents*, NeurIPS 2024 D&B. Changes: shebang and comment lines stripped. |
| NL2Bash (`data/bash/all.cm`, `all.nl`, commit d6b9f5b) | MIT (data/bash/LICENSE) | Copyright (c) 2020 NL2Bash dataset — Lin et al., LREC 2018. |
| `manual/real_world_commands.txt` | MIT (this repository) | written for this reproduction (see DECISIONS.md D4) |

Many of these commands are attack techniques. They are stored as text and are never executed by this
reproduction: every guard only reads the command string.
