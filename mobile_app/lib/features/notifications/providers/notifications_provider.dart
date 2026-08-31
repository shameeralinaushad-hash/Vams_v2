import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../models/notification_models.dart';

class NotificationsState {
  final List<AppNotification> notifications;
  final bool isLoading;
  final bool isLoadingMore;
  final int unreadCount;
  final int totalPages;
  final int currentPage;
  final String? error;

  NotificationsState({
    this.notifications = const [],
    this.isLoading = false,
    this.isLoadingMore = false,
    this.unreadCount = 0,
    this.totalPages = 1,
    this.currentPage = 1,
    this.error,
  });

  NotificationsState copyWith({
    List<AppNotification>? notifications,
    bool? isLoading,
    bool? isLoadingMore,
    int? unreadCount,
    int? totalPages,
    int? currentPage,
    String? error,
  }) {
    return NotificationsState(
      notifications: notifications ?? this.notifications,
      isLoading: isLoading ?? this.isLoading,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      unreadCount: unreadCount ?? this.unreadCount,
      totalPages: totalPages ?? this.totalPages,
      currentPage: currentPage ?? this.currentPage,
      error: error,
    );
  }
}

class NotificationsNotifier extends StateNotifier<NotificationsState> {
  final Dio _dio;

  NotificationsNotifier(this._dio) : super(NotificationsState());

  Future<void> loadNotifications({bool refresh = false}) async {
    if (state.isLoading || state.isLoadingMore) return;

    final page = refresh ? 1 : state.currentPage + 1;

    if (refresh) {
      state = state.copyWith(isLoading: true, error: null, notifications: []);
    } else {
      state = state.copyWith(isLoadingMore: true);
    }

    try {
      final response = await _dio.get(
        '/api/v1/notifications',
        queryParameters: {'page': page, 'per_page': 25},
      );

      if (response.data['success'] == true) {
        final notifs = (response.data['notifications'] as List)
            .map((n) => AppNotification.fromJson(n))
            .toList();
        final allNotifs = refresh ? notifs : [...state.notifications, ...notifs];

        state = state.copyWith(
          notifications: allNotifs,
          unreadCount: response.data['unread_count'] ?? 0,
          totalPages: response.data['pages'] ?? 1,
          currentPage: response.data['current_page'] ?? page,
          isLoading: false,
          isLoadingMore: false,
        );
      } else {
        state = state.copyWith(
          isLoading: false,
          isLoadingMore: false,
          error: response.data['message'] ?? 'Failed to load notifications.',
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

  Future<void> markRead(int id) async {
    try {
      await _dio.post('/api/v1/notifications/$id/read');
      state = state.copyWith(
        notifications: state.notifications.map((n) {
          if (n.id == id) {
            return AppNotification(
              id: n.id,
              message: n.message,
              link: n.link,
              isRead: true,
              createdAt: n.createdAt,
            );
          }
          return n;
        }).toList(),
        unreadCount: state.unreadCount > 0 ? state.unreadCount - 1 : 0,
      );
    } catch (_) {}
  }

  Future<void> markAllRead() async {
    try {
      await _dio.post('/api/v1/notifications/read-all');
      state = state.copyWith(
        notifications: state.notifications
            .map((n) => AppNotification(
                  id: n.id,
                  message: n.message,
                  link: n.link,
                  isRead: true,
                  createdAt: n.createdAt,
                ))
            .toList(),
        unreadCount: 0,
      );
    } catch (_) {}
  }

  Future<void> clearAll() async {
    try {
      await _dio.post('/api/v1/notifications/clear-all');
      state = state.copyWith(notifications: [], unreadCount: 0);
    } catch (_) {}
  }
}

final notificationsProvider =
    StateNotifierProvider<NotificationsNotifier, NotificationsState>((ref) {
  final dio = ref.watch(apiClientProvider);
  return NotificationsNotifier(dio);
});
