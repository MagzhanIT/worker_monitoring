import 'package:flutter/foundation.dart';

import '../services/auth_service.dart';

class AuthProvider extends ChangeNotifier {
  AuthProvider(this.service);
  final AuthService service;
  bool loading = true;
  String? error;
  String? token;

  bool get authenticated => token != null;

  Future<void> restore() async {
    loading = true;
    notifyListeners();
    token = await service.restore();
    loading = false;
    notifyListeners();
  }

  Future<bool> login(String username, String password) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      token = await service.login(username, password);
      return true;
    } catch (exception) {
      error = exception.toString();
      return false;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    await service.logout();
    token = null;
    notifyListeners();
  }
}
