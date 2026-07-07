# Host Coupling

Overview
- The host machine is both context and substrate. Orrin learns the host's normal profiles and adapts behavior to resource constraints.

Key metrics
- Disk free, memory free, CPU load, swap usage, battery level.

How host coupling works
- Infancy learning phase establishes baselines.
- Deviations produce control-signal adjustments and may throttle expensive operations.

Code pointers
- supervisor/host_resources.py
