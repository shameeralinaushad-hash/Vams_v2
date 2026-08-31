class ClientListItem {
  final int id;
  final String name;
  final String? clientCode;
  final String? email;
  final String? contactInfo;
  final String? logoFilename;
  final String? createdAt;

  ClientListItem({
    required this.id,
    required this.name,
    this.clientCode,
    this.email,
    this.contactInfo,
    this.logoFilename,
    this.createdAt,
  });

  factory ClientListItem.fromJson(Map<String, dynamic> json) {
    return ClientListItem(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      clientCode: json['client_code'],
      email: json['email'],
      contactInfo: json['contact_info'],
      logoFilename: json['logo_filename'],
      createdAt: json['created_at'],
    );
  }
}

class ClientDetail {
  final int id;
  final String name;
  final String? address;
  final String? contactInfo;
  final String? taxNumber;
  final String? clientCode;
  final String? email;
  final String? emails;
  final String? domain;
  final String? logoFilename;
  final String? createdAt;
  final bool gstRegistration;
  final String? gstRegistrationNumber;
  final List<ClientCompany> companies;
  final List<ClientSubsidiary> subsidiaries;
  final int orderCount;

  ClientDetail({
    required this.id,
    required this.name,
    this.address,
    this.contactInfo,
    this.taxNumber,
    this.clientCode,
    this.email,
    this.emails,
    this.domain,
    this.logoFilename,
    this.createdAt,
    this.gstRegistration = false,
    this.gstRegistrationNumber,
    this.companies = const [],
    this.subsidiaries = const [],
    this.orderCount = 0,
  });

  factory ClientDetail.fromJson(Map<String, dynamic> json) {
    return ClientDetail(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      address: json['address'],
      contactInfo: json['contact_info'],
      taxNumber: json['tax_number'],
      clientCode: json['client_code'],
      email: json['email'],
      emails: json['emails'],
      domain: json['domain'],
      logoFilename: json['logo_filename'],
      createdAt: json['created_at'],
      gstRegistration: json['gst_registration'] ?? false,
      gstRegistrationNumber: json['gst_registration_number'],
      companies: (json['companies'] as List? ?? [])
          .map((c) => ClientCompany.fromJson(c))
          .toList(),
      subsidiaries: (json['subsidiaries'] as List? ?? [])
          .map((s) => ClientSubsidiary.fromJson(s))
          .toList(),
      orderCount: json['order_count'] ?? 0,
    );
  }
}

class ClientCompany {
  final int id;
  final String name;

  ClientCompany({required this.id, required this.name});

  factory ClientCompany.fromJson(Map<String, dynamic> json) {
    return ClientCompany(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
    );
  }
}

class ClientSubsidiary {
  final int id;
  final String name;
  final String? address;
  final String? contactInfo;
  final String? clientCode;

  ClientSubsidiary({
    required this.id,
    required this.name,
    this.address,
    this.contactInfo,
    this.clientCode,
  });

  factory ClientSubsidiary.fromJson(Map<String, dynamic> json) {
    return ClientSubsidiary(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      address: json['address'],
      contactInfo: json['contact_info'],
      clientCode: json['client_code'],
    );
  }
}

class PaginatedClients {
  final List<ClientListItem> clients;
  final int total;
  final int pages;
  final int currentPage;
  final int perPage;

  PaginatedClients({
    required this.clients,
    required this.total,
    required this.pages,
    required this.currentPage,
    required this.perPage,
  });

  factory PaginatedClients.fromJson(Map<String, dynamic> json) {
    return PaginatedClients(
      clients: (json['clients'] as List? ?? [])
          .map((c) => ClientListItem.fromJson(c))
          .toList(),
      total: json['total'] ?? 0,
      pages: json['pages'] ?? 0,
      currentPage: json['current_page'] ?? 1,
      perPage: json['per_page'] ?? 25,
    );
  }
}

class ClientSearchResult {
  final int id;
  final String name;
  final String? clientCode;
  final String? email;

  ClientSearchResult({
    required this.id,
    required this.name,
    this.clientCode,
    this.email,
  });

  factory ClientSearchResult.fromJson(Map<String, dynamic> json) {
    return ClientSearchResult(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      clientCode: json['client_code'],
      email: json['email'],
    );
  }
}
