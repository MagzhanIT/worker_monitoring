import '../models/report_model.dart';
import 'api_service.dart';

class ReportService {
  ReportService(this.api);
  final ApiService api;

  Future<ReportModel> latest() async => ReportModel.fromJson(
    await api.get('/reports/latest') as Map<String, dynamic>,
  );

  Future<ReportModel> generate({String? reportDate}) async =>
      ReportModel.fromJson(
        await api.post('/reports/generate', body: {'report_date': reportDate})
            as Map<String, dynamic>,
      );
}
