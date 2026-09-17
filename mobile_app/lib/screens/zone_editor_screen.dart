import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/camera_model.dart';
import '../models/zone_model.dart';
import '../services/api_service.dart';
import '../widgets/zone_painter.dart';

class ZoneEditorScreen extends StatefulWidget {
  const ZoneEditorScreen({super.key, required this.camera});
  final CameraModel camera;
  @override
  State<ZoneEditorScreen> createState() => _ZoneEditorScreenState();
}

class _ZoneEditorScreenState extends State<ZoneEditorScreen> {
  static const types = [
    'employee_area',
    'customer_area',
    'cashier',
    'register_interaction',
    'shelf_interaction',
    'medicine_shelf',
    'storage',
    'computer',
    'pos',
    'service_position',
    'waiting',
    'entrance',
    'authorized_out_of_zone',
    'break_area',
    'ignore_area',
  ];
  static const descriptions = {
    'employee_area':
        'Floor area where staff normally stand or walk. Include their feet, not the shelves.',
    'customer_area':
        'Floor area open to customers. Include customer feet and keep it separate from staff-only floor where possible.',
    'cashier':
        'Floor behind the counter where the cashier stands. Combine it with register_interaction over the register surface.',
    'register_interaction':
        'Register or checkout work surface reached by a worker hand. Hand contact plus cashier position supports CASHIER_WORK.',
    'shelf_interaction':
        'Shelf fronts or stocking surfaces reached by a worker hand. Combine it with employee_area under the worker feet.',
    'medicine_shelf':
        'Medicine shelf or drawer surface reached while fulfilling an active customer request.',
    'storage':
        'Staff-only floor area used to retrieve stored medicines or supplies.',
    'computer':
        'Computer keyboard, screen, or desk interaction area used during service.',
    'pos': 'Point-of-sale device or payment terminal interaction area.',
    'service_position':
        'Floor position where a worker serves a nearby customer.',
    'waiting':
        'Customer floor area where a queue begins. This starts customer waiting-time measurement.',
    'entrance': 'Floor area used to observe customers entering the scene.',
    'authorized_out_of_zone':
        'An approved staff location outside normal work areas; do not treat presence here as inactivity.',
    'break_area':
        'Approved break floor area. A confirmed worker here is shown as APPROVED_BREAK.',
    'ignore_area':
        'Area excluded from monitoring, such as mirrors, screens, or neighboring premises.',
  };
  final name = TextEditingController();
  final points = <Offset>[];
  final canvasKey = GlobalKey();
  String type = types.first;
  bool closed = false;
  bool loading = true;
  String? status;
  ui.Image? image;
  Size imageSize = const Size(1920, 1080);
  List<ZoneModel> saved = [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => load());
  }

  @override
  void dispose() {
    name.dispose();
    image?.dispose();
    super.dispose();
  }

  Future<void> load() async {
    final api = context.read<ApiService>();
    try {
      final results = await Future.wait([
        api.get('/cameras/${widget.camera.id}/zones'),
        api.download('/cameras/${widget.camera.id}/frame.jpg'),
      ]);
      saved = (results[0] as List<dynamic>)
          .whereType<Map<String, dynamic>>()
          .map(ZoneModel.fromJson)
          .toList();
      final bytes = results[1] as Uint8List;
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      image = frame.image;
      imageSize = Size(image!.width.toDouble(), image!.height.toDouble());
    } catch (exception) {
      status = 'Frame or saved zones unavailable: $exception';
    }
    if (mounted) setState(() => loading = false);
  }

  void addPoint(TapDownDetails details) {
    if (closed) return;
    final box = canvasKey.currentContext?.findRenderObject() as RenderBox?;
    if (box == null) return;
    final normalized = screenToNormalized(
      box.globalToLocal(details.globalPosition),
      box.size,
      imageSize,
    );
    if (normalized != null) setState(() => points.add(normalized));
  }

  Future<void> validateAndSave() async {
    if (!closed || points.length < 3 || name.text.trim().isEmpty) {
      setState(
        () => status =
            'Close a polygon with at least three points and enter a name.',
      );
      return;
    }
    final zone = ZoneModel(
      displayName: name.text.trim(),
      zoneType: type,
      normalizedPoints: points,
    );
    final api = context.read<ApiService>();
    try {
      final validation =
          await api.post(
                '/cameras/${widget.camera.id}/zones/validate',
                body: zone.toJson(),
              )
              as Map<String, dynamic>;
      if (validation['valid'] != true) {
        setState(
          () => status = (validation['errors'] as List<dynamic>? ?? const [])
              .join(' · '),
        );
        return;
      }
      final savedValue =
          await api.post(
                '/cameras/${widget.camera.id}/zones',
                body: zone.toJson(),
              )
              as Map<String, dynamic>;
      setState(() {
        saved.add(ZoneModel.fromJson(savedValue));
        status =
            'Zone saved and will become active within about 2 seconds. No camera restart is needed.';
        points.clear();
        closed = false;
        name.clear();
      });
    } catch (exception) {
      setState(() => status = exception.toString());
    }
  }

  Future<void> deleteZone(ZoneModel zone) async {
    if (zone.id == null) return;
    await context.read<ApiService>().delete(
      '/cameras/${widget.camera.id}/zones/${zone.id}',
    );
    setState(() => saved.remove(zone));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Zone editor · ${widget.camera.name}')),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : LayoutBuilder(
              builder: (context, constraints) {
                final wide = constraints.maxWidth >= 900;
                final canvas = GestureDetector(
                  key: canvasKey,
                  onTapDown: addPoint,
                  child: CustomPaint(
                    painter: ZonePainter(
                      points: List.of(points),
                      imageSize: imageSize,
                      closed: closed,
                      savedZones: List.of(saved),
                      label: name.text.isEmpty ? null : name.text,
                      image: image,
                    ),
                    child: const SizedBox.expand(),
                  ),
                );
                final editor = ListView(
                  padding: const EdgeInsets.all(18),
                  children: [
                    const Text(
                      'Draw on the exact camera frame',
                      style: TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 18,
                      ),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'Standing zones follow a person\'s feet. Interaction zones follow fresh wrist points. Taps outside the displayed image are ignored.',
                    ),
                    const SizedBox(height: 18),
                    TextField(
                      controller: name,
                      onChanged: (_) => setState(() {}),
                      decoration: const InputDecoration(
                        labelText: 'Display name',
                      ),
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      initialValue: type,
                      decoration: const InputDecoration(
                        labelText: 'Formal zone type',
                      ),
                      items: types
                          .map(
                            (value) => DropdownMenuItem(
                              value: value,
                              child: Text(value.replaceAll('_', ' ')),
                            ),
                          )
                          .toList(),
                      onChanged: (value) =>
                          setState(() => type = value ?? type),
                    ),
                    const SizedBox(height: 8),
                    DecoratedBox(
                      decoration: BoxDecoration(
                        color: Theme.of(
                          context,
                        ).colorScheme.surfaceContainerHighest,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Text(descriptions[type]!),
                      ),
                    ),
                    const SizedBox(height: 14),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        OutlinedButton.icon(
                          onPressed: points.isEmpty || closed
                              ? null
                              : () => setState(points.removeLast),
                          icon: const Icon(Icons.undo),
                          label: const Text('Undo point'),
                        ),
                        OutlinedButton.icon(
                          onPressed: () => setState(() {
                            points.clear();
                            closed = false;
                          }),
                          icon: const Icon(Icons.refresh),
                          label: const Text('Reset'),
                        ),
                        FilledButton.tonalIcon(
                          onPressed: points.length < 3
                              ? null
                              : () => setState(() => closed = true),
                          icon: const Icon(Icons.check),
                          label: const Text('Close polygon'),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    FilledButton.icon(
                      onPressed: validateAndSave,
                      icon: const Icon(Icons.save_outlined),
                      label: const Text('Validate and save'),
                    ),
                    if (status != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text(status!),
                      ),
                    const Divider(height: 32),
                    Text(
                      'Saved zones (${saved.length})',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    ...saved.map(
                      (zone) => ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(zone.displayName),
                        subtitle: Text(zone.zoneType),
                        trailing: IconButton(
                          tooltip: 'Delete zone',
                          onPressed: () => deleteZone(zone),
                          icon: const Icon(Icons.delete_outline),
                        ),
                      ),
                    ),
                  ],
                );
                return wide
                    ? Row(
                        children: [
                          Expanded(flex: 7, child: canvas),
                          SizedBox(width: 360, child: editor),
                        ],
                      )
                    : Column(
                        children: [
                          Expanded(flex: 5, child: canvas),
                          Expanded(flex: 4, child: editor),
                        ],
                      );
              },
            ),
    );
  }
}
