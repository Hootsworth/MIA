#!/usr/bin/env python3
# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Download the exact public model revisions used by the local detector app."""

from pathlib import Path

from huggingface_hub import hf_hub_download

MODELS = (
    ("jaspai/modernbert-ai-text-detector", "a12cb885313fd3b44a190bb31412bc72d15c4891"),
    ("wasitaigeneratedcom/tropa-mini-ai-text-detector", "10fecd0856ed65ddfe92b88416b0a1e1350d8fb8"),
)


def main():
    for repo_id, revision in MODELS:
        print(f"Downloading {repo_id}@{revision}", flush=True)
        weight_path = hf_hub_download(repo_id=repo_id, filename="model.safetensors", revision=revision,
                                      cache_dir="storage/models/hub")
        if not Path(weight_path).is_file() or Path(weight_path).stat().st_size == 0:
            raise RuntimeError(f"Model weights are incomplete: {weight_path}")
        print(f"Verified weights: {weight_path} ({Path(weight_path).stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
