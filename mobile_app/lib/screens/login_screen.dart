import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../providers/settings_provider.dart';
import '../theme/app_theme.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final username = TextEditingController(text: 'admin');
  final password = TextEditingController();
  final endpoint = TextEditingController();
  bool hidePassword = true;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (endpoint.text.isEmpty) {
      endpoint.text = context.read<SettingsProvider>().baseUrl;
    }
  }

  @override
  void dispose() {
    username.dispose();
    password.dispose();
    endpoint.dispose();
    super.dispose();
  }

  Future<void> submit() async {
    await context.read<SettingsProvider>().setBaseUrl(endpoint.text);
    if (!mounted) return;
    await context.read<AuthProvider>().login(
      username.text.trim(),
      password.text,
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    return Scaffold(
      body: Row(
        children: [
          if (MediaQuery.sizeOf(context).width >= 900)
            Expanded(
              child: ColoredBox(
                color: AppTheme.forest,
                child: Padding(
                  padding: const EdgeInsets.all(56),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(
                        Icons.local_pharmacy_outlined,
                        color: Colors.white,
                        size: 54,
                      ),
                      const SizedBox(height: 28),
                      Text(
                        'Operations you can review,\nnot judgments you cannot.',
                        style: Theme.of(context).textTheme.displaySmall
                            ?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                            ),
                      ),
                      const SizedBox(height: 18),
                      const Text(
                        'Anonymous worker sessions · conservative activity evidence · clear unavailable periods',
                        style: TextStyle(color: Colors.white70, fontSize: 17),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          Expanded(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(28),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 430),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        'Manager sign in',
                        style: Theme.of(context).textTheme.headlineMedium
                            ?.copyWith(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Pharmacy Operations Analytics using existing CCTV.',
                      ),
                      const SizedBox(height: 28),
                      TextField(
                        controller: endpoint,
                        decoration: const InputDecoration(
                          labelText: 'Backend address',
                          prefixIcon: Icon(Icons.dns_outlined),
                        ),
                      ),
                      const SizedBox(height: 14),
                      TextField(
                        controller: username,
                        autofillHints: const [AutofillHints.username],
                        decoration: const InputDecoration(
                          labelText: 'Username',
                          prefixIcon: Icon(Icons.person_outline),
                        ),
                      ),
                      const SizedBox(height: 14),
                      TextField(
                        controller: password,
                        obscureText: hidePassword,
                        autofillHints: const [AutofillHints.password],
                        onSubmitted: (_) => submit(),
                        decoration: InputDecoration(
                          labelText: 'Password',
                          prefixIcon: const Icon(Icons.lock_outline),
                          suffixIcon: IconButton(
                            onPressed: () =>
                                setState(() => hidePassword = !hidePassword),
                            icon: Icon(
                              hidePassword
                                  ? Icons.visibility_outlined
                                  : Icons.visibility_off_outlined,
                            ),
                          ),
                        ),
                      ),
                      if (auth.error != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 12),
                          child: Text(
                            auth.error!,
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.error,
                            ),
                          ),
                        ),
                      const SizedBox(height: 20),
                      FilledButton.icon(
                        onPressed: auth.loading ? null : submit,
                        icon: const Icon(Icons.login),
                        label: Text(auth.loading ? 'Signing in…' : 'Sign in'),
                      ),
                      const SizedBox(height: 18),
                      const Text(
                        'An administrator exists only when DEFAULT_ADMIN_PASSWORD was explicitly set during backend setup.',
                        style: TextStyle(fontSize: 12, color: Colors.black54),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
