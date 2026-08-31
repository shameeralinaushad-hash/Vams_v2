import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme.dart';
import '../../../core/api_client.dart';
import '../models/client_models.dart';
import '../providers/clients_provider.dart';

class ClientDetailScreen extends ConsumerWidget {
  final int clientId;

  const ClientDetailScreen({super.key, required this.clientId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final clientAsync = ref.watch(clientDetailProvider(clientId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Client'),
        actions: [
          clientAsync.whenOrNull(
            data: (client) => client != null
                ? IconButton(
                    icon: const Icon(Icons.edit, size: 20),
                    onPressed: () => _showEditSheet(context, ref, client),
                  )
                : null,
          ) ?? const SizedBox.shrink(),
        ],
      ),
      body: clientAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
              const SizedBox(height: 12),
              const Text('Failed to load client', style: TextStyle(color: VamsTheme.textSecondary)),
              const SizedBox(height: 12),
              ElevatedButton(onPressed: () => ref.invalidate(clientDetailProvider(clientId)), child: const Text('Retry')),
            ],
          ),
        ),
        data: (client) {
          if (client == null) {
            return const Center(child: Text('Client not found'));
          }
          return _ClientDetailBody(client: client);
        },
      ),
    );
  }

  void _showEditSheet(BuildContext context, WidgetRef ref, ClientDetail client) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (context) => _EditClientSheet(client: client),
    );
  }
}

class _ClientDetailBody extends ConsumerWidget {
  final ClientDetail client;
  const _ClientDetailBody({required this.client});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final initials = client.name.length >= 2
        ? client.name.substring(0, 2).toUpperCase()
        : client.name.toUpperCase();

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Row(
                  children: [
                    Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(
                        color: VamsTheme.primary.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Center(
                        child: Text(
                          initials,
                          style: const TextStyle(color: VamsTheme.primary, fontWeight: FontWeight.w700, fontSize: 20),
                        ),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            client.name,
                            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                          ),
                          if (client.clientCode != null && client.clientCode!.isNotEmpty)
                            Text(
                              client.clientCode!,
                              style: const TextStyle(fontSize: 13, color: VamsTheme.textMuted),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                const Divider(height: 1),
                const SizedBox(height: 12),
                if (client.email != null && client.email!.isNotEmpty)
                  _InfoRow(icon: Icons.email_outlined, value: client.email!),
                if (client.contactInfo != null && client.contactInfo!.isNotEmpty)
                  _InfoRow(icon: Icons.phone_outlined, value: client.contactInfo!),
                if (client.address != null && client.address!.isNotEmpty)
                  _InfoRow(icon: Icons.location_on_outlined, value: client.address!),
                if (client.taxNumber != null && client.taxNumber!.isNotEmpty)
                  _InfoRow(icon: Icons.receipt_outlined, value: 'Tax: ${client.taxNumber}'),
                if (client.gstRegistration)
                  _InfoRow(
                    icon: Icons.verified_outlined,
                    value: 'GST: ${client.gstRegistrationNumber ?? "Registered"}',
                  ),
              ],
            ),
          ),
        ),

        if (client.companies.isNotEmpty) ...[
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Companies', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 8),
                  ...client.companies.map((c) => Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Row(
                          children: [
                            const Icon(Icons.business, size: 16, color: VamsTheme.textMuted),
                            const SizedBox(width: 8),
                            Text(c.name, style: const TextStyle(fontSize: 13)),
                          ],
                        ),
                      )),
                ],
              ),
            ),
          ),
        ],

        if (client.subsidiaries.isNotEmpty) ...[
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text('Subsidiaries (${client.subsidiaries.length})', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                      ),
                      IconButton(
                        icon: const Icon(Icons.add, size: 20),
                        onPressed: () => _showAddSubsidiarySheet(context, ref, client),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  ...client.subsidiaries.map((s) => Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(color: VamsTheme.background, borderRadius: BorderRadius.circular(10)),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(s.name, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                                  if (s.address != null && s.address!.isNotEmpty)
                                    Text(s.address!, style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
                                  if (s.contactInfo != null && s.contactInfo!.isNotEmpty)
                                    Text(s.contactInfo!, style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
                                ],
                              ),
                            ),
                            IconButton(
                              icon: const Icon(Icons.delete_outline, size: 18, color: VamsTheme.danger),
                              onPressed: () => _confirmDeleteSubsidiary(context, ref, client, s),
                            ),
                          ],
                        ),
                      )),
                ],
              ),
            ),
          ),
        ] else ...[
          const SizedBox(height: 12),
          Card(
            child: ListTile(
              leading: const Icon(Icons.add_circle_outline, color: VamsTheme.primary),
              title: const Text('Add Subsidiary'),
              subtitle: const Text('Add a subsidiary for this client'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => _showAddSubsidiarySheet(context, ref, client),
            ),
          ),
        ],

        Card(
          margin: const EdgeInsets.only(top: 12),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const Icon(Icons.shopping_bag_outlined, size: 20, color: VamsTheme.textMuted),
                const SizedBox(width: 12),
                Text(
                  '${client.orderCount} order${client.orderCount == 1 ? '' : 's'}',
                  style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                ),
              ],
            ),
          ),
        ),

        const SizedBox(height: 32),
      ],
    );
  }
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String value;
  const _InfoRow({required this.icon, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Icon(icon, size: 16, color: VamsTheme.textMuted),
          const SizedBox(width: 8),
          Expanded(child: Text(value, style: const TextStyle(fontSize: 13))),
        ],
      ),
    );
  }
}

void _showAddSubsidiarySheet(BuildContext context, WidgetRef ref, ClientDetail client) {
  final nameCtrl = TextEditingController();
  final addressCtrl = TextEditingController();
  final contactCtrl = TextEditingController();

  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (ctx) => Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(ctx).viewInsets.bottom,
        left: 16, right: 16, top: 16,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Add Subsidiary', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
            const SizedBox(height: 16),
            TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: 'Name', isDense: true)),
            const SizedBox(height: 12),
            TextField(controller: addressCtrl, decoration: const InputDecoration(labelText: 'Address', isDense: true)),
            const SizedBox(height: 12),
            TextField(controller: contactCtrl, decoration: const InputDecoration(labelText: 'Contact Info', isDense: true)),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: () async {
                if (nameCtrl.text.trim().isEmpty) return;
                try {
                  final dio = ref.read(apiClientProvider);
                  final response = await dio.post('/api/v1/clients/${client.id}/subsidiaries', data: {
                    'name': nameCtrl.text.trim(),
                    'address': addressCtrl.text.trim().isEmpty ? null : addressCtrl.text.trim(),
                    'contact_info': contactCtrl.text.trim().isEmpty ? null : contactCtrl.text.trim(),
                  });
                  if (ctx.mounted) {
                    Navigator.pop(ctx);
                    if (response.data['success'] == true) {
                      ref.invalidate(clientDetailProvider(client.id));
                      ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(content: Text('Subsidiary added')));
                    }
                  }
                } catch (e) {
                  if (ctx.mounted) {
                    ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text('Error: $e')));
                  }
                }
              },
              child: const Text('Add'),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    ),
  );
}

void _confirmDeleteSubsidiary(BuildContext context, WidgetRef ref, ClientDetail client, ClientSubsidiary sub) {
  showDialog(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Delete Subsidiary'),
      content: Text('Delete "${sub.name}"?'),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
        TextButton(
          onPressed: () async {
            Navigator.pop(ctx);
            try {
              final dio = ref.read(apiClientProvider);
              final response = await dio.delete('/api/v1/clients/subsidiaries/${sub.id}');
              if (context.mounted) {
                if (response.data['success'] == true) {
                  ref.invalidate(clientDetailProvider(client.id));
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Subsidiary deleted')));
                }
              }
            } catch (e) {
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
              }
            }
          },
          child: const Text('Delete', style: TextStyle(color: VamsTheme.danger)),
        ),
      ],
    ),
  );
}

class _EditClientSheet extends ConsumerStatefulWidget {
  final ClientDetail client;
  const _EditClientSheet({required this.client});

  @override
  ConsumerState<_EditClientSheet> createState() => _EditClientSheetState();
}

class _EditClientSheetState extends ConsumerState<_EditClientSheet> {
  late final TextEditingController _nameCtrl;
  late final TextEditingController _emailCtrl;
  late final TextEditingController _contactCtrl;
  late final TextEditingController _addressCtrl;
  late final TextEditingController _taxCtrl;
  late final TextEditingController _codeCtrl;

  @override
  void initState() {
    super.initState();
    _nameCtrl = TextEditingController(text: widget.client.name);
    _emailCtrl = TextEditingController(text: widget.client.email ?? '');
    _contactCtrl = TextEditingController(text: widget.client.contactInfo ?? '');
    _addressCtrl = TextEditingController(text: widget.client.address ?? '');
    _taxCtrl = TextEditingController(text: widget.client.taxNumber ?? '');
    _codeCtrl = TextEditingController(text: widget.client.clientCode ?? '');
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _contactCtrl.dispose();
    _addressCtrl.dispose();
    _taxCtrl.dispose();
    _codeCtrl.dispose();
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
            const Text('Edit Client', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
            const SizedBox(height: 16),
            TextField(controller: _nameCtrl, decoration: const InputDecoration(labelText: 'Name', isDense: true)),
            const SizedBox(height: 12),
            TextField(controller: _emailCtrl, decoration: const InputDecoration(labelText: 'Email', isDense: true)),
            const SizedBox(height: 12),
            TextField(controller: _contactCtrl, decoration: const InputDecoration(labelText: 'Contact', isDense: true)),
            const SizedBox(height: 12),
            TextField(controller: _addressCtrl, decoration: const InputDecoration(labelText: 'Address', isDense: true)),
            const SizedBox(height: 12),
            TextField(controller: _taxCtrl, decoration: const InputDecoration(labelText: 'Tax Number', isDense: true)),
            const SizedBox(height: 12),
            TextField(controller: _codeCtrl, decoration: const InputDecoration(labelText: 'Client Code', isDense: true)),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: _save,
              child: const Text('Save'),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }

  Future<void> _save() async {
    if (_nameCtrl.text.trim().isEmpty) return;

    final data = {
      'name': _nameCtrl.text.trim(),
      'email': _emailCtrl.text.trim().isEmpty ? null : _emailCtrl.text.trim(),
      'contact_info': _contactCtrl.text.trim().isEmpty ? null : _contactCtrl.text.trim(),
      'address': _addressCtrl.text.trim().isEmpty ? null : _addressCtrl.text.trim(),
      'tax_number': _taxCtrl.text.trim().isEmpty ? null : _taxCtrl.text.trim(),
      'client_code': _codeCtrl.text.trim().isEmpty ? null : _codeCtrl.text.trim(),
    };

    final updated = await ref
        .read(clientsProvider.notifier)
        .updateClient(widget.client.id, data);

    if (mounted) {
      Navigator.of(context).pop();
      if (updated != null) {
        ref.invalidate(clientDetailProvider(widget.client.id));
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Client updated')),
        );
      }
    }
  }
}
