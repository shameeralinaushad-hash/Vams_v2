import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/api_client.dart';
import 'core/theme.dart';
import 'core/router.dart';
import 'core/update_checker.dart';
import 'core/sse_provider.dart';
import 'features/auth/providers/auth_provider.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ProviderScope(child: VamsApp()));
}

class VamsApp extends ConsumerStatefulWidget {
  const VamsApp({super.key});

  @override
  ConsumerState<VamsApp> createState() => _VamsAppState();
}

class _VamsAppState extends ConsumerState<VamsApp> {
  @override
  void initState() {
    super.initState();
    debugPrint('[MAIN] initState called');
    WidgetsBinding.instance.addPostFrameCallback((_) {
      debugPrint('[MAIN] addPostFrameCallback fired');
      ApiClient.onAuthExpired = () {
        debugPrint('[MAIN] onAuthExpired triggered!');
        if (mounted) {
          ref.read(authProvider.notifier).logout();
        }
      };
      _checkForUpdate();
      ref.read(sseListenerProvider);
    });
  }

  Future<void> _checkForUpdate() async {
    final updateInfo = await UpdateChecker.check();
    if (updateInfo != null && mounted) {
      UpdateChecker.showUpdateDialog(context, updateInfo);
    }
  }

  @override
  Widget build(BuildContext context) {
    debugPrint('[MAIN] build called');
    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      title: 'VAMS',
      debugShowCheckedModeBanner: false,
      theme: VamsTheme.light,
      routerConfig: router,
    );
  }
}
