import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../../hr/providers/hr_provider.dart';

class EmployeeEditScreen extends ConsumerStatefulWidget {
  final int? employeeId;
  const EmployeeEditScreen({super.key, this.employeeId});

  @override
  ConsumerState<EmployeeEditScreen> createState() => _EmployeeEditScreenState();
}

class _EmployeeEditScreenState extends ConsumerState<EmployeeEditScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _phoneCtrl = TextEditingController();
  final _departmentCtrl = TextEditingController();
  final _designationCtrl = TextEditingController();
  final _empCodeCtrl = TextEditingController();
  final _salaryCtrl = TextEditingController(text: '0');
  final _leaveAccrualCtrl = TextEditingController(text: '0');
  bool _isActive = true;
  bool _saving = false;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    if (widget.employeeId != null) {
      _loadEmployee();
    } else {
      _loading = false;
    }
  }

  Future<void> _loadEmployee() async {
    try {
      final dio = ref.read(apiClientProvider);
      final response = await dio.get('/api/v1/hr/employees/${widget.employeeId}');
      if (response.data['success'] == true) {
        final emp = response.data['employee'];
        _nameCtrl.text = emp['name'] ?? '';
        _emailCtrl.text = emp['email'] ?? '';
        _phoneCtrl.text = emp['phone'] ?? '';
        _departmentCtrl.text = emp['department'] ?? '';
        _designationCtrl.text = emp['designation'] ?? '';
        _empCodeCtrl.text = emp['employee_code'] ?? '';
        _salaryCtrl.text = (emp['base_monthly_salary'] ?? 0).toString();
        _leaveAccrualCtrl.text = (emp['monthly_leave_accrual'] ?? 0).toString();
        _isActive = emp['is_active'] ?? true;
      }
    } on DioException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.response?.data?['message'] ?? 'Failed to load employee')),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _phoneCtrl.dispose();
    _departmentCtrl.dispose();
    _designationCtrl.dispose();
    _empCodeCtrl.dispose();
    _salaryCtrl.dispose();
    _leaveAccrualCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    try {
      final dio = ref.read(apiClientProvider);
      final data = {
        'name': _nameCtrl.text.trim(),
        'email': _emailCtrl.text.trim().isEmpty ? null : _emailCtrl.text.trim(),
        'phone': _phoneCtrl.text.trim().isEmpty ? null : _phoneCtrl.text.trim(),
        'department': _departmentCtrl.text.trim().isEmpty ? null : _departmentCtrl.text.trim(),
        'designation': _designationCtrl.text.trim().isEmpty ? null : _designationCtrl.text.trim(),
        'employee_code': _empCodeCtrl.text.trim().isEmpty ? null : _empCodeCtrl.text.trim(),
        'base_monthly_salary': double.tryParse(_salaryCtrl.text) ?? 0,
        'monthly_leave_accrual': double.tryParse(_leaveAccrualCtrl.text) ?? 0,
        'is_active': _isActive,
      };

      if (widget.employeeId != null) {
        await dio.put('/api/v1/hr/employees/${widget.employeeId}', data: data);
      } else {
        await dio.post('/api/v1/hr/employees', data: data);
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(widget.employeeId != null ? 'Employee updated' : 'Employee created')),
        );
        ref.invalidate(hrEmployeesProvider);
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
        appBar: AppBar(title: Text(widget.employeeId != null ? 'Edit Employee' : 'Add Employee')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(title: Text(widget.employeeId != null ? 'Edit Employee' : 'Add Employee')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextFormField(
              controller: _nameCtrl,
              decoration: InputDecoration(labelText: 'Name *', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
              validator: (v) => v == null || v.trim().isEmpty ? 'Required' : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _emailCtrl,
              decoration: InputDecoration(labelText: 'Email', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
              keyboardType: TextInputType.emailAddress,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _phoneCtrl,
              decoration: InputDecoration(labelText: 'Phone', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
              keyboardType: TextInputType.phone,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _departmentCtrl,
              decoration: InputDecoration(labelText: 'Department', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _designationCtrl,
              decoration: InputDecoration(labelText: 'Designation', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _empCodeCtrl,
              decoration: InputDecoration(labelText: 'Employee Code', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _salaryCtrl,
              decoration: InputDecoration(labelText: 'Monthly Salary', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
            ),
            const SizedBox(height: 16),
            SwitchListTile(
              title: const Text('Active'),
              value: _isActive,
              onChanged: (v) => setState(() => _isActive = v),
              contentPadding: EdgeInsets.zero,
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
                    : Text(widget.employeeId != null ? 'Save Changes' : 'Create Employee'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
