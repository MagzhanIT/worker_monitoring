import 'dart:ui';

class ZoneModel {
  const ZoneModel({
    this.id,
    required this.displayName,
    required this.zoneType,
    required this.normalizedPoints,
    this.enabled = true,
  });

  final int? id;
  final String displayName;
  final String zoneType;
  final List<Offset> normalizedPoints;
  final bool enabled;

  Map<String, dynamic> toJson() => {
    'display_name': displayName,
    'zone_type': zoneType,
    'normalized_points': normalizedPoints
        .map((point) => [point.dx, point.dy])
        .toList(),
    'enabled': enabled,
  };

  factory ZoneModel.fromJson(Map<String, dynamic> json) => ZoneModel(
    id: (json['id'] as num?)?.toInt(),
    displayName: json['display_name'] as String? ?? 'Zone',
    zoneType: json['zone_type'] as String? ?? 'employee_area',
    normalizedPoints: (json['normalized_points'] as List<dynamic>? ?? const [])
        .whereType<List<dynamic>>()
        .where((point) => point.length >= 2)
        .map(
          (point) => Offset(
            (point[0] as num).toDouble(),
            (point[1] as num).toDouble(),
          ),
        )
        .toList(),
    enabled: json['enabled'] as bool? ?? true,
  );
}
