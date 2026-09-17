# Model registry

Status: metadata inspection and missing-model degradation are **implemented**; trained weights are not included.

Each local model record includes filename/path, SHA-256, discovered classes, input size, threshold, dataset/version, training date, Ultralytics/PyTorch versions, device, license and limitations. Models are never downloaded automatically. Missing weights keep unrelated services running and mark perception unavailable.

