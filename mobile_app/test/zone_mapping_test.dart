import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:pharmacy_worker_monitor_v2/widgets/zone_painter.dart';

void main() {
  test('zone editor reverses BoxFit contain letterboxing', () {
    final center = screenToNormalized(
      const Offset(500, 500),
      const Size(1000, 1000),
      const Size(1920, 1080),
    );
    expect(center?.dx, closeTo(0.5, 0.000001));
    expect(center?.dy, closeTo(0.5, 0.000001));
    expect(
      screenToNormalized(
        const Offset(500, 100),
        const Size(1000, 1000),
        const Size(1920, 1080),
      ),
      isNull,
    );
  });
}
