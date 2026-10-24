import Foundation
import Combine

/// A row in the faculty session list from GET /api/v1/attendance/sessions/.
struct AttendanceSessionSummary: Codable, Identifiable, Equatable {
    let id: Int
    let title: String
    let classroomId: String
    let classroomName: String
    let openedBy: String?
    let openedAt: Date
    let closedAt: Date?
    let presentCount: Int

    var isOpen: Bool { closedAt == nil }
}

/// GET /api/v1/attendance/sessions/{id}/report/. All counts come from the server;
/// the app never works out who was present itself.
struct SessionReport: Codable, Equatable {
    struct Session: Codable, Equatable {
        let id: Int
        let title: String
        let openedAt: Date
        let closedAt: Date?
        /// "final" once the session is closed, "provisional" while it's open.
        let status: String

        var isFinal: Bool { status == "final" }
    }

    struct Classroom: Codable, Equatable {
        let id: String
        let name: String
    }

    struct Faculty: Codable, Equatable {
        let name: String?
        let username: String?
    }

    struct Summary: Codable, Equatable {
        let totalStudents: Int
        let present: Int
        let absent: Int
        /// nil when nobody is enrolled.
        let attendancePercentage: Double?
    }

    struct Student: Codable, Identifiable, Equatable {
        let rollNumber: String
        let name: String
        let username: String
        let status: String
        // Only present students have these.
        var markedAt: Date?
        var source: AttendanceSource?
        var cardUid: String?

        var id: String { username }
    }

    let session: Session
    let classroom: Classroom
    let faculty: Faculty
    let summary: Summary
    let presentStudents: [Student]
    let absentStudents: [Student]
    /// Tapped in but not on the class roster; not counted in the summary.
    var notEnrolledAttendees: [Student] = []
    let generatedAt: Date
}

extension SessionReport {
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        session = try container.decode(Session.self, forKey: .session)
        classroom = try container.decode(Classroom.self, forKey: .classroom)
        faculty = try container.decode(Faculty.self, forKey: .faculty)
        summary = try container.decode(Summary.self, forKey: .summary)
        presentStudents = try container.decode([Student].self, forKey: .presentStudents)
        absentStudents = try container.decode([Student].self, forKey: .absentStudents)
        notEnrolledAttendees = try container.decodeIfPresent([Student].self, forKey: .notEnrolledAttendees) ?? []
        generatedAt = try container.decode(Date.self, forKey: .generatedAt)
    }
}

extension SessionReport.Summary {
    var percentageText: String {
        guard let attendancePercentage else { return "—" }
        return "\(attendancePercentage.formatted(.number.precision(.fractionLength(0...1))))%"
    }
}

/// Read-only report endpoints, kept apart from AttendanceService (which opens and closes sessions).
protocol AttendanceReportService {
    func fetchSessions() async throws -> [AttendanceSessionSummary]
    func fetchReport(sessionId: Int) async throws -> SessionReport
    func downloadReportPDF(sessionId: Int) async throws -> (data: Data, filename: String?)
}

extension APIAttendanceService: AttendanceReportService {
    func fetchSessions() async throws -> [AttendanceSessionSummary] {
        try await api.get("attendance/sessions/", authenticated: true)
    }

    func fetchReport(sessionId: Int) async throws -> SessionReport {
        try await api.get("attendance/sessions/\(sessionId)/report/", authenticated: true)
    }

    func downloadReportPDF(sessionId: Int) async throws -> (data: Data, filename: String?) {
        // JSON is listed too so error responses (403, 404) still come back readable.
        try await api.download("attendance/sessions/\(sessionId)/report/pdf/",
                               accept: "application/pdf, application/json", authenticated: true)
    }
}

/// Faculty attendance reports: the session list, one session's report, and its PDF.
@MainActor
final class AttendanceReportStore: ObservableObject {
    @Published private(set) var sessions: [AttendanceSessionSummary] = []
    @Published private(set) var sessionsState: LoadState = .idle
    @Published private(set) var report: SessionReport?
    @Published private(set) var reportState: LoadState = .idle
    @Published private(set) var isExporting = false

    private let service: AttendanceReportService
    private let fileManager: FileManager

    init(service: AttendanceReportService, fileManager: FileManager = .default) {
        self.service = service
        self.fileManager = fileManager
    }

    func loadSessions() async {
        if sessions.isEmpty { sessionsState = .loading }
        do {
            sessions = try await service.fetchSessions()
            sessionsState = .loaded
        } catch {
            sessionsState = .failed(error.localizedDescription)
        }
    }

    func loadReport(sessionId: Int) async {
        if report?.session.id != sessionId {
            report = nil
            reportState = .loading
        }
        do {
            let next = try await service.fetchReport(sessionId: sessionId)
            report = next
            reportState = .loaded
        } catch {
            // A refresh that fails keeps the last good report on screen.
            reportState = .failed(error.localizedDescription)
        }
    }

    /// Downloads the server-generated PDF to a temporary file for Quick Look and the share sheet.
    func exportPDF(sessionId: Int) async throws -> URL {
        isExporting = true
        defer { isExporting = false }
        let (data, suggested) = try await service.downloadReportPDF(sessionId: sessionId)
        guard data.starts(with: Data("%PDF".utf8)) else { throw APIError.badResponse }
        let folder = fileManager.temporaryDirectory.appendingPathComponent("AttendX", isDirectory: true)
        try fileManager.createDirectory(at: folder, withIntermediateDirectories: true)
        let url = folder.appendingPathComponent(Self.safeFilename(suggested, sessionId: sessionId))
        try data.write(to: url, options: .atomic)
        return url
    }

    /// The server's filename without any path parts, or a fallback.
    nonisolated static func safeFilename(_ suggested: String?, sessionId: Int) -> String {
        let name = (suggested ?? "").split(separator: "/").last.map(String.init) ?? ""
        let cleaned = name.filter { $0.isLetter || $0.isNumber || "-_.".contains($0) }
        guard cleaned.lowercased().hasSuffix(".pdf"), cleaned.count > 4, !cleaned.hasPrefix(".") else {
            return "AttendX_Session_\(sessionId).pdf"
        }
        return cleaned
    }

    func reset() {
        sessions = []
        sessionsState = .idle
        report = nil
        reportState = .idle
    }
}
