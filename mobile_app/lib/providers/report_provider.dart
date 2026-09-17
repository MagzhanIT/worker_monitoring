import 'package:flutter/foundation.dart';

import '../models/report_model.dart';
import '../services/report_service.dart';

class ReportProvider extends ChangeNotifier {
  ReportProvider(this.service);
  final ReportService service;
  ReportModel? latestReport;
  bool loading = false;
  String? error;

  Future<void> refresh() async {
    try {
      latestReport = await service.latest();
      notifyListeners();
    } catch (exception) {
      error = exception.toString();
      notifyListeners();
    }
  }

  Future<void> generate(String? reportDate) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      latestReport = await service.generate(reportDate: reportDate);
    } catch (exception) {
      error = exception.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }
}
