import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../features/auth/providers/auth_provider.dart';
import '../features/auth/screens/login_screen.dart';
import '../features/auth/screens/server_config_screen.dart';
import '../features/home/screens/home_screen.dart';
import '../features/orders/screens/orders_list_screen.dart';
import '../features/orders/screens/order_detail_screen.dart';
import '../features/orders/screens/create_order_screen.dart';
import '../features/orders/screens/edit_order_screen.dart';
import '../features/orders/screens/create_quotation_screen.dart';
import '../features/orders/screens/create_invoice_screen.dart';
import '../features/orders/screens/create_challan_screen.dart';
import '../features/companies/screens/companies_list_screen.dart';
import '../features/companies/screens/company_detail_screen.dart';
import '../features/more/screens/more_screen.dart';
import '../features/notifications/screens/notifications_screen.dart';
import '../features/tasks/screens/team_tasks_screen.dart';
import '../features/tasks/screens/personal_tasks_screen.dart';
import '../features/tasks/screens/create_team_task_screen.dart';
import '../features/hr/screens/hr_screen.dart';
import '../features/hr/screens/attendance_screen.dart';
import '../features/hr/screens/payroll_screen.dart';
import '../features/accounts/screens/accounts_screen.dart';
import '../features/accounts/screens/expenses_screen.dart';
import '../features/accounts/screens/budgets_screen.dart';
import '../features/profile/screens/profile_screen.dart';
import '../features/profile/screens/edit_profile_screen.dart';
import '../features/profile/screens/change_password_screen.dart';
import '../features/orders/models/order_models.dart';
import '../features/quotations/screens/quotations_list_screen.dart';
import '../features/quotations/screens/edit_quotation_screen.dart';
import '../features/challans/screens/challans_list_screen.dart';
import '../features/invoices/screens/edit_invoice_screen.dart';
import '../features/auth/screens/users_list_screen.dart';
import '../features/auth/screens/user_edit_screen.dart';
import '../features/tasks/screens/edit_team_task_screen.dart';
import '../features/hr/screens/employee_edit_screen.dart';
import '../features/accounts/screens/create_budget_screen.dart';
import '../features/accounts/screens/payments_list_screen.dart';
import '../features/projects/screens/projects_list_screen.dart';
import '../features/todos/screens/todos_screen.dart';
import '../features/companies/screens/company_edit_screen.dart';
import '../features/projects/screens/project_detail_screen.dart';
import '../features/projects/screens/add_project_task_screen.dart';
import '../features/projects/screens/create_project_screen.dart';
import '../features/challans/screens/edit_challan_screen.dart';
import '../features/settings/screens/settings_screen.dart';
import '../features/settings/screens/audit_log_screen.dart';
import '../features/accounts/screens/categories_screen.dart';
import '../features/tasks/screens/task_detail_screen.dart';

String? _handleRedirect(AuthState authState, String location) {
  final isServerConfig = location == '/server-config';
  final isLogin = location == '/login';

  if (authState is AuthServerConfig) {
    return isServerConfig ? null : '/server-config';
  }

  if (authState is AuthAuthenticated) {
    return (isServerConfig || isLogin) ? '/' : null;
  }

  if (authState is AuthLoading || authState is AuthInitial) {
    return isLogin ? null : '/login';
  }

  return isLogin ? null : '/login';
}

final routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);
  debugPrint('[ROUTER] rebuilt. auth=${authState.runtimeType}');

  return GoRouter(
    initialLocation: '/',
    redirect: (context, state) {
      final result = _handleRedirect(authState, state.matchedLocation);
      debugPrint('[ROUTER] ${state.matchedLocation} + ${authState.runtimeType} → $result');
      return result;
    },
    routes: [
      GoRoute(
        path: '/server-config',
        builder: (context, state) => const ServerConfigScreen(),
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      ShellRoute(
        builder: (context, state, child) => HomeShell(child: child),
        routes: [
          GoRoute(
            path: '/',
            builder: (context, state) => const HomeScreen(),
          ),
          GoRoute(
            path: '/orders',
            builder: (context, state) => const OrdersListScreen(),
          ),
          GoRoute(
            path: '/orders/create',
            builder: (context, state) => const CreateOrderScreen(),
          ),
          GoRoute(
            path: '/orders/:orderId',
            builder: (context, state) {
              final orderId = int.parse(state.pathParameters['orderId']!);
              return OrderDetailScreen(orderId: orderId);
            },
          ),
          GoRoute(
            path: '/orders/:orderId/edit',
            builder: (context, state) {
              final orderId = int.parse(state.pathParameters['orderId']!);
              final order = state.extra as OrderDetail;
              return EditOrderScreen(orderId: orderId, order: order);
            },
          ),
          GoRoute(
            path: '/orders/:orderId/quotations/create',
            builder: (context, state) {
              final orderId = int.parse(state.pathParameters['orderId']!);
              return CreateQuotationScreen(orderId: orderId);
            },
          ),
          GoRoute(
            path: '/orders/:orderId/invoices/create',
            builder: (context, state) {
              final orderId = int.parse(state.pathParameters['orderId']!);
              return CreateInvoiceScreen(orderId: orderId);
            },
          ),
          GoRoute(
            path: '/orders/:orderId/challans/create',
            builder: (context, state) {
              final orderId = int.parse(state.pathParameters['orderId']!);
              return CreateChallanScreen(orderId: orderId);
            },
          ),
          GoRoute(
            path: '/companies',
            builder: (context, state) => const CompaniesListScreen(),
          ),
          GoRoute(
            path: '/companies/:companyId',
            builder: (context, state) {
              final companyId = int.parse(state.pathParameters['companyId']!);
              return CompanyDetailScreen(companyId: companyId);
            },
          ),
          GoRoute(
            path: '/more',
            builder: (context, state) => const MoreScreen(),
          ),
          GoRoute(
            path: '/more/notifications',
            builder: (context, state) => const NotificationsScreen(),
          ),
          GoRoute(
            path: '/more/tasks',
            builder: (context, state) => const TeamTasksScreen(),
          ),
          GoRoute(
            path: '/more/tasks/create',
            builder: (context, state) => const CreateTeamTaskScreen(),
          ),
          GoRoute(
            path: '/more/tasks/personal',
            builder: (context, state) => const PersonalTasksScreen(),
          ),
          GoRoute(
            path: '/more/hr',
            builder: (context, state) => const HrScreen(),
          ),
          GoRoute(
            path: '/more/hr/attendance',
            builder: (context, state) => const AttendanceScreen(),
          ),
          GoRoute(
            path: '/more/hr/payroll',
            builder: (context, state) => const PayrollScreen(),
          ),
          GoRoute(
            path: '/more/accounts',
            builder: (context, state) => const AccountsScreen(),
          ),
          GoRoute(
            path: '/more/accounts/expenses',
            builder: (context, state) => const ExpensesScreen(),
          ),
          GoRoute(
            path: '/more/accounts/budgets',
            builder: (context, state) => const BudgetsScreen(),
          ),
          GoRoute(
            path: '/more/profile',
            builder: (context, state) => const ProfileScreen(),
          ),
          GoRoute(
            path: '/more/profile/edit',
            builder: (context, state) => const EditProfileScreen(),
          ),
          GoRoute(
            path: '/more/profile/change-password',
            builder: (context, state) => const ChangePasswordScreen(),
          ),
          GoRoute(
            path: '/more/quotations',
            builder: (context, state) => const QuotationsListScreen(),
          ),
          GoRoute(
            path: '/more/challans',
            builder: (context, state) => const ChallansListScreen(),
          ),
          GoRoute(
            path: '/more/users',
            builder: (context, state) => const UsersListScreen(),
          ),
          GoRoute(
            path: '/more/users/create',
            builder: (context, state) => const UserEditScreen(),
          ),
          GoRoute(
            path: '/more/users/:userId',
            builder: (context, state) {
              final userId = int.parse(state.pathParameters['userId']!);
              return UserEditScreen(userId: userId);
            },
          ),
          GoRoute(
            path: '/orders/:orderId/quotations/:quotationId/edit',
            builder: (context, state) {
              final orderId = int.parse(state.pathParameters['orderId']!);
              final quotationId = int.parse(state.pathParameters['quotationId']!);
              return EditQuotationScreen(quotationId: quotationId, orderId: orderId);
            },
          ),
          GoRoute(
            path: '/orders/:orderId/invoices/:invoiceId/edit',
            builder: (context, state) {
              final orderId = int.parse(state.pathParameters['orderId']!);
              final invoiceId = int.parse(state.pathParameters['invoiceId']!);
              return EditInvoiceScreen(invoiceId: invoiceId, orderId: orderId);
            },
          ),
          GoRoute(
            path: '/more/tasks/:taskId/edit',
            builder: (context, state) {
              final taskId = int.parse(state.pathParameters['taskId']!);
              return EditTeamTaskScreen(taskId: taskId);
            },
          ),
          GoRoute(
            path: '/more/hr/employees/create',
            builder: (context, state) => const EmployeeEditScreen(),
          ),
          GoRoute(
            path: '/more/hr/employees/:empId/edit',
            builder: (context, state) {
              final empId = int.parse(state.pathParameters['empId']!);
              return EmployeeEditScreen(employeeId: empId);
            },
          ),
          GoRoute(
            path: '/more/accounts/budgets/create',
            builder: (context, state) => const CreateBudgetScreen(),
          ),
          GoRoute(
            path: '/more/accounts/payments',
            builder: (context, state) => const PaymentsListScreen(),
          ),
          GoRoute(
            path: '/more/projects',
            builder: (context, state) => const ProjectsListScreen(),
          ),
          GoRoute(
            path: '/more/projects/create',
            builder: (context, state) => const CreateProjectScreen(),
          ),
          GoRoute(
            path: '/more/todos',
            builder: (context, state) => const TodosScreen(),
          ),
          GoRoute(
            path: '/more/companies/create',
            builder: (context, state) => const CompanyEditScreen(),
          ),
          GoRoute(
            path: '/more/companies/:companyId/edit',
            builder: (context, state) {
              final companyId = int.parse(state.pathParameters['companyId']!);
              return CompanyEditScreen(companyId: companyId);
            },
          ),
          GoRoute(
            path: '/more/projects/:projectId',
            builder: (context, state) {
              final projectId = int.parse(state.pathParameters['projectId']!);
              return ProjectDetailScreen(projectId: projectId);
            },
          ),
          GoRoute(
            path: '/more/projects/:projectId/tasks/create',
            builder: (context, state) {
              final projectId = int.parse(state.pathParameters['projectId']!);
              return AddProjectTaskScreen(projectId: projectId);
            },
          ),
          GoRoute(
            path: '/orders/:orderId/challans/:challanId/edit',
            builder: (context, state) {
              final orderId = int.parse(state.pathParameters['orderId']!);
              final challanId = int.parse(state.pathParameters['challanId']!);
              return EditChallanScreen(challanId: challanId, orderId: orderId);
            },
          ),
          GoRoute(
            path: '/more/settings',
            builder: (context, state) => const SettingsScreen(),
          ),
          GoRoute(
            path: '/more/audit-log',
            builder: (context, state) => const AuditLogScreen(),
          ),
          GoRoute(
            path: '/more/accounts/categories',
            builder: (context, state) => const CategoriesScreen(),
          ),
          GoRoute(
            path: '/more/tasks/:taskId/detail',
            builder: (context, state) {
              final taskId = int.parse(state.pathParameters['taskId']!);
              return TaskDetailScreen(taskId: taskId);
            },
          ),
        ],
      ),
    ],
  );
});

class HomeShell extends StatelessWidget {
  final Widget child;
  const HomeShell({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _calculateSelectedIndex(context),
        onDestinationSelected: (index) => _onItemTapped(index, context),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.shopping_bag_outlined),
            selectedIcon: Icon(Icons.shopping_bag),
            label: 'Orders',
          ),
          NavigationDestination(
            icon: Icon(Icons.business_outlined),
            selectedIcon: Icon(Icons.business),
            label: 'Companies',
          ),
          NavigationDestination(
            icon: Icon(Icons.more_horiz_outlined),
            selectedIcon: Icon(Icons.more_horiz),
            label: 'More',
          ),
        ],
      ),
    );
  }

  int _calculateSelectedIndex(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;
    if (location.startsWith('/orders')) return 1;
    if (location.startsWith('/companies')) return 2;
    if (location.startsWith('/more')) return 3;
    return 0;
  }

  void _onItemTapped(int index, BuildContext context) {
    switch (index) {
      case 0:
        context.go('/');
        break;
      case 1:
        context.go('/orders');
        break;
      case 2:
        context.go('/companies');
        break;
      case 3:
        context.go('/more');
        break;
    }
  }
}
