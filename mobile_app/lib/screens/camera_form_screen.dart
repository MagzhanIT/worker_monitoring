import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/camera_model.dart';
import '../providers/camera_provider.dart';

class CameraFormScreen extends StatefulWidget {
  const CameraFormScreen({super.key, this.camera});
  final CameraModel? camera;

  @override
  State<CameraFormScreen> createState() => _CameraFormScreenState();
}

class _CameraFormScreenState extends State<CameraFormScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final TextEditingController _source;
  late final TextEditingController _width;
  late final TextEditingController _height;
  late String _kind;
  late int _rotation;
  late bool _enabled;
  late bool _mirror;
  late bool _loopVideo;
  bool _saving = false;
  String? _error;

  bool get _editing => widget.camera != null;

  @override
  void initState() {
    super.initState();
    final camera = widget.camera;
    _name = TextEditingController(text: camera?.name ?? '');
    _kind = _sourceKind(camera?.source);
    _source = TextEditingController(text: _editableSource(camera?.source));
    _width = TextEditingController(
      text: camera?.referenceWidth?.toString() ?? '',
    );
    _height = TextEditingController(
      text: camera?.referenceHeight?.toString() ?? '',
    );
    _rotation = camera?.rotation ?? 0;
    _enabled = camera?.enabled ?? true;
    _mirror = camera?.mirror ?? false;
    _loopVideo = _sourceOption(camera?.source, 'loop', true);
  }

  static String _sourceKind(String? source) {
    if (source?.startsWith('rtsp') == true) return 'rtsp';
    if (source?.startsWith('file:') == true) return 'file';
    if (source?.startsWith('demo:') == true) return 'demo';
    return 'webcam';
  }

  static String _editableSource(String? source) {
    if (source == null) return '0';
    if (source.startsWith('webcam://')) return source.substring(9);
    if (source == 'demo://sample') return '';
    if (source.startsWith('file:')) {
      return Uri.parse(source).replace(query: '').toString();
    }
    return source;
  }

  static bool _sourceOption(String? source, String name, bool fallback) {
    if (source == null) return fallback;
    final value = Uri.tryParse(source)?.queryParameters[name]?.toLowerCase();
    if (value == null) return fallback;
    return !{'0', 'false', 'no', 'off'}.contains(value);
  }

  String _buildSource() {
    final value = _source.text.trim();
    if (_kind == 'webcam') return 'webcam://$value';
    if (_kind == 'demo') {
      return 'demo://sample?loop=$_loopVideo&realtime=true';
    }
    var source = value;
    if (_kind == 'file' && !value.startsWith('file:')) {
      source = Uri.file(
        value,
        windows: RegExp(r'^[A-Za-z]:[\\/]').hasMatch(value),
      ).toString();
    }
    if (_kind == 'file') {
      return Uri.parse(source)
          .replace(
            queryParameters: {
              'loop': _loopVideo.toString(),
              'realtime': 'true',
            },
          )
          .toString();
    }
    return source;
  }

  String? _validateSource(String? raw) {
    final value = raw?.trim() ?? '';
    if (_kind == 'demo') return null;
    if (value.isEmpty) return 'This field is required';
    if (_kind == 'webcam' && int.tryParse(value) == null) {
      return 'Enter a device number, for example 0';
    }
    if (_kind == 'rtsp' &&
        !(value.startsWith('rtsp://') || value.startsWith('rtsps://'))) {
      return 'Enter a complete rtsp:// or rtsps:// URL';
    }
    if (_editing && value.contains('***')) {
      return 'Re-enter the complete source; hidden credentials cannot be saved';
    }
    return null;
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    final payload = <String, dynamic>{
      'name': _name.text.trim(),
      'source': _buildSource(),
      'enabled': _enabled,
      'reference_width': int.tryParse(_width.text.trim()),
      'reference_height': int.tryParse(_height.text.trim()),
      'rotation': _rotation,
      'mirror': _mirror,
    };
    try {
      final provider = context.read<CameraProvider>();
      if (_editing) {
        await provider.updateCamera(widget.camera!.id, payload);
      } else {
        await provider.createCamera(payload);
      }
      if (mounted) Navigator.pop(context, true);
    } catch (exception) {
      if (mounted) setState(() => _error = exception.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _source.dispose();
    _width.dispose();
    _height.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(_editing ? 'Edit camera' : 'Add camera')),
    body: Form(
      key: _formKey,
      child: ListView(
        padding: const EdgeInsets.all(22),
        children: [
          TextFormField(
            controller: _name,
            decoration: const InputDecoration(labelText: 'Camera name'),
            validator: (v) =>
                v == null || v.trim().isEmpty ? 'Enter a camera name' : null,
          ),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
            initialValue: _kind,
            decoration: const InputDecoration(labelText: 'Source type'),
            items: const [
              DropdownMenuItem(value: 'webcam', child: Text('Webcam')),
              DropdownMenuItem(value: 'rtsp', child: Text('RTSP camera')),
              DropdownMenuItem(value: 'file', child: Text('Local video file')),
              DropdownMenuItem(value: 'demo', child: Text('Built-in demo')),
            ],
            onChanged: (value) => setState(() {
              _kind = value!;
              if (_kind == 'demo') _source.clear();
            }),
          ),
          const SizedBox(height: 16),
          if (_kind != 'demo')
            TextFormField(
              controller: _source,
              decoration: InputDecoration(
                labelText: switch (_kind) {
                  'webcam' => 'Device number',
                  'file' => 'Video file path',
                  _ => 'RTSP URL',
                },
                hintText: switch (_kind) {
                  'webcam' => '0',
                  'file' => r'C:\Videos\camera.mp4',
                  _ => 'rtsp://user:password@host/stream',
                },
                helperText: _kind == 'rtsp'
                    ? 'Credentials are encrypted by the server and hidden after saving.'
                    : null,
              ),
              obscureText: _kind == 'rtsp',
              validator: _validateSource,
            ),
          const SizedBox(height: 20),
          Text(
            'Optional frame settings',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: TextFormField(
                  controller: _width,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Reference width',
                  ),
                  validator: _positiveOptional,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextFormField(
                  controller: _height,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Reference height',
                  ),
                  validator: _positiveOptional,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<int>(
            initialValue: _rotation,
            decoration: const InputDecoration(labelText: 'Rotation'),
            items: const [0, 90, 180, 270]
                .map((v) => DropdownMenuItem(value: v, child: Text('$v°')))
                .toList(),
            onChanged: (v) => setState(() => _rotation = v!),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Mirror image'),
            value: _mirror,
            onChanged: (v) => setState(() => _mirror = v),
          ),
          if (_kind == 'file' || _kind == 'demo')
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Loop video continuously'),
              subtitle: const Text(
                'Playback follows the video’s recorded speed.',
              ),
              value: _loopVideo,
              onChanged: (value) => setState(() => _loopVideo = value),
            ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Enabled'),
            value: _enabled,
            onChanged: (v) => setState(() => _enabled = v),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          const SizedBox(height: 20),
          FilledButton.icon(
            onPressed: _saving ? null : _save,
            icon: _saving
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.save_outlined),
            label: Text(_editing ? 'Save changes' : 'Add camera'),
          ),
        ],
      ),
    ),
  );

  static String? _positiveOptional(String? value) {
    if (value == null || value.trim().isEmpty) return null;
    final parsed = int.tryParse(value);
    return parsed == null || parsed <= 0 ? 'Enter a positive number' : null;
  }
}
