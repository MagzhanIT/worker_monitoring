import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/api_service.dart';

class SettingsProvider extends ChangeNotifier {
  SettingsProvider(this.api);
  final ApiService api;

  String get baseUrl => api.baseUrl;

  Future<void> setBaseUrl(String value) async {
    api.baseUrl = value.trim().replaceAll(RegExp(r'/$'), '');
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString('api_base_url', api.baseUrl);
    notifyListeners();
  }
}
