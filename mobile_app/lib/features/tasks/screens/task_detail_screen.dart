import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../../../shared/widgets/status_chip.dart';

final taskDetailProvider = FutureProvider.family<Map<String, dynamic>?, int>((ref, taskId) async {
  final dio = ref.read(apiClientProvider);
  try {
    final response = await dio.get('/api/v1/tasks/team/$taskId');
    if (response.data['success'] == true) {
      return response.data['task'];
    }
    return null;
  } catch (_) {
    return null;
  }
});

class TaskDetailScreen extends ConsumerStatefulWidget {
  final int taskId;
  const TaskDetailScreen({super.key, required this.taskId});

  @override
  ConsumerState<TaskDetailScreen> createState() => _TaskDetailScreenState();
}

class _TaskDetailScreenState extends ConsumerState<TaskDetailScreen> {
  final _commentCtrl = TextEditingController();
  final _subtaskCtrl = TextEditingController();

  @override
  void dispose() {
    _commentCtrl.dispose();
    _subtaskCtrl.dispose();
    super.dispose();
  }

  Future<void> _addSubtask() async {
    if (_subtaskCtrl.text.trim().isEmpty) return;
    try {
      final dio = ref.read(apiClientProvider);
      await dio.post('/api/v1/tasks/team/${widget.taskId}/subtask', data: {
        'title': _subtaskCtrl.text.trim(),
      });
      _subtaskCtrl.clear();
      ref.invalidate(taskDetailProvider(widget.taskId));
    } on DioException {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Failed to add subtask')));
      }
    }
  }

  Future<void> _toggleSubtask(int subtaskId) async {
    try {
      final dio = ref.read(apiClientProvider);
      await dio.post('/api/v1/tasks/subtask/$subtaskId/toggle');
      ref.invalidate(taskDetailProvider(widget.taskId));
    } on DioException {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Failed to update')));
      }
    }
  }

  Future<void> _addComment() async {
    if (_commentCtrl.text.trim().isEmpty) return;
    try {
      final dio = ref.read(apiClientProvider);
      await dio.post('/api/v1/tasks/team/${widget.taskId}/comments', data: {
        'body': _commentCtrl.text.trim(),
      });
      _commentCtrl.clear();
      ref.invalidate(taskDetailProvider(widget.taskId));
    } on DioException {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Failed to add comment')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final taskAsync = ref.watch(taskDetailProvider(widget.taskId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Task Detail'),
        actions: [
          IconButton(
            icon: const Icon(Icons.edit_outlined),
            onPressed: () => context.push('/more/tasks/${widget.taskId}/edit'),
          ),
        ],
      ),
      body: taskAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => const Center(child: Text('Failed to load task')),
        data: (task) {
          if (task == null) return const Center(child: Text('Task not found'));

          final subItems = (task['sub_items'] as List? ?? []);
          final comments = (task['comments'] as List? ?? []);

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(task['title'] ?? '', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                      if (task['description'] != null && (task['description'] as String).isNotEmpty) ...[
                        const SizedBox(height: 8),
                        Text(task['description'], style: const TextStyle(color: VamsTheme.textSecondary)),
                      ],
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          StatusChip(status: task['status'] ?? '', color: VamsTheme.primary),
                          const SizedBox(width: 8),
                          StatusChip(status: task['priority'] ?? '', color: VamsTheme.warning),
                          const Spacer(),
                          if (task['due_date'] != null)
                            Text(task['due_date'], style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
                        ],
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 16),
              Row(
                children: [
                  const Icon(Icons.checklist, size: 20, color: VamsTheme.primary),
                  const SizedBox(width: 8),
                  Text('Subtasks (${subItems.length})', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                ],
              ),
              const SizedBox(height: 8),
              ...subItems.map((s) => Card(
                margin: const EdgeInsets.only(bottom: 4),
                child: CheckboxListTile(
                  value: s['is_done'] ?? false,
                  onChanged: (_) => _toggleSubtask(s['id']),
                  title: Text(
                    s['title'] ?? '',
                    style: TextStyle(
                      decoration: (s['is_done'] ?? false) ? TextDecoration.lineThrough : null,
                    ),
                  ),
                  dense: true,
                ),
              )),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _subtaskCtrl,
                      decoration: InputDecoration(
                        hintText: 'Add subtask...',
                        isDense: true,
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                      onSubmitted: (_) => _addSubtask(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton(
                    onPressed: _addSubtask,
                    icon: const Icon(Icons.add_circle, color: VamsTheme.primary),
                  ),
                ],
              ),

              const SizedBox(height: 24),
              Row(
                children: [
                  const Icon(Icons.comment_outlined, size: 20, color: VamsTheme.primary),
                  const SizedBox(width: 8),
                  Text('Discussion (${comments.length})', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                ],
              ),
              const SizedBox(height: 8),
              ...comments.map((c) => Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(c['body'] ?? '', style: const TextStyle(fontSize: 14)),
                      const SizedBox(height: 4),
                      Text(
                        _formatTime(c['created_at']),
                        style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted),
                      ),
                    ],
                  ),
                ),
              )),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _commentCtrl,
                      decoration: InputDecoration(
                        hintText: 'Add comment...',
                        isDense: true,
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                      onSubmitted: (_) => _addComment(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton(
                    onPressed: _addComment,
                    icon: const Icon(Icons.send, color: VamsTheme.primary),
                  ),
                ],
              ),
            ],
          );
        },
      ),
    );
  }

  String _formatTime(String? isoString) {
    if (isoString == null || isoString.isEmpty) return '';
    try {
      final dt = DateTime.parse(isoString);
      final now = DateTime.now();
      final diff = now.difference(dt);
      if (diff.inMinutes < 1) return 'Just now';
      if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
      if (diff.inHours < 24) return '${diff.inHours}h ago';
      if (diff.inDays < 7) return '${diff.inDays}d ago';
      return '${dt.day}/${dt.month}/${dt.year}';
    } catch (_) {
      return isoString;
    }
  }
}
