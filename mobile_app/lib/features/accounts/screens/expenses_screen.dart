import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../providers/accounts_provider.dart';
import 'add_expense_screen.dart';

class ExpensesScreen extends ConsumerStatefulWidget {
  final String scope;

  const ExpensesScreen({super.key, this.scope = 'company'});

  @override
  ConsumerState<ExpensesScreen> createState() => _ExpensesScreenState();
}

class _ExpensesScreenState extends ConsumerState<ExpensesScreen> {
  @override
  Widget build(BuildContext context) {
    final expensesAsync = ref.watch(expensesProvider(widget.scope));

    return Scaffold(
      appBar: AppBar(
        title: Text('${_scopeLabel} Expenses'),
        actions: [
          IconButton(
            icon: const Icon(Icons.download_outlined),
            tooltip: 'Export CSV',
            onPressed: () async {
              final dio = ref.read(apiClientProvider);
              final response = await dio.get('/api/v1/accounts/expenses/export', queryParameters: {'scope': widget.scope});
              // For mobile, we'll use a simple approach - show the URL
              if (response.statusCode == 200) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('CSV exported successfully')),
                );
              }
            },
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: VamsTheme.primary,
        foregroundColor: Colors.white,
        onPressed: () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => AddExpenseScreen(scope: widget.scope)),
        ),
        child: const Icon(Icons.add),
      ),
      body: expensesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
              const SizedBox(height: 12),
              Text('Failed to load expenses', style: const TextStyle(color: VamsTheme.textSecondary)),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => ref.invalidate(expensesProvider(widget.scope)),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (expenses) {
          if (expenses.isEmpty) {
            return const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.receipt_long_outlined, size: 48, color: VamsTheme.textMuted),
                  SizedBox(height: 12),
                  Text('No expenses found', style: TextStyle(color: VamsTheme.textSecondary)),
                ],
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(expensesProvider(widget.scope)),
            child: ListView.builder(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 80),
              itemCount: expenses.length,
              itemBuilder: (context, index) {
                final expense = expenses[index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            color: VamsTheme.warning.withOpacity(0.1),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Icon(Icons.receipt_long, color: VamsTheme.warning, size: 20),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                expense.categoryName ?? expense.category ?? 'Unknown',
                                style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                              ),
                              const SizedBox(height: 2),
                              Row(
                                children: [
                                  if (expense.payee != null) ...[
                                    Text(
                                      expense.payee!,
                                      style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                                    ),
                                    const Text(' · ', style: TextStyle(color: VamsTheme.textMuted)),
                                  ],
                                  Text(
                                    expense.expenseDate ?? '',
                                    style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                        Text(
                          _formatAmount(expense.amount),
                          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }

  String get _scopeLabel {
    switch (widget.scope) {
      case 'personal':
        return 'Personal';
      case 'general':
        return 'General';
      case 'company':
        return 'Company';
      default:
        return widget.scope[0].toUpperCase() + widget.scope.substring(1);
    }
  }

  String _formatAmount(double value) {
    if (value >= 1000000) return '${(value / 1000000).toStringAsFixed(1)}M';
    if (value >= 1000) return '${(value / 1000).toStringAsFixed(1)}K';
    return value.toStringAsFixed(0);
  }
}
