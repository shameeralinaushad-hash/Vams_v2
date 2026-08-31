import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../providers/tasks_provider.dart';

class CreateTeamTaskScreen extends ConsumerStatefulWidget {
  const CreateTeamTaskScreen({super.key});

  @override
  ConsumerState<CreateTeamTaskScreen> createState() => _CreateTeamTaskScreenState();
}

class _CreateTeamTaskScreenState extends ConsumerState<CreateTeamTaskScreen> {
  final _formKey = GlobalKey<FormState>();
  final _titleCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  bool _saving = false;
  int? _selectedAssigneeId;
  String _selectedPriority = 'Medium';
  DateTime? _dueDate;
  List<Map<String, dynamic>> _employees = [];
  bool _loadingEmployees = true;

  @override
  void initState() {
    super.initState();
    _loadEmployees();
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    _descCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadEmployees() async {
    try {
      final dio = ref.read(apiClientProvider);
      final response = await dio.get('/api/v1/hr/employees');
      if (response.data['success'] == true) {
        final list = (response.data['employees'] as List? ?? [])
            .map((e) => {'id': e['id'], 'name': e['name']})
            .toList();
        setState(() => _employees = list);
      }
    } on DioException catch (_) {}
    if (mounted) setState(() => _loadingEmployees = false);
  }

  Future<void> _pickDueDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _dueDate ?? DateTime.now(),
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null) setState(() => _dueDate = picked);
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_selectedAssigneeId == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Please select an assignee')));
      return;
    }

    setState(() => _saving = true);

    try {
      final dio = ref.read(apiClientProvider);
      final result = await createTeamTask(
        dio,
        title: _titleCtrl.text.trim(),
        assigneeId: _selectedAssigneeId!,
        description: _descCtrl.text.trim().isEmpty ? null : _descCtrl.text.trim(),
        priority: _selectedPriority,
        dueDate: _dueDate != null ? DateFormat('yyyy-MM-dd').format(_dueDate!) : null,
      );

      if (mounted) {
        if (result['success'] == true) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Task created')));
          ref.read(teamTasksProvider.notifier).loadTasks(refresh: true);
          context.pop();
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(result['message'] ?? 'Failed to create task')),
          );
        }
      }
    } on DioException catch (e) {
      if (mounted) {
        final msg = e.response?.data is Map ? (e.response?.data['message'] ?? 'Error') : 'Error';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Create Team Task')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('Title', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
            const SizedBox(height: 6),
            TextFormField(
              controller: _titleCtrl,
              decoration: const InputDecoration(hintText: 'Task title'),
              validator: (v) => v == null || v.trim().isEmpty ? 'Title is required' : null,
            ),
            const SizedBox(height: 16),
            const Text('Assignee', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
            const SizedBox(height: 6),
            if (_loadingEmployees)
              const SizedBox(
                height: 48,
                child: Center(child: CircularProgressIndicator()),
              )
            else DropdownButtonFormField<int>(
              initialValue: _selectedAssigneeId,
              items: _employees
                  .map((e) => DropdownMenuItem(value: e['id'] as int, child: Text(e['name'] as String)))
                  .toList(),
              onChanged: (v) => setState(() => _selectedAssigneeId = v),
              decoration: const InputDecoration(hintText: 'Select assignee'),
              validator: (v) => v == null ? 'Assignee is required' : null,
            ),
            const SizedBox(height: 16),
            const Text('Priority', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
            const SizedBox(height: 6),
            DropdownButtonFormField<String>(
              initialValue: _selectedPriority,
              items: ['Low', 'Medium', 'High'].map((p) => DropdownMenuItem(value: p, child: Text(p))).toList(),
              onChanged: (v) => setState(() => _selectedPriority = v!),
              decoration: const InputDecoration(),
            ),
            const SizedBox(height: 16),
            const Text('Due Date', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
            const SizedBox(height: 6),
            GestureDetector(
              onTap: _pickDueDate,
              child: InputDecorator(
                decoration: const InputDecoration(),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      _dueDate != null ? DateFormat('yyyy-MM-dd').format(_dueDate!) : 'Select due date',
                      style: TextStyle(
                        color: _dueDate != null ? VamsTheme.textPrimary : VamsTheme.textMuted,
                      ),
                    ),
                    const Icon(Icons.calendar_today, size: 18),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            const Text('Description', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
            const SizedBox(height: 6),
            TextFormField(
              controller: _descCtrl,
              decoration: const InputDecoration(hintText: 'Description (optional)'),
              maxLines: 3,
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _saving ? null : _submit,
                child: _saving
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Text('Create Task'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
