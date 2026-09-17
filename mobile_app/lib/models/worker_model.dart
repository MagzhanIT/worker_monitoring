class WorkerModel {
  const WorkerModel({
    required this.id,
    required this.displayName,
    required this.cameraId,
    required this.firstSeen,
    required this.lastSeen,
    this.endedAt,
    this.observedSeconds = 0,
    this.bestFaceMediaId,
    this.bestBodyMediaId,
    this.globalWorkerId,
    this.identityMatchStatus,
    this.identityConfidence,
  });

  final String id;
  final String displayName;
  final int cameraId;
  final DateTime? firstSeen;
  final DateTime? lastSeen;
  final DateTime? endedAt;
  final double observedSeconds;
  final String? bestFaceMediaId;
  final String? bestBodyMediaId;
  final String? globalWorkerId;
  final String? identityMatchStatus;
  final double? identityConfidence;

  bool get active => endedAt == null;

  factory WorkerModel.fromJson(Map<String, dynamic> json) => WorkerModel(
    id: json['id'] as String? ?? 'Unknown session',
    displayName: json['display_name'] as String? ?? 'Anonymous worker',
    cameraId: (json['camera_id'] as num?)?.toInt() ?? 0,
    firstSeen: DateTime.tryParse(json['first_seen'] as String? ?? ''),
    lastSeen: DateTime.tryParse(json['last_seen'] as String? ?? ''),
    endedAt: DateTime.tryParse(json['ended_at'] as String? ?? ''),
    observedSeconds: (json['observed_seconds'] as num?)?.toDouble() ?? 0,
    bestFaceMediaId: json['best_face_media_id'] as String?,
    bestBodyMediaId: json['best_body_media_id'] as String?,
    globalWorkerId: json['global_worker_id'] as String?,
    identityMatchStatus: json['identity_match_status'] as String?,
    identityConfidence: (json['identity_confidence'] as num?)?.toDouble(),
  );
}
