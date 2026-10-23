import Foundation

protocol AttendanceService {
    func fetchLive() async throws -> AttendanceLive
    func fetchMine() async throws -> [MyAttendance]
}

struct APIAttendanceService: AttendanceService {
    let api: APIClient

    func fetchLive() async throws -> AttendanceLive {
        try await api.get("attendance/live/", authenticated: true)
    }

    func fetchMine() async throws -> [MyAttendance] {
        try await api.get("attendance/mine/", authenticated: true)
    }
}
