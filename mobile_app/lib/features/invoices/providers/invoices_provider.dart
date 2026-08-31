import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/invoice_models.dart';

class InvoicesState {
  final List<InvoiceListItem> invoices;
  final bool isLoading;
  final bool isLoadingMore;
  final String? error;
  final int currentPage;
  final int totalPages;
  final int total;
  final String searchQuery;
  final String? statusFilter;
  final bool hasReachedEnd;

  InvoicesState({
    this.invoices = const [],
    this.isLoading = false,
    this.isLoadingMore = false,
    this.error,
    this.currentPage = 1,
    this.totalPages = 0,
    this.total = 0,
    this.searchQuery = '',
    this.statusFilter,
    this.hasReachedEnd = false,
  });

  InvoicesState copyWith({
    List<InvoiceListItem>? invoices,
    bool? isLoading,
    bool? isLoadingMore,
    String? error,
    int? currentPage,
    int? totalPages,
    int? total,
    String? searchQuery,
    String? statusFilter,
    bool? hasReachedEnd,
  }) {
    return InvoicesState(
      invoices: invoices ?? this.invoices,
      isLoading: isLoading ?? this.isLoading,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      error: error,
      currentPage: currentPage ?? this.currentPage,
      totalPages: totalPages ?? this.totalPages,
      total: total ?? this.total,
      searchQuery: searchQuery ?? this.searchQuery,
      statusFilter: statusFilter,
      hasReachedEnd: hasReachedEnd ?? this.hasReachedEnd,
    );
  }
}

class InvoicesNotifier extends StateNotifier<InvoicesState> {
  final Dio _dio;

  InvoicesNotifier(this._dio) : super(InvoicesState());

  Future<void> loadInvoices({bool refresh = false}) async {
    if (state.isLoading || state.isLoadingMore) return;

    final page = refresh ? 1 : state.currentPage + 1;

    if (refresh) {
      state = state.copyWith(isLoading: true, error: null, invoices: []);
    } else {
      state = state.copyWith(isLoadingMore: true);
    }

    try {
      final response = await _dio.get(
        '/api/v1/invoices',
        queryParameters: {
          'page': page,
          'per_page': 25,
          if (state.searchQuery.isNotEmpty) 'search': state.searchQuery,
          if (state.statusFilter != null) 'status': state.statusFilter,
        },
      );

      if (response.data['success'] == true) {
        final paginated = PaginatedInvoices.fromJson(response.data);
        final allInvoices = refresh
            ? paginated.invoices
            : [...state.invoices, ...paginated.invoices];

        state = state.copyWith(
          invoices: allInvoices,
          currentPage: paginated.currentPage,
          totalPages: paginated.pages,
          total: paginated.total,
          isLoading: false,
          isLoadingMore: false,
          hasReachedEnd: paginated.currentPage >= paginated.pages,
        );
      } else {
        state = state.copyWith(
          isLoading: false,
          isLoadingMore: false,
          error: response.data['message'] ?? 'Failed to load invoices.',
        );
      }
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        isLoadingMore: false,
        error: 'Error: ${e.toString()}',
      );
    }
  }

  Future<void> search(String query) async {
    state = state.copyWith(searchQuery: query);
    await loadInvoices(refresh: true);
  }

  Future<void> filterByStatus(String? status) async {
    state = state.copyWith(statusFilter: status);
    await loadInvoices(refresh: true);
  }

  Future<InvoiceDetail?> getInvoiceDetail(int invoiceId) async {
    try {
      final response = await _dio.get('/api/v1/invoices/$invoiceId');
      if (response.data['success'] == true) {
        return InvoiceDetail.fromJson(response.data['invoice']);
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  Future<Map<String, dynamic>?> addPayment(int invoiceId, Map<String, dynamic> data) async {
    try {
      final response = await _dio.post('/api/v1/invoices/$invoiceId/payments', data: data);
      if (response.data['success'] == true) {
        return response.data;
      }
      return null;
    } catch (e) {
      return null;
    }
  }
}

final invoicesProvider = StateNotifierProvider<InvoicesNotifier, InvoicesState>((ref) {
  final dio = ref.watch(apiClientProvider);
  return InvoicesNotifier(dio);
});

final invoiceDetailProvider = FutureProvider.family<InvoiceDetail?, int>((ref, invoiceId) async {
  final dio = ref.watch(apiClientProvider);
  try {
    final response = await dio.get('/api/v1/invoices/$invoiceId');
    if (response.data['success'] == true) {
      return InvoiceDetail.fromJson(response.data['invoice']);
    }
    return null;
  } catch (e) {
    return null;
  }
});
