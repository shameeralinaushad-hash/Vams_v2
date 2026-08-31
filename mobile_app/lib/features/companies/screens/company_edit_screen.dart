import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../../companies/providers/companies_provider.dart';

class CompanyEditScreen extends ConsumerStatefulWidget {
  final int? companyId;
  const CompanyEditScreen({super.key, this.companyId});

  @override
  ConsumerState<CompanyEditScreen> createState() => _CompanyEditScreenState();
}

class _CompanyEditScreenState extends ConsumerState<CompanyEditScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _shortNameCtrl = TextEditingController();
  final _addressCtrl = TextEditingController();
  final _phoneCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _taxCtrl = TextEditingController();
  final _locationCtrl = TextEditingController();
  bool _saving = false;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    if (widget.companyId != null) {
      _loadCompany();
    } else {
      _loading = false;
    }
  }

  Future<void> _loadCompany() async {
    try {
      final dio = ref.read(apiClientProvider);
      final response = await dio.get('/api/v1/companies/${widget.companyId}');
      if (response.data['success'] == true) {
        final c = response.data['company'];
        _nameCtrl.text = c['name'] ?? '';
        _shortNameCtrl.text = c['short_name'] ?? '';
        _addressCtrl.text = c['address'] ?? '';
        _phoneCtrl.text = c['phone'] ?? '';
        _emailCtrl.text = c['email'] ?? '';
        _taxCtrl.text = c['tax_number'] ?? '';
        _locationCtrl.text = c['location_code'] ?? '';
      }
    } on DioException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.response?.data?['message'] ?? 'Failed to load company')),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _shortNameCtrl.dispose();
    _addressCtrl.dispose();
    _phoneCtrl.dispose();
    _emailCtrl.dispose();
    _taxCtrl.dispose();
    _locationCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    try {
      final dio = ref.read(apiClientProvider);
      final data = {
        'name': _nameCtrl.text.trim(),
        'short_name': _shortNameCtrl.text.trim().isEmpty ? null : _shortNameCtrl.text.trim(),
        'address': _addressCtrl.text.trim().isEmpty ? null : _addressCtrl.text.trim(),
        'phone': _phoneCtrl.text.trim().isEmpty ? null : _phoneCtrl.text.trim(),
        'email': _emailCtrl.text.trim().isEmpty ? null : _emailCtrl.text.trim(),
        'tax_number': _taxCtrl.text.trim().isEmpty ? null : _taxCtrl.text.trim(),
        'location_code': _locationCtrl.text.trim().isEmpty ? null : _locationCtrl.text.trim(),
      };

      if (widget.companyId != null) {
        await dio.put('/api/v1/companies/${widget.companyId}', data: data);
      } else {
        await dio.post('/api/v1/companies', data: data);
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(widget.companyId != null ? 'Company updated' : 'Company created')),
        );
        ref.invalidate(companiesListProvider);
        context.pop();
      }
    } on DioException catch (e) {
      if (mounted) {
        final msg = e.response?.data is Map ? (e.response?.data['message'] ?? 'Error') : 'Error';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: Text(widget.companyId != null ? 'Edit Company' : 'Add Company')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(title: Text(widget.companyId != null ? 'Edit Company' : 'Add Company')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextFormField(
              controller: _nameCtrl,
              decoration: InputDecoration(labelText: 'Company Name *', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
              validator: (v) => v == null || v.trim().isEmpty ? 'Required' : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _shortNameCtrl,
              decoration: InputDecoration(labelText: 'Short Name', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _addressCtrl,
              decoration: InputDecoration(labelText: 'Address', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
              maxLines: 2,
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(child: TextFormField(
                  controller: _phoneCtrl,
                  decoration: InputDecoration(labelText: 'Phone', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
                  keyboardType: TextInputType.phone,
                )),
                const SizedBox(width: 12),
                Expanded(child: TextFormField(
                  controller: _emailCtrl,
                  decoration: InputDecoration(labelText: 'Email', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
                  keyboardType: TextInputType.emailAddress,
                )),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(child: TextFormField(
                  controller: _taxCtrl,
                  decoration: InputDecoration(labelText: 'Tax Number', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
                )),
                const SizedBox(width: 12),
                Expanded(child: TextFormField(
                  controller: _locationCtrl,
                  decoration: InputDecoration(labelText: 'Location Code', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
                )),
              ],
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: ElevatedButton(
                onPressed: _saving ? null : _submit,
                style: ElevatedButton.styleFrom(
                  backgroundColor: VamsTheme.primary,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                child: _saving
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : Text(widget.companyId != null ? 'Save Changes' : 'Create Company'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
