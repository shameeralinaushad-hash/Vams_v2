import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../features/auth/providers/auth_provider.dart';
import '../features/home/providers/dashboard_provider.dart';
import '../features/orders/providers/orders_provider.dart';
import '../features/clients/providers/clients_provider.dart';
import '../features/invoices/providers/invoices_provider.dart';
import 'sse_client.dart';

// Will be wired when notifications feature is created:
// import '../features/more/providers/notifications_provider.dart';
// final notificationsProvider = ...

final sseClientProvider = Provider<SseClient>((ref) {
  final client = SseClient();

  ref.listen<AuthState>(authProvider, (prev, next) {
    if (next is AuthAuthenticated) {
      client.start();
    } else if (next is AuthUnauthenticated || next is AuthInitial) {
      client.stop();
    }
  });

  ref.onDispose(() => client.stop());

  return client;
});

final sseListenerProvider = Provider<void>((ref) {
  final client = ref.watch(sseClientProvider);

  final sub = client.events.listen((event) {
    final eventType = event['event'] as String;
    final data = event['data'];

    if (eventType == 'refresh' && data is Map) {
      final section = data['section'] as String?;

      switch (section) {
        case 'dashboard':
          ref.invalidate(dashboardProvider);
          break;
        case 'orders':
          ref.invalidate(ordersProvider);
          ref.invalidate(dashboardProvider);
          break;
        case 'clients':
          ref.invalidate(clientsProvider);
          ref.invalidate(dashboardProvider);
          break;
        case 'invoices':
          ref.invalidate(invoicesProvider);
          ref.invalidate(dashboardProvider);
          break;
        default:
          ref.invalidate(dashboardProvider);
          ref.invalidate(ordersProvider);
          ref.invalidate(clientsProvider);
          ref.invalidate(invoicesProvider);
          break;
      }
    }

    if (eventType == 'notification') {
      // ref.invalidate(notificationsProvider);
      // TODO: Wire when notifications feature is created
    }
  });

  ref.onDispose(() => sub.cancel());
});
