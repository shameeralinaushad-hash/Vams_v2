class OrderListItem {
  final int id;
  final String? orderNumber;
  final String? title;
  final String? status;
  final String? inquiryDate;
  final OrderClient? client;
  final OrderPo? po;
  final String? quotationNumber;

  OrderListItem({
    required this.id,
    this.orderNumber,
    this.title,
    this.status,
    this.inquiryDate,
    this.client,
    this.po,
    this.quotationNumber,
  });

  factory OrderListItem.fromJson(Map<String, dynamic> json) {
    return OrderListItem(
      id: json['id'] ?? 0,
      orderNumber: json['order_number'],
      title: json['title'],
      status: json['status'],
      inquiryDate: json['inquiry_date'],
      client: json['client'] != null ? OrderClient.fromJson(json['client']) : null,
      po: json['po'] != null ? OrderPo.fromJson(json['po']) : null,
      quotationNumber: json['quotation_number'],
    );
  }
}

class OrderClient {
  final int? id;
  final String? name;

  OrderClient({this.id, this.name});
  factory OrderClient.fromJson(Map<String, dynamic> json) {
    return OrderClient(id: json['id'], name: json['name']);
  }
}

class OrderPo {
  final String? poNumber;
  final String? status;
  final double? totalAmount;

  OrderPo({this.poNumber, this.status, this.totalAmount});
  factory OrderPo.fromJson(Map<String, dynamic> json) {
    return OrderPo(
      poNumber: json['po_number'],
      status: json['status'],
      totalAmount: (json['total_amount'] as num?)?.toDouble(),
    );
  }
}

class OrderDetail {
  final int id;
  final String? orderNumber;
  final String? title;
  final String? status;
  final String? inquiryDate;
  final String? notes;
  final OrderClient? client;
  final OrderCompany? company;
  final PurchaseOrderInfo? purchaseOrder;
  final List<QuotationInfo> quotations;
  final List<InvoiceInfo> invoices;
  final List<ChallanInfo> deliveryChallans;

  OrderDetail({
    required this.id,
    this.orderNumber,
    this.title,
    this.status,
    this.inquiryDate,
    this.notes,
    this.client,
    this.company,
    this.purchaseOrder,
    this.quotations = const [],
    this.invoices = const [],
    this.deliveryChallans = const [],
  });

  factory OrderDetail.fromJson(Map<String, dynamic> json) {
    return OrderDetail(
      id: json['id'] ?? 0,
      orderNumber: json['order_number'],
      title: json['title'],
      status: json['status'],
      inquiryDate: json['inquiry_date'],
      notes: json['notes'],
      client: json['client'] != null ? OrderClient.fromJson(json['client']) : null,
      company: json['company'] != null ? OrderCompany.fromJson(json['company']) : null,
      purchaseOrder: json['purchase_order'] != null ? PurchaseOrderInfo.fromJson(json['purchase_order']) : null,
      quotations: (json['quotations'] as List? ?? []).map((q) => QuotationInfo.fromJson(q)).toList(),
      invoices: (json['invoices'] as List? ?? []).map((i) => InvoiceInfo.fromJson(i)).toList(),
      deliveryChallans: (json['delivery_challans'] as List? ?? []).map((c) => ChallanInfo.fromJson(c)).toList(),
    );
  }
}

class OrderCompany {
  final int? id;
  final String? name;
  OrderCompany({this.id, this.name});
  factory OrderCompany.fromJson(Map<String, dynamic> json) {
    return OrderCompany(id: json['id'], name: json['name']);
  }
}

class PurchaseOrderInfo {
  final int? id;
  final String? poNumber;
  final String? poDate;
  final String? status;
  final double? totalAmount;

  PurchaseOrderInfo({this.id, this.poNumber, this.poDate, this.status, this.totalAmount});
  factory PurchaseOrderInfo.fromJson(Map<String, dynamic> json) {
    return PurchaseOrderInfo(
      id: json['id'],
      poNumber: json['po_number'],
      poDate: json['po_date'],
      status: json['status'],
      totalAmount: (json['total_amount'] as num?)?.toDouble(),
    );
  }
}

class QuotationInfo {
  final int id;
  final String? quoteNumber;
  final String? quoteDate;
  final String? docType;
  final String? subject;
  final double? taxAmount;
  final double? discountAmount;
  final String? pdfPath;
  final List<LineItem> lineItems;

  QuotationInfo({
    required this.id,
    this.quoteNumber,
    this.quoteDate,
    this.docType,
    this.subject,
    this.taxAmount,
    this.discountAmount,
    this.pdfPath,
    this.lineItems = const [],
  });

  factory QuotationInfo.fromJson(Map<String, dynamic> json) {
    return QuotationInfo(
      id: json['id'] ?? 0,
      quoteNumber: json['quote_number'],
      quoteDate: json['quote_date'],
      docType: json['doc_type'],
      subject: json['subject'],
      taxAmount: (json['tax_amount'] as num?)?.toDouble(),
      discountAmount: (json['discount_amount'] as num?)?.toDouble(),
      pdfPath: json['pdf_path'],
      lineItems: (json['line_items'] as List? ?? []).map((l) => LineItem.fromJson(l)).toList(),
    );
  }
}

class LineItem {
  final int? id;
  final String? partNo;
  final String? description;
  final String? unit;
  final double? qty;
  final double? unitPrice;
  final double? taxPercent;

  LineItem({this.id, this.partNo, this.description, this.unit, this.qty, this.unitPrice, this.taxPercent});
  factory LineItem.fromJson(Map<String, dynamic> json) {
    return LineItem(
      id: json['id'],
      partNo: json['part_no'],
      description: json['description'],
      unit: json['unit'],
      qty: (json['qty'] as num?)?.toDouble(),
      unitPrice: (json['unit_price'] as num?)?.toDouble(),
      taxPercent: (json['tax_percent'] as num?)?.toDouble(),
    );
  }

  double get lineTotal => (qty ?? 0) * (unitPrice ?? 0);
}

class InvoiceInfo {
  final int id;
  final String? invoiceNumber;
  final String? invoiceDate;
  final double? totalAmount;
  final String? status;
  final double? balanceDue;
  final double? totalPaid;
  final bool? isFullyPaid;
  final String? pdfPath;
  final List<PaymentInfo> payments;

  InvoiceInfo({
    required this.id,
    this.invoiceNumber,
    this.invoiceDate,
    this.totalAmount,
    this.status,
    this.balanceDue,
    this.totalPaid,
    this.isFullyPaid,
    this.pdfPath,
    this.payments = const [],
  });

  factory InvoiceInfo.fromJson(Map<String, dynamic> json) {
    return InvoiceInfo(
      id: json['id'] ?? 0,
      invoiceNumber: json['invoice_number'],
      invoiceDate: json['invoice_date'],
      totalAmount: (json['total_amount'] as num?)?.toDouble(),
      status: json['status'],
      balanceDue: (json['balance_due'] as num?)?.toDouble(),
      totalPaid: (json['total_paid'] as num?)?.toDouble(),
      isFullyPaid: json['is_fully_paid'],
      pdfPath: json['pdf_path'],
      payments: (json['payments'] as List? ?? []).map((p) => PaymentInfo.fromJson(p)).toList(),
    );
  }
}

class PaymentInfo {
  final int id;
  final double? amount;
  final String? paidDate;
  final String? method;

  PaymentInfo({required this.id, this.amount, this.paidDate, this.method});
  factory PaymentInfo.fromJson(Map<String, dynamic> json) {
    return PaymentInfo(
      id: json['id'] ?? 0,
      amount: (json['amount'] as num?)?.toDouble(),
      paidDate: json['paid_date'],
      method: json['method'],
    );
  }
}

class ChallanInfo {
  final int id;
  final String? challanNumber;
  final String? dispatchDate;
  final String? transportMode;
  final String? pdfPath;

  ChallanInfo({required this.id, this.challanNumber, this.dispatchDate, this.transportMode, this.pdfPath});
  factory ChallanInfo.fromJson(Map<String, dynamic> json) {
    return ChallanInfo(
      id: json['id'] ?? 0,
      challanNumber: json['challan_number'],
      dispatchDate: json['dispatch_date'],
      transportMode: json['transport_mode'],
      pdfPath: json['pdf_path'],
    );
  }
}

class PaginatedOrders {
  final List<OrderListItem> orders;
  final int total;
  final int pages;
  final int currentPage;

  PaginatedOrders({required this.orders, required this.total, required this.pages, required this.currentPage});

  factory PaginatedOrders.fromJson(Map<String, dynamic> json) {
    return PaginatedOrders(
      orders: (json['orders'] as List? ?? []).map((o) => OrderListItem.fromJson(o)).toList(),
      total: json['total'] ?? 0,
      pages: json['pages'] ?? 0,
      currentPage: json['current_page'] ?? 1,
    );
  }
}
