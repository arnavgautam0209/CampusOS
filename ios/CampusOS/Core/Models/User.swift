import Foundation

enum CampusRole: String, Codable, CaseIterable {
    case student, faculty, administrator
}

struct CampusUser: Identifiable, Codable {
    let id: String
    let name: String
    let email: String
    let role: CampusRole
    /// Login name (e.g. a roll number). Older servers don't send it.
    var username: String? = nil
}
