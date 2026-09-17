import 'package:flutter/foundation.dart';

import '../models/camera_model.dart';
import '../models/event_model.dart';
import '../models/health_model.dart';
import '../models/live_person_model.dart';
import '../models/worker_model.dart';
import '../services/api_service.dart';

class CameraProvider extends ChangeNotifier {
  CameraProvider(this.api);
  final ApiService api;
  List<CameraModel> cameras = [];
  List<WorkerModel> workers = [];
  List<EventModel> events = [];
  final Map<int, HealthModel> health = {};
  final Map<int, List<LivePersonModel>> livePeople = {};
  final Map<int, int> activeWaitingCustomers = {};
  final Map<int, int> activeServiceSessions = {};
  bool loading = false;
  String? error;

  Future<void> refresh() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      final values = await Future.wait([
        api.get('/cameras'),
        api.get('/worker-sessions'),
        api.get('/events'),
      ]);
      cameras = (values[0] as List<dynamic>)
          .whereType<Map<String, dynamic>>()
          .map(CameraModel.fromJson)
          .toList();
      workers = (values[1] as List<dynamic>)
          .whereType<Map<String, dynamic>>()
          .map(WorkerModel.fromJson)
          .toList();
      events = (values[2] as List<dynamic>)
          .whereType<Map<String, dynamic>>()
          .map(EventModel.fromJson)
          .toList();
      for (final camera in cameras) {
        try {
          health[camera.id] = HealthModel.fromJson(
            await api.get('/cameras/${camera.id}/status')
                as Map<String, dynamic>,
          );
        } catch (_) {
          health[camera.id] = const HealthModel(
            status: 'UNAVAILABLE',
            cameraConnected: false,
            receivingFrames: false,
            processingFps: 0,
          );
        }
      }
    } catch (exception) {
      error = exception.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> cameraAction(int id, String action) async {
    await api.post('/cameras/$id/$action');
    if (action == 'stop' || action == 'restart') {
      livePeople[id] = [];
    }
    health[id] = HealthModel.fromJson(
      await api.get('/cameras/$id/status') as Map<String, dynamic>,
    );
    notifyListeners();
  }

  Future<void> createCamera(Map<String, dynamic> camera) async {
    await api.post('/cameras', body: camera);
    await refresh();
  }

  Future<void> updateCamera(int id, Map<String, dynamic> camera) async {
    await api.put('/cameras/$id', body: camera);
    await refresh();
  }

  Future<void> deleteCamera(int id) async {
    await api.delete('/cameras/$id');
    cameras.removeWhere((camera) => camera.id == id);
    health.remove(id);
    notifyListeners();
  }

  void applyLive(int cameraId, Map<String, dynamic> payload) {
    final value = payload['camera_health'];
    if (value is Map<String, dynamic>) {
      health[cameraId] = HealthModel.fromJson(value);
    }
    final people = payload['observed_people'];
    if (people is List<dynamic>) {
      livePeople[cameraId] = people
          .whereType<Map<String, dynamic>>()
          .map(LivePersonModel.fromJson)
          .toList();
    }
    activeWaitingCustomers[cameraId] =
        (payload['active_waiting_customers'] as num?)?.toInt() ?? 0;
    activeServiceSessions[cameraId] =
        (payload['active_service_sessions'] as num?)?.toInt() ?? 0;
    notifyListeners();
  }
}
