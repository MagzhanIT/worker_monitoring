class LivePersonModel {
  const LivePersonModel({
    required this.trackId,
    required this.displayName,
    required this.role,
    required this.activity,
    required this.evidenceStatus,
    required this.confidence,
    required this.reasons,
    this.workerSessionId,
    this.zone,
    this.motion = 'UNKNOWN',
    this.stationarySeconds,
    this.globalWorkerId,
    this.identityMatchStatus,
    this.identityConfidence,
    this.customerServiceSessionId,
    this.customerServicePhase,
    this.unknownReason,
    this.candidateActivity,
    this.candidateDurationSeconds = 0,
    this.idleCandidateSeconds = 0,
    this.idleConfirmationSeconds = 0,
    this.confirmedIdleSeconds = 0,
    this.trackAgeSeconds = 0,
    this.trackStable = false,
    this.evidenceQuality,
    this.bodyMotion = 0,
    this.bboxMotion = 0,
    this.wristMotion = 0,
    this.elbowMotion = 0,
    this.poseStatus,
    this.poseConfidence = 0,
    this.idleBlockingReasons = const [],
  });

  final int trackId;
  final String? workerSessionId;
  final String displayName;
  final String role;
  final String activity;
  final String evidenceStatus;
  final double confidence;
  final String? zone;
  final String motion;
  final double? stationarySeconds;
  final List<String> reasons;
  final String? globalWorkerId;
  final String? identityMatchStatus;
  final double? identityConfidence;
  final String? customerServiceSessionId;
  final String? customerServicePhase;
  final String? unknownReason;
  final String? candidateActivity;
  final double candidateDurationSeconds;
  final double idleCandidateSeconds;
  final double idleConfirmationSeconds;
  final double confirmedIdleSeconds;
  final double trackAgeSeconds;
  final bool trackStable;
  final String? evidenceQuality;
  final double bodyMotion;
  final double bboxMotion;
  final double wristMotion;
  final double elbowMotion;
  final String? poseStatus;
  final double poseConfidence;
  final List<String> idleBlockingReasons;

  factory LivePersonModel.fromJson(Map<String, dynamic> json) =>
      LivePersonModel(
        trackId: (json['track_id'] as num?)?.toInt() ?? 0,
        workerSessionId: json['worker_session_id'] as String?,
        displayName: json['display_name'] as String? ?? 'Observed person',
        role: json['role'] as String? ?? 'UNKNOWN',
        activity: json['activity'] as String? ?? 'UNKNOWN',
        evidenceStatus:
            json['evidence_status'] as String? ?? 'INSUFFICIENT_EVIDENCE',
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
        zone: json['zone'] as String?,
        motion: json['motion'] as String? ?? 'UNKNOWN',
        stationarySeconds: (json['stationary_seconds'] as num?)?.toDouble(),
        globalWorkerId: json['global_worker_id'] as String?,
        identityMatchStatus: json['identity_match_status'] as String?,
        identityConfidence: (json['identity_confidence'] as num?)?.toDouble(),
        customerServiceSessionId:
            json['customer_service_session_id'] as String?,
        customerServicePhase: json['customer_service_phase'] as String?,
        unknownReason: json['unknown_reason'] as String?,
        candidateActivity: json['candidate_activity'] as String?,
        candidateDurationSeconds:
            (json['candidate_duration_seconds'] as num?)?.toDouble() ?? 0,
        idleCandidateSeconds:
            (json['idle_candidate_seconds'] as num?)?.toDouble() ?? 0,
        idleConfirmationSeconds:
            (json['idle_confirmation_seconds'] as num?)?.toDouble() ?? 0,
        confirmedIdleSeconds:
            (json['confirmed_idle_seconds'] as num?)?.toDouble() ?? 0,
        trackAgeSeconds: (json['track_age_seconds'] as num?)?.toDouble() ?? 0,
        trackStable: json['track_stable'] as bool? ?? false,
        evidenceQuality: json['evidence_quality'] as String?,
        bodyMotion: (json['body_motion'] as num?)?.toDouble() ?? 0,
        bboxMotion: (json['bbox_motion'] as num?)?.toDouble() ?? 0,
        wristMotion: (json['wrist_motion'] as num?)?.toDouble() ?? 0,
        elbowMotion: (json['elbow_motion'] as num?)?.toDouble() ?? 0,
        poseStatus: json['pose_status'] as String?,
        poseConfidence: (json['pose_confidence'] as num?)?.toDouble() ?? 0,
        idleBlockingReasons:
            (json['idle_blocking_reasons'] as List<dynamic>?)
                ?.map((value) => value.toString())
                .toList() ??
            const [],
        reasons:
            (json['reasons'] as List<dynamic>?)
                ?.map((value) => value.toString())
                .toList() ??
            const [],
      );
}
