import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/app_config.dart';

class WebSocketService {
  WebSocketChannel? _channel;
  StreamController<Map<String, dynamic>>? _controller;
  Timer? _retry;
  bool _closed = false;

  Stream<Map<String, dynamic>> connect({
    required String baseUrl,
    required int cameraId,
    required String token,
  }) {
    _closed = false;
    _controller ??= StreamController<Map<String, dynamic>>.broadcast();
    void open() {
      if (_closed) return;
      try {
        _channel = WebSocketChannel.connect(
          Uri.parse(AppConfig.websocketUrl(baseUrl, cameraId)),
        );
        _channel!.sink.add(jsonEncode({'type': 'auth', 'token': token}));
        _channel!.stream.listen(
          (message) {
            final value = jsonDecode(message.toString());
            if (value is Map<String, dynamic>) _controller?.add(value);
          },
          onError: (_) => retry(open),
          onDone: () => retry(open),
        );
      } catch (_) {
        retry(open);
      }
    }

    open();
    return _controller!.stream;
  }

  void retry(void Function() open) {
    if (_closed || _retry?.isActive == true) return;
    _retry = Timer(const Duration(seconds: 3), open);
  }

  Future<void> close() async {
    _closed = true;
    _retry?.cancel();
    await _channel?.sink.close();
    await _controller?.close();
    _controller = null;
  }
}
