import Foundation
import Testing
@testable import CampusOS

// Captured from the backend after `manage.py seed_safelab_demo`.
private let labsJSON = #"""
[{"id": "LAB005", "name": "Mac Lab", "equipment": [{"id": "MAC-MON-01", "name": "External Monitor", "type": "Display", "isAvailable": true}, {"id": "MAC-IMAC-01", "name": "iMac 01", "type": "Computer", "isAvailable": true}]}, {"id": "LAB006", "name": "IoT Lab", "equipment": [{"id": "IOT-ARD-01", "name": "Arduino Uno", "type": "Microcontroller", "isAvailable": true}]}]
"""#

private let reportJSON = #"""
{"id": 26, "labId": "LAB006", "labName": "IoT Lab", "equipmentId": "IOT-ARD-01", "equipmentName": "Arduino Uno", "equipmentType": "Microcontroller", "category": "unexpected_behaviour", "categoryLabel": "Unexpected Behaviour", "severity": "low", "description": "Pin 13 LED stays on after reset.", "status": "pending", "reporter": "Diya Kapoor", "username": "safelab_demo_2", "decisionNote": "", "decidedBy": null, "createdAt": "2026-10-22T07:56:40.701228+00:00", "updatedAt": "2026-10-24T07:56:40.707678+00:00"}
"""#

private let analyticsJSON = #"""
{"byEquipmentType": [{"key": "Computer", "label": "Computer", "count": 5}, {"key": "Microcontroller", "label": "Microcontroller", "count": 4}], "byLab": [{"key": "LAB005", "label": "Mac Lab", "count": 9}], "byStatus": [{"key": "pending", "label": "Pending", "count": 4}, {"key": "approved", "label": "Approved", "count": 3}, {"key": "rejected", "label": "Rejected", "count": 3}, {"key": "under_maintenance", "label": "Under Maintenance", "count": 1}, {"key": "resolved", "label": "Resolved", "count": 15}], "mostReported": [{"key": "IOT-ESP32-01", "label": "ESP32 Development Board", "count": 3}], "monthly": [{"key": "2026-09", "label": "Sep", "count": 5}, {"key": "2026-10", "label": "Oct", "count": 6}], "total": 26}
"""#

private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
    try JSONDecoder.campusOS.decode(T.self, from: Data(json.utf8))
}

final class FakeFaultService: EquipmentFaultService {
    var labs: [FaultLab] = []
    var reports: [EquipmentFaultReport] = []
    var decideResult: Result<EquipmentFaultReport, Error> = .failure(APIError.badResponse)
    private(set) var submissions: [FaultSubmission] = []
    private(set) var decisions: [(id: Int, action: FaultAction, note: String)] = []
    private(set) var analyticsFetches = 0

    func fetchLabs() async throws -> [FaultLab] { labs }
    func fetchReports() async throws -> [EquipmentFaultReport] { reports }

    func submit(_ report: FaultSubmission) async throws -> EquipmentFaultReport {
        submissions.append(report)
        return try decode(EquipmentFaultReport.self, reportJSON)
    }

    func decide(id: Int, action: FaultAction, note: String) async throws -> EquipmentFaultReport {
        decisions.append((id, action, note))
        return try decideResult.get()
    }

    func fetchAnalytics() async throws -> FaultAnalytics {
        analyticsFetches += 1
        return try decode(FaultAnalytics.self, analyticsJSON)
    }
}

@Suite("SafeLab equipment faults")
struct EquipmentFaultDecodingTests {
    @Test func decodesReportAndAnalytics() throws {
        let report = try decode(EquipmentFaultReport.self, reportJSON)
        #expect((report.status, report.equipmentId, report.labName) == (.pending, "IOT-ARD-01", "IoT Lab"))
        #expect(report.status.actions == [.approve, .maintenance, .reject])
        let analytics = try decode(FaultAnalytics.self, analyticsJSON)
        #expect(analytics.total == 26)
        #expect(analytics.byStatus.map(\.count).reduce(0, +) == 26)
    }

    @Test func allowedActionsFollowTheServer() {
        typealias S = EquipmentFaultReport.Status
        #expect(S.approved.actions == [.maintenance, .resolve])
        #expect(S.underMaintenance.actions == [.resolve])
        #expect(S.resolved.actions.isEmpty)
        #expect(S.rejected.actions.isEmpty)
    }

    @Test func categoriesMatchTheSpec() {
        #expect(FaultCategory.allCases.map(\.label) == ["Not Working", "Partially Working", "Physically Damaged",
                                                        "Unexpected Behaviour", "Other Equipment Fault"])
        #expect(FaultCategory.allCases.map(\.rawValue) == ["not_working", "partially_working", "physically_damaged",
                                                           "unexpected_behaviour", "other"])
    }
}

@MainActor
@Suite("EquipmentFaultStore")
struct EquipmentFaultStoreTests {
    private let service = FakeFaultService()

    @Test func equipmentIsLimitedToTheChosenLab() async throws {
        service.labs = try decode([FaultLab].self, labsJSON)
        let store = EquipmentFaultStore(service: service)
        await store.load(staff: false)
        #expect(store.equipment(inLab: "LAB005").map(\.id) == ["MAC-MON-01", "MAC-IMAC-01"])
        #expect(store.equipment(inLab: "LAB006").map(\.name) == ["Arduino Uno"])
        #expect(store.equipment(inLab: nil).isEmpty)
        #expect(store.analytics == nil)   // students don't load analytics
        #expect(service.analyticsFetches == 0)
    }

    @Test func submitSendsLabEquipmentAndFields() async throws {
        service.labs = try decode([FaultLab].self, labsJSON)
        let store = EquipmentFaultStore(service: service)
        await store.load(staff: false)
        let arduino = try #require(store.equipment(inLab: "LAB006").first)
        let report = try await store.submit(labId: "LAB006", equipment: arduino, category: .unexpectedBehaviour,
                                            severity: .low, description: "  Pin 13 LED stays on after reset. ")
        #expect(service.submissions == [FaultSubmission(labId: "LAB006", equipmentId: "IOT-ARD-01",
                                                        category: "unexpected_behaviour", severity: "low",
                                                        description: "Pin 13 LED stays on after reset.")])
        #expect(report.status == .pending)
        #expect(store.reports.first?.id == 26)
    }

    @Test func facultyDecisionReplacesTheReportAndRefreshesCharts() async throws {
        let pending = try decode(EquipmentFaultReport.self, reportJSON)
        service.reports = [pending]
        service.decideResult = .success(try decode(EquipmentFaultReport.self, reportJSON.replacingOccurrences(
            of: #""status": "pending""#, with: #""status": "rejected""#).replacingOccurrences(
            of: #""decisionNote": """#, with: #""decisionNote": "Not a fault""#)))
        let store = EquipmentFaultStore(service: service)
        await store.load(staff: true)
        #expect(store.analytics?.total == 26)
        try await store.decide(pending, .reject, note: " Not a fault ")
        #expect(service.decisions.map(\.note) == ["Not a fault"])
        #expect(store.reports.first?.status == .rejected)
        #expect(store.reports.first?.decisionNote == "Not a fault")
        #expect(service.analyticsFetches == 2)
        #expect(store.busyID == nil)
    }
}
