import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';

class ReceiptOcrScreen extends ConsumerStatefulWidget {
  const ReceiptOcrScreen({super.key});

  @override
  ConsumerState<ReceiptOcrScreen> createState() => _ReceiptOcrScreenState();
}

class _ReceiptOcrScreenState extends ConsumerState<ReceiptOcrScreen> {
  bool _loading = false;
  Map<String, dynamic>? _result;
  String? _error;
  String? _rawText;

  Future<void> _pickImage(ImageSource source) async {
    final picker = ImagePicker();
    final picked = await picker.pickImage(source: source, imageQuality: 85);
    if (picked == null) return;

    setState(() {
      _loading = true;
      _error = null;
      _result = null;
      _rawText = null;
    });

    try {
      final dio = ref.read(apiClientProvider);
      final formData = FormData.fromMap({
        'file': await MultipartFile.fromFile(picked.path, filename: picked.name),
      });
      final response = await dio.post('/api/v1/accounts/receipt-ocr', data: formData);

      if (mounted) {
        if (response.data['success'] == true) {
          setState(() {
            _result = response.data['result'];
            _rawText = response.data['result']['raw_text'];
          });
        } else {
          setState(() => _error = response.data['message'] ?? 'OCR failed');
        }
      }
    } on DioException catch (e) {
      if (mounted) {
        setState(() => _error = e.response?.data is Map ? (e.response?.data['message'] ?? 'Error') : 'Error');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _showSourcePicker() {
    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.camera_alt),
              title: const Text('Take Photo'),
              onTap: () {
                Navigator.pop(ctx);
                _pickImage(ImageSource.camera);
              },
            ),
            ListTile(
              leading: const Icon(Icons.photo_library),
              title: const Text('Choose from Gallery'),
              onTap: () {
                Navigator.pop(ctx);
                _pickImage(ImageSource.gallery);
              },
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scan Receipt')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _loading ? null : _showSourcePicker,
              icon: const Icon(Icons.document_scanner, size: 20),
              label: const Text('Scan Receipt'),
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
            ),
          ),
          if (_loading) ...[
            const SizedBox(height: 24),
            const Center(child: CircularProgressIndicator()),
            const SizedBox(height: 12),
            const Center(child: Text('Processing receipt...', style: TextStyle(color: VamsTheme.textMuted))),
          ],
          if (_error != null) ...[
            const SizedBox(height: 16),
            Card(
              color: VamsTheme.danger.withValues(alpha: 0.1),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    const Icon(Icons.error_outline, color: VamsTheme.danger),
                    const SizedBox(width: 12),
                    Expanded(child: Text(_error!, style: const TextStyle(color: VamsTheme.danger))),
                  ],
                ),
              ),
            ),
          ],
          if (_result != null) ...[
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Extracted Data', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 12),
                    if ((_result!['vendor'] as String?)?.isNotEmpty == true)
                      _ResultRow(label: 'Vendor', value: _result!['vendor']),
                    if ((_result!['date'] as String?)?.isNotEmpty == true)
                      _ResultRow(label: 'Date', value: _result!['date']),
                    if ((_result!['total'] as num?) != null && (_result!['total'] as num) > 0)
                      _ResultRow(label: 'Total', value: (_result!['total'] as num).toStringAsFixed(2)),
                    if ((_result!['items'] as List?)?.isNotEmpty == true) ...[
                      const SizedBox(height: 12),
                      const Text('Items', style: TextStyle(fontWeight: FontWeight.w600)),
                      const SizedBox(height: 8),
                      ...(_result!['items'] as List).map((item) => Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: Row(
                              children: [
                                Expanded(child: Text(item['item'] ?? '', style: const TextStyle(fontSize: 13))),
                                Text('x${item['qty']}', style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
                                const SizedBox(width: 8),
                                Text('${item['total']}', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                              ],
                            ),
                          )),
                    ],
                  ],
                ),
              ),
            ),
          ],
          if (_rawText != null && _rawText!.isNotEmpty) ...[
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Raw Text', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 8),
                    Text(_rawText!, style: const TextStyle(fontSize: 12, fontFamily: 'monospace')),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _ResultRow extends StatelessWidget {
  final String label;
  final String value;
  const _ResultRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(width: 80, child: Text(label, style: const TextStyle(color: VamsTheme.textMuted, fontSize: 13))),
          Expanded(child: Text(value, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13))),
        ],
      ),
    );
  }
}
