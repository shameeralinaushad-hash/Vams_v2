import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../auth/providers/auth_provider.dart';
import '../providers/hr_provider.dart';
import 'attendance_screen.dart';
import 'attendance_list_screen.dart';
import 'payroll_screen.dart';

class HrScreen extends ConsumerWidget {
  const HrScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final employeesAsync = ref.watch(hrEmployeesProvider);
    final auth = ref.watch(authProvider);
    final isAdmin = auth is AuthAuthenticated && auth.user.role == 'admin';

    return Scaffold(
      appBar: AppBar(title: const Text('HR Management')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _MenuTile(
            icon: Icons.people_outline,
            title: 'Employees List',
            subtitle: employeesAsync.when(
              data: (list) => '${list.length} employees',
              loading: () => 'Loading...',
              error: (_, __) => 'Error loading',
            ),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const _EmployeesListScreen()),
            ),
          ),
          if (isAdmin) ...[
            _MenuTile(
              icon: Icons.table_chart_outlined,
              title: 'All Attendance',
              subtitle: 'View monthly attendance grid',
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const AttendanceListScreen()),
              ),
            ),
            _MenuTile(
              icon: Icons.qr_code_2,
              title: 'Attendance QR',
              subtitle: 'Display QR for scanning',
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const _AttendanceQrScreen()),
              ),
            ),
          ],
          _MenuTile(
            icon: Icons.fingerprint,
            title: 'Mark Attendance',
            subtitle: 'Scan fingerprint to mark',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const AttendanceScreen()),
            ),
          ),
          _MenuTile(
            icon: Icons.today,
            title: 'My Attendance',
            subtitle: 'View today\'s status',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const AttendanceScreen()),
            ),
          ),
          _MenuTile(
            icon: Icons.account_balance_wallet_outlined,
            title: 'Payroll',
            subtitle: 'View payroll records',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const PayrollScreen()),
            ),
          ),
          _MenuTile(
            icon: Icons.event_outlined,
            title: 'Holidays',
            subtitle: 'Holiday list',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const _HolidaysScreen()),
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

class _EmployeesListScreen extends ConsumerWidget {
  const _EmployeesListScreen();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final employeesAsync = ref.watch(hrEmployeesProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Employees'),
        actions: [
          IconButton(
            icon: const Icon(Icons.person_add_outlined),
            onPressed: () => context.push('/more/hr/employees/create'),
          ),
        ],
      ),
      body: employeesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
              const SizedBox(height: 12),
              Text('Failed to load employees', style: const TextStyle(color: VamsTheme.textSecondary)),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => ref.invalidate(hrEmployeesProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (employees) {
          if (employees.isEmpty) {
            return const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.people_outline, size: 48, color: VamsTheme.textMuted),
                  SizedBox(height: 12),
                  Text('No employees found', style: TextStyle(color: VamsTheme.textSecondary)),
                ],
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(hrEmployeesProvider),
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              itemCount: employees.length,
              itemBuilder: (context, index) {
                final emp = employees[index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        CircleAvatar(
                          backgroundColor: emp.isActive
                              ? VamsTheme.primary.withOpacity(0.1)
                              : VamsTheme.textMuted.withOpacity(0.1),
                          child: Text(
                            emp.name.substring(0, emp.name.length.clamp(0, 2)).toUpperCase(),
                            style: TextStyle(
                              color: emp.isActive ? VamsTheme.primary : VamsTheme.textMuted,
                              fontWeight: FontWeight.w700,
                              fontSize: 13,
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(emp.name, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                              const SizedBox(height: 2),
                              if (emp.department != null || emp.designation != null)
                                Text(
                                  [emp.department, emp.designation].where((e) => e != null).join(' - '),
                                  style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                                ),
                            ],
                          ),
                        ),
                        if (!emp.isActive)
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: VamsTheme.danger.withOpacity(0.1),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: const Text(
                              'Inactive',
                              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: VamsTheme.danger),
                            ),
                          ),
                        const SizedBox(width: 8),
                        IconButton(
                          icon: const Icon(Icons.edit_outlined, size: 18),
                          onPressed: () => context.push('/more/hr/employees/${emp.id}/edit'),
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
}

class _HolidaysScreen extends ConsumerWidget {
  const _HolidaysScreen();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final holidaysAsync = ref.watch(holidaysProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Holidays')),
      body: holidaysAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
              const SizedBox(height: 12),
              Text('Failed to load holidays', style: const TextStyle(color: VamsTheme.textSecondary)),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => ref.invalidate(holidaysProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (holidays) {
          if (holidays.isEmpty) {
            return const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.event_outlined, size: 48, color: VamsTheme.textMuted),
                  SizedBox(height: 12),
                  Text('No holidays found', style: TextStyle(color: VamsTheme.textSecondary)),
                ],
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(holidaysProvider),
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              itemCount: holidays.length,
              itemBuilder: (context, index) {
                final holiday = holidays[index];
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
                            color: VamsTheme.success.withOpacity(0.1),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Icon(Icons.event, color: VamsTheme.success, size: 20),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(holiday.name, style: const TextStyle(fontWeight: FontWeight.w600)),
                              const SizedBox(height: 2),
                              Text(holiday.date, style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted)),
                            ],
                          ),
                        ),
                        if (holiday.isRecurring)
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: VamsTheme.primary.withOpacity(0.1),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: const Text(
                              'Recurring',
                              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: VamsTheme.primary),
                            ),
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
}

class _AttendanceQrScreen extends ConsumerWidget {
  const _AttendanceQrScreen();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final qrAsync = ref.watch(attendanceQrProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Attendance QR')),
      body: qrAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
              const SizedBox(height: 12),
              Text('Failed to load QR code', style: TextStyle(color: VamsTheme.textSecondary)),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => ref.invalidate(attendanceQrProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (data) {
          final qrImage = data['qr_image'] as String?;
          final scanUrl = data['scan_url'] as String?;

          return Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.qr_code_2, size: 24, color: VamsTheme.primary),
                  const SizedBox(height: 8),
                  const Text('Scan to Mark Attendance', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 24),
                  if (qrImage != null)
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: [
                          BoxShadow(color: Colors.black.withOpacity(0.08), blurRadius: 12, offset: const Offset(0, 4)),
                        ],
                      ),
                      child: Image.memory(
                        Uri.parse(qrImage).data!.contentAsBytes(),
                        width: 220,
                        height: 220,
                      ),
                    )
                  else
                    const Icon(Icons.qr_code_2, size: 220, color: VamsTheme.textMuted),
                  const SizedBox(height: 20),
                  if (scanUrl != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: VamsTheme.background,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        scanUrl,
                        style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted),
                        textAlign: TextAlign.center,
                      ),
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
