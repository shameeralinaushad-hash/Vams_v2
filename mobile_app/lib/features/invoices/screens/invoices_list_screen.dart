import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../../shared/widgets/status_chip.dart';
import '../providers/invoices_provider.dart';

class InvoicesListScreen extends ConsumerStatefulWidget {
  const InvoicesListScreen({super.key});

  @override
  ConsumerState<InvoicesListScreen> createState() => _InvoicesListScreenState();
}

class _InvoicesListScreenState extends ConsumerState<InvoicesListScreen> {
  final _searchController = TextEditingController();
  final _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(invoicesProvider.notifier).loadInvoices(refresh: true);
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
      ref.read(invoicesProvider.notifier).loadInvoices();
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(invoicesProvider);

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: TextField(
            controller: _searchController,
            decoration: InputDecoration(
              hintText: 'Search invoices...',
              prefixIcon: const Icon(Icons.search, size: 20),
              suffixIcon: _searchController.text.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.clear, size: 18),
                      onPressed: () {
                        _searchController.clear();
                        ref.read(invoicesProvider.notifier).search('');
                      },
                    )
                  : null,
              isDense: true,
            ),
            onChanged: (v) {
              setState(() {});
              ref.read(invoicesProvider.notifier).search(v);
            },
          ),
        ),
        SizedBox(
          height: 48,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            children: [
              _FilterChip(label: 'All', selected: state.statusFilter == null, onTap: () => ref.read(invoicesProvider.notifier).filterByStatus(null)),
              const SizedBox(width: 8),
              _FilterChip(label: 'Issued', selected: state.statusFilter == 'issued', onTap: () => ref.read(invoicesProvider.notifier).filterByStatus('issued')),
              const SizedBox(width: 8),
              _FilterChip(label: 'Cancelled', selected: state.statusFilter == 'cancelled', onTap: () => ref.read(invoicesProvider.notifier).filterByStatus('cancelled')),
            ],
          ),
        ),
        if (state.isLoading && state.invoices.isEmpty)
          const Expanded(child: Center(child: CircularProgressIndicator()))
        else if (state.error != null && state.invoices.isEmpty)
          Expanded(
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
                  const SizedBox(height: 12),
                  Text(state.error!, style: const TextStyle(color: VamsTheme.textSecondary)),
                  const SizedBox(height: 12),
                  ElevatedButton(onPressed: () => ref.read(invoicesProvider.notifier).loadInvoices(refresh: true), child: const Text('Retry')),
                ],
              ),
            ),
          )
        else if (state.invoices.isEmpty)
          const Expanded(
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.receipt_long_outlined, size: 48, color: VamsTheme.textMuted),
                  SizedBox(height: 12),
                  Text('No invoices found', style: TextStyle(color: VamsTheme.textSecondary)),
                ],
              ),
            ),
          )
        else
          Expanded(
            child: RefreshIndicator(
              onRefresh: () => ref.read(invoicesProvider.notifier).loadInvoices(refresh: true),
              child: ListView.builder(
                controller: _scrollController,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                itemCount: state.invoices.length + (state.currentPage < state.totalPages ? 1 : 0),
                itemBuilder: (context, index) {
                  if (index == state.invoices.length) {
                    return const Padding(
                      padding: EdgeInsets.all(16),
                      child: Center(child: CircularProgressIndicator()),
                    );
                  }
                  final invoice = state.invoices[index];
                  return _InvoiceCard(
                    invoice: invoice,
                    onTap: () => context.push('/invoices/${invoice.id}'),
                  );
                },
              ),
            ),
          ),
      ],
    );
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _FilterChip({required this.label, required this.selected, required this.onTap});

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

class _InvoiceCard extends StatelessWidget {
  final dynamic invoice;
  final VoidCallback onTap;

  const _InvoiceCard({required this.invoice, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final isPaid = invoice.isFullyPaid;
    final isCancelled = invoice.status == 'cancelled';
    final statusColor = isCancelled
        ? VamsTheme.textMuted
        : isPaid
            ? VamsTheme.success
            : invoice.balanceDue > 0
                ? VamsTheme.danger
                : VamsTheme.primary;

    final statusLabel = isCancelled ? 'Cancelled' : isPaid ? 'Paid' : 'Unpaid';

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
                  color: statusColor.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Center(
                  child: Icon(
                    isPaid ? Icons.check_circle_outline : Icons.receipt_outlined,
                    color: statusColor,
                    size: 20,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          invoice.invoiceNumber ?? '#${invoice.id}',
                          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                        ),
                        const SizedBox(width: 6),
                        if (invoice.orderNumber != null)
                          Text(
                            'Order #${invoice.orderNumber}',
                            style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                          ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      invoice.client?.name ?? 'No client',
                      style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${invoice.totalAmount.toStringAsFixed(2)}',
                      style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  StatusChip(status: statusLabel, color: statusColor),
                  if (!isPaid && !isCancelled && invoice.balanceDue > 0)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(
                        'Due: ${invoice.balanceDue.toStringAsFixed(2)}',
                        style: const TextStyle(fontSize: 11, color: VamsTheme.danger),
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
