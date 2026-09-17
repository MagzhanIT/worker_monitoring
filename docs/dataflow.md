# Data flow

Status: capture-to-event flow is **implemented**; site-specific perception quality is **unmeasured**.

```mermaid
sequenceDiagram
  participant Camera
  participant Capture
  participant Vision
  participant State
  participant Database
  participant Manager
  Camera->>Capture: advancing decoded frames
  Capture->>Vision: newest frame only
  Vision->>State: track-keyed observations
  State->>Database: completed interval event
  Database-->>Manager: API/WebSocket/report
  Manager->>Database: review while original result remains
```

There is one bounded latest-frame slot per camera, so slow inference drops stale frames rather than accumulating delay.

