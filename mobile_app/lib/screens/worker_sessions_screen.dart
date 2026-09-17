import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/camera_provider.dart';
import '../widgets/worker_session_card.dart';
import 'worker_session_detail_screen.dart';

class WorkerSessionsScreen extends StatelessWidget {
  const WorkerSessionsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<CameraProvider>();
    return ListView(
      padding: const EdgeInsets.fromLTRB(22, 8, 22, 30),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const Icon(Icons.info_outline),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Each camera keeps its own anonymous session. Clear worker sessions may also share a day-scoped global anonymous ID across cameras. ${state.workers.length} session(s) are available.',
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        ...state.workers.map(
          (worker) => Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: WorkerSessionCard(
              worker: worker,
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => WorkerSessionDetailScreen(worker: worker),
                ),
              ),
            ),
          ),
        ),
        if (state.workers.isEmpty)
          const Padding(
            padding: EdgeInsets.all(40),
            child: Center(
              child: Text('No confirmed anonymous worker sessions.'),
            ),
          ),
      ],
    );
  }
}
