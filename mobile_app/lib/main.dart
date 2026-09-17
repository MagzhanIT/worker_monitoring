import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'config/app_config.dart';
import 'providers/auth_provider.dart';
import 'providers/camera_provider.dart';
import 'providers/report_provider.dart';
import 'providers/settings_provider.dart';
import 'screens/dashboard_screen.dart';
import 'screens/login_screen.dart';
import 'services/api_service.dart';
import 'services/auth_service.dart';
import 'services/report_service.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final api = ApiService(baseUrl: AppConfig.defaultApiBaseUrl);
  runApp(
    MultiProvider(
      providers: [
        Provider.value(value: api),
        ChangeNotifierProvider(create: (_) => SettingsProvider(api)),
        ChangeNotifierProvider(
          create: (_) => AuthProvider(AuthService(api))..restore(),
        ),
        ChangeNotifierProvider(create: (_) => CameraProvider(api)),
        ChangeNotifierProvider(
          create: (_) => ReportProvider(ReportService(api)),
        ),
      ],
      child: const PharmacyMonitorApp(),
    ),
  );
}

class PharmacyMonitorApp extends StatelessWidget {
  const PharmacyMonitorApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Pharmacy Worker Monitor V2',
    debugShowCheckedModeBanner: false,
    theme: AppTheme.light,
    home: Consumer<AuthProvider>(
      builder: (context, auth, _) {
        if (auth.loading && auth.token == null) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        return auth.authenticated
            ? const DashboardScreen()
            : const LoginScreen();
      },
    ),
  );
}
