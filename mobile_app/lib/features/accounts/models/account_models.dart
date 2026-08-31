class ExpenseItem {
  final int id;
  final String? category;
  final String? categoryName;
  final String scope;
  final double amount;
  final String? expenseDate;
  final String? notes;
  final String? payee;
  final String? paymentMethod;

  ExpenseItem({
    required this.id,
    this.category,
    this.categoryName,
    required this.scope,
    required this.amount,
    this.expenseDate,
    this.notes,
    this.payee,
    this.paymentMethod,
  });

  factory ExpenseItem.fromJson(Map<String, dynamic> json) {
    return ExpenseItem(
      id: json['id'] ?? 0,
      category: json['category'],
      categoryName: json['category_name'],
      scope: json['scope'] ?? 'company',
      amount: (json['amount'] ?? 0).toDouble(),
      expenseDate: json['expense_date'],
      notes: json['notes'],
      payee: json['payee'],
      paymentMethod: json['payment_method'],
    );
  }
}

class ExpenseCategory {
  final int id;
  final String name;
  final String scope;

  ExpenseCategory({required this.id, required this.name, required this.scope});

  factory ExpenseCategory.fromJson(Map<String, dynamic> json) {
    return ExpenseCategory(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      scope: json['scope'] ?? 'general',
    );
  }
}

class BudgetItem {
  final int id;
  final String scope;
  final double amount;
  final int month;
  final int year;
  final String? categoryName;

  BudgetItem({
    required this.id,
    required this.scope,
    required this.amount,
    required this.month,
    required this.year,
    this.categoryName,
  });

  factory BudgetItem.fromJson(Map<String, dynamic> json) {
    return BudgetItem(
      id: json['id'] ?? 0,
      scope: json['scope'] ?? 'company',
      amount: (json['amount'] ?? 0).toDouble(),
      month: json['month'] ?? 0,
      year: json['year'] ?? 0,
      categoryName: json['category_name'],
    );
  }
}
