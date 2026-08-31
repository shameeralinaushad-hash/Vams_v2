import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../../shared/widgets/status_chip.dart';
import '../providers/quotations_provider.dart';

class QuotationsListScreen extends ConsumerStatefulWidget {
  const QuotationsListScreen({super.key});

  @override
  ConsumerState<QuotationsListScreen> createState() => _QuotationsListScreenState();
}

class _QuotationsListScreenState extends ConsumerState<QuotationsListScreen> {
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
      ref.read(quotationsListProvider.notifier).loadMore();
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(quotationsListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('All Quotations')),
      body: state.isLoading && state.quotations.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : state.error != null && state.quotations.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
                      const SizedBox(height: 12),
                      Text(state.error!, style: const TextStyle(color: VamsTheme.textSecondary)),
                      const SizedBox(height: 12),
                      ElevatedButton(
                        onPressed: () => ref.read(quotationsListProvider.notifier).loadQuotations(refresh: true),
                        child: const Text('Retry'),
                      ),
                    ],
                  ),
                )
              : state.quotations.isEmpty
                  ? const Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.description_outlined, size: 48, color: VamsTheme.textMuted),
                          SizedBox(height: 12),
                          Text('No quotations found', style: TextStyle(color: VamsTheme.textSecondary)),
                        ],
                      ),
                    )
                  : RefreshIndicator(
                      onRefresh: () => ref.read(quotationsListProvider.notifier).loadQuotations(refresh: true),
                      child: ListView.builder(
                        controller: _scrollController,
                        padding: const EdgeInsets.all(16),
                        itemCount: state.quotations.length + (state.currentPage < state.totalPages ? 1 : 0),
                        itemBuilder: (context, index) {
                          if (index == state.quotations.length) {
                            return const Padding(
                              padding: EdgeInsets.all(16),
                              child: Center(child: CircularProgressIndicator()),
                            );
                          }
                          final q = state.quotations[index];
                          final docType = q.docType ?? 'commercial';
                          final docColor = docType == 'technical' ? VamsTheme.warning : VamsTheme.primary;

                          return Card(
                            child: ListTile(
                              leading: StatusChip(status: docType, color: docColor),
                              title: Text(q.quoteNumber ?? '-', style: const TextStyle(fontWeight: FontWeight.w600)),
                              subtitle: Text(
                                '${q.clientName ?? '-'} • ${q.orderNumber != null ? 'Order #${q.orderNumber}' : '-'}',
                                style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                              ),
                              trailing: const Icon(Icons.chevron_right, size: 20),
                              onTap: () => context.push('/orders/${q.orderId}'),
                            ),
                          );
                        },
                      ),
                    ),
    );
  }
}
