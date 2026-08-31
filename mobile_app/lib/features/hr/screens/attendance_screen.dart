import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../models/hr_models.dart';
import '../providers/hr_provider.dart';

class AttendanceScreen extends ConsumerStatefulWidget {
  const AttendanceScreen({super.key});

  @override
  ConsumerState<AttendanceScreen> createState() => _AttendanceScreenState();
}

class _AttendanceScreenState extends ConsumerState<AttendanceScreen> {
  bool _isMarking = false;
  AttendanceStatus? _result;

  @override
  Widget build(BuildContext context) {
    final todayAsync = ref.watch(attendanceTodayProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Attendance')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            todayAsync.when(
              loading: () => const SizedBox(height: 100, child: Center(child: CircularProgressIndicator())),
              error: (_, __) => const SizedBox.shrink(),
              data: (data) {
                if (data.isEmpty) return const SizedBox.shrink();
                final todayRecords = data['records'] as List<dynamic>? ?? [];
                return Card(
                  margin: const EdgeInsets.only(bottom: 24),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Today\'s Status',
                          style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                        ),
                        const SizedBox(height: 12),
                        if (todayRecords.isEmpty)
                          const Text(
                            'No attendance recorded today',
                            style: TextStyle(color: VamsTheme.textMuted),
                          )
                        else
                          ...todayRecords.map((record) {
                            final status = record['status'] ?? 'unknown';
                            final statusColor = status == 'present'
                                ? VamsTheme.success
                                : status == 'absent'
                                    ? VamsTheme.danger
                                    : VamsTheme.warning;
                            return Padding(
                              padding: const EdgeInsets.only(bottom: 4),
                              child: Row(
                                children: [
                                  Icon(
                                    status == 'present' ? Icons.check_circle : Icons.schedule,
                                    size: 16,
                                    color: statusColor,
                                  ),
                                  const SizedBox(width: 8),
                                  Text(
                                    '${record['check_in'] ?? '--:--'} - ${record['check_out'] ?? '--:--'}',
                                    style: const TextStyle(fontSize: 14),
                                  ),
                                  const Spacer(),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                    decoration: BoxDecoration(
                                      color: statusColor.withOpacity(0.1),
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Text(
                                      status.toString().toUpperCase(),
                                      style: TextStyle(
                                        fontSize: 11,
                                        fontWeight: FontWeight.w600,
                                        color: statusColor,
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
              },
            ),
            const Spacer(),
            if (_result != null)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16),
                margin: const EdgeInsets.only(bottom: 24),
                decoration: BoxDecoration(
                  color: (_result!.alreadyMarked ? VamsTheme.warning : VamsTheme.success).withOpacity(0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  children: [
                    Icon(
                      _result!.alreadyMarked ? Icons.info_outline : Icons.check_circle_outline,
                      color: _result!.alreadyMarked ? VamsTheme.warning : VamsTheme.success,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        _result!.alreadyMarked
                            ? 'Already marked today (${_result!.status})'
                            : 'Attendance marked successfully!',
                        style: TextStyle(
                          fontWeight: FontWeight.w600,
                          color: _result!.alreadyMarked ? VamsTheme.warning : VamsTheme.success,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            SizedBox(
              width: double.infinity,
              height: 56,
              child: ElevatedButton.icon(
                onPressed: _isMarking ? null : _markAttendance,
                icon: _isMarking
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.fingerprint, size: 24),
                label: Text(_isMarking ? 'Marking...' : 'Mark Attendance', style: const TextStyle(fontSize: 16)),
              ),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }

  Future<void> _markAttendance() async {
    setState(() {
      _isMarking = true;
      _result = null;
    });

    try {
      final dio = ref.read(apiClientProvider);
      final response = await dio.post('/api/v1/hr/attendance/scan');
      if (!mounted) return;

      if (response.data['success'] == true) {
        final status = AttendanceStatus.fromJson(response.data);
        setState(() => _result = status);
        ref.invalidate(attendanceTodayProvider);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(response.data['message'] ?? 'Failed to mark attendance'),
            backgroundColor: VamsTheme.danger,
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Network error. Please try again.'),
          backgroundColor: VamsTheme.danger,
        ),
      );
    } finally {
      if (mounted) setState(() => _isMarking = false);
    }
  }
}
