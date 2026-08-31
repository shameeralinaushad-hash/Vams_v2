import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../../core/storage.dart';
import '../../../core/api_client.dart';
import '../../auth/providers/auth_provider.dart';
import '../../auth/models/auth_models.dart';
import '../providers/companies_provider.dart';

class CompaniesListScreen extends ConsumerStatefulWidget {
  const CompaniesListScreen({super.key});

  @override
  ConsumerState<CompaniesListScreen> createState() => _CompaniesListScreenState();
}

class _CompaniesListScreenState extends ConsumerState<CompaniesListScreen> {
  int? _currentCompanyId;

  @override
  void initState() {
    super.initState();
    _loadCurrentCompany();
  }

  Future<void> _loadCurrentCompany() async {
    final id = await AppStorage.getCompanyId();
    setState(() => _currentCompanyId = id);
  }

  @override
  Widget build(BuildContext context) {
    final companiesAsync = ref.watch(companiesProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Companies'),
      ),
      body: companiesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
              const SizedBox(height: 12),
              const Text('Failed to load companies', style: TextStyle(color: VamsTheme.textSecondary)),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => ref.invalidate(companiesProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (companies) {
          if (companies.isEmpty) {
            return const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.business_outlined, size: 48, color: VamsTheme.textMuted),
                  SizedBox(height: 12),
                  Text('No companies found', style: TextStyle(color: VamsTheme.textSecondary)),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(companiesProvider),
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              itemCount: companies.length,
              itemBuilder: (context, index) {
                final company = companies[index];
                final isSelected = company.id == _currentCompanyId;

                return Card(
                  child: InkWell(
                    onTap: () => context.push('/companies/${company.id}'),
                    borderRadius: BorderRadius.circular(16),
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Row(
                        children: [
                          Container(
                            width: 42,
                            height: 42,
                            decoration: BoxDecoration(
                              color: isSelected
                                  ? VamsTheme.primary.withOpacity(0.15)
                                  : VamsTheme.primary.withOpacity(0.05),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Center(
                              child: Text(
                                company.name.substring(0, company.name.length >= 2 ? 2 : 1).toUpperCase(),
                                style: TextStyle(
                                  color: isSelected ? VamsTheme.primary : VamsTheme.textSecondary,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 14,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        company.name,
                                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    if (isSelected)
                                      const Icon(Icons.check_circle, color: VamsTheme.primary, size: 18),
                                  ],
                                ),
                                const SizedBox(height: 2),
                                if (company.shortName != null && company.shortName!.isNotEmpty)
                                  Text(
                                    company.shortName!,
                                    style: const TextStyle(fontSize: 12, color: VamsTheme.textMuted),
                                  ),
                                if (company.locationCode != null && company.locationCode!.isNotEmpty)
                                  Text(
                                    company.locationCode!,
                                    style: const TextStyle(fontSize: 11, color: VamsTheme.textMuted),
                                  ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 8),
                          if (!isSelected)
                            TextButton(
                              onPressed: () => _switchCompany(company.id),
                              style: TextButton.styleFrom(
                                backgroundColor: VamsTheme.primary.withOpacity(0.08),
                                foregroundColor: VamsTheme.primary,
                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                minimumSize: Size.zero,
                                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              ),
                              child: const Text('Switch', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                            ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }

  Future<void> _switchCompany(int companyId) async {
    final result = await ref.read(authProvider.notifier).selectCompany(companyId);
    if (!mounted) return;

    if (result is AuthError) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message), backgroundColor: VamsTheme.danger),
      );
    } else {
      setState(() => _currentCompanyId = companyId);
      ref.invalidate(companiesProvider);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Company switched')),
      );
    }
  }
}
