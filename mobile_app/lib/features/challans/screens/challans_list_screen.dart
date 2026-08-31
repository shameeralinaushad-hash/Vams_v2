import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../providers/challans_provider.dart';

class ChallansListScreen extends ConsumerStatefulWidget {
  const ChallansListScreen({super.key});

  @override
  ConsumerState<ChallansListScreen> createState() => _ChallansListScreenState();
}

class _ChallansListScreenState extends ConsumerState<ChallansListScreen> {
  final _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 200) {
      ref.read(challansListProvider.notifier).loadMore();
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(challansListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('All Delivery Challans')),
      body: state.isLoading && state.challans.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : state.error != null && state.challans.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
                      const SizedBox(height: 12),
                      Text(state.error!, style: const TextStyle(color: VamsTheme.textSecondary)),
                      const SizedBox(height: 12),
                      ElevatedButton(
                        onPressed: () => ref.read(challansListProvider.notifier).loadChallans(refresh: true),
                        child: const Text('Retry'),
                      ),
                    ],
                  ),
                )
              : state.challans.isEmpty
                  ? const Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.local_shipping_outlined, size: 48, color: VamsTheme.textMuted),
                          SizedBox(height: 12),
                          Text('No delivery challans found', style: TextStyle(color: VamsTheme.textSecondary)),
                        ],
                      ),
                    )
                  : RefreshIndicator(
                      onRefresh: () => ref.read(challansListProvider.notifier).loadChallans(refresh: true),
                      child: ListView.builder(
                        controller: _scrollController,
                        padding: const EdgeInsets.all(16),
                        itemCount: state.challans.length + (state.currentPage < state.totalPages ? 1 : 0),
                        itemBuilder: (context, index) {
                          if (index == state.challans.length) {
                            return const Padding(
                              padding: EdgeInsets.all(16),
                              child: Center(child: CircularProgressIndicator()),
                            );
                          }
                          final c = state.challans[index];

                          return Card(
                            child: ListTile(
                              leading: Container(
                                width: 36,
                                height: 36,
                                decoration: BoxDecoration(
                                  color: VamsTheme.primary.withValues(alpha: 0.1),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: const Icon(Icons.local_shipping, size: 18, color: VamsTheme.primary),
                              ),
                              title: Text(c.challanNumber ?? '-', style: const TextStyle(fontWeight: FontWeight.w600)),
                              subtitle: Text(
                                '${c.clientName ?? '-'} • ${c.orderNumber != null ? 'Order #${c.orderNumber}' : '-'}',
                                style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                              ),
                              trailing: const Icon(Icons.chevron_right, size: 20),
                              onTap: () => context.push('/orders/${c.orderId}'),
                            ),
                          );
                        },
                      ),
                    ),
    );
  }
}
