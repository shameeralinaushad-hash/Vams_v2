import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';

final unreadCountProvider = FutureProvider<int>((ref) async {
  final dio = ref.watch(apiClientProvider);
  try {
    final response = await dio.get('/api/v1/notifications/unread-count');
    if (response.data['success'] == true) {
      return response.data['unread_count'] ?? 0;
    }
  } catch (_) {}
  return 0;
});
