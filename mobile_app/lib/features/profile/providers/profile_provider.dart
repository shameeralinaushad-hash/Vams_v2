import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../../hr/models/hr_models.dart';

final profileDashboardProvider = FutureProvider<ProfileDashboard>((ref) async {
  final dio = ref.watch(apiClientProvider);
  final response = await dio.get('/api/v1/auth/profile/dashboard');
  if (response.data['success'] == true) {
    return ProfileDashboard.fromJson(response.data);
  }
  throw Exception('Failed to load profile');
});
