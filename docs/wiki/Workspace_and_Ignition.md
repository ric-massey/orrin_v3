# Workspace & Ignition

Global Workspace concept
- Orrin implements a workspace where multiple subsystems propose candidate actions. A single winner is selected (broadcast), preserving a bottleneck for serializing outputs.

Ignition gate
- A configurable gate (deliberation_gate.py) determines whether current proposals merit a deliberative pass or reactively accept a fast action.
- Triggers include high activation, low predicted success, or explicit external requests.

Hysteresis & continuity
- Workspace uses hysteresis to prefer recently-active items, improving continuity of behavior across cycles.

Code pointers
- brain/cognition/global_workspace.py
- brain/think/deliberation_gate.py
