import Foundation

protocol AttendanceService {
    func fetchLive() async throws -> AttendanceLive
    func fetchMine() async throws -> [MyAttendance]
    func openSession(classroomId: String, title: String) async throws -> LiveSession
    func closeSession(id: Int) async throws -> LiveSession
}

struct APIAttendanceService: AttendanceService {
    let api: APIClient

    func fetchLive() async throws -> AttendanceLive {
        try await api.get("attendance/live/", authenticated: true)
    }

    func fetchMine() async throws -> [MyAttendance] {
        try await api.get("attendance/mine/", authenticated: true)
    }

    func openSession(classroomId: String, title: String) async throws -> LiveSession {
        struct Request: Encodable { let classroomId: String; let title: String }
        return try await api.post("attendance/sessions/",
                                  body: Request(classroomId: classroomId, title: title), authenticated: true)
    }

    func closeSession(id: Int) async throws -> LiveSession {
        try await api.post("attendance/sessions/\(id)/close/", authenticated: true)
    }
}
