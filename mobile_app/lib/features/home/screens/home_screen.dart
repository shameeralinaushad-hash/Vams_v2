import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../../auth/models/auth_models.dart';
import '../../auth/providers/auth_provider.dart';
import '../../orders/providers/orders_provider.dart';
import '../../clients/providers/clients_provider.dart';
import '../../invoices/providers/invoices_provider.dart';
import '../models/dashboard_models.dart';
import '../providers/dashboard_provider.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  @override
  void initState() {
    super.initState();
    debugPrint('[HOME] initState called');
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final auth = ref.read(authProvider);
      debugPrint('[HOME] addPostFrameCallback: auth state = ${auth.runtimeType}');
      if (auth is AuthAuthenticated) {
        debugPrint('[HOME] authenticated → loading dashboard');
        ref.read(dashboardProvider.notifier).loadDashboard();
      } else {
        debugPrint('[HOME] NOT authenticated → skipping dashboard load');
      }
    });
  }

  void _showCompanySwitcher(BuildContext context, WidgetRef ref) async {
    final dio = ApiClient.instance;
    try {
      final response = await dio.get('/api/v1/auth/me');
      if (response.statusCode == 200 && response.data['success'] == true) {
        final companies = (response.data['companies'] as List)
            .map((c) => Company.fromJson(c))
            .toList();
        if (!context.mounted) return;
        showModalBottomSheet(
          context: context,
          isScrollControlled: true,
          shape: const RoundedRectangleBorder(
            borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          ),
          builder: (ctx) => DraggableScrollableSheet(
            initialChildSize: 0.5,
            minChildSize: 0.3,
            maxChildSize: 0.8,
            expand: false,
            builder: (ctx, scrollController) => Column(
              children: [
                const SizedBox(height: 12),
                Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.grey.shade300,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                const SizedBox(height: VamsTheme.spacing16),
                const Text(
                  'Switch Company',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: VamsTheme.spacing16),
                Expanded(
                  child: ListView.builder(
                    controller: scrollController,
                    itemCount: companies.length,
                    itemBuilder: (ctx, i) {
                      final company = companies[i];
                      final currentAuth = ref.read(authProvider);
                      final currentCompanyId = currentAuth is AuthAuthenticated
                          ? currentAuth.user.companyId
                          : null;
                      final isSelected = company.id == currentCompanyId;
                      return ListTile(
                        leading: CircleAvatar(
                          backgroundColor: isSelected
                              ? VamsTheme.primary
                              : VamsTheme.primary.withValues(alpha: 0.1),
                          child: Text(
                            company.name.substring(0, 1).toUpperCase(),
                            style: TextStyle(
                              color: isSelected ? Colors.white : VamsTheme.primary,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        title: Text(company.name),
                        trailing: isSelected
                            ? const Icon(Icons.check_circle, color: VamsTheme.primary)
                            : const Icon(Icons.chevron_right),
                        onTap: isSelected
                            ? null
                            : () async {
                                Navigator.of(ctx).pop();
                                final result = await ref
                                    .read(authProvider.notifier)
                                    .selectCompany(company.id);
                                if (!context.mounted) return;
                                if (result is AuthError) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(content: Text(result.message), backgroundColor: VamsTheme.danger),
                                  );
                                } else {
                                  ref.invalidate(dashboardProvider);
                                  ref.invalidate(ordersProvider);
                                  ref.invalidate(clientsProvider);
                                  ref.invalidate(invoicesProvider);
                                  ref.read(dashboardProvider.notifier).loadDashboard();
                                }
                              },
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        );
      }
    } catch (e) {
      debugPrint('Failed to load companies: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final dashboard = ref.watch(dashboardProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('VAMS'),
        actions: [
          if (auth is AuthAuthenticated)
            PopupMenuButton<String>(
              onSelected: (value) {
                if (value == 'logout') {
                  ref.read(authProvider.notifier).logout();
                } else if (value == 'switch_company') {
                  _showCompanySwitcher(context, ref);
                }
              },
              itemBuilder: (context) => [
                PopupMenuItem(
                  enabled: false,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(auth.user.name, style: const TextStyle(fontWeight: FontWeight.w700, color: VamsTheme.textPrimary)),
                      Text(auth.user.email, style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
                      if (auth.user.companyName != null)
                        Text(auth.user.companyName!, style: const TextStyle(fontSize: 11, color: VamsTheme.primary)),
                    ],
                  ),
                ),
                const PopupMenuDivider(),
                const PopupMenuItem(value: 'switch_company', child: Row(children: [Icon(Icons.business_outlined, size: 18), SizedBox(width: 8), Text('Switch Company')])),
                const PopupMenuItem(value: 'logout', child: Row(children: [Icon(Icons.logout, size: 18), SizedBox(width: 8), Text('Logout')])),
              ],
            ),
        ],
      ),
      body: dashboard.isLoading && dashboard.data == null
          ? const Center(child: CircularProgressIndicator())
          : dashboard.error != null && dashboard.data == null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
                      const SizedBox(height: 12),
                      Text(dashboard.error!, style: const TextStyle(color: VamsTheme.textSecondary)),
                      const SizedBox(height: 12),
                      ElevatedButton(
                        onPressed: () => ref.read(dashboardProvider.notifier).loadDashboard(),
                        child: const Text('Retry'),
                      ),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: () => ref.read(dashboardProvider.notifier).loadDashboard(),
                  child: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      _QuickActions(),
                      const SizedBox(height: 16),
                      if (dashboard.data != null) ...[
                        _StatsGrid(stats: dashboard.data!.stats),
                        const SizedBox(height: 16),
                        _MyTasksSection(tasks: dashboard.data!.assignedTasks),
                        const SizedBox(height: 16),
                        _PersonalTasksSection(tasks: dashboard.data!.personalTasks),
                        const SizedBox(height: 16),
                        _RecentOrders(orders: dashboard.data!.recentOrders),
                      ],
                    ],
                  ),
                ),
    );
  }
}

class _QuickActions extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(child: _ActionCard(
          icon: Icons.shopping_bag_outlined,
          label: 'Orders',
          onTap: () => context.push('/orders'),
        )),
        const SizedBox(width: 8),
        Expanded(child: _ActionCard(
          icon: Icons.business_outlined,
          label: 'Companies',
          onTap: () => context.push('/companies'),
        )),
        const SizedBox(width: 8),
        Expanded(child: _ActionCard(
          icon: Icons.more_horiz_outlined,
          label: 'More',
          onTap: () => context.push('/more'),
        )),
      ],
    );
  }
}

class _ActionCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _ActionCard({required this.icon, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: Column(
            children: [
              Icon(icon, size: 28, color: VamsTheme.primary),
              const SizedBox(height: 6),
              Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatsGrid extends StatelessWidget {
  final dynamic stats;
  const _StatsGrid({required this.stats});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Row(
          children: [
            Expanded(child: _StatCard(
              label: 'Total Orders',
              value: '${stats.totalOrders}',
              icon: Icons.shopping_bag_outlined,
              color: VamsTheme.primary,
            )),
            const SizedBox(width: 8),
            Expanded(child: _StatCard(
              label: 'Revenue',
              value: _formatCurrency(stats.totalRevenue),
              icon: Icons.account_balance_wallet_outlined,
              color: VamsTheme.success,
            )),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(child: _StatCard(
              label: 'Outstanding',
              value: _formatCurrency(stats.totalOutstanding),
              icon: Icons.pending_outlined,
              color: VamsTheme.danger,
            )),
            const SizedBox(width: 8),
            Expanded(child: _StatCard(
              label: 'Win Rate',
              value: stats.winRate != null ? '${stats.winRate}%' : 'N/A',
              icon: Icons.trending_up,
              color: VamsTheme.primary,
            )),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(child: _StatCard(
              label: 'Clients',
              value: '${stats.clientCount}',
              icon: Icons.people_outline,
              color: VamsTheme.primary,
            )),
            const SizedBox(width: 8),
            Expanded(child: _StatCard(
              label: 'Pending PO',
              value: '${stats.poPending}',
              icon: Icons.hourglass_empty,
              color: VamsTheme.warning,
            )),
          ],
        ),
      ],
    );
  }

  String _formatCurrency(double value) {
    if (value >= 1000000) return '${(value / 1000000).toStringAsFixed(1)}M';
    if (value >= 1000) return '${(value / 1000).toStringAsFixed(1)}K';
    return value.toStringAsFixed(0);
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;

  const _StatCard({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: color.withOpacity(0.1),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, size: 18, color: color),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    value,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                  ),
                  Text(
                    label,
                    style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MyTasksSection extends StatelessWidget {
  final List<DashboardTask> tasks;
  const _MyTasksSection({required this.tasks});

  @override
  Widget build(BuildContext context) {
    if (tasks.isEmpty) return const SizedBox.shrink();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text('My Tasks', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                ),
                Text('${tasks.length}', style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
              ],
            ),
            const SizedBox(height: 12),
            ...tasks.map((task) => _TaskTile(task: task)),
          ],
        ),
      ),
    );
  }
}

class _PersonalTasksSection extends StatelessWidget {
  final List<DashboardPersonalTask> tasks;
  const _PersonalTasksSection({required this.tasks});

  @override
  Widget build(BuildContext context) {
    if (tasks.isEmpty) return const SizedBox.shrink();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text('Personal Tasks', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                ),
                Text('${tasks.length}', style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
              ],
            ),
            const SizedBox(height: 12),
            ...tasks.map((task) => _PersonalTaskTile(task: task)),
          ],
        ),
      ),
    );
  }
}

class _TaskTile extends StatelessWidget {
  final DashboardTask task;
  const _TaskTile({required this.task});

  @override
  Widget build(BuildContext context) {
    final statusColor = _statusColor(task.status);
    final priorityColor = _priorityColor(task.priority);

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        leading: Container(
          width: 4,
          height: 40,
          decoration: BoxDecoration(
            color: priorityColor,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        title: Text(
          task.title,
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: statusColor.withOpacity(0.1),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                task.status.replaceAll('_', ' '),
                style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: statusColor),
              ),
            ),
            if (task.orderNumber != null) ...[
              const SizedBox(width: 6),
              Text(
                'Order #${task.orderNumber}',
                style: const TextStyle(fontSize: 10, color: VamsTheme.textMuted),
              ),
            ],
          ],
        ),
        trailing: task.dueDate != null
            ? Text(
                _formatDueDate(task.dueDate!),
                style: TextStyle(
                  fontSize: 10,
                  color: _isOverdue(task.dueDate!) ? VamsTheme.danger : VamsTheme.textMuted,
                  fontWeight: _isOverdue(task.dueDate!) ? FontWeight.w600 : FontWeight.normal,
                ),
              )
            : null,
      ),
    );
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'completed':
        return VamsTheme.success;
      case 'in_progress':
        return VamsTheme.primary;
      case 'to_do':
        return VamsTheme.warning;
      default:
        return VamsTheme.textMuted;
    }
  }

  Color _priorityColor(String priority) {
    switch (priority) {
      case 'high':
        return VamsTheme.danger;
      case 'medium':
        return VamsTheme.warning;
      case 'low':
        return VamsTheme.success;
      default:
        return VamsTheme.textMuted;
    }
  }

  String _formatDueDate(String dateStr) {
    try {
      final date = DateTime.parse(dateStr);
      final now = DateTime.now();
      final diff = date.difference(DateTime(now.year, now.month, now.day)).inDays;
      if (diff == 0) return 'Today';
      if (diff == 1) return 'Tomorrow';
      if (diff == -1) return 'Yesterday';
      if (diff < -1) return '${-diff}d overdue';
      if (diff <= 7) return '${diff}d left';
      return '${date.month}/${date.day}';
    } catch (_) {
      return dateStr;
    }
  }

  bool _isOverdue(String dateStr) {
    try {
      final date = DateTime.parse(dateStr);
      final now = DateTime.now();
      return date.isBefore(DateTime(now.year, now.month, now.day));
    } catch (_) {
      return false;
    }
  }
}

class _PersonalTaskTile extends StatelessWidget {
  final DashboardPersonalTask task;
  const _PersonalTaskTile({required this.task});

  @override
  Widget build(BuildContext context) {
    final statusColor = _statusColor(task.status);
    final priorityColor = _priorityColor(task.priority);

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        leading: Container(
          width: 4,
          height: 40,
          decoration: BoxDecoration(
            color: priorityColor,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        title: Text(
          task.title,
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: statusColor.withOpacity(0.1),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                task.status.replaceAll('_', ' '),
                style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: statusColor),
              ),
            ),
            const SizedBox(width: 6),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: VamsTheme.primary.withOpacity(0.08),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                task.lane,
                style: const TextStyle(fontSize: 10, color: VamsTheme.primary),
              ),
            ),
          ],
        ),
        trailing: task.dueDate != null
            ? Text(
                _formatDueDate(task.dueDate!),
                style: TextStyle(
                  fontSize: 10,
                  color: _isOverdue(task.dueDate!) ? VamsTheme.danger : VamsTheme.textMuted,
                  fontWeight: _isOverdue(task.dueDate!) ? FontWeight.w600 : FontWeight.normal,
                ),
              )
            : null,
      ),
    );
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'completed':
        return VamsTheme.success;
      case 'in_progress':
        return VamsTheme.primary;
      case 'to_do':
        return VamsTheme.warning;
      default:
        return VamsTheme.textMuted;
    }
  }

  Color _priorityColor(String priority) {
    switch (priority) {
      case 'high':
        return VamsTheme.danger;
      case 'medium':
        return VamsTheme.warning;
      case 'low':
        return VamsTheme.success;
      default:
        return VamsTheme.textMuted;
    }
  }

  String _formatDueDate(String dateStr) {
    try {
      final date = DateTime.parse(dateStr);
      final now = DateTime.now();
      final diff = date.difference(DateTime(now.year, now.month, now.day)).inDays;
      if (diff == 0) return 'Today';
      if (diff == 1) return 'Tomorrow';
      if (diff == -1) return 'Yesterday';
      if (diff < -1) return '${-diff}d overdue';
      if (diff <= 7) return '${diff}d left';
      return '${date.month}/${date.day}';
    } catch (_) {
      return dateStr;
    }
  }

  bool _isOverdue(String dateStr) {
    try {
      final date = DateTime.parse(dateStr);
      final now = DateTime.now();
      return date.isBefore(DateTime(now.year, now.month, now.day));
    } catch (_) {
      return false;
    }
  }
}

class _RecentOrders extends StatelessWidget {
  final List<dynamic> orders;
  const _RecentOrders({required this.orders});

  @override
  Widget build(BuildContext context) {
    if (orders.isEmpty) return const SizedBox.shrink();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Recent Orders', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
            const SizedBox(height: 12),
            ...orders.map((order) {
              final status = order.status ?? 'Pending';
              final statusColor = status == 'Delivered'
                  ? VamsTheme.success
                  : status == 'PO Received'
                      ? VamsTheme.primary
                      : status == 'Not Received'
                          ? VamsTheme.danger
                          : VamsTheme.warning;

              return InkWell(
                onTap: () => context.push('/orders/${order.id}'),
                borderRadius: BorderRadius.circular(10),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '#${order.orderNumber ?? order.id}',
                              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                            ),
                            Text(
                              order.client ?? 'No client',
                              style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                            ),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: statusColor.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          status,
                          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: statusColor),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}
