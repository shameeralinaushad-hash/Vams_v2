import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:url_launcher/url_launcher.dart';

class UpdateInfo {
  final String latestVersion;
  final int versionCode;
  final String apkUrl;
  final String releaseNotes;
  final bool forceUpdate;

  UpdateInfo({
    required this.latestVersion,
    required this.versionCode,
    required this.apkUrl,
    required this.releaseNotes,
    required this.forceUpdate,
  });

  factory UpdateInfo.fromJson(Map<String, dynamic> json) {
    return UpdateInfo(
      latestVersion: json['latest_version'] ?? '0.0.0',
      versionCode: json['version_code'] ?? 0,
      apkUrl: json['apk_url'] ?? '',
      releaseNotes: json['release_notes'] ?? '',
      forceUpdate: json['force_update'] ?? false,
    );
  }
}

class UpdateChecker {
  static const _storage = FlutterSecureStorage();

  static Future<UpdateInfo?> check() async {
    try {
      final serverUrl = await _storage.read(key: 'server_url');
      if (serverUrl == null || serverUrl.isEmpty) return null;

      final dio = Dio();
      final response = await dio.get(
        '$serverUrl/api/v1/app-version',
        options: Options(
          receiveTimeout: const Duration(seconds: 5),
          sendTimeout: const Duration(seconds: 5),
        ),
      );

      if (response.statusCode == 200 && response.data['success'] == true) {
        final updateInfo = UpdateInfo.fromJson(response.data);

        final packageInfo = await PackageInfo.fromPlatform();
        final installedBuildNumber = int.tryParse(packageInfo.buildNumber) ?? 0;

        if (updateInfo.versionCode > installedBuildNumber) {
          return updateInfo;
        }
      }
      return null;
    } catch (e) {
      debugPrint('Update check failed: $e');
      return null;
    }
  }

  static void showUpdateDialog(BuildContext context, UpdateInfo info) {
    showDialog(
      context: context,
      barrierDismissible: !info.forceUpdate,
      builder: (context) => AlertDialog(
        icon: Icon(
          Icons.system_update,
          size: 48,
          color: Theme.of(context).colorScheme.primary,
        ),
        title: Text(info.forceUpdate ? 'Update Required' : 'Update Available'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Version ${info.latestVersion}',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
              ),
              const SizedBox(height: 12),
              if (info.releaseNotes.isNotEmpty) ...[
                Text(
                  'What\'s new:',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                ),
                const SizedBox(height: 4),
                Text(
                  info.releaseNotes,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ],
            ],
          ),
        ),
        actions: [
          if (!info.forceUpdate)
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Later'),
            ),
          FilledButton(
            onPressed: () async {
              final uri = Uri.parse(info.apkUrl);
              if (await canLaunchUrl(uri)) {
                await launchUrl(uri, mode: LaunchMode.externalApplication);
              }
              if (context.mounted) {
                Navigator.of(context).pop();
              }
            },
            child: const Text('Update Now'),
          ),
        ],
      ),
    );
  }
}
