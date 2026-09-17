import 'package:flutter/material.dart';

class AppTheme {
  static const forest = Color(0xFF0A5C4A);
  static const mint = Color(0xFFE7F4EF);
  static const ink = Color(0xFF17342D);
  static const sand = Color(0xFFF6F7F3);

  static ThemeData get light {
    final scheme = ColorScheme.fromSeed(
      seedColor: forest,
      brightness: Brightness.light,
      surface: Colors.white,
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: sand,
      fontFamily: 'sans-serif',
      cardTheme: const CardThemeData(
        color: Colors.white,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(18)),
          side: BorderSide(color: Color(0xFFDDE5E1)),
        ),
      ),
      inputDecorationTheme: const InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.all(Radius.circular(12)),
        ),
      ),
      navigationRailTheme: const NavigationRailThemeData(
        backgroundColor: Colors.white,
        indicatorColor: mint,
        selectedIconTheme: IconThemeData(color: forest),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: sand,
        foregroundColor: ink,
        elevation: 0,
      ),
    );
  }
}
