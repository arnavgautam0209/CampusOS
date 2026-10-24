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

    // MARK: Live updates

    private func provisional(present: [String], absent: [String], final: Bool = false) throws -> SessionReport {
        var report = try decodeReport()
        let student = { (name: String, here: Bool) in
            SessionReport.Student(rollNumber: name.uppercased(), name: name, username: name,
                                  status: here ? "present" : "absent", markedAt: here ? Date() : nil,
                                  source: here ? .card : nil, cardUid: nil)
        }
        report = SessionReport(
            session: .init(id: 17, title: "Embedded Systems Lecture 02", openedAt: report.session.openedAt,
                           closedAt: final ? Date() : nil, status: final ? "final" : "provisional"),
            classroom: report.classroom, faculty: report.faculty,
            summary: .init(totalStudents: present.count + absent.count, present: present.count, absent: absent.count,
                           attendancePercentage: nil),
            presentStudents: present.map { student($0, true) }, absentStudents: absent.map { student($0, false) },
            generatedAt: report.generatedAt)
        return report
    }

    @Test func studentWhoTapsWhileReportIsOpenIsHighlighted() async throws {
        service.reports = [.success(try provisional(present: ["riya"], absent: ["aarav"])),
                           .success(try provisional(present: ["aarav", "riya"], absent: [])),
                           .success(try provisional(present: ["aarav", "riya"], absent: []))]
        let clock = TestClock(Date(timeIntervalSince1970: 1_800_000_000))
        let store = AttendanceReportStore(service: service, now: { clock.now })

        await store.loadReport(sessionId: 17)
        #expect(store.newlyPresent.isEmpty)   // riya was already present when the report opened
        clock.advance(1)
        await store.loadReport(sessionId: 17)
        #expect(store.newlyPresent == ["aarav"])
        #expect(store.report?.absentStudents.isEmpty == true)
        clock.advance(AttendanceStore.highlightDuration)
        await store.loadReport(sessionId: 17)
        #expect(store.newlyPresent.isEmpty)
    }

    @Test func openingAnotherSessionDoesNotHighlightItsStudents() async throws {
        let other = try decodeReport()   // session 14
        service.reports = [.success(try provisional(present: [], absent: ["aarav"])), .success(other)]
        let store = AttendanceReportStore(service: service)
        await store.loadReport(sessionId: 17)
        await store.loadReport(sessionId: 14)
        #expect(store.newlyPresent.isEmpty)
    }

    @Test func pollingRefreshesAProvisionalReportUntilItIsFinal() async throws {
        service.reports = [.success(try provisional(present: [], absent: ["aarav"])),
                           .success(try provisional(present: ["aarav"], absent: [])),
                           .success(try provisional(present: ["aarav"], absent: [], final: true))]
        let store = AttendanceReportStore(service: service)
        await store.pollReport(sessionId: 17, every: .milliseconds(5))   // returns once the report is final
        #expect(service.reportRequests == [17, 17, 17])
        #expect(store.report?.session.isFinal == true)
    }

    @Test func closedSessionIsLoadedOnce() async throws {
        service.reports = [.success(try decodeReport())]
        let store = AttendanceReportStore(service: service)
        await store.pollReport(sessionId: 14, every: .milliseconds(5))
        #expect(service.reportRequests == [14])
    }

    @Test func pollingStopsWhenCancelled() async throws {
        service.reports = [.success(try provisional(present: [], absent: ["aarav"]))]
        let store = AttendanceReportStore(service: service)
        let task = Task { await store.pollReport(sessionId: 17, every: .milliseconds(10)) }
        try await Task.sleep(for: .milliseconds(80))
        task.cancel()
        await task.value
        let count = service.reportRequests.count
        #expect(count > 1)
        try await Task.sleep(for: .milliseconds(50))
        #expect(service.reportRequests.count == count)
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
