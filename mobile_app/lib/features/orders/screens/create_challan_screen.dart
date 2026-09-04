import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../models/order_models.dart';
import '../providers/orders_provider.dart';

class CreateChallanScreen extends ConsumerStatefulWidget {
  final int orderId;
  const CreateChallanScreen({super.key, required this.orderId});

  @override
  ConsumerState<CreateChallanScreen> createState() => _CreateChallanScreenState();
}

class _CreateChallanScreenState extends ConsumerState<CreateChallanScreen> {
  final _formKey = GlobalKey<FormState>();
  final _recipientCtrl = TextEditingController();
  final _dateCtrl = TextEditingController();
  final _transportModeCtrl = TextEditingController();
  final _vehicleCtrl = TextEditingController();
  final _placeCtrl = TextEditingController();
  List<_ChallanItemForm> _items = [_ChallanItemForm()];
  bool _saving = false;
  bool _loading = true;

  List<PurchaseOrderInfo> _purchaseOrders = [];
  int? _selectedPoId;

  @override
  void initState() {
    super.initState();
    _dateCtrl.text = DateTime.now().toIso8601String().split('T').first;
    _prefillFromOrder();
  }

  Future<void> _prefillFromOrder() async {
    try {
      final dio = ref.read(apiClientProvider);
      final response = await dio.get('/api/v1/orders/${widget.orderId}');
      final order = response.data;
      if (order == null) return;

      final poList = (order['purchase_orders'] as List? ?? [])
          .map((p) => PurchaseOrderInfo.fromJson(p))
          .toList();
      _purchaseOrders = poList;

      if (poList.isNotEmpty) {
        _selectedPoId = poList.first.id;
        _prefillItemsFromPo(poList.first);
      } else {
        _prefillFromQuotation(order);
      }
    } catch (_) {
      // Silently keep default empty item
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _prefillItemsFromPo(PurchaseOrderInfo po) {
    if (po.id == null) return;
    final dio = ref.read(apiClientProvider);
    dio.get('/api/v1/orders/${widget.orderId}').then((response) {
      final order = response.data;
      if (order == null) return;
      final poList = order['purchase_orders'] as List? ?? [];
      final selectedPo = poList.firstWhere(
        (p) => p['id'] == po.id,
        orElse: () => {},
      );
      final poItems = selectedPo['line_items'] as List<dynamic>? ?? [];
      if (poItems.isNotEmpty && mounted) {
        setState(() {
          _items = poItems.map<_ChallanItemForm>((item) {
            final f = _ChallanItemForm();
            f.descCtrl.text = item['description'] ?? '';
            f.partNoCtrl.text = item['part_no'] ?? '';
            f.unitCtrl.text = item['unit'] ?? '';
            f.qtyCtrl.text = '${item['qty'] ?? 0}';
            return f;
          }).toList();
        });
      }
    }).catchError((_) {});
  }

  void _prefillFromQuotation(Map<String, dynamic> order) {
    final quotations = order['quotations'] as List<dynamic>? ?? [];
    final qItems = quotations.isNotEmpty
        ? (quotations.first['line_items'] as List<dynamic>?)
        : null;
    if (qItems != null && qItems.isNotEmpty) {
      _items = qItems.map<_ChallanItemForm>((item) {
        final f = _ChallanItemForm();
        f.descCtrl.text = item['description'] ?? '';
        f.partNoCtrl.text = item['part_no'] ?? '';
        f.unitCtrl.text = item['unit'] ?? '';
        f.qtyCtrl.text = '${item['qty'] ?? 0}';
        return f;
      }).toList();
    }
  }

  @override
  void dispose() {
    _recipientCtrl.dispose();
    _dateCtrl.dispose();
    _transportModeCtrl.dispose();
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
      initialDate: DateTime.now(),
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
      final response = await dio.post('/api/v1/orders/${widget.orderId}/challans', data: {
        'recipient': _recipientCtrl.text.trim().isEmpty ? null : _recipientCtrl.text.trim(),
        'dispatch_date': _dateCtrl.text,
        'transport_mode': _transportModeCtrl.text.trim().isEmpty ? null : _transportModeCtrl.text.trim(),
        'vehicle_number': _vehicleCtrl.text.trim().isEmpty ? null : _vehicleCtrl.text.trim(),
        'place': _placeCtrl.text.trim().isEmpty ? null : _placeCtrl.text.trim(),
        'purchase_order_id': _selectedPoId,
        'items': lineItems,
      });

      if (mounted) {
        if (response.data['success'] == true) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Challan created')));
          ref.invalidate(orderDetailProvider(widget.orderId));
          if (mounted) context.pop();
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(response.data['message'] ?? 'Failed to create challan')),
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
    return Scaffold(
      appBar: AppBar(title: const Text('New Delivery Challan')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _sectionHeader('Dispatch Details'),
            const SizedBox(height: 12),
            if (_purchaseOrders.isNotEmpty) ...[
              DropdownButtonFormField<int>(
                value: _selectedPoId,
                decoration: _inputDecoration('Purchase Order', Icons.receipt_long),
                items: _purchaseOrders.map((po) => DropdownMenuItem(
                  value: po.id,
                  child: Text(
                    '${po.poNumber ?? '-'} (${po.status ?? '-'})',
                    overflow: TextOverflow.ellipsis,
                  ),
                )).toList(),
                onChanged: (val) {
                  setState(() => _selectedPoId = val);
                  final selectedPo = _purchaseOrders.firstWhere(
                    (p) => p.id == val,
                    orElse: () => _purchaseOrders.first,
                  );
                  _prefillItemsFromPo(selectedPo);
                },
              ),
              const SizedBox(height: 12),
            ],
            TextFormField(
              controller: _recipientCtrl,
              decoration: _inputDecoration('Deliver To / Recipient', Icons.person_outline),
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
            Row(
              children: [
                Expanded(child: TextFormField(
                  controller: _transportModeCtrl,
                  decoration: _inputDecoration('Transport Mode', Icons.local_shipping),
                )),
                const SizedBox(width: 12),
                Expanded(child: TextFormField(
                  controller: _vehicleCtrl,
                  decoration: _inputDecoration('Vehicle No.', Icons.directions_car),
                )),
              ],
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _placeCtrl,
              decoration: _inputDecoration('Place / Destination', Icons.location_on_outlined),
            ),

            const SizedBox(height: 28),
            _sectionHeader('Items'),
            const SizedBox(height: 4),
            Text('Tap + to add items. Swipe left to remove.', style: TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
            const SizedBox(height: 12),
            ...List.generate(_items.length, (i) => _buildItemCard(i)),

            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () => setState(() => _items.add(_ChallanItemForm())),
              icon: const Icon(Icons.add, size: 18),
              label: const Text('Add Item'),
              style: OutlinedButton.styleFrom(
                foregroundColor: VamsTheme.primary,
                side: const BorderSide(color: VamsTheme.primary),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                padding: const EdgeInsets.symmetric(vertical: 12),
              ),
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
                    : const Text('Create Challan', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
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

  InputDecoration _inputDecoration(String label, IconData icon) {
    return InputDecoration(
      labelText: label,
      prefixIcon: Icon(icon, size: 20, color: VamsTheme.textMuted),
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
            TextFormField(
              controller: item.partNoCtrl,
              decoration: _inputDecoration('Part No', Icons.qr_code),
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(child: TextFormField(
                  controller: item.unitCtrl,
                  decoration: _inputConfirmation('Unit', Icons.straighten),
                )),
                const SizedBox(width: 10),
                Expanded(child: TextFormField(
                  controller: item.qtyCtrl,
                  decoration: _inputConfirmation('Quantity', Icons.numbers),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                )),
              ],
            ),
          ],
        ),
      ),
    );
  }

  InputDecoration _inputConfirmation(String label, IconData icon) {
    return InputDecoration(
      labelText: label,
      isDense: true,
      filled: true,
      fillColor: Theme.of(context).colorScheme.surfaceContainerHighest.withOpacity(0.3),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: BorderSide(color: Colors.grey.shade300),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: BorderSide(color: Colors.grey.shade300),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: VamsTheme.primary, width: 2),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
    );
  }
}

class _ChallanItemForm {
  final descCtrl = TextEditingController();
  final partNoCtrl = TextEditingController();
  final unitCtrl = TextEditingController();
  final qtyCtrl = TextEditingController(text: '0');

  void dispose() {
    descCtrl.dispose();
    partNoCtrl.dispose();
    unitCtrl.dispose();
    qtyCtrl.dispose();
  }
}
