"""Lightweight internal configuration types."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PollConfig:
    initial_interval: float = 2.0
    max_interval: float = 5.0
    timeout: float = 30 * 60.0
