class CameraModel {
  const CameraModel({
    required this.id,
    required this.name,
    required this.source,
    required this.enabled,
    required this.configVersion,
    this.referenceWidth,
    this.referenceHeight,
    this.rotation = 0,
    this.mirror = false,
  });

  final int id;
  final String name;
  final String source;
  final bool enabled;
  final int configVersion;
  final int? referenceWidth;
  final int? referenceHeight;
  final int rotation;
  final bool mirror;

  factory CameraModel.fromJson(Map<String, dynamic> json) => CameraModel(
    id: (json['id'] as num?)?.toInt() ?? 0,
    name: json['name'] as String? ?? 'Unnamed camera',
    source: json['source'] as String? ?? 'Unavailable',
    enabled: json['enabled'] as bool? ?? false,
    configVersion: (json['config_version'] as num?)?.toInt() ?? 1,
    referenceWidth: (json['reference_width'] as num?)?.toInt(),
    referenceHeight: (json['reference_height'] as num?)?.toInt(),
    rotation: (json['rotation'] as num?)?.toInt() ?? 0,
    mirror: json['mirror'] as bool? ?? false,
  );
}
