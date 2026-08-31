import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';

final todosListProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final dio = ref.read(apiClientProvider);
  final response = await dio.get('/api/v1/todos');
  if (response.data['success'] == true) {
    return List<Map<String, dynamic>>.from(response.data['todos']);
  }
  return [];
});

class TodosScreen extends ConsumerStatefulWidget {
  const TodosScreen({super.key});

  @override
  ConsumerState<TodosScreen> createState() => _TodosScreenState();
}

class _TodosScreenState extends ConsumerState<TodosScreen> {
  final _titleCtrl = TextEditingController();

  @override
  void dispose() {
    _titleCtrl.dispose();
    super.dispose();
  }

  Future<void> _addTodo() async {
    if (_titleCtrl.text.trim().isEmpty) return;
    try {
      final dio = ref.read(apiClientProvider);
      await dio.post('/api/v1/todos', data: {
        'title': _titleCtrl.text.trim(),
        'priority': 'medium',
      });
      _titleCtrl.clear();
      ref.invalidate(todosListProvider);
    } on DioException {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Failed to add todo')));
      }
    }
  }

  Future<void> _toggleTodo(int id) async {
    try {
      final dio = ref.read(apiClientProvider);
      await dio.post('/api/v1/todos/$id/toggle');
      ref.invalidate(todosListProvider);
    } on DioException {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Failed to update')));
      }
    }
  }

  Future<void> _deleteTodo(int id) async {
    try {
      final dio = ref.read(apiClientProvider);
      await dio.delete('/api/v1/todos/$id');
      ref.invalidate(todosListProvider);
    } on DioException {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Failed to delete')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final todosAsync = ref.watch(todosListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('My Todos')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _titleCtrl,
                    decoration: InputDecoration(
                      hintText: 'Add a todo...',
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                    onSubmitted: (_) => _addTodo(),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton(
                  onPressed: _addTodo,
                  icon: const Icon(Icons.add_circle, color: VamsTheme.primary),
                ),
              ],
            ),
          ),
          Expanded(
            child: todosAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('Error: $e')),
              data: (todos) {
                if (todos.isEmpty) {
                  return const Center(child: Text('No todos'));
                }
                return ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: todos.length,
                  itemBuilder: (context, index) {
                    final t = todos[index];
                    final isDone = t['status'] == 'done';
                    return Card(
                      margin: const EdgeInsets.only(bottom: 8),
                      child: ListTile(
                        leading: Checkbox(
                          value: isDone,
                          onChanged: (_) => _toggleTodo(t['id']),
                        ),
                        title: Text(
                          t['title'] ?? '',
                          style: TextStyle(
                            decoration: isDone ? TextDecoration.lineThrough : null,
                            color: isDone ? Colors.grey : null,
                          ),
                        ),
                        trailing: IconButton(
                          icon: const Icon(Icons.delete_outline, size: 20, color: VamsTheme.danger),
                          onPressed: () => _deleteTodo(t['id']),
                        ),
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
