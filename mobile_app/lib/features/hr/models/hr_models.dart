class HrEmployee {
  final int id;
  final String name;
  final String? email;
  final String? phone;
  final String? department;
  final String? designation;
  final String? employeeCode;
  final double baseMonthlySalary;
  final bool isActive;
  final String? dateJoined;

  HrEmployee({
    required this.id,
    required this.name,
    this.email,
    this.phone,
    this.department,
    this.designation,
    this.employeeCode,
    this.baseMonthlySalary = 0,
    this.isActive = true,
    this.dateJoined,
  });

  factory HrEmployee.fromJson(Map<String, dynamic> json) {
    return HrEmployee(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      email: json['email'],
      phone: json['phone'],
      department: json['department'],
      designation: json['designation'],
      employeeCode: json['employee_code'],
      baseMonthlySalary: (json['base_monthly_salary'] ?? 0).toDouble(),
      isActive: json['is_active'] ?? true,
      dateJoined: json['date_joined'],
    );
  }
}

class AttendanceStatus {
  final bool alreadyMarked;
  final String? status;

  AttendanceStatus({this.alreadyMarked = false, this.status});

  factory AttendanceStatus.fromJson(Map<String, dynamic> json) {
    return AttendanceStatus(
      alreadyMarked: json['already_marked'] ?? false,
      status: json['status'],
    );
  }
}

class PayrollRecord {
  final int id;
  final String employeeName;
  final int month;
  final int year;
  final double baseSalary;
  final double finalSalary;
  final String status;

  PayrollRecord({
    required this.id,
    required this.employeeName,
    required this.month,
    required this.year,
    this.baseSalary = 0,
    this.finalSalary = 0,
    this.status = 'draft',
  });

  factory PayrollRecord.fromJson(Map<String, dynamic> json) {
    return PayrollRecord(
      id: json['id'] ?? 0,
      employeeName: json['employee_name'] ?? '',
      month: json['month'] ?? 0,
      year: json['year'] ?? 0,
      baseSalary: (json['base_salary'] ?? 0).toDouble(),
      finalSalary: (json['final_salary'] ?? 0).toDouble(),
      status: json['status'] ?? 'draft',
    );
  }
}

class Holiday {
  final int id;
  final String name;
  final String date;
  final bool isRecurring;

  Holiday({
    required this.id,
    required this.name,
    required this.date,
    this.isRecurring = false,
  });

  factory Holiday.fromJson(Map<String, dynamic> json) {
    return Holiday(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      date: json['date'] ?? '',
      isRecurring: json['is_recurring'] ?? false,
    );
  }
}

class AttendanceDay {
  final int day;
  final String weekday;
  final bool isWeekend;
  final String? holiday;

  AttendanceDay({
    required this.day,
    required this.weekday,
    this.isWeekend = false,
    this.holiday,
  });

  factory AttendanceDay.fromJson(Map<String, dynamic> json) {
    return AttendanceDay(
      day: json['day'] ?? 0,
      weekday: json['weekday'] ?? '',
      isWeekend: json['is_weekend'] ?? false,
      holiday: json['holiday'],
    );
  }
}

class AttendanceEmployee {
  final int id;
  final String name;
  final String? department;
  final String? designation;
  final Map<String, dynamic> days;
  final int present;
  final int absent;
  final int halfDay;
  final int leave;
  final double percentage;

  AttendanceEmployee({
    required this.id,
    required this.name,
    this.department,
    this.designation,
    required this.days,
    this.present = 0,
    this.absent = 0,
    this.halfDay = 0,
    this.leave = 0,
    this.percentage = 0,
  });

  factory AttendanceEmployee.fromJson(Map<String, dynamic> json) {
    return AttendanceEmployee(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      department: json['department'],
      designation: json['designation'],
      days: Map<String, dynamic>.from(json['days'] ?? {}),
      present: json['present'] ?? 0,
      absent: json['absent'] ?? 0,
      halfDay: json['half_day'] ?? 0,
      leave: json['leave'] ?? 0,
      percentage: (json['percentage'] ?? 0).toDouble(),
    );
  }
}

class AttendanceListData {
  final int month;
  final int year;
  final int numDays;
  final List<AttendanceEmployee> employees;
  final List<AttendanceDay> days;

  AttendanceListData({
    required this.month,
    required this.year,
    required this.numDays,
    required this.employees,
    required this.days,
  });

  factory AttendanceListData.fromJson(Map<String, dynamic> json) {
    return AttendanceListData(
      month: json['month'] ?? 0,
      year: json['year'] ?? 0,
      numDays: json['num_days'] ?? 0,
      employees: (json['employees'] as List? ?? [])
          .map((e) => AttendanceEmployee.fromJson(e))
          .toList(),
      days: (json['days'] as List? ?? [])
          .map((d) => AttendanceDay.fromJson(d))
          .toList(),
    );
  }
}

class ProfileDashboard {
  final Map<String, dynamic> user;
  final Map<String, dynamic>? employee;
  final double efficiency;
  final double attnPct;
  final double taskPct;
  final int taskDoneThisMonth;
  final double taskRollingAvg;
  final Map<String, String> heatmap;
  final List<double> monthlyPct;
  final Map<String, dynamic>? leaveStats;
  final List<Map<String, dynamic>> tasks;
  final List<Map<String, dynamic>> payrollHistory;
  final List<Map<String, dynamic>> upcomingHolidays;
  final List<Map<String, dynamic>> notifications;

  ProfileDashboard({
    required this.user,
    this.employee,
    this.efficiency = 0,
    this.attnPct = 0,
    this.taskPct = 0,
    this.taskDoneThisMonth = 0,
    this.taskRollingAvg = 0,
    this.heatmap = const {},
    this.monthlyPct = const [],
    this.leaveStats,
    this.tasks = const [],
    this.payrollHistory = const [],
    this.upcomingHolidays = const [],
    this.notifications = const [],
  });

  factory ProfileDashboard.fromJson(Map<String, dynamic> json) {
    return ProfileDashboard(
      user: Map<String, dynamic>.from(json['user'] ?? {}),
      employee: json['employee'] != null ? Map<String, dynamic>.from(json['employee']) : null,
      efficiency: (json['efficiency'] ?? 0).toDouble(),
      attnPct: (json['attn_pct'] ?? 0).toDouble(),
      taskPct: (json['task_pct'] ?? 0).toDouble(),
      taskDoneThisMonth: json['task_done_this_month'] ?? 0,
      taskRollingAvg: (json['task_rolling_avg'] ?? 0).toDouble(),
      heatmap: Map<String, String>.from(json['heatmap'] ?? {}),
      monthlyPct: (json['monthly_pct'] as List? ?? []).map((e) => (e as num).toDouble()).toList(),
      leaveStats: json['leave_stats'] != null ? Map<String, dynamic>.from(json['leave_stats']) : null,
      tasks: (json['tasks'] as List? ?? []).map((e) => Map<String, dynamic>.from(e)).toList(),
      payrollHistory: (json['payroll_history'] as List? ?? []).map((e) => Map<String, dynamic>.from(e)).toList(),
      upcomingHolidays: (json['upcoming_holidays'] as List? ?? []).map((e) => Map<String, dynamic>.from(e)).toList(),
      notifications: (json['notifications'] as List? ?? []).map((e) => Map<String, dynamic>.from(e)).toList(),
    );
  }
}
