import 'package:flutter/material.dart';

class HealthBadge extends StatelessWidget {
  const HealthBadge({super.key, required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    final healthy = status == 'HEALTHY';
    final color = healthy
        ? const Color(0xFF187A55)
        : status == 'DEGRADED'
        ? const Color(0xFFB06A00)
        : const Color(0xFFB33A31);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.circle, size: 9, color: color),
        const SizedBox(width: 6),
        Text(
          status,
          style: TextStyle(
            color: color,
            fontWeight: FontWeight.w700,
            fontSize: 12,
          ),
        ),
      ],
    );
  }
}
