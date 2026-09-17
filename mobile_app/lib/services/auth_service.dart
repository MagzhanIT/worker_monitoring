import 'package:shared_preferences/shared_preferences.dart';

import 'api_service.dart';

class AuthService {
  AuthService(this.api);
  final ApiService api;

  Future<String> login(String username, String password) async {
    final data =
        await api.post(
              '/auth/login',
              body: {'username': username, 'password': password},
            )
            as Map<String, dynamic>;
    final token = data['access_token'] as String;
    api.token = token;
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString('access_token', token);
    await preferences.setString('api_base_url', api.baseUrl);
    return token;
  }

  Future<String?> restore() async {
    final preferences = await SharedPreferences.getInstance();
    final token = preferences.getString('access_token');
    final baseUrl = preferences.getString('api_base_url');
    if (baseUrl != null) api.baseUrl = baseUrl;
    if (token == null) return null;
    api.token = token;
    try {
      await api.get('/auth/me');
      return token;
    } catch (_) {
      await logout();
      return null;
    }
  }

  Future<void> logout() async {
    api.token = null;
    final preferences = await SharedPreferences.getInstance();
    await preferences.remove('access_token');
  }
}
