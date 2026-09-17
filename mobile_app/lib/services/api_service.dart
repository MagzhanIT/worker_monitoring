import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;
  @override
  String toString() => message;
}

class ApiService {
  ApiService({required this.baseUrl, this.token});
  String baseUrl;
  String? token;

  Map<String, String> get headers => {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    if (token != null) 'Authorization': 'Bearer $token',
  };

  Uri uri(String path, [Map<String, String>? query]) => Uri.parse(
    '${baseUrl.replaceAll(RegExp(r'/$'), '')}$path',
  ).replace(queryParameters: query);

  Future<dynamic> get(String path, {Map<String, String>? query}) async =>
      _decode(await http.get(uri(path, query), headers: headers));

  Future<dynamic> post(String path, {Object? body}) async => _decode(
    await http.post(
      uri(path),
      headers: headers,
      body: body == null ? null : jsonEncode(body),
    ),
  );

  Future<dynamic> put(String path, {Object? body}) async => _decode(
    await http.put(
      uri(path),
      headers: headers,
      body: body == null ? null : jsonEncode(body),
    ),
  );

  Future<void> delete(String path) async =>
      _decode(await http.delete(uri(path), headers: headers));

  Future<Uint8List> download(String path) async {
    final response = await http.get(uri(path), headers: headers);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(
        'Download failed (${response.statusCode})',
        statusCode: response.statusCode,
      );
    }
    return response.bodyBytes;
  }

  dynamic _decode(http.Response response) {
    dynamic body;
    if (response.body.isNotEmpty) {
      try {
        body = jsonDecode(response.body);
      } catch (_) {
        body = response.body;
      }
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final message = body is Map
          ? body['detail']?.toString()
          : body?.toString();
      throw ApiException(
        message ?? 'Request failed (${response.statusCode})',
        statusCode: response.statusCode,
      );
    }
    return body;
  }
}
