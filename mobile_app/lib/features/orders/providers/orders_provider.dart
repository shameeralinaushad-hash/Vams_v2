import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/order_models.dart';

class OrdersState {
  final List<OrderListItem> orders;
  final int total;
  final int pages;
  final int currentPage;
  final bool isLoading;
  final bool isLoadingMore;
  final String? error;
  final String search;
  final String? statusFilter;

  OrdersState({
    this.orders = const [],
    this.total = 0,
    this.pages = 0,
    this.currentPage = 1,
    this.isLoading = false,
    this.isLoadingMore = false,
    this.error,
    this.search = '',
    this.statusFilter,
  });

  OrdersState copyWith({
    List<OrderListItem>? orders,
    int? total,
    int? pages,
    int? currentPage,
    bool? isLoading,
    bool? isLoadingMore,
    String? error,
    String? search,
    String? statusFilter,
  }) {
    return OrdersState(
      orders: orders ?? this.orders,
      total: total ?? this.total,
      pages: pages ?? this.pages,
      currentPage: currentPage ?? this.currentPage,
      isLoading: isLoading ?? this.isLoading,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      error: error,
      search: search ?? this.search,
      statusFilter: statusFilter,
    );
  }
}

class OrdersNotifier extends StateNotifier<OrdersState> {
  final Dio _dio;

  OrdersNotifier(this._dio) : super(OrdersState()) {
    loadOrders(refresh: true);
  }

  Future<void> loadOrders({bool refresh = false, String? status, String? search}) async {
    if (state.isLoading || state.isLoadingMore) return;

    final page = refresh ? 1 : state.currentPage + 1;

    if (refresh) {
      state = state.copyWith(isLoading: true, error: null, orders: []);
    } else {
      state = state.copyWith(isLoadingMore: true);
    }

    try {
      final params = <String, dynamic>{
        'page': page,
        'per_page': 25,
      };
      if (status != null && status.isNotEmpty) params['status'] = status;
      if (search != null && search.isNotEmpty) params['search'] = search;

      final response = await _dio.get('/api/v1/orders', queryParameters: params);

      if (response.data['success'] == true) {
        final result = PaginatedOrders.fromJson(response.data);
        final allOrders = refresh ? result.orders : [...state.orders, ...result.orders];

        state = state.copyWith(
          orders: allOrders,
          total: result.total,
          pages: result.pages,
          currentPage: result.currentPage,
          isLoading: false,
          isLoadingMore: false,
          search: search ?? state.search,
          statusFilter: status,
        );
      } else {
        state = state.copyWith(isLoading: false, isLoadingMore: false, error: 'Failed to load orders.');
      }
    } on DioException catch (e) {
      String msg;
      if (e.type == DioExceptionType.connectionError) {
        msg = 'Cannot connect to server.';
      } else if (e.response?.data is Map && e.response?.data['message'] != null) {
        msg = e.response!.data['message'];
      } else {
        msg = 'Failed to load orders.';
      }
      state = state.copyWith(isLoading: false, isLoadingMore: false, error: msg);
    } catch (e) {
      debugPrint('Orders error: $e');
      state = state.copyWith(isLoading: false, isLoadingMore: false, error: 'Unexpected error.');
    }
  }

  Future<void> refreshOrders() async {
    await loadOrders(refresh: true, status: state.statusFilter, search: state.search.isNotEmpty ? state.search : null);
  }

  Future<void> searchOrders(String query) async {
    state = state.copyWith(search: query);
    await loadOrders(refresh: true, status: state.statusFilter, search: query);
  }

  Future<void> filterByStatus(String? status) async {
    await loadOrders(refresh: true, status: status, search: state.search.isNotEmpty ? state.search : null);
  }

  Future<void> loadMore() async {
    if (state.currentPage < state.pages) {
      await loadOrders(refresh: false, status: state.statusFilter, search: state.search.isNotEmpty ? state.search : null);
    }
  }
}

final ordersProvider = StateNotifierProvider<OrdersNotifier, OrdersState>((ref) {
  final dio = ref.watch(apiClientProvider);
  return OrdersNotifier(dio);
});

final orderDetailProvider = FutureProvider.family<OrderDetail?, int>((ref, orderId) async {
  final dio = ref.watch(apiClientProvider);
  try {
    final response = await dio.get('/api/v1/orders/$orderId');
    debugPrint('[ORDER_DETAIL] API response success=${response.data['success']}, order keys=${response.data['order']?.keys.toList()}');
    if (response.data['success'] == true) {
      final orderJson = response.data['order'] as Map<String, dynamic>;
      debugPrint('[ORDER_DETAIL] quotations=${orderJson['quotations']?.length ?? 0}, invoices=${orderJson['invoices']?.length ?? 0}, delivery_challans=${orderJson['delivery_challans']?.length ?? 0}');
      return OrderDetail.fromJson(orderJson);
    }
    return null;
  } catch (e) {
    debugPrint('Order detail error: $e');
    return null;
  }
});

Future<Map<String, dynamic>> editOrder(Dio dio, int orderId, {String? title, String? notes, String? status}) async {
  final data = <String, dynamic>{};
  if (title != null) data['title'] = title;
  if (notes != null) data['notes'] = notes;
  if (status != null) data['status'] = status;

  final response = await dio.put('/api/v1/orders/$orderId', data: data);
  return response.data as Map<String, dynamic>;
}

Future<Map<String, dynamic>> deleteOrder(Dio dio, int orderId) async {
  final response = await dio.delete('/api/v1/orders/$orderId');
  return response.data as Map<String, dynamic>;
}

Future<Map<String, dynamic>> changeOrderStatus(Dio dio, int orderId, String status) async {
  final response = await dio.post('/api/v1/orders/$orderId/status', data: {'status': status});
  return response.data as Map<String, dynamic>;
}
