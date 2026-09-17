import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../models/event_model.dart';
import '../models/worker_model.dart';
import '../services/api_service.dart';
import '../widgets/event_card.dart';
import '../widgets/report_metric.dart';

class WorkerSessionDetailScreen extends StatefulWidget {
  const WorkerSessionDetailScreen({super.key, required this.worker});
  final WorkerModel worker;
  @override
  State<WorkerSessionDetailScreen> createState() =>
      _WorkerSessionDetailScreenState();
}

class _WorkerSessionDetailScreenState extends State<WorkerSessionDetailScreen> {
  List<EventModel> events = [];
  List<Map<String, dynamic>> snapshots = [];
  bool loading = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => load());
  }

  Future<void> load() async {
    final api = context.read<ApiService>();
    try {
      final values = await Future.wait([
        api.get('/worker-sessions/${widget.worker.id}/events'),
        api.get('/worker-sessions/${widget.worker.id}/snapshots'),
      ]);
      events = (values[0] as List<dynamic>)
          .whereType<Map<String, dynamic>>()
          .map(EventModel.fromJson)
          .toList();
      snapshots = (values[1] as List<dynamic>)
          .whereType<Map<String, dynamic>>()
          .toList();
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  double total(String activity) => events
      .where(
        (event) =>
            event.activity == activity && event.reviewStatus != 'false_alarm',
      )
      .fold(0, (sum, event) => sum + (event.durationSeconds ?? 0));

  @override
  Widget build(BuildContext context) {
    final api = context.read<ApiService>();
    final face = snapshots.where((item) => item['kind'] == 'face').firstOrNull;
    final body = snapshots.where((item) => item['kind'] == 'body').firstOrNull;
    Widget preview(Map<String, dynamic>? item, String fallback) => AspectRatio(
      aspectRatio: 4 / 3,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: item == null
            ? ColoredBox(
                color: const Color(0xFFE8ECEA),
                child: Center(child: Text(fallback)),
              )
            : Image.network(
                api.uri('/media/snapshots/${item['media_id']}').toString(),
                headers: api.headers,
                fit: BoxFit.contain,
                errorBuilder: (_, _, _) => Center(child: Text(fallback)),
              ),
      ),
    );
    return Scaffold(
      appBar: AppBar(title: Text(widget.worker.displayName)),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(20),
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: preview(face, 'No safe face preview'),
                            ),
                            const SizedBox(width: 12),
                            Expanded(child: preview(body, 'No body preview')),
                          ],
                        ),
                        const SizedBox(height: 16),
                        Text(
                          widget.worker.id,
                          style: Theme.of(context).textTheme.titleMedium
                              ?.copyWith(fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'Camera ${widget.worker.cameraId} | ${_date(widget.worker.firstSeen)} - ${_date(widget.worker.lastSeen)}',
                        ),
                        const SizedBox(height: 12),
                        Text(
                          widget.worker.globalWorkerId == null
                              ? 'Global anonymous worker ID was not established for this session.'
                              : 'Global anonymous ID: ${widget.worker.globalWorkerId} (${_identityLabel(widget.worker.identityMatchStatus)}).',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                        const Text(
                          'Cross-camera association uses clothing/body appearance only. It is day-scoped, can be wrong with similar uniforms, and must be reviewed for important decisions. No face recognition is used.',
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Text(
                      'All saved session crops',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const Spacer(),
                    Text('${snapshots.length} saved'),
                  ],
                ),
                const SizedBox(height: 10),
                if (snapshots.isEmpty)
                  const Card(
                    child: Padding(
                      padding: EdgeInsets.all(18),
                      child: Text(
                        'No worker crop passed the configured quality threshold for this session.',
                      ),
                    ),
                  )
                else
                  GridView.builder(
                    gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: MediaQuery.sizeOf(context).width >= 900
                          ? 5
                          : 2,
                      childAspectRatio: 0.78,
                      mainAxisSpacing: 10,
                      crossAxisSpacing: 10,
                    ),
                    itemCount: snapshots.length,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemBuilder: (context, index) {
                      final snapshot = snapshots[index];
                      final kind = snapshot['kind']?.toString() ?? 'crop';
                      final quality = (snapshot['quality'] as num?)?.toDouble();
                      return Card(
                        clipBehavior: Clip.antiAlias,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Expanded(
                              child: Image.network(
                                api
                                    .uri(
                                      '/media/snapshots/${snapshot['media_id']}',
                                    )
                                    .toString(),
                                headers: api.headers,
                                fit: BoxFit.contain,
                                errorBuilder: (_, _, _) => const Center(
                                  child: Icon(Icons.broken_image_outlined),
                                ),
                              ),
                            ),
                            Padding(
                              padding: const EdgeInsets.all(8),
                              child: Text(
                                quality == null
                                    ? kind
                                    : '$kind | quality ${quality.toStringAsFixed(2)}',
                                textAlign: TextAlign.center,
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
                const SizedBox(height: 16),
                GridView.count(
                  crossAxisCount: MediaQuery.sizeOf(context).width >= 900
                      ? 4
                      : 2,
                  childAspectRatio: 1.5,
                  mainAxisSpacing: 10,
                  crossAxisSpacing: 10,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  children: [
                    ReportMetric(
                      label: 'Cashier work',
                      value: _duration(total('CASHIER_WORK')),
                      icon: Icons.point_of_sale_outlined,
                    ),
                    ReportMetric(
                      label: 'Serving customers',
                      value: _duration(total('SERVING_CUSTOMER')),
                      icon: Icons.support_agent_outlined,
                    ),
                    ReportMetric(
                      label: 'Fetching medicine',
                      value: _duration(total('FETCHING_MEDICINE')),
                      icon: Icons.medication_outlined,
                    ),
                    ReportMetric(
                      label: 'Computer / POS',
                      value: _duration(total('COMPUTER_POS_WORK')),
                      icon: Icons.point_of_sale_outlined,
                    ),
                    ReportMetric(
                      label: 'Confirmed phone',
                      value: _duration(total('ON_PHONE')),
                      icon: Icons.phone_iphone,
                    ),
                    ReportMetric(
                      label: 'Possible phone',
                      value: _duration(total('POSSIBLE_PHONE')),
                      icon: Icons.help_outline,
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                Text(
                  'Reviewable events',
                  style: Theme.of(
                    context,
                  ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 10),
                ...events.map(
                  (event) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: EventCard(event: event),
                  ),
                ),
              ],
            ),
    );
  }

  String _duration(double seconds) =>
      '${(seconds / 60).toStringAsFixed(1)} min';
  String _date(DateTime? value) => value == null
      ? 'Unavailable'
      : DateFormat.MMMd().add_Hm().format(value.toLocal());

  String _identityLabel(String? value) => switch (value) {
    'manager_confirmed' => 'manager confirmed',
    'appearance_matched' => 'appearance matched',
    'ambiguous_separate' => 'kept separate for review',
    'new_identity' => 'new anonymous ID',
    _ => 'unconfirmed',
  };
}
