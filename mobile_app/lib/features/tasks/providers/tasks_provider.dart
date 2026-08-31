import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/task_models.dart';

class TeamTasksState {
  final List<TeamTask> tasks;
  final bool isLoading;
  final bool isLoadingMore;
  final String? error;
  final int currentPage;
  final int totalPages;
  final int total;
  final String? statusFilter;

  TeamTasksState({
    this.tasks = const [],
    this.isLoading = false,
    this.isLoadingMore = false,
    this.error,
    this.currentPage = 1,
    this.totalPages = 0,
    this.total = 0,
    this.statusFilter,
  });

  TeamTasksState copyWith({
    List<TeamTask>? tasks,
    bool? isLoading,
    bool? isLoadingMore,
    String? error,
    int? currentPage,
    int? totalPages,
    int? total,
    String? statusFilter,
  }) {
    return TeamTasksState(
      tasks: tasks ?? this.tasks,
      isLoading: isLoading ?? this.isLoading,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      error: error,
      currentPage: currentPage ?? this.currentPage,
      totalPages: totalPages ?? this.totalPages,
      total: total ?? this.total,
      statusFilter: statusFilter,
    );
  }
}

class TeamTasksNotifier extends StateNotifier<TeamTasksState> {
  final Dio _dio;

  TeamTasksNotifier(this._dio) : super(TeamTasksState());

  Future<void> loadTasks({bool refresh = false, String? status}) async {
    if (state.isLoading || state.isLoadingMore) return;

    final page = refresh ? 1 : state.currentPage + 1;

    if (refresh) {
      state = state.copyWith(isLoading: true, error: null, tasks: []);
    } else {
      state = state.copyWith(isLoadingMore: true);
    }

    try {
      final params = <String, dynamic>{
        'page': page,
        'per_page': 25,
      };
      if (status != null && status.isNotEmpty) params['status'] = status;

      final response = await _dio.get('/api/v1/tasks/team', queryParameters: params);

      if (response.data['success'] == true) {
        final taskList = (response.data['tasks'] as List? ?? [])
            .map((t) => TeamTask.fromJson(t))
            .toList();
        final allTasks = refresh ? taskList : [...state.tasks, ...taskList];

        state = state.copyWith(
          tasks: allTasks,
          currentPage: response.data['current_page'] ?? page,
          totalPages: response.data['pages'] ?? 1,
          total: response.data['total'] ?? 0,
          isLoading: false,
          isLoadingMore: false,
          statusFilter: status,
        );
      } else {
        state = state.copyWith(
          isLoading: false,
          isLoadingMore: false,
          error: response.data['message'] ?? 'Failed to load tasks.',
        );
      }
    } on DioException catch (e) {
      String msg;
      if (e.type == DioExceptionType.connectionError) {
        msg = 'Cannot connect to server.';
      } else if (e.response?.data is Map && e.response?.data['message'] != null) {
        msg = e.response!.data['message'];
      } else {
        msg = 'Failed to load tasks.';
      }
      state = state.copyWith(isLoading: false, isLoadingMore: false, error: msg);
    } catch (e) {
      debugPrint('Team tasks error: $e');
      state = state.copyWith(isLoading: false, isLoadingMore: false, error: 'Unexpected error.');
    }
  }

  Future<void> filterByStatus(String? status) async {
    await loadTasks(refresh: true, status: status);
  }
}

final teamTasksProvider = StateNotifierProvider<TeamTasksNotifier, TeamTasksState>((ref) {
  final dio = ref.watch(apiClientProvider);
  return TeamTasksNotifier(dio);
});

class PersonalItemsState {
  final List<PersonalItem> items;
  final bool isLoading;
  final bool isLoadingMore;
  final String? error;
  final int currentPage;
  final int totalPages;
  final int total;
  final String? laneFilter;

  PersonalItemsState({
    this.items = const [],
    this.isLoading = false,
    this.isLoadingMore = false,
    this.error,
    this.currentPage = 1,
    this.totalPages = 0,
    this.total = 0,
    this.laneFilter,
  });

  PersonalItemsState copyWith({
    List<PersonalItem>? items,
    bool? isLoading,
    bool? isLoadingMore,
    String? error,
    int? currentPage,
    int? totalPages,
    int? total,
    String? laneFilter,
  }) {
    return PersonalItemsState(
      items: items ?? this.items,
      isLoading: isLoading ?? this.isLoading,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      error: error,
      currentPage: currentPage ?? this.currentPage,
      totalPages: totalPages ?? this.totalPages,
      total: total ?? this.total,
      laneFilter: laneFilter,
    );
  }
}

class PersonalItemsNotifier extends StateNotifier<PersonalItemsState> {
  final Dio _dio;

  PersonalItemsNotifier(this._dio) : super(PersonalItemsState());

  Future<void> loadItems({bool refresh = false, String? lane}) async {
    if (state.isLoading || state.isLoadingMore) return;

    final page = refresh ? 1 : state.currentPage + 1;

    if (refresh) {
      state = state.copyWith(isLoading: true, error: null, items: []);
    } else {
      state = state.copyWith(isLoadingMore: true);
    }

    try {
      final params = <String, dynamic>{
        'page': page,
        'per_page': 25,
      };
      if (lane != null && lane.isNotEmpty) params['lane'] = lane;

      final response = await _dio.get('/api/v1/tasks/personal', queryParameters: params);

      if (response.data['success'] == true) {
        final itemList = (response.data['items'] as List? ?? [])
            .map((i) => PersonalItem.fromJson(i))
            .toList();
        final allItems = refresh ? itemList : [...state.items, ...itemList];

        state = state.copyWith(
          items: allItems,
          currentPage: response.data['current_page'] ?? page,
          totalPages: response.data['pages'] ?? 1,
          total: response.data['total'] ?? 0,
          isLoading: false,
          isLoadingMore: false,
          laneFilter: lane,
        );
      } else {
        state = state.copyWith(
          isLoading: false,
          isLoadingMore: false,
          error: response.data['message'] ?? 'Failed to load personal items.',
        );
      }
    } on DioException catch (e) {
      String msg;
      if (e.type == DioExceptionType.connectionError) {
        msg = 'Cannot connect to server.';
      } else if (e.response?.data is Map && e.response?.data['message'] != null) {
        msg = e.response!.data['message'];
      } else {
        msg = 'Failed to load personal items.';
      }
      state = state.copyWith(isLoading: false, isLoadingMore: false, error: msg);
    } catch (e) {
      debugPrint('Personal items error: $e');
      state = state.copyWith(isLoading: false, isLoadingMore: false, error: 'Unexpected error.');
    }
  }

  Future<void> filterByLane(String? lane) async {
    await loadItems(refresh: true, lane: lane);
  }

  Future<PersonalItem?> createItem(Map<String, dynamic> data) async {
    try {
      final response = await _dio.post('/api/v1/tasks/personal', data: data);
      if (response.data['success'] == true) {
        await loadItems(refresh: true, lane: state.laneFilter);
        return PersonalItem.fromJson(response.data['item']);
      }
      return null;
    } catch (e) {
      return null;
    }
  }
}

final personalItemsProvider = StateNotifierProvider<PersonalItemsNotifier, PersonalItemsState>((ref) {
  final dio = ref.watch(apiClientProvider);
  return PersonalItemsNotifier(dio);
});

final taskDetailProvider = FutureProvider.family<TaskDetail?, int>((ref, taskId) async {
  final dio = ref.watch(apiClientProvider);
  try {
    final response = await dio.get('/api/v1/tasks/team/$taskId');
    if (response.data['success'] == true) {
      return TaskDetail.fromJson(response.data['task']);
    }
    return null;
  } catch (e) {
    debugPrint('Task detail error: $e');
    return null;
  }
});

Future<Map<String, dynamic>> createTeamTask(Dio dio, {
  required String title,
  required int assigneeId,
  String? description,
  String? priority,
  String? dueDate,
  int? orderId,
}) async {
  final data = <String, dynamic>{
    'title': title,
    'assignee_id': assigneeId,
  };
  if (description != null && description.isNotEmpty) data['description'] = description;
  if (priority != null) data['priority'] = priority;
  if (dueDate != null) data['due_date'] = dueDate;
  if (orderId != null) data['order_id'] = orderId;

  final response = await dio.post('/api/v1/tasks/team', data: data);
  return response.data as Map<String, dynamic>;
}
