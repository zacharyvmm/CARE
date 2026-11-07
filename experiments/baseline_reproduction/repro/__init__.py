"""Helper modules for baseline_reproduction.ipynb (the notebook is the entry point)."""
import os

import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # experiments/baseline_reproduction
REPO = os.path.dirname(os.path.dirname(HERE))


def load_config(path=None):
    with open(path or os.path.join(HERE, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)
