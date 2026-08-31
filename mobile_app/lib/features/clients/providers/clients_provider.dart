import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/client_models.dart';

class ClientsState {
  final List<ClientListItem> clients;
  final bool isLoading;
  final bool isLoadingMore;
  final String? error;
  final int currentPage;
  final int totalPages;
  final int total;
  final String searchQuery;
  final bool hasReachedEnd;

  ClientsState({
    this.clients = const [],
    this.isLoading = false,
    this.isLoadingMore = false,
    this.error,
    this.currentPage = 1,
    this.totalPages = 0,
    this.total = 0,
    this.searchQuery = '',
    this.hasReachedEnd = false,
  });

  ClientsState copyWith({
    List<ClientListItem>? clients,
    bool? isLoading,
    bool? isLoadingMore,
    String? error,
    int? currentPage,
    int? totalPages,
    int? total,
    String? searchQuery,
    bool? hasReachedEnd,
  }) {
    return ClientsState(
      clients: clients ?? this.clients,
      isLoading: isLoading ?? this.isLoading,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      error: error,
      currentPage: currentPage ?? this.currentPage,
      totalPages: totalPages ?? this.totalPages,
      total: total ?? this.total,
      searchQuery: searchQuery ?? this.searchQuery,
      hasReachedEnd: hasReachedEnd ?? this.hasReachedEnd,
    );
  }
}

class ClientsNotifier extends StateNotifier<ClientsState> {
  final Dio _dio;

  ClientsNotifier(this._dio) : super(ClientsState());

  Future<void> loadClients({bool refresh = false}) async {
    if (state.isLoading || state.isLoadingMore) return;

    final page = refresh ? 1 : state.currentPage + 1;

    if (refresh) {
      state = state.copyWith(isLoading: true, error: null, clients: []);
    } else {
      state = state.copyWith(isLoadingMore: true);
    }

    try {
      final response = await _dio.get(
        '/api/v1/clients',
        queryParameters: {
          'page': page,
          'per_page': 25,
          if (state.searchQuery.isNotEmpty) 'search': state.searchQuery,
        },
      );

      if (response.data['success'] == true) {
        final paginated = PaginatedClients.fromJson(response.data);
        final allClients = refresh
            ? paginated.clients
            : [...state.clients, ...paginated.clients];

        state = state.copyWith(
          clients: allClients,
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
          error: response.data['message'] ?? 'Failed to load clients.',
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
    await loadClients(refresh: true);
  }

  Future<ClientDetail?> getClientDetail(int clientId) async {
    try {
      final response = await _dio.get('/api/v1/clients/$clientId');
      if (response.data['success'] == true) {
        return ClientDetail.fromJson(response.data['client']);
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  Future<ClientDetail?> createClient(Map<String, dynamic> data) async {
    try {
      final response = await _dio.post('/api/v1/clients', data: data);
      if (response.data['success'] == true) {
        await loadClients(refresh: true);
        return ClientDetail.fromJson(response.data['client']);
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  Future<ClientDetail?> updateClient(int clientId, Map<String, dynamic> data) async {
    try {
      final response = await _dio.put('/api/v1/clients/$clientId', data: data);
      if (response.data['success'] == true) {
        return ClientDetail.fromJson(response.data['client']);
      }
      return null;
    } catch (e) {
      return null;
    }
  }
}

final clientsProvider = StateNotifierProvider<ClientsNotifier, ClientsState>((ref) {
  final dio = ref.watch(apiClientProvider);
  return ClientsNotifier(dio);
});

final clientDetailProvider = FutureProvider.family<ClientDetail?, int>((ref, clientId) async {
  final dio = ref.watch(apiClientProvider);
  try {
    final response = await dio.get('/api/v1/clients/$clientId');
    if (response.data['success'] == true) {
      return ClientDetail.fromJson(response.data['client']);
    }
    return null;
  } catch (e) {
    return null;
  }
});
