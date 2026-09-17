# Local model files

Weights are deliberately not committed and are never downloaded at runtime.

- `employee_customer.pt`: Ultralytics detection model whose class names may contain `person` and/or `lab_coat`.
- `labcoat.pt`: optional Codea lab-coat verifier fused into the primary person boxes; it is not tracked as a second person detector.
- `phone_yolo.pt`: physical-phone model (`phone`, `cell phone`, `mobile phone`, `smartphone`) and optionally `phone_call` behavior evidence.
- `yolo11n-pose.pt`: COCO-17 pose model.
- `optional_face_detector.onnx`: optional face **detection/cropping only**. Recognition, embeddings and comparison are forbidden.

Record dataset, license, training date and limitations in a sidecar `<model>.metadata.json` when available.
