import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/camera_model.dart';
import '../models/live_person_model.dart';
import '../providers/auth_provider.dart';
import '../providers/camera_provider.dart';
import '../providers/report_provider.dart';
import '../providers/settings_provider.dart';
import '../services/api_service.dart';
import '../services/websocket_service.dart';
import '../widgets/activity_badge.dart';
import '../widgets/camera_stream.dart';
import '../widgets/health_badge.dart';
import 'zone_editor_screen.dart';

class CameraDetailScreen extends StatefulWidget {
  const CameraDetailScreen({super.key, required this.camera});
  final CameraModel camera;
  @override
  State<CameraDetailScreen> createState() => _CameraDetailScreenState();
}

class _CameraDetailScreenState extends State<CameraDetailScreen> {
  final socket = WebSocketService();
  StreamSubscription<Map<String, dynamic>>? subscription;
  bool testMode = false;
  bool debugLoading = true;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (subscription == null) {
      final auth = context.read<AuthProvider>();
      final settings = context.read<SettingsProvider>();
      final cameraProvider = context.read<CameraProvider>();
      if (auth.token != null) {
        subscription = socket
            .connect(
              baseUrl: settings.baseUrl,
              cameraId: widget.camera.id,
              token: auth.token!,
            )
            .listen(
              (payload) => cameraProvider.applyLive(widget.camera.id, payload),
            );
        _loadDebug(api: context.read<ApiService>());
      }
    }
  }

  Future<void> _loadDebug({required ApiService api}) async {
    try {
      final value = await api.get('/cameras/${widget.camera.id}/debug');
      if (mounted && value is Map<String, dynamic>) {
        setState(() => testMode = value['enabled'] == true);
      }
    } catch (_) {
      // Keep the production view usable when an older/offline backend does not
      // expose TEST settings yet. The next explicit toggle will show an error.
    } finally {
      if (mounted) setState(() => debugLoading = false);
    }
  }

  Future<void> _toggleTest(ApiService api) async {
    if (debugLoading) return;
    setState(() => debugLoading = true);
    final enabled = !testMode;
    try {
      await api.put(
        '/cameras/${widget.camera.id}/debug',
        body: {
          'enabled': enabled,
          'show_pose': true,
          'show_zones': true,
          'show_phone_boxes': true,
          'show_assignments': true,
          'show_performance': true,
        },
      );
      if (mounted) setState(() => testMode = enabled);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not change TEST mode: $error')),
        );
      }
    } finally {
      if (mounted) setState(() => debugLoading = false);
    }
  }

  @override
  void dispose() {
    subscription?.cancel();
    socket.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<CameraProvider>();
    final health = state.health[widget.camera.id];
    final api = context.read<ApiService>();
    final observedPeople = state.livePeople[widget.camera.id] ?? const [];
    final wide = MediaQuery.sizeOf(context).width >= 980;
    final video = AspectRatio(
      aspectRatio: 16 / 9,
      child: CameraStream(
        api: api,
        cameraId: widget.camera.id,
        view: testMode ? 'test' : 'normal',
      ),
    );
    final panel = Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  'Current observations',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const Spacer(),
                Text('${observedPeople.length} visible'),
              ],
            ),
            const Divider(height: 24),
            if (observedPeople.isNotEmpty) ...[
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _SummaryChip(
                    label: 'Work observed',
                    count: observedPeople
                        .where(
                          (person) => person.evidenceStatus == 'WORK_OBSERVED',
                        )
                        .length,
                    color: const Color(0xFF176343),
                  ),
                  _SummaryChip(
                    label: 'Confirmed idle',
                    count: observedPeople
                        .where(
                          (person) => person.evidenceStatus == 'CONFIRMED_IDLE',
                        )
                        .length,
                    color: const Color(0xFF24569A),
                  ),
                  _SummaryChip(
                    label: 'Review',
                    count: observedPeople
                        .where(
                          (person) => person.evidenceStatus == 'REVIEW_NEEDED',
                        )
                        .length,
                    color: const Color(0xFF805000),
                  ),
                  _SummaryChip(
                    label: 'Insufficient evidence',
                    count: observedPeople
                        .where(
                          (person) =>
                              person.evidenceStatus == 'INSUFFICIENT_EVIDENCE',
                        )
                        .length,
                    color: const Color(0xFF52635E),
                  ),
                ],
              ),
              const Divider(height: 24),
            ],
            ...observedPeople.take(6).map(_LivePersonRow.new),
            if (observedPeople.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: Text('No person is currently detected.')),
              ),
            if (observedPeople.any(
              (person) =>
                  person.reasons.any(
                    (reason) => reason.contains('no camera zones configured'),
                  ) ||
                  person.reasons.any(
                    (reason) => reason.contains('feet inside employee area'),
                  ),
            ))
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(
                  'Zone setup needs attention. Put employee_area or cashier under the worker\'s feet. Draw shelf_interaction or register_interaction over the surfaces reached by the worker\'s hands.',
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
          ],
        ),
      ),
    );
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.camera.name),
        actions: [
          HealthBadge(status: health?.status ?? 'UNAVAILABLE'),
          const SizedBox(width: 18),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          if (wide)
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(flex: 7, child: video),
                const SizedBox(width: 16),
                Expanded(flex: 3, child: panel),
              ],
            )
          else ...[
            video,
            const SizedBox(height: 16),
            panel,
          ],
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Wrap(
                spacing: 10,
                runSpacing: 10,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  FilledButton.icon(
                    onPressed: () =>
                        state.cameraAction(widget.camera.id, 'start'),
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('Start'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () =>
                        state.cameraAction(widget.camera.id, 'stop'),
                    icon: const Icon(Icons.stop),
                    label: const Text('Stop'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () =>
                        state.cameraAction(widget.camera.id, 'restart'),
                    icon: const Icon(Icons.restart_alt),
                    label: const Text('Restart'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => ZoneEditorScreen(camera: widget.camera),
                      ),
                    ),
                    icon: const Icon(Icons.polyline_outlined),
                    label: const Text('Edit zones'),
                  ),
                  FilledButton.tonalIcon(
                    onPressed: debugLoading ? null : () => _toggleTest(api),
                    icon: const Icon(Icons.bug_report_outlined),
                    label: Text(testMode ? 'TEST: ON' : 'TEST'),
                  ),
                  if (testMode)
                    const Chip(
                      avatar: Icon(Icons.visibility_outlined, size: 18),
                      label: Text(
                        'AI evidence overlay — tracking is preserved',
                      ),
                    ),
                  OutlinedButton.icon(
                    onPressed: () =>
                        context.read<ReportProvider>().generate(null),
                    icon: const Icon(Icons.description_outlined),
                    label: const Text('Generate report'),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Wrap(
                spacing: 32,
                runSpacing: 16,
                children: [
                  _Reading(
                    label: 'Capture FPS',
                    value: health?.captureFps.toStringAsFixed(1) ?? '0.0',
                  ),
                  _Reading(
                    label: 'Processing FPS',
                    value: health?.processingFps.toStringAsFixed(1) ?? '0.0',
                  ),
                  _Reading(
                    label: 'Last frame age',
                    value: health?.lastFrameAgeSeconds == null
                        ? 'Unavailable'
                        : '${health!.lastFrameAgeSeconds!.toStringAsFixed(1)} s',
                  ),
                  _Reading(
                    label: 'Presence',
                    value: health?.available == true ? 'Observed' : 'UNKNOWN',
                  ),
                  _Reading(
                    label: 'System status',
                    value: health?.available == true
                        ? 'Running'
                        : 'CAMERA_UNAVAILABLE',
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _LivePersonRow extends StatelessWidget {
  const _LivePersonRow(this.person);
  final LivePersonModel person;

  @override
  Widget build(BuildContext context) {
    final role = switch (person.role) {
      'WORKER' => 'Worker',
      'CUSTOMER' => 'Customer',
      _ => 'Role unknown',
    };
    final reason = person.reasons.isEmpty
        ? 'Waiting for activity evidence'
        : person.reasons.join(' | ');
    final movement = switch (person.motion) {
      'RECENT_MOVEMENT' => 'Recent movement observed',
      'STATIONARY' =>
        'Stationary for ${person.stationarySeconds?.toStringAsFixed(1) ?? '?'} s (not proof of inactivity)',
      _ => 'Movement evidence unavailable',
    };
    final identity = person.globalWorkerId == null
        ? 'Global ID pending'
        : '${person.globalWorkerId} | ${_identityLabel(person.identityMatchStatus)}';
    final service = person.customerServiceSessionId == null
        ? ''
        : '\nService ${person.customerServiceSessionId}: ${person.customerServicePhase ?? 'UNKNOWN'}';
    final unknown = person.unknownReason == null
        ? ''
        : '\nUnknown reason: ${person.unknownReason!.replaceAll('_', ' ')}';
    final evidence = person.role != 'WORKER'
        ? ''
        : '\nEvidence ${person.evidenceQuality ?? 'LOW'} | '
              'candidate ${person.candidateActivity == null ? 'none' : ActivityBadge.label(person.candidateActivity!)} '
              '${person.candidateDurationSeconds.toStringAsFixed(1)} s | '
              'idle ${person.idleCandidateSeconds.toStringAsFixed(1)}/${person.idleConfirmationSeconds.toStringAsFixed(1)} s';
    final blockers = person.idleBlockingReasons.isEmpty
        ? ''
        : '\nIdle blocked: ${person.idleBlockingReasons.join(' | ')}';
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 4, vertical: 5),
      leading: CircleAvatar(
        backgroundColor: Theme.of(context).colorScheme.secondaryContainer,
        child: const Icon(Icons.person_outline),
      ),
      title: Text(
        '${person.displayName} | $role',
        style: const TextStyle(fontWeight: FontWeight.w700),
      ),
      subtitle: Text(
        '$identity$service\n$movement\nActivity: ${ActivityBadge.label(person.activity)} | $reason$unknown$evidence$blockers',
        maxLines: 8,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: _EvidenceBadge(status: person.evidenceStatus),
    );
  }

  String _identityLabel(String? value) => switch (value) {
    'manager_confirmed' => 'manager confirmed',
    'appearance_matched' => 'appearance matched',
    'ambiguous_separate' => 'kept separate for review',
    'new_identity' => 'new anonymous ID',
    'pending_active_conflict' => 'waiting for camera hand-off',
    _ => 'collecting evidence',
  };
}

class _EvidenceBadge extends StatelessWidget {
  const _EvidenceBadge({required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    final (label, background, foreground) = switch (status) {
      'WORK_OBSERVED' => (
        'Work observed',
        const Color(0xFFDDF3E7),
        const Color(0xFF176343),
      ),
      'REVIEW_NEEDED' => (
        'Review evidence',
        const Color(0xFFFFEEC7),
        const Color(0xFF805000),
      ),
      'APPROVED_BREAK' => (
        'Approved break',
        const Color(0xFFDDEBFF),
        const Color(0xFF24569A),
      ),
      'CUSTOMER_OBSERVED' => (
        'Customer observed',
        const Color(0xFFE9E2FA),
        const Color(0xFF59408A),
      ),
      'CONFIRMED_IDLE' => (
        'Confirmed idle',
        const Color(0xFFDDEBFF),
        const Color(0xFF24569A),
      ),
      _ => (
        'Insufficient evidence',
        const Color(0xFFE8ECEA),
        const Color(0xFF52635E),
      ),
    };
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        child: Text(
          label,
          style: TextStyle(
            color: foreground,
            fontSize: 11,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}

class _SummaryChip extends StatelessWidget {
  const _SummaryChip({
    required this.label,
    required this.count,
    required this.color,
  });
  final String label;
  final int count;
  final Color color;

  @override
  Widget build(BuildContext context) => Chip(
    visualDensity: VisualDensity.compact,
    side: BorderSide(color: color.withValues(alpha: 0.25)),
    backgroundColor: color.withValues(alpha: 0.08),
    label: Text(
      '$label: $count',
      style: TextStyle(color: color, fontWeight: FontWeight.w700),
    ),
  );
}

class _Reading extends StatelessWidget {
  const _Reading({required this.label, required this.value});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => SizedBox(
    width: 170,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 3),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
      ],
    ),
  );
}
