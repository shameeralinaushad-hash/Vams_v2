import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';

final auditLogProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final dio = ref.read(apiClientProvider);
  try {
    final response = await dio.get('/api/v1/audit-logs');
    if (response.data['success'] == true) {
      return List<Map<String, dynamic>>.from(response.data['logs'] ?? []);
    }
    return [];
  } catch (_) {
    return [];
  }
});

class AuditLogScreen extends ConsumerWidget {
  const AuditLogScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final logsAsync = ref.watch(auditLogProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Audit Log')),
      body: logsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => const Center(child: Text('Failed to load audit log')),
        data: (logs) {
          if (logs.isEmpty) {
            return const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.history, size: 48, color: VamsTheme.textMuted),
                  SizedBox(height: 12),
                  Text('No audit log entries'),
                ],
              ),
            );
          }

          return ListView.builder(
            itemCount: logs.length,
            itemBuilder: (context, i) {
              final log = logs[i];
              final action = log['action'] ?? '';
              final entityType = log['entity_type'] ?? '';
              final details = log['details'] ?? '';
              final timestamp = log['created_at'] ?? '';

              IconData icon;
              Color color;
              switch (action) {
                case 'create':
                  icon = Icons.add_circle_outline;
                  color = VamsTheme.success;
                  break;
                case 'update':
                  icon = Icons.edit_outlined;
                  color = VamsTheme.primary;
                  break;
                case 'delete':
                  icon = Icons.delete_outline;
                  color = VamsTheme.danger;
                  break;
                case 'login':
                  icon = Icons.login;
                  color = VamsTheme.primary;
                  break;
                default:
                  icon = Icons.circle;
                  color = VamsTheme.textMuted;
              }

              return ListTile(
                leading: Icon(icon, size: 20, color: color),
                title: Text(
                  '$action $entityType',
                  style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                ),
                subtitle: details != null && details.toString().isNotEmpty
                    ? Text(details, style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted), maxLines: 2, overflow: TextOverflow.ellipsis)
                    : null,
                trailing: Text(timestamp, style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted)),
              );
            },
          );
        },
      ),
    );
  }
}
