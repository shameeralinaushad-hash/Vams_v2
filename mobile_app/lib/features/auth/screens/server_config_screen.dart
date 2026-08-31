import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:dio/dio.dart';
import '../../../core/theme.dart';
import '../providers/auth_provider.dart';

class ServerConfigScreen extends ConsumerStatefulWidget {
  const ServerConfigScreen({super.key});

  @override
  ConsumerState<ServerConfigScreen> createState() => _ServerConfigScreenState();
}

class _ServerConfigScreenState extends ConsumerState<ServerConfigScreen> {
  final _formKey = GlobalKey<FormState>();
  final _urlController = TextEditingController(text: 'https://vamsbeta.dpdns.org');
  bool _isTesting = false;
  String? _error;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _testAndSave() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isTesting = true;
      _error = null;
    });

    final url = _urlController.text.trim().replaceAll(RegExp(r'/+$'), '');

    try {
      final dio = Dio(BaseOptions(
        headers: {
          'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
        },
      ));
      final response = await dio.get(
        '$url/api/v1/app-version',
        options: Options(receiveTimeout: const Duration(seconds: 5)),
      );

      if (response.statusCode == 200) {
        debugPrint('SSE TEST OK url=$url');
        await ref.read(authProvider.notifier).setServerUrl(url);
      } else {
        setState(() => _error = 'Server returned an error. Please check the URL.');
      }
    } on DioException catch (e) {
      String msg;
      debugPrint('SSE TEST ERROR type=${e.type} message=${e.message} uri=${e.requestOptions.uri}');
      if (e.type == DioExceptionType.connectionTimeout || e.type == DioExceptionType.connectionError) {
        msg = 'Cannot connect to this server. Check the URL and your network.';
      } else {
        msg = 'Failed to reach server. Please check the URL. (${e.type})';
      }
      setState(() => _error = msg);
    } catch (e) {
      setState(() => _error = 'Unexpected error. Please try again.');
    } finally {
      if (mounted) setState(() => _isTesting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(VamsTheme.spacing24),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.dns_outlined, size: 56, color: VamsTheme.primary),
                  const SizedBox(height: VamsTheme.spacing16),
                  const Text(
                    'Connect to VAMS',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: VamsTheme.textPrimary),
                  ),
                  const Text(
                    'Enter your VAMS server address',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 14, color: VamsTheme.textSecondary),
                  ),
                  const SizedBox(height: VamsTheme.spacing32),
                  TextFormField(
                    controller: _urlController,
                    keyboardType: TextInputType.url,
                    decoration: const InputDecoration(
                      labelText: 'Server URL',
                      hintText: 'https://vams.example.com',
                      prefixIcon: Icon(Icons.link),
                    ),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return 'Server URL is required';
                      if (!v.startsWith('http://') && !v.startsWith('https://')) {
                        return 'URL must start with http:// or https://';
                      }
                      return null;
                    },
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: VamsTheme.spacing12),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: VamsTheme.danger.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline, color: VamsTheme.danger, size: 18),
                          const SizedBox(width: 8),
                          Expanded(child: Text(_error!, style: const TextStyle(color: VamsTheme.danger, fontSize: 13))),
                        ],
                      ),
                    ),
                  ],
                  const SizedBox(height: VamsTheme.spacing24),
                  SizedBox(
                    height: 50,
                    child: ElevatedButton(
                      onPressed: _isTesting ? null : _testAndSave,
                      child: _isTesting
                          ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                          : const Text('Connect'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
