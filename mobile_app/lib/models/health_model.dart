class HealthModel {
  const HealthModel({
    required this.status,
    required this.cameraConnected,
    required this.receivingFrames,
    required this.processingFps,
    this.captureFps = 0,
    this.lastFrameAgeSeconds,
    this.lastError,
  });

  final String status;
  final bool cameraConnected;
  final bool receivingFrames;
  final double processingFps;
  final double captureFps;
  final double? lastFrameAgeSeconds;
  final String? lastError;

  bool get available => !{
    'UNAVAILABLE',
    'FROZEN',
    'RECONNECTING',
    'END_OF_FILE',
  }.contains(status);

  factory HealthModel.fromJson(Map<String, dynamic> json) => HealthModel(
    status: json['status'] as String? ?? 'UNAVAILABLE',
    cameraConnected: json['camera_connected'] as bool? ?? false,
    receivingFrames: json['receiving_frames'] as bool? ?? false,
    processingFps: (json['processing_fps'] as num?)?.toDouble() ?? 0,
    captureFps: (json['capture_fps'] as num?)?.toDouble() ?? 0,
    lastFrameAgeSeconds: (json['last_frame_age_seconds'] as num?)?.toDouble(),
    lastError: json['last_processing_error'] as String?,
  );
}
