import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme.dart';
import 'expenses_screen.dart';
import 'budgets_screen.dart';
import 'categories_screen.dart';
import 'receipt_ocr_screen.dart';

class AccountsScreen extends ConsumerWidget {
  const AccountsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('Accounts')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _MenuTile(
            icon: Icons.person_outline,
            title: 'Personal Expenses',
            subtitle: 'Your personal expenses',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const ExpensesScreen(scope: 'personal')),
            ),
          ),
          _MenuTile(
            icon: Icons.category_outlined,
            title: 'General Expenses',
            subtitle: 'General expenses',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const ExpensesScreen(scope: 'general')),
            ),
          ),
          _MenuTile(
            icon: Icons.business_outlined,
            title: 'Company Expenses',
            subtitle: 'Company-wide expenses',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const ExpensesScreen(scope: 'company')),
            ),
          ),
          _MenuTile(
            icon: Icons.account_balance_outlined,
            title: 'Budgets',
            subtitle: 'View and manage budgets',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const BudgetsScreen()),
            ),
          ),
          _MenuTile(
            icon: Icons.label_outlined,
            title: 'Categories',
            subtitle: 'Manage expense categories',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const CategoriesScreen()),
            ),
          ),
          _MenuTile(
            icon: Icons.camera_alt_outlined,
            title: 'Scan Receipt',
            subtitle: 'Capture receipt with camera',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const ReceiptOcrScreen()),
            ),
          ),
        ],
      ),
    );
  }
}

class _MenuTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _MenuTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: VamsTheme.primary.withOpacity(0.1),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, color: VamsTheme.primary, size: 20),
        ),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(subtitle, style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
        trailing: const Icon(Icons.chevron_right, size: 20, color: VamsTheme.textMuted),
        onTap: onTap,
      ),
    );
  }
}
