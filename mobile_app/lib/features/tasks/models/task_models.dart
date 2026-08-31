class TeamTask {
  final int id;
  final String title;
  final String description;
  final String status;
  final String priority;
  final String? assigneeName;
  final String? assigneeId;
  final String? dueDate;
  final String? createdAt;
  final String? projectName;

  TeamTask({
    required this.id,
    required this.title,
    this.description = '',
    this.status = 'To Do',
    this.priority = 'Medium',
    this.assigneeName,
    this.assigneeId,
    this.dueDate,
    this.createdAt,
    this.projectName,
  });

  factory TeamTask.fromJson(Map<String, dynamic> json) {
    final assignee = json['assignee'] as Map<String, dynamic>?;
    return TeamTask(
      id: json['id'] ?? 0,
      title: json['title'] ?? '',
      description: json['description'] ?? '',
      status: json['status'] ?? 'To Do',
      priority: json['priority'] ?? 'Medium',
      assigneeName: assignee?['name'] ?? json['assignee_name'],
      assigneeId: (assignee?['id'] ?? json['assignee_id'])?.toString(),
      dueDate: json['due_date'],
      createdAt: json['created_at'],
      projectName: json['project_name'],
    );
  }
}

class PersonalItem {
  final int id;
  final String title;
  final String description;
  final String status;
  final String priority;
  final String lane;
  final String? dueDate;
  final String? createdAt;

  PersonalItem({
    required this.id,
    required this.title,
    this.description = '',
    this.status = 'To Do',
    this.priority = 'Medium',
    this.lane = 'Task',
    this.dueDate,
    this.createdAt,
  });

  factory PersonalItem.fromJson(Map<String, dynamic> json) {
    return PersonalItem(
      id: json['id'] ?? 0,
      title: json['title'] ?? '',
      description: json['description'] ?? '',
      status: json['status'] ?? 'To Do',
      priority: json['priority'] ?? 'Medium',
      lane: json['lane'] ?? 'Task',
      dueDate: json['due_date'],
      createdAt: json['created_at'],
    );
  }
}

class TaskDetail {
  final int id;
  final String title;
  final String description;
  final String status;
  final String priority;
  final String? assigneeName;
  final String? assigneeId;
  final String? dueDate;
  final String? createdAt;
  final String? projectName;
  final String? notes;
  final List<TaskComment> comments;

  TaskDetail({
    required this.id,
    required this.title,
    this.description = '',
    this.status = 'To Do',
    this.priority = 'Medium',
    this.assigneeName,
    this.assigneeId,
    this.dueDate,
    this.createdAt,
    this.projectName,
    this.notes,
    this.comments = const [],
  });

  factory TaskDetail.fromJson(Map<String, dynamic> json) {
    final assignee = json['assignee'] as Map<String, dynamic>?;
    return TaskDetail(
      id: json['id'] ?? 0,
      title: json['title'] ?? '',
      description: json['description'] ?? '',
      status: json['status'] ?? 'To Do',
      priority: json['priority'] ?? 'Medium',
      assigneeName: assignee?['name'] ?? json['assignee_name'],
      assigneeId: (assignee?['id'] ?? json['assignee_id'])?.toString(),
      dueDate: json['due_date'],
      createdAt: json['created_at'],
      projectName: json['project_name'],
      notes: json['notes'],
      comments: (json['comments'] as List? ?? [])
          .map((c) => TaskComment.fromJson(c))
          .toList(),
    );
  }
}

class TaskComment {
  final int id;
  final String authorName;
  final String content;
  final String createdAt;

  TaskComment({
    required this.id,
    required this.authorName,
    required this.content,
    required this.createdAt,
  });

  factory TaskComment.fromJson(Map<String, dynamic> json) {
    return TaskComment(
      id: json['id'] ?? 0,
      authorName: json['author_name'] ?? '',
      content: json['content'] ?? '',
      createdAt: json['created_at'] ?? '',
    );
  }
}
