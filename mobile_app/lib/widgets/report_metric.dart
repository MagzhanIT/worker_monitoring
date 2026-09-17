import 'package:flutter/material.dart';

class ReportMetric extends StatelessWidget {
  const ReportMetric({
    super.key,
    required this.label,
    required this.value,
    required this.icon,
    this.note,
  });
  final String label;
  final String value;
  final IconData icon;
  final String? note;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: Theme.of(context).colorScheme.primary),
          const Spacer(),
          Text(
            value,
            style: Theme.of(
              context,
            ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800),
          ),
          Text(label, style: Theme.of(context).textTheme.bodyMedium),
          if (note != null)
            Text(note!, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    ),
  );
}
