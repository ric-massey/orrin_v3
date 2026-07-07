# Action Selection & Bandit Learning

Bandit selector
- Multi-armed bandit where each arm is a cognitive function. UCB1-like or Thompson-sampling variants are supported.

Workspace prior
- Workspace winners receive additive priors to favor coherent behavior.

Cost prediction & EVC
- Expected Value of Control computes cost vs. reward trade-offs to decide whether deeper planning is warranted.

Learning
- Immediate reward updates and delayed evaluation by evaluator daemons; credit assignment supports both short- and long-term reward signals.
