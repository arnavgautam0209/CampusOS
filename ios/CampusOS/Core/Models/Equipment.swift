import Foundation

struct Equipment: Identifiable, Codable, Hashable {
    let id: String
    let name: String
    let category: String
    let isAvailable: Bool
}
