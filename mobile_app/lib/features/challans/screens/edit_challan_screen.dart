import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../../orders/providers/orders_provider.dart';

class EditChallanScreen extends ConsumerStatefulWidget {
  final int challanId;
  final int orderId;
  const EditChallanScreen({super.key, required this.challanId, required this.orderId});

  @override
  ConsumerState<EditChallanScreen> createState() => _EditChallanScreenState();
}

class _EditChallanScreenState extends ConsumerState<EditChallanScreen> {
  final _formKey = GlobalKey<FormState>();
  final _recipientCtrl = TextEditingController();
  final _dateCtrl = TextEditingController();
  final _transportCtrl = TextEditingController();
  final _vehicleCtrl = TextEditingController();
  final _placeCtrl = TextEditingController();
  List<_LineItemForm> _items = [];
  bool _saving = false;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadChallan();
  }

  Future<void> _loadChallan() async {
    try {
      final dio = ref.read(apiClientProvider);
      final response = await dio.get('/api/v1/challans/${widget.challanId}');
      if (response.data['success'] == true) {
        final c = response.data['challan'];
        _recipientCtrl.text = c['recipient'] ?? '';
        _dateCtrl.text = c['dispatch_date'] ?? '';
        _transportCtrl.text = c['transport_mode'] ?? '';
        _vehicleCtrl.text = c['vehicle_number'] ?? '';
        _placeCtrl.text = c['place'] ?? '';
        _items = (c['line_items'] as List).map((li) => _LineItemForm(
          descCtrl: TextEditingController(text: li['description'] ?? ''),
          partNoCtrl: TextEditingController(text: li['part_no'] ?? ''),
          unitCtrl: TextEditingController(text: li['unit'] ?? ''),
          qtyCtrl: TextEditingController(text: (li['qty'] ?? 0).toString()),
        )).toList();
        if (_items.isEmpty) _items = [_LineItemForm()];
      }
    } on DioException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.response?.data?['message'] ?? 'Failed to load challan')),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _recipientCtrl.dispose();
    _dateCtrl.dispose();
    _transportCtrl.dispose();
    _vehicleCtrl.dispose();
    _placeCtrl.dispose();
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
              })
          .toList();

      final dio = ref.read(apiClientProvider);
      final response = await dio.put('/api/v1/challans/${widget.challanId}', data: {
        'recipient': _recipientCtrl.text.trim().isEmpty ? null : _recipientCtrl.text.trim(),
        'dispatch_date': _dateCtrl.text,
        'transport_mode': _transportCtrl.text.trim().isEmpty ? null : _transportCtrl.text.trim(),
        'vehicle_number': _vehicleCtrl.text.trim().isEmpty ? null : _vehicleCtrl.text.trim(),
        'place': _placeCtrl.text.trim().isEmpty ? null : _placeCtrl.text.trim(),
        'items': lineItems,
      });

      if (mounted) {
        if (response.data['success'] == true) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Challan updated')));
          ref.invalidate(orderDetailProvider(widget.orderId));
          context.pop();
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(response.data['message'] ?? 'Failed to update challan')),
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
        appBar: AppBar(title: const Text('Edit Challan')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Edit Challan')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextFormField(
              controller: _recipientCtrl,
              decoration: _inputDecoration('Recipient', Icons.person_outline),
              maxLines: 2,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _dateCtrl,
              decoration: _inputDecoration('Dispatch Date', Icons.calendar_today),
              readOnly: true,
              onTap: _pickDate,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _transportCtrl,
              decoration: _inputDecoration('Transport Mode', Icons.local_shipping),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(child: TextFormField(
                  controller: _vehicleCtrl,
                  decoration: _inputDecoration('Vehicle Number', Icons.directions_car),
                )),
                const SizedBox(width: 12),
                Expanded(child: TextFormField(
                  controller: _placeCtrl,
                  decoration: _inputDecoration('Place', Icons.location_on),
                )),
              ],
            ),

            const SizedBox(height: 24),
            const Text('Line Items', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            const SizedBox(height: 8),
            ...List.generate(_items.length, (i) => _buildItemCard(i)),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () => setState(() => _items.add(_LineItemForm())),
              icon: const Icon(Icons.add, size: 18),
              label: const Text('Add Item'),
              style: OutlinedButton.styleFrom(
                foregroundColor: VamsTheme.primary,
                side: const BorderSide(color: VamsTheme.primary),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),

            const SizedBox(height: 24),
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
                    : const Text('Save Changes'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  InputDecoration _inputDecoration(String label, IconData icon) {
    return InputDecoration(
      labelText: label,
      prefixIcon: Icon(icon, size: 20, color: VamsTheme.textMuted),
      filled: true,
      fillColor: Theme.of(context).colorScheme.surfaceContainerHighest.withOpacity(0.3),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: VamsTheme.primary, width: 2)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    );
  }

  Widget _buildItemCard(int index) {
    final item = _items[index];
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            Row(
              children: [
                Text('${index + 1}', style: const TextStyle(fontWeight: FontWeight.w600)),
                const SizedBox(width: 8),
                Expanded(
                  child: TextFormField(
                    controller: item.descCtrl,
                    decoration: const InputDecoration(isDense: true, hintText: 'Description *'),
                    validator: (v) => index == 0 ? (v == null || v.trim().isEmpty ? 'Required' : null) : null,
                  ),
                ),
                if (_items.length > 1)
                  IconButton(
                    icon: const Icon(Icons.delete_outline, size: 18, color: VamsTheme.danger),
                    onPressed: () => setState(() => _items.removeAt(index)),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    controller: item.partNoCtrl,
                    decoration: const InputDecoration(isDense: true, hintText: 'Part No'),
                  ),
                ),
                const SizedBox(width: 8),
                SizedBox(
                  width: 70,
                  child: TextFormField(
                    controller: item.unitCtrl,
                    decoration: const InputDecoration(isDense: true, hintText: 'Unit'),
                  ),
                ),
                const SizedBox(width: 8),
                SizedBox(
                  width: 60,
                  child: TextFormField(
                    controller: item.qtyCtrl,
                    decoration: const InputDecoration(isDense: true, hintText: 'Qty'),
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  ),
                ),
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

  _LineItemForm({
    TextEditingController? descCtrl,
    TextEditingController? partNoCtrl,
    TextEditingController? unitCtrl,
    TextEditingController? qtyCtrl,
  })  : descCtrl = descCtrl ?? TextEditingController(),
        partNoCtrl = partNoCtrl ?? TextEditingController(),
        unitCtrl = unitCtrl ?? TextEditingController(),
        qtyCtrl = qtyCtrl ?? TextEditingController(text: '0');

  void dispose() {
    descCtrl.dispose();
    partNoCtrl.dispose();
    unitCtrl.dispose();
    qtyCtrl.dispose();
  }
}
