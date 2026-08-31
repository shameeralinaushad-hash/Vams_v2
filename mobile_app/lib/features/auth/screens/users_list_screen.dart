import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/api_client.dart';
import '../../../core/theme.dart';

final usersListProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final dio = ref.read(apiClientProvider);
  final response = await dio.get('/api/v1/auth/users');
  if (response.data['success'] == true) {
    return List<Map<String, dynamic>>.from(response.data['users']);
  }
  return [];
});

class UsersListScreen extends ConsumerWidget {
  const UsersListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final usersAsync = ref.watch(usersListProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('User Management'),
        actions: [
          IconButton(
            icon: const Icon(Icons.person_add_outlined),
            onPressed: () async {
              await context.push('/more/users/create');
              ref.invalidate(usersListProvider);
            },
          ),
        ],
      ),
      body: usersAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (users) {
          if (users.isEmpty) {
            return const Center(child: Text('No users found'));
          }
          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: users.length,
            itemBuilder: (context, index) {
              final user = users[index];
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: VamsTheme.primary.withOpacity(0.1),
                    child: Text(
                      (user['name'] ?? 'U').substring(0, 1).toUpperCase(),
                      style: const TextStyle(color: VamsTheme.primary, fontWeight: FontWeight.w700),
                    ),
                  ),
                  title: Text(user['name'] ?? '', style: const TextStyle(fontWeight: FontWeight.w600)),
                  subtitle: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(user['email'] ?? '', style: const TextStyle(fontSize: 12)),
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                            decoration: BoxDecoration(
                              color: user['role'] == 'admin' ? VamsTheme.primary.withOpacity(0.1) : Colors.grey.withOpacity(0.1),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              user['role'] ?? 'staff',
                              style: TextStyle(
                                fontSize: 10,
                                color: user['role'] == 'admin' ? VamsTheme.primary : Colors.grey,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          const SizedBox(width: 6),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                            decoration: BoxDecoration(
                              color: user['is_active_user'] == true ? Colors.green.withOpacity(0.1) : Colors.red.withOpacity(0.1),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              user['is_active_user'] == true ? 'Active' : 'Inactive',
                              style: TextStyle(
                                fontSize: 10,
                                color: user['is_active_user'] == true ? Colors.green : Colors.red,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  trailing: const Icon(Icons.chevron_right, size: 20),
                  onTap: () async {
                    await context.push('/more/users/${user['id']}');
                    ref.invalidate(usersListProvider);
                  },
                ),
              );
            },
          );
        },
      ),
    );
  }
}
