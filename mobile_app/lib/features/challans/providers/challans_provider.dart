import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/challan_models.dart';

class ChallansListState {
  final List<ChallanListItem> challans;
  final bool isLoading;
  final bool isLoadingMore;
  final String? error;
  final int currentPage;
  final int totalPages;
  final int total;

  ChallansListState({
    this.challans = const [],
    this.isLoading = false,
    this.isLoadingMore = false,
    this.error,
    this.currentPage = 1,
    this.totalPages = 0,
    this.total = 0,
  });

  ChallansListState copyWith({
    List<ChallanListItem>? challans,
    bool? isLoading,
    bool? isLoadingMore,
    String? error,
    int? currentPage,
    int? totalPages,
    int? total,
  }) {
    return ChallansListState(
      challans: challans ?? this.challans,
      isLoading: isLoading ?? this.isLoading,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      error: error,
      currentPage: currentPage ?? this.currentPage,
      totalPages: totalPages ?? this.totalPages,
      total: total ?? this.total,
    );
  }
}

class ChallansListNotifier extends StateNotifier<ChallansListState> {
  final Dio _dio;

  ChallansListNotifier(this._dio) : super(ChallansListState()) {
    loadChallans(refresh: true);
  }

  Future<void> loadChallans({bool refresh = false}) async {
    if (state.isLoading || state.isLoadingMore) return;

    final page = refresh ? 1 : state.currentPage + 1;

    if (refresh) {
      state = state.copyWith(isLoading: true, error: null, challans: []);
    } else {
      state = state.copyWith(isLoadingMore: true);
    }

    try {
      final response = await _dio.get('/api/v1/challans', queryParameters: {
        'page': page,
        'per_page': 25,
      });

      if (response.data['success'] == true) {
        final list = (response.data['challans'] as List? ?? [])
            .map((c) => ChallanListItem.fromJson(c))
            .toList();
        final all = refresh ? list : [...state.challans, ...list];

        state = state.copyWith(
          challans: all,
          currentPage: response.data['current_page'] ?? page,
          totalPages: response.data['pages'] ?? 1,
          total: response.data['total'] ?? 0,
          isLoading: false,
          isLoadingMore: false,
        );
      } else {
        state = state.copyWith(isLoading: false, isLoadingMore: false, error: 'Failed to load challans.');
      }
    } on DioException catch (e) {
      String msg;
      if (e.type == DioExceptionType.connectionError) {
        msg = 'Cannot connect to server.';
      } else if (e.response?.data is Map && e.response?.data['message'] != null) {
        msg = e.response!.data['message'];
      } else {
        msg = 'Failed to load challans.';
      }
      state = state.copyWith(isLoading: false, isLoadingMore: false, error: msg);
    } catch (e) {
      debugPrint('Challans list error: $e');
      state = state.copyWith(isLoading: false, isLoadingMore: false, error: 'Unexpected error.');
    }
  }

  Future<void> loadMore() async {
    if (state.currentPage < state.totalPages) {
      await loadChallans(refresh: false);
    }
  }
}

final challansListProvider = StateNotifierProvider<ChallansListNotifier, ChallansListState>((ref) {
  final dio = ref.watch(apiClientProvider);
  return ChallansListNotifier(dio);
});
