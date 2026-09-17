import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../providers/camera_provider.dart';
import '../screens/daily_report_screen.dart';
import '../screens/event_review_screen.dart';
import '../screens/settings_screen.dart';
import '../screens/system_health_screen.dart';
import '../screens/worker_sessions_screen.dart';
import '../theme/app_theme.dart';
import '../widgets/activity_badge.dart';
import '../widgets/health_badge.dart';
import '../widgets/report_metric.dart';
import 'camera_detail_screen.dart';
import 'camera_form_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});
  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  int index = 0;
  bool loaded = false;

  static const destinations = [
    (Icons.dashboard_outlined, Icons.dashboard, 'Overview'),
    (Icons.videocam_outlined, Icons.videocam, 'Cameras'),
    (Icons.badge_outlined, Icons.badge, 'Worker sessions'),
    (Icons.fact_check_outlined, Icons.fact_check, 'Events'),
    (Icons.assessment_outlined, Icons.assessment, 'Reports'),
    (Icons.monitor_heart_outlined, Icons.monitor_heart, 'System health'),
    (Icons.settings_outlined, Icons.settings, 'Settings'),
  ];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!loaded) {
      loaded = true;
      WidgetsBinding.instance.addPostFrameCallback(
        (_) => context.read<CameraProvider>().refresh(),
      );
    }
  }

  Widget page() => switch (index) {
    0 => const _Overview(),
    1 => const _Cameras(),
    2 => const WorkerSessionsScreen(),
    3 => const EventReviewScreen(),
    4 => const DailyReportScreen(),
    5 => const SystemHealthScreen(),
    _ => const SettingsScreen(),
  };

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 860;
    final body = Column(
      children: [
        _TopBar(
          title: destinations[index].$3,
          onRefresh: () => context.read<CameraProvider>().refresh(),
        ),
        Expanded(child: page()),
      ],
    );
    return Scaffold(
      body: SafeArea(
        child: Row(
          children: [
            if (wide)
              NavigationRail(
                extended: MediaQuery.sizeOf(context).width >= 1180,
                selectedIndex: index,
                onDestinationSelected: (value) => setState(() => index = value),
                leading: const Padding(
                  padding: EdgeInsets.symmetric(vertical: 20),
                  child: Icon(
                    Icons.local_pharmacy,
                    color: AppTheme.forest,
                    size: 32,
                  ),
                ),
                destinations: destinations
                    .map(
                      (item) => NavigationRailDestination(
                        icon: Icon(item.$1),
                        selectedIcon: Icon(item.$2),
                        label: Text(item.$3),
                      ),
                    )
                    .toList(),
              ),
            Expanded(child: body),
          ],
        ),
      ),
      bottomNavigationBar: wide
          ? null
          : NavigationBar(
              selectedIndex: index > 4 ? 0 : index,
              onDestinationSelected: (value) => setState(() => index = value),
              destinations: destinations
                  .take(5)
                  .map(
                    (item) => NavigationDestination(
                      icon: Icon(item.$1),
                      selectedIcon: Icon(item.$2),
                      label: item.$3,
                    ),
                  )
                  .toList(),
            ),
      drawer: wide
          ? null
          : Drawer(
              child: SafeArea(
                child: ListView(
                  children: [
                    const DrawerHeader(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(
                            Icons.local_pharmacy,
                            color: AppTheme.forest,
                            size: 34,
                          ),
                          Spacer(),
                          Text(
                            'Pharmacy Monitor',
                            style: TextStyle(
                              fontWeight: FontWeight.w800,
                              fontSize: 20,
                            ),
                          ),
                        ],
                      ),
                    ),
                    ListTile(
                      leading: const Icon(Icons.monitor_heart_outlined),
                      title: const Text('System health'),
                      onTap: () {
                        Navigator.pop(context);
                        setState(() => index = 5);
                      },
                    ),
                    ListTile(
                      leading: const Icon(Icons.settings_outlined),
                      title: const Text('Settings'),
                      onTap: () {
                        Navigator.pop(context);
                        setState(() => index = 6);
                      },
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.title, required this.onRefresh});
  final String title;
  final VoidCallback onRefresh;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(22, 14, 14, 10),
    child: Row(
      children: [
        Builder(
          builder: (context) => MediaQuery.sizeOf(context).width < 860
              ? IconButton(
                  onPressed: Scaffold.of(context).openDrawer,
                  icon: const Icon(Icons.menu),
                )
              : const SizedBox(),
        ),
        Expanded(
          child: Text(
            title,
            style: Theme.of(
              context,
            ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
          ),
        ),
        IconButton(
          tooltip: 'Refresh',
          onPressed: onRefresh,
          icon: const Icon(Icons.refresh),
        ),
        IconButton(
          tooltip: 'Sign out',
          onPressed: context.read<AuthProvider>().logout,
          icon: const Icon(Icons.logout),
        ),
      ],
    ),
  );
}

class _Overview extends StatelessWidget {
  const _Overview();
  @override
  Widget build(BuildContext context) {
    final state = context.watch<CameraProvider>();
    final healthy = state.health.values
        .where((value) => value.status == 'HEALTHY')
        .length;
    final phoneEvents = state.events
        .where((event) => event.activity == 'ON_PHONE' && event.endTime == null)
        .length;
    return RefreshIndicator(
      onRefresh: state.refresh,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(22, 8, 22, 30),
        children: [
          if (state.error != null) _Notice(text: state.error!, danger: true),
          const _Notice(
            text:
                'Facts, possible results and unavailable periods stay separate. Global worker IDs are anonymous appearance associations, not confirmed identity or employee ratings.',
          ),
          const SizedBox(height: 18),
          GridView.count(
            crossAxisCount: MediaQuery.sizeOf(context).width >= 1100 ? 4 : 2,
            childAspectRatio: 1.55,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 12,
            crossAxisSpacing: 12,
            children: [
              ReportMetric(
                label: 'Healthy cameras',
                value: '$healthy / ${state.cameras.length}',
                icon: Icons.videocam_outlined,
              ),
              ReportMetric(
                label: 'Visible sessions',
                value:
                    '${state.workers.where((worker) => worker.active).length}',
                icon: Icons.people_outline,
              ),
              ReportMetric(
                label: 'Customers waiting',
                value:
                    '${state.activeWaitingCustomers.values.fold<int>(0, (sum, value) => sum + value)}',
                icon: Icons.hourglass_top,
                note: 'Confirmed in configured queue/service zones',
              ),
              ReportMetric(
                label: 'Active confirmed phone',
                value: '$phoneEvents',
                icon: Icons.phone_iphone,
              ),
            ],
          ),
          const SizedBox(height: 22),
          Text(
            'Camera coverage',
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 10),
          ...state.cameras.map(
            (camera) => Card(
              child: ListTile(
                leading: const CircleAvatar(
                  child: Icon(Icons.videocam_outlined),
                ),
                title: Text(
                  camera.name,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                subtitle: Text(camera.source),
                trailing: HealthBadge(
                  status: state.health[camera.id]?.status ?? 'UNAVAILABLE',
                ),
              ),
            ),
          ),
          if (state.cameras.isEmpty && !state.loading)
            const _Empty(
              icon: Icons.videocam_off_outlined,
              text: 'No cameras configured yet.',
            ),
          const SizedBox(height: 22),
          Text(
            'Recent important events',
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 10),
          ...state.events
              .take(5)
              .map(
                (event) => Card(
                  child: ListTile(
                    title: Text(event.workerSessionId),
                    subtitle: Text(
                      '${event.durationSeconds?.toStringAsFixed(0) ?? 'Open'} seconds',
                    ),
                    trailing: ActivityBadge(activity: event.activity),
                  ),
                ),
              ),
        ],
      ),
    );
  }
}

class _Cameras extends StatelessWidget {
  const _Cameras();
  @override
  Widget build(BuildContext context) {
    final state = context.watch<CameraProvider>();
    return ListView(
      padding: const EdgeInsets.fromLTRB(22, 8, 22, 30),
      children: [
        Align(
          alignment: Alignment.centerRight,
          child: FilledButton.icon(
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const CameraFormScreen()),
            ),
            icon: const Icon(Icons.add),
            label: const Text('Add camera'),
          ),
        ),
        const SizedBox(height: 12),
        ...state.cameras.map(
          (camera) => Card(
            child: ListTile(
              contentPadding: const EdgeInsets.all(16),
              leading: const CircleAvatar(
                radius: 26,
                child: Icon(Icons.videocam_outlined),
              ),
              title: Text(
                camera.name,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              subtitle: Text(camera.source),
              trailing: PopupMenuButton<String>(
                onSelected: (action) async {
                  if (action == 'open') {
                    await Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => CameraDetailScreen(camera: camera),
                      ),
                    );
                  } else if (action == 'edit') {
                    await Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => CameraFormScreen(camera: camera),
                      ),
                    );
                  } else if (action == 'delete' && context.mounted) {
                    final confirmed = await showDialog<bool>(
                      context: context,
                      builder: (dialogContext) => AlertDialog(
                        title: const Text('Delete camera?'),
                        content: Text(
                          'Delete “${camera.name}”? Existing analytics are not deleted.',
                        ),
                        actions: [
                          TextButton(
                            onPressed: () =>
                                Navigator.pop(dialogContext, false),
                            child: const Text('Cancel'),
                          ),
                          FilledButton(
                            onPressed: () => Navigator.pop(dialogContext, true),
                            child: const Text('Delete'),
                          ),
                        ],
                      ),
                    );
                    if (confirmed == true && context.mounted) {
                      try {
                        await context.read<CameraProvider>().deleteCamera(
                          camera.id,
                        );
                      } catch (e) {
                        if (context.mounted) {
                          ScaffoldMessenger.of(
                            context,
                          ).showSnackBar(SnackBar(content: Text(e.toString())));
                        }
                      }
                    }
                  }
                },
                itemBuilder: (_) => const [
                  PopupMenuItem(value: 'open', child: Text('Open')),
                  PopupMenuItem(value: 'edit', child: Text('Edit')),
                  PopupMenuItem(value: 'delete', child: Text('Delete')),
                ],
              ),
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => CameraDetailScreen(camera: camera),
                ),
              ),
            ),
          ),
        ),
        if (state.cameras.isEmpty)
          const _Empty(
            icon: Icons.add_a_photo_outlined,
            text:
                'No cameras yet. Use Add camera to connect a webcam, RTSP stream, or local video.',
          ),
      ],
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice({required this.text, this.danger = false});
  final String text;
  final bool danger;
  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: danger ? const Color(0xFFFFE5E1) : AppTheme.mint,
      borderRadius: BorderRadius.circular(14),
    ),
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          Icon(danger ? Icons.error_outline : Icons.privacy_tip_outlined),
          const SizedBox(width: 10),
          Expanded(child: Text(text)),
        ],
      ),
    ),
  );
}

class _Empty extends StatelessWidget {
  const _Empty({required this.icon, required this.text});
  final IconData icon;
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(42),
    child: Column(
      children: [
        Icon(icon, size: 44, color: Colors.black38),
        const SizedBox(height: 10),
        Text(text, textAlign: TextAlign.center),
      ],
    ),
  );
}
