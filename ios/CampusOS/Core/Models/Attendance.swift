import Foundation

/// Faculty dashboard from GET /api/v1/attendance/live/.
struct AttendanceLive: Codable, Equatable {
    let generatedAt: Date
    let openSessions: [LiveSession]
    let readers: [CardReader]
    let recentScans: [ReaderScan]
    /// Rooms faculty can open a session in. Empty from servers older than this field.
    var classrooms: [LiveClassroom] = []
}

extension AttendanceLive {
    // In an extension so the memberwise initializer is kept.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        generatedAt = try container.decode(Date.self, forKey: .generatedAt)
        openSessions = try container.decode([LiveSession].self, forKey: .openSessions)
        readers = try container.decode([CardReader].self, forKey: .readers)
        recentScans = try container.decode([ReaderScan].self, forKey: .recentScans)
        classrooms = try container.decodeIfPresent([LiveClassroom].self, forKey: .classrooms) ?? []
    }
}

struct LiveClassroom: Codable, Identifiable, Equatable {
    let id: String
    let name: String
    let hasOpenSession: Bool
}

struct LiveSession: Codable, Identifiable, Equatable {
    let id: Int
    let title: String
    let classroomId: String
    let classroomName: String
    let openedBy: String?
    let openedAt: Date
    let closedAt: Date?
    let records: [SessionAttendee]
}

enum AttendanceSource: String, Codable {
    case card, manual
}

struct SessionAttendee: Codable, Identifiable, Equatable {
    let id: Int
    let student: String
    let studentUsername: String
    let source: AttendanceSource
    let markedAt: Date
    let deviceId: String?
}

struct CardReader: Codable, Identifiable, Equatable {
    let id: String
    let name: String
    let classroomId: String?
    /// Set for lab door readers (check-in) instead of classroomId.
    let labId: String?
    let isActive: Bool
    let hasKey: Bool
    let lastSeenAt: Date?
}

/// One tap on a reader, accepted or not.
struct ReaderScan: Codable, Identifiable, Equatable {
    let id: Int
    let deviceId: String
    let uid: String
    let result: ScanResult
    let student: String?
    /// The classroom or lab the reader sent.
    let classroomId: String
    let createdAt: Date
    /// Why lab access was denied ("no_booking", "too_early", ...).
    var reason: String? = nil

    var detail: String {
        guard result == .denied, let reason, !reason.isEmpty else { return result.label }
        let readable = [
            "no_booking": "no booking now",
            "too_early": "too early",
            "certification_required": "needs certification",
            "lab_closed": "lab closed",
            "awaiting_approval": "awaiting approval",
        ][reason] ?? reason.replacingOccurrences(of: "_", with: " ")
        return "\(result.label): \(readable)"
    }
}

enum ScanResult: String, Codable {
    case marked
    case duplicate
    case unknownCard = "unknown_card"
    case noSession = "no_session"
    case wrongClassroom = "wrong_classroom"
    case granted
    case alreadyCheckedIn = "already_checked_in"
    case denied
    case other

    // Results added on the server later still decode instead of breaking the feed.
    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = ScanResult(rawValue: raw) ?? .other
    }

    var label: String {
        switch self {
        case .marked: return "Marked present"
        case .duplicate: return "Already marked"
        case .unknownCard: return "Unknown card"
        case .noSession: return "No session open"
        case .wrongClassroom: return "Wrong classroom or lab"
        case .granted: return "Lab access granted"
        case .alreadyCheckedIn: return "Already checked in"
        case .denied: return "Lab access denied"
        case .other: return "Other"
        }
    }
}

/// The student's own attendance from GET /api/v1/attendance/mine/.
struct MyAttendance: Codable, Identifiable, Equatable {
    let id: Int
    let sessionId: Int
    let session: String
    let classroomId: String
    let classroomName: String
    let source: AttendanceSource
    let markedAt: Date
}

extension CampusRole {
    /// Faculty and administrators see the live dashboard. The server enforces this too.
    var isStaff: Bool { self != .student }
}
