import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme.dart';
import '../providers/hr_provider.dart';

class AttendanceListScreen extends ConsumerStatefulWidget {
  const AttendanceListScreen({super.key});

  @override
  ConsumerState<AttendanceListScreen> createState() => _AttendanceListScreenState();
}

class _AttendanceListScreenState extends ConsumerState<AttendanceListScreen> {
  void _prevMonth() {
    final currentMonth = ref.read(attendanceMonthProvider);
    final currentYear = ref.read(attendanceYearProvider);
    if (currentMonth == 1) {
      ref.read(attendanceMonthProvider.notifier).state = 12;
      ref.read(attendanceYearProvider.notifier).state = currentYear - 1;
    } else {
      ref.read(attendanceMonthProvider.notifier).state = currentMonth - 1;
    }
  }

  void _nextMonth() {
    final currentMonth = ref.read(attendanceMonthProvider);
    final currentYear = ref.read(attendanceYearProvider);
    if (currentMonth == 12) {
      ref.read(attendanceMonthProvider.notifier).state = 1;
      ref.read(attendanceYearProvider.notifier).state = currentYear + 1;
    } else {
      ref.read(attendanceMonthProvider.notifier).state = currentMonth + 1;
    }
  }

  @override
  Widget build(BuildContext context) {
    final month = ref.watch(attendanceMonthProvider);
    final year = ref.watch(attendanceYearProvider);
    final dataAsync = ref.watch(attendanceListProvider);
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    return Scaffold(
      appBar: AppBar(
        title: const Text('Attendance'),
        actions: [
          IconButton(
            icon: const Icon(Icons.qr_code),
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const _AttendanceQrInline())),
          ),
        ],
      ),
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            color: VamsTheme.surface,
            child: Row(
              children: [
                IconButton(icon: const Icon(Icons.chevron_left), onPressed: _prevMonth),
                Expanded(
                  child: Center(
                    child: Text(
                      '${months[month - 1]} $year',
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                    ),
                  ),
                ),
                IconButton(icon: const Icon(Icons.chevron_right), onPressed: _nextMonth),
              ],
            ),
          ),
          Expanded(
            child: dataAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
                    const SizedBox(height: 12),
                    Text('Failed to load attendance', style: TextStyle(color: VamsTheme.textSecondary)),
                    const SizedBox(height: 12),
                    ElevatedButton(
                      onPressed: () => ref.invalidate(attendanceListProvider),
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ),
              data: (data) {
                if (data.employees.isEmpty) {
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
                return _buildGrid(data);
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildGrid(dynamic data) {
    final employees = data.employees as List;
    final days = data.days as List;
    final numDays = data.numDays as int;

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Table(
              columnWidths: {
                0: const FixedColumnWidth(140),
                for (int i = 1; i <= numDays; i++) i: const FixedColumnWidth(36),
                numDays + 1: const FixedColumnWidth(36),
                numDays + 2: const FixedColumnWidth(36),
                numDays + 3: const FixedColumnWidth(36),
                numDays + 4: const FixedColumnWidth(36),
                numDays + 5: const FixedColumnWidth(44),
              },
              children: [
                TableRow(
                  decoration: BoxDecoration(color: VamsTheme.surface),
                  children: [
                    const Padding(
                      padding: EdgeInsets.all(8),
                      child: Text('Employee', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
                    ),
                    ...days.map((d) => Padding(
                      padding: const EdgeInsets.all(2),
                      child: Column(
                        children: [
                          Text('${d.day}', style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: d.isWeekend ? VamsTheme.textMuted : VamsTheme.textPrimary)),
                          Text(d.weekday.substring(0, 2), style: TextStyle(fontSize: 8, color: d.isWeekend ? VamsTheme.textMuted : VamsTheme.textSecondary)),
                        ],
                      ),
                    )),
                    const Padding(padding: EdgeInsets.all(4), child: Text('P', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 11, color: VamsTheme.success))),
                    const Padding(padding: EdgeInsets.all(4), child: Text('A', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 11, color: VamsTheme.danger))),
                    const Padding(padding: EdgeInsets.all(4), child: Text('H', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 11, color: VamsTheme.warning))),
                    const Padding(padding: EdgeInsets.all(4), child: Text('L', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 11, color: VamsTheme.textMuted))),
                    const Padding(padding: EdgeInsets.all(4), child: Text('%', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 11))),
                  ],
                ),
                ...employees.map((emp) {
                  final empData = emp as dynamic;
                  return TableRow(
                    decoration: BoxDecoration(
                      border: Border(bottom: BorderSide(color: VamsTheme.border.withOpacity(0.5), width: 0.5)),
                    ),
                    children: [
                      Padding(
                        padding: const EdgeInsets.all(8),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(empData.name, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12), overflow: TextOverflow.ellipsis),
                            if (empData.department != null)
                              Text(empData.department, style: const TextStyle(fontSize: 9, color: VamsTheme.textMuted), overflow: TextOverflow.ellipsis),
                          ],
                        ),
                      ),
                      ...List.generate(numDays, (i) {
                        final dayNum = i + 1;
                        final status = empData.days[dayNum.toString()];
                        final dayInfo = days[i];
                        final isWeekend = dayInfo.isWeekend;
                        final holiday = dayInfo.holiday;

                        Color bgColor = Colors.transparent;
                        Color textColor = VamsTheme.textMuted;
                        String label = '--';

                        if (holiday != null) {
                          bgColor = VamsTheme.warning.withOpacity(0.15);
                          textColor = VamsTheme.warning;
                          label = 'H';
                        } else if (isWeekend) {
                          bgColor = VamsTheme.background;
                          label = 'W';
                        } else if (status == 'present') {
                          bgColor = VamsTheme.success.withOpacity(0.15);
                          textColor = VamsTheme.success;
                          label = '\u2713';
                        } else if (status == 'absent') {
                          bgColor = VamsTheme.danger.withOpacity(0.15);
                          textColor = VamsTheme.danger;
                          label = '\u2717';
                        } else if (status == 'half_day') {
                          bgColor = VamsTheme.warning.withOpacity(0.15);
                          textColor = VamsTheme.warning;
                          label = 'H';
                        } else if (status == 'leave') {
                          bgColor = VamsTheme.textMuted.withOpacity(0.15);
                          textColor = VamsTheme.textMuted;
                          label = 'L';
                        }

                        return Container(
                          margin: const EdgeInsets.all(1),
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          decoration: BoxDecoration(
                            color: bgColor,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Center(
                            child: Text(label, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: textColor)),
                          ),
                        );
                      }),
                      Padding(padding: const EdgeInsets.all(4), child: Text('${empData.present}', style: const TextStyle(fontSize: 11, color: VamsTheme.success))),
                      Padding(padding: const EdgeInsets.all(4), child: Text('${empData.absent}', style: const TextStyle(fontSize: 11, color: VamsTheme.danger))),
                      Padding(padding: const EdgeInsets.all(4), child: Text('${empData.halfDay}', style: const TextStyle(fontSize: 11, color: VamsTheme.warning))),
                      Padding(padding: const EdgeInsets.all(4), child: Text('${empData.leave}', style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted))),
                      Padding(
                        padding: const EdgeInsets.all(4),
                        child: Text(
                          '${empData.percentage.toInt()}%',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: empData.percentage >= 80 ? VamsTheme.success : VamsTheme.danger,
                          ),
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
}

class _AttendanceQrInline extends ConsumerWidget {
  const _AttendanceQrInline();

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
