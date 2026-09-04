import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../../shared/widgets/status_chip.dart';
import '../providers/orders_provider.dart';

class OrdersListScreen extends ConsumerStatefulWidget {
  const OrdersListScreen({super.key});

  @override
  ConsumerState<OrdersListScreen> createState() => _OrdersListScreenState();
}

class _OrdersListScreenState extends ConsumerState<OrdersListScreen> {
  final _searchController = TextEditingController();
  final _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 200) {
      ref.read(ordersProvider.notifier).loadMore();
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(ordersProvider);

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: TextField(
            controller: _searchController,
            decoration: InputDecoration(
              hintText: 'Search orders...',
              prefixIcon: const Icon(Icons.search, size: 20),
              suffixIcon: _searchController.text.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.clear, size: 18),
                      onPressed: () {
                        _searchController.clear();
                        ref.read(ordersProvider.notifier).searchOrders('');
                      },
                    )
                  : null,
              isDense: true,
            ),
            onChanged: (v) {
              setState(() {});
              ref.read(ordersProvider.notifier).searchOrders(v);
            },
          ),
        ),
        SizedBox(
          height: 48,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            children: [
              _FilterChip(label: 'All', selected: state.statusFilter == null, onTap: () => ref.read(ordersProvider.notifier).filterByStatus(null)),
              const SizedBox(width: 8),
              _FilterChip(label: 'Pending', selected: state.statusFilter == 'Pending', onTap: () => ref.read(ordersProvider.notifier).filterByStatus('Pending')),
              const SizedBox(width: 8),
              _FilterChip(label: 'PO Received', selected: state.statusFilter == 'PO Received', onTap: () => ref.read(ordersProvider.notifier).filterByStatus('PO Received')),
              const SizedBox(width: 8),
              _FilterChip(label: 'Delivered', selected: state.statusFilter == 'Delivered', onTap: () => ref.read(ordersProvider.notifier).filterByStatus('Delivered')),
            ],
          ),
        ),
        if (state.isLoading && state.orders.isEmpty)
          const Expanded(child: Center(child: CircularProgressIndicator()))
        else if (state.error != null && state.orders.isEmpty)
          Expanded(
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
                  const SizedBox(height: 12),
                  Text(state.error!, style: const TextStyle(color: VamsTheme.textSecondary)),
                  const SizedBox(height: 12),
                  ElevatedButton(onPressed: () => ref.read(ordersProvider.notifier).refreshOrders(), child: const Text('Retry')),
                ],
              ),
            ),
          )
        else if (state.orders.isEmpty)
          const Expanded(
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.inbox_outlined, size: 48, color: VamsTheme.textMuted),
                  SizedBox(height: 12),
                  Text('No orders found', style: TextStyle(color: VamsTheme.textSecondary)),
                ],
              ),
            ),
          )
        else
          Expanded(
            child: RefreshIndicator(
              onRefresh: () => ref.read(ordersProvider.notifier).refreshOrders(),
              child: ListView.builder(
                controller: _scrollController,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                itemCount: state.orders.length + (state.currentPage < state.pages ? 1 : 0),
                itemBuilder: (context, index) {
                  if (index == state.orders.length) {
                    return const Padding(
                      padding: EdgeInsets.all(16),
                      child: Center(child: CircularProgressIndicator()),
                    );
                  }
                  final order = state.orders[index];
                  return _OrderCard(
                    order: order,
                    onTap: () => context.push('/orders/${order.id}'),
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

class _OrderCard extends StatelessWidget {
  final dynamic order;
  final VoidCallback onTap;

  const _OrderCard({required this.order, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final status = order.status ?? 'Pending';
    final statusColor = status == 'Delivered'
        ? VamsTheme.success
        : status == 'PO Received'
            ? VamsTheme.primary
            : VamsTheme.warning;

    final poCount = order.purchaseOrders.length;
    final firstPo = poCount > 0 ? order.purchaseOrders.first : null;

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
                  child: Text(
                    (order.client?.name ?? '?')[0].toUpperCase(),
                    style: TextStyle(color: statusColor, fontWeight: FontWeight.w700, fontSize: 16),
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
                          '#${order.orderNumber ?? order.id}',
                          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            order.title ?? 'Untitled',
                            style: const TextStyle(fontSize: 14),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      order.client?.name ?? 'No client',
                      style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                    ),
                    if (poCount > 0) ...[
                      const SizedBox(height: 2),
                      Text(
                        poCount == 1
                            ? 'PO: ${firstPo?.poNumber ?? '-'}'
                            : '$poCount POs: ${firstPo?.poNumber ?? '-'}',
                        style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted),
                      ),
                    ],
                  ],
                ),
              ),
              StatusChip(status: status, color: statusColor),
            ],
          ),
        ),
      ),
    );
  }
}
