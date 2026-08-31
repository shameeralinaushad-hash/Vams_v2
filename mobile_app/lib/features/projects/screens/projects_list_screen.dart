import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';

final projectsListProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final dio = ref.read(apiClientProvider);
  final response = await dio.get('/api/v1/projects');
  if (response.data['success'] == true) {
    return List<Map<String, dynamic>>.from(response.data['projects']);
  }
  return [];
});

class ProjectsListScreen extends ConsumerWidget {
  const ProjectsListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final projectsAsync = ref.watch(projectsListProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Projects'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            onPressed: () async {
              await context.push('/more/projects/create');
              ref.invalidate(projectsListProvider);
            },
          ),
        ],
      ),
      body: projectsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (projects) {
          if (projects.isEmpty) {
            return const Center(child: Text('No projects found'));
          }
          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: projects.length,
            itemBuilder: (context, index) {
              final p = projects[index];
              final health = p['health'] ?? 'green';
              final healthColor = health == 'red' ? VamsTheme.danger
                  : health == 'yellow' ? VamsTheme.warning
                  : VamsTheme.success;
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  leading: Container(
                    width: 4,
                    height: 40,
                    decoration: BoxDecoration(
                      color: healthColor,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                  title: Text(p['title'] ?? '', style: const TextStyle(fontWeight: FontWeight.w600)),
                  subtitle: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(p['status'] ?? 'planning', style: const TextStyle(fontSize: 12)),
                      const SizedBox(height: 2),
                      LinearProgressIndicator(
                        value: (p['progress_pct'] ?? 0) / 100,
                        backgroundColor: Colors.grey.shade200,
                        color: VamsTheme.primary,
                      ),
                    ],
                  ),
                  trailing: Text('${p['progress_pct'] ?? 0}%', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                  onTap: () => context.push('/more/projects/${p['id']}'),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
