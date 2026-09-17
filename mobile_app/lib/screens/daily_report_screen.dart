import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../providers/report_provider.dart';
import '../services/api_service.dart';
import '../widgets/report_metric.dart';

class DailyReportScreen extends StatefulWidget {
  const DailyReportScreen({super.key});
  @override
  State<DailyReportScreen> createState() => _DailyReportScreenState();
}

class _DailyReportScreenState extends State<DailyReportScreen> {
  DateTime date = DateTime.now();
  Map<String, dynamic>? analytics;
  Map<String, dynamic>? customers;
  bool loading = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => load());
  }

  Future<void> load() async {
    setState(() => loading = true);
    final value = DateFormat('yyyy-MM-dd').format(date);
    final api = context.read<ApiService>();
    try {
      final results = await Future.wait([
        api.get('/analytics/daily', query: {'report_date': value}),
        api.get('/analytics/customer-service', query: {'report_date': value}),
      ]);
      analytics = results[0] as Map<String, dynamic>;
      customers = results[1] as Map<String, dynamic>;
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> chooseDate() async {
    final picked = await showDatePicker(
      context: context,
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
      initialDate: date,
    );
    if (picked != null) {
      date = picked;
      await load();
    }
  }

  @override
  Widget build(BuildContext context) {
    final reports = context.watch<ReportProvider>();
    String metric(String key) {
      final value = (analytics?[key] as num?)?.toDouble();
      return value == null
          ? 'Unavailable'
          : '${(value / 60).toStringAsFixed(1)} min';
    }

    return ListView(
      padding: const EdgeInsets.fromLTRB(22, 8, 22, 30),
      children: [
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            OutlinedButton.icon(
              onPressed: chooseDate,
              icon: const Icon(Icons.calendar_today_outlined),
              label: Text(DateFormat.yMMMd().format(date)),
            ),
            FilledButton.icon(
              onPressed: reports.loading
                  ? null
                  : () =>
                        reports.generate(DateFormat('yyyy-MM-dd').format(date)),
              icon: const Icon(Icons.description_outlined),
              label: const Text('Generate local report'),
            ),
            OutlinedButton.icon(
              onPressed: load,
              icon: const Icon(Icons.refresh),
              label: const Text('Refresh metrics'),
            ),
          ],
        ),
        if (reports.error != null)
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: Text(
              reports.error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        const SizedBox(height: 18),
        if (loading) const LinearProgressIndicator(),
        GridView.count(
          crossAxisCount: MediaQuery.sizeOf(context).width >= 1050 ? 4 : 2,
          childAspectRatio: 1.5,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 10,
          crossAxisSpacing: 10,
          children: [
            ReportMetric(
              label: 'Confirmed productive activity observed',
              value: metric('confirmed_productive_seconds'),
              icon: Icons.task_alt,
            ),
            ReportMetric(
              label: 'Confirmed phone',
              value: metric('confirmed_phone_seconds'),
              icon: Icons.phone_iphone,
            ),
            ReportMetric(
              label: 'Possible phone',
              value: metric('possible_phone_seconds'),
              icon: Icons.help_outline,
            ),
            ReportMetric(
              label: 'Unknown activity',
              value: metric('unknown_activity_seconds'),
              icon: Icons.visibility_off_outlined,
            ),
          ],
        ),
        const SizedBox(height: 18),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Report quality',
                  style: Theme.of(
                    context,
                  ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 10),
                _row(
                  'Camera availability',
                  _percent(
                    analytics?['report_quality']?['camera_availability_percent'],
                  ),
                ),
                _row(
                  'Observation coverage',
                  _percent(
                    analytics?['report_quality']?['observation_coverage_percent'],
                  ),
                ),
                _row(
                  'Unknown activity',
                  _percent(
                    analytics?['report_quality']?['unknown_activity_percent'],
                  ),
                ),
                _row(
                  'Camera unavailable',
                  metric('camera_unavailable_seconds'),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 14),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Customer waiting and service',
                  style: Theme.of(
                    context,
                  ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 10),
                _row(
                  'Customers detected',
                  customers?['customers_detected']?.toString() ?? 'Unavailable',
                ),
                _row(
                  'Completed service sessions',
                  customers?['completed_service_sessions']?.toString() ??
                      'Unavailable',
                ),
                _row(
                  'Customers currently waiting',
                  customers?['customers_currently_waiting']?.toString() ??
                      'Unavailable',
                ),
                _row(
                  'Average wait',
                  _seconds(customers?['average_wait_seconds']),
                ),
                _row(
                  'Median wait',
                  _seconds(customers?['median_wait_seconds']),
                ),
                _row(
                  'Longest wait',
                  _seconds(customers?['longest_wait_seconds']),
                ),
                _row(
                  'Average total service',
                  _seconds(customers?['average_service_seconds']),
                ),
                _row(
                  'Median total service',
                  _seconds(customers?['median_service_seconds']),
                ),
                _row(
                  'Average medicine retrieval',
                  _seconds(customers?['average_medicine_retrieval_seconds']),
                ),
                _row(
                  'Left without service',
                  customers?['customers_left_without_service']?.toString() ??
                      'Unavailable',
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 14),
        const Card(
          child: Padding(
            padding: EdgeInsets.all(16),
            child: Text(
              'Short camera-local tracking gaps may be stitched only when time, movement, location, and clothing/body evidence agree. Cross-camera anonymous IDs remain day-scoped and reviewable; no face recognition or automatic real-name identification is used.',
            ),
          ),
        ),
      ],
    );
  }

  Widget _row(String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Row(
      children: [
        Expanded(child: Text(label)),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
      ],
    ),
  );
  String _percent(dynamic value) =>
      value is num ? '${value.toStringAsFixed(1)}%' : 'Unavailable';
  String _seconds(dynamic value) =>
      value is num ? '${value.toStringAsFixed(0)} s' : 'Unavailable';
}
