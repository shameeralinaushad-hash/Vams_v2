class DashboardData {
  final DashboardStats stats;
  final List<RecentOrder> recentOrders;
  final List<DashboardTask> assignedTasks;
  final List<DashboardPersonalTask> personalTasks;

  DashboardData({
    required this.stats,
    required this.recentOrders,
    required this.assignedTasks,
    required this.personalTasks,
  });

  factory DashboardData.fromJson(Map<String, dynamic> json) {
    return DashboardData(
      stats: DashboardStats.fromJson(json['stats'] ?? {}),
      recentOrders: (json['recent_orders'] as List? ?? [])
          .map((o) => RecentOrder.fromJson(o))
          .toList(),
      assignedTasks: (json['assigned_tasks'] as List? ?? [])
          .map((t) => DashboardTask.fromJson(t))
          .toList(),
      personalTasks: (json['personal_tasks'] as List? ?? [])
          .map((t) => DashboardPersonalTask.fromJson(t))
          .toList(),
    );
  }
}

class DashboardStats {
  final int totalOrders;
  final int wonCount;
  final int pendingCount;
  final int notReceivedCount;
  final int deliveredCount;
  final double? winRate;
  final double totalRevenue;
  final double totalPaid;
  final double totalOutstanding;
  final int poPending;
  final int poReceived;
  final int poDelivered;
  final int poCancelled;
  final int clientCount;

  DashboardStats({
    this.totalOrders = 0,
    this.wonCount = 0,
    this.pendingCount = 0,
    this.notReceivedCount = 0,
    this.deliveredCount = 0,
    this.winRate,
    this.totalRevenue = 0,
    this.totalPaid = 0,
    this.totalOutstanding = 0,
    this.poPending = 0,
    this.poReceived = 0,
    this.poDelivered = 0,
    this.poCancelled = 0,
    this.clientCount = 0,
  });

  factory DashboardStats.fromJson(Map<String, dynamic> json) {
    return DashboardStats(
      totalOrders: json['total_orders'] ?? 0,
      wonCount: json['won_count'] ?? 0,
      pendingCount: json['pending_count'] ?? 0,
      notReceivedCount: json['not_received_count'] ?? 0,
      deliveredCount: json['delivered_count'] ?? 0,
      winRate: (json['win_rate'] ?? 0).toDouble(),
      totalRevenue: (json['total_revenue'] ?? 0).toDouble(),
      totalPaid: (json['total_paid'] ?? 0).toDouble(),
      totalOutstanding: (json['total_outstanding'] ?? 0).toDouble(),
      poPending: json['po_pending'] ?? 0,
      poReceived: json['po_received'] ?? 0,
      poDelivered: json['po_delivered'] ?? 0,
      poCancelled: json['po_cancelled'] ?? 0,
      clientCount: json['client_count'] ?? 0,
    );
  }
}

class RecentOrder {
  final int id;
  final String? orderNumber;
  final String? title;
  final String? status;
  final String? inquiryDate;
  final String? client;
  final String? poStatus;
  final double? poAmount;

  RecentOrder({
    required this.id,
    this.orderNumber,
    this.title,
    this.status,
    this.inquiryDate,
    this.client,
    this.poStatus,
    this.poAmount,
  });

  factory RecentOrder.fromJson(Map<String, dynamic> json) {
    return RecentOrder(
      id: json['id'] ?? 0,
      orderNumber: json['order_number'],
      title: json['title'],
      status: json['status'],
      inquiryDate: json['inquiry_date'],
      client: json['client'],
      poStatus: json['po_status'],
      poAmount: (json['po_amount'] ?? 0).toDouble(),
    );
  }
}

class DashboardTask {
  final int id;
  final String title;
  final String status;
  final String priority;
  final String? dueDate;
  final String? orderNumber;

  DashboardTask({
    required this.id,
    required this.title,
    required this.status,
    required this.priority,
    this.dueDate,
    this.orderNumber,
  });

  factory DashboardTask.fromJson(Map<String, dynamic> json) {
    return DashboardTask(
      id: json['id'] ?? 0,
      title: json['title'] ?? '',
      status: json['status'] ?? 'to_do',
      priority: json['priority'] ?? 'medium',
      dueDate: json['due_date'],
      orderNumber: json['order_number']?.toString(),
    );
  }
}

class DashboardPersonalTask {
  final int id;
  final String title;
  final String lane;
  final String status;
  final String priority;
  final String? dueDate;

  DashboardPersonalTask({
    required this.id,
    required this.title,
    required this.lane,
    required this.status,
    required this.priority,
    this.dueDate,
  });

  factory DashboardPersonalTask.fromJson(Map<String, dynamic> json) {
    return DashboardPersonalTask(
      id: json['id'] ?? 0,
      title: json['title'] ?? '',
      lane: json['lane'] ?? 'task',
      status: json['status'] ?? 'in_progress',
      priority: json['priority'] ?? 'medium',
      dueDate: json['due_date'],
    );
  }
}
