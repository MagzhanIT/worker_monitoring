# Privacy

Status: restrictions are **implemented in design and code paths**; a deployment privacy review is still required.

Workers and customers begin with camera-local temporary IDs. Face detection is permitted only for cropping a likely worker reference image. There is no face recognition, face embedding, face comparison, automatic employee naming, or face gallery. Customer face snapshots and customer appearance matching are prohibited.

Confirmed workers may receive a global anonymous ID across cameras for the same calendar day. This uses encrypted, short-lived clothing/body descriptors, never face data. A strict match threshold, second-best margin, and active-camera conflict check reduce unsafe merges. Similar uniforms, lighting, occlusion, or clothing changes can still cause wrong or duplicate IDs, so match method, confidence, and review status remain visible. Managers can correct session assignments through authenticated APIs.

Snapshots and clips stay local unless an authorized manager exports them; Google Sheets receives aggregates only. Appearance signatures expire independently of session/report history.
