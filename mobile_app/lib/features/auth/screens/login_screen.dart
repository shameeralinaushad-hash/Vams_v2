import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme.dart';
import '../models/auth_models.dart';
import '../providers/auth_provider.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _obscurePassword = true;
  bool _isLoading = false;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _handleLogin() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isLoading = true);
    debugPrint('[LOGIN] _handleLogin: calling authProvider.login');

    final result = await ref.read(authProvider.notifier).login(
          _emailController.text.trim(),
          _passwordController.text,
        );

    debugPrint('[LOGIN] _handleLogin: result type=${result.runtimeType}');
    if (!mounted) {
      debugPrint('[LOGIN] _handleLogin: widget NOT mounted after login');
      return;
    }
    setState(() => _isLoading = false);

    if (result is AuthError) {
      debugPrint('[LOGIN] _handleLogin: AuthError - ${result.message}');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message), backgroundColor: VamsTheme.danger),
      );
    } else if (result is AuthNeedsCompany) {
      debugPrint('[LOGIN] _handleLogin: AuthNeedsCompany - showing picker');
      _showCompanyPicker(result.companies);
    } else {
      debugPrint('[LOGIN] _handleLogin: result is ${result.runtimeType} (router should redirect)');
    }
  }

  void _showCompanyPicker(List<Company> companies) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => DraggableScrollableSheet(
        initialChildSize: 0.5,
        minChildSize: 0.3,
        maxChildSize: 0.8,
        expand: false,
        builder: (ctx, scrollController) => Column(
          children: [
            const SizedBox(height: 12),
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.grey.shade300,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: VamsTheme.spacing16),
            const Text(
              'Select Company',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: VamsTheme.spacing8),
            const Text(
              'Choose a company to continue',
              style: TextStyle(fontSize: 13, color: VamsTheme.textSecondary),
            ),
            const SizedBox(height: VamsTheme.spacing16),
            Expanded(
              child: ListView.builder(
                controller: scrollController,
                itemCount: companies.length,
                itemBuilder: (ctx, i) {
                  final company = companies[i];
                  return ListTile(
                    leading: CircleAvatar(
                      backgroundColor: VamsTheme.primary.withValues(alpha: 0.1),
                      child: Text(
                        company.name.substring(0, 1).toUpperCase(),
                        style: const TextStyle(color: VamsTheme.primary, fontWeight: FontWeight.w600),
                      ),
                    ),
                    title: Text(company.name),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () async {
                      Navigator.of(ctx).pop();
                      setState(() => _isLoading = true);
                      final result = await ref.read(authProvider.notifier).selectCompany(company.id);
                      if (!mounted) return;
                      setState(() => _isLoading = false);
                      if (result is AuthError) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text(result.message), backgroundColor: VamsTheme.danger),
                        );
                      }
                    },
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
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
                  const Icon(Icons.business_center, size: 56, color: VamsTheme.primary),
                  const SizedBox(height: VamsTheme.spacing16),
                  const Text(
                    'VAMS',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: VamsTheme.textPrimary),
                  ),
                  const Text(
                    'Sign in to your account',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 14, color: VamsTheme.textSecondary),
                  ),
                  const SizedBox(height: VamsTheme.spacing32),
                  TextFormField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(labelText: 'Email', prefixIcon: Icon(Icons.email_outlined)),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return 'Email is required';
                      if (!v.contains('@')) return 'Enter a valid email';
                      return null;
                    },
                  ),
                  const SizedBox(height: VamsTheme.spacing16),
                  TextFormField(
                    controller: _passwordController,
                    obscureText: _obscurePassword,
                    textInputAction: TextInputAction.done,
                    onFieldSubmitted: (_) => _handleLogin(),
                    decoration: InputDecoration(
                      labelText: 'Password',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(_obscurePassword ? Icons.visibility_off : Icons.visibility),
                        onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
                      ),
                    ),
                    validator: (v) {
                      if (v == null || v.isEmpty) return 'Password is required';
                      return null;
                    },
                  ),
                  const SizedBox(height: VamsTheme.spacing24),
                  SizedBox(
                    height: 50,
                    child: ElevatedButton(
                      onPressed: _isLoading ? null : _handleLogin,
                      child: _isLoading
                          ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                          : const Text('Sign In'),
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
