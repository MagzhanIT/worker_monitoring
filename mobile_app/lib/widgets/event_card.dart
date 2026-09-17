import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/event_model.dart';
import 'activity_badge.dart';

class EventCard extends StatelessWidget {
  const EventCard({super.key, required this.event, this.onReview});
  final EventModel event;
  final VoidCallback? onReview;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              ActivityBadge(activity: event.activity),
              const Spacer(),
              Text(
                event.startTime == null
                    ? 'Time unavailable'
                    : DateFormat.MMMd().add_Hm().format(
                        event.startTime!.toLocal(),
                      ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            event.workerSessionId,
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          Text(
            '${event.durationSeconds?.toStringAsFixed(0) ?? 'Open'} seconds · confidence ${(event.confidence * 100).round()}%',
          ),
          if (event.limitations.isNotEmpty)
            Text(
              'Limitation: ${event.limitations.first}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          if (event.unknownReason != null)
            Text(
              'Unknown reason: ${event.unknownReason!.replaceAll('_', ' ')}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          const SizedBox(height: 10),
          Row(
            children: [
              Text('Review: ${event.reviewStatus.replaceAll('_', ' ')}'),
              const Spacer(),
              if (onReview != null)
                TextButton.icon(
                  onPressed: onReview,
                  icon: const Icon(Icons.fact_check_outlined),
                  label: const Text('Review'),
                ),
            ],
          ),
        ],
      ),
    ),
  );
}
