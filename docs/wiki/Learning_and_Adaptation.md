# Learning & Adaptation

Learning surfaces
- Bandit updates, depth bandit, evaluator daemons, and optional self-shaping fine-tuning.

Evaluator daemon
- Performs delayed credit assignment based on outcomes observed after decisions.

Self-shaping
- Optional fine-tuning pipeline (OpenAI or other providers) that submits curated traces for model updates; guarded with filters to avoid low-quality drift.

Metrics
- Success rate per function, reward trajectory, goal closure rates.
