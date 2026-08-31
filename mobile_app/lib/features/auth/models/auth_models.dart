class Company {
  final int id;
  final String name;

  Company({required this.id, required this.name});

  factory Company.fromJson(Map<String, dynamic> json) {
    return Company(id: json['id'] ?? 0, name: json['name'] ?? '');
  }
}

class LoginRequest {
  final String email;
  final String password;
  final int? companyId;

  LoginRequest({required this.email, required this.password, this.companyId});

  Map<String, dynamic> toJson() => {
    'email': email,
    'password': password,
    if (companyId != null) 'company_id': companyId,
  };
}

class AuthTokens {
  final String accessToken;
  final String refreshToken;

  AuthTokens({required this.accessToken, required this.refreshToken});

  factory AuthTokens.fromJson(Map<String, dynamic> json) {
    return AuthTokens(
      accessToken: json['access_token'] ?? '',
      refreshToken: json['refresh_token'] ?? '',
    );
  }
}

class UserProfile {
  final int id;
  final String name;
  final String email;
  final String role;
  final int? companyId;
  final String? companyName;

  UserProfile({
    required this.id,
    required this.name,
    required this.email,
    required this.role,
    this.companyId,
    this.companyName,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      email: json['email'] ?? '',
      role: json['role'] ?? 'staff',
      companyId: json['company_id'],
      companyName: json['company_name'],
    );
  }
}
