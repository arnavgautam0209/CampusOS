import Foundation
import Testing
@testable import CampusOS

/// Captured from GET /api/v1/attendance/sessions/14/report/ after `manage.py seed_attendance_demo`.
private let reportJSON = """
{"session":{"id":14,"title":"Embedded Systems Lecture 01","openedAt":"2026-10-24T03:14:27.685333+00:00","closedAt":"2026-10-24T04:04:27.685333+00:00","status":"final"},"classroom":{"id":"ECE","name":"ECE Classroom"},"faculty":{"name":"Demo Faculty","username":"demo_faculty"},"summary":{"totalStudents":4,"present":2,"absent":2,"attendancePercentage":50.0},"presentStudents":[{"rollNumber":"ECE001","name":"Aarav Sharma","username":"ECE001","status":"present","markedAt":"2026-10-24T03:17:27.685333+00:00","source":"card","cardUid":"A1B2C3D4"},{"rollNumber":"ECE002","name":"Riya Verma","username":"ECE002","status":"present","markedAt":"2026-10-24T03:19:27.685333+00:00","source":"card","cardUid":"B1C2D3E4"}],"absentStudents":[{"rollNumber":"ECE003","name":"Kabir Mehta","username":"ECE003","status":"absent"},{"rollNumber":"ECE004","name":"Ananya Singh","username":"ECE004","status":"absent"}],"notEnrolledAttendees":[],"generatedAt":"2026-10-24T05:17:21.450170+00:00","rosterPolicy":"Students enrolled in the classroom at any time while the session was open."}
"""

/// Captured from GET /api/v1/attendance/sessions/?classroom=ECE (an open session).
private let sessionJSON = """
{"id": 10, "title": "ECE Hardware Test", "classroomId": "ECE", "classroomName": "ECE Classroom", "openedBy": null, "openedAt": "2026-10-24T06:13:49.551447+05:30", "closedAt": null, "presentCount": 1}
"""

private func decodeReport(_ json: String = reportJSON) throws -> SessionReport {
    try JSONDecoder.campusOS.decode(SessionReport.self, from: Data(json.utf8))
}

final class FakeReportService: AttendanceReportService {
    var sessions: [AttendanceSessionSummary] = []
    var reports: [Result<SessionReport, Error>] = []
    var pdf: Result<(data: Data, filename: String?), Error> = .failure(APIError.badResponse)
    private(set) var reportRequests: [Int] = []

    func fetchSessions() async throws -> [AttendanceSessionSummary] { sessions }

    func fetchReport(sessionId: Int) async throws -> SessionReport {
        reportRequests.append(sessionId)
        return try (reports.count > 1 ? reports.removeFirst() : reports[0]).get()
    }

    func downloadReportPDF(sessionId: Int) async throws -> (data: Data, filename: String?) { try pdf.get() }
}

@Suite("Attendance reports")
struct AttendanceReportDecodingTests {
    @Test func decodesServerReport() throws {
        let report = try decodeReport()
        #expect(report.session.isFinal)
        #expect(report.summary == .init(totalStudents: 4, present: 2, absent: 2, attendancePercentage: 50))
        #expect(report.summary.percentageText == "50%")
        #expect(report.presentStudents.map(\.name) == ["Aarav Sharma", "Riya Verma"])
        #expect(report.presentStudents.map(\.source) == [.card, .card])
        #expect(report.absentStudents.map(\.rollNumber) == ["ECE003", "ECE004"])
        // Absent students have no scan data.
        #expect(report.absentStudents.allSatisfy { $0.markedAt == nil && $0.cardUid == nil })
    }

    @Test func emptyRosterAndOlderServersDecode() throws {
        let empty = reportJSON
            .replacingOccurrences(of: #""attendancePercentage":50.0"#, with: #""attendancePercentage":null"#)
            .replacingOccurrences(of: #""notEnrolledAttendees":[],"#, with: "")
            .replacingOccurrences(of: #""status":"final""#, with: #""status":"provisional""#)
        let report = try decodeReport(empty)
        #expect(report.summary.percentageText == "—")
        #expect(report.notEnrolledAttendees.isEmpty)
        #expect(!report.session.isFinal)
    }

    @Test func percentageShowsOneDecimalWhenNeeded() {
        #expect(SessionReport.Summary(totalStudents: 3, present: 1, absent: 2, attendancePercentage: 33.3)
            .percentageText == "33.3%")
    }

    @Test func decodesSessionSummary() throws {
        let session = try JSONDecoder.campusOS.decode(AttendanceSessionSummary.self, from: Data(sessionJSON.utf8))
        #expect(session.isOpen)
        #expect(session.presentCount == 1)
        #expect(session.openedBy == nil)
    }

    @Test(arguments: [
        ("AttendX_ECE_Session_14.pdf", "AttendX_ECE_Session_14.pdf"),
        ("../../evil/AttendX.pdf", "AttendX.pdf"),
        (nil, "AttendX_Session_7.pdf"),
        ("report.exe", "AttendX_Session_7.pdf"),
        (".pdf", "AttendX_Session_7.pdf"),
    ] as [(String?, String)])
    func safeFilename(suggested: String?, expected: String) {
        #expect(AttendanceReportStore.safeFilename(suggested, sessionId: 7) == expected)
    }
}

@MainActor
@Suite("AttendanceReportStore")
struct AttendanceReportStoreTests {
    private let service = FakeReportService()

    @Test func loadsReportFromServer() async throws {
        service.reports = [.success(try decodeReport())]
        let store = AttendanceReportStore(service: service)
        await store.loadReport(sessionId: 14)
        #expect(store.reportState == .loaded)
        #expect(store.report?.summary.present == 2)
        #expect(service.reportRequests == [14])
    }

    @Test func failedRefreshKeepsLastReport() async throws {
        service.reports = [.success(try decodeReport()), .failure(APIError.unreachable)]
        let store = AttendanceReportStore(service: service)
        await store.loadReport(sessionId: 14)
        await store.loadReport(sessionId: 14)
        #expect(store.report?.session.id == 14)
        #expect(store.reportState.errorMessage != nil)
    }

    @Test func switchingSessionsClearsTheOldReport() async throws {
        service.reports = [.success(try decodeReport()), .failure(APIError.notFound("No such session."))]
        let store = AttendanceReportStore(service: service)
        await store.loadReport(sessionId: 14)
        await store.loadReport(sessionId: 99)
        #expect(store.report == nil)
        #expect(store.reportState.errorMessage == "No such session.")
    }

    @Test func forbiddenReportShowsServerMessage() async {
        service.reports = [.failure(APIError.invalid("You do not have permission to perform this action."))]
        let store = AttendanceReportStore(service: service)
        await store.loadReport(sessionId: 14)
        #expect(store.report == nil)
        #expect(store.reportState.errorMessage == "You do not have permission to perform this action.")
    }

    @Test func exportWritesPDFWithServerFilename() async throws {
        service.pdf = .success((Data("%PDF-1.4 test".utf8), "AttendX_ECE_Session_14.pdf"))
        let store = AttendanceReportStore(service: service)
        let url = try await store.exportPDF(sessionId: 14)
        #expect(url.lastPathComponent == "AttendX_ECE_Session_14.pdf")
        #expect(try Data(contentsOf: url) == Data("%PDF-1.4 test".utf8))
        #expect(!store.isExporting)
        try? FileManager.default.removeItem(at: url)
    }

    @Test func exportRejectsNonPDF() async {
        service.pdf = .success((Data("{\"detail\":\"oops\"}".utf8), "AttendX.pdf"))
        let store = AttendanceReportStore(service: service)
        await #expect(throws: APIError.badResponse) { try await store.exportPDF(sessionId: 14) }
    }

    @Test func resetClearsEverything() async throws {
        service.reports = [.success(try decodeReport())]
        let store = AttendanceReportStore(service: service)
        await store.loadReport(sessionId: 14)
        store.reset()
        #expect(store.report == nil)
        #expect(store.sessions.isEmpty)
        #expect(store.reportState == .idle)
    }
}
