import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/quotation_models.dart';

class QuotationsListState {
  final List<QuotationListItem> quotations;
  final bool isLoading;
  final bool isLoadingMore;
  final String? error;
  final int currentPage;
  final int totalPages;
  final int total;

  QuotationsListState({
    this.quotations = const [],
    this.isLoading = false,
    this.isLoadingMore = false,
    this.error,
    this.currentPage = 1,
    this.totalPages = 0,
    this.total = 0,
  });

  QuotationsListState copyWith({
    List<QuotationListItem>? quotations,
    bool? isLoading,
    bool? isLoadingMore,
    String? error,
    int? currentPage,
    int? totalPages,
    int? total,
  }) {
    return QuotationsListState(
      quotations: quotations ?? this.quotations,
      isLoading: isLoading ?? this.isLoading,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      error: error,
      currentPage: currentPage ?? this.currentPage,
      totalPages: totalPages ?? this.totalPages,
      total: total ?? this.total,
    );
  }
}

class QuotationsListNotifier extends StateNotifier<QuotationsListState> {
  final Dio _dio;

  QuotationsListNotifier(this._dio) : super(QuotationsListState()) {
    loadQuotations(refresh: true);
  }

  Future<void> loadQuotations({bool refresh = false}) async {
    if (state.isLoading || state.isLoadingMore) return;

    final page = refresh ? 1 : state.currentPage + 1;

    if (refresh) {
      state = state.copyWith(isLoading: true, error: null, quotations: []);
    } else {
      state = state.copyWith(isLoadingMore: true);
    }

    try {
      final response = await _dio.get('/api/v1/quotations', queryParameters: {
        'page': page,
        'per_page': 25,
      });

      if (response.data['success'] == true) {
        final list = (response.data['quotations'] as List? ?? [])
            .map((q) => QuotationListItem.fromJson(q))
            .toList();
        final all = refresh ? list : [...state.quotations, ...list];

        state = state.copyWith(
          quotations: all,
          currentPage: response.data['current_page'] ?? page,
          totalPages: response.data['pages'] ?? 1,
          total: response.data['total'] ?? 0,
          isLoading: false,
          isLoadingMore: false,
        );
      } else {
        state = state.copyWith(isLoading: false, isLoadingMore: false, error: 'Failed to load quotations.');
      }
    } on DioException catch (e) {
      String msg;
      if (e.type == DioExceptionType.connectionError) {
        msg = 'Cannot connect to server.';
      } else if (e.response?.data is Map && e.response?.data['message'] != null) {
        msg = e.response!.data['message'];
      } else {
        msg = 'Failed to load quotations.';
      }
      state = state.copyWith(isLoading: false, isLoadingMore: false, error: msg);
    } catch (e) {
      debugPrint('Quotations list error: $e');
      state = state.copyWith(isLoading: false, isLoadingMore: false, error: 'Unexpected error.');
    }
  }

  Future<void> loadMore() async {
    if (state.currentPage < state.totalPages) {
      await loadQuotations(refresh: false);
    }
  }
}

final quotationsListProvider = StateNotifierProvider<QuotationsListNotifier, QuotationsListState>((ref) {
  final dio = ref.watch(apiClientProvider);
  return QuotationsListNotifier(dio);
});
