import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../auth/providers/auth_provider.dart';
import '../../../core/storage.dart';
import '../../../core/theme.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  void _showServerUrlDialog(BuildContext context, WidgetRef ref) async {
    final currentUrl = await AppStorage.getServerUrl() ?? '';
    final controller = TextEditingController(text: currentUrl);

    final result = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Server URL'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(
            hintText: 'https://vams.example.com',
            prefixIcon: Icon(Icons.link),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, controller.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );

    if (result != null && result.isNotEmpty && context.mounted) {
      final url = result.replaceAll(RegExp(r'/+$'), '');
      await AppStorage.setServerUrl(url);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Server URL updated. Restart the app to apply.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    final user = auth is AuthAuthenticated ? auth.user : null;
    final isAdmin = user?.role == 'admin';

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        children: [
          const _SectionHeader('Account'),
          _SettingsTile(
            icon: Icons.person_outline,
            title: 'Edit Profile',
            subtitle: 'Update your name and email',
            onTap: () => context.push('/profile/edit'),
          ),
          _SettingsTile(
            icon: Icons.lock_outline,
            title: 'Change Password',
            subtitle: 'Update your password',
            onTap: () => context.push('/profile/change-password'),
          ),
          _SettingsTile(
            icon: Icons.business,
            title: 'Company Details',
            subtitle: 'View and edit company information',
            onTap: () {
              // Navigate to company detail for user's company
            },
          ),

          const _SectionHeader('Connection'),
          _SettingsTile(
            icon: Icons.dns_outlined,
            title: 'Server URL',
            subtitle: 'Change the server address',
            onTap: () => _showServerUrlDialog(context, ref),
          ),

          const _SectionHeader('Admin'),
          if (isAdmin) ...[
            _SettingsTile(
              icon: Icons.people_outline,
              title: 'User Management',
              subtitle: 'Manage user accounts',
              onTap: () => context.push('/users'),
            ),
            _SettingsTile(
              icon: Icons.receipt_long,
              title: 'Expense Categories',
              subtitle: 'Manage categories',
              onTap: () => context.push('/accounts/categories'),
            ),
            _SettingsTile(
              icon: Icons.account_balance_wallet_outlined,
              title: 'Budgets',
              subtitle: 'Manage budget plans',
              onTap: () => context.push('/accounts/budgets'),
            ),
          ],

          const _SectionHeader('Data'),
          _SettingsTile(
            icon: Icons.download,
            title: 'Export Expenses (CSV)',
            subtitle: 'Download expenses as CSV',
            onTap: () async {
              // Triggers export from the expenses screen
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Go to Accounts > Expenses to export')),
              );
            },
          ),

          const _SectionHeader('About'),
          _SettingsTile(
            icon: Icons.info_outline,
            title: 'App Version',
            subtitle: 'VAMS Mobile v2.0.0',
            onTap: null,
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader(this.title);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 24, 16, 8),
      child: Text(
        title.toUpperCase(),
        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: VamsTheme.textMuted, letterSpacing: 1),
      ),
    );
  }
}

class _SettingsTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback? onTap;

  const _SettingsTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(icon, size: 22, color: VamsTheme.primary),
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
      subtitle: Text(subtitle, style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
      trailing: onTap != null ? const Icon(Icons.chevron_right, size: 20, color: VamsTheme.textMuted) : null,
      onTap: onTap,
    );
  }
}
