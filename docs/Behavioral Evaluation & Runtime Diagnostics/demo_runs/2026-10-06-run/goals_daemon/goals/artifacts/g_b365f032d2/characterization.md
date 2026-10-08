# What makes my CPU load climb?

**Hypothesis** (from 144 prior runs): My CPU load rises after generate_intrinsic_goals runs.
Training: mean +0.0382 vs baseline +0.0003.

**Test** on telemetry recorded after the hypothesis: inconclusive: generate_intrinsic_goals did not recur >= 10x in 4554 fresh samples.
