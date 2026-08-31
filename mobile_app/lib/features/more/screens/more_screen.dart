import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../auth/providers/auth_provider.dart';
import '../providers/notifications_count_provider.dart';

class MoreScreen extends ConsumerStatefulWidget {
  const MoreScreen({super.key});

  @override
  ConsumerState<MoreScreen> createState() => _MoreScreenState();
}

class _MoreScreenState extends ConsumerState<MoreScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.invalidate(unreadCountProvider);
    });
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final unreadAsync = ref.watch(unreadCountProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('More'),
      ),
      body: ListView(
        padding: const EdgeInsets.symmetric(vertical: 8),
        children: [
          if (auth is AuthAuthenticated) ...[
            Card(
              margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    CircleAvatar(
                      backgroundColor: VamsTheme.primary.withOpacity(0.1),
                      radius: 24,
                      child: Text(
                        auth.user.name.substring(0, auth.user.name.length >= 2 ? 2 : 1).toUpperCase(),
                        style: const TextStyle(color: VamsTheme.primary, fontWeight: FontWeight.w700, fontSize: 16),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(auth.user.name, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                          Text(auth.user.email, style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
                          if (auth.user.companyName != null)
                            Text(auth.user.companyName!, style: const TextStyle(fontSize: 11, color: VamsTheme.primary)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 8),
          ],

          Card(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: Column(
              children: [
                _MenuTile(
                  icon: Icons.notifications_outlined,
                  title: 'Notifications',
                  badgeCount: unreadAsync.valueOrNull,
                  onTap: () => context.push('/more/notifications'),
                ),
                const Divider(height: 1, indent: 56),
                _MenuTile(
                  icon: Icons.task_alt,
                  title: 'My Tasks',
                  onTap: () => context.push('/more/tasks/personal'),
                ),
                const Divider(height: 1, indent: 56),
                _MenuTile(
                  icon: Icons.group_outlined,
                  title: 'Team Tasks',
                  onTap: () => context.push('/more/tasks'),
                ),
                const Divider(height: 1, indent: 56),
                _MenuTile(
                  icon: Icons.description_outlined,
                  title: 'All Quotations',
                  onTap: () => context.push('/more/quotations'),
                ),
                const Divider(height: 1, indent: 56),
                _MenuTile(
                  icon: Icons.local_shipping_outlined,
                  title: 'All Delivery Challans',
                  onTap: () => context.push('/more/challans'),
                ),
                const Divider(height: 1, indent: 56),
                _MenuTile(
                  icon: Icons.check_circle_outline,
                  title: 'My Todos',
                  onTap: () => context.push('/more/todos'),
                ),
                const Divider(height: 1, indent: 56),
                _MenuTile(
                  icon: Icons.folder_outlined,
                  title: 'Projects',
                  onTap: () => context.push('/more/projects'),
                ),
                const Divider(height: 1, indent: 56),
                _MenuTile(
                  icon: Icons.payment_outlined,
                  title: 'Payments',
                  onTap: () => context.push('/more/accounts/payments'),
                ),
              ],
            ),
          ),

          Card(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: Column(
              children: [
                _MenuTile(
                  icon: Icons.person_outline,
                  title: 'My Profile',
                  onTap: () => context.push('/more/profile'),
                ),
                const Divider(height: 1, indent: 56),
                _MenuTile(
                  icon: Icons.business_center_outlined,
                  title: 'HR',
                  onTap: () => context.push('/more/hr'),
                ),
                const Divider(height: 1, indent: 56),
                _MenuTile(
                  icon: Icons.account_balance_wallet_outlined,
                  title: 'Accounts',
                  onTap: () => context.push('/more/accounts'),
                ),
              ],
            ),
          ),

          Card(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: Column(
              children: [
                _MenuTile(
                  icon: Icons.business_outlined,
                  title: 'Companies',
                  onTap: () => context.push('/companies'),
                ),
                if (auth is AuthAuthenticated && auth.user.role == 'admin') ...[
                  const Divider(height: 1, indent: 56),
                  _MenuTile(
                    icon: Icons.people_outline,
                    title: 'User Management',
                    onTap: () => context.push('/more/users'),
                  ),
                ],
                const Divider(height: 1, indent: 56),
                _MenuTile(
                  icon: Icons.settings_outlined,
                  title: 'Settings',
                  onTap: () => context.push('/more/settings'),
                ),
                if (auth is AuthAuthenticated && auth.user.role == 'admin') ...[
                  const Divider(height: 1, indent: 56),
                  _MenuTile(
                    icon: Icons.history,
                    title: 'Audit Log',
                    onTap: () => context.push('/more/audit-log'),
                  ),
                ],
              ],
            ),
          ),

          const SizedBox(height: 16),

          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Card(
              child: ListTile(
                leading: const Icon(Icons.logout, color: VamsTheme.danger),
                title: const Text('Logout', style: TextStyle(color: VamsTheme.danger)),
                onTap: () => ref.read(authProvider.notifier).logout(),
              ),
            ),
          ),

          const SizedBox(height: 32),
        ],
      ),
    );
  }
}

class _MenuTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final int? badgeCount;
  final VoidCallback onTap;

  const _MenuTile({
    required this.icon,
    required this.title,
    this.badgeCount,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(icon, size: 22, color: VamsTheme.textSecondary),
      title: Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500)),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (badgeCount != null && badgeCount! > 0)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(
                color: VamsTheme.danger,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                '$badgeCount',
                style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700),
              ),
            ),
          const SizedBox(width: 4),
          const Icon(Icons.chevron_right, size: 20, color: VamsTheme.textMuted),
        ],
      ),
      onTap: onTap,
    );
  }
}
