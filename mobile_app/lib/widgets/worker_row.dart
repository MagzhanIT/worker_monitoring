import 'package:flutter/material.dart';

import '../models/worker_model.dart';
import 'activity_badge.dart';

class WorkerRow extends StatelessWidget {
  const WorkerRow({
    super.key,
    required this.worker,
    required this.activity,
    this.onTap,
  });
  final WorkerModel worker;
  final String activity;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => ListTile(
    onTap: onTap,
    contentPadding: const EdgeInsets.symmetric(horizontal: 4, vertical: 5),
    leading: CircleAvatar(
      backgroundColor: Theme.of(context).colorScheme.secondaryContainer,
      child: const Icon(Icons.person_outline),
    ),
    title: Text(
      worker.displayName,
      style: const TextStyle(fontWeight: FontWeight.w700),
    ),
    subtitle: Text(worker.id, maxLines: 1, overflow: TextOverflow.ellipsis),
    trailing: ActivityBadge(activity: activity),
  );
}
