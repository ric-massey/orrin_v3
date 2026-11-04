# What makes my memory use (RSS) climb?

**Hypothesis** (from 48 prior runs): My memory use (RSS) rises after read_rss runs.
Training: mean +49.6729 vs baseline +0.0493.

**Test** on telemetry recorded after the hypothesis: failed out of sample: mean -40.25 after read_rss (n=10) vs baseline +0.5867.
