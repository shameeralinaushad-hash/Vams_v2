import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/account_models.dart';

final expensesProvider =
    FutureProvider.family<List<ExpenseItem>, String>((ref, scope) async {
  final dio = ref.watch(apiClientProvider);
  final response = await dio.get('/api/v1/accounts/expenses', queryParameters: {'scope': scope});
  if (response.data['success'] == true) {
    return (response.data['expenses'] as List)
        .map((e) => ExpenseItem.fromJson(e))
        .toList();
  }
  return [];
});

final expenseCategoriesProvider = FutureProvider<List<ExpenseCategory>>((ref) async {
  final dio = ref.watch(apiClientProvider);
  final response = await dio.get('/api/v1/accounts/categories');
  if (response.data['success'] == true) {
    return (response.data['categories'] as List)
        .map((c) => ExpenseCategory.fromJson(c))
        .toList();
  }
  return [];
});

final budgetsProvider = FutureProvider<List<BudgetItem>>((ref) async {
  final dio = ref.watch(apiClientProvider);
  final response = await dio.get('/api/v1/accounts/budgets');
  if (response.data['success'] == true) {
    return (response.data['budgets'] as List)
        .map((b) => BudgetItem.fromJson(b))
        .toList();
  }
  return [];
});
