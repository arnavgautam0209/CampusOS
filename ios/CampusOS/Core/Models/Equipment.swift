import Foundation

struct Equipment: Identifiable, Codable, Hashable {
    let id: String
    let name: String
    let category: String
    let isAvailable: Bool
    /// SkillPass certification IDs needed to operate this equipment.
    var requiredCertifications: [String] = []
}

extension Equipment {
    // Defined in an extension so the memberwise initializer is kept.
    // Older servers don't send requiredCertifications, so it is optional here.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        category = try container.decode(String.self, forKey: .category)
        isAvailable = try container.decode(Bool.self, forKey: .isAvailable)
        requiredCertifications = try container.decodeIfPresent([String].self, forKey: .requiredCertifications) ?? []
    }
}
