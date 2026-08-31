class InvoiceListItem {
  final int id;
  final String? invoiceNumber;
  final String? invoiceDate;
  final double totalAmount;
  final String status;
  final double balanceDue;
  final double totalPaid;
  final bool isFullyPaid;
  final int? orderId;
  final String? orderNumber;
  final InvoiceClient? client;

  InvoiceListItem({
    required this.id,
    this.invoiceNumber,
    this.invoiceDate,
    this.totalAmount = 0,
    this.status = 'issued',
    this.balanceDue = 0,
    this.totalPaid = 0,
    this.isFullyPaid = false,
    this.orderId,
    this.orderNumber,
    this.client,
  });

  factory InvoiceListItem.fromJson(Map<String, dynamic> json) {
    return InvoiceListItem(
      id: json['id'] ?? 0,
      invoiceNumber: json['invoice_number'],
      invoiceDate: json['invoice_date'],
      totalAmount: (json['total_amount'] ?? 0).toDouble(),
      status: json['status'] ?? 'issued',
      balanceDue: (json['balance_due'] ?? 0).toDouble(),
      totalPaid: (json['total_paid'] ?? 0).toDouble(),
      isFullyPaid: json['is_fully_paid'] ?? false,
      orderId: json['order_id'],
      orderNumber: json['order_number'],
      client: json['client'] != null ? InvoiceClient.fromJson(json['client']) : null,
    );
  }
}

class InvoiceClient {
  final int id;
  final String name;

  InvoiceClient({required this.id, required this.name});

  factory InvoiceClient.fromJson(Map<String, dynamic> json) {
    return InvoiceClient(id: json['id'] ?? 0, name: json['name'] ?? '');
  }
}

class InvoiceDetail {
  final int id;
  final String? invoiceNumber;
  final String? invoiceDate;
  final double totalAmount;
  final String status;
  final double balanceDue;
  final double totalPaid;
  final bool isFullyPaid;
  final double discountAmount;
  final double installationCharges;
  final double transportationCharges;
  final double taxAmount;
  final String? pdfPath;
  final String? recipient;
  final int? orderId;
  final InvoiceOrder? order;
  final InvoiceClient? client;
  final InvoiceCompany? company;
  final List<InvoiceLineItem> lineItems;
  final List<InvoicePayment> payments;
  final List<InvoiceCreditNote> creditNotes;

  InvoiceDetail({
    required this.id,
    this.invoiceNumber,
    this.invoiceDate,
    this.totalAmount = 0,
    this.status = 'issued',
    this.balanceDue = 0,
    this.totalPaid = 0,
    this.isFullyPaid = false,
    this.discountAmount = 0,
    this.installationCharges = 0,
    this.transportationCharges = 0,
    this.taxAmount = 0,
    this.pdfPath,
    this.recipient,
    this.orderId,
    this.order,
    this.client,
    this.company,
    this.lineItems = const [],
    this.payments = const [],
    this.creditNotes = const [],
  });

  factory InvoiceDetail.fromJson(Map<String, dynamic> json) {
    return InvoiceDetail(
      id: json['id'] ?? 0,
      invoiceNumber: json['invoice_number'],
      invoiceDate: json['invoice_date'],
      totalAmount: (json['total_amount'] ?? 0).toDouble(),
      status: json['status'] ?? 'issued',
      balanceDue: (json['balance_due'] ?? 0).toDouble(),
      totalPaid: (json['total_paid'] ?? 0).toDouble(),
      isFullyPaid: json['is_fully_paid'] ?? false,
      discountAmount: (json['discount_amount'] ?? 0).toDouble(),
      installationCharges: (json['installation_charges'] ?? 0).toDouble(),
      transportationCharges: (json['transportation_charges'] ?? 0).toDouble(),
      taxAmount: (json['tax_amount'] ?? 0).toDouble(),
      pdfPath: json['pdf_path'],
      recipient: json['recipient'],
      orderId: json['order_id'],
      order: json['order'] != null ? InvoiceOrder.fromJson(json['order']) : null,
      client: json['client'] != null ? InvoiceClient.fromJson(json['client']) : null,
      company: json['company'] != null ? InvoiceCompany.fromJson(json['company']) : null,
      lineItems: (json['line_items'] as List? ?? [])
          .map((li) => InvoiceLineItem.fromJson(li))
          .toList(),
      payments: (json['payments'] as List? ?? [])
          .map((p) => InvoicePayment.fromJson(p))
          .toList(),
      creditNotes: (json['credit_notes'] as List? ?? [])
          .map((c) => InvoiceCreditNote.fromJson(c))
          .toList(),
    );
  }
}

class InvoiceOrder {
  final int id;
  final String? orderNumber;
  final String? title;

  InvoiceOrder({required this.id, this.orderNumber, this.title});

  factory InvoiceOrder.fromJson(Map<String, dynamic> json) {
    return InvoiceOrder(
      id: json['id'] ?? 0,
      orderNumber: json['order_number'],
      title: json['title'],
    );
  }
}

class InvoiceCompany {
  final int id;
  final String name;

  InvoiceCompany({required this.id, required this.name});

  factory InvoiceCompany.fromJson(Map<String, dynamic> json) {
    return InvoiceCompany(id: json['id'] ?? 0, name: json['name'] ?? '');
  }
}

class InvoiceLineItem {
  final int id;
  final String? partNo;
  final String? description;
  final String? unit;
  final double qty;
  final double unitPrice;
  final double taxPercent;

  InvoiceLineItem({
    required this.id,
    this.partNo,
    this.description,
    this.unit,
    this.qty = 0,
    this.unitPrice = 0,
    this.taxPercent = 0,
  });

  factory InvoiceLineItem.fromJson(Map<String, dynamic> json) {
    return InvoiceLineItem(
      id: json['id'] ?? 0,
      partNo: json['part_no'],
      description: json['description'],
      unit: json['unit'],
      qty: (json['qty'] ?? 0).toDouble(),
      unitPrice: (json['unit_price'] ?? 0).toDouble(),
      taxPercent: (json['tax_percent'] ?? 0).toDouble(),
    );
  }
}

class InvoicePayment {
  final int id;
  final double amount;
  final String? paidDate;
  final String? method;
  final String? notes;

  InvoicePayment({
    required this.id,
    required this.amount,
    this.paidDate,
    this.method,
    this.notes,
  });

  factory InvoicePayment.fromJson(Map<String, dynamic> json) {
    return InvoicePayment(
      id: json['id'] ?? 0,
      amount: (json['amount'] ?? 0).toDouble(),
      paidDate: json['paid_date'],
      method: json['method'],
      notes: json['notes'],
    );
  }
}

class InvoiceCreditNote {
  final int id;
  final String? creditNumber;
  final String? creditDate;
  final double amount;
  final String? reason;

  InvoiceCreditNote({
    required this.id,
    this.creditNumber,
    this.creditDate,
    this.amount = 0,
    this.reason,
  });

  factory InvoiceCreditNote.fromJson(Map<String, dynamic> json) {
    return InvoiceCreditNote(
      id: json['id'] ?? 0,
      creditNumber: json['credit_number'],
      creditDate: json['credit_date'],
      amount: (json['amount'] ?? 0).toDouble(),
      reason: json['reason'],
    );
  }
}

class PaginatedInvoices {
  final List<InvoiceListItem> invoices;
  final int total;
  final int pages;
  final int currentPage;
  final int perPage;

  PaginatedInvoices({
    required this.invoices,
    required this.total,
    required this.pages,
    required this.currentPage,
    required this.perPage,
  });

  factory PaginatedInvoices.fromJson(Map<String, dynamic> json) {
    return PaginatedInvoices(
      invoices: (json['invoices'] as List? ?? [])
          .map((i) => InvoiceListItem.fromJson(i))
          .toList(),
      total: json['total'] ?? 0,
      pages: json['pages'] ?? 0,
      currentPage: json['current_page'] ?? 1,
      perPage: json['per_page'] ?? 25,
    );
  }
}

class InvoiceSearchResult {
  final int id;
  final String? invoiceNumber;
  final String? client;
  final double totalAmount;
  final String status;

  InvoiceSearchResult({
    required this.id,
    this.invoiceNumber,
    this.client,
    this.totalAmount = 0,
    this.status = 'issued',
  });

  factory InvoiceSearchResult.fromJson(Map<String, dynamic> json) {
    return InvoiceSearchResult(
      id: json['id'] ?? 0,
      invoiceNumber: json['invoice_number'],
      client: json['client'],
      totalAmount: (json['total_amount'] ?? 0).toDouble(),
      status: json['status'] ?? 'issued',
    );
  }
}
