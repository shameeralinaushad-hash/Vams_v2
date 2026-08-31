import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme.dart';
import '../providers/companies_provider.dart';

class CompanyDetailScreen extends ConsumerWidget {
  final int companyId;

  const CompanyDetailScreen({super.key, required this.companyId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final companyAsync = ref.watch(companyDetailProvider(companyId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Company'),
      ),
      body: companyAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: VamsTheme.danger),
              const SizedBox(height: 12),
              const Text('Failed to load company', style: TextStyle(color: VamsTheme.textSecondary)),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => ref.invalidate(companyDetailProvider(companyId)),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (company) {
          if (company == null) {
            return const Center(child: Text('Company not found'));
          }

          final initials = company.name.length >= 2
              ? company.name.substring(0, 2).toUpperCase()
              : company.name.toUpperCase();

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    children: [
                      Row(
                        children: [
                          Container(
                            width: 56,
                            height: 56,
                            decoration: BoxDecoration(
                              color: VamsTheme.primary.withOpacity(0.1),
                              borderRadius: BorderRadius.circular(16),
                            ),
                            child: Center(
                              child: Text(
                                initials,
                                style: const TextStyle(
                                  color: VamsTheme.primary,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 20,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 16),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  company.name,
                                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                                ),
                                if (company.shortName != null && company.shortName!.isNotEmpty)
                                  Text(
                                    company.shortName!,
                                    style: const TextStyle(fontSize: 13, color: VamsTheme.textMuted),
                                  ),
                              ],
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      const Divider(height: 1),
                      const SizedBox(height: 12),
                      if (company.email != null && company.email!.isNotEmpty)
                        _InfoRow(icon: Icons.email_outlined, value: company.email!),
                      if (company.phone != null && company.phone!.isNotEmpty)
                        _InfoRow(icon: Icons.phone_outlined, value: company.phone!),
                      if (company.address != null && company.address!.isNotEmpty)
                        _InfoRow(icon: Icons.location_on_outlined, value: company.address!),
                      if (company.locationCode != null && company.locationCode!.isNotEmpty)
                        _InfoRow(icon: Icons.location_city_outlined, value: company.locationCode!),
                    ],
                  ),
                ),
              ),

              if (company.taxNumber != null && company.taxNumber!.isNotEmpty ||
                  company.entityType != null && company.entityType!.isNotEmpty ||
                  company.ein != null && company.ein!.isNotEmpty) ...[
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Tax & Legal', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                        const SizedBox(height: 8),
                        if (company.taxNumber != null && company.taxNumber!.isNotEmpty)
                          _InfoRow(icon: Icons.receipt_outlined, value: 'Tax: ${company.taxNumber}'),
                        if (company.entityType != null && company.entityType!.isNotEmpty)
                          _InfoRow(icon: Icons.business_outlined, value: company.entityType!),
                        if (company.ein != null && company.ein!.isNotEmpty)
                          _InfoRow(icon: Icons.badge_outlined, value: 'EIN: ${company.ein}'),
                        if (company.registeredAgent != null && company.registeredAgent!.isNotEmpty)
                          _InfoRow(icon: Icons.person_outlined, value: company.registeredAgent!),
                      ],
                    ),
                  ),
                ),
              ],

              if (company.authorizedName != null && company.authorizedName!.isNotEmpty ||
                  company.designation != null && company.designation!.isNotEmpty) ...[
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Authorization', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                        const SizedBox(height: 8),
                        if (company.authorizedName != null && company.authorizedName!.isNotEmpty)
                          _InfoRow(icon: Icons.person_outlined, value: company.authorizedName!),
                        if (company.designation != null && company.designation!.isNotEmpty)
                          _InfoRow(icon: Icons.work_outline, value: company.designation!),
                      ],
                    ),
                  ),
                ),
              ],

              if (company.bankDetails != null && company.bankDetails!.isNotEmpty) ...[
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Bank Details', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                        const SizedBox(height: 8),
                        _InfoRow(icon: Icons.account_balance_outlined, value: company.bankDetails!),
                      ],
                    ),
                  ),
                ),
              ],

              if (company.termsConditions != null && company.termsConditions!.isNotEmpty) ...[
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Terms & Conditions', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                        const SizedBox(height: 8),
                        Text(
                          company.termsConditions!,
                          style: const TextStyle(fontSize: 13, color: VamsTheme.textSecondary),
                        ),
                      ],
                    ),
                  ),
                ),
              ],

              const SizedBox(height: 32),
            ],
          );
        },
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String value;
  const _InfoRow({required this.icon, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Icon(icon, size: 16, color: VamsTheme.textMuted),
          const SizedBox(width: 8),
          Expanded(child: Text(value, style: const TextStyle(fontSize: 13))),
        ],
      ),
    );
  }
}
