import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/event_model.dart';
import '../providers/camera_provider.dart';
import '../services/api_service.dart';
import '../widgets/event_card.dart';

class EventReviewScreen extends StatefulWidget {
  const EventReviewScreen({super.key});
  @override
  State<EventReviewScreen> createState() => _EventReviewScreenState();
}

class _EventReviewScreenState extends State<EventReviewScreen> {
  String filter = 'important';

  @override
  Widget build(BuildContext context) {
    final state = context.watch<CameraProvider>();
    final events = filter == 'all'
        ? state.events
        : state.events
              .where(
                (event) => {
                  'ON_PHONE',
                  'POSSIBLE_IDLE',
                  'POSSIBLE_PHONE',
                  'UNKNOWN',
                }.contains(event.activity),
              )
              .toList();
    return ListView(
      padding: const EdgeInsets.fromLTRB(22, 8, 22, 30),
      children: [
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'important', label: Text('Important')),
            ButtonSegment(value: 'all', label: Text('All events')),
          ],
          selected: {filter},
          onSelectionChanged: (value) => setState(() => filter = value.first),
        ),
        const SizedBox(height: 14),
        ...events.map(
          (event) => Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: EventCard(event: event, onReview: () => review(event)),
          ),
        ),
        if (events.isEmpty)
          const Padding(
            padding: EdgeInsets.all(40),
            child: Center(child: Text('No events match this view.')),
          ),
      ],
    );
  }

  Future<void> review(EventModel event) async {
    final note = TextEditingController();
    String status = 'confirmed';
    final result = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Review original result'),
          content: SizedBox(
            width: 430,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Original activity: ${event.activity} · confidence ${(event.confidence * 100).round()}%',
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<String>(
                  initialValue: status,
                  decoration: const InputDecoration(
                    labelText: 'Manager decision',
                  ),
                  items: const [
                    DropdownMenuItem(
                      value: 'confirmed',
                      child: Text('Confirmed'),
                    ),
                    DropdownMenuItem(
                      value: 'false_alarm',
                      child: Text('False alarm'),
                    ),
                    DropdownMenuItem(
                      value: 'approved_activity',
                      child: Text('Approved activity'),
                    ),
                    DropdownMenuItem(value: 'unclear', child: Text('Unclear')),
                  ],
                  onChanged: (value) =>
                      setDialogState(() => status = value ?? status),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: note,
                  maxLines: 3,
                  decoration: const InputDecoration(labelText: 'Manager note'),
                ),
                const SizedBox(height: 8),
                const Text(
                  'The original automated result remains preserved.',
                  style: TextStyle(fontSize: 12),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Save review'),
            ),
          ],
        ),
      ),
    );
    if (result == true && mounted) {
      await context.read<ApiService>().post(
        '/events/${event.id}/review',
        body: {'manager_status': status, 'manager_note': note.text},
      );
      if (mounted) await context.read<CameraProvider>().refresh();
    }
    note.dispose();
  }
}
