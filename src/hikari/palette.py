"""Shared Solana-inspired terminal palette with NO_COLOR support."""
from __future__ import annotations
import os
NO_COLOR = "NO_COLOR" in os.environ
RESET = "" if NO_COLOR else "\033[0m"
OCEAN_BLUE = "" if NO_COLOR else "\033[38;5;45m"
SURGE_GREEN = "" if NO_COLOR else "\033[38;5;49m"
PURPLE_DINO = "" if NO_COLOR else "\033[38;5;165m"
GRAY_BORDER = "" if NO_COLOR else "\033[38;5;238m"
GRAY_VALUE = "" if NO_COLOR else "\033[38;5;245m"
VARIABLE = SURGE_GREEN
