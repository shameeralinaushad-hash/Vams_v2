import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../../orders/providers/orders_provider.dart';

class EditQuotationScreen extends ConsumerStatefulWidget {
  final int quotationId;
  final int orderId;
  const EditQuotationScreen({super.key, required this.quotationId, required this.orderId});

  @override
  ConsumerState<EditQuotationScreen> createState() => _EditQuotationScreenState();
}

class _EditQuotationScreenState extends ConsumerState<EditQuotationScreen> {
  final _formKey = GlobalKey<FormState>();
  final _subjectCtrl = TextEditingController();
  final _recipientCtrl = TextEditingController();
  final _dateCtrl = TextEditingController();
  final _termsCtrl = TextEditingController();
  final _taxAmountCtrl = TextEditingController(text: '0');
  final _discountAmountCtrl = TextEditingController(text: '0');
  final _installationCtrl = TextEditingController(text: '0');
  final _transportCtrl = TextEditingController(text: '0');
  List<_LineItemForm> _items = [];
  bool _saving = false;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadQuotation();
  }

  Future<void> _loadQuotation() async {
    try {
      final dio = ref.read(apiClientProvider);
      final response = await dio.get('/api/v1/quotations/${widget.quotationId}');
      if (response.data['success'] == true) {
        final q = response.data['quotation'];
        _subjectCtrl.text = q['subject'] ?? '';
        _recipientCtrl.text = q['recipient'] ?? '';
        _dateCtrl.text = q['quote_date'] ?? '';
        _termsCtrl.text = q['terms_conditions'] ?? '';
        _taxAmountCtrl.text = (q['tax_amount'] ?? 0).toString();
        _discountAmountCtrl.text = (q['discount_amount'] ?? 0).toString();
        _installationCtrl.text = (q['installation_charges'] ?? 0).toString();
        _transportCtrl.text = (q['transportation_charges'] ?? 0).toString();
        _items = (q['line_items'] as List).map((li) => _LineItemForm(
          descCtrl: TextEditingController(text: li['description'] ?? ''),
          partNoCtrl: TextEditingController(text: li['part_no'] ?? ''),
          unitCtrl: TextEditingController(text: li['unit'] ?? ''),
          qtyCtrl: TextEditingController(text: (li['qty'] ?? 0).toString()),
          priceCtrl: TextEditingController(text: (li['unit_price'] ?? 0).toString()),
          taxCtrl: TextEditingController(text: (li['tax_percent'] ?? 0).toString()),
        )).toList();
        if (_items.isEmpty) _items = [_LineItemForm()];
      }
    } on DioException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.response?.data?['message'] ?? 'Failed to load quotation')),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _subjectCtrl.dispose();
    _recipientCtrl.dispose();
    _dateCtrl.dispose();
    _termsCtrl.dispose();
    _taxAmountCtrl.dispose();
    _discountAmountCtrl.dispose();
    _installationCtrl.dispose();
    _transportCtrl.dispose();
    for (final item in _items) {
      item.dispose();
    }
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime.tryParse(_dateCtrl.text) ?? DateTime.now(),
      firstDate: DateTime(2020),
      lastDate: DateTime(2030),
    );
    if (picked != null) {
      _dateCtrl.text = picked.toIso8601String().split('T').first;
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _saving = true);

    try {
      final lineItems = _items
          .where((item) => item.descCtrl.text.trim().isNotEmpty)
          .map((item) => {
                'description': item.descCtrl.text.trim(),
                'part_no': item.partNoCtrl.text.trim().isEmpty ? null : item.partNoCtrl.text.trim(),
                'unit': item.unitCtrl.text.trim().isEmpty ? null : item.unitCtrl.text.trim(),
                'qty': double.tryParse(item.qtyCtrl.text) ?? 0,
                'unit_price': double.tryParse(item.priceCtrl.text) ?? 0,
                'tax_percent': double.tryParse(item.taxCtrl.text) ?? 0,
              })
          .toList();

      final dio = ref.read(apiClientProvider);
      final response = await dio.put('/api/v1/quotations/${widget.quotationId}', data: {
        'subject': _subjectCtrl.text.trim().isEmpty ? null : _subjectCtrl.text.trim(),
        'recipient': _recipientCtrl.text.trim().isEmpty ? null : _recipientCtrl.text.trim(),
        'quote_date': _dateCtrl.text,
        'terms_conditions': _termsCtrl.text.trim().isEmpty ? null : _termsCtrl.text.trim(),
        'tax_amount': double.tryParse(_taxAmountCtrl.text) ?? 0,
        'discount_amount': double.tryParse(_discountAmountCtrl.text) ?? 0,
        'installation_charges': double.tryParse(_installationCtrl.text) ?? 0,
        'transportation_charges': double.tryParse(_transportCtrl.text) ?? 0,
        'items': lineItems,
      });

      if (mounted) {
        if (response.data['success'] == true) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Quotation updated')));
          ref.invalidate(orderDetailProvider(widget.orderId));
          if (mounted) context.pop();
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(response.data['message'] ?? 'Failed to update quotation')),
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
    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: const Text('Edit Quotation')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Edit Quotation')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _sectionHeader('Quotation Details'),
            const SizedBox(height: 12),
            TextFormField(
              controller: _subjectCtrl,
              decoration: _inputDecoration('Subject', Icons.subject),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _recipientCtrl,
              decoration: _inputDecoration('Recipient / Bill To', Icons.person_outline),
              maxLines: 2,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _dateCtrl,
              decoration: _inputDecoration('Date', Icons.calendar_today),
              readOnly: true,
              onTap: _pickDate,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _termsCtrl,
              decoration: _inputDecoration('Terms & Conditions', Icons.gavel),
              maxLines: 3,
            ),

            const SizedBox(height: 28),
            _sectionHeader('Line Items'),
            const SizedBox(height: 4),
            Text('Tap + to add items. Swipe left to remove.', style: TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
            const SizedBox(height: 12),
            ...List.generate(_items.length, (i) => _buildItemCard(i)),

            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () => setState(() => _items.add(_LineItemForm())),
              icon: const Icon(Icons.add, size: 18),
              label: const Text('Add Line Item'),
              style: OutlinedButton.styleFrom(
                foregroundColor: VamsTheme.primary,
                side: const BorderSide(color: VamsTheme.primary),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                padding: const EdgeInsets.symmetric(vertical: 12),
              ),
            ),

            const SizedBox(height: 28),
            _sectionHeader('Additional Charges'),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(child: TextFormField(
                  controller: _taxAmountCtrl,
                  decoration: _inputDecoration('Tax Amount', Icons.receipt, prefix: 'Rs '),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                )),
                const SizedBox(width: 12),
                Expanded(child: TextFormField(
                  controller: _discountAmountCtrl,
                  decoration: _inputDecoration('Discount', Icons.discount, prefix: 'Rs '),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                )),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(child: TextFormField(
                  controller: _installationCtrl,
                  decoration: _inputDecoration('Installation', Icons.build, prefix: 'Rs '),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                )),
                const SizedBox(width: 12),
                Expanded(child: TextFormField(
                  controller: _transportCtrl,
                  decoration: _inputDecoration('Transportation', Icons.local_shipping, prefix: 'Rs '),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                )),
              ],
            ),

            const SizedBox(height: 32),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: ElevatedButton(
                onPressed: _saving ? null : _submit,
                style: ElevatedButton.styleFrom(
                  backgroundColor: VamsTheme.primary,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                child: _saving
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Text('Save Changes', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
              ),
            ),
            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }

  Widget _sectionHeader(String title) {
    return Row(
      children: [
        Container(width: 4, height: 16, decoration: BoxDecoration(color: VamsTheme.primary, borderRadius: BorderRadius.circular(2))),
        const SizedBox(width: 8),
        Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
      ],
    );
  }

  InputDecoration _inputDecoration(String label, IconData icon, {String? prefix}) {
    return InputDecoration(
      labelText: label,
      prefixIcon: Icon(icon, size: 20, color: VamsTheme.textMuted),
      prefixText: prefix,
      filled: true,
      fillColor: Theme.of(context).colorScheme.surfaceContainerHighest.withOpacity(0.3),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: Colors.grey.shade300),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: Colors.grey.shade300),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: VamsTheme.primary, width: 2),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    );
  }

  Widget _buildItemCard(int index) {
    final item = _items[index];
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 1,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 28,
                  height: 28,
                  decoration: BoxDecoration(color: VamsTheme.primary.withOpacity(0.1), borderRadius: BorderRadius.circular(8)),
                  child: Center(child: Text('${index + 1}', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: VamsTheme.primary))),
                ),
                const SizedBox(width: 8),
                const Text('Item', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                const Spacer(),
                if (_items.length > 1)
                  IconButton(
                    icon: const Icon(Icons.delete_outline, size: 20, color: VamsTheme.danger),
                    onPressed: () => setState(() => _items.removeAt(index)),
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ),
            const SizedBox(height: 10),
            TextFormField(
              controller: item.descCtrl,
              decoration: _inputDecoration('Description *', Icons.description),
              validator: (v) => index == 0 ? (v == null || v.trim().isEmpty ? 'Required' : null) : null,
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(child: TextFormField(
                  controller: item.partNoCtrl,
                  decoration: _inputDecoration('Part No.', Icons.qr_code),
                )),
                const SizedBox(width: 10),
                Expanded(child: TextFormField(
                  controller: item.unitCtrl,
                  decoration: _inputDecoration('Unit', Icons.straighten),
                )),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(child: TextFormField(
                  controller: item.qtyCtrl,
                  decoration: _inputDecoration('Qty', Icons.numbers),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                )),
                const SizedBox(width: 10),
                Expanded(child: TextFormField(
                  controller: item.priceCtrl,
                  decoration: _inputDecoration('Unit Price', Icons.attach_money),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                )),
                const SizedBox(width: 10),
                Expanded(child: TextFormField(
                  controller: item.taxCtrl,
                  decoration: _inputDecoration('Tax %', Icons.percent),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                )),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _LineItemForm {
  late final TextEditingController descCtrl;
  late final TextEditingController partNoCtrl;
  late final TextEditingController unitCtrl;
  late final TextEditingController qtyCtrl;
  late final TextEditingController priceCtrl;
  late final TextEditingController taxCtrl;

  _LineItemForm({
    TextEditingController? descCtrl,
    TextEditingController? partNoCtrl,
    TextEditingController? unitCtrl,
    TextEditingController? qtyCtrl,
    TextEditingController? priceCtrl,
    TextEditingController? taxCtrl,
  })  : descCtrl = descCtrl ?? TextEditingController(),
        partNoCtrl = partNoCtrl ?? TextEditingController(),
        unitCtrl = unitCtrl ?? TextEditingController(),
        qtyCtrl = qtyCtrl ?? TextEditingController(text: '0'),
        priceCtrl = priceCtrl ?? TextEditingController(text: '0'),
        taxCtrl = taxCtrl ?? TextEditingController(text: '0');

  void dispose() {
    descCtrl.dispose();
    partNoCtrl.dispose();
    unitCtrl.dispose();
    qtyCtrl.dispose();
    priceCtrl.dispose();
    taxCtrl.dispose();
  }
}
