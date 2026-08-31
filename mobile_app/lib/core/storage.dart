import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AppStorage {
  static const _storage = FlutterSecureStorage();

  static const _keyServerUrl = 'server_url';
  static const _keyAccessToken = 'access_token';
  static const _keyRefreshToken = 'refresh_token';
  static const _keyCompanyId = 'company_id';
  static const _keyCompanyName = 'company_name';
  static const _keyUserName = 'user_name';
  static const _keyUserEmail = 'user_email';
  static const _keyUserRole = 'user_role';

  static Future<String?> getServerUrl() => _storage.read(key: _keyServerUrl);
  static Future<void> setServerUrl(String url) => _storage.write(key: _keyServerUrl, value: url);

  static Future<String?> getAccessToken() => _storage.read(key: _keyAccessToken);
  static Future<void> setAccessToken(String token) => _storage.write(key: _keyAccessToken, value: token);

  static Future<String?> getRefreshToken() => _storage.read(key: _keyRefreshToken);
  static Future<void> setRefreshToken(String token) => _storage.write(key: _keyRefreshToken, value: token);

  static Future<int?> getCompanyId() async {
    final val = await _storage.read(key: _keyCompanyId);
    return val != null ? int.tryParse(val) : null;
  }

  static Future<void> setCompanyId(int id) => _storage.write(key: _keyCompanyId, value: id.toString());

  static Future<String?> getCompanyName() => _storage.read(key: _keyCompanyName);
  static Future<void> setCompanyName(String name) => _storage.write(key: _keyCompanyName, value: name);

  static Future<String?> getUserName() => _storage.read(key: _keyUserName);
  static Future<void> setUserName(String name) => _storage.write(key: _keyUserName, value: name);

  static Future<String?> getUserEmail() => _storage.read(key: _keyUserEmail);
  static Future<void> setUserEmail(String email) => _storage.write(key: _keyUserEmail, value: email);

  static Future<String?> getUserRole() => _storage.read(key: _keyUserRole);
  static Future<void> setUserRole(String role) => _storage.write(key: _keyUserRole, value: role);

  static Future<bool> hasServerUrl() async {
    final url = await _storage.read(key: _keyServerUrl);
    return url != null && url.isNotEmpty;
  }

  static Future<bool> hasToken() async {
    final token = await _storage.read(key: _keyAccessToken);
    return token != null && token.isNotEmpty;
  }

  static Future<void> clearAuth() async {
    await _storage.delete(key: _keyAccessToken);
    await _storage.delete(key: _keyRefreshToken);
    await _storage.delete(key: _keyCompanyId);
    await _storage.delete(key: _keyCompanyName);
    await _storage.delete(key: _keyUserName);
    await _storage.delete(key: _keyUserEmail);
    await _storage.delete(key: _keyUserRole);
  }

  static Future<void> clearAll() async {
    await _storage.deleteAll();
  }
}
