import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/hr_models.dart';

final hrEmployeesProvider = FutureProvider<List<HrEmployee>>((ref) async {
  final dio = ref.watch(apiClientProvider);
  final response = await dio.get('/api/v1/hr/employees');
  if (response.data['success'] == true) {
    return (response.data['employees'] as List)
        .map((e) => HrEmployee.fromJson(e))
        .toList();
  }
  return [];
});

final attendanceTodayProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final dio = ref.watch(apiClientProvider);
  final response = await dio.get('/api/v1/hr/attendance/today');
  if (response.data['success'] == true) {
    return response.data;
  }
  return {};
});

final payrollProvider =
    FutureProvider.family<List<PayrollRecord>, Map<String, int>>((ref, params) async {
  final dio = ref.watch(apiClientProvider);
  final response = await dio.get('/api/v1/hr/payroll', queryParameters: params);
  if (response.data['success'] == true) {
    return (response.data['payroll'] as List)
        .map((p) => PayrollRecord.fromJson(p))
        .toList();
  }
  return [];
});

final holidaysProvider = FutureProvider<List<Holiday>>((ref) async {
  final dio = ref.watch(apiClientProvider);
  final response = await dio.get('/api/v1/hr/holidays');
  if (response.data['success'] == true) {
    return (response.data['holidays'] as List)
        .map((h) => Holiday.fromJson(h))
        .toList();
  }
  return [];
});
