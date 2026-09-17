import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/settings_provider.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});
  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController endpoint;
  @override
  void initState() {
    super.initState();
    endpoint = TextEditingController(
      text: context.read<SettingsProvider>().baseUrl,
    );
  }

  @override
  void dispose() {
    endpoint.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<SettingsProvider>();
    return ListView(
      padding: const EdgeInsets.fromLTRB(22, 8, 22, 30),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Connection',
                  style: Theme.of(
                    context,
                  ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: endpoint,
                  decoration: const InputDecoration(
                    labelText: 'Backend address',
                  ),
                ),
                const SizedBox(height: 12),
                FilledButton(
                  onPressed: () => settings.setBaseUrl(endpoint.text),
                  child: const Text('Save address'),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 14),
        const Card(
          child: ListTile(
            leading: Icon(Icons.bug_report_outlined),
            title: Text('Per-camera TEST mode'),
            subtitle: Text(
              'Open a camera and press TEST to show stored, camera-specific AI evidence overlays. Toggling TEST does not restart or reset tracking.',
            ),
          ),
        ),
        const SizedBox(height: 14),
        const Card(
          child: Padding(
            padding: EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Privacy boundary',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18),
                ),
                SizedBox(height: 10),
                Text(
                  '• No automatic face recognition, face embeddings or face matching.\n• Cross-camera worker IDs use day-scoped clothing/body appearance and show review status.\n• Global IDs are anonymous; they are not automatic employee names.\n• No customer appearance matching or face snapshots.\n• No automatic salary or discipline decisions.\n• Unknown and unavailable periods remain explicit.',
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
