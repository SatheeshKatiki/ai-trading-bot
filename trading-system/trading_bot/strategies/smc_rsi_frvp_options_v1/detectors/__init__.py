"""smc1 detectors (spec §3), incremental and causal.

Every tracker consumes CLOSED bars one at a time through ``update`` and never
reads a bar it has not been given, so its output at bar ``i`` depends only on
bars ``0..i``. Running a tracker over a full history and over any prefix of
it yields identical output on the shared bars; the tests assert this
(owner decision D1: step-by-step detectors, not frame-level recomputation).
"""

from __future__ import annotations
