import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'storage.dart';

class SseClient {
  HttpClient? _client;
  bool _running = false;
  Timer? _reconnectTimer;

  final StreamController<Map<String, dynamic>> _eventController =
      StreamController<Map<String, dynamic>>.broadcast();

  Stream<Map<String, dynamic>> get events => _eventController.stream;
  bool get isRunning => _running;

  Future<void> start() async {
    if (_running) return;
    _running = true;
    _connect();
  }

  void stop() {
    _running = false;
    _reconnectTimer?.cancel();
    _client?.close(force: true);
    _client = null;
    _eventController.close();
  }

  Future<void> _connect() async {
    try {
      final serverUrl = await AppStorage.getServerUrl();
      final token = await AppStorage.getAccessToken();
      if (serverUrl == null || token == null) {
        _scheduleReconnect();
        return;
      }

      final uri = Uri.parse('$serverUrl/api/v1/events?token=$token');
      _client = HttpClient();
      _client!.connectionTimeout = const Duration(seconds: 10);

      final request = await _client!.getUrl(uri);
      request.headers.set('Authorization', 'Bearer $token');
      request.headers.set('User-Agent', 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36');
      request.headers.set('Accept', 'text/event-stream');
      request.headers.set('Cache-Control', 'no-cache');

      final response = await request.close().timeout(const Duration(seconds: 10));

      if (response.statusCode != 200) {
        debugPrint('SSE: Server returned ${response.statusCode}');
        _scheduleReconnect();
        return;
      }

      debugPrint('SSE: Connected');

      String eventType = '';
      String data = '';

      await for (final chunk in response.transform(utf8.decoder)) {
        final lines = chunk.split('\n');
        for (final line in lines) {
          if (line.startsWith('event:')) {
            eventType = line.substring(6).trim();
          } else if (line.startsWith('data:')) {
            data = line.substring(5).trim();
          } else if (line.trim().isEmpty && (eventType.isNotEmpty || data.isNotEmpty)) {
            // Empty line = end of event
            if (data.isNotEmpty) {
              try {
                final parsed = jsonDecode(data);
                _eventController.add({
                  'event': eventType.isNotEmpty ? eventType : 'message',
                  'data': parsed,
                });
              } catch (_) {
                _eventController.add({
                  'event': eventType.isNotEmpty ? eventType : 'message',
                  'data': data,
                });
              }
            }
            eventType = '';
            data = '';
          }
        }
      }
    } on TimeoutException {
      debugPrint('SSE: Connection timed out');
    } on SocketException catch (e) {
      debugPrint('SSE: Socket error: ${e.message}');
    } catch (e) {
      debugPrint('SSE: Error: $e');
    } finally {
      _client?.close(force: true);
      _client = null;
    }

    if (_running) _scheduleReconnect();
  }

  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), () {
      if (_running) _connect();
    });
  }
}
