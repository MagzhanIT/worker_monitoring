class ReportModel {
  const ReportModel({
    required this.available,
    this.updatedAt,
    this.files = const {},
  });
  final bool available;
  final DateTime? updatedAt;
  final Map<String, String> files;

  factory ReportModel.fromJson(Map<String, dynamic> json) => ReportModel(
    available: json['available'] as bool? ?? json['success'] as bool? ?? false,
    updatedAt: json['updated_at'] is num
        ? DateTime.fromMillisecondsSinceEpoch(
            ((json['updated_at'] as num) * 1000).round(),
          )
        : DateTime.tryParse(json['updated_at'] as String? ?? ''),
    files: (json['files'] as Map<String, dynamic>? ?? const {}).map(
      (key, value) => MapEntry(key, value.toString()),
    ),
  );
}
