import 'package:flutter/material.dart';

class ActivityBadge extends StatelessWidget {
  const ActivityBadge({super.key, required this.activity});
  final String activity;

  @override
  Widget build(BuildContext context) {
    final colors = switch (activity) {
      'ON_PHONE' => (const Color(0xFFFFE1DE), const Color(0xFF9A2E24)),
      'POSSIBLE_PHONE' ||
      'POSSIBLE_IDLE' => (const Color(0xFFFFEEC7), const Color(0xFF805000)),
      'IDLE' => (const Color(0xFFDDEBFF), const Color(0xFF24569A)),
      'UNKNOWN' => (const Color(0xFFE8ECEA), const Color(0xFF52635E)),
      _ => (const Color(0xFFDDF3E7), const Color(0xFF176343)),
    };
    return Semantics(
      label: 'Activity ${label(activity)}',
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: colors.$1,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          child: Text(
            label(activity),
            style: TextStyle(
              color: colors.$2,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ),
    );
  }

  static String label(String value) => value
      .toLowerCase()
      .split('_')
      .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
      .join(' ');
}
