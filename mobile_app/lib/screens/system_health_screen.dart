import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/camera_provider.dart';
import '../widgets/health_badge.dart';

class SystemHealthScreen extends StatelessWidget {
  const SystemHealthScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<CameraProvider>();
    return ListView(
      padding: const EdgeInsets.fromLTRB(22, 8, 22, 30),
      children: [
        const Card(
          child: Padding(
            padding: EdgeInsets.all(16),
            child: Row(
              children: [
                Icon(Icons.shield_outlined),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Camera failure is reported as unavailable. It never becomes worker idle or absence.',
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        ...state.cameras.map((camera) {
          final health = state.health[camera.id];
          return Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            camera.name,
                            style: Theme.of(context).textTheme.titleMedium
                                ?.copyWith(fontWeight: FontWeight.w800),
                          ),
                        ),
                        HealthBadge(status: health?.status ?? 'UNAVAILABLE'),
                      ],
                    ),
                    const Divider(height: 24),
                    Wrap(
                      spacing: 28,
                      runSpacing: 12,
                      children: [
                        _value(
                          'Connected',
                          health?.cameraConnected == true ? 'Yes' : 'No',
                        ),
                        _value(
                          'Receiving frames',
                          health?.receivingFrames == true ? 'Yes' : 'No',
                        ),
                        _value(
                          'Processing FPS',
                          health?.processingFps.toStringAsFixed(1) ?? '0.0',
                        ),
                        _value(
                          'Last frame age',
                          health?.lastFrameAgeSeconds == null
                              ? 'Unavailable'
                              : '${health!.lastFrameAgeSeconds!.toStringAsFixed(1)} s',
                        ),
                      ],
                    ),
                    if (health?.lastError != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text(
                          'Last processing error: ${health!.lastError}',
                        ),
                      ),
                  ],
                ),
              ),
            ),
          );
        }),
        if (state.cameras.isEmpty)
          const Padding(
            padding: EdgeInsets.all(40),
            child: Center(child: Text('No configured camera health records.')),
          ),
      ],
    );
  }

  Widget _value(String label, String value) => SizedBox(
    width: 160,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(fontSize: 12)),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
      ],
    ),
  );
}
