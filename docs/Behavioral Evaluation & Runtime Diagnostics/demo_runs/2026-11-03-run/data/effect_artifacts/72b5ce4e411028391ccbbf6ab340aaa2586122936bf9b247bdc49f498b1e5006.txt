# What makes my memory use (RSS) climb?

**Hypothesis** (from 94 prior runs): My memory use (RSS) rises after wikipedia_search runs.
Training: mean +11.9777 vs baseline +0.241.

**Test** on telemetry recorded after the hypothesis: failed out of sample: mean -55.08 after wikipedia_search (n=10) vs baseline +0.3348.
