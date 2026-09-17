import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../models/zone_model.dart';

Rect containRect(Size canvasSize, Size imageSize) {
  final scale = (canvasSize.width / imageSize.width).clamp(
    0.0,
    canvasSize.height / imageSize.height,
  );
  final shown = Size(imageSize.width * scale, imageSize.height * scale);
  return Rect.fromLTWH(
    (canvasSize.width - shown.width) / 2,
    (canvasSize.height - shown.height) / 2,
    shown.width,
    shown.height,
  );
}

Offset? screenToNormalized(
  Offset screenPoint,
  Size canvasSize,
  Size imageSize,
) {
  final rect = containRect(canvasSize, imageSize);
  if (!rect.contains(screenPoint)) return null;
  return Offset(
    ((screenPoint.dx - rect.left) / rect.width).clamp(0, 1),
    ((screenPoint.dy - rect.top) / rect.height).clamp(0, 1),
  );
}

class ZonePainter extends CustomPainter {
  const ZonePainter({
    required this.points,
    required this.imageSize,
    required this.closed,
    this.savedZones = const [],
    this.label,
    this.image,
  });

  final List<Offset> points;
  final Size imageSize;
  final bool closed;
  final List<ZoneModel> savedZones;
  final String? label;
  final ui.Image? image;

  @override
  void paint(Canvas canvas, Size size) {
    final imageRect = containRect(size, imageSize);
    canvas.drawRect(
      Offset.zero & size,
      Paint()..color = const Color(0xFF12231F),
    );
    if (image != null) {
      canvas.drawImageRect(
        image!,
        Rect.fromLTWH(0, 0, image!.width.toDouble(), image!.height.toDouble()),
        imageRect,
        Paint(),
      );
    }
    Offset pixel(Offset point) => Offset(
      imageRect.left + point.dx * imageRect.width,
      imageRect.top + point.dy * imageRect.height,
    );
    for (final zone in savedZones.where(
      (zone) => zone.enabled && zone.normalizedPoints.length >= 3,
    )) {
      final color = _zoneColor(zone.zoneType);
      final savedPath = Path()
        ..moveTo(
          pixel(zone.normalizedPoints.first).dx,
          pixel(zone.normalizedPoints.first).dy,
        );
      for (final point in zone.normalizedPoints.skip(1)) {
        final value = pixel(point);
        savedPath.lineTo(value.dx, value.dy);
      }
      savedPath.close();
      canvas.drawPath(
        savedPath,
        Paint()..color = color.withValues(alpha: 0.16),
      );
      canvas.drawPath(
        savedPath,
        Paint()
          ..color = color
          ..strokeWidth = 2
          ..style = PaintingStyle.stroke,
      );
      _paintLabel(
        canvas,
        zone.normalizedPoints.map(pixel).reduce((a, b) => a + b) /
            zone.normalizedPoints.length.toDouble(),
        '${zone.displayName} (${zone.zoneType.replaceAll('_', ' ')})',
        color,
      );
    }
    if (points.isEmpty) return;
    final path = Path()..moveTo(pixel(points.first).dx, pixel(points.first).dy);
    for (final point in points.skip(1)) {
      final value = pixel(point);
      path.lineTo(value.dx, value.dy);
    }
    if (closed && points.length >= 3) path.close();
    if (closed) canvas.drawPath(path, Paint()..color = const Color(0x5538D39F));
    canvas.drawPath(
      path,
      Paint()
        ..color = const Color(0xFF64E8B8)
        ..strokeWidth = 3
        ..style = PaintingStyle.stroke,
    );
    for (final point in points) {
      canvas.drawCircle(pixel(point), 7, Paint()..color = Colors.white);
      canvas.drawCircle(
        pixel(point),
        5,
        Paint()..color = const Color(0xFF0A5C4A),
      );
    }
    if (label != null && points.isNotEmpty) {
      final center =
          points.map(pixel).reduce((a, b) => a + b) / points.length.toDouble();
      _paintLabel(canvas, center, label!, const Color(0xFF0A5C4A));
    }
  }

  void _paintLabel(Canvas canvas, Offset center, String value, Color color) {
    final text = TextPainter(
      text: TextSpan(
        text: value,
        style: TextStyle(
          color: Colors.white,
          fontSize: 11,
          fontWeight: FontWeight.w700,
          backgroundColor: color.withValues(alpha: 0.88),
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: 220);
    text.paint(canvas, center - Offset(text.width / 2, text.height / 2));
  }

  Color _zoneColor(String zoneType) => switch (zoneType) {
    'employee_area' => const Color(0xFF00A67A),
    'customer_area' => const Color(0xFF2878D0),
    'cashier' || 'service_position' => const Color(0xFFE17816),
    'register_interaction' || 'computer' || 'pos' => const Color(0xFFD62D78),
    'shelf_interaction' ||
    'medicine_shelf' ||
    'storage' => const Color(0xFF7357C8),
    'waiting' || 'entrance' => const Color(0xFFC39700),
    'break_area' || 'authorized_out_of_zone' => const Color(0xFF158A9A),
    'ignore_area' => const Color(0xFFC23B3B),
    _ => const Color(0xFF52635E),
  };

  @override
  bool shouldRepaint(covariant ZonePainter oldDelegate) =>
      oldDelegate.points != points ||
      oldDelegate.closed != closed ||
      oldDelegate.savedZones != savedZones ||
      oldDelegate.label != label ||
      oldDelegate.image != image;
}
