import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';

class CategoriesScreen extends ConsumerStatefulWidget {
  const CategoriesScreen({super.key});

  @override
  ConsumerState<CategoriesScreen> createState() => _CategoriesScreenState();
}

class _CategoriesScreenState extends ConsumerState<CategoriesScreen> {
  List<Map<String, dynamic>> _categories = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadCategories();
  }

  Future<void> _loadCategories() async {
    setState(() => _loading = true);
    try {
      final dio = ref.read(apiClientProvider);
      final response = await dio.get('/api/v1/accounts/categories');
      if (response.data['success'] == true) {
        setState(() {
          _categories = List<Map<String, dynamic>>.from(response.data['categories']);
        });
      }
    } on DioException catch (_) {}
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _addCategory() async {
    final nameCtrl = TextEditingController();
    String scope = 'general';

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add Category'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameCtrl,
              decoration: const InputDecoration(hintText: 'Category name'),
              autofocus: true,
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: scope,
              items: ['general', 'personal', 'company'].map((s) => DropdownMenuItem(value: s, child: Text(s))).toList(),
              onChanged: (v) => scope = v!,
              decoration: const InputDecoration(labelText: 'Scope'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Add')),
        ],
      ),
    );

    if (result == true && nameCtrl.text.trim().isNotEmpty) {
      try {
        final dio = ref.read(apiClientProvider);
        final response = await dio.post('/api/v1/accounts/categories', data: {
          'name': nameCtrl.text.trim(),
          'scope': scope,
        });
        if (response.data['success'] == true) {
          await _loadCategories();
          if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Category added')));
        }
      } on DioException catch (e) {
        if (mounted) {
          final msg = e.response?.data is Map ? (e.response?.data['message'] ?? 'Error') : 'Error';
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
        }
      }
    }
    nameCtrl.dispose();
  }

  Future<void> _toggleCategory(Map<String, dynamic> cat) async {
    try {
      final dio = ref.read(apiClientProvider);
      await dio.post('/api/v1/accounts/categories/${cat['id']}/toggle');
      await _loadCategories();
    } on DioException catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Categories'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add, size: 22),
            onPressed: _addCategory,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _categories.isEmpty
              ? const Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.category_outlined, size: 48, color: VamsTheme.textMuted),
                      SizedBox(height: 12),
                      Text('No categories found', style: TextStyle(color: VamsTheme.textSecondary)),
                    ],
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: _categories.length,
                  itemBuilder: (context, index) {
                    final cat = _categories[index];
                    final isActive = cat['is_active'] == true;
                    return Card(
                      child: ListTile(
                        leading: Icon(
                          Icons.label,
                          color: isActive ? VamsTheme.primary : VamsTheme.textMuted,
                          size: 20,
                        ),
                        title: Text(
                          cat['name'] ?? '',
                          style: TextStyle(
                            fontWeight: FontWeight.w600,
                            color: isActive ? null : VamsTheme.textMuted,
                          ),
                        ),
                        subtitle: Text(
                          cat['scope'] ?? '',
                          style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                        ),
                        trailing: Switch(
                          value: isActive,
                          onChanged: (_) => _toggleCategory(cat),
                        ),
                      ),
                    );
                  },
                ),
    );
  }
}
