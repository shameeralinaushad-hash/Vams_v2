import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../auth/providers/auth_provider.dart';
import '../../hr/models/hr_models.dart';
import '../providers/profile_provider.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    final profileAsync = ref.watch(profileDashboardProvider);

    if (auth is! AuthAuthenticated) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      appBar: AppBar(title: const Text('My Profile')),
      body: profileAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
              const SizedBox(height: 12),
              Text('Failed to load profile', style: TextStyle(color: VamsTheme.textSecondary)),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => ref.invalidate(profileDashboardProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (profile) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(profileDashboardProvider),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _buildUserInfo(auth.user.name, auth.user.email, auth.user.role, profile),
              const SizedBox(height: 16),
              _buildEfficiencyRing(profile),
              if (profile.leaveStats != null) ...[
                const SizedBox(height: 16),
                _buildLeaveBalance(profile.leaveStats!),
              ],
              if (profile.employee != null) ...[
                const SizedBox(height: 16),
                _buildAttendanceHeatmap(profile),
                const SizedBox(height: 16),
                _buildMonthlyTrend(profile.monthlyPct),
                const SizedBox(height: 16),
                _buildTaskVelocity(profile),
              ],
              if (profile.upcomingHolidays.isNotEmpty) ...[
                const SizedBox(height: 16),
                _buildUpcomingHolidays(profile.upcomingHolidays),
              ],
              if (profile.tasks.isNotEmpty) ...[
                const SizedBox(height: 16),
                _buildMyTasks(profile.tasks),
              ],
              if (profile.payrollHistory.isNotEmpty) ...[
                const SizedBox(height: 16),
                _buildPayrollHistory(profile.payrollHistory),
              ],
              const SizedBox(height: 16),
              _buildActions(context, ref),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildUserInfo(String name, String email, String role, ProfileDashboard profile) {
    final roleLabel = role == 'admin' ? 'Administrator' : role[0].toUpperCase() + role.substring(1);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            CircleAvatar(
              radius: 32,
              backgroundColor: VamsTheme.primary.withOpacity(0.1),
              child: Text(
                name.substring(0, name.length.clamp(0, 2)).toUpperCase(),
                style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: VamsTheme.primary),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text(email, style: const TextStyle(fontSize: 13, color: VamsTheme.textMuted)),
                  const SizedBox(height: 4),
                  Row(children: [
                    _Tag(label: roleLabel, color: VamsTheme.primary),
                    if (profile.employee != null) ...[
                      const SizedBox(width: 6),
                      _Tag(label: profile.employee!['department'] ?? '', color: VamsTheme.success),
                    ],
                  ]),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEfficiencyRing(ProfileDashboard profile) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            SizedBox(
              width: 100,
              height: 100,
              child: CustomPaint(
                painter: _RingPainter(
                  percent: profile.efficiency,
                  color: VamsTheme.primary,
                  bgColor: VamsTheme.border,
                ),
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '${profile.efficiency.toInt()}%',
                        style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: VamsTheme.primary),
                      ),
                      const Text('Score', style: TextStyle(fontSize: 10, color: VamsTheme.textMuted)),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(width: 20),
            Expanded(
              child: Column(
                children: [
                  _MetricCard(
                    label: 'Attendance',
                    value: '${profile.attnPct.toInt()}%',
                    icon: Icons.calendar_today,
                    color: VamsTheme.success,
                  ),
                  const SizedBox(height: 8),
                  _MetricCard(
                    label: 'Velocity',
                    value: '${profile.taskPct.toInt()}%',
                    icon: Icons.speed,
                    color: VamsTheme.warning,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLeaveBalance(Map<String, dynamic> stats) {
    final earned = (stats['earned'] ?? 0).toDouble();
    final used = (stats['used'] ?? 0).toDouble();
    final balance = (stats['balance'] ?? 0).toDouble();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Paid Leave Balance', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(child: _StatMini(label: 'Earned', value: earned.toInt().toString(), color: VamsTheme.success)),
                Expanded(child: _StatMini(label: 'Used', value: used.toInt().toString(), color: VamsTheme.danger)),
                Expanded(child: _StatMini(label: 'Balance', value: balance.toInt().toString(), color: VamsTheme.primary)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAttendanceHeatmap(ProfileDashboard profile) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    final now = DateTime.now();
    final year = now.year;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('My Attendance \u2014 $year', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            const SizedBox(height: 12),
            _HeatmapGrid(heatmap: profile.heatmap, year: year),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _LegendDot(color: VamsTheme.success, label: 'Present'),
                const SizedBox(width: 12),
                _LegendDot(color: VamsTheme.danger, label: 'Absent'),
                const SizedBox(width: 12),
                _LegendDot(color: VamsTheme.warning, label: 'Half'),
                const SizedBox(width: 12),
                _LegendDot(color: VamsTheme.textMuted, label: 'Leave'),
                const SizedBox(width: 12),
                _LegendDot(color: VamsTheme.border, label: 'None'),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMonthlyTrend(List<double> monthlyPct) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    final maxVal = monthlyPct.isEmpty ? 100.0 : monthlyPct.reduce(math.max).clamp(1.0, 100.0);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Monthly Attendance Trend', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            const SizedBox(height: 16),
            SizedBox(
              height: 160,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: List.generate(12, (i) {
                  final val = i < monthlyPct.length ? monthlyPct[i] : 0.0;
                  final height = (val / maxVal) * 130;
                  return Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        Text('${val.toInt()}', style: const TextStyle(fontSize: 8, color: VamsTheme.textMuted)),
                        const SizedBox(height: 2),
                        Container(
                          height: height.clamp(2, 130),
                          margin: const EdgeInsets.symmetric(horizontal: 2),
                          decoration: BoxDecoration(
                            color: val >= 80 ? VamsTheme.success : val >= 50 ? VamsTheme.warning : VamsTheme.danger,
                            borderRadius: BorderRadius.circular(3),
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(months[i].substring(0, 1), style: const TextStyle(fontSize: 9, color: VamsTheme.textMuted)),
                      ],
                    ),
                  );
                }),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTaskVelocity(ProfileDashboard profile) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Text('Task Velocity', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: VamsTheme.primary.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text('3-mo avg: ${profile.taskRollingAvg}', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: VamsTheme.primary)),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(child: _StatMini(label: 'Velocity', value: '${profile.taskPct.toInt()}%', color: VamsTheme.primary)),
                Expanded(child: _StatMini(label: 'This Month', value: '${profile.taskDoneThisMonth}', color: VamsTheme.success)),
                Expanded(child: _StatMini(label: '3-mo Avg', value: '${profile.taskRollingAvg}', color: VamsTheme.warning)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUpcomingHolidays(List<Map<String, dynamic>> holidays) {
    final now = DateTime.now();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Upcoming Holidays', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            const SizedBox(height: 8),
            ...holidays.map((h) {
              final hDate = DateTime.parse(h['date']);
              final daysUntil = hDate.difference(now).inDays;
              Color badgeColor = VamsTheme.textMuted;
              if (daysUntil <= 3) badgeColor = VamsTheme.danger;
              else if (daysUntil <= 7) badgeColor = VamsTheme.warning;

              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(h['name'], style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                          Text(h['date'], style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted)),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(color: badgeColor.withOpacity(0.1), borderRadius: BorderRadius.circular(6)),
                      child: Text('${daysUntil}d', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: badgeColor)),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildMyTasks(List<Map<String, dynamic>> tasks) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('My Tasks', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            const SizedBox(height: 8),
            ...tasks.take(8).map((t) {
              final isDone = t['is_done'] == true;
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: [
                    Icon(
                      isDone ? Icons.check_circle : Icons.radio_button_unchecked,
                      size: 16,
                      color: isDone ? VamsTheme.success : VamsTheme.textMuted,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        t['text'] ?? '',
                        style: TextStyle(
                          fontSize: 13,
                          decoration: isDone ? TextDecoration.lineThrough : null,
                          color: isDone ? VamsTheme.textMuted : VamsTheme.textPrimary,
                        ),
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildPayrollHistory(List<Map<String, dynamic>> records) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Payroll History', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            const SizedBox(height: 8),
            Table(
              columnWidths: const {
                0: FlexColumnWidth(2),
                1: FlexColumnWidth(1.5),
                2: FlexColumnWidth(1.5),
                3: FlexColumnWidth(1),
              },
              children: [
                TableRow(
                  children: const [
                    Text('Period', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: VamsTheme.textMuted)),
                    Text('Base', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: VamsTheme.textMuted)),
                    Text('Final', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: VamsTheme.textMuted)),
                    Text('Status', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: VamsTheme.textMuted)),
                  ],
                ),
                ...records.map((r) {
                  final statusColor = r['status'] == 'paid'
                      ? VamsTheme.success
                      : r['status'] == 'finalized'
                          ? VamsTheme.warning
                          : VamsTheme.textMuted;
                  return TableRow(
                    children: [
                      Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text('${r['month']}/${r['year']}', style: const TextStyle(fontSize: 12))),
                      Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text('${r['base_salary']}', style: const TextStyle(fontSize: 12))),
                      Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text('${r['final_salary']}', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600))),
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 4),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(color: statusColor.withOpacity(0.1), borderRadius: BorderRadius.circular(4)),
                          child: Text(r['status'], style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: statusColor)),
                        ),
                      ),
                    ],
                  );
                }),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActions(BuildContext context, WidgetRef ref) {
    return Column(
      children: [
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            onPressed: () => context.push('/more/profile/edit'),
            icon: const Icon(Icons.edit, size: 18),
            label: const Text('Edit Profile'),
            style: OutlinedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ),
        const SizedBox(height: 8),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            onPressed: () => context.push('/more/profile/change-password'),
            icon: const Icon(Icons.lock_outline, size: 18),
            label: const Text('Change Password'),
            style: OutlinedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ),
        const SizedBox(height: 24),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            onPressed: () {
              showDialog(
                context: context,
                builder: (ctx) => AlertDialog(
                  title: const Text('Logout'),
                  content: const Text('Are you sure you want to logout?'),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
                    TextButton(
                      onPressed: () {
                        Navigator.pop(ctx);
                        ref.read(authProvider.notifier).logout();
                      },
                      style: TextButton.styleFrom(foregroundColor: VamsTheme.danger),
                      child: const Text('Logout'),
                    ),
                  ],
                ),
              );
            },
            icon: const Icon(Icons.logout, color: VamsTheme.danger),
            label: const Text('Logout', style: TextStyle(color: VamsTheme.danger)),
            style: OutlinedButton.styleFrom(
              side: const BorderSide(color: VamsTheme.danger),
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ),
      ],
    );
  }
}

class _Tag extends StatelessWidget {
  final String label;
  final Color color;
  const _Tag({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    if (label.isEmpty) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: color.withOpacity(0.1), borderRadius: BorderRadius.circular(4)),
      child: Text(label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color)),
    );
  }
}

class _MetricCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;
  const _MetricCard({required this.label, required this.value, required this.icon, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.06),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(value, style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: color)),
              Text(label, style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted)),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatMini extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  const _StatMini({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(value, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: color)),
        const SizedBox(height: 2),
        Text(label, style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted)),
      ],
    );
  }
}

class _RingPainter extends CustomPainter {
  final double percent;
  final Color color;
  final Color bgColor;
  _RingPainter({required this.percent, required this.color, required this.bgColor});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 8;
    final strokeWidth = 10.0;

    final bgPaint = Paint()
      ..color = bgColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth;
    canvas.drawCircle(center, radius, bgPaint);

    final fgPaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;
    final sweepAngle = 2 * math.pi * (percent / 100).clamp(0.0, 1.0);
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2,
      sweepAngle,
      false,
      fgPaint,
    );
  }

  @override
  bool shouldRepaint(covariant _RingPainter old) => old.percent != percent;
}

class _HeatmapGrid extends StatelessWidget {
  final Map<String, String> heatmap;
  final int year;
  const _HeatmapGrid({required this.heatmap, required this.year});

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final startDay = DateTime(year, 1, 1);
    final totalDays = now.year == year ? now.difference(startDay).inDays + 1 : 365;

    return Wrap(
      spacing: 2,
      runSpacing: 2,
      children: List.generate(totalDays, (i) {
        final dt = startDay.add(Duration(days: i));
        final key = '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')}';
        final status = heatmap[key];

        Color color = VamsTheme.border;
        if (status == 'present') color = VamsTheme.success;
        else if (status == 'absent') color = VamsTheme.danger;
        else if (status == 'half_day') color = VamsTheme.warning;
        else if (status == 'leave') color = VamsTheme.textMuted;

        return Tooltip(
          message: '$key: ${status ?? "none"}',
          child: Container(
            width: 12,
            height: 12,
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
        );
      }),
    );
  }
}

class _LegendDot extends StatelessWidget {
  final Color color;
  final String label;
  const _LegendDot({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(width: 10, height: 10, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(2))),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 10, color: VamsTheme.textMuted)),
      ],
    );
  }
}
