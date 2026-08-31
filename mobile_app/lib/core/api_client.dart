import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'storage.dart';

class ApiClient {
  static Dio? _dio;
  static bool _isRefreshing = false;
  static VoidCallback? onAuthExpired;

  static Dio get instance {
    _dio ??= _createDio();
    return _dio!;
  }

  static Dio _createDio() {
    final dio = Dio(BaseOptions(
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 15),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
      },
    ));

    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final serverUrl = await AppStorage.getServerUrl();
        if (serverUrl != null) {
          options.baseUrl = serverUrl;
        }

        final token = await AppStorage.getAccessToken();
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        debugPrint('[DIO] → ${options.method} ${options.uri}');
        handler.next(options);
      },
      onError: (error, handler) async {
        debugPrint('[DIO] ← ${error.requestOptions.method} ${error.requestOptions.uri} → ${error.response?.statusCode}');
        if (error.response?.statusCode == 401 && !_isRefreshing) {
          _isRefreshing = true;
          try {
            final refreshed = await _refreshToken();
            if (refreshed) {
              final retryReq = error.requestOptions;
              final newToken = await AppStorage.getAccessToken();
              if (newToken != null) {
                retryReq.headers['Authorization'] = 'Bearer $newToken';
              }
              try {
                final response = await dio.fetch(retryReq);
                return handler.resolve(response);
              } catch (e) {
                return handler.next(error);
              }
            } else {
              await AppStorage.clearAuth();
              onAuthExpired?.call();
            }
          } finally {
            _isRefreshing = false;
          }
        }
        handler.next(error);
      },
    ));

    return dio;
  }

  static Future<bool> _refreshToken() async {
    try {
      final refreshToken = await AppStorage.getRefreshToken();
      final serverUrl = await AppStorage.getServerUrl();
      if (refreshToken == null || serverUrl == null) return false;

      final refreshDio = Dio(BaseOptions(
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $refreshToken',
          'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
        },
      ));
      final response = await refreshDio.post(
        '$serverUrl/api/v1/auth/refresh',
      );

      if (response.statusCode == 200 && response.data['success'] == true) {
        await AppStorage.setAccessToken(response.data['access_token']);
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('Token refresh failed: $e');
      return false;
    }
  }

  static void reset() {
    _dio = null;
    _isRefreshing = false;
  }
}

final apiClientProvider = Provider<Dio>((ref) {
  return ApiClient.instance;
});
