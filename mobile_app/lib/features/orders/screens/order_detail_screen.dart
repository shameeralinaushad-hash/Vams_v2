import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../../core/api_client.dart';
import '../../../core/storage.dart';
import '../../../core/theme.dart';
import '../../../shared/widgets/status_chip.dart';
import '../models/order_models.dart';
import '../providers/orders_provider.dart';

const List<String> _validStatuses = [
  'Pending',
  'In Progress',
  'PO Received',
  'Delivered',
  'Cancelled',
  'On Hold',
];

class OrderDetailScreen extends ConsumerWidget {
  final int orderId;

  const OrderDetailScreen({super.key, required this.orderId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final orderAsync = ref.watch(orderDetailProvider(orderId));

    return Scaffold(
      appBar: AppBar(
        title: Text('Order #${orderId}'),
      ),
      body: orderAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
              const SizedBox(height: 12),
              Text('Failed to load order', style: const TextStyle(color: VamsTheme.textSecondary)),
              const SizedBox(height: 12),
              ElevatedButton(onPressed: () => ref.invalidate(orderDetailProvider(orderId)), child: const Text('Retry')),
            ],
          ),
        ),
        data: (order) {
          if (order == null) {
            return const Center(child: Text('Order not found'));
          }
          debugPrint('[ORDER_DETAIL] Order ${order.id}: quotations=${order.quotations.length}, invoices=${order.invoices.length}, challans=${order.deliveryChallans.length}, po=${order.purchaseOrder != null}');
          return _OrderDetailBody(order: order, ref: ref);
        },
      ),
    );
  }
}

class _OrderDetailBody extends StatelessWidget {
  final OrderDetail order;
  final WidgetRef ref;
  const _OrderDetailBody({required this.order, required this.ref});

  @override
  Widget build(BuildContext context) {
    debugPrint('[ORDER_DETAIL] Building body: title=${order.title}, status=${order.status}, quotations=${order.quotations.length}, invoices=${order.invoices.length}, challans=${order.deliveryChallans.length}');
    final status = order.status ?? 'Pending';
    final statusColor = status == 'Delivered'
        ? VamsTheme.success
        : status == 'PO Received'
            ? VamsTheme.primary
            : VamsTheme.warning;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        order.title ?? 'Untitled Order',
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                      ),
                    ),
                    StatusChip(status: status, color: statusColor),
                  ],
                ),
                const SizedBox(height: 12),
                _InfoRow(label: 'Client', value: order.client?.name ?? 'No client'),
                _InfoRow(label: 'Inquiry Date', value: order.inquiryDate ?? '-'),
                if (order.notes != null && order.notes!.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  const Text('Notes', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: VamsTheme.textMuted)),
                  const SizedBox(height: 4),
                  Text(order.notes!, style: const TextStyle(fontSize: 13)),
                ],
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () => context.push('/orders/${order.id}/edit', extra: order),
                        icon: const Icon(Icons.edit, size: 16),
                        label: const Text('Edit Order'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () => _showStatusDialog(context),
                        icon: const Icon(Icons.swap_horiz, size: 16),
                        label: const Text('Status'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    OutlinedButton.icon(
                      onPressed: () => _confirmDelete(context),
                      icon: const Icon(Icons.delete_outline, size: 16, color: VamsTheme.danger),
                      label: const Text('Delete', style: TextStyle(color: VamsTheme.danger)),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),

        if (order.purchaseOrder != null) ...[
          const SizedBox(height: 8),
          ExpansionTile(
            tilePadding: const EdgeInsets.symmetric(horizontal: 16),
            childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: const Text('Purchase Order', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            children: [
              _InfoRow(label: 'PO Number', value: order.purchaseOrder!.poNumber ?? '-'),
              _InfoRow(label: 'Status', value: order.purchaseOrder!.status ?? '-'),
              if (order.purchaseOrder!.totalAmount != null)
                _InfoRow(label: 'Amount', value: order.purchaseOrder!.totalAmount!.toStringAsFixed(2)),
            ],
          ),
        ],

        if (order.quotations.isNotEmpty) ...[
          const SizedBox(height: 8),
          ExpansionTile(
            tilePadding: const EdgeInsets.symmetric(horizontal: 16),
            childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: Text('Quotations (${order.quotations.length})', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            children: [
              ...order.quotations.map((q) => _QuotationTile(quotation: q, orderId: order.id)),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: () => context.push('/orders/${order.id}/quotations/create'),
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('Add Quotation'),
                ),
              ),
            ],
          ),
        ] else ...[
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.add_circle_outline, color: VamsTheme.primary),
              title: const Text('Add Quotation'),
              subtitle: const Text('Create a new quotation for this order'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => context.push('/orders/${order.id}/quotations/create'),
            ),
          ),
        ],

        if (order.invoices.isNotEmpty) ...[
          const SizedBox(height: 8),
          ExpansionTile(
            tilePadding: const EdgeInsets.symmetric(horizontal: 16),
            childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: Text('Invoices (${order.invoices.length})', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            children: [
              ...order.invoices.map((inv) => _InvoiceTile(invoice: inv, orderId: order.id)),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: () => context.push('/orders/${order.id}/invoices/create'),
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('Add Invoice'),
                ),
              ),
            ],
          ),
        ] else ...[
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.add_circle_outline, color: VamsTheme.primary),
              title: const Text('Add Invoice'),
              subtitle: const Text('Create a new invoice for this order'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => context.push('/orders/${order.id}/invoices/create'),
            ),
          ),
        ],

        if (order.deliveryChallans.isNotEmpty) ...[
          const SizedBox(height: 8),
          ExpansionTile(
            tilePadding: const EdgeInsets.symmetric(horizontal: 16),
            childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: Text('Delivery Challans (${order.deliveryChallans.length})', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            children: [
              ...order.deliveryChallans.map((c) => _ChallanTile(challan: c, orderId: order.id)),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: () => context.push('/orders/${order.id}/challans/create'),
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('Add Delivery Challan'),
                ),
              ),
            ],
          ),
        ] else ...[
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.add_circle_outline, color: VamsTheme.primary),
              title: const Text('Add Delivery Challan'),
              subtitle: const Text('Create a new delivery challan for this order'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => context.push('/orders/${order.id}/challans/create'),
            ),
          ),
        ],

        const SizedBox(height: 32),
      ],
    );
  }

  void _showStatusDialog(BuildContext context) {
    final currentStatus = order.status ?? 'Pending';
    String selectedStatus = currentStatus;

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Change Status'),
        content: StatefulBuilder(
          builder: (ctx, setDialogState) => DropdownButton<String>(
            value: selectedStatus,
            isExpanded: true,
            items: _validStatuses.map((s) => DropdownMenuItem(value: s, child: Text(s))).toList(),
            onChanged: (v) => setDialogState(() => selectedStatus = v!),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          TextButton(
            onPressed: () async {
              Navigator.pop(ctx);
              if (selectedStatus != currentStatus) {
                await _changeStatus(context, selectedStatus);
              }
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }

  Future<void> _changeStatus(BuildContext context, String status) async {
    try {
      final dio = ref.read(apiClientProvider);
      await changeOrderStatus(dio, order.id, status);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Status changed to $status')));
        ref.invalidate(orderDetailProvider(order.id));
        ref.read(ordersProvider.notifier).refreshOrders();
      }
    } on DioException catch (e) {
      if (context.mounted) {
        final msg = e.response?.data is Map ? (e.response?.data['message'] ?? 'Error') : 'Error';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      }
    }
  }

  void _confirmDelete(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Order'),
        content: Text('Are you sure you want to delete Order #${order.orderNumber ?? order.id}? This cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          TextButton(
            onPressed: () async {
              Navigator.pop(ctx);
              await _deleteOrder(context);
            },
            child: const Text('Delete', style: TextStyle(color: VamsTheme.danger)),
          ),
        ],
      ),
    );
  }

  Future<void> _deleteOrder(BuildContext context) async {
    try {
      final dio = ref.read(apiClientProvider);
      await deleteOrder(dio, order.id);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Order deleted')));
        ref.read(ordersProvider.notifier).refreshOrders();
        context.go('/orders');
      }
    } on DioException catch (e) {
      if (context.mounted) {
        final msg = e.response?.data is Map ? (e.response?.data['message'] ?? 'Error') : 'Error';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      }
    }
  }
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;
  const _InfoRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          SizedBox(
            width: 110,
            child: Text(label, style: const TextStyle(fontSize: 13, color: VamsTheme.textMuted)),
          ),
          Expanded(child: Text(value, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600))),
        ],
      ),
    );
  }
}

Future<void> _launchPdf(String? pdfPath, BuildContext context) async {
  if (pdfPath == null || pdfPath.isEmpty) return;
  final serverUrl = await AppStorage.getServerUrl();
  if (serverUrl == null) return;
  final fullUrl = '$serverUrl/$pdfPath';
  final uri = Uri.parse(fullUrl);
  if (await canLaunchUrl(uri)) {
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }
}

class _QuotationTile extends StatelessWidget {
  final QuotationInfo quotation;
  final int orderId;
  const _QuotationTile({required this.quotation, required this.orderId});

  @override
  Widget build(BuildContext context) {
    final docType = quotation.docType ?? 'commercial';
    final docColor = docType == 'technical' ? VamsTheme.warning : VamsTheme.primary;

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 4),
      leading: StatusChip(status: docType, color: docColor),
      title: Text(quotation.quoteNumber ?? '-', style: const TextStyle(fontWeight: FontWeight.w600)),
      subtitle: Text(quotation.quoteDate ?? '-', style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (quotation.pdfPath != null)
            IconButton(
              icon: const Icon(Icons.picture_as_pdf, size: 20),
              onPressed: () => _launchPdf(quotation.pdfPath, context),
            ),
          IconButton(
            icon: const Icon(Icons.edit_outlined, size: 20),
            onPressed: () => context.push('/orders/$orderId/quotations/${quotation.id}/edit'),
          ),
        ],
      ),
      onTap: quotation.pdfPath != null ? () => _launchPdf(quotation.pdfPath, context) : null,
    );
  }
}

class _InvoiceTile extends StatelessWidget {
  final InvoiceInfo invoice;
  final int orderId;
  const _InvoiceTile({required this.invoice, required this.orderId});

  @override
  Widget build(BuildContext context) {
    final isPaid = invoice.isFullyPaid ?? false;
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 4),
      leading: StatusChip(
        status: isPaid ? 'Paid' : 'Unpaid',
        color: isPaid ? VamsTheme.success : VamsTheme.danger,
      ),
      title: Text(invoice.invoiceNumber ?? '-', style: const TextStyle(fontWeight: FontWeight.w600)),
      subtitle: Text(
        '${invoice.invoiceDate ?? '-'}${invoice.totalAmount != null ? ' • ${invoice.totalAmount!.toStringAsFixed(2)}' : ''}',
        style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (invoice.pdfPath != null)
            IconButton(
              icon: const Icon(Icons.picture_as_pdf, size: 20),
              onPressed: () => _launchPdf(invoice.pdfPath, context),
            ),
          IconButton(
            icon: const Icon(Icons.edit_outlined, size: 20),
            onPressed: () => context.push('/orders/$orderId/invoices/${invoice.id}/edit'),
          ),
        ],
      ),
      onTap: invoice.pdfPath != null ? () => _launchPdf(invoice.pdfPath, context) : null,
    );
  }
}

class _ChallanTile extends StatelessWidget {
  final ChallanInfo challan;
  final int orderId;
  const _ChallanTile({required this.challan, required this.orderId});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 4),
      leading: Container(
        width: 32,
        height: 32,
        decoration: BoxDecoration(
          color: VamsTheme.primary.withOpacity(0.1),
          borderRadius: BorderRadius.circular(8),
        ),
        child: const Icon(Icons.local_shipping, size: 16, color: VamsTheme.primary),
      ),
      title: Text(challan.challanNumber ?? '-', style: const TextStyle(fontWeight: FontWeight.w600)),
      subtitle: Text(
        '${challan.dispatchDate ?? '-'}${challan.transportMode != null ? ' • ${challan.transportMode}' : ''}',
        style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (challan.pdfPath != null)
            IconButton(
              icon: const Icon(Icons.picture_as_pdf, size: 20),
              onPressed: () => _launchPdf(challan.pdfPath, context),
            ),
          IconButton(
            icon: const Icon(Icons.edit_outlined, size: 20),
            onPressed: () => context.push('/orders/$orderId/challans/${challan.id}/edit'),
          ),
        ],
      ),
      onTap: challan.pdfPath != null ? () => _launchPdf(challan.pdfPath, context) : null,
    );
  }
}
