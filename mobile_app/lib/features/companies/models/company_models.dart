class CompanyListItem {
  final int id;
  final String name;
  final String? shortName;
  final String? locationCode;

  CompanyListItem({
    required this.id,
    required this.name,
    this.shortName,
    this.locationCode,
  });

  factory CompanyListItem.fromJson(Map<String, dynamic> json) {
    return CompanyListItem(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      shortName: json['short_name'],
      locationCode: json['location_code'],
    );
  }
}

class CompanyDetail {
  final int id;
  final String name;
  final String? shortName;
  final String? address;
  final String? phone;
  final String? email;
  final String? taxNumber;
  final String? bankDetails;
  final String? authorizedName;
  final String? designation;
  final String? entityType;
  final String? ein;
  final String? registeredAgent;
  final String? termsConditions;
  final String? locationCode;

  CompanyDetail({
    required this.id,
    required this.name,
    this.shortName,
    this.address,
    this.phone,
    this.email,
    this.taxNumber,
    this.bankDetails,
    this.authorizedName,
    this.designation,
    this.entityType,
    this.ein,
    this.registeredAgent,
    this.termsConditions,
    this.locationCode,
  });

  factory CompanyDetail.fromJson(Map<String, dynamic> json) {
    return CompanyDetail(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      shortName: json['short_name'],
      address: json['address'],
      phone: json['phone'],
      email: json['email'],
      taxNumber: json['tax_number'],
      bankDetails: json['bank_details'],
      authorizedName: json['authorized_name'],
      designation: json['designation'],
      entityType: json['entity_type'],
      ein: json['ein'],
      registeredAgent: json['registered_agent'],
      termsConditions: json['terms_conditions'],
      locationCode: json['location_code'],
    );
  }
}
