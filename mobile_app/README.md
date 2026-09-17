# Pharmacy Worker Monitor V2 — manager app

Responsive Flutter Web/iOS/Android interface for the local FastAPI service. It displays backend-calculated anonymous sessions, camera health, reviewable events and local-report status. It never calculates activities or assigns employee identities on the device.

Run `flutter pub get`, `dart analyze`, `flutter test`, then `flutter run -d chrome`. Override the backend at compile time with `--dart-define=API_BASE_URL=http://host:8000` or edit it on the sign-in screen.

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Learn Flutter](https://docs.flutter.dev/get-started/learn-flutter)
- [Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Flutter learning resources](https://docs.flutter.dev/reference/learning-resources)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.
