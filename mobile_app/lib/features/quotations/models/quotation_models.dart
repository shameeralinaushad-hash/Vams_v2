class QuotationListItem {
  final int id;
  final String? quoteNumber;
  final String? quoteDate;
  final String? docType;
  final String? subject;
  final int? orderId;
  final String? orderNumber;
  final String? clientName;

  QuotationListItem({
    required this.id,
    this.quoteNumber,
    this.quoteDate,
    this.docType,
    this.subject,
    this.orderId,
    this.orderNumber,
    this.clientName,
  });

  factory QuotationListItem.fromJson(Map<String, dynamic> json) {
    return QuotationListItem(
      id: json['id'] ?? 0,
      quoteNumber: json['quote_number'],
      quoteDate: json['quote_date'],
      docType: json['doc_type'],
      subject: json['subject'],
      orderId: json['order_id'],
      orderNumber: json['order_number'],
      clientName: json['client_name'],
    );
  }
}
