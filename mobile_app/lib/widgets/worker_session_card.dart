import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/worker_model.dart';

class WorkerSessionCard extends StatelessWidget {
  const WorkerSessionCard({super.key, required this.worker, this.onTap});
  final WorkerModel worker;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => Card(
    child: InkWell(
      borderRadius: BorderRadius.circular(18),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            const CircleAvatar(
              radius: 28,
              child: Icon(Icons.person_outline, size: 30),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    worker.displayName,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 4),
                  if (worker.globalWorkerId != null)
                    Text(
                      'Global ID: ${worker.globalWorkerId} (${_identityLabel(worker.identityMatchStatus)})',
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  Text(worker.id, overflow: TextOverflow.ellipsis),
                  Text(
                    '${worker.active ? 'Active' : 'Closed'} · ${_time(worker.firstSeen)} – ${_time(worker.lastSeen)}',
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right),
          ],
        ),
      ),
    ),
  );

  String _time(DateTime? value) =>
      value == null ? 'Unavailable' : DateFormat.Hm().format(value.toLocal());

  String _identityLabel(String? status) => switch (status) {
    'manager_confirmed' => 'manager confirmed',
    'appearance_matched' => 'appearance matched',
    'review_required' => 'review required',
    'provisional' => 'provisional',
    _ => 'not linked',
  };
}
