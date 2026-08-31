class ChallanListItem {
  final int id;
  final String? challanNumber;
  final String? dispatchDate;
  final String? transportMode;
  final int? orderId;
  final String? orderNumber;
  final String? clientName;

  ChallanListItem({
    required this.id,
    this.challanNumber,
    this.dispatchDate,
    this.transportMode,
    this.orderId,
    this.orderNumber,
    this.clientName,
  });

  factory ChallanListItem.fromJson(Map<String, dynamic> json) {
    return ChallanListItem(
      id: json['id'] ?? 0,
      challanNumber: json['challan_number'],
      dispatchDate: json['dispatch_date'],
      transportMode: json['transport_mode'],
      orderId: json['order_id'],
      orderNumber: json['order_number'],
      clientName: json['client_name'],
    );
  }
}
