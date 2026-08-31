import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../../shared/widgets/status_chip.dart';
import '../providers/tasks_provider.dart';

class TeamTasksScreen extends ConsumerStatefulWidget {
  const TeamTasksScreen({super.key});

  @override
  ConsumerState<TeamTasksScreen> createState() => _TeamTasksScreenState();
}

class _TeamTasksScreenState extends ConsumerState<TeamTasksScreen> {
  final _scrollController = ScrollController();
  String? _selectedStatus;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(teamTasksProvider.notifier).loadTasks(refresh: true);
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 200) {
      ref.read(teamTasksProvider.notifier).loadTasks();
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(teamTasksProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Team Tasks'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add_task, size: 22),
            onPressed: () => context.push('/more/tasks/create'),
          ),
        ],
      ),
      body: Column(
        children: [
          SizedBox(
            height: 48,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              children: [
                _FilterChip(
                  label: 'All',
                  selected: _selectedStatus == null,
                  onTap: () {
                    setState(() => _selectedStatus = null);
                    ref.read(teamTasksProvider.notifier).filterByStatus(null);
                  },
                ),
                const SizedBox(width: 8),
                _FilterChip(
                  label: 'To Do',
                  selected: _selectedStatus == 'To Do',
                  onTap: () {
                    setState(() => _selectedStatus = 'To Do');
                    ref.read(teamTasksProvider.notifier).filterByStatus('To Do');
                  },
                ),
                const SizedBox(width: 8),
                _FilterChip(
                  label: 'In Progress',
                  selected: _selectedStatus == 'In Progress',
                  onTap: () {
                    setState(() => _selectedStatus = 'In Progress');
                    ref.read(teamTasksProvider.notifier).filterByStatus('In Progress');
                  },
                ),
                const SizedBox(width: 8),
                _FilterChip(
                  label: 'Done',
                  selected: _selectedStatus == 'Done',
                  onTap: () {
                    setState(() => _selectedStatus = 'Done');
                    ref.read(teamTasksProvider.notifier).filterByStatus('Done');
                  },
                ),
              ],
            ),
          ),
          Expanded(
            child: state.isLoading && state.tasks.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : state.error != null && state.tasks.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
                            const SizedBox(height: 12),
                            Text(state.error!, style: const TextStyle(color: VamsTheme.textSecondary)),
                            const SizedBox(height: 12),
                            ElevatedButton(
                              onPressed: () => ref.read(teamTasksProvider.notifier).loadTasks(refresh: true),
                              child: const Text('Retry'),
                            ),
                          ],
                        ),
                      )
                    : state.tasks.isEmpty
                        ? const Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.task_alt, size: 48, color: VamsTheme.textMuted),
                                SizedBox(height: 12),
                                Text('No tasks found', style: TextStyle(color: VamsTheme.textSecondary)),
                              ],
                            ),
                          )
                        : RefreshIndicator(
                            onRefresh: () => ref.read(teamTasksProvider.notifier).loadTasks(refresh: true),
                            child: ListView.builder(
                              controller: _scrollController,
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                              itemCount: state.tasks.length +
                                  (state.currentPage < state.totalPages ? 1 : 0),
                              itemBuilder: (context, index) {
                                if (index == state.tasks.length) {
                                  return const Padding(
                                    padding: EdgeInsets.all(16),
                                    child: Center(child: CircularProgressIndicator()),
                                  );
                                }
                                final task = state.tasks[index];
                                return _TaskCard(task: task);
                              },
                            ),
                          ),
          ),
        ],
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? VamsTheme.primary : VamsTheme.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: selected ? VamsTheme.primary : VamsTheme.border),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: selected ? Colors.white : VamsTheme.textSecondary,
          ),
        ),
      ),
    );
  }
}

class _TaskCard extends StatelessWidget {
  final dynamic task;
  const _TaskCard({required this.task});

  @override
  Widget build(BuildContext context) {
    final priorityColor = task.priority == 'High'
        ? VamsTheme.danger
        : task.priority == 'Medium'
            ? VamsTheme.warning
            : VamsTheme.success;

    final statusColor = task.status == 'Done'
        ? VamsTheme.success
        : task.status == 'In Progress'
            ? VamsTheme.primary
            : VamsTheme.textMuted;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    task.title,
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                StatusChip(status: task.priority, color: priorityColor),
                const SizedBox(width: 8),
                IconButton(
                  icon: const Icon(Icons.edit_outlined, size: 18),
                  onPressed: () => context.push('/more/tasks/${task.id}/edit'),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                StatusChip(status: task.status, color: statusColor),
                const SizedBox(width: 8),
                if (task.assigneeName != null && task.assigneeName!.isNotEmpty) ...[
                  const Icon(Icons.person_outline, size: 14, color: VamsTheme.textMuted),
                  const SizedBox(width: 4),
                  Text(
                    task.assigneeName!,
                    style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                  ),
                ],
                const Spacer(),
                if (task.dueDate != null && task.dueDate!.isNotEmpty)
                  Text(
                    task.dueDate!,
                    style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted),
                  ),
              ],
            ),
            if (task.projectName != null && task.projectName!.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                task.projectName!,
                style: const TextStyle(fontSize: 11, color: VamsTheme.primary),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
