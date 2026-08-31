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
