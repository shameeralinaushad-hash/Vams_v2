import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../../clients/models/client_models.dart';

class CreateOrderScreen extends ConsumerStatefulWidget {
  const CreateOrderScreen({super.key});

  @override
  ConsumerState<CreateOrderScreen> createState() => _CreateOrderScreenState();
}

class _CreateOrderScreenState extends ConsumerState<CreateOrderScreen> {
  final _formKey = GlobalKey<FormState>();
  final _titleCtrl = TextEditingController();
  final _notesCtrl = TextEditingController();
  final _clientSearchCtrl = TextEditingController();
  bool _saving = false;
  List<ClientSearchResult> _searchResults = [];
  bool _searching = false;
  ClientSearchResult? _selectedClient;

  @override
  void dispose() {
    _titleCtrl.dispose();
    _notesCtrl.dispose();
    _clientSearchCtrl.dispose();
    super.dispose();
  }

  Future<void> _searchClients(String query) async {
    if (query.trim().length < 2) {
      setState(() => _searchResults = []);
      return;
    }
    setState(() => _searching = true);
    try {
      final dio = ref.read(apiClientProvider);
      final response = await dio.get('/api/v1/clients', queryParameters: {'search': query, 'per_page': 10});
      if (response.data['success'] == true) {
        final clients = PaginatedClients.fromJson(response.data).clients;
        setState(() {
          _searchResults = clients
              .map((c) => ClientSearchResult(id: c.id, name: c.name, clientCode: c.clientCode, email: c.email))
              .toList();
        });
      }
    } on DioException catch (_) {}
    if (mounted) setState(() => _searching = false);
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_selectedClient == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Please select a client')));
      return;
    }

    setState(() => _saving = true);

    try {
      final dio = ref.read(apiClientProvider);
      final response = await dio.post('/api/v1/orders', data: {
        'client_id': _selectedClient!.id,
        'title': _titleCtrl.text.trim(),
        'notes': _notesCtrl.text.trim().isEmpty ? null : _notesCtrl.text.trim(),
      });

      if (mounted) {
        if (response.data['success'] == true) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Order created')));
          context.pop();
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(response.data['message'] ?? 'Failed to create order')),
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
      appBar: AppBar(title: const Text('Create Order')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('Client', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
            const SizedBox(height: 6),
            if (_selectedClient != null)
              Card(
                child: ListTile(
                  leading: CircleAvatar(
                    radius: 16,
                    backgroundColor: VamsTheme.primary.withOpacity(0.1),
                    child: Text(_selectedClient!.name[0].toUpperCase(), style: const TextStyle(color: VamsTheme.primary, fontWeight: FontWeight.w700, fontSize: 14)),
                  ),
                  title: Text(_selectedClient!.name, style: const TextStyle(fontWeight: FontWeight.w600)),
                  subtitle: Text(_selectedClient!.clientCode ?? '', style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
                  trailing: IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: () => setState(() {
                      _selectedClient = null;
                      _clientSearchCtrl.clear();
                      _searchResults = [];
                    }),
                  ),
                ),
              )
            else
              TextField(
                controller: _clientSearchCtrl,
                decoration: InputDecoration(
                  hintText: 'Search clients...',
                  prefixIcon: const Icon(Icons.search, size: 20),
                  suffixIcon: _searching ? const Padding(
                    padding: EdgeInsets.all(12),
                    child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
                  ) : null,
                ),
                onChanged: _searchClients,
              ),
            if (_searchResults.isNotEmpty && _selectedClient == null)
              Container(
                margin: const EdgeInsets.only(top: 4),
                constraints: const BoxConstraints(maxHeight: 200),
                decoration: BoxDecoration(
                  color: VamsTheme.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: VamsTheme.border),
                ),
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: _searchResults.length,
                  itemBuilder: (context, index) {
                    final client = _searchResults[index];
                    return ListTile(
                      dense: true,
                      title: Text(client.name, style: const TextStyle(fontSize: 14)),
                      subtitle: Text(client.clientCode ?? '', style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
                      onTap: () => setState(() {
                        _selectedClient = client;
                        _searchResults = [];
                        _clientSearchCtrl.clear();
                      }),
                    );
                  },
                ),
              ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _titleCtrl,
              decoration: const InputDecoration(hintText: 'Order title'),
              validator: (v) => v == null || v.trim().isEmpty ? 'Title is required' : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _notesCtrl,
              decoration: const InputDecoration(hintText: 'Notes (optional)'),
              maxLines: 3,
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _saving ? null : _submit,
                child: _saving
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Text('Create Order'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
