# Orrin learning investigation

**Main deliverable:** [Research report and final assessment](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/REPORT.md>).

Supporting reports:

- [Actual architecture: inputs, outputs, persistent state, consumers and authority](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/ARCHITECTURE.md>)
- [Historical chronology, independent denominators and current-fix status](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/CHRONOLOGY.md>)
- [Controlled experimental verification plan](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/EXPERIMENTS.md>)

Reproducible evidence:

- [Archive measurements](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/archive_measurements.json>), produced by [measure_archives.py](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/measure_archives.py>)
- [Isolated source probes and independent telemetry recomputation](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/probe_results.json>), produced by [probe_evidence.py](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/probe_evidence.py>)
- [Structural source inventory](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/source_inventory.json>)
- [Archive input hashes](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/input_hashes.json>) and [probe input hashes](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/probe_input_hashes.json>)
- [Linked-source provenance](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/report_sources.json>) and [final validation](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/validation.json>)

Source baseline: `1c51dfb`. Research performed 17 October 2026. Latest complete archived life: Run 13, 6–8 October; later Phase B code changes have no subsequent complete-life capture here.

Only files in this analysis directory were created or edited. No Orrin modules were imported, runtime or daemons launched, configuration changed, neural training run, or original artifacts edited. No full test suite was run. The small source probes use extracted definitions and in-memory dependencies; their results are local semantic checks, not a live performance test.

To reproduce the derived evidence, invoke each analysis script using Python 3. Both locate the repository relative to this output directory and write only adjacent derived outputs. They use the standard library. The archive script streams compressed artifacts; the probe script additionally compiles selected function definitions without importing the application.

The report differentiates confirmed code behavior, observed archived outcomes, earlier report claims, hypotheses and unknowns. It deliberately does not prescribe or implement fixes.
