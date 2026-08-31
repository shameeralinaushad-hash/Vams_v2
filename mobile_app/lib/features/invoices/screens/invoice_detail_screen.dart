import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme.dart';
import '../../../shared/widgets/status_chip.dart';
import '../models/invoice_models.dart';
import '../providers/invoices_provider.dart';

class InvoiceDetailScreen extends ConsumerWidget {
  final int invoiceId;

  const InvoiceDetailScreen({super.key, required this.invoiceId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final invoiceAsync = ref.watch(invoiceDetailProvider(invoiceId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Invoice'),
      ),
      body: invoiceAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
              const SizedBox(height: 12),
              const Text('Failed to load invoice', style: TextStyle(color: VamsTheme.textSecondary)),
              const SizedBox(height: 12),
              ElevatedButton(onPressed: () => ref.invalidate(invoiceDetailProvider(invoiceId)), child: const Text('Retry')),
            ],
          ),
        ),
        data: (invoice) {
          if (invoice == null) {
            return const Center(child: Text('Invoice not found'));
          }
          return _InvoiceDetailBody(invoiceId: invoiceId, invoice: invoice);
        },
      ),
    );
  }
}

class _InvoiceDetailBody extends StatelessWidget {
  final int invoiceId;
  final InvoiceDetail invoice;
  const _InvoiceDetailBody({required this.invoiceId, required this.invoice});

  @override
  Widget build(BuildContext context) {
    final isPaid = invoice.isFullyPaid;
    final isCancelled = invoice.status == 'cancelled';
    final statusColor = isCancelled
        ? VamsTheme.textMuted
        : isPaid
            ? VamsTheme.success
            : VamsTheme.danger;
    final statusLabel = isCancelled ? 'Cancelled' : isPaid ? 'Paid' : 'Unpaid';

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
                        invoice.invoiceNumber ?? 'Invoice #${invoice.id}',
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                      ),
                    ),
                    StatusChip(status: statusLabel, color: statusColor),
                  ],
                ),
                const SizedBox(height: 12),
                _InfoRow(label: 'Client', value: invoice.client?.name ?? 'No client'),
                _InfoRow(label: 'Order', value: invoice.order?.orderNumber ?? '-'),
                _InfoRow(label: 'Date', value: invoice.invoiceDate ?? '-'),
                _InfoRow(label: 'Total', value: '${invoice.totalAmount.toStringAsFixed(2)}'),
                _InfoRow(label: 'Paid', value: '${invoice.totalPaid.toStringAsFixed(2)}'),
                if (invoice.balanceDue > 0)
                  _InfoRow(label: 'Balance Due', value: '${invoice.balanceDue.toStringAsFixed(2)}', isWarning: true),
              ],
            ),
          ),
        ),

        if (invoice.lineItems.isNotEmpty) ...[
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Line Items (${invoice.lineItems.length})', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 8),
                  ...invoice.lineItems.map((li) => Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(color: VamsTheme.background, borderRadius: BorderRadius.circular(10)),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    li.description ?? '-',
                                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                                  ),
                                ),
                                Text(
                                  '${li.qty.toStringAsFixed(0)} ${li.unit ?? ''}',
                                  style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Row(
                              children: [
                                Text(
                                  '@ ${li.unitPrice.toStringAsFixed(2)}',
                                  style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                                ),
                                if (li.taxPercent > 0) ...[
                                  const SizedBox(width: 8),
                                  Text(
                                    '+${li.taxPercent.toStringAsFixed(1)}% tax',
                                    style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted),
                                  ),
                                ],
                              ],
                            ),
                          ],
                        ),
                      )),
                ],
              ),
            ),
          ),
        ],

        if (invoice.payments.isNotEmpty) ...[
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Payments (${invoice.payments.length})', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 8),
                  ...invoice.payments.map((p) => Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(color: VamsTheme.background, borderRadius: BorderRadius.circular(10)),
                        child: Row(
                          children: [
                            Container(
                              width: 32,
                              height: 32,
                              decoration: BoxDecoration(
                                color: VamsTheme.success.withOpacity(0.1),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: const Icon(Icons.payment, size: 16, color: VamsTheme.success),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    '${p.amount.toStringAsFixed(2)}',
                                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                                  ),
                                  Text(
                                    '${p.paidDate ?? '-'}${p.method != null && p.method!.isNotEmpty ? ' • ${p.method}' : ''}',
                                    style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      )),
                ],
              ),
            ),
          ),
        ],

        if (invoice.creditNotes.isNotEmpty) ...[
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Credit Notes (${invoice.creditNotes.length})', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 8),
                  ...invoice.creditNotes.map((c) => Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(color: VamsTheme.background, borderRadius: BorderRadius.circular(10)),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Text(c.creditNumber ?? '-', style: const TextStyle(fontWeight: FontWeight.w600)),
                                const SizedBox(width: 8),
                                Text('${c.amount.toStringAsFixed(2)}', style: const TextStyle(color: VamsTheme.danger)),
                              ],
                            ),
                            if (c.reason != null && c.reason!.isNotEmpty)
                              Text(c.reason!, style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
                          ],
                        ),
                      )),
                ],
              ),
            ),
          ),
        ],

        if (!isPaid && !isCancelled) ...[
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: () => _showAddPaymentSheet(context, invoiceId),
              icon: const Icon(Icons.payment, size: 18),
              label: const Text('Add Payment'),
            ),
          ),
        ],

        const SizedBox(height: 32),
      ],
    );
  }

  void _showAddPaymentSheet(BuildContext context, int invoiceId) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (context) => _AddPaymentSheet(invoiceId: invoiceId),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;
  final bool isWarning;
  const _InfoRow({required this.label, required this.value, this.isWarning = false});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          SizedBox(
            width: 100,
            child: Text(label, style: const TextStyle(fontSize: 13, color: VamsTheme.textMuted)),
          ),
          Expanded(
            child: Text(
              value,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: isWarning ? VamsTheme.danger : null,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _AddPaymentSheet extends ConsumerStatefulWidget {
  final int invoiceId;
  const _AddPaymentSheet({required this.invoiceId});

  @override
  ConsumerState<_AddPaymentSheet> createState() => _AddPaymentSheetState();
}

class _AddPaymentSheetState extends ConsumerState<_AddPaymentSheet> {
  final _amountCtrl = TextEditingController();
  final _methodCtrl = TextEditingController();
  final _notesCtrl = TextEditingController();
  bool _saving = false;

  @override
  void dispose() {
    _amountCtrl.dispose();
    _methodCtrl.dispose();
    _notesCtrl.dispose();
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
            const Text('Add Payment', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
            const SizedBox(height: 16),
            TextField(
              controller: _amountCtrl,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Amount', isDense: true),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _methodCtrl,
              decoration: const InputDecoration(labelText: 'Method (e.g. Bank, Cash)', isDense: true),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _notesCtrl,
              decoration: const InputDecoration(labelText: 'Notes', isDense: true),
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Save'),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }

  Future<void> _save() async {
    final amount = double.tryParse(_amountCtrl.text.trim());
    if (amount == null || amount <= 0) return;

    setState(() => _saving = true);

    final data = {
      'amount': amount,
      'method': _methodCtrl.text.trim().isEmpty ? null : _methodCtrl.text.trim(),
      'notes': _notesCtrl.text.trim().isEmpty ? null : _notesCtrl.text.trim(),
    };

    final result = await ref
        .read(invoicesProvider.notifier)
        .addPayment(widget.invoiceId, data);

    if (mounted) {
      Navigator.of(context).pop();
      if (result != null) {
        ref.invalidate(invoiceDetailProvider(widget.invoiceId));
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Payment added')),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to add payment')),
        );
      }
    }
  }
}
