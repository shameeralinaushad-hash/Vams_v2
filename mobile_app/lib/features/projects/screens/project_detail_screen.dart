import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../../../shared/widgets/status_chip.dart';

final projectDetailProvider = FutureProvider.family<Map<String, dynamic>?, int>((ref, projectId) async {
  final dio = ref.read(apiClientProvider);
  try {
    final response = await dio.get('/api/v1/projects/$projectId');
    if (response.data['success'] == true) {
      return response.data['project'];
    }
    return null;
  } catch (_) {
    return null;
  }
});

class ProjectDetailScreen extends ConsumerWidget {
  final int projectId;
  const ProjectDetailScreen({super.key, required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final projectAsync = ref.watch(projectDetailProvider(projectId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Project Detail'),
        actions: [
          IconButton(
            icon: const Icon(Icons.edit_outlined),
            onPressed: () {
              // TODO: implement edit project screen
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Edit project coming soon')),
              );
            },
          ),
        ],
      ),
      body: projectAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => const Center(child: Text('Failed to load project')),
        data: (project) {
          if (project == null) return const Center(child: Text('Project not found'));

          final tasks = (project['tasks'] as List? ?? []);
          final taskCounts = project['task_counts'] ?? {};
          final health = project['health'] ?? 'green';
          final healthColor = health == 'red' ? VamsTheme.danger
              : health == 'yellow' ? VamsTheme.warning
              : VamsTheme.success;

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            width: 12,
                            height: 12,
                            decoration: BoxDecoration(color: healthColor, shape: BoxShape.circle),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              project['title'] ?? '',
                              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                            ),
                          ),
                        ],
                      ),
                      if (project['description'] != null && (project['description'] as String).isNotEmpty) ...[
                        const SizedBox(height: 8),
                        Text(project['description'], style: const TextStyle(color: VamsTheme.textSecondary)),
                      ],
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          StatusChip(status: project['status'] ?? 'planning', color: VamsTheme.primary),
                          const Spacer(),
                          Text('${project['progress_pct'] ?? 0}%', style: const TextStyle(fontWeight: FontWeight.w600)),
                        ],
                      ),
                      const SizedBox(height: 8),
                      LinearProgressIndicator(
                        value: (project['progress_pct'] ?? 0) / 100,
                        backgroundColor: Colors.grey.shade200,
                        color: VamsTheme.primary,
                      ),
                      if (project['target_date'] != null) ...[
                        const SizedBox(height: 8),
                        Text(
                          'Deadline: ${project['target_date']}',
                          style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                        ),
                      ],
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 16),
              Row(
                children: [
                  _StatCard(label: 'To Do', count: taskCounts['to_do'] ?? 0, color: VamsTheme.textMuted),
                  const SizedBox(width: 8),
                  _StatCard(label: 'In Progress', count: taskCounts['in_progress'] ?? 0, color: VamsTheme.primary),
                  const SizedBox(width: 8),
                  _StatCard(label: 'Done', count: taskCounts['done'] ?? 0, color: VamsTheme.success),
                ],
              ),

              const SizedBox(height: 16),
              const Text('Tasks', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
              const SizedBox(height: 8),
              if (tasks.isEmpty)
                const Card(
                  child: Padding(
                    padding: EdgeInsets.all(16),
                    child: Center(child: Text('No tasks in this project')),
                  ),
                )
              else
                ...tasks.map((t) {
                  final assignee = t['assignee'];
                  final statusColor = t['status'] == 'done' ? VamsTheme.success
                      : t['status'] == 'in_progress' ? VamsTheme.primary
                      : VamsTheme.textMuted;
                  return Card(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: ListTile(
                      leading: StatusChip(status: t['status'] ?? '', color: statusColor),
                      title: Text(t['title'] ?? '', style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                      subtitle: assignee != null ? Text(assignee['name'] ?? '', style: const TextStyle(fontSize: 12)) : null,
                      trailing: t['due_date'] != null
                          ? Text(t['due_date'], style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted))
                          : null,
                    ),
                  );
                }),
            ],
          );
        },
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final int count;
  final Color color;

  const _StatCard({required this.label, required this.count, required this.color});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            children: [
              Text('$count', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700, color: color)),
              const SizedBox(height: 4),
              Text(label, style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
            ],
          ),
        ),
      ),
    );
  }
}
