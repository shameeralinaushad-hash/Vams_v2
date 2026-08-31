import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/company_models.dart';

final companiesProvider = FutureProvider<List<CompanyListItem>>((ref) async {
  final dio = ref.watch(apiClientProvider);
  final response = await dio.get('/api/v1/companies');
  if (response.data['success'] == true) {
    return (response.data['companies'] as List)
        .map((c) => CompanyListItem.fromJson(c))
        .toList();
  }
  return [];
});

final companiesListProvider = companiesProvider;

final companyDetailProvider = FutureProvider.family<CompanyDetail?, int>((ref, companyId) async {
  final dio = ref.watch(apiClientProvider);
  try {
    final response = await dio.get('/api/v1/companies/$companyId');
    if (response.data['success'] == true) {
      return CompanyDetail.fromJson(response.data['company']);
    }
    return null;
  } catch (e) {
    return null;
  }
});
