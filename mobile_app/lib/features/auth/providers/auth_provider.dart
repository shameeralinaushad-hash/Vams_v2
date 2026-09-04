import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:local_auth/local_auth.dart';
import '../../../core/api_client.dart';
import '../../../core/storage.dart';
import '../models/auth_models.dart';

abstract class AuthState {
  const AuthState();
}

class AuthInitial extends AuthState {}

class AuthServerConfig extends AuthState {}

class AuthUnauthenticated extends AuthState {}

class AuthLoading extends AuthState {}

class AuthNeedsCompany extends AuthState {
  final List<Company> companies;
  final String accessToken;
  final String refreshToken;
  final UserProfile user;
  const AuthNeedsCompany({
    required this.companies,
    required this.accessToken,
    required this.refreshToken,
    required this.user,
  });
}

class AuthAuthenticated extends AuthState {
  final UserProfile user;
  const AuthAuthenticated(this.user);
}

class AuthError extends AuthState {
  final String message;
  const AuthError(this.message);
}

class AuthNotifier extends StateNotifier<AuthState> {
  final LocalAuthentication _localAuth = LocalAuthentication();

  AuthNotifier() : super(AuthInitial()) {
    _init();
  }

  Future<void> _init() async {
    debugPrint('[AUTH] _init() called');
    final hasServer = await AppStorage.hasServerUrl();
    if (!hasServer) {
      debugPrint('[AUTH] _init: no server URL → AuthServerConfig');
      state = AuthServerConfig();
      return;
    }

    final hasToken = await AppStorage.hasToken();
    if (!hasToken) {
      debugPrint('[AUTH] _init: no token → AuthUnauthenticated');
      state = AuthUnauthenticated();
      return;
    }

    debugPrint('[AUTH] _init: has server and token, verifying with /me');
    try {
      final dio = ApiClient.instance;
      final response = await dio.get('/api/v1/auth/me');
      debugPrint('[AUTH] _init: /me response status=${response.statusCode}');
      if (response.statusCode == 200 && response.data['success'] == true) {
        final needsCompany = response.data['needs_company'] == true;
        final user = UserProfile.fromJson(response.data['user']);
        if (needsCompany) {
          final companies = (response.data['companies'] as List)
              .map((c) => Company.fromJson(c))
              .toList();
          final accessToken = await AppStorage.getAccessToken() ?? '';
          final refreshToken = await AppStorage.getRefreshToken() ?? '';
          state = AuthNeedsCompany(
            companies: companies,
            accessToken: accessToken,
            refreshToken: refreshToken,
            user: user,
          );
        } else {
          state = AuthAuthenticated(user);
        }
      } else {
        // Token invalid — try refresh before giving up
        final refreshed = await _tryRefreshToken();
        if (refreshed) {
          await _init(); // retry with new token
          return;
        }
        await AppStorage.clearAuth();
        state = AuthUnauthenticated();
      }
    } catch (e) {
      debugPrint('[AUTH] _init: /me failed: $e');
      // Network or other error — try refresh before giving up
      final refreshed = await _tryRefreshToken();
      if (refreshed) {
        await _init(); // retry with new token
        return;
      }
      await AppStorage.clearAuth();
      state = AuthUnauthenticated();
    }
  }

  Future<bool> _tryRefreshToken() async {
    try {
      final refreshToken = await AppStorage.getRefreshToken();
      final serverUrl = await AppStorage.getServerUrl();
      if (refreshToken == null || serverUrl == null) return false;

      final refreshDio = Dio(BaseOptions(
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $refreshToken',
        },
      ));
      final response = await refreshDio.post('$serverUrl/api/v1/auth/refresh');
      if (response.statusCode == 200 && response.data['success'] == true) {
        await AppStorage.setAccessToken(response.data['access_token']);
        debugPrint('[AUTH] _tryRefreshToken: success');
        return true;
      }
      debugPrint('[AUTH] _tryRefreshToken: failed status=${response.statusCode}');
      return false;
    } catch (e) {
      debugPrint('[AUTH] _tryRefreshToken error: $e');
      return false;
    }
  }

  Future<void> setServerUrl(String url) async {
    var cleaned = url.trim();
    cleaned = cleaned.replaceAll(RegExp(r'/+$'), '');
    cleaned = cleaned.replaceAll(RegExp(r':///{2,}'), '://');
    if (!cleaned.startsWith('http://') && !cleaned.startsWith('https://')) {
      cleaned = 'https://$cleaned';
    }
    await AppStorage.setServerUrl(cleaned);
    ApiClient.reset();
    state = AuthUnauthenticated();
  }

  Future<AuthState> login(String email, String password) async {
    debugPrint('[AUTH] login() called for $email');
    state = AuthLoading();
    try {
      final dio = ApiClient.instance;
      debugPrint('[AUTH] login: posting to /api/v1/auth/login');
      final response = await dio.post(
        '/api/v1/auth/login',
        data: LoginRequest(email: email, password: password).toJson(),
      );

      debugPrint('[AUTH] login: response status=${response.statusCode} success=${response.data['success']}');
      if (response.statusCode == 200 && response.data['success'] == true) {
        final tokens = AuthTokens.fromJson(response.data);
        final user = UserProfile.fromJson(response.data['user']);
        debugPrint('[AUTH] login: user=${user.name} company_id=${user.companyId} needs_company=${response.data['needs_company']}');

        await AppStorage.setAccessToken(tokens.accessToken);
        await AppStorage.setRefreshToken(tokens.refreshToken);
        if (await AppStorage.getBiometricEnabled()) {
          await AppStorage.setBiometricRefreshToken(tokens.refreshToken);
        }
        await AppStorage.setUserName(user.name);
        await AppStorage.setUserEmail(user.email);
        await AppStorage.setUserRole(user.role);
        if (user.companyId != null) {
          await AppStorage.setCompanyId(user.companyId!);
        }
        if (user.companyName != null) {
          await AppStorage.setCompanyName(user.companyName!);
        }

        final needsCompany = response.data['needs_company'] == true;
        if (needsCompany) {
          debugPrint('[AUTH] login: needsCompany=true → AuthNeedsCompany');
          final companies = (response.data['companies'] as List)
              .map((c) => Company.fromJson(c))
              .toList();
          state = AuthNeedsCompany(
            companies: companies,
            accessToken: tokens.accessToken,
            refreshToken: tokens.refreshToken,
            user: user,
          );
        } else {
          debugPrint('[AUTH] login: setting state=AuthAuthenticated');
          state = AuthAuthenticated(user);
        }
        debugPrint('[AUTH] login: returning state=${state.runtimeType}');
        return state;
      }

      final msg = response.data['message'] ?? 'Login failed';
      debugPrint('[AUTH] login: failed - $msg');
      state = AuthError(msg);
      return state;
    } on DioException catch (e) {
      String msg;
      debugPrint('[AUTH] login: DioException type=${e.type} status=${e.response?.statusCode}');
      if (e.response?.data is Map && e.response?.data['message'] != null) {
        msg = e.response!.data['message'];
      } else if (e.type == DioExceptionType.connectionTimeout ||
          e.type == DioExceptionType.connectionError) {
        msg = 'Cannot connect to server. Check the URL and try again.';
      } else {
        msg = 'Something went wrong. Please try again.';
      }
      state = AuthError(msg);
      return state;
    } catch (e) {
      debugPrint('[AUTH] login: unexpected error: $e');
      state = const AuthError('Unexpected error. Please try again.');
      return state;
    }
  }

  Future<bool> canUseBiometrics() async {
    try {
      final canAuthenticate = await _localAuth.canCheckBiometrics;
      final isDeviceSupported = await _localAuth.isDeviceSupported();
      debugPrint('[AUTH] canUseBiometrics: canCheckBiometrics=$canAuthenticate isDeviceSupported=$isDeviceSupported');
      return canAuthenticate && isDeviceSupported;
    } catch (e) {
      debugPrint('[AUTH] canUseBiometrics error: $e');
      return false;
    }
  }

  Future<bool> authenticateWithBiometrics() async {
    try {
      debugPrint('[AUTH] authenticateWithBiometrics: calling _localAuth.authenticate()');
      final didAuthenticate = await _localAuth.authenticate(
        localizedReason: 'Authenticate to access VAMS',
        options: const AuthenticationOptions(
          stickyAuth: true,
          biometricOnly: false,
        ),
      );
      debugPrint('[AUTH] authenticateWithBiometrics: result=$didAuthenticate');
      return didAuthenticate;
    } catch (e, stack) {
      debugPrint('[AUTH] authenticateWithBiometrics ERROR: $e');
      debugPrint('[AUTH] authenticateWithBiometrics STACK: $stack');
      return false;
    }
  }

  Future<void> loginWithStoredToken() async {
    debugPrint('[AUTH] loginWithStoredToken() called');
    state = AuthLoading();

    // Try refresh using biometric refresh token (survives logout)
    final biometricRefreshToken = await AppStorage.getBiometricRefreshToken();
    if (biometricRefreshToken != null && biometricRefreshToken.isNotEmpty) {
      try {
        final serverUrl = await AppStorage.getServerUrl();
        if (serverUrl != null) {
          final refreshDio = Dio(BaseOptions(
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer $biometricRefreshToken',
            },
          ));
          final response = await refreshDio.post('$serverUrl/api/v1/auth/refresh');
          if (response.statusCode == 200 && response.data['success'] == true) {
            await AppStorage.setAccessToken(response.data['access_token']);
            debugPrint('[AUTH] loginWithStoredToken: biometric refresh success');
          } else {
            debugPrint('[AUTH] loginWithStoredToken: biometric refresh failed status=${response.statusCode}');
            state = const AuthError('Session expired. Please log in with email and password.');
            return;
          }
        }
      } catch (e) {
        debugPrint('[AUTH] loginWithStoredToken: biometric refresh error: $e');
        state = const AuthError('Session expired. Please log in with email and password.');
        return;
      }
    } else {
      // Fallback: try regular refresh token
      final refreshed = await _tryRefreshToken();
      if (!refreshed) {
        debugPrint('[AUTH] loginWithStoredToken: refresh failed → AuthUnauthenticated');
        state = const AuthError('Session expired. Please log in with email and password.');
        return;
      }
    }

    try {
      final dio = ApiClient.instance;
      final response = await dio.get('/api/v1/auth/me');
      debugPrint('[AUTH] loginWithStoredToken: /me status=${response.statusCode}');
      if (response.statusCode == 200 && response.data['success'] == true) {
        final needsCompany = response.data['needs_company'] == true;
        final user = UserProfile.fromJson(response.data['user']);
        if (needsCompany) {
          final companies = (response.data['companies'] as List)
              .map((c) => Company.fromJson(c))
              .toList();
          final accessToken = await AppStorage.getAccessToken() ?? '';
          final refreshToken = await AppStorage.getRefreshToken() ?? '';
          state = AuthNeedsCompany(
            companies: companies,
            accessToken: accessToken,
            refreshToken: refreshToken,
            user: user,
          );
        } else {
          state = AuthAuthenticated(user);
        }
      } else {
        state = const AuthError('Session expired. Please log in with email and password.');
      }
    } catch (e) {
      debugPrint('[AUTH] loginWithStoredToken failed: $e');
      state = const AuthError('Session expired. Please log in with email and password.');
    }
  }

  Future<AuthState> selectCompany(int companyId) async {
    state = AuthLoading();
    try {
      final dio = ApiClient.instance;
      final response = await dio.post(
        '/api/v1/auth/select-company',
        data: {'company_id': companyId},
      );

      if (response.statusCode == 200 && response.data['success'] == true) {
        final newToken = response.data['access_token'] as String;
        final company = response.data['company'] as Map<String, dynamic>;

        await AppStorage.setAccessToken(newToken);
        await AppStorage.setCompanyId(company['id']);
        await AppStorage.setCompanyName(company['name']);

        final userResponse = await dio.get('/api/v1/auth/me');
        if (userResponse.statusCode == 200 && userResponse.data['success'] == true) {
          final user = UserProfile.fromJson(userResponse.data['user']);
          state = AuthAuthenticated(user);
          return state;
        }

        state = const AuthError('Failed to load profile');
        return state;
      }

      final msg = response.data['message'] ?? 'Failed to select company';
      state = AuthError(msg);
      return state;
    } on DioException catch (e) {
      String msg;
      if (e.response?.data is Map && e.response?.data['message'] != null) {
        msg = e.response!.data['message'];
      } else {
        msg = 'Something went wrong. Please try again.';
      }
      state = AuthError(msg);
      return state;
    } catch (e) {
      debugPrint('Select company error: $e');
      state = const AuthError('Unexpected error. Please try again.');
      return state;
    }
  }

  Future<void> logout() async {
    debugPrint('[AUTH] logout() called');
    await AppStorage.clearAuth();
    ApiClient.reset();
    state = AuthUnauthenticated();
    debugPrint('[AUTH] logout: state=AuthUnauthenticated');
  }

  Future<void> refreshUser() async {
    try {
      final dio = ApiClient.instance;
      final response = await dio.get('/api/v1/auth/me');
      if (response.statusCode == 200 && response.data['success'] == true) {
        final user = UserProfile.fromJson(response.data['user']);
        state = AuthAuthenticated(user);
      }
    } catch (e) {
      debugPrint('[AUTH] refreshUser failed: $e');
    }
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier();
});
