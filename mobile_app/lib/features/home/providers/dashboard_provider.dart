import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/dashboard_models.dart';

class DashboardState {
  final DashboardData? data;
  final bool isLoading;
  final String? error;

  DashboardState({this.data, this.isLoading = false, this.error});

  DashboardState copyWith({DashboardData? data, bool? isLoading, String? error}) {
    return DashboardState(
      data: data ?? this.data,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

class DashboardNotifier extends StateNotifier<DashboardState> {
  final Dio _dio;

  DashboardNotifier(this._dio) : super(DashboardState());

  Future<void> loadDashboard() async {
    debugPrint('[DASHBOARD] loadDashboard() called');
    state = state.copyWith(isLoading: true, error: null);

    try {
      debugPrint('[DASHBOARD] GET /api/v1/dashboard');
      final response = await _dio.get('/api/v1/dashboard');
      debugPrint('[DASHBOARD] response status=${response.statusCode} success=${response.data['success']}');

      if (response.data['success'] == true) {
        final data = DashboardData.fromJson(response.data);
        debugPrint('[DASHBOARD] loaded: ${data.recentOrders.length} orders, ${data.importantActions.length} actions, ${data.todos.length} todos');
        state = state.copyWith(data: data, isLoading: false);
      } else {
        debugPrint('[DASHBOARD] failed: ${response.data['message']}');
        state = state.copyWith(
          isLoading: false,
          error: response.data['message'] ?? 'Failed to load dashboard.',
        );
      }
    } catch (e) {
      debugPrint('[DASHBOARD] error: $e');
      String msg;
      if (e is DioException) {
        if (e.response?.statusCode == 401) {
          msg = 'Session expired. Please log in again.';
        } else if (e.type == DioExceptionType.connectionError) {
          msg = 'Cannot connect to server.';
        } else {
          msg = 'Failed to load dashboard.';
        }
      } else {
        msg = 'Failed to load dashboard.';
      }
      state = state.copyWith(
        isLoading: false,
        error: msg,
      );
    }
  }

  Future<void> dismissAction(String source, {int? sourceId, double snoozeHours = 24}) async {
    try {
      await _dio.post('/api/v1/dashboard/actions/dismiss', data: {
        'source': source,
        'source_id': sourceId,
        'snooze_hours': snoozeHours,
      });
      // Reload dashboard to reflect dismissed action
      await loadDashboard();
    } catch (e) {
      debugPrint('[DASHBOARD] dismissAction error: $e');
    }
  }
}

final dashboardProvider = StateNotifierProvider<DashboardNotifier, DashboardState>((ref) {
  final dio = ref.watch(apiClientProvider);
  return DashboardNotifier(dio);
});
