import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme.dart';
import '../../../shared/widgets/status_chip.dart';
import '../providers/tasks_provider.dart';

class PersonalTasksScreen extends ConsumerStatefulWidget {
  const PersonalTasksScreen({super.key});

  @override
  ConsumerState<PersonalTasksScreen> createState() => _PersonalTasksScreenState();
}

class _PersonalTasksScreenState extends ConsumerState<PersonalTasksScreen> {
  final _scrollController = ScrollController();
  String? _selectedLane;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(personalItemsProvider.notifier).loadItems(refresh: true);
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 200) {
      ref.read(personalItemsProvider.notifier).loadItems();
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(personalItemsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('My Tasks'),
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
                  selected: _selectedLane == null,
                  onTap: () {
                    setState(() => _selectedLane = null);
                    ref.read(personalItemsProvider.notifier).filterByLane(null);
                  },
                ),
                const SizedBox(width: 8),
                _FilterChip(
                  label: 'Task',
                  selected: _selectedLane == 'Task',
                  onTap: () {
                    setState(() => _selectedLane = 'Task');
                    ref.read(personalItemsProvider.notifier).filterByLane('Task');
                  },
                ),
                const SizedBox(width: 8),
                _FilterChip(
                  label: 'Goal',
                  selected: _selectedLane == 'Goal',
                  onTap: () {
                    setState(() => _selectedLane = 'Goal');
                    ref.read(personalItemsProvider.notifier).filterByLane('Goal');
                  },
                ),
                const SizedBox(width: 8),
                _FilterChip(
                  label: 'Future Plan',
                  selected: _selectedLane == 'Future Plan',
                  onTap: () {
                    setState(() => _selectedLane = 'Future Plan');
                    ref.read(personalItemsProvider.notifier).filterByLane('Future Plan');
                  },
                ),
              ],
            ),
          ),
          Expanded(
            child: state.isLoading && state.items.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : state.error != null && state.items.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
                            const SizedBox(height: 12),
                            Text(state.error!, style: const TextStyle(color: VamsTheme.textSecondary)),
                            const SizedBox(height: 12),
                            ElevatedButton(
                              onPressed: () => ref.read(personalItemsProvider.notifier).loadItems(refresh: true),
                              child: const Text('Retry'),
                            ),
                          ],
                        ),
                      )
                    : state.items.isEmpty
                        ? const Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.checklist, size: 48, color: VamsTheme.textMuted),
                                SizedBox(height: 12),
                                Text('No items yet', style: TextStyle(color: VamsTheme.textSecondary)),
                              ],
                            ),
                          )
                        : RefreshIndicator(
                            onRefresh: () => ref.read(personalItemsProvider.notifier).loadItems(refresh: true),
                            child: ListView.builder(
                              controller: _scrollController,
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                              itemCount: state.items.length +
                                  (state.currentPage < state.totalPages ? 1 : 0),
                              itemBuilder: (context, index) {
                                if (index == state.items.length) {
                                  return const Padding(
                                    padding: EdgeInsets.all(16),
                                    child: Center(child: CircularProgressIndicator()),
                                  );
                                }
                                final item = state.items[index];
                                return _ItemCard(item: item);
                              },
                            ),
                          ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showAddItemSheet(context),
        backgroundColor: VamsTheme.primary,
        child: const Icon(Icons.add, color: Colors.white),
      ),
    );
  }

  void _showAddItemSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (context) => _AddItemSheet(lane: _selectedLane),
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

class _ItemCard extends StatelessWidget {
  final dynamic item;
  const _ItemCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final priorityColor = item.priority == 'High'
        ? VamsTheme.danger
        : item.priority == 'Medium'
            ? VamsTheme.warning
            : VamsTheme.success;

    final statusColor = item.status == 'Done'
        ? VamsTheme.success
        : item.status == 'In Progress'
            ? VamsTheme.primary
            : VamsTheme.textMuted;

    final laneColor = item.lane == 'Goal'
        ? VamsTheme.primary
        : item.lane == 'Future Plan'
            ? VamsTheme.warning
            : VamsTheme.textMuted;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: laneColor.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    item.lane,
                    style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: laneColor),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    item.title,
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                StatusChip(status: item.priority, color: priorityColor),
              ],
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                StatusChip(status: item.status, color: statusColor),
                const Spacer(),
                if (item.dueDate != null && item.dueDate!.isNotEmpty)
                  Text(
                    item.dueDate!,
                    style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted),
                  ),
              ],
            ),
            if (item.description.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                item.description,
                style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _AddItemSheet extends ConsumerStatefulWidget {
  final String? lane;
  const _AddItemSheet({this.lane});

  @override
  ConsumerState<_AddItemSheet> createState() => _AddItemSheetState();
}

class _AddItemSheetState extends ConsumerState<_AddItemSheet> {
  late final TextEditingController _titleCtrl;
  late final TextEditingController _descCtrl;
  String _selectedLane = 'Task';
  String _selectedPriority = 'Medium';

  @override
  void initState() {
    super.initState();
    _titleCtrl = TextEditingController();
    _descCtrl = TextEditingController();
    if (widget.lane != null) _selectedLane = widget.lane!;
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    _descCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
        left: 16, right: 16, top: 16,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('New Item', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
            const SizedBox(height: 16),
            TextField(controller: _titleCtrl, decoration: const InputDecoration(labelText: 'Title', isDense: true)),
            const SizedBox(height: 12),
            TextField(
              controller: _descCtrl,
              decoration: const InputDecoration(labelText: 'Description', isDense: true),
              maxLines: 3,
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: _selectedLane,
              decoration: const InputDecoration(labelText: 'Lane', isDense: true),
              items: const [
                DropdownMenuItem(value: 'Task', child: Text('Task')),
                DropdownMenuItem(value: 'Goal', child: Text('Goal')),
                DropdownMenuItem(value: 'Future Plan', child: Text('Future Plan')),
              ],
              onChanged: (v) => setState(() => _selectedLane = v ?? 'Task'),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: _selectedPriority,
              decoration: const InputDecoration(labelText: 'Priority', isDense: true),
              items: const [
                DropdownMenuItem(value: 'Low', child: Text('Low')),
                DropdownMenuItem(value: 'Medium', child: Text('Medium')),
                DropdownMenuItem(value: 'High', child: Text('High')),
              ],
              onChanged: (v) => setState(() => _selectedPriority = v ?? 'Medium'),
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: _save,
              child: const Text('Create'),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }

  Future<void> _save() async {
    if (_titleCtrl.text.trim().isEmpty) return;

    final data = {
      'title': _titleCtrl.text.trim(),
      'description': _descCtrl.text.trim().isEmpty ? null : _descCtrl.text.trim(),
      'lane': _selectedLane,
      'priority': _selectedPriority,
    };

    final result = await ref.read(personalItemsProvider.notifier).createItem(data);

    if (mounted) {
      Navigator.of(context).pop();
      if (result != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Item created')),
        );
      }
    }
  }
}
