import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../services/api_service.dart';

typedef CameraFrameLoader = Future<Uint8List> Function();

class CameraStream extends StatefulWidget {
  const CameraStream({
    super.key,
    required this.api,
    required this.cameraId,
    this.fit = BoxFit.contain,
    this.frameLoader,
    this.view = 'normal',
    this.refreshInterval = const Duration(milliseconds: 200),
  });
  final ApiService api;
  final int cameraId;
  final BoxFit fit;
  final CameraFrameLoader? frameLoader;
  final String view;
  final Duration refreshInterval;

  @override
  State<CameraStream> createState() => _CameraStreamState();
}

class _CameraStreamState extends State<CameraStream> {
  Timer? _nextFrame;
  Uint8List? _frame;
  Object? _lastError;
  bool _loading = false;
  int _consecutiveFailures = 0;

  @override
  void initState() {
    super.initState();
    _loadFrame();
  }

  @override
  void didUpdateWidget(covariant CameraStream oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.cameraId != widget.cameraId ||
        oldWidget.api != widget.api ||
        oldWidget.frameLoader != widget.frameLoader ||
        oldWidget.view != widget.view) {
      _nextFrame?.cancel();
      _frame = null;
      _lastError = null;
      _consecutiveFailures = 0;
      _loadFrame();
    }
  }

  Future<void> _loadFrame() async {
    if (_loading) return;
    _loading = true;
    var succeeded = false;
    try {
      final bytes =
          await (widget.frameLoader?.call() ??
              widget.api.download(
                '/cameras/${widget.cameraId}/frame.jpg?view=${widget.view}',
              ));
      if (bytes.isEmpty) throw StateError('The camera returned an empty frame');
      succeeded = true;
      _consecutiveFailures = 0;
      if (mounted) {
        setState(() {
          _frame = bytes;
          _lastError = null;
        });
      }
    } catch (error) {
      _consecutiveFailures += 1;
      if (mounted && (_frame == null || _consecutiveFailures >= 4)) {
        setState(() {
          _frame = null;
          _lastError = error;
        });
      }
    } finally {
      _loading = false;
      if (mounted) {
        _nextFrame = Timer(
          succeeded ? widget.refreshInterval : const Duration(seconds: 1),
          _loadFrame,
        );
      }
    }
  }

  @override
  void dispose() {
    _nextFrame?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final frame = _frame;
    return ColoredBox(
      color: const Color(0xFF12231F),
      child: frame != null
          ? Image.memory(
              frame,
              fit: widget.fit,
              gaplessPlayback: true,
              filterQuality: FilterQuality.low,
            )
          : Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (_lastError == null)
                    const CircularProgressIndicator(color: Colors.white70)
                  else
                    const Icon(
                      Icons.videocam_off_outlined,
                      color: Colors.white54,
                      size: 42,
                    ),
                  const SizedBox(height: 10),
                  Text(
                    _lastError == null
                        ? 'Waiting for live frame…'
                        : 'Live frame unavailable',
                    style: const TextStyle(color: Colors.white70),
                  ),
                ],
              ),
            ),
    );
  }
}
