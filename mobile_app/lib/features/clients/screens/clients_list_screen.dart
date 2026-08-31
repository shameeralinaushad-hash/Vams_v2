import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../providers/clients_provider.dart';

class ClientsListScreen extends ConsumerStatefulWidget {
  const ClientsListScreen({super.key});

  @override
  ConsumerState<ClientsListScreen> createState() => _ClientsListScreenState();
}

class _ClientsListScreenState extends ConsumerState<ClientsListScreen> {
  final _searchController = TextEditingController();
  final _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(clientsProvider.notifier).loadClients(refresh: true);
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 200) {
      ref.read(clientsProvider.notifier).loadClients();
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(clientsProvider);

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: TextField(
            controller: _searchController,
            decoration: InputDecoration(
              hintText: 'Search clients...',
              prefixIcon: const Icon(Icons.search, size: 20),
              suffixIcon: _searchController.text.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.clear, size: 18),
                      onPressed: () {
                        _searchController.clear();
                        ref.read(clientsProvider.notifier).search('');
                      },
                    )
                  : null,
              isDense: true,
            ),
            onChanged: (v) {
              setState(() {});
              ref.read(clientsProvider.notifier).search(v);
            },
          ),
        ),
        if (state.isLoading && state.clients.isEmpty)
          const Expanded(child: Center(child: CircularProgressIndicator()))
        else if (state.error != null && state.clients.isEmpty)
          Expanded(
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
                  const SizedBox(height: 12),
                  Text(state.error!, style: const TextStyle(color: VamsTheme.textSecondary)),
                  const SizedBox(height: 12),
                  ElevatedButton(onPressed: () => ref.read(clientsProvider.notifier).loadClients(refresh: true), child: const Text('Retry')),
                ],
              ),
            ),
          )
        else if (state.clients.isEmpty)
          const Expanded(
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.people_outline, size: 48, color: VamsTheme.textMuted),
                  SizedBox(height: 12),
                  Text('No clients found', style: TextStyle(color: VamsTheme.textSecondary)),
                ],
              ),
            ),
          )
        else
          Expanded(
            child: RefreshIndicator(
              onRefresh: () => ref.read(clientsProvider.notifier).loadClients(refresh: true),
              child: ListView.builder(
                controller: _scrollController,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                itemCount: state.clients.length + (state.currentPage < state.totalPages ? 1 : 0),
                itemBuilder: (context, index) {
                  if (index == state.clients.length) {
                    return const Padding(
                      padding: EdgeInsets.all(16),
                      child: Center(child: CircularProgressIndicator()),
                    );
                  }
                  final client = state.clients[index];
                  return _ClientCard(
                    client: client,
                    onTap: () => context.push('/clients/${client.id}'),
                  );
                },
              ),
            ),
          ),
      ],
    );
  }
}

class _ClientCard extends StatelessWidget {
  final dynamic client;
  final VoidCallback onTap;

  const _ClientCard({required this.client, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final initials = client.name.length >= 2
        ? client.name.substring(0, 2).toUpperCase()
        : client.name.toUpperCase();

    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: VamsTheme.primary.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Center(
                  child: Text(
                    initials,
                    style: const TextStyle(color: VamsTheme.primary, fontWeight: FontWeight.w700, fontSize: 14),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      client.name,
                      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    if (client.email != null)
                      Text(
                        client.email!,
                        style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                        overflow: TextOverflow.ellipsis,
                      ),
                    if (client.contactInfo != null && client.contactInfo!.isNotEmpty)
                      Text(
                        client.contactInfo!,
                        style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                        overflow: TextOverflow.ellipsis,
                      ),
                  ],
                ),
              ),
              if (client.clientCode != null && client.clientCode!.isNotEmpty)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: VamsTheme.surface,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    client.clientCode!,
                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: VamsTheme.textSecondary),
                  ),
                ),
              const SizedBox(width: 4),
              const Icon(Icons.chevron_right, size: 20, color: VamsTheme.textMuted),
            ],
          ),
        ),
      ),
    );
  }
}
