import Foundation

struct Lab: Identifiable, Codable, Hashable {
    let id: String
    let name: String
    let location: String
    let symbol: String
    let capacity: Int
    let equipment: [Equipment]
    let isOpenForBooking: Bool
    /// SkillPass certification IDs a student must hold to book this lab.
    var requiredCertifications: [String] = []
}

extension Lab {
    // Defined in an extension so the memberwise initializer is kept.
    // Older servers don't send requiredCertifications, so it is optional here.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        location = try container.decode(String.self, forKey: .location)
        symbol = try container.decode(String.self, forKey: .symbol)
        capacity = try container.decode(Int.self, forKey: .capacity)
        equipment = try container.decode([Equipment].self, forKey: .equipment)
        isOpenForBooking = try container.decode(Bool.self, forKey: .isOpenForBooking)
        requiredCertifications = try container.decodeIfPresent([String].self, forKey: .requiredCertifications) ?? []
    }
}

enum DemoLabs {
    static let all: [Lab] = [
        Lab(id: "LAB001", name: "Robotics Lab", location: "Block A · 204",
            symbol: "cpu", capacity: 30, equipment: [
                Equipment(id: "EQ001", name: "ESP32 Kits", category: "Embedded", isAvailable: true),
                Equipment(id: "EQ002", name: "Robotic Arm", category: "Robotics", isAvailable: true),
                Equipment(id: "EQ003", name: "Soldering Station", category: "Tools", isAvailable: true)
            ], isOpenForBooking: true),
        Lab(id: "LAB002", name: "Electronics Lab", location: "Block B · 102",
            symbol: "bolt", capacity: 40, equipment: [
                Equipment(id: "EQ004", name: "Oscilloscope", category: "Testing", isAvailable: true),
                Equipment(id: "EQ005", name: "Multimeter", category: "Testing", isAvailable: true)
            ], isOpenForBooking: true),
        Lab(id: "LAB003", name: "3D Printing Lab", location: "Innovation Centre",
            symbol: "printer", capacity: 15, equipment: [
                Equipment(id: "EQ006", name: "3D Printer", category: "Fabrication", isAvailable: false)
            ], isOpenForBooking: false),
        Lab(id: "LAB004", name: "AI & Computing Lab", location: "Block C · 301",
            symbol: "desktopcomputer", capacity: 50, equipment: [
                Equipment(id: "EQ007", name: "GPU Workstation", category: "Computing", isAvailable: true)
            ], isOpenForBooking: true)
    ]
}
