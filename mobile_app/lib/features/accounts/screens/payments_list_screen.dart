import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';

final paymentsListProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final dio = ref.read(apiClientProvider);
  final response = await dio.get('/api/v1/payments');
  if (response.data['success'] == true) {
    return List<Map<String, dynamic>>.from(response.data['payments']);
  }
  return [];
});

class PaymentsListScreen extends ConsumerWidget {
  const PaymentsListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final paymentsAsync = ref.watch(paymentsListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Payments')),
      body: paymentsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (payments) {
          if (payments.isEmpty) {
            return const Center(child: Text('No payments found'));
          }
          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: payments.length,
            itemBuilder: (context, index) {
              final p = payments[index];
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  leading: Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: VamsTheme.success.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(Icons.payment, color: VamsTheme.success, size: 20),
                  ),
                  title: Text(
                    'Rs ${(p['amount'] ?? 0).toStringAsFixed(2)}',
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                  subtitle: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(p['invoice_number'] ?? '', style: const TextStyle(fontSize: 12)),
                      Text(p['client_name'] ?? '', style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted)),
                    ],
                  ),
                  trailing: Text(
                    p['paid_date'] ?? '',
                    style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
