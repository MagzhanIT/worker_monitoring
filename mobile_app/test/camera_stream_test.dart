import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pharmacy_worker_monitor_v2/services/api_service.dart';
import 'package:pharmacy_worker_monitor_v2/widgets/camera_stream.dart';

void main() {
  testWidgets('renders an authenticated snapshot as the live camera frame', (
    tester,
  ) async {
    final png = base64Decode(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: SizedBox(
          width: 320,
          height: 180,
          child: CameraStream(
            api: ApiService(baseUrl: 'http://localhost:8000'),
            cameraId: 1,
            frameLoader: () async => png,
            refreshInterval: const Duration(hours: 1),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(Image), findsOneWidget);
    expect(find.text('Waiting for live frame…'), findsNothing);

    await tester.pumpWidget(const SizedBox.shrink());
  });
}
