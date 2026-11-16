# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Run the package tests against the checked-out source tree."""

import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))
