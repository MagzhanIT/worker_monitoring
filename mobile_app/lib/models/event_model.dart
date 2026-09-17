class EventModel {
  const EventModel({
    required this.id,
    required this.workerSessionId,
    required this.activity,
    required this.presence,
    required this.startTime,
    required this.confidence,
    required this.reviewStatus,
    this.endTime,
    this.durationSeconds,
    this.zone,
    this.reasons = const [],
    this.limitations = const [],
    this.unknownReason,
    this.evidence = const {},
  });

  final String id;
  final String workerSessionId;
  final String activity;
  final String presence;
  final DateTime? startTime;
  final DateTime? endTime;
  final double? durationSeconds;
  final double confidence;
  final String reviewStatus;
  final String? zone;
  final List<String> reasons;
  final List<String> limitations;
  final String? unknownReason;
  final Map<String, dynamic> evidence;

  factory EventModel.fromJson(Map<String, dynamic> json) => EventModel(
    id: json['id'] as String? ?? '',
    workerSessionId: json['worker_session_id'] as String? ?? '',
    activity: json['activity'] as String? ?? 'UNKNOWN',
    presence: json['presence'] as String? ?? 'UNKNOWN',
    startTime: DateTime.tryParse(json['start_time'] as String? ?? ''),
    endTime: DateTime.tryParse(json['end_time'] as String? ?? ''),
    durationSeconds: (json['duration_seconds'] as num?)?.toDouble(),
    confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
    reviewStatus: json['review_status'] as String? ?? 'unreviewed',
    zone: json['zone'] as String?,
    reasons: (json['reasons_json'] as List<dynamic>? ?? const [])
        .map((e) => e.toString())
        .toList(),
    limitations: (json['limitations_json'] as List<dynamic>? ?? const [])
        .map((e) => e.toString())
        .toList(),
    unknownReason: json['unknown_reason'] as String?,
    evidence: (json['evidence_json'] as Map<String, dynamic>?) ?? const {},
  );
}
