# Debugging Memory Issues

Symptoms
- Missing retrievals, consolidation stalls, embedding failures.

Steps
1. Inspect memory daemon logs.
2. Check WAL size and snapshot cadence.
3. Run embedding provider locally with sample inputs.
4. Rebuild index and restart daemon if needed.
